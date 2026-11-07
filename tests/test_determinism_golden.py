"""Golden determinism check: canonical-hash every fixture, fail on drift.

Catches unordered-set serialization, dict iteration order, and any
nondeterministic field leaking into contract artifacts.
"""
import hashlib
import json
import pathlib

FIXTURES = sorted(pathlib.Path("tests").rglob("*.json"))
MANIFEST = pathlib.Path("tests/golden/hashes.txt")


def canonical_hash(path: pathlib.Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    blob = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def test_fixtures_deterministic():
    lines = [f"{canonical_hash(p)}  {p}" for p in FIXTURES]
    if not MANIFEST.exists():  # bootstrap on first run
        MANIFEST.write_text("\n".join(lines) + "\n", encoding="utf-8")
    expected = MANIFEST.read_text(encoding="utf-8").splitlines()
    assert lines == expected, (
        "Determinism drift detected. Diff your fixtures against "
        "tests/golden/hashes.txt — if the change is intentional, "
        "delete hashes.txt and re-run to re-baseline."
    )
