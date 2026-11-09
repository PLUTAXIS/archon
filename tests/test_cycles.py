"""Tests for archon.cluster.cycles: Tarjan cycle detection and labeling."""

import unittest

from archon.cluster.cycles import (
    Cycle,
    classify_cycle,
    find_cycles,
    suggest_classification,
)


class TestFindCycles(unittest.TestCase):
    """Tarjan's SCC algorithm applied to a cell dependency graph."""

    def test_simple_three_cell_cycle(self):
        """A->B->C->A is found as one 3-member cycle."""
        graph = {
            ("S", "A"): [("S", "B")],
            ("S", "B"): [("S", "C")],
            ("S", "C"): [("S", "A")],
        }
        cycles = find_cycles(graph)
        self.assertEqual(len(cycles), 1)
        self.assertEqual(cycles[0].members, frozenset({("S", "A"), ("S", "B"), ("S", "C")}))
        self.assertIsNone(cycles[0].classification)

    def test_self_loop_is_a_cycle(self):
        """A cell that reads its own address is a 1-member cycle."""
        graph = {("S", "A"): [("S", "A"), ("S", "B")]}
        cycles = find_cycles(graph)
        self.assertEqual(len(cycles), 1)
        self.assertEqual(cycles[0].members, frozenset({("S", "A")}))

    def test_straight_chain_has_no_cycles(self):
        """A->B->C with no edge back is not a cycle."""
        graph = {("S", "A"): [("S", "B")], ("S", "B"): [("S", "C")]}
        self.assertEqual(find_cycles(graph), [])

    def test_two_independent_cycles_found_separately(self):
        """Two unrelated cycles in the same graph are reported separately."""
        graph = {
            ("S", "A"): [("S", "B")],
            ("S", "B"): [("S", "A")],
            ("S", "C"): [("S", "D")],
            ("S", "D"): [("S", "C")],
        }
        cycles = find_cycles(graph)
        member_sets = {c.members for c in cycles}
        self.assertEqual(
            member_sets,
            {frozenset({("S", "A"), ("S", "B")}), frozenset({("S", "C"), ("S", "D")})},
        )

    def test_empty_graph_no_cycles(self):
        """An empty graph has no cycles."""
        self.assertEqual(find_cycles({}), [])

    def test_deep_chain_does_not_raise_recursion_error(self):
        """A very deep acyclic chain doesn't blow the recursion limit --
        this is the whole reason Tarjan is implemented iteratively here."""
        graph = {("S", str(i)): [("S", str(i + 1))] for i in range(20000)}
        self.assertEqual(find_cycles(graph), [])

    def test_mutual_pair_plus_tail_only_cycle_is_reported(self):
        """A->B->A with a non-cyclic C hanging off B: only {A,B} is a cycle."""
        graph = {
            ("S", "A"): [("S", "B")],
            ("S", "B"): [("S", "A"), ("S", "C")],
        }
        cycles = find_cycles(graph)
        self.assertEqual(len(cycles), 1)
        self.assertEqual(cycles[0].members, frozenset({("S", "A"), ("S", "B")}))


class TestSuggestClassification(unittest.TestCase):
    """The heuristic suggestion -- advisory, never authoritative."""

    def test_iterative_function_suggests_logic(self):
        """A cycle containing IRR(...) suggests 'logic'."""
        cycle = Cycle(members=frozenset({("S", "A"), ("S", "B")}))
        formulas = {("S", "A"): "=IRR(B1:B10)", ("S", "B"): "=A1*2"}
        label, reason = suggest_classification(cycle, formulas)
        self.assertEqual(label, "logic")
        self.assertIn("IRR", reason)

    def test_no_iterative_function_suggests_error(self):
        """A cycle with no iterative-calc function suggests 'error'."""
        cycle = Cycle(members=frozenset({("S", "A"), ("S", "B")}))
        formulas = {("S", "A"): "=B1+1", ("S", "B"): "=A1+1"}
        label, reason = suggest_classification(cycle, formulas)
        self.assertEqual(label, "error")

    def test_suggestion_is_case_insensitive(self):
        """Lowercase function names are still detected."""
        cycle = Cycle(members=frozenset({("S", "A")}))
        formulas = {("S", "A"): "=rate(12,-100,1000)"}
        label, _ = suggest_classification(cycle, formulas)
        self.assertEqual(label, "logic")

    def test_missing_formula_text_does_not_crash(self):
        """A cell with no entry in formulas is treated as empty text."""
        cycle = Cycle(members=frozenset({("S", "A"), ("S", "B")}))
        label, _ = suggest_classification(cycle, {})
        self.assertEqual(label, "error")

    def test_xirr_does_not_also_match_irr(self):
        """XIRR(...) should report only XIRR, not also IRR as a substring."""
        cycle = Cycle(members=frozenset({("S", "A")}))
        formulas = {("S", "A"): "=XIRR(B1:B10,C1:C10)"}
        label, reason = suggest_classification(cycle, formulas)
        self.assertEqual(label, "logic")
        self.assertIn("XIRR", reason)
        self.assertNotIn("IRR,", reason)
        self.assertNotRegex(reason, r"(?<![A-Z])IRR(?!R)")

    def test_intrate_does_not_match_rate_suggests_error(self):
        """INTRATE(...) should not be mistaken for RATE(...)."""
        cycle = Cycle(members=frozenset({("S", "A")}))
        formulas = {("S", "A"): "=INTRATE(A1,B1,C1,D1)"}
        label, _ = suggest_classification(cycle, formulas)
        self.assertEqual(label, "error")


class TestClassifyCycle(unittest.TestCase):
    """Recording the human's actual classification decision."""

    def test_classify_sets_label_and_note(self):
        """classify_cycle returns a new Cycle with the label and note set."""
        cycle = Cycle(members=frozenset({("S", "A"), ("S", "B")}))
        labeled = classify_cycle(cycle, "logic", "Confirmed with Wrik: depreciation schedule")
        self.assertEqual(labeled.classification, "logic")
        self.assertEqual(labeled.note, "Confirmed with Wrik: depreciation schedule")

    def test_classify_does_not_mutate_original(self):
        """The original Cycle is untouched (Cycle is frozen)."""
        cycle = Cycle(members=frozenset({("S", "A")}))
        classify_cycle(cycle, "error")
        self.assertIsNone(cycle.classification)


if __name__ == "__main__":
    unittest.main()
