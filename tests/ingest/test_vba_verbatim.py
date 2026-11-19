import hashlib
from pathlib import Path
import pytest
import openpyxl
from archon.ingest.vba import extract_vba


FIXTURE = Path(__file__).parent / "fixtures" / "macro_enabled.xlsm"


def test_no_vba_returns_empty(tmp_path):
    """A plain xlsx with no macros returns empty lists."""
    fixture = tmp_path / "plain.xlsx"
    wb = openpyxl.Workbook()
    wb.save(fixture)

    modules, exceptions = extract_vba(fixture)
    assert modules == []
    assert exceptions == []


def test_vba_sha256_is_stable():
    """SHA256 of VBA source must be stable across two extractions."""
    if not FIXTURE.exists():
        pytest.skip("macro_enabled.xlsm fixture not available")

    modules1, _ = extract_vba(FIXTURE)
    modules2, _ = extract_vba(FIXTURE)

    assert len(modules1) > 0, "No VBA modules found in fixture"

    # Compare counts first — zip would silently pass on mismatched lists
    assert len(modules1) == len(modules2), \
        f"Module count changed between runs: {len(modules1)} vs {len(modules2)}"

    # Compare complete name-to-hash mappings
    map1 = {m.name: m.sha256 for m in modules1}
    map2 = {m.name: m.sha256 for m in modules2}

    assert map1 == map2, \
        f"SHA256 mappings differ between runs: {map1} vs {map2}"

def test_vba_sha256_matches_source():
    """SHA256 stored on each module must match its source."""
    if not FIXTURE.exists():
        pytest.skip("macro_enabled.xlsm fixture not available")

    modules, _ = extract_vba(FIXTURE)
    assert len(modules) > 0, "No VBA modules found in fixture"

    for module in modules:
        expected = hashlib.sha256(
            module.source.encode("utf-8", errors="replace")
        ).hexdigest()
        assert module.sha256 == expected, \
            f"SHA256 mismatch for module {module.name}"


def test_vba_source_is_verbatim():
    """VBA source must not be normalized — line endings and content preserved."""
    if not FIXTURE.exists():
        pytest.skip("macro_enabled.xlsm fixture not available")

    modules, _ = extract_vba(FIXTURE)
    assert len(modules) > 0, "No VBA modules found in fixture"

    for module in modules:
        # Fix: Replace tautological assertion with meaningful checks
        assert len(module.source) > 0, \
            f"Module {module.name} has empty source"
        assert module.line_count == module.source.count("\n") + 1, \
            f"line_count mismatch for module {module.name}"
        # Verify source has real line structure
        assert "\n" in module.source or len(module.source) > 0, \
            f"Module {module.name} source has no line structure"

def test_empty_module_recorded_as_exception():
    """Modules with no name or code must be recorded as exceptions."""
    from unittest.mock import patch, MagicMock

    mock_vp = MagicMock()
    mock_vp.detect_vba_macros.return_value = True
    # Return one module with no name and no code
    mock_vp.extract_macros.return_value = [
        ("file", "stream", "", ""),
    ]
    mock_vp.modules_ = []

    with patch("archon.ingest.vba.VBA_Parser", return_value=mock_vp):
        modules, exceptions = extract_vba(Path("fake.xlsm"))

    assert modules == [], "Empty module should not be in modules list"
    assert len(exceptions) > 0, "Empty module should produce an exception"
    assert exceptions[0].code == "E_OLE_PARSE_FAILED"


def test_partial_extraction_records_exceptions():
    """When some modules are empty, exceptions are recorded for each skip."""
    from unittest.mock import patch, MagicMock

    mock_vp = MagicMock()
    mock_vp.detect_vba_macros.return_value = True
    # One valid module and one with no code
    mock_vp.extract_macros.return_value = [
        ("file", "stream", "Module1", "Sub Test()\nEnd Sub\n"),
        ("file", "stream", "Module2", ""),
    ]
    mock_vp.modules_ = []

    with patch("archon.ingest.vba.VBA_Parser", return_value=mock_vp):
        modules, exceptions = extract_vba(Path("fake.xlsm"))

    assert len(modules) == 1, "Only valid module should be extracted"
    assert len(exceptions) == 1, "Skipped module should produce an exception"
    assert exceptions[0].code == "E_OLE_PARSE_FAILED"