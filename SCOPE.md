# v1 Scope (LOCKED)
- Audit report + bug ledger ONLY
- Transpiler, migration shell, certificate signing → v2
# KPIs
- parse_failure_rate < 5% (reported by `/audit` as `analysis.summary.parse_failure_rate`)
- risk precision/recall published vs ExceLint

# Decision 2026-11-21: the deck follows this scope, not the other way round
v1 scope stays locked. `archon/transpile/` is empty, so the pitch deck must not
claim migration or parity as working today. Edits for the deck owner:

| Slide | Remove / change | Replace with |
|---|---|---|
| 2 | "21 days to get verifiable web application", "We can prove equivalence (ε ≤ 10⁻⁹)", "equivalence certificate", "Convert into verifiable code" | "72h audit report + bug ledger. Verified migration is on the v2 roadmap." |
| 3 | "Convert validated logic into FastAPI/SQL/React…", "Validated migration in 21 days", USP "Per-cell match proof", "certified migration in 1 workflow" | "Hardcoded-override, circular-reference and risk findings with the cells they affect" |
| 4 | "Parity certification", "Verified transpilation", Package 2 as a current offer | Move Package 2 under "Roadmap (v2)" |
| 6, 7 | Box "04 Verified transpilation"; "Transpiler" box and "Parity cert" output | End the flow at the audit report; grey out transpiler/parity as "v2" |
| 8 | "Verified Transpilation" column (ε ≤ 10⁻⁹ app) | Label the column "v2 roadmap" |
| 10 | "04 VERIFY & MIGRATE" card, "Migration Sprint" tier | Show the live report screen (bug ledger, cycles, risk) |
| 11 | "Python code generated was functionally identical … ε ≤ 10⁻⁹" | Delete the sentence (no generated code exists to back it) |
| 12 | (add) | "Verified migration + parity certificate (v2)" as the first roadmap item |
