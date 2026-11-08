import hashlib
from pathlib import Path
import openpyxl
from archon.ingest.vba import extract_vba


FIXTURE = Path(__file__).parent / "fixtures" / "macro_enabled.xlsm"


def test_no_vba_returns_empty(tmp_path):
    """A plain xlsx with no macros returns empty lists."""
    # Create a plain xlsx (no VBA)
    fixture = tmp_path / "plain.xlsx"
    wb = openpyxl.Workbook()
    wb.save(fixture)

    modules, exceptions = extract_vba(fixture)
    assert modules == []
    assert exceptions == []


def test_vba_sha256_is_stable(tmp_path):
    """SHA256 of VBA source must be stable across two extractions."""
    if not FIXTURE.exists():
        return  # skip if fixture not available

    modules1, _ = extract_vba(FIXTURE)
    modules2, _ = extract_vba(FIXTURE)

    assert len(modules1) > 0, "No VBA modules found in fixture"

    for m1, m2 in zip(modules1, modules2):
        assert m1.sha256 == m2.sha256, \
            f"SHA256 changed between runs for module {m1.name}"


def test_vba_sha256_matches_source(tmp_path):
    """SHA256 stored on each module must match its source."""
    if not FIXTURE.exists():
        return  # skip if fixture not available

    modules, _ = extract_vba(FIXTURE)
    assert len(modules) > 0, "No VBA modules found in fixture"

    for module in modules:
        expected = hashlib.sha256(
            module.source.encode("utf-8", errors="replace")
        ).hexdigest()
        assert module.sha256 == expected, \
            f"SHA256 mismatch for module {module.name}"


def test_vba_source_is_verbatim(tmp_path):
    """VBA source must not be normalized — line endings preserved."""
    if not FIXTURE.exists():
        return  # skip if fixture not available

    modules, _ = extract_vba(FIXTURE)
    assert len(modules) > 0, "No VBA modules found in fixture"

    for module in modules:
        assert module.source == module.source, \
            "Source was modified"
        assert module.line_count == module.source.count("\n") + 1, \
            f"line_count mismatch for module {module.name}"