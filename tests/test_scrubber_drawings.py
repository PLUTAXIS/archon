import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import scrubber  # noqa: E402


class ScrubDrawings(unittest.TestCase):
    def test_text_box_text_is_redacted(self):
        m = scrubber.Masker()
        xml = '<xdr:sp><a:p><a:r><a:t>Acme payroll: 145000</a:t></a:r></a:p></xdr:sp>'
        out = scrubber.scrub_drawing(xml, m)
        self.assertNotIn("Acme", out)
        self.assertNotIn("145000", out)
        self.assertIn("<a:t>redacted</a:t>", out)
        self.assertEqual(m.count["drawings"], 1)

    def test_drawing_parts_are_routed_to_the_handler(self):
        for name in ("xl/drawings/drawing1.xml", "xl/drawings/drawing12.xml"):
            self.assertIs(scrubber.pick_handler(name), scrubber.scrub_drawing)

    def test_other_drawing_files_are_not_routed(self):
        self.assertIsNone(scrubber.pick_handler("xl/drawings/vmlDrawing1.vml"))
        self.assertIsNone(scrubber.pick_handler("xl/drawings/_rels/drawing1.xml.rels"))

    def test_smartart_triggers_a_review_warning(self):
        warnings = [why for key, why in scrubber.REVIEW.items() if key in "xl/diagrams/data1.xml"]
        self.assertTrue(any("SmartArt" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()