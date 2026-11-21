# ARCHON (Plutaxis)

**Spreadsheet archaeology.** Upload an Excel workbook (`.xlsx` / `.xlsm`) and ARCHON reads
every formula and macro without Microsoft Office, then tells you what the file really does
and where it is broken:

- a **0–100 workbook risk score** with a reason for every point
- a **bug ledger**: values typed over a copied formula, how far they are from what the
  formula would give, and every cell they break
- **circular references**, with a suggested verdict a reviewer can confirm
- **macro findings**: macros that overwrite formulas, `On Error Resume Next`, writes to
  cells chosen at run time
- **plain-English explanations** of every formula, with cells named by their headers
  ("Revenue: product of Price (A2) and Qty (B2)")
- an interactive **dependency map** (click a bug to see exactly what it breaks)
- a **specification**: per sheet, inputs and every calculation in dependency order
- a printable **audit pack** (Download PDF on the results page)

Everything is deterministic: the same file always gives the same report, and no language
model is involved. A formula ARCHON cannot read exactly is listed as *unverified*, never
guessed. v1 scope is locked in [SCOPE.md](SCOPE.md).

---

## Privacy model

1. **Scrub on the client's machine.** `archon/scrubber/scrubber.py` is a single,
   standard-library-only script (no network code) that masks text, numbers, comments,
   document properties, charts, pictures, pivot-table and external-link copies of data,
   file paths, print headers and quoted text inside formulas. The same value always gets
   the same dummy, so formula logic still lines up after scrubbing. Formula structure,
   sheet names, layout and VBA are kept.
2. **Verify before sending.** `verify_scrub.py` checks the scrubbed copy against the
   original and scans every part for words you list.
3. **Audit offline.** In the Docker demo the API container has no route to the internet.

---

## Quick start

### Demo (one command)

```
docker compose up --build
```

Open http://localhost:8080. Only the web container publishes a port, and only on
localhost; the API container sits on an internal network with no outbound access.

### Local development

Requires Python 3.12+ with [uv](https://docs.astral.sh/uv/) and Node 22.

```
uv sync --locked
uv run pytest -q
uv run uvicorn archon.api.main:app --port 8765

cd archon-web
npm ci
VITE_API_BASE_URL=http://localhost:8765 npm run dev     # bash; opens http://localhost:5173
$env:VITE_API_BASE_URL = "http://localhost:8765"; npm run dev   # PowerShell
```

Without `VITE_API_BASE_URL` the web app talks to the hosted API.

---

## Auditing a client file

```
# 1. Client side: mask the data (writes MyFile.scrubbed.xlsm, never touches the original)
python archon/scrubber/scrubber.py MyFile.xlsm                    # add --keep-headers to keep row-1 column names

# 2. Check nothing confidential is left (list real names, clients, amounts)
python -m archon.scrubber.verify_scrub MyFile.xlsm MyFile.scrubbed.xlsm "Acme Corp" "Jane Doe"

# 3. Audit: in the browser, or from the command line
python run_pipeline.py MyFile.scrubbed.xlsm -o audit.json
```

Measure a batch of workbooks (coverage, findings, timing, determinism):

```
python scripts/benchmark.py book1.xlsm book2.xlsm
```

On Windows with Excel installed, `scripts/excel_roundtrip.ps1` builds a workbook with pivot
tables, pictures, external links and quoted text, then confirms the scrubbed copy opens in
real Excel without a repair. Usage is at the top of the script.

---

## API

| Method | Path | What it does |
|---|---|---|
| `POST` | `/audit/jobs` | Upload a workbook (multipart field `file`); starts a background audit, returns `job_id` |
| `GET` | `/audit/jobs/{job_id}` | The job's current stage (`step` of `steps`), then its full result when `status` is `done` |
| `POST` | `/audit` | Upload and wait for the full result in one request |
| `GET` | `/health` | Liveness check |

Uploads are limited to 20 MB. Password-protected files are refused with a clear message.
Interactive docs: `/docs` on the running API.

---

## How it works

`archon/pipeline.py` chains the stages; each stage is its own module.

| Stage | Module | Output |
|---|---|---|
| Extract cells, formulas, sheets, names, VBA (no Office) | `archon/ingest/xlsx.py`, `vba.py` | Contract A: `RawExtract` |
| Expand named ranges, bound whole columns | `archon/names.py` | |
| Group copied formulas by relative (R1C1) form | `archon/cluster/engine.py` | logic blocks |
| Dependency graph: formulas, macro reads and writes | `archon/graph/graph_builder.py` | |
| Hardcoded overrides and their downstream impact | `archon/cluster/bugs.py` | Contract C: bug ledger |
| Circular references (Tarjan) | `archon/cluster/cycles.py` | |
| Explanations: patterns, functions, header labels | `archon/explain/` | explanation records |
| Risk per formula and per workbook | `archon/explain/risk.py`, `archon/risk/scorecard.py` | |
| Map of blocks, inputs, macros | `archon/pipeline.py` | Contract B: `DagGraph` |
| Report sections | `archon/explain/composer.py` | Contract F: report |

Contracts are Pydantic models in `archon/contracts/` and are checked in CI.

**Rules are data, not code.** Behaviour you may want to tune lives in YAML:

| File | Controls |
|---|---|
| `archon/explain/patterns/*.yaml` | formula idioms and their sentences |
| `archon/explain/functions.yaml` | how functions are read aloud (MAX, IF, LEFT, …) |
| `archon/explain/vocab/*.yaml` | business vocabulary for column headers |
| `archon/explain/risk_rules.yaml` | risk points per formula flag |
| `archon/risk/scorecard.yaml` | workbook score: four weighted axes (30/30/25/15) |

---

## Repository layout

```
archon/
  api/            FastAPI app (/audit, background jobs)
  ingest/         Contract A extraction (.xlsx/.xlsm, VBA via oletools)
  formula/        formula tokenizer, parser, R1C1 conversion
  cluster/        grouping, override bugs, circular references
  graph/          dependency graph builder (formulas + VBA)
  explain/        explanations, labels, risk, report composer
  risk/           workbook scorecard
  scrubber/       client-side scrubber and verifier
  contracts/      data contracts shared by every stage
  guardian/       PR policy and risk evaluation used by the repo's bots
  parity/, transpile/   v2 (parity tolerance policy; transpiler not built)
  names.py, pipeline.py
archon-web/       React app: upload, report, map, specification, PDF
landing/          marketing site
scripts/          benchmark, Excel round trip, golden-file helpers
tests/            unit, contract, golden determinism and end-to-end tests
docker-compose.yml, Dockerfile, archon-web/Dockerfile
```

---

## Tests and CI

```
uv run pytest -q                 # everything
uv run ruff check archon tests   # lint
uv run mypy --strict archon/contracts
```

CI (`.github/workflows/ci.yml`) runs lint, strict types on the contracts, unit tests, an
end-to-end determinism step, and a web lint and build. Repo guards block raw client data
(`.xlsx`, `.accdb`, the drop folders) from pull requests, except synthetic fixtures under
`tests/`. Note that `.gitignore` excludes workbook files, so add a new test fixture with
`git add -f`.

---

## Scope and known limits

In v1: audit report, bug ledger, map, specification, scorecard. Moved to v2 (see
[SCOPE.md](SCOPE.md)): Python transpilation, parity certificate, migration shell,
Access (`.accdb`/`.mdb`) and binary `.xlsb` analysis.

Known limits of the current build:

- Macro cell references are followed only when the target is fixed in the code. A
  reference through `ActiveSheet`, or built at run time (`Range("A" & i)`), is listed as
  a finding but not traced.
- A formula outside the known patterns and `functions.yaml` is reported as unverified.
- Explanations are structured sentences, not long-form prose.
- The scrubber masks dates as random numbers, so masked dates are not real dates.
- Background jobs live in the API process's memory: one server, lost on restart.
- Scorecard weights are a proposal awaiting sign-off.
