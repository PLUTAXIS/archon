from pathlib import Path
from archon.ingest.xlsx import extract

FIXTURE = Path(__file__).parent / "fixtures" / "dragged_10k.xlsx"


def test_dragged_range_yields_formula_per_cell():
    """Every cell in a dragged 10k range must have a non-null formula."""
    if not FIXTURE.exists():
        return  # skip if fixture not available

    result = extract(FIXTURE)
    g = [c for c in result.cells if c.col == 7]

    assert len(g) == 10_000, f"Expected 10,000 cells, got {len(g)}"
    assert all(c.formula is not None for c in g), \
        "Some cells in dragged range have no formula"
    