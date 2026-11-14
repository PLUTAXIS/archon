# archon/ingest/exceptions.py
# This file is the "notebook" — it records everything that goes wrong.
# Rule: NEVER silently skip something. Always write it down.

from archon.contracts.extract import ExtractException


# These are the ONLY valid error codes.
# Do NOT invent new ones. If you need a new one, ask Wrik first.
VALID_CODES = {
    "E_PASSWORD_PROTECTED",
    "E_VBA_LOCKED",
    "E_VERY_HIDDEN_SHEET",
    "E_CORRUPT_ZIP",
    "E_PARTIAL_SHEET_RECOVERY",
    "E_EXTERNAL_LINK_UNRESOLVED",
    "E_UNSUPPORTED_FEATURE",
    "E_OLE_PARSE_FAILED",
}


def make_exception(
    code: str,
    detail: str,
    severity: str = "warn",   # "warn" = partial problem, "error" = serious problem
    sheet: str | None = None, # which sheet had the problem (if any)
) -> ExtractException:
    """
    Creates one exception record.
    
    Example usage:
        make_exception("E_VERY_HIDDEN_SHEET", "Sheet 'Secrets' is very hidden")
        make_exception("E_PASSWORD_PROTECTED", "File is locked", severity="error")
    """

    # Safety check — catch typos in code names immediately
    if code not in VALID_CODES:
        raise ValueError(
            f"Unknown exception code: '{code}'. "
            f"Valid codes are: {sorted(VALID_CODES)}"
        )

    return ExtractException(
        code=code,
        severity=severity,
        sheet=sheet,
        detail=detail,
    )