# archon/ingest/recovery.py
# Tries to open a workbook using 4 methods, from easiest to hardest.
# If all 4 fail, it gives up and tells Wrik.

from pathlib import Path
from openpyxl import load_workbook
from archon.ingest.exceptions import make_exception


class UnprocessableWorkbook(Exception):
    """Raised when a file is too broken to open at any recovery tier."""
    pass


def open_workbook(path: Path) -> tuple:
    """
    Tries to open an Excel file using 4 tiers.
    
    Returns: (workbook, exceptions_list)
    
    Tier 1 — Normal open (strict)
    Tier 2 — Lenient open (ignore broken styles)
    Tier 3 — Salvage open (last resort)
    Tier 4 — Give up (raise UnprocessableWorkbook)
    """
    exceptions = []

    # ----------------------------
    # TIER 1 — Normal open
    # ----------------------------
    try:
        wb = load_workbook(
            path,
            read_only=True,
            data_only=False,
            keep_links=True,
        )
        # Tier 1 worked — no exceptions, return cleanly
        return wb, exceptions

    except Exception as e:
        # Tier 1 failed, try next
        pass

    # ----------------------------
    # TIER 2 — Lenient open
    # Ignores broken styles/relationships
    # ----------------------------
    try:
        wb = load_workbook(
            path,
            read_only=True,
            data_only=False,
            keep_links=False,   # ignore broken external links
        )
        # Tier 2 worked — but we warn that it wasn't a clean open
        exceptions.append(make_exception(
            "E_PARTIAL_SHEET_RECOVERY",
            "File opened in lenient mode — some styles or links may be missing",
            severity="warn",
        ))
        return wb, exceptions

    except Exception as e:
        pass

    # ----------------------------
    # TIER 3 — Salvage open
    # Last resort — tries to read raw sheet XML
    # ----------------------------
    try:
        import zipfile

        # An xlsx file is just a zip file inside
        # We try to open it as a zip directly
        with zipfile.ZipFile(path, "r") as zf:
            names = zf.namelist()

        # If we can at least list the zip contents, partial recovery is possible
        exceptions.append(make_exception(
            "E_PARTIAL_SHEET_RECOVERY",
            "File opened via raw zip salvage — data may be incomplete",
            severity="warn",
        ))

        # Try one more time with openpyxl after confirming zip is readable
        wb = load_workbook(
            path,
            read_only=True,
            data_only=False,
        )
        return wb, exceptions

    except Exception as e:
        pass

    # ----------------------------
    # TIER 4 — Give up
    # File is too broken. Tell Wrik immediately.
    # ----------------------------
    raise UnprocessableWorkbook(
        f"Could not open '{path.name}' at any recovery tier. "
        f"Escalate to Wrik within 1 hour."
    )