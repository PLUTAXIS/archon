"""Tests for scrubber.py. Run from the repo root:  python -m unittest discover -s tests -v"""
import ast
import hashlib
import io
import os
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from archon.scrubber import scrubber

SCRIPT = os.path.join(ROOT, "archon", "scrubber", "scrubber.py")


def script_text():
    with open(SCRIPT, encoding="utf-8") as f:
        return f.read()
VBA = b"\xd0\xcf\x11\xe0 fake vba project: Secret macro, Jane Doe \x00\x01\x02"

SHEET = (
    '<?xml version="1.0" encoding="UTF-8"?><worksheet><sheetData><row r="1">'
    '<c r="A1" t="s"><v>0</v></c>'
    '<c r="B1"><v>145000.50</v></c>'
    '<c r="C1"><f>B1*2</f><v>290001</v></c>'
    '<c r="D1" t="inlineStr"><is><t>Jane Doe</t></is></c>'
    '<c r="E1" t="b"><v>1</v></c>'
    '<c r="F1" s="3"/>'
    '<c r="G1"><v>-1.5E-3</v></c>'
    '<c r="H1"><v>0</v></c>'
    '<c r="I1" t="str"><f>A1&amp;"x"</f><v>Acme Corp x</v></c>'
    '<c r="J1"><f t="shared" si="0"/><v>777</v></c>'
    '<c r="K1"><v>145000.50</v></c>'
    '</row></sheetData></worksheet>')
PARTS = {
    "[Content_Types].xml": b"<Types/>",
    "xl/workbook.xml": b'<workbook><sheets><sheet name="Payroll Acme" sheetId="1"/></sheets></workbook>',
    "xl/worksheets/sheet1.xml": SHEET.encode(),
    "xl/sharedStrings.xml": b'<sst count="2"><si><t>Acme Corp</t></si>'
                            b'<si><r><t>Rich</t></r><r><t> Text</t></r></si></sst>',
    "docProps/core.xml": b"<cp><dc:creator>Jane Doe</dc:creator>"
                         b"<cp:lastModifiedBy>John Smith</cp:lastModifiedBy></cp>",
    "docProps/app.xml": b"<Properties><Company>Acme Corp</Company></Properties>",
    "xl/comments1.xml": b"<comments><authors><author>Jane Doe</author></authors><commentList>"
                        b'<comment ref="A1"><text><r><t>Salary is 99999</t></r></text></comment>'
                        b"</commentList></comments>",
    "xl/charts/chart1.xml": b"<c:chartSpace><a:t>Acme Revenue</a:t><c:numRef><c:f>S!$B$1</c:f>"
                            b"<c:numCache><c:pt><c:v>145000.5</c:v></c:pt></c:numCache></c:numRef>"
                            b"</c:chartSpace>",
    "xl/vbaProject.bin": VBA,
}


def build(path, parts=PARTS):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in parts.items():
            z.writestr(name, data)


def read_all(path):
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in z.namelist()}


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class ScrubTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.src = os.path.join(self.dir.name, "book.xlsm")
        self.dst = os.path.join(self.dir.name, "book.scrubbed.xlsm")
        build(self.src)

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = scrubber.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def scrub(self):
        code, out, _ = self.run_cli(self.src)
        self.assertEqual(code, 0)
        return read_all(self.dst), out

    def test_no_confidential_text_survives_in_scrubbed_parts(self):
        parts, _ = self.scrub()
        for name, data in parts.items():
            if name in ("xl/vbaProject.bin", "xl/workbook.xml"):  # kept on purpose
                continue
            for secret in (b"Acme", b"Jane", b"John", b"Smith", b"145000", b"99999", b"Rich"):
                self.assertNotIn(secret, data, "%r leaked in %s" % (secret, name))

    def test_formulas_are_kept_and_their_saved_results_removed(self):
        sheet = self.scrub()[0]["xl/worksheets/sheet1.xml"].decode()
        self.assertIn("<f>B1*2</f>", sheet)
        self.assertIn('<f>A1&amp;"x"</f>', sheet)
        self.assertIn('<f t="shared" si="0"/>', sheet)
        for gone in ("290001", "Acme Corp x", "777"):
            self.assertNotIn(gone, sheet)

    def test_vba_is_byte_identical(self):
        self.assertEqual(self.scrub()[0]["xl/vbaProject.bin"], VBA)

    def test_sheet_names_and_part_list_are_preserved(self):
        parts, _ = self.scrub()
        self.assertEqual(list(parts), list(PARTS))
        self.assertIn(b"Payroll Acme", parts["xl/workbook.xml"])

    def test_numbers_keep_their_shape_and_equal_numbers_match(self):
        sheet = self.scrub()[0]["xl/worksheets/sheet1.xml"].decode()
        import re
        b1 = re.search(r'<c r="B1"><v>(.*?)</v>', sheet).group(1)
        k1 = re.search(r'<c r="K1"><v>(.*?)</v>', sheet).group(1)
        g1 = re.search(r'<c r="G1"><v>(.*?)</v>', sheet).group(1)
        h1 = re.search(r'<c r="H1"><v>(.*?)</v>', sheet).group(1)
        self.assertRegex(b1, r"^[1-9]\d{5}\.\d\d$")  # 6 digits, 2 decimals, like 145000.50
        self.assertEqual(b1, k1)                      # same input -> same dummy
        self.assertRegex(g1, r"^-[1-9]\.\dE-3$")      # sign and exponent kept
        self.assertEqual(h1, "0")                     # zero stays zero

    def test_empty_cell_untouched_and_neighbours_not_swallowed(self):
        sheet = self.scrub()[0]["xl/worksheets/sheet1.xml"].decode()
        self.assertIn('<c r="F1" s="3"/>', sheet)
        self.assertIn('<c r="E1" t="b"><v>1</v></c>', sheet)
        self.assertEqual(sheet.count("<c "), 11)

    def test_same_text_gets_same_dummy_and_different_text_differs(self):
        import re
        parts = dict(PARTS)
        parts["xl/sharedStrings.xml"] = (b"<sst><si><t>Acme Corp</t></si><si><t>Other</t></si>"
                                         b"<si><t>Acme Corp</t></si></sst>")
        build(self.src, parts)
        strings = self.scrub()[0]["xl/sharedStrings.xml"].decode()
        dummies = re.findall(r"<si><t>(Text_\d+)</t></si>", strings)
        self.assertEqual(len(dummies), 3)
        self.assertEqual(dummies[0], dummies[2])   # same text -> same dummy
        self.assertNotEqual(dummies[0], dummies[1])  # different text -> different dummy

    def test_original_file_is_never_changed(self):
        before = sha(self.src)
        self.scrub()
        self.assertEqual(sha(self.src), before)

    def test_output_is_a_valid_zip_and_summary_warns_about_vba(self):
        _, out = self.scrub()
        with zipfile.ZipFile(self.dst) as z:
            self.assertIsNone(z.testzip())
        self.assertIn("VBA macro code", out)
    def test_unknown_component_is_preserved_and_reported(self):
        parts = dict(PARTS)
        name = "xl/customData/private-records.xml"
        payload = b"<records>Confidential Customer Record</records>"
        parts[name] = payload
        build(self.src, parts)

        output, out = self.scrub()
        self.assertEqual(output[name], payload)
        self.assertIn(name, out)
        self.assertIn("uninspected workbook component copied unchanged", out)
        self.assertIn("SANITIZATION STATUS: REVIEW_REQUIRED", out)

    def test_two_runs_use_different_random_digits(self):
        first = self.scrub()[0]["xl/worksheets/sheet1.xml"]
        outs = {self.scrub()[0]["xl/worksheets/sheet1.xml"] for _ in range(5)}
        self.assertGreater(len(outs | {first}), 1)

    def test_refuses_to_overwrite_original(self):
        code, _, err = self.run_cli(self.src, "-o", self.src)
        self.assertEqual(code, 1)
        self.assertIn("different file", err)

    def test_missing_file_and_non_zip_give_plain_errors(self):
        code, _, err = self.run_cli(os.path.join(self.dir.name, "nope.xlsx"))
        self.assertEqual((code, "not found" in err), (1, True))
        fake = os.path.join(self.dir.name, "old.xls")
        with open(fake, "wb") as f:
            f.write(b"\xd0\xcf\x11\xe0 not a zip")
        code, _, err = self.run_cli(fake)
        self.assertEqual((code, "password" in err), (1, True))

    def test_xlsb_style_zip_is_rejected_and_leaves_no_output(self):
        xlsb = os.path.join(self.dir.name, "b.xlsb")
        build(xlsb, {"xl/workbook.bin": b"x"})
        code, _, err = self.run_cli(xlsb)
        self.assertEqual(code, 1)
        self.assertIn("xlsb", err)
        self.assertFalse(os.path.exists(os.path.join(self.dir.name, "b.scrubbed.xlsb")))


class TrustTests(unittest.TestCase):
    """The things a security team will check."""

    def test_only_allowed_standard_library_imports(self):
        tree = ast.parse(script_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        allowed = {"argparse", "os", "random", "re", "secrets", "sys", "zipfile"}
        self.assertEqual(imported - allowed, set())

    def test_no_network_or_process_words_anywhere_in_the_file(self):
        text = script_text().lower()
        for word in ("socket", "urllib", "http", "requests", "subprocess", "ftplib", "smtplib",
                     "eval(", "exec(", "__import__"):
            self.assertNotIn(word, text)

    def test_file_stays_short_enough_to_audit(self):
        self.assertLessEqual(len(script_text().splitlines()), 250)


@unittest.skipUnless(__import__("importlib").util.find_spec("openpyxl"), "openpyxl not installed")
class RealWorkbookTest(unittest.TestCase):
    def test_openpyxl_workbook_formulas_identical_and_data_masked(self):
        import openpyxl
        with tempfile.TemporaryDirectory() as d:
            src, dst = os.path.join(d, "r.xlsx"), os.path.join(d, "r.scrubbed.xlsx")
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Model"
            ws["A1"], ws["B1"], ws["C1"] = "Client: Globex", "Revenue", "Tax"
            for r in range(2, 52):
                ws.cell(r, 1, "Person %d" % r)
                ws.cell(r, 2, 1000 * r + 0.25)
                ws.cell(r, 3, "=B%d*0.2" % r)
            ws["C30"] = 31234.5  # a hand-typed number in the middle of formulas
            ws2 = wb.create_sheet("Totals")
            ws2["A1"] = "=SUM(Model!B2:B51)"
            wb.properties.creator = "Jane Doe"
            wb.save(src)
            self.assertEqual(scrubber.main([src]), 0)
            a, b = openpyxl.load_workbook(src), openpyxl.load_workbook(dst)
            self.assertEqual(a.sheetnames, b.sheetnames)
            self.assertNotEqual(b.properties.creator, "Jane Doe")
            for name in a.sheetnames:
                for row in a[name].iter_rows():
                    for cell in row:
                        other = b[name][cell.coordinate]
                        if isinstance(cell.value, str) and cell.value.startswith("="):
                            self.assertEqual(cell.value, other.value)  # formulas identical
                        elif cell.value is not None:
                            self.assertNotEqual(cell.value, other.value)  # data masked
            # The hand-typed number is still a number, not a formula (so bug-spotting still works)
            self.assertIsInstance(b["Model"]["C30"].value, (int, float))


if __name__ == "__main__":
    unittest.main()
