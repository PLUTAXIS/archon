# ARCHON (Plutaxis)

Spreadsheet archaeology: upload an Excel workbook (.xlsx / .xlsm) and get a dependency
map, a bug ledger (hardcoded overrides with the cells they break), circular references,
plain-English explanations and risk flags. v1 scope is in [SCOPE.md](SCOPE.md).

## Demo in one command

```
docker compose up --build
```

Open http://localhost:8080. The API container has no outbound network, so workbook
data cannot leave the machine. Use **Download PDF** on the results page for the audit pack.

## Local development

```
uv sync --locked
uv run pytest -q
uv run uvicorn archon.api.main:app --port 8765
cd archon-web && npm ci && VITE_API_BASE_URL=http://localhost:8765 npm run dev
```

## Command line

```
python -m archon.scrubber.scrubber MyFile.xlsm          # client side: mask data first
python run_pipeline.py MyFile.scrubbed.xlsm -o audit.json
python scripts/benchmark.py book1.xlsm book2.xlsm      # coverage, timing, determinism
```
