"""Tests for archon.cluster.bugs: override detection with downstream impact."""

import unittest

from archon.cluster.bugs import Bug, find_override_bugs
from archon.cluster.engine import cluster_cells_ast


def rows_with_override():
    """3 dragged rows, a hardcoded override at row 5, then 3 more dragged."""
    rows = [("Sheet1", f"D{r}", f"=B{r}*C{r}") for r in range(2, 5)]
    rows.append(("Sheet1", "D5", "145000"))
    rows += [("Sheet1", f"D{r}", f"=B{r}*C{r}") for r in range(6, 9)]
    return rows


class TestFindOverrideBugs(unittest.TestCase):
    """Core override detection: sandwiched constants vs. unrelated ones."""

    def test_sandwiched_constant_is_a_bug(self):
        """A constant inside a cluster's row span is flagged."""
        rows = rows_with_override()
        clusters, constants, _ = cluster_cells_ast(rows)
        bugs = find_override_bugs(rows, clusters, constants)
        self.assertEqual(len(bugs), 1)
        bug = bugs[0]
        self.assertEqual(bug.sheet, "Sheet1")
        self.assertEqual(bug.cell, "D5")
        self.assertEqual(bug.hardcoded_value, "145000")

    def test_example_formula_comes_from_nearest_member(self):
        """The example formula is drawn from a real cluster member."""
        rows = rows_with_override()
        clusters, constants, _ = cluster_cells_ast(rows)
        bugs = find_override_bugs(rows, clusters, constants)
        bug = bugs[0]
        self.assertIn(bug.example_formula_cell, ("D4", "D6"))
        self.assertEqual(
            bug.example_formula,
            {"D4": "=B4*C4", "D6": "=B6*C6"}[bug.example_formula_cell],
        )

    def test_constant_outside_cluster_span_not_flagged(self):
        """A header or totals row above/below the cluster isn't a bug."""
        rows = [("Sheet1", "D1", "Revenue")]
        rows += [("Sheet1", f"D{r}", f"=B{r}*C{r}") for r in range(2, 5)]
        clusters, constants, _ = cluster_cells_ast(rows)
        bugs = find_override_bugs(rows, clusters, constants)
        self.assertEqual(bugs, [])

    def test_constant_in_unrelated_column_not_flagged(self):
        """A constant in a column with no cluster at all isn't a bug."""
        rows = [("Sheet1", "D2", "=B2*C2"), ("Sheet1", "F2", "999")]
        clusters, constants, _ = cluster_cells_ast(rows)
        bugs = find_override_bugs(rows, clusters, constants)
        self.assertEqual(bugs, [])

    def test_no_constants_no_bugs(self):
        """A column with no overrides at all produces no bugs."""
        rows = [("Sheet1", f"D{r}", f"=B{r}*C{r}") for r in range(2, 5)]
        clusters, constants, _ = cluster_cells_ast(rows)
        bugs = find_override_bugs(rows, clusters, constants)
        self.assertEqual(bugs, [])


class TestDownstreamTracing(unittest.TestCase):
    """Downstream impact: BFS over an optional dependency graph."""

    def test_downstream_traced_when_graph_given(self):
        """Every transitively dependent cell is listed, in BFS order."""
        rows = rows_with_override()
        clusters, constants, _ = cluster_cells_ast(rows)
        graph = {
            ("Sheet1", "D5"): [("Sheet1", "E5")],
            ("Sheet1", "E5"): [("Sheet1", "F5"), ("Sheet1", "G5")],
        }
        bugs = find_override_bugs(rows, clusters, constants, graph=graph)
        bug = bugs[0]
        self.assertTrue(bug.downstream_traced)
        self.assertEqual(
            set(bug.downstream),
            {("Sheet1", "E5"), ("Sheet1", "F5"), ("Sheet1", "G5")},
        )

    def test_no_graph_means_untraced_not_empty_impact(self):
        """Without a graph, downstream_traced is False, not a false 'no impact'."""
        rows = rows_with_override()
        clusters, constants, _ = cluster_cells_ast(rows)
        bugs = find_override_bugs(rows, clusters, constants)
        bug = bugs[0]
        self.assertFalse(bug.downstream_traced)
        self.assertEqual(bug.downstream, ())

    def test_cycle_in_graph_does_not_hang(self):
        """A circular dependency in the graph is handled, not looped forever."""
        rows = rows_with_override()
        clusters, constants, _ = cluster_cells_ast(rows)
        graph = {
            ("Sheet1", "D5"): [("Sheet1", "E5")],
            ("Sheet1", "E5"): [("Sheet1", "D5")],
        }
        bugs = find_override_bugs(rows, clusters, constants, graph=graph)
        self.assertEqual(bugs[0].downstream, (("Sheet1", "E5"),))

    def test_absolute_address_constant_still_matches_graph(self):
        """A constant whose own address has $ markers still finds its
        dependents in a graph that uses plain addresses."""
        rows = [("Sheet1", f"D{r}", f"=B{r}*C{r}") for r in range(2, 5)]
        rows.append(("Sheet1", "$D$5", "145000"))
        rows += [("Sheet1", f"D{r}", f"=B{r}*C{r}") for r in range(6, 9)]
        clusters, constants, _ = cluster_cells_ast(rows)
        graph = {("Sheet1", "D5"): [("Sheet1", "E5")]}
        bugs = find_override_bugs(rows, clusters, constants, graph=graph)
        self.assertEqual(bugs[0].downstream, (("Sheet1", "E5"),))

    def test_cell_with_no_dependents_has_empty_downstream(self):
        """A traced cell with no entry in the graph has empty downstream."""
        rows = rows_with_override()
        clusters, constants, _ = cluster_cells_ast(rows)
        bugs = find_override_bugs(rows, clusters, constants, graph={})
        bug = bugs[0]
        self.assertTrue(bug.downstream_traced)
        self.assertEqual(bug.downstream, ())

    def test_duplicate_dependent_edges_deduplicated(self):
        """A formula like =E5+E5 could list E5 twice as a dependent; the
        downstream list must not contain E5 twice."""
        rows = rows_with_override()
        clusters, constants, _ = cluster_cells_ast(rows)
        graph = {("Sheet1", "D5"): [("Sheet1", "E5"), ("Sheet1", "E5")]}
        bugs = find_override_bugs(rows, clusters, constants, graph=graph)
        self.assertEqual(bugs[0].downstream, (("Sheet1", "E5"),))

    def test_self_edge_excludes_start_from_downstream(self):
        """If start appears in its own dependent list, it must not appear
        in its own downstream result."""
        rows = rows_with_override()
        clusters, constants, _ = cluster_cells_ast(rows)
        graph = {("Sheet1", "D5"): [("Sheet1", "D5"), ("Sheet1", "E5")]}
        bugs = find_override_bugs(rows, clusters, constants, graph=graph)
        self.assertEqual(bugs[0].downstream, (("Sheet1", "E5"),))


if __name__ == "__main__":
    unittest.main()
