import subprocess
import platform
from pathlib import Path

from archon.contracts.extract import ExtractException


MDBTOOLS_TIMEOUT = 30


def _run(cmd: list[str], timeout: int = MDBTOOLS_TIMEOUT) -> str:
    """Run a subprocess command and return stdout. Raises on failure."""
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"Command failed: {cmd}")
    return result.stdout


def _get_tables(path: Path) -> list[str]:
    """Return table names from accdb. Preserves whitespace in names."""
    output = _run(["mdb-tables", "-1", str(path)])
    # Do NOT strip() — Access allows trailing spaces in table names
    return [t for t in output.splitlines() if t != ""]


def _get_columns(path: Path, table: str) -> list[str]:
    """Return column names for a table using mdb-schema. Never SELECT *."""
    output = _run(["mdb-schema", str(path), "access"])
    columns = []
    in_table = False
    for line in output.splitlines():
        line_stripped = line.strip()
        if f'"{table}"' in line_stripped or f"[{table}]" in line_stripped:
            in_table = True
            continue
        if in_table:
            if line_stripped.startswith(")") or line_stripped.startswith("];"):
                break
            if line_stripped and not line_stripped.startswith("("):
                col = line_stripped.split()[0].strip('",[]')
                if col:
                    columns.append(col)
    return columns


def _get_queries(path: Path) -> list[dict]:
    """Get stored query names from MSysQueries using schema only — no row data."""
    try:
        output = _run(["mdb-tables", "-1", str(path)])
        tables = [t for t in output.splitlines() if t != ""]
        if "MSysQueries" not in tables:
            return []
        cols = _get_columns(path, "MSysQueries")
        return [{"columns": cols}]
    except Exception:
        return []


def extract_accdb(path: Path) -> tuple[list[dict], list[ExtractException]]:
    """Extract table and column metadata from an accdb file.

    Returns (tables, exceptions). Schema only — no row data ever.
    Uses mdbtools on Linux, pyodbc as Windows dev fallback only.
    """
    path = Path(path)
    tables = []
    exceptions: list[ExtractException] = []

    if platform.system() == "Windows":
        try:
            import pyodbc
            conn_str = (
                r"Driver={Microsoft Access Driver (*.mdb, *.accdb)};"
                f"DBQ={path};"
            )
            conn = pyodbc.connect(conn_str)
            try:
                cursor = conn.cursor()
                for row in cursor.tables(tableType="TABLE"):
                    table_name = row.table_name
                    cols = [
                        col.column_name
                        for col in cursor.columns(table=table_name)
                    ]
                    tables.append({"name": table_name, "columns": cols})
            finally:
                conn.close()
        except Exception as e:
            exceptions.append(ExtractException(
                code="E_OLE_PARSE_FAILED",
                severity="error",
                sheet=None,
                detail=f"Windows accdb extraction failed: {e}",
            ))
        return tables, exceptions

    # Linux path — mdbtools
    try:
        table_names = _get_tables(path)
        for table_name in table_names:
            try:
                cols = _get_columns(path, table_name)
                tables.append({"name": table_name, "columns": cols})
            except Exception as e:
                exceptions.append(ExtractException(
                    code="E_OLE_PARSE_FAILED",
                    severity="warn",
                    sheet=None,
                    detail=f"Failed to read columns for table {table_name}: {e}",
                ))

    except FileNotFoundError:
        raise RuntimeError(
            "mdbtools not found. Install with: apt-get install mdbtools"
        )
    except Exception as e:
        exceptions.append(ExtractException(
            code="E_OLE_PARSE_FAILED",
            severity="error",
            sheet=None,
            detail=f"accdb extraction failed: {e}",
        ))

    return tables, exceptions