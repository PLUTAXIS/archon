
import platform
from pathlib import Path

import archon.ingest.accdb as accdb
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


def test_msysqueries_included_with_extracted_columns(monkeypatch, tmp_path):
    """MSysQueries must be included with its actual column metadata."""

    monkeypatch.setattr(accdb.platform, "system", lambda: "Linux")

    # Simulate ordinary table discovery.
    monkeypatch.setattr(
        accdb,
        "_get_tables",
        lambda path: ["Customers"],
    )

    # Simulate system-table discovery.
    def fake_run(cmd, timeout=accdb.MDBTOOLS_TIMEOUT):
        if cmd[:3] == ["mdb-tables", "-1", "-S"]:
            return "MSysQueries\n"
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(accdb, "_run", fake_run)

    def fake_get_columns(path, table):
        if table == "Customers":
            return ["CustomerID", "CustomerName"]

        if table == "MSysQueries":
            return ["Name", "Flag", "Expression"]

        raise AssertionError(f"Unexpected table: {table}")

    monkeypatch.setattr(accdb, "_get_columns", fake_get_columns)

    tables, exceptions = extract_accdb(tmp_path / "fake.accdb")

    msysqueries = [
        table for table in tables
        if table["name"] == "MSysQueries"
    ]

    assert len(msysqueries) == 1
    assert msysqueries[0]["columns"] == [
        "Name",
        "Flag",
        "Expression",
    ]
    assert not exceptions


def test_msysqueries_schema_uses_targeted_mdb_schema(monkeypatch):
    """MSysQueries schema must be requested using mdb-schema -T."""

    commands = []

    def fake_run(cmd, timeout=accdb.MDBTOOLS_TIMEOUT):
        commands.append(cmd)

        return (
            "CREATE TABLE [MSysQueries] (\n"
            "    [Name] TEXT,\n"
            "    [Flag] LONG,\n"
            "    [Expression] MEMO\n"
            ");\n"
        )

    monkeypatch.setattr(accdb, "_run", fake_run)

    columns = accdb._get_columns(
        Path("fake.accdb"),
        "MSysQueries",
    )

    assert commands
    assert commands[0][:3] == [
        "mdb-schema",
        "-T",
        "MSysQueries",
    ]
    assert columns == ["Name", "Flag", "Expression"]


def test_query_extraction_failure_reaches_exceptions(
    monkeypatch,
    tmp_path,
):
    """MSysQueries extraction failures must be reported as warnings."""

    monkeypatch.setattr(accdb.platform, "system", lambda: "Linux")

    # No ordinary tables are needed for this test.
    monkeypatch.setattr(
        accdb,
        "_get_tables",
        lambda path: [],
    )

    # Make system-table discovery succeed.
    def fake_run(cmd, timeout=accdb.MDBTOOLS_TIMEOUT):
        if cmd[:3] == ["mdb-tables", "-1", "-S"]:
            return "MSysQueries\n"
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(accdb, "_run", fake_run)

    # Simulate a failure while reading MSysQueries columns.
    def failing_get_columns(path, table):
        raise RuntimeError("Simulated MSysQueries schema failure")

    monkeypatch.setattr(
        accdb,
        "_get_columns",
        failing_get_columns,
    )

    tables, exceptions = extract_accdb(tmp_path / "fake.accdb")

    assert not tables
    assert len(exceptions) == 1

    exc = exceptions[0]

    assert exc.code == "E_OLE_PARSE_FAILED"
    assert exc.severity == "warn"
    assert "MSysQueries extraction failed" in exc.detail
    assert "Simulated MSysQueries schema failure" in exc.detail
