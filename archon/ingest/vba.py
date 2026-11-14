import hashlib
import os
from pathlib import Path

from oletools.olevba import VBA_Parser

from archon.contracts.extract import VbaModule, ExtractException


def _classify(name: str, code: str) -> str:
    """Classify a VBA module type from its name and source.
    
    Strips file extension before comparing module identifiers so that
    ThisWorkbook.cls correctly classifies as thisworkbook.
    """
    # Fix 1: Strip extension before comparison
    name_lower = os.path.splitext(name)[0].lower()
    if name_lower == "thisworkbook":
        return "thisworkbook"
    if code.startswith("VERSION 1.0 CLASS"):
        return "class"
    if any(name_lower.startswith(p) for p in ("sheet", "blad", "feuil", "tabelle")):
        return "sheet"
    return "standard"


def extract_vba(path: Path) -> tuple[list[VbaModule], list[ExtractException]]:
    """Extract VBA modules from an xlsm/xlsb file at path.

    Returns a tuple of (modules, exceptions).
    Raises if the VBA project is unreadable and not password-locked.
    Never returns an empty list silently — either modules are found,
    an exception is recorded, or an error is raised.
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
                if not name or not code:
                    continue
                sha = hashlib.sha256(
                    code.encode("utf-8", errors="replace")
                ).hexdigest()
                modules.append(VbaModule(
                    name=name,
                    type=_classify(name, code),
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

    # Fix 2: If VBA was detected but no modules extracted, record an exception
    if vp is not None:
        try:
            has_macros = vp.detect_vba_macros()
        except Exception:
            has_macros = False
        if has_macros and not modules and not exceptions:
            exceptions.append(ExtractException(
                code="E_OLE_PARSE_FAILED",
                severity="warn",
                sheet=None,
                detail="VBA project detected but no modules could be extracted.",
            ))

    return modules, exceptions