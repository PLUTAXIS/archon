Builds dag_graph.json from formulas + decompiled VBA text.

Input (invented sample format, not final - Saba's may differ)
json
{
  "formulas": [
    {"sheet": "Budget", "cell": "C2", "formula": "=A2+B2", "cluster": "R1C1-001"}
  ],
  "vba": [
    {"module": "Module1", "default_sheet": "Budget", "code": "Sub A()\n Range(\"A2\").Value = 1\nEnd Sub"}
  ]
}

cluster and default_sheet are optional. default_sheet is the sheet used for Range(...) with no sheet named. Without it, such writes become "unknown".

Output
nodes: cells (Sheet!A1), types: formula, value, range, vba_proc, vba_write_range_unknown.
edges: source -> target, label formula (precedent -> formula cell) or vba_write (VBA procedure -> cell).
vba_unknown_writes: dynamic writes (module, procedure, line, text, reason) for Sneha. They are also nodes, flagged, never dropped.
meta: counts and has_cycles.
Validation (nothing is written if it fails)

No orphan nodes, every edge labelled, graph has both formula and vba_write edges.

Limits

Whole-column refs (A:A), named ranges, and R1C1-style formulas are not read as references. Ranges over 2000 cells become one range node. Only Range/Cells writes (and x.Value =) are detected; statements joined with : on one line are not split. Cell reads in VBA make no edges.