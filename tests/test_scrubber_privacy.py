"""Scrubber privacy rules added after testing with real Excel files.

Each part below is a cut-down copy of what Excel writes. The point of every test:
no confidential value leaves, and the same value gets the same dummy everywhere,
so the audit logic (IF(B2="Closed",...)) still lines up after scrubbing.
"""

import os
import re
import tempfile
import unittest
import zipfile

from archon.scrubber import scrubber

SECRETS = ("Acme", "Closed", "Confidential", "Bob", "Deal", "145000", "logo.png")

PARTS = {
    "xl/workbook.xml": '<workbook><x15ac:absPath url="C:\\Users\\Bob\\Deal\\"/><sheets/></workbook>',
    "xl/sharedStrings.xml": "<sst><si><t>Status</t></si><si><t>Closed</t></si><si><t>Acme</t></si></sst>",
    "xl/worksheets/sheet1.xml": (
        '<worksheet><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c></row>'
        '<row r="2"><c r="A2" t="s"><v>1</v></c><c r="B2"><f>IF(A2="Closed",1,0)</f><v>1</v></c>'
        '<c r="C2" t="str"><f>"Acme"&amp;"-"&amp;A2</f><v>x</v></c></row></sheetData>'
        '<dataValidations><dataValidation type="list"><formula1>"Closed,Acme"</formula1>'
        "</dataValidation></dataValidations>"
        "<headerFooter><oddHeader>&amp;CConfidential Acme</oddHeader></headerFooter></worksheet>"),
    "xl/pivotCache/pivotCacheDefinition1.xml": (
        '<pivotCacheDefinition refreshedBy="Bob"><cacheFields><cacheField name="Status">'
        '<sharedItems><s v="Closed"/><s v="Acme"/></sharedItems></cacheField>'
        '<cacheField name="Revenue"><sharedItems containsNumber="1" minValue="145000" maxValue="245000"/>'
        "</cacheField></cacheFields></pivotCacheDefinition>"),
    "xl/pivotCache/pivotCacheRecords1.xml": '<pivotCacheRecords><r><x v="0"/><n v="145000"/></r></pivotCacheRecords>',
    "xl/externalLinks/externalLink1.xml": (
        '<externalLink><externalBook><sheetDataSet><sheetData sheetId="0">'
        '<row r="1"><cell r="A1"><v>145000</v></cell><cell r="B1" t="str"><v>Acme</v></cell></row>'
        "</sheetData></sheetDataSet></externalBook></externalLink>"),
    "xl/externalLinks/_rels/externalLink1.xml.rels": (
        '<Relationships><Relationship Id="rId1" Target="file:///C:\\Users\\Bob\\Deal.xlsx" TargetMode="External"/>'
        '<Relationship Id="rId2" Target="Deal.xlsx"/></Relationships>'),
    "xl/drawings/drawing1.xml": (
        '<xdr:wsDr><xdr:pic><xdr:cNvPr id="2" name="Picture 1" descr="logo.png" title="Acme"/></xdr:pic>'
        "<xdr:sp><a:t>Confidential note</a:t></xdr:sp></xdr:wsDr>"),
    "xl/media/image1.png": b"\x89PNG real picture of Acme",
}


class PrivacyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = os.path.join(self.tmp.name, "in.xlsx")
        with zipfile.ZipFile(self.src, "w") as z:
            for name, data in PARTS.items():
                z.writestr(name, data)

    def tearDown(self):
        self.tmp.cleanup()

    def scrub(self, keep_headers=False):
        dst = os.path.join(self.tmp.name, "out.xlsx")
        scrubber.scrub_file(self.src, dst, keep_headers)
        with zipfile.ZipFile(dst) as z:
            return {n: z.read(n) for n in z.namelist()}

    def test_no_secret_survives_anywhere(self):
        for name, data in self.scrub().items():
            for word in SECRETS:
                self.assertNotIn(word.encode(), data, f"{word!r} leaked in {name}")

    def test_quoted_text_gets_the_same_dummy_as_the_cell(self):
        out = self.scrub()
        closed = re.findall(rb"<si><t>(Text_\d+)</t></si>", out["xl/sharedStrings.xml"])[1]
        sheet = out["xl/worksheets/sheet1.xml"]
        self.assertIn(b'<f>IF(A2="' + closed + b'",1,0)</f>', sheet)
        pivot = out["xl/pivotCache/pivotCacheDefinition1.xml"]
        self.assertIn(b'<s v="' + closed + b'"/>', pivot)

    def test_lists_and_print_headers(self):
        sheet = self.scrub()["xl/worksheets/sheet1.xml"]
        self.assertRegex(sheet, rb'<formula1>"Text_\d+"</formula1>')
        self.assertIn(b"<oddHeader>&amp;Credacted</oddHeader>", sheet)

    def test_pivot_cache_and_links(self):
        out = self.scrub()
        pivot = out["xl/pivotCache/pivotCacheDefinition1.xml"]
        self.assertIn(b'refreshedBy="redacted"', pivot)
        self.assertNotIn(b"minValue", pivot)
        rels = out["xl/externalLinks/_rels/externalLink1.xml.rels"]
        self.assertEqual(len(re.findall(rb'Target="redacted_link\d+\.xlsx"', rels)), 2)

    def test_header_names_stay_with_keep_headers(self):
        self.assertIn(b'name="Status"', self.scrub(keep_headers=True)["xl/pivotCache/pivotCacheDefinition1.xml"])

    def test_pictures_become_a_valid_blank_png(self):
        image = self.scrub()["xl/media/image1.png"]
        self.assertEqual(image, scrubber.BLANK_PNG)
        self.assertTrue(image.startswith(b"\x89PNG\r\n\x1a\n"))


if __name__ == "__main__":
    unittest.main()
