
import hashlib
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import openpyxl

from archon.ingest.vba import extract_vba, _classify


FIXTURE = Path(__file__).parent / "fixtures" / "vba_classification_test.xlsm"


def test_no_vba_returns_empty(tmp_path):
    """A plain xlsx with no macros returns empty lists."""
    fixture = tmp_path / "plain.xlsx"
    workbook = openpyxl.Workbook()
    workbook.save(fixture)

    modules, exceptions = extract_vba(fixture)

    assert modules == []
    assert exceptions == []


def test_vba_sha256_is_stable():
    """SHA256 of VBA source must be stable across two extractions."""
    assert FIXTURE.exists(), f"Missing real VBA fixture: {FIXTURE}"

    modules1, _ = extract_vba(FIXTURE)
    modules2, _ = extract_vba(FIXTURE)

    assert modules1, "No VBA modules found in fixture"
    assert len(modules1) == len(modules2)

    map1 = {module.name: module.sha256 for module in modules1}
    map2 = {module.name: module.sha256 for module in modules2}

    assert map1 == map2


def test_vba_sha256_matches_source():
    """SHA256 stored on each module must match its source."""
    assert FIXTURE.exists(), f"Missing real VBA fixture: {FIXTURE}"

    modules, _ = extract_vba(FIXTURE)
    assert modules, "No VBA modules found in fixture"

    for module in modules:
        expected = hashlib.sha256(
            module.source.encode("utf-8", errors="replace")
        ).hexdigest()

        assert module.sha256 == expected


def test_vba_source_is_verbatim():
    """Extracted source is retained and line counts match that source."""
    assert FIXTURE.exists(), f"Missing real VBA fixture: {FIXTURE}"

    modules, _ = extract_vba(FIXTURE)
    assert modules, "No VBA modules found in fixture"

    for module in modules:
        assert module.source
        assert module.line_count == module.source.count("\n") + 1


def test_real_fixture_module_classification():
    """Real oletools metadata classifies document, class, and standard modules."""
    assert FIXTURE.exists(), f"Missing real VBA fixture: {FIXTURE}"

    modules, exceptions = extract_vba(FIXTURE)

    assert not exceptions, [
        exception.detail for exception in exceptions
    ]

    # oletools may return names with .cls or .bas extensions.
    actual_types = {
        Path(module.name).stem.lower(): module.type
        for module in modules
    }

    assert actual_types["thisworkbook"] == "thisworkbook"
    assert actual_types["salesdatasheet"] == "sheet"
    assert actual_types["customer"] == "class"
    assert actual_types["module1"] == "standard"


def test_empty_module_recorded_as_exception():
    """A module with no name or code is recorded as an exception."""
    mock_vp = MagicMock()
    mock_vp.detect_vba_macros.return_value = True
    mock_vp.extract_macros.return_value = [
        ("file", "stream", "", ""),
    ]
    mock_vp.ole_file = None
    mock_vp.ole_subfiles = []
    mock_vp.find_vba_projects.return_value = []

    with patch("archon.ingest.vba.VBA_Parser", return_value=mock_vp):
        modules, exceptions = extract_vba(Path("fake.xlsm"))

    assert modules == []
    assert len(exceptions) == 1
    assert exceptions[0].code == "E_OLE_PARSE_FAILED"


def test_partial_extraction_records_exceptions():
    """A valid module is retained when another module has empty code."""
    mock_vp = MagicMock()
    mock_vp.detect_vba_macros.return_value = True
    mock_vp.extract_macros.return_value = [
        ("file", "stream", "Module1", "Sub Test()\nEnd Sub\n"),
        ("file", "stream", "Module2", ""),
    ]
    mock_vp.ole_file = None
    mock_vp.ole_subfiles = []
    mock_vp.find_vba_projects.return_value = []

    with patch("archon.ingest.vba.VBA_Parser", return_value=mock_vp):
        modules, exceptions = extract_vba(Path("fake.xlsm"))

    assert len(modules) == 1
    assert modules[0].name == "Module1"
    assert len(exceptions) == 1
    assert exceptions[0].code == "E_OLE_PARSE_FAILED"


def test_swallowed_parse_failure_recorded_olevba_logger():
    """A swallowed extraction failure logged by olevba is reported."""
    mock_vp = MagicMock()
    mock_vp.detect_vba_macros.return_value = True
    mock_vp.ole_file = None
    mock_vp.ole_subfiles = []
    mock_vp.find_vba_projects.return_value = []

    def extract_with_log():
        yield (
            "file",
            "stream",
            "Module1",
            "Sub Test()\nEnd Sub\n",
        )
        logging.getLogger("olevba").error(
            "Error in _extract_vba: simulated corrupt VBA stream"
        )

    mock_vp.extract_macros.return_value = extract_with_log()

    with patch("archon.ingest.vba.VBA_Parser", return_value=mock_vp):
        modules, exceptions = extract_vba(Path("fake.xlsm"))

    assert len(modules) == 1
    assert modules[0].name == "Module1"
    assert any(
        exception.code == "E_OLE_PARSE_FAILED"
        and "parse failure" in exception.detail.lower()
        for exception in exceptions
    )


def test_swallowed_parse_failure_recorded_oletools_logger():
    """A swallowed extraction failure logged by oletools.olevba is reported."""
    mock_vp = MagicMock()
    mock_vp.detect_vba_macros.return_value = True
    mock_vp.ole_file = None
    mock_vp.ole_subfiles = []
    mock_vp.find_vba_projects.return_value = []

    def extract_with_log():
        yield (
            "file",
            "stream",
            "Module1",
            "Sub Test()\nEnd Sub\n",
        )
        logging.getLogger("oletools.olevba").error(
            "Error in extract_vba: simulated corrupt VBA stream",
            exc_info=False,
        )

    mock_vp.extract_macros.return_value = extract_with_log()

    with patch("archon.ingest.vba.VBA_Parser", return_value=mock_vp):
        modules, exceptions = extract_vba(Path("fake.xlsm"))

    assert len(modules) == 1
    assert modules[0].name == "Module1"
    assert any(
        exception.code == "E_OLE_PARSE_FAILED"
        and "parse failure" in exception.detail.lower()
        for exception in exceptions
    )


def test_classify_uses_project_stream_for_class():
    """Class= record in PROJECT stream classifies a module as class."""
    result = _classify(
        "Customer.cls",
        'Attribute VB_Name = "Customer"\n',
        {"customer": "class"},
    )

    assert result == "class"


def test_classify_uses_project_stream_for_sheet():
    """Document= record in PROJECT stream classifies a module as sheet."""
    result = _classify(
        "SalesDataSheet.cls",
        "",
        {"salesdatasheet": "sheet"},
    )

    assert result == "sheet"


def test_classify_thisworkbook():
    """ThisWorkbook is always classified as thisworkbook."""
    result = _classify("ThisWorkbook.cls", "", {})

    assert result == "thisworkbook"


def test_classify_standard_fallback():
    """An unrecognized procedural module defaults to standard."""
    result = _classify(
        "Module1.bas",
        "Sub Test()\nEnd Sub\n",
        {},
    )

    assert result == "standard"


def test_classify_class_by_code_header():
    """A VERSION 1.0 CLASS header identifies an exported class module."""
    result = _classify(
        "Unknown.cls",
        "VERSION 1.0 CLASS\nBEGIN\nEND\n",
        {},
    )

    assert result == "class"
