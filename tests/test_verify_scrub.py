"""Tests for verify_scrub.py. Run from the repo folder:  python -m unittest -v"""
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from archon.scrubber import scrubber, verify_scrub

NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
SHEET = ('<worksheet %s><sheetData>'
         '<row r="1"><c r="A1" t="s"><v>0</v></c></row>'
         '<row r="2"><c r="A2" t="s"><v>1</v></c><c r="B2"><v>5000</v></c>'
         '<c r="C2"><f>B2*2</f><v>10000</v></c></row></sheetData></worksheet>' % NS)
SHARED = '<sst %s><si><t>Customer</t></si><si><t>Acme Test Corp</t></si></sst>' % NS
VBA = os.urandom(2048)


def make(path, with_vba=True):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/workbook.xml", '<workbook %s><sheets><sheet name="S" sheetId="1"/></sheets></workbook>' % NS)
        z.writestr("xl/worksheets/sheet1.xml", SHEET)
        z.writestr("xl/sharedStrings.xml", SHARED)
        if with_vba:
            z.writestr("xl/vbaProject.bin", VBA)


def rewrite(src, dst, part, data):
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
        for item in zin.infolist():
            zout.writestr(item, data if item.filename == part else zin.read(item))


class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.orig, self.out = d / "a.xlsm", d / "a_scrubbed.xlsm"
        make(self.orig)
        scrubber.scrub_file(self.orig, self.out)

    def tearDown(self):
        self.tmp.cleanup()

    def statuses(self, orig=None, out=None, words=()):
        return [s for s, _ in verify_scrub.verify(orig or self.orig, out or self.out, words)]

    def test_good_scrub_passes_every_check(self):
        self.assertEqual(set(self.statuses(words=["Acme"])), {"OK"})

    def test_changed_vba_fails(self):
      bad = Path(self.tmp.name) / "bad.xlsm"
      flipped = bytes([VBA[-1] ^ 0xFF])  # guaranteed different from the last byte, whatever it is
      rewrite(self.out, bad, "xl/vbaProject.bin", VBA[:-1] + flipped)
      self.assertIn("FAIL", self.statuses(out=bad))

    def test_changed_formula_fails(self):
        bad = Path(self.tmp.name) / "bad.xlsm"
        rewrite(self.out, bad, "xl/worksheets/sheet1.xml", SHEET.replace("B2*2", "B2*3").encode())
        self.assertIn("FAIL", self.statuses(out=bad))

    def test_word_left_behind_fails(self):
        # an unscrubbed copy still contains the name, so the check must fail
        self.assertIn("FAIL", self.statuses(out=self.orig, words=["Acme"]))

    def test_utf16_sensitive_word_fails(self):
        bad = Path(self.tmp.name) / "utf16.xlsm"
        payload = b"Private Customer: " + "Acme".encode("utf-16le")
        rewrite(self.out, bad, "xl/sharedStrings.xml", payload)
        self.assertIn("FAIL", self.statuses(out=bad, words=["Acme"]))

    def test_sensitive_word_in_preserved_vba_fails(self):
        source = Path(self.tmp.name) / "macro_source.xlsm"
        output = Path(self.tmp.name) / "macro_scrubbed.xlsm"
        macro = b"\xd0\xcf\x11\xe0 VBA payload: Acme Customer Record"

        rewrite(self.orig, source, "xl/vbaProject.bin", macro)
        scrubber.scrub_file(source, output)

        results = verify_scrub.verify(source, output, ["Acme"])
        self.assertIn("FAIL", [status for status, _ in results])
        self.assertTrue(any(
            status == "FAIL" and "FOUND in xl/vbaProject.bin" in message
            for status, message in results
        ))

    def test_file_without_vba_is_skipped_not_passed(self):
        plain, plain_out = Path(self.tmp.name) / "p.xlsx", Path(self.tmp.name) / "p_s.xlsx"
        make(plain, with_vba=False)
        scrubber.scrub_file(plain, plain_out)
        self.assertIn("SKIP", self.statuses(orig=plain, out=plain_out))

    def test_exit_codes(self):
        self.assertEqual(verify_scrub.main([str(self.orig), str(self.out)]), 0)
        self.assertEqual(verify_scrub.main([str(self.orig), str(self.orig), "Acme"]), 1)


if __name__ == "__main__":
    unittest.main()
