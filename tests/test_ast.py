"""Tests for archon.formula.ast node types."""

import unittest
from dataclasses import FrozenInstanceError

from archon.formula.ast import BinOp, Func, Lit, Ref, UnaryOp


class TestNodes(unittest.TestCase):
    def test_lit_holds_value(self) -> None:
        self.assertEqual(Lit(5.0).value, 5.0)
        self.assertEqual(Lit("hello").value, "hello")
        self.assertEqual(Lit(True).value, True)

    def test_ref_fields(self) -> None:
        r = Ref(sheet="Sales", r1c1="RC[-1]", absolute=(False, True))
        self.assertEqual(r.sheet, "Sales")
        self.assertEqual(r.r1c1, "RC[-1]")
        self.assertEqual(r.absolute, (False, True))

    def test_binop_fields(self) -> None:
        node = BinOp("+", Lit(1.0), Lit(2.0))
        self.assertEqual(node.op, "+")
        self.assertEqual(node.left, Lit(1.0))
        self.assertEqual(node.right, Lit(2.0))

    def test_func_fields(self) -> None:
        node = Func("SUM", (Lit(1.0), Lit(2.0)))
        self.assertEqual(node.name, "SUM")
        self.assertEqual(node.args, (Lit(1.0), Lit(2.0)))

    def test_unaryop_defaults_to_prefix(self) -> None:
        node = UnaryOp("-", Lit(2.0))
        self.assertFalse(node.postfix)

    def test_unaryop_postfix(self) -> None:
        node = UnaryOp("%", Lit(50.0), postfix=True)
        self.assertTrue(node.postfix)

    def test_nodes_are_frozen(self) -> None:
        node = Lit(1.0)
        with self.assertRaises(FrozenInstanceError):
            node.value = 2.0  # type: ignore[misc]

    def test_nodes_are_hashable(self) -> None:
        a = BinOp("*", Ref(None, "RC[-2]", (False, False)), Ref(None, "RC[-1]", (False, False)))
        b = BinOp("*", Ref(None, "RC[-2]", (False, False)), Ref(None, "RC[-1]", (False, False)))
        self.assertEqual(hash(a), hash(b))
        self.assertEqual(a, b)

    def test_equal_structure_means_equal_nodes(self) -> None:
        tree1 = Func("SUM", (BinOp("*", Lit(1.0), Lit(2.0)),))
        tree2 = Func("SUM", (BinOp("*", Lit(1.0), Lit(2.0)),))
        self.assertEqual(tree1, tree2)
        self.assertEqual(hash(tree1), hash(tree2))

    def test_different_structure_means_different_nodes(self) -> None:
        tree1 = BinOp("+", Lit(1.0), Lit(2.0))
        tree2 = BinOp("-", Lit(1.0), Lit(2.0))
        self.assertNotEqual(tree1, tree2)


if __name__ == "__main__":
    unittest.main()
