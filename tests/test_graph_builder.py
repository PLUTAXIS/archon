import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from archon.graph import graph_builder as gb

SAMPLE = os.path.join(ROOT, "samples", "sample_input.json")


def load_sample():
    with open(SAMPLE, encoding="utf-8") as fh:
        return json.load(fh)


def vba_only(code, default_sheet="S"):
    """Tiny graph: one formula (so validation has formula edges) + given VBA."""
    return {
        "formulas": [{"sheet": "S", "cell": "Z1", "formula": "=Z2"}],
        "vba": [{"module": "M", "default_sheet": default_sheet, "code": code}],
    }


class TestRefs(unittest.TestCase):
    def test_simple_and_absolute(self):
        refs = gb.extract_refs("=A1+$B$2", "S")
        self.assertEqual(refs, [("S", "A1", None), ("S", "B2", None)])

    def test_range_and_other_sheet(self):
        refs = gb.extract_refs("=SUM(Data!A1:A3)", "S")
        self.assertEqual(refs, [("Data", "A1", "A3")])

    def test_quoted_sheet(self):
        refs = gb.extract_refs("='My Sheet'!B4*2", "S")
        self.assertEqual(refs, [("My Sheet", "B4", None)])

    def test_strings_and_function_names_ignored(self):
        refs = gb.extract_refs('=IF(A1>0,"B2 text",LOG10(100))', "S")
        self.assertEqual(refs, [("S", "A1", None)])

    def test_big_range_becomes_range_node(self):
        data = {
            "formulas": [{"sheet": "S", "cell": "A1", "formula": "=SUM(B1:B100000)"}],
            "vba": [],
        }
        g = gb.build_graph(data)
        self.assertEqual(g.nodes["S!B1:B100000"]["type"], "range")
        self.assertEqual(g.number_of_nodes(), 2)


class TestVba(unittest.TestCase):
    def targets(self, g):
        return {v for u, v, d in g.edges(data=True)
                if d["label"] == "vba_write" and g.nodes[v]["type"] != "vba_write_range_unknown"}

    def test_static_writes_resolved(self):
        code = ('Sub A()\n'
                '  Range("A2").Value = 1\n'
                '  Worksheets("Other").Range("B2") = 2\n'
                '  Cells(3, 2).Value = 3\n'
                '  If x Then Range("C5").Value = 4\n'
                'End Sub\n')
        g = gb.build_graph(vba_only(code))
        self.assertEqual(self.targets(g), {"S!A2", "Other!B2", "S!B3", "S!C5"})
        self.assertTrue(g.nodes["S!A2"]["vba_written"])

    def test_static_range_expands(self):
        g = gb.build_graph(vba_only('Sub A()\n Range("A1:A3").Value = 0\nEnd Sub'))
        self.assertEqual(self.targets(g), {"S!A1", "S!A2", "S!A3"})

    def test_dynamic_writes_flagged_not_dropped(self):
        code = ('Sub A()\n'
                '  Range("A" & i).Value = 1\n'
                '  Cells(i, 1).Value = 2\n'
                '  With Sheets("X")\n'
                '    .Range("A1").Value = 3\n'
                '  End With\n'
                '  Range("A1").Offset(1, 0).Value = 4\n'
                '  rng.Value = 5\n'
                'End Sub\n')
        g = gb.build_graph(vba_only(code))
        unknown = [d for _, d in g.nodes(data=True)
                   if d["type"] == "vba_write_range_unknown"]
        self.assertEqual(sorted(u["line"] for u in unknown), [2, 3, 5, 7, 8])
        for u in unknown:
            self.assertEqual(u["module"], "M")
            self.assertTrue(u["flagged"])
        out = gb.to_dict(g)
        self.assertEqual(len(out["vba_unknown_writes"]), 5)
        self.assertEqual(out["meta"]["vba_unknown_writes"], 5)

    def test_no_default_sheet_makes_it_unknown(self):
        g = gb.build_graph(vba_only('Sub A()\n Range("A1").Value = 1\nEnd Sub', default_sheet=None))
        self.assertEqual(gb.to_dict(g)["meta"]["vba_unknown_writes"], 1)

    def test_reads_comments_and_conditions_are_not_writes(self):
        code = ('Sub A()\n'
                "  ' Range(\"A1\").Value = 1\n"
                '  y = Range("A1").Value\n'
                '  If Range("A1").Value = 5 Then\n'
                '    z = 1\n'
                '  End If\n'
                '  Set r = Range("A1")\n'
                'End Sub\n')
        g = gb.build_graph(vba_only(code))
        self.assertFalse([n for n in g if n.startswith("VBA")])

    def test_proc_name_and_line_numbers(self):
        g = gb.build_graph(vba_only('\nSub First()\nEnd Sub\nSub Second()\n Range("A1").Value = 1\nEnd Sub'))
        self.assertIn("VBA:M.Second", g)
        self.assertNotIn("VBA:M.First", g)


class TestSampleAndValidation(unittest.TestCase):
    def test_sample_builds_and_validates(self):
        g = gb.build_graph(load_sample())
        self.assertEqual(gb.validate(g), [])
        out = gb.to_dict(g)
        self.assertEqual(out["meta"]["edges_by_label"], {"formula": 10, "vba_write": 7})
        self.assertEqual(out["meta"]["vba_unknown_writes"], 3)
        self.assertEqual(g.nodes["Budget!C2"]["cluster"], "R1C1-001")

    def test_every_edge_labelled(self):
        out = gb.to_dict(gb.build_graph(load_sample()))
        for e in out["edges"]:
            self.assertIn(e["label"], gb.EDGE_LABELS)

    def test_orphan_detected(self):
        data = load_sample()
        data["formulas"].append({"sheet": "S", "cell": "Q9", "formula": "=5"})
        errors = gb.validate(gb.build_graph(data))
        self.assertTrue(any("orphan" in e and "S!Q9" in e for e in errors))

    def test_formulas_only_fails_validation(self):
        data = load_sample()
        data["vba"] = []
        errors = gb.validate(gb.build_graph(data))
        self.assertTrue(any("vba_write" in e for e in errors))

    def test_vba_only_fails_validation(self):
        data = load_sample()
        data["formulas"] = []
        errors = gb.validate(gb.build_graph(data))
        self.assertTrue(any("'formula'" in e for e in errors))

    def test_unlabelled_edge_detected(self):
        g = gb.build_graph(load_sample())
        g.add_edge("Budget!A2", "Budget!B2")
        self.assertTrue(any("unlabelled" in e for e in gb.validate(g)))

    def test_cycle_flagged(self):
        data = {"formulas": [{"sheet": "S", "cell": "A1", "formula": "=B1"},
                             {"sheet": "S", "cell": "B1", "formula": "=A1"}],
                "vba": [{"module": "M", "default_sheet": "S",
                         "code": "Sub A()\n Range(\"C1\").Value = 1\nEnd Sub"}]}
        g = gb.build_graph(data)
        self.assertTrue(gb.to_dict(g)["meta"]["has_cycles"])

    def test_bad_input_raises(self):
        with self.assertRaises(ValueError):
            gb.build_graph({"formulas": [{"sheet": "S", "cell": "A1"}]})
        with self.assertRaises(ValueError):
            gb.build_graph({"formulas": [{"sheet": "S", "cell": "ZZZZ9", "formula": "=1"}]})
        with self.assertRaises(ValueError):
            gb.build_graph([])


class TestCli(unittest.TestCase):
    def test_cli_writes_file(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "dag_graph.json")
            self.assertEqual(gb.main([SAMPLE, "-o", out]), 0)
            with open(out, encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertEqual(set(data), {"meta", "nodes", "edges", "vba_unknown_writes"})
            self.assertEqual(len(data["vba_unknown_writes"]), 3)

    def test_cli_refuses_invalid(self):
        data = load_sample()
        data["vba"] = []
        with tempfile.TemporaryDirectory() as d:
            inp, out = os.path.join(d, "in.json"), os.path.join(d, "out.json")
            with open(inp, "w", encoding="utf-8") as fh:
                json.dump(data, fh)
            self.assertEqual(gb.main([inp, "-o", out]), 1)
            self.assertFalse(os.path.exists(out))

    def test_cli_missing_file(self):
        self.assertEqual(gb.main(["no_such_file.json"]), 1)


class SheetModuleScopeTests(unittest.TestCase):
    """In a sheet's own module, Range()/Me.Range() mean that sheet; ActiveSheet never does."""

    def test_me_and_bare_range_use_the_module_sheet(self):
        g = gb.build_graph(vba_only('Sub A()\n Me.Range("B2").Value = 1\n Range("C3").Value = 2\nEnd Sub'))
        targets = {v for _u, v, d in g.edges(data=True) if d["label"] == "vba_write"}
        self.assertEqual(targets, {"S!B2", "S!C3"})

    def test_active_sheet_stays_unknown_even_with_a_default(self):
        g = gb.build_graph(vba_only('Sub A()\n ActiveSheet.Range("B2").Value = 1\nEnd Sub'))
        (unknown,) = [d for _n, d in g.nodes(data=True) if d["type"] == "vba_write_range_unknown"]
        self.assertIn("ActiveSheet", unknown["reason"])


if __name__ == "__main__":
    unittest.main()
