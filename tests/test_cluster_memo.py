"""The R1C1 memo in cluster_cells_ast must give exactly the per-cell result."""

from archon.cluster.engine import cluster_cells_ast, cluster_id_for
from archon.formula.parser import ParseError
from archon.formula.r1c1 import num_to_col, parse_address


def _direct(rows):
    """Reference implementation: cluster_id_for on every cell, no memo."""
    clusters, unparsed = {}, []
    for sheet, addr, text in rows:
        if not text.startswith("="):
            continue
        try:
            cid = cluster_id_for(text, addr)
        except (ParseError, ValueError):
            unparsed.append((sheet, addr, text))
            continue
        row, col = parse_address(addr)
        clusters.setdefault((sheet, num_to_col(col), cid), []).append((row, addr))
    return {k: sorted(v) for k, v in clusters.items()}, unparsed


ROWS = (
    [("S", f"C{r}", f"=A{r}*B{r}") for r in range(2, 40)]
    + [("S", f"D{r}", f'="A{r}"&B{r}') for r in range(2, 10)]  # cell-like text in quotes
    + [("S", f"E{r}", f"='Q1 2024'!A{r}*$F$1") for r in range(2, 10)]
    + [("S", f"G{r}", f"=SUM(A$2:A{r})") for r in range(2, 10)]  # growing range
    + [("S", f"H{r}", f"=A{r}+(") for r in range(2, 6)]  # broken: memoised failure
    + [("T", f"C{r}", f"=A{r}*B{r}") for r in range(2, 6)]  # same text, other sheet
    + [("S", "Z1", "145000")]
)


def test_memo_matches_per_cell_clustering():
    clusters, _constants, unparsed = cluster_cells_ast(ROWS)
    expected_clusters, expected_unparsed = _direct(ROWS)
    assert clusters == expected_clusters
    assert unparsed == expected_unparsed
    assert len(unparsed) == 4
