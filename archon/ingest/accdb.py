

import platform
import re
import subprocess
from pathlib import Path

from archon.contracts.extract import ExtractException


MDBTOOLS_TIMEOUT = 30


def _run(cmd, timeout=MDBTOOLS_TIMEOUT):
    """Run an mdbtools command and return its standard output."""
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip()
            or f"Command failed with exit code {result.returncode}: {cmd}"
        )

    return result.stdout


def _get_tables(path):
    """Return Access table names without stripping meaningful whitespace."""
    output = _run(["mdb-tables", "-1", str(path)])
    return [
        line.rstrip("\r\n")
        for line in output.splitlines()
        if line.rstrip("\r\n")
    ]


def _get_columns(path, table):
    """Extract column names for one table using targeted mdb-schema output."""
    output = _run(
        [
            "mdb-schema",
            "-T",
            table,
            str(path),
            "access",
        ]
    )

    columns = []
    in_table = False

    table_pattern = (
        rf'^CREATE\s+TABLE\s+(?:\[{re.escape(table)}\]|'
        rf'"{re.escape(table)}"|{re.escape(table)})'
        rf'(?:\s*\(|\s*$)'
    )

    for line in output.splitlines():
        line_stripped = line.strip()

        if not in_table:
            if re.match(
                table_pattern,
                line_stripped,
                re.IGNORECASE,
            ):
                in_table = True
            continue

        if line_stripped.startswith(")"):
            break

        if not line_stripped or line_stripped.startswith("("):
            continue

        match = re.match(
            r'^\s*(?:\[([^\]]+)\]|"([^"]+)"|`([^`]+)`)',
            line,
        )

        if match:
            column_name = next(
                group for group in match.groups() if group is not None
            )
            columns.append(column_name)

    return columns


def _get_queries(path):
    """Return metadata for Access queries represented in MSysQueries."""
    output = _run(["mdb-tables", "-1", "-S", str(path)])

    system_tables = [
        line.rstrip("\r\n")
        for line in output.splitlines()
        if line.rstrip("\r\n")
    ]

    if "MSysQueries" not in system_tables:
        return []

    columns = _get_columns(path, "MSysQueries")

    return [
        {
            "name": "MSysQueries",
            "columns": columns,
        }
    ]


def _extract_windows(path):
    """Extract table and column metadata using the Microsoft Access ODBC driver."""
    try:
        import pyodbc
    except ImportError as exc:
        raise RuntimeError(
            "pyodbc is required for Access extraction on Windows"
        ) from exc

    connection_string = (
        "DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
        f"DBQ={Path(path).resolve()};"
    )

    tables = []

    connection = pyodbc.connect(connection_string)
    try:
        cursor = connection.cursor()

        for table_info in cursor.tables(tableType="TABLE"):
            table_name = table_info.table_name

            # Fix: escape _ as [_] to prevent wildcard matching in pyodbc
            # cursor.columns(table=...) treats _ as single-char wildcard
            # so Order_Items would also return columns from OrderXItems
            escaped = table_name.replace("_", "[_]")
            column_names = [
                column.column_name
                for column in cursor.columns(table=escaped)
                if column.table_name == table_name
            ]

            tables.append(
                {
                    "name": table_name,
                    "columns": column_names,
                }
            )
    finally:
        connection.close()

    return tables


def extract_accdb(path):
    """Extract table and column metadata from an Access database.

    Returns:
        A tuple containing:
        - A list of table metadata dictionaries.
        - A list of ExtractException objects.

    Row data is never extracted.
    """
    path = Path(path)
    tables = []
    exceptions = []

    if platform.system() == "Windows":
        try:
            tables = _extract_windows(path)
        except Exception as exc:
            exceptions.append(
                ExtractException(
                    code="E_OLE_PARSE_FAILED",
                    severity="error",
                    detail=f"Access database extraction failed: {exc}",
                )
            )

        return tables, exceptions

    # Linux/macOS extraction using mdbtools
    try:
        table_names = _get_tables(path)

        for table_name in table_names:
            try:
                columns = _get_columns(path, table_name)
                tables.append(
                    {
                        "name": table_name,
                        "columns": columns,
                    }
                )
            except Exception as exc:
                exceptions.append(
                    ExtractException(
                        code="E_OLE_PARSE_FAILED",
                        severity="warn",
                        detail=(
                            f"Table extraction failed for "
                            f"{table_name}: {exc}"
                        ),
                    )
                )

    except Exception as exc:
        exceptions.append(
            ExtractException(
                code="E_OLE_PARSE_FAILED",
                severity="error",
                detail=f"Access table listing failed: {exc}",
            )
        )

    # Extract system query metadata separately
    try:
        query_tables = _get_queries(path)
        tables.extend(query_tables)
    except Exception as exc:
        exceptions.append(
            ExtractException(
                code="E_OLE_PARSE_FAILED",
                severity="warn",
                detail=f"MSysQueries extraction failed: {exc}",
            )
        )

    return tables, exceptions
