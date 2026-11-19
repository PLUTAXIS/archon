import hashlib
import os
from pathlib import Path

from oletools.olevba import VBA_Parser

from archon.contracts.extract import VbaModule, ExtractException


# oletools module type constants
MODULETYPE_CLASS = "Class"
MODULETYPE_DOCUMENT = "Document"


def _classify_by_metadata(vp, name: str, code: str) -> str:
    """Classify a VBA module using oletools project metadata.

    Uses vp.modules_ metadata when available to correctly identify
    class and document modules regardless of filename prefix.
    Falls back to code-header and name-based heuristics.
    """
    name_lower = os.path.splitext(name)[0].lower()

    # Check thisworkbook first — always a document module
    if name_lower == "thisworkbook":
        return "thisworkbook"

    # Use oletools module metadata if available
    try:
        if hasattr(vp, "modules_") and vp.modules_:
            for mod in vp.modules_:
                mod_name = getattr(mod, "name", "") or ""
                if os.path.splitext(mod_name)[0].lower() == name_lower:
                    mod_type = getattr(mod, "type", "") or ""
                    if mod_type == MODULETYPE_DOCUMENT:
                        return "sheet"
                    if mod_type == MODULETYPE_CLASS:
                        return "class"
    except Exception:
        pass

    # Fall back to code header — attribute-led class modules start with this
    if code.lstrip().startswith("VERSION 1.0 CLASS"):
        return "class"

    # Fall back to name prefix for sheet modules
    if any(name_lower.startswith(p) for p in
           ("sheet", "blad", "feuil", "tabelle")):
        return "sheet"

    return "standard"


def extract_vba(path: Path) -> tuple[list[VbaModule], list[ExtractException]]:
    """Extract VBA modules from an xlsm/xlsb file at path.

    Returns a tuple of (modules, exceptions).
    Raises if the VBA project is unreadable and not password-locked.
    Records an exception for every skipped or failed module so partial
    extraction is never reported as successful.
    """
    path = Path(path)
    modules: list[VbaModule] = []
    exceptions: list[ExtractException] = []

    vp = None
    try:
        vp = VBA_Parser(str(path))

        if not vp.detect_vba_macros():
            # No VBA in this file — empty list is valid here
            return [], []

        try:
            for _filename, _stream, name, code in vp.extract_macros():
                # Record skipped modules instead of silently dropping them
                if not name and not code:
                    exceptions.append(ExtractException(
                        code="E_OLE_PARSE_FAILED",
                        severity="warn",
                        sheet=None,
                        detail="VBA module skipped: both name and code are empty.",
                    ))
                    continue
                if not name:
                    exceptions.append(ExtractException(
                        code="E_OLE_PARSE_FAILED",
                        severity="warn",
                        sheet=None,
                        detail="VBA module skipped: module has no name.",
                    ))
                    continue
                if not code:
                    exceptions.append(ExtractException(
                        code="E_OLE_PARSE_FAILED",
                        severity="warn",
                        sheet=None,
                        detail=f"VBA module '{name}' skipped: empty code.",
                    ))
                    continue

                sha = hashlib.sha256(
                    code.encode("utf-8", errors="replace")
                ).hexdigest()
                modules.append(VbaModule(
                    name=name,
                    type=_classify_by_metadata(vp, name, code),
                    source=code,
                    sha256=sha,
                    line_count=code.count("\n") + 1,
                ))

        except Exception as e:
            err_msg = str(e).lower()
            if "locked" in err_msg or "password" in err_msg:
                exceptions.append(ExtractException(
                    code="E_VBA_LOCKED",
                    severity="warn",
                    sheet=None,
                    detail=f"VBA project is password-locked: {e}",
                ))
            else:
                raise

    except Exception as e:
        err_msg = str(e).lower()
        if "locked" in err_msg or "password" in err_msg:
            exceptions.append(ExtractException(
                code="E_VBA_LOCKED",
                severity="warn",
                sheet=None,
                detail=f"VBA project is password-locked: {e}",
            ))
        else:
            raise
    finally:
        if vp is not None:
            vp.close()

    # If VBA was detected but no modules extracted, record an exception
    if not modules and not exceptions:
        exceptions.append(ExtractException(
            code="E_OLE_PARSE_FAILED",
            severity="warn",
            sheet=None,
            detail="VBA project detected but no modules could be extracted.",
        ))

    return modules, exceptions