"""Golden determinism check: canonical-hash every JSON fixture against a committed manifest.

Fails on fixture drift (unordered serialization, dict ordering, etc.).
Regenerate the baseline explicitly with: python tests/test_determinism_golden.py
"""
import hashlib
import json
import pathlib

HERE = pathlib.Path(__file__).parent
FIXTURES = sorted((HERE.parent).rglob("*.json"))
MANIFEST = HERE / "golden" / "hashes.txt"


def canonical_hash(path: pathlib.Path) -> str:
    """Return the SHA-256 of the fixture's canonical (sorted-key, compact) JSON form."""
    data = json.loads(path.read_text(encoding="utf-8"))
    blob = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def test_fixtures_match_golden_manifest():
    """Every JSON fixture's canonical hash must equal its committed manifest entry."""
    assert MANIFEST.exists(), (
        "tests/golden/hashes.txt missing. Regenerate the baseline explicitly with: "
        "python tests/test_determinism_golden.py"
    )
    lines = [
        f"{canonical_hash(p)}  {p.relative_to(HERE.parent).as_posix()}" for p in FIXTURES
    ]
    expected = MANIFEST.read_text(encoding="utf-8").splitlines()
    assert lines == expected, (
        "Determinism drift detected. Diff fixtures against tests/golden/hashes.txt; "
        "if the change is intentional, regenerate with: python tests/test_determinism_golden.py"
    )


if __name__ == "__main__":
    MANIFEST.write_text(
        "\n".join(f"{canonical_hash(p)}  {p.relative_to(HERE.parent).as_posix()}" for p in FIXTURES) + "\n",
        encoding="utf-8",
    )
    print(f"Regenerated {MANIFEST} ({len(FIXTURES)} fixtures)")
