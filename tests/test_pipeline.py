"""End-to-end: workbook upload -> /audit -> report with bugs, cycles, explanations."""

import asyncio
import unittest
from io import BytesIO
from uuid import UUID

from fastapi import UploadFile
from openpyxl import Workbook

from archon.api.main import audit_workbook
from archon.contracts.report import ReportDocument
from archon.pipeline import run_audit

WID = UUID(int=1)


def _rows():
    rows = [("S", "A1", "Price"), ("S", "B1", "Qty"), ("S", "C1", "Amount")]
    for r in range(2, 12):
        rows += [("S", f"A{r}", str(r)), ("S", f"B{r}", "3")]
        rows.append(("S", f"C{r}", "145000" if r == 6 else f"=A{r}*B{r}"))
    rows.append(("S", "D12", "=SUM(C2:C11)"))
    rows += [("S", "E1", "=F1+1"), ("S", "F1", "=E1")]  # circular reference
    return rows


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


class AuditEndpointTests(unittest.TestCase):
    def test_upload_returns_report(self):
        wb = Workbook()
        ws = wb.active
        for sheet, addr, content in _rows():
            ws[addr] = float(content) if content.isdigit() else content
        buf = BytesIO()
        wb.save(buf)

        buf.seek(0)
        body = asyncio.run(audit_workbook(UploadFile(file=buf, filename="demo.xlsx")))
        self.assertEqual(body["audit_level"], "full_pipeline")
        self.assertEqual(len(body["analysis"]["bugs"]), 1)
        self.assertEqual(body["analysis"]["bugs"][0]["address"], "C6")
        ReportDocument.model_validate(body["analysis"]["report"])


if __name__ == "__main__":
    unittest.main()
