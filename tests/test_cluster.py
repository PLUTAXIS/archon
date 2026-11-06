"""Tests for archon.cluster.engine (formula clustering)."""

import json
import tempfile
import unittest
from pathlib import Path

from archon.cluster.engine import (
    cluster_cells,
    contiguous_runs,
    load_formulas,
    summarise,
)


def sample_rows(n: int = 5000) -> list[tuple[str, str, str]]:
    """n dragged rows in three columns, plus two planted errors and a total."""
    rows = []
    for r in range(2, n + 2):
        if r != 4312:
            rows.append(("Sales", f"D{r}", f"=B{r}*C{r}"))
        if r != 2500:
            rows.append(("Sales", f"E{r}", f"=D{r}*1.18"))
        rows.append(("Sales", f"F{r}", f"=SUM($D$2:D{r})"))
    rows.append(("Sales", "D4312", "145000"))
    rows.append(("Sales", "E2500", "=D2500*1.12"))
    rows.append(("Sales", "D5003", f"=SUM(D2:D{n + 1})"))
    return rows


class TestClusterCells(unittest.TestCase):
    def setUp(self) -> None:
        self.clusters, self.constants = cluster_cells(sample_rows())

    def test_counts(self) -> None:
        s = summarise(self.clusters, self.constants)
        self.assertEqual(s["formula_cells"], 15000)
        self.assertEqual(s["clusters"], 5)
        self.assertEqual(s["constant_cells"], 1)
        self.assertEqual(s["compression_ratio"], 3000.0)

    def test_hardcoded_cell_is_reported(self) -> None:
        self.assertEqual(self.constants, [("Sales", "D4312", "145000")])

    def test_wrong_rate_forms_its_own_cluster(self) -> None:
        key = ("Sales", "E", "=RC[-1]*1.12")
        self.assertEqual(self.clusters[key], [(2500, "E2500")])

    def test_override_leaves_a_gap_in_its_cluster(self) -> None:
        members = self.clusters[("Sales", "D", "=RC[-2]*RC[-1]")]
        rows = [r for r, _ in members]
        self.assertEqual(contiguous_runs(rows), [(2, 4311), (4313, 5001)])

    def test_blank_cells_are_ignored(self) -> None:
        clusters, constants = cluster_cells([("S", "A1", "  ")])
        self.assertEqual((clusters, constants), ({}, []))

    def test_empty_input(self) -> None:
        clusters, constants = cluster_cells([])
        self.assertEqual(summarise(clusters, constants)["compression_ratio"], 0.0)


class TestContiguousRuns(unittest.TestCase):
    def test_runs(self) -> None:
        self.assertEqual(contiguous_runs([2, 3, 4, 6, 7]), [(2, 4), (6, 7)])

    def test_single_and_empty(self) -> None:
        self.assertEqual(contiguous_runs([5]), [(5, 5)])
        self.assertEqual(contiguous_runs([]), [])


class TestLoadFormulas(unittest.TestCase):
    def test_reads_extracted_formulas_format(self) -> None:
        data = [{"sheet": "Main", "cell_reference": "C1", "formula": "=A1*B1"}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "extracted_formulas.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(load_formulas(path), [("Main", "C1", "=A1*B1")])

    def test_null_formula_becomes_empty_string_not_literal_none(self) -> None:
        data = [{"sheet": "Main", "cell_reference": "C1", "formula": None}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "extracted_formulas.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(load_formulas(path), [("Main", "C1", "")])

    def test_non_list_json_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "extracted_formulas.json"
            path.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_formulas(path)

    def test_missing_field_raises_value_error_naming_index(self) -> None:
        data = [
            {"sheet": "Main", "cell_reference": "C1", "formula": "=A1*B1"},
            {"sheet": "Main", "cell_reference": "C2"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "extracted_formulas.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                load_formulas(path)
            self.assertIn("index 1", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
