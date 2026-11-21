"""End-to-end: workbook upload -> /audit -> report with bugs, cycles, explanations."""

import asyncio
import unittest
from io import BytesIO
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, UploadFile
from openpyxl import Workbook
from openpyxl.workbook.defined_name import DefinedName as OpenpyxlName

from archon.api.main import OLE_MAGIC, audit_workbook
from archon.contracts.extract import DefinedName
from archon.contracts.graph import DagGraph
from archon.contracts.report import ReportDocument
from archon.ingest.xlsx import extract
from archon.names import reference_names
from archon.pipeline import run_audit, run_extract

WID = UUID(int=1)
XLSM = Path(__file__).parent / "ingest" / "fixtures" / "vba_classification_test.xlsm"


def _rows():
    rows = [("S", "A1", "Price"), ("S", "B1", "Qty"), ("S", "C1", "Amount")]
    for r in range(2, 12):
        rows += [("S", f"A{r}", str(r)), ("S", f"B{r}", "3")]
        rows.append(("S", f"C{r}", "145000" if r == 6 else f"=A{r}*B{r}"))
    rows.append(("S", "D12", "=SUM(C2:C11)"))
    rows += [("S", "E1", "=F1+1"), ("S", "F1", "=E1")]  # circular reference
    return rows


def _xlsx(rows, very_hidden=None):
    wb = Workbook()
    ws = wb.active
    ws.title = "S"
    for _sheet, addr, content in rows:
        ws[addr] = float(content) if content.isdigit() else content
    if very_hidden:
        wb.create_sheet(very_hidden).sheet_state = "veryHidden"
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _upload(data, name="demo.xlsx"):
    return asyncio.run(audit_workbook(UploadFile(file=BytesIO(data), filename=name)))


class RunAuditTests(unittest.TestCase):
    def setUp(self):
        self.out = run_audit(_rows(), WID)

    def test_override_bug_found_with_downstream_impact(self):
        (bug,) = self.out["bugs"]
        self.assertEqual((bug["sheet"], bug["address"], bug["observed"]), ("S", "C6", 145000.0))
        self.assertEqual(bug["downstream_sample"], ["S!D12"])
        self.assertEqual(bug["expected_r1c1"], "=RC[-2]*RC[-1]")

    def test_cycle_found_and_left_unclassified(self):
        (cycle,) = self.out["cycles"]
        self.assertEqual(cycle["members"], ["S!E1", "S!F1"])
        self.assertIsNone(cycle["classification"])

    def test_report_is_a_valid_contract_document(self):
        doc = ReportDocument.model_validate(self.out["report"])
        ids = [e.node_id for s in doc.sections for e in s.entries]
        self.assertIn("S!C2:C11", ids)

    def test_summary_counts(self):
        s = self.out["summary"]
        self.assertEqual(s["formula_cells"], 12)  # 9 dragged + SUM + 2 cycle cells
        self.assertEqual(s["override_bugs"], 1)
        self.assertEqual(s["unparsed_formulas"], 0)

    def test_deterministic_and_order_independent(self):
        self.assertEqual(run_audit(list(reversed(_rows())), WID), self.out)

    def test_explanations_name_cells_by_their_headers(self):
        entries = {e["node_id"]: e for s in self.out["report"]["sections"] for e in s["entries"]}
        self.assertEqual(
            entries["S!C2:C11"]["plain_english"], "Amount: product of Price (A2) and Qty (B2)."
        )

    def test_unexplained_formulas_are_not_ranked_as_risks(self):
        sections = {s["kind"]: s["entries"] for s in self.out["report"]["sections"]}
        appendix = {e["node_id"] for e in sections["unverified_appendix"]}
        self.assertFalse(appendix & {e["node_id"] for e in sections["risk"]})

    def test_scorecard_reflects_the_findings(self):
        card = self.out["scorecard"]
        structural = card["axes"][0]["contributions"]
        self.assertIn({"signal": "override_bug", "label": "hardcoded values typed over a copied formula",
                       "count": 1, "points": 25}, structural)
        self.assertIn({"signal": "cycle", "label": "circular references", "count": 1, "points": 20},
                      structural)
        self.assertGreater(card["score"], 0)


class NamesAndColumnsTests(unittest.TestCase):
    def setUp(self):
        self.names = reference_names(
            [DefinedName(name="TaxRate", scope="workbook", refers_to="In!$B$1")], ["S", "In"]
        )
        rows = [("In", "A1", "Tax rate"), ("In", "B1", "0.2"), ("S", "A1", "Amount")]
        rows += [("S", f"A{r}", str(r)) for r in range(2, 12)]
        rows += [("S", "B2", "=A2*TaxRate"), ("S", "C1", "Total"), ("S", "C2", "=SUM(A:A)")]
        self.out = run_audit(rows, WID, names=self.names)
        self.edges = {(e["source"], e["target"]) for e in self.out["graph"]["edges"]}
        self.text = {e["node_id"]: e["plain_english"]
                     for s in self.out["report"]["sections"] for e in s["entries"]}

    def test_named_input_is_a_dependency_and_keeps_its_name(self):
        self.assertIn(("In!B:B", "S!B2"), self.edges)
        # column B has no header, so no "Label:" prefix; the named input is named
        self.assertEqual(self.text["S!B2"], "Product of Amount (A2) and TaxRate (In!B1).")

    def test_whole_column_total_depends_on_the_column(self):
        self.assertIn(("S!A:A", "S!C2"), self.edges)
        self.assertEqual(self.text["S!C2"], "Total: sum of Amount (A:A).")

    def test_spec_shows_the_formula_as_written(self):
        calc = {c["id"]: c for c in self.out["spec"]["sheets"][1]["calculations"]}
        self.assertEqual(calc["S!B2"]["formula"], "=A2*TaxRate")

    def test_override_inside_a_huge_range_shows_its_impact(self):
        rows = [("S", f"A{r}", f"=B{r}*2") for r in range(1, 2501)]
        rows[1199] = ("S", "A1200", "777")  # typed over, inside a 2,500-cell range
        rows += [("S", f"B{r}", "1") for r in range(1, 2501)] + [("S", "C1", "=SUM(A1:A2500)")]
        (bug,) = run_audit(rows, WID)["bugs"]
        self.assertEqual(bug["address"], "A1200")
        self.assertEqual(bug["downstream_sample"], ["S!A1:A2500", "S!C1"])

    def test_defined_names_flow_through_upload(self):
        wb = Workbook()
        ws = wb.active
        ws.title = "S"
        ws["A1"], ws["A2"], ws["B2"] = "Amount", 5, "=A2*TaxRate"
        wb.create_sheet("In")["B1"] = 0.2
        wb.defined_names["TaxRate"] = OpenpyxlName("TaxRate", attr_text="In!$B$1")
        buf = BytesIO()
        wb.save(buf)
        report = _upload(buf.getvalue())["analysis"]["report"]
        text = {e["node_id"]: e["plain_english"] for s in report["sections"] for e in s["entries"]}
        self.assertIn("TaxRate (In!B1)", text["S!B2"])


MACRO = """Sub Update()
    On Error Resume Next
    x = Worksheets("S").Range("A2").Value * 2
    Worksheets("S").Range("C3").Value = x
    If Worksheets("S").Range("A3").Value > 0 Then Worksheets("S").Range("B9").Value = 1
    Range("A" & i).Value = 5
End Sub
Sub Bump()
    Worksheets("S").Range("A1").Value = Worksheets("S").Range("A1").Value + 1
End Sub"""


class VbaFindingsTests(unittest.TestCase):
    def setUp(self):
        self.out = run_audit(_rows(), WID, vba=[{"module": "M", "code": MACRO}])
        self.edges = {(e["source"], e["target"], e["origin"]) for e in self.out["graph"]["edges"]}

    def test_static_reads_become_edges_but_the_write_target_does_not(self):
        self.assertIn(("S!A:A", "VBA:M.Update", "vba_read"), self.edges)  # A2 and A3 (in the If)
        self.assertNotIn(("S!C2:C11", "VBA:M.Update", "vba_read"), self.edges)  # C3 is written

    def test_findings_name_each_problem_and_where_it_is(self):
        kinds = {(f["kind"], f["procedure"], f.get("line"), f.get("cell"))
                 for f in self.out["vba_findings"]}
        self.assertIn(("error_suppression", "Update", 2, None), kinds)
        self.assertIn(("overwrites_formula", "Update", None, "S!C3"), kinds)
        self.assertIn(("dynamic_write", "Update", 6, None), kinds)

    def test_a_macro_updating_a_cell_is_not_a_circular_reference(self):
        cycles = [c["members"] for c in self.out["cycles"]]
        self.assertEqual(cycles, [["S!E1", "S!F1"]])  # only the formula cycle

    def test_spec_lists_what_each_macro_reads_and_writes(self):
        macros = {m["procedure"]: m for m in self.out["spec"]["macros"]}
        update = macros["VBA:M.Update"]
        self.assertIn("Price (S!A:A)", update["reads_from"])
        self.assertIn("a cell chosen at run time (M, line 6)", update["writes_to"])
        self.assertTrue(any("C2:C11" in w for w in update["writes_to"]))
        DagGraph.model_validate(self.out["graph"])

    def test_findings_listed_most_damaging_first(self):
        kinds = [f["kind"] for f in self.out["vba_findings"]]
        self.assertEqual(kinds, ["overwrites_formula", "error_suppression", "dynamic_write"])


class AffectedBlocksTests(unittest.TestCase):
    def test_bug_lists_exactly_the_blocks_its_cells_reach(self):
        # E2:E11 reads only column D; D reads column C. A bug in C6 reaches D6 and E6,
        # which live in the D and E blocks; F12 reads only A1 and must not be listed.
        rows = [("S", "A1", "Rate"), ("S", "B1", "0.1")]
        for r in range(2, 12):
            rows += [("S", f"A{r}", str(r)), ("S", f"C{r}", "7" if r == 6 else f"=A{r}*2"),
                     ("S", f"D{r}", f"=C{r}+1"), ("S", f"E{r}", f"=D{r}*3")]
        rows.append(("S", "F12", "=A1+1"))
        (bug,) = run_audit(rows, WID)["bugs"]
        self.assertEqual(bug["affected_nodes"], ["S!D2:D11", "S!E2:E11"])


class SeverityTests(unittest.TestCase):
    def test_local_override_with_plausible_value_is_minor(self):
        (bug,) = run_audit(_rows(), WID, values={("S", "C5"): 15.0})["bugs"]
        # C6 typed 145000 next to a formula that gave 15: far off, feeds D12
        self.assertEqual(bug["severity_reasons"][0], "feeds 1 other cell")
        self.assertIn("far from the 15", bug["severity_reasons"][1])
        self.assertEqual(bug["severity"], 3)

    def test_value_close_to_the_formula_result_is_not_an_outlier(self):
        (bug,) = run_audit(_rows(), WID, values={("S", "C5"): 140000.0})["bugs"]
        self.assertEqual(bug["severity_reasons"], ["feeds 1 other cell"])
        self.assertEqual(bug["severity"], 2)

    def test_wide_cross_sheet_impact_raises_severity(self):
        rows = _rows() + [("R", f"A{r}", f"=S!D12*{r}") for r in range(1, 11)]
        (bug,) = run_audit(rows, WID)["bugs"]
        self.assertEqual(bug["severity_reasons"], [
            "feeds 11 other cells", "wide blast radius (10 or more cells)",
            "reaches other sheets: R",
        ])
        self.assertEqual(bug["severity"], 4)


class SpecTests(unittest.TestCase):
    def setUp(self):
        (self.sheet,) = run_audit(_rows(), WID)["spec"]["sheets"]
        self.calc = {c["id"]: c for c in self.sheet["calculations"]}
        self.order = [c["id"] for c in self.sheet["calculations"]]

    def test_inputs_listed_with_their_users(self):
        inputs = {i["id"]: i for i in self.sheet["inputs"]}
        self.assertEqual(inputs["S!A:A"]["label"], "Price")
        self.assertEqual(inputs["S!A:A"]["used_by"], ["Amount (S!C2:C11)"])

    def test_calculations_come_after_what_they_read(self):
        self.assertLess(self.order.index("S!C2:C11"), self.order.index("S!D12"))
        self.assertLess(self.order.index("S!C6"), self.order.index("S!D12"))

    def test_entry_carries_explanation_formula_and_links(self):
        block = self.calc["S!C2:C11"]
        self.assertEqual(block["explanation"], "Amount: product of Price (A2) and Qty (B2).")
        self.assertEqual(block["formula"], "=A2*B2")
        self.assertEqual(block["cells"], ["C2:C5", "C7:C11"])
        self.assertIn("S!D12", block["used_by"][0])

    def test_override_is_explained_and_points_to_the_ledger(self):
        override = self.calc["S!C6"]
        self.assertEqual(override["kind"], "override")
        self.assertTrue(override["explanation"].startswith("BUG-001: the value 145000 is typed in"))

    def test_final_results_are_marked_as_outputs(self):
        self.assertTrue(self.calc["S!D12"]["is_output"])
        self.assertFalse(self.calc["S!C2:C11"]["is_output"])

    def test_sheets_follow_workbook_order(self):
        wb = Workbook()
        wb.active.title = "Zeta"
        wb.active["A1"] = "=1+1"
        wb.create_sheet("Alpha")["A1"] = "=Zeta!A1*2"
        buf = BytesIO()
        wb.save(buf)
        spec = _upload(buf.getvalue())["analysis"]["spec"]
        self.assertEqual([s["name"] for s in spec["sheets"]], ["Zeta", "Alpha"])


class GraphContractTests(unittest.TestCase):
    def setUp(self):
        self.graph = DagGraph.model_validate(run_audit(_rows(), WID)["graph"])
        self.nodes = {n.id: n for n in self.graph.nodes}
        self.edges = {(e.source, e.target, e.origin) for e in self.graph.edges}

    def test_cluster_node_keeps_the_gap_where_the_override_sits(self):
        node = self.nodes["S!C2:C11"]
        self.assertEqual((node.kind, node.member_count), ("cluster", 9))
        self.assertEqual(node.member_ranges, ["C2:C5", "C7:C11"])
        self.assertEqual(node.header, "Amount")

    def test_bug_cell_is_its_own_node_wired_to_what_it_breaks(self):
        self.assertEqual(self.nodes["S!C6"].kind, "cell")
        self.assertIn(("S!C6", "S!D12", "formula"), self.edges)

    def test_input_cells_collapse_to_one_node_per_column(self):
        node = self.nodes["S!A:A"]
        # 9, not 10: A6 is never read because C6's formula was typed over
        self.assertEqual((node.kind, node.member_count, node.header), ("input", 9, "Price"))
        self.assertIn(("S!A:A", "S!C2:C11", "formula"), self.edges)

    def test_cycle_and_bug_carried_in_contract(self):
        self.assertEqual([c.nodes for c in self.graph.cycles], [["S!E1", "S!F1"]])
        self.assertEqual([b.address for b in self.graph.bugs], ["C6"])


class VbaTests(unittest.TestCase):
    def test_static_and_dynamic_vba_writes(self):
        code = (
            'Sub Fix()\n Worksheets("S").Range("A3").Value = 0\nEnd Sub\n'
            'Sub Loop1()\n For i = 2 To 9\n  Range("A" & i).Value = 1\n Next\nEnd Sub'
        )
        out = run_audit(_rows(), WID, vba=[{"module": "Module1", "code": code}])
        edges = {(e["source"], e["target"], e["origin"]) for e in out["graph"]["edges"]}
        self.assertIn(("VBA:Module1.Fix", "S!A:A", "vba_write"), edges)
        self.assertEqual(out["summary"]["vba_dynamic_writes"], 1)
        self.assertEqual(out["vba_unknown_writes"][0]["procedure"], "Loop1")

    def test_real_xlsm_runs_end_to_end_and_deterministically(self):
        first = run_extract(extract(XLSM))
        self.assertTrue(first["extract"]["vba_modules"])
        DagGraph.model_validate(first["graph"])
        self.assertEqual(run_extract(extract(XLSM)), first)


class AuditEndpointTests(unittest.TestCase):
    def test_upload_returns_report(self):
        body = _upload(_xlsx(_rows()))
        self.assertEqual(body["audit_level"], "full_pipeline")
        self.assertEqual(len(body["analysis"]["bugs"]), 1)
        self.assertEqual(body["analysis"]["bugs"][0]["address"], "C6")
        ReportDocument.model_validate(body["analysis"]["report"])
        DagGraph.model_validate(body["analysis"]["graph"])

    def test_very_hidden_sheet_is_flagged_not_skipped(self):
        body = _upload(_xlsx(_rows(), very_hidden="Secret"))
        codes = [(e["code"], e["sheet"]) for e in body["analysis"]["extract"]["exceptions"]]
        self.assertIn(("E_VERY_HIDDEN_SHEET", "Secret"), codes)

    def test_password_protected_file_gets_a_clear_error(self):
        with self.assertRaises(HTTPException) as ctx:
            _upload(OLE_MAGIC + b"\0" * 64)
        self.assertIn("password-protected", ctx.exception.detail)

    def test_xlsm_upload_is_accepted(self):
        body = _upload(XLSM.read_bytes(), name="macro.xlsm")
        self.assertTrue(body["analysis"]["extract"]["vba_modules"])



class SheetModuleTests(unittest.TestCase):
    def test_sheet_module_defaults_to_its_own_sheet(self):
        from archon.pipeline import _vba_inputs

        modules = {m["module"]: m.get("default_sheet") for m in _vba_inputs(extract(XLSM))}
        self.assertEqual(modules["SalesDataSheet.cls"], "SalesData")
        self.assertIsNone(modules["Module1.bas"])  # standard modules have no own sheet


if __name__ == "__main__":
    unittest.main()
