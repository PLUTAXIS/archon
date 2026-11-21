# Plutaxis - Progress and Context (updated 2026-10-31)

> **Current entrypoints (2026-11-21).** The paths in the sections below are historical.
> Use these instead; nothing should be run from old root copies:
> - Scrub a client file: `python -m archon.scrubber.scrubber MyFile.xlsm`
> - Audit a workbook (CLI): `python run_pipeline.py MyFile.xlsm -o audit.json`
> - Coverage, timing and determinism on real workbooks: `python scripts/benchmark.py a.xlsm b.xlsm`
> - Demo (API + web, no outbound network): `docker compose up --build`, then http://localhost:8080
> - Graph builder: `archon/graph/graph_builder.py` (called by `archon/pipeline.py`)
> - Ingestion: `archon/ingest/xlsx.py` (Contract A). Saba's drop-folder tools moved to
>   `archon/ingest/ingestion_core.py` and `archon/ingest/watcher.py`.

Overall progress: about 22% (my own estimate, not measured).
Rough split: scrubber v1 done, graph builder done, Docker VPC 0%, lead generation 0%,
real-Excel and real-data testing 0%, integration with teammates' pieces 0%.

## 1. The project
Plutaxis (internal docs also say "Archon"): spreadsheet archaeology. Clients send Excel files.
We find hidden formula/macro damage and sell a $9,500 audit pack.

Owner of this repo: Mainak (backend core, DevOps, technical outreach). Beginner: does not write
code, only runs commands and reports back.

Mainak's deliverables:
1. scrubber.py (DONE v1)
2. Unified dependency graph dag_graph.json (builder DONE, real data not yet tried)
3. Docker VPC (NOT STARTED, Docker not installed)
4. 50 leads/day into Arnab's sheet, CFO + Head of Audit contacts (NOT STARTED)

Pipeline: client runs scrubber -> Saba extracts formulas + VBA text -> Senpai (R1C1 clusters,
bug list) + Mainak (graph) -> Sneha (AI report), Arnab/Deepsikha (UI).
SLAs: scrubbed file to Saba within 1 hour; dag_graph.json + bug list within 6 hours of raw data.

## 2. Environment
- Windows, PowerShell, VS Code, Python 3 (venv in the repo folder, named .venv).
- Repo folder: C:\Users\Maina\Plutaxis-repo  (clone of https://github.com/PLUTAXIS/plutaxis, branch main)
- The old folder C:\Users\Maina\Plutaxis is only a local backup with a separate git history. Ignore it.
- NOTE: C:\Plutaxis does NOT exist. Always use the path above.
- Activate venv in each new PowerShell window:  .venv\Scripts\Activate.ps1
- Git 2.55 installed. Docker NOT installed. openpyxl installed in the venv (tests only).
- networkx 3.7 installed (runtime dependency of graph_builder.py).

## 3. What is in the repo (all pushed to GitHub)
- scrubber.py (218 lines, standard library only, no network)
- graph_builder.py (about 320 lines, needs networkx)
- GRAPH_BUILDER.md (input format and limits of the graph builder)
- samples\sample_input.json (invented sample input for the graph builder)
- tests\__init__.py (empty, makes plain "python -m unittest" find the tests)
- tests\test_scrubber.py (17 tests), tests\test_graph_builder.py (22 tests)
- requirements.txt (networkx>=3.0), .gitignore (ignores dag_graph.json, __pycache__/, .venv/, .vscode/)
- README.md (starter file from GitHub, not yet written)

Commits: 01434e6 Initial commit; 92c768c Add graph builder with tests and sample;
0443b67 Add scrubber v1 with tests.

## 4. How to run (from C:\Users\Maina\Plutaxis-repo, venv active)
    python -m unittest
Expected: Ran 39 tests ... OK  (error and VALIDATION FAILED lines inside the output are normal,
they come from tests that check bad input is refused).

    python graph_builder.py samples\sample_input.json -o dag_graph.json
Expected: OK: 16 nodes, 17 edges, 3 unknown VBA writes, cycles=False -> dag_graph.json

    python scrubber.py MyFile.xlsm
Creates MyFile.scrubbed.xlsm, never changes the original.

## 5. Scrubber v1 (verified: 17 tests pass on Mainak's machine)
Masks text and typed numbers (random digits, same shape; equal inputs get equal dummies), cell
comments, authors and document properties; strips cached formula results; masks chart text and
caches. Keeps formulas, sheet names, layout, top-row headers readable, and VBA byte-for-byte.
Known limits: dates are masked, text inside formulas is untouched (warned), pivot caches,
external links and media are not scrubbed (the script lists them), .xlsb and password-protected
files are rejected with a plain message.
NOT TESTED: a real .xlsm with real VBA, opening the output in real Excel.

## 6. Graph builder (verified: 22 tests pass; sample builds as expected)
Input JSON (format INVENTED by us, Saba's real format is not final):
    {"formulas": [{"sheet": "S", "cell": "C2", "formula": "=A2+B2", "cluster": "R1C1-001"}],
     "vba": [{"module": "Module1", "default_sheet": "S", "code": "<decompiled VBA text>"}]}
"cluster" and "default_sheet" are optional.

Output dag_graph.json has: meta (counts, has_cycles), nodes, edges, vba_unknown_writes.
- Node ids: "Sheet!A1". Types: formula, value, range, vba_proc, vba_write_range_unknown.
- Edges: source -> target, label is "formula" (precedent -> formula cell) or "vba_write"
  (VBA procedure -> cell). No other labels allowed.
- Static VBA writes are resolved (Range("A1"), Worksheets("X").Range(...), Cells(3, 2), single-line
  If ... Then). Dynamic writes (Range("A" & i), Cells(i, 1), With-block .Range, Offset, variable.Value)
  become nodes of type vba_write_range_unknown with module, procedure, line number, text, reason,
  flagged=true. They are never dropped and are also listed in vba_unknown_writes for Sneha.
- Validation (nothing is written if it fails): no orphan nodes, every edge labelled, graph built
  from BOTH formula edges and vba_write edges.
- Cycles are reported in meta.has_cycles, not treated as an error (circular references are a finding).
- R1C1 clusters are only a node attribute ("cluster"), not separate nodes. To confirm with Senpai.
- Ranges over 2000 cells become one "range" node.
Known limits: whole-column refs (A:A), named ranges and R1C1-style formula text are not read as
references; statements joined with ":" on one VBA line are not split; VBA reads make no edges;
Range with no sheet and no default_sheet counts as unknown; a formula with no references
(such as "=5") becomes an orphan and FAILS validation, so a real workbook with constant formulas
needs a decision (see next steps).
NOT TESTED: Saba's real data, real VBA, large workbooks.

## 7. Next steps (in my suggested order)
1. Real-Excel check: scrub a small generated workbook, Mainak opens it in Excel, reports what
   happens (opens cleanly / repair prompt / error). Biggest untested risk.
2. Agree the real input formats with Saba (formulas + VBA text) and Senpai (R1C1 clusters, bug
   list). Then adapt graph_builder.py to them.
3. Decide the policy for orphan nodes (constant-only formulas): keep strict, or attach to a
   "constants" node, or report as warning.
4. Docker: install Docker Desktop (needs restart), check "docker --version", then a Dockerfile that
   runs the tests and the sample; later the VPC layout (scrubber is client-side, graph is server-side).
5. Lead list: 50 leads/day, CFO + Head of Audit, into Arnab's sheet. Needs a source, format and
   rules about what data may be stored (no client data in git).
6. Write the real README.md.
7. Later: scrubber gaps (dates, text inside formulas, pivot caches, external links, media),
   timing checks against the 1h and 6h SLAs.

## 8. Mistakes and lessons so far
- Wrong folder: C:\Plutaxis does not exist. Use C:\Users\Maina\Plutaxis-repo.
- Pasting old terminal output together with commands breaks them. Paste only command lines.
- A stray character after a command (python -m unittest]) made it fail.
- Files that were "created" in earlier steps were not saved in the repo until checked with
  Test-Path or a file listing. Always verify with a line count or file list.
- Do not git push before the repo has the right remote. Never put passwords or tokens in chat or files.

## 9. How to work with me (paste this when restarting in a new chat)
I am Mainak, a beginner on Windows with VS Code and Python 3. I do not write code, I only run
commands and report back. Give me the finished code and tests, write tests first and tell me
the exact failure and pass counts to expect, give exact PowerShell commands plus the output I
should see, work in small steps, keep replies short and plain, ask at most one question,
diagnose any error I paste, never claim something works unless it has been seen working, keep a
running percentage, keep secrets and client data out of git, and remember everything in this file.