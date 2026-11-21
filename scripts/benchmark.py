"""Real-workbook proof: coverage, findings, run time and determinism.

Run on scrubbed client-grade workbooks (never raw client data):
    python scripts/benchmark.py book1.xlsm book2.xlsm ...

For each file it runs the full pipeline twice and reports:
- coverage: logic blocks explained vs unverified, formula parse failure rate
  (SCOPE.md KPI: < 5%), and the most common unexplained formula shapes, which
  are the candidates for new patterns/*.yaml or vocab/*.yaml entries
- findings: override bugs, circular references, risk-flagged blocks, dynamic
  VBA writes, very hidden sheets (the demo needs 3+ per file)
- timing of each run, and whether both runs produced byte-identical output
"""

import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from archon.ingest.xlsx import extract
from archon.pipeline import run_extract


def _run(path: Path) -> tuple[dict, str, float]:
    start = time.perf_counter()
    result = run_extract(extract(path))
    elapsed = time.perf_counter() - start
    digest = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
    return result, digest, elapsed


def report(path: Path) -> bool:
    result, first, t1 = _run(path)
    _, second, t2 = _run(path)
    s = result["summary"]
    risk = next(x for x in result["report"]["sections"] if x["kind"] == "risk")["entries"]
    hidden = [e for e in result["extract"]["exceptions"] if e["code"] == "E_VERY_HIDDEN_SHEET"]
    blocks = s["explained_clusters"] + s["unverified_clusters"]
    findings = s["override_bugs"] + s["cycles"] + len(risk) + s["vba_dynamic_writes"] + len(hidden)

    print(f"\n== {path.name}")
    print(f"  cells {result['extract']['cell_count']:,}  formulas {s['formula_cells']:,}  "
          f"logic blocks {s['clusters']:,} ({s['compression_ratio']:.1f}x)  "
          f"VBA modules {len(result['extract']['vba_modules'])}")
    print(f"  coverage: {s['explained_clusters']}/{blocks} blocks explained "
          f"({s['explained_clusters'] / blocks:.0%})" if blocks else "  coverage: no formulas")
    print(f"  parse failure rate: {s['parse_failure_rate']:.2%} (KPI < 5%)")
    for shape in result["report"]["unmatched_shapes"][:5]:
        print(f"    unexplained shape x{shape['count']}: {shape['shape']}")
    print(f"  findings: {s['override_bugs']} overrides, {s['cycles']} cycles, {len(risk)} risk-flagged, "
          f"{s['vba_dynamic_writes']} dynamic VBA writes, {len(hidden)} very hidden sheets "
          f"-> {findings} total {'(OK, 3+)' if findings >= 3 else '(below the 3 the demo needs)'}")
    same = first == second
    print(f"  time: {t1:.1f}s then {t2:.1f}s   deterministic: {'yes' if same else 'NO - outputs differ'}")
    return same


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    results = [report(Path(p)) for p in sys.argv[1:]]  # report every file, even after a failure
    ok = all(results)
    sys.exit(0 if ok else 1)
