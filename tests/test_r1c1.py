import unittest

from archon.formula.r1c1 import parse_address, to_a1, to_r1c1

CASES = [
    ("=B6*C6", "D6", "=RC[-2]*RC[-1]"),
    ("=B7*C7", "D7", "=RC[-2]*RC[-1]"),
    ("=A1", "A1", "=RC"),
    ("=$A$1+B2", "C3", "=R1C1+R[-1]C[-1]"),
    ("=$A1+B$1", "C3", "=R[-2]C1+R1C[-1]"),
    ("=SUM(B2:B100)", "B101", "=SUM(R[-99]C:R[-1]C)"),
    ("=SUM($B$2:B2)", "C2", "=SUM(R2C2:RC[-1])"),
    ("=Sheet2!A1*2", "B5", "=Sheet2!R[-4]C[-1]*2"),
    ("='Q1 Data'!B2", "C3", "='Q1 Data'!R[-1]C[-1]"),
    ("=Q1!A1", "B2", "=Q1!R[-1]C[-1]"),
    ('="A1 total: "&A1', "B1", '="A1 total: "&RC[-1]'),
    ("=LOG10(A1)", "B1", "=LOG10(RC[-1])"),
    ("=SUM(A:A)", "B1", "=SUM(C[-1]:C[-1])"),
    ("=SUM($A:$C)", "D1", "=SUM(C1:C3)"),
    ("=SUM(2:2)", "A5", "=SUM(R[-3]:R[-3])"),
    ("=IF(A2>0,B2,0)", "C2", "=IF(RC[-2]>0,RC[-1],0)"),
    ("=A1+ROUND(B1,2)", "C1", "=RC[-2]+ROUND(RC[-1],2)"),
    ("=XFE1", "A1", "=XFE1"),
    ("145000", "D4312", "145000"),
]

ROUND_TRIP = [c for c in CASES if not any(s in c[0] for s in ("A:A", "$A:$C", "2:2"))]


class TestToR1C1(unittest.TestCase):
    def test_cases(self) -> None:
        for a1, cell, expected in CASES:
            with self.subTest(formula=a1, cell=cell):
                self.assertEqual(to_r1c1(a1, cell), expected)

    def test_round_trip(self) -> None:
        for a1, cell, _ in ROUND_TRIP:
            with self.subTest(formula=a1, cell=cell):
                back = to_a1(to_r1c1(a1, cell), cell)
                self.assertEqual(back.replace("$", ""), a1.replace("$", ""))

    def test_dragged_formula_collapses_to_one_text(self) -> None:
        texts = {to_r1c1(f"=B{r}*C{r}", f"D{r}") for r in range(2, 10002)}
        self.assertEqual(len(texts), 1)

    def test_override_differs_from_dragged_formula(self) -> None:
        dragged = to_r1c1("=B4312*C4312", "D4312")
        self.assertNotEqual(to_r1c1("145000", "D4312"), dragged)

    def test_bad_address_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_address("not-a-cell")


if __name__ == "__main__":
    unittest.main()
