"""Tests for the AST-hash-based clustering in archon.cluster.engine."""

import unittest

from archon.cluster.engine import cluster_cells_ast, cluster_id_for
from archon.formula.parser import ParseError


class TestClusterIdFor(unittest.TestCase):
    """cluster_id_for: one formula+address -> a stable blake3 hex id."""

    def test_same_dragged_formula_same_id(self):
        """A formula dragged down rows produces the same id each time."""
        self.assertEqual(
            cluster_id_for("=B2*C2", "D2"),
            cluster_id_for("=B3*C3", "D3"),
        )

    def test_different_formula_different_id(self):
        """A structurally different formula gets a different id."""
        self.assertNotEqual(
            cluster_id_for("=B2*C2", "D2"),
            cluster_id_for("=B2+C2", "D2"),
        )

    def test_id_is_hex_string(self):
        """The id is a blake3 hex digest (64 lowercase hex characters)."""
        cid = cluster_id_for("=A1", "B1")
        self.assertEqual(len(cid), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in cid))

    def test_malformed_formula_raises_parse_error(self):
        """An unparseable formula surfaces as ParseError, not a crash."""
        with self.assertRaises(ParseError):
            cluster_id_for("=)", "A1")

    def test_numeric_vs_string_literal_different_id(self):
        """A numeric literal and a string literal that print the same way
        must still hash differently -- the literal's type is part of the
        canonical form, not just its value."""
        self.assertNotEqual(
            cluster_id_for('="1"', "A1"),
            cluster_id_for("=1", "A1"),
        )

    def test_different_sheet_different_id(self):
        """Two refs with the same cell text but different sheets must
        hash differently."""
        self.assertNotEqual(
            cluster_id_for("=Sheet1\x21A1", "B1"),
            cluster_id_for("=Sheet2\x21A1", "B1"),
        )

    def test_absolute_vs_relative_ref_different_id(self):
        """$A$1 and A1 translate to different R1C1 text (absolute vs.
        relative), so they must hash differently."""
        self.assertNotEqual(
            cluster_id_for("=$A$1", "B1"),
            cluster_id_for("=A1", "B1"),
        )

    def test_function_name_case_currently_distinct(self):
        """Documents current behavior: function-name case is NOT folded,
        so sum(A1) and SUM(A1) get different ids. If the parser or this
        module ever adds case-insensitive function names, this test
        should be updated to assertEqual instead."""
        self.assertNotEqual(
            cluster_id_for("=sum(A1)", "B1"),
            cluster_id_for("=SUM(A1)", "B1"),
        )


class TestClusterCellsAst(unittest.TestCase):
    """cluster_cells_ast: group rows by (sheet, column, AST hash)."""

    def test_dragged_range_forms_one_cluster(self):
        """10 identical dragged rows collapse into a single cluster."""
        rows = [("Sheet1", f"D{r}", f"=B{r}*C{r}") for r in range(2, 12)]
        clusters, constants, unparsed = cluster_cells_ast(rows)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(constants, [])
        self.assertEqual(unparsed, [])
        ((members),) = clusters.values()
        self.assertEqual(len(members), 10)

    def test_override_breaks_out_of_cluster(self):
        """A hardcoded override is a constant, and leaves a gap in the
        cluster's row range (the override-detection behavior)."""
        rows = [("Sheet1", f"D{r}", f"=B{r}*C{r}") for r in range(2, 5)]
        rows.append(("Sheet1", "D5", "145000"))
        rows += [("Sheet1", f"D{r}", f"=B{r}*C{r}") for r in range(6, 9)]
        clusters, constants, _unparsed = cluster_cells_ast(rows)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(constants, [("Sheet1", "D5", "145000")])
        ((members),) = clusters.values()
        self.assertEqual([m[0] for m in members], [2, 3, 4, 6, 7, 8])

    def test_different_columns_different_clusters(self):
        """The same relative formula in a different column is a separate
        cluster, since the cluster key includes the column."""
        rows = [("Sheet1", "D2", "=B2*C2"), ("Sheet1", "E2", "=C2*D2")]
        clusters, _, _ = cluster_cells_ast(rows)
        self.assertEqual(len(clusters), 2)

    def test_malformed_formula_goes_to_unparsed_not_crash(self):
        """A malformed formula is routed to unparsed, not raised."""
        rows = [("Sheet1", "D2", "=B2*C2"), ("Sheet1", "D3", "=)")]
        clusters, _constants, unparsed = cluster_cells_ast(rows)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(unparsed, [("Sheet1", "D3", "=)")])

    def test_blank_rows_skipped(self):
        """Blank/whitespace-only content is skipped entirely."""
        rows = [("Sheet1", "D2", "=B2*C2"), ("Sheet1", "D3", "   ")]
        _clusters, constants, unparsed = cluster_cells_ast(rows)
        self.assertEqual(len(unparsed), 0)
        self.assertEqual(len(constants), 0)

    def test_sheet_qualified_range_clusters_correctly(self):
        """A dragged formula referencing a sheet-qualified range still
        clusters correctly -- this is the case the old regex-based
        to_r1c1() could never fix (Sheet1!A1:Sheet1!B1 ambiguity)."""
        rows = [
            ("Sheet2", "D2", "=SUM(Sheet1\x21A2:Sheet1\x21B2)"),
            ("Sheet2", "D3", "=SUM(Sheet1\x21A3:Sheet1\x21B3)"),
        ]
        clusters, _, unparsed = cluster_cells_ast(rows)
        self.assertEqual(unparsed, [])
        self.assertEqual(len(clusters), 1)


if __name__ == "__main__":
    unittest.main()
