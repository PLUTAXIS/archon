"""Comment scrubbing tests, including the xl/comments/ folder layout. Run: python -m pytest -q"""
import os
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from archon.scrubber import scrubber

NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
WORKBOOK = f'<workbook {NS}><sheets><sheet name="S" sheetId="1"/></sheets></workbook>'
COMMENTS = (
    f'<comments {NS}><authors><author>Jane Doe</author></authors><commentList>'
    '<comment ref="A1" authorId="0"><text><r><t>Ask John Smith</t></r></text></comment>'
    "</commentList></comments>"
)


class CommentLocationTests(unittest.TestCase):
    def scrubbed_part(self, part):
        """Scrub a tiny workbook that stores its comments at `part`; return that part."""
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = os.path.join(tmp, "in.xlsx"), os.path.join(tmp, "out.xlsx")
            with zipfile.ZipFile(src, "w") as z:
                z.writestr("xl/workbook.xml", WORKBOOK)
                z.writestr(part, COMMENTS)
            scrubber.scrub_file(src, dst)
            with zipfile.ZipFile(dst) as z:
                return z.read(part).decode()

    def test_comment_text_in_comments_folder_is_masked(self):
        self.assertNotIn("John Smith", self.scrubbed_part("xl/comments/comment1.xml"))

    def test_comment_author_in_comments_folder_is_masked(self):
        self.assertNotIn("Jane Doe", self.scrubbed_part("xl/comments/comment1.xml"))

    def test_classic_comments_file_is_still_masked(self):
        xml = self.scrubbed_part("xl/comments1.xml")
        self.assertNotIn("John Smith", xml)
        self.assertNotIn("Jane Doe", xml)


if __name__ == "__main__":
    unittest.main()