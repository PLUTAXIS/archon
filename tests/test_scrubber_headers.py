"""Tests for the --keep-headers option of scrubber.py. Run:  python -m unittest -v"""
import io
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from archon.scrubber import scrubber

NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
SHEET = ('<worksheet %s><sheetData>'
         '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1"><v>2024</v></c></row>'
         '<row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2"><v>5000</v></c><c r="C2"><f>B2*2</f><v>10000</v></c></row>'
         '<row r="3"><c r="A3" t="s"><v>0</v></c><c r="B3"><v>7000</v></c></row>'
         '<row r="4"><c r="A4" t="inlineStr"><is><t>Globex Corp</t></is></c></row>'
         '</sheetData></worksheet>' % NS)
SHARED = ('<sst %s><si><t>Customer</t></si><si><t>Gross_Revenue</t></si>'
          '<si><t>Acme Test Corp</t></si></sst>' % NS)

SHEET_SINGLE_QUOTE = ('<worksheet %s><sheetData>'
         '<row r="1"><c r="A1" t="s"><v>0</v></c></row>'
         "<row r=\"2\"><c r=\"A2\" t='s'><v>0</v></c></row>"
         '</sheetData></worksheet>' % NS)
SHARED_SINGLE = '<sst %s><si><t>Customer</t></si></sst>' % NS


def make(path, sheet=SHEET, shared=SHARED):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/workbook.xml", '<workbook %s><sheets><sheet name="S" sheetId="1"/></sheets></workbook>' % NS)
        z.writestr("xl/worksheets/sheet1.xml", sheet)
        z.writestr("xl/sharedStrings.xml", shared)


class KeepHeadersTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = Path(self.tmp.name) / "m.xlsx"
        make(self.src)

    def tearDown(self):
        self.tmp.cleanup()

    def run_scrub(self, keep, src=None):
        src = src or self.src
        out = Path(self.tmp.name) / ("keep.xlsx" if keep else "mask.xlsx")
        if keep:
            scrubber.scrub_file(src, out, keep_headers=True)
        else:
            scrubber.scrub_file(src, out)
        z = zipfile.ZipFile(out)
        return z.read("xl/sharedStrings.xml").decode(), z.read("xl/worksheets/sheet1.xml").decode(), z

    def test_default_still_masks_headers(self):
        shared, _, _ = self.run_scrub(keep=False)
        for word in ("Customer", "Gross_Revenue", "Acme"):
            self.assertNotIn(word, shared)

    def test_keep_headers_keeps_row_one_text_only(self):
        shared, sheet, z = self.run_scrub(keep=True)
        self.assertIn("Customer", shared)
        self.assertIn("Gross_Revenue", shared)
        self.assertNotIn("Acme", shared)          # row 2 text is still masked
        self.assertNotIn("Globex", sheet)         # inline text in a data row is masked
        for n in z.namelist():
            if n.endswith(".xml"):
                ET.fromstring(z.read(n))          # still well-formed

    def test_header_word_reused_in_a_data_row_is_masked(self):
        _, sheet, _ = self.run_scrub(keep=True)
        self.assertRegex(sheet, r'<c r="A3" t="inlineStr"><is><t>Text_\d+</t></is></c>')
        self.assertIn('<c r="A1" t="s"><v>0</v></c>', sheet)  # the header cell itself is untouched

    def test_numbers_and_formulas_are_handled_as_before(self):
        _, sheet, _ = self.run_scrub(keep=True)
        self.assertNotIn("<v>2024</v>", sheet)    # a number in row 1 is still masked
        self.assertNotIn("<v>5000</v>", sheet)
        self.assertIn("<f>B2*2</f>", sheet)

    def test_command_line_flag(self):
        out = Path(self.tmp.name) / "cli.xlsx"
        with redirect_stdout(io.StringIO()) as buf:
            code = scrubber.main([str(self.src), "-o", str(out), "--keep-headers"])
        self.assertEqual(code, 0)
        self.assertIn("Customer", zipfile.ZipFile(out).read("xl/sharedStrings.xml").decode())
        self.assertIn("KEPT readable", buf.getvalue())
        with redirect_stdout(io.StringIO()) as buf2:
            scrubber.main([str(self.src), "-o", str(out)])
        self.assertNotIn("KEPT readable", buf2.getvalue())

    def test_single_quoted_type_attribute_is_recognized(self):
        # CWE-201 regression: a data cell with t='s' (single-quoted) reusing a header's
        # shared-string index must still be masked, not silently left showing header text
        # with a mismatched type attribute.
        single_src = Path(self.tmp.name) / "single.xlsx"
        make(single_src, sheet=SHEET_SINGLE_QUOTE, shared=SHARED_SINGLE)
        _, sheet, _ = self.run_scrub(keep=True, src=single_src)
        self.assertRegex(sheet, r'<c r="A2" t="inlineStr"><is><t>Text_\d+</t></is></c>')
        self.assertNotIn("Customer", sheet)

    def test_single_and_double_quoted_numbers_both_masked(self):
        sheet = ('<worksheet %s><sheetData>'
                 "<row r=\"1\"><c r=\"A1\" t='n'><v>42</v></c></row>"
                 '</sheetData></worksheet>' % NS)
        src = Path(self.tmp.name) / "num.xlsx"
        make(src, sheet=sheet, shared='<sst %s></sst>' % NS)
        _, out_sheet, _ = self.run_scrub(keep=False, src=src)
        self.assertNotIn("<v>42</v>", out_sheet)


if __name__ == "__main__":
    unittest.main()
