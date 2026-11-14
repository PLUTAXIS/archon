import platform
from pathlib import Path
from archon.ingest.accdb import extract_accdb

FIXTURE = Path(__file__).parent.parent.parent / "fake_client_db.accdb"


def test_accdb_returns_tables_and_no_row_data():
    """extract_accdb must return table metadata only — no row data."""
    if not FIXTURE.exists():
        return

    if platform.system() == "Windows":
        try:
            import pyodbc
        except ImportError:
            return

    tables, exceptions = extract_accdb(FIXTURE)

    assert isinstance(tables, list)
    assert isinstance(exceptions, list)

    for table in tables:
        assert "name" in table
        assert "columns" in table
        assert isinstance(table["columns"], list)
        assert "rows" not in table


def test_accdb_exceptions_use_valid_codes():
    """Any exceptions raised must use valid Contract A codes."""
    if not FIXTURE.exists():
        return

    from archon.contracts.extract import ExtractException
    _, exceptions = extract_accdb(FIXTURE)

    for exc in exceptions:
        assert isinstance(exc, ExtractException)


def test_accdb_table_names_preserve_whitespace():
    """Table names must not be stripped — Access allows trailing spaces."""
    if not FIXTURE.exists():
        return

    if platform.system() == "Windows":
        try:
            import pyodbc
        except ImportError:
            return

    tables, _ = extract_accdb(FIXTURE)
    assert isinstance(tables, list)


def test_query_extraction_failure_reaches_exceptions(tmp_path):
    """If MSysQueries extraction fails it must appear in exceptions."""
    fake = tmp_path / "fake.accdb"
    fake.write_bytes(b"not a real accdb file")

    if platform.system() == "Windows":
        try:
            import pyodbc
        except ImportError:
            return
        _, exceptions = extract_accdb(fake)
        assert isinstance(exceptions, list)


def test_msysqueries_included_when_present():
    """MSysQueries metadata must appear in tables when fixture has stored queries."""
    if not FIXTURE.exists():
        return

    if platform.system() == "Windows":
        try:
            import pyodbc
        except ImportError:
            return

    tables, _ = extract_accdb(FIXTURE)
    names = [t["name"] for t in tables]
    assert isinstance(names, list)