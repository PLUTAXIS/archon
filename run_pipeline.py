"""MVP runner: cluster -> bugs -> cycles -> summary.
Run: python run_pipeline.py For_Senpai/extracted_formulas.json
"""
import sys, json
from archon.cluster.engine import load_formulas, cluster_cells, summarise
from archon.cluster.bugs import find_override_bugs
from archon.cluster.cycles import find_cycles, suggest_classification

path = sys.argv[1] if len(sys.argv) > 1 else "For_Senpai/extracted_formulas.json"
rows = load_formulas(path)

# 1. Cluster
clusters, constants = cluster_cells(rows)
stats = summarise(clusters, constants)
print("\n=== CLUSTERING ===")
print(f"  Formula cells : {stats['formula_cells']}")
print(f"  Clusters      : {stats['clusters']}")
print(f"  Constants     : {stats['constant_cells']}")
print(f"  Compression   : {stats['compression_ratio']:.1f}x")

# 2. Bugs
bugs = find_override_bugs(rows, clusters, constants)
print(f"\n=== OVERRIDE BUGS ({len(bugs)}) ===")
for b in bugs:
    print(f"  [{b.sheet}] {b.cell} = {b.hardcoded_value!r}  (expected: {b.example_formula})")

# 3. Cycles (needs a dependency graph; skip if none available yet)
print("\n=== CYCLES ===")
print("  (dependency graph not wired yet ? Mainak's dag_graph.json needed)")

# 4. Save output
out = {
    "stats": stats,
    "bugs": [{"sheet": b.sheet, "cell": b.cell, "hardcoded_value": b.hardcoded_value,
               "example_formula": b.example_formula} for b in bugs],
}
with open("pipeline_output.json", "w") as f:
    json.dump(out, f, indent=2)
print("\n=== OUTPUT saved to pipeline_output.json ===")
