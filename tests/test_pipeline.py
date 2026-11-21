"""End-to-end: workbook upload -> /audit -> report with bugs, cycles, explanations."""

import asyncio
import unittest
from io import BytesIO
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, UploadFile
from openpyxl import Workbook

from archon.api.main import OLE_MAGIC, audit_workbook
from archon.contracts.graph import DagGraph
from archon.contracts.report import ReportDocument
from archon.ingest.xlsx import extract
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


if __name__ == "__main__":
    unittest.main()
