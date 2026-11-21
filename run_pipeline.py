"""Audit one workbook end to end and write the full result as JSON.

Run: python run_pipeline.py path/to/workbook.xlsm [-o audit.json]
"""

import argparse
import json
import sys
from pathlib import Path

from archon.ingest.xlsx import extract
from archon.pipeline import run_extract


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("workbook", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=Path("audit.json"))
    args = ap.parse_args(argv)

    result = run_extract(extract(args.workbook))
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    s = result["summary"]
    print(f"{args.workbook.name}: {s['formula_cells']} formulas -> {s['clusters']} logic blocks "
          f"({s['compression_ratio']:.1f}x)")
    print(f"  override bugs: {s['override_bugs']}  cycles: {s['cycles']}  "
          f"dynamic VBA writes: {s['vba_dynamic_writes']}")
    print(f"  explained: {s['explained_clusters']}  unverified: {s['unverified_clusters']}  "
          f"parse failures: {s['parse_failure_rate']:.1%}")
    print(f"  -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
