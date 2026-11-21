
import hashlib
import logging
import os
from pathlib import Path

from oletools.olevba import VBA_Parser, VBA_Project

from archon.contracts.extract import ExtractException, VbaModule

log = logging.getLogger(__name__)

# Excel uses this GUID for worksheet and ThisWorkbook document modules.
EXCEL_DOCUMENT_GUID = "00020820-0000-0000-C000-000000000046"


def _iter_ole_parsers(vp):
    """Yield the parser and any embedded OLE subfile parsers."""
    yield vp

    for subfile in getattr(vp, "ole_subfiles", []) or []:
        yield from _iter_ole_parsers(subfile)


def _read_project_stream(vp) -> dict[str, str]:
    """Read Class= and Document= records from VBA PROJECT streams."""
    project_map: dict[str, str] = {}

    for parser in _iter_ole_parsers(vp):
        ole_file = getattr(parser, "ole_file", None)
        if ole_file is None:
            continue

        try:
            projects = parser.find_vba_projects() or []
        except Exception:
            log.exception("Unable to locate VBA projects")
            continue

        for _vba_root, project_path, _dir_path in projects:
            try:
                raw = ole_file.openstream(project_path).read()
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    text = raw.decode("latin-1")

                for line in text.splitlines():
                    line = line.strip()
                    key, separator, value = line.partition("=")

                    if not separator:
                        continue

                    key = key.strip().lower()
                    value = value.strip()

                    if key == "class":
                        name = value.lower()
                        if name:
                            project_map[name] = "class"

                    elif key == "document":
                        # Document records may contain a name followed by
                        # a slash and additional document metadata.
                        name = value.split("/", 1)[0].strip().lower()
                        if name:
                            project_map[name] = "sheet"

            except Exception:
                log.exception(
                    "Unable to read VBA PROJECT stream: %s",
                    project_path,
                )

    return project_map


def _read_module_metadata(vp) -> dict[str, str]:
    """Read module types from oletools' parsed VBA_Project objects.

    VBA_Module.type 0x0021 identifies procedural modules.
    Type 0x0022 covers document, class, and designer modules, so the
    module source attributes are also inspected to distinguish them.
    """
    module_map: dict[str, str] = {}

    for parser in _iter_ole_parsers(vp):
        ole_file = getattr(parser, "ole_file", None)
        if ole_file is None:
            continue

        try:
            projects = parser.find_vba_projects() or []
        except Exception:
            log.exception("Unable to locate VBA projects for module metadata")
            continue

        for project_entry in projects:
            try:
                project = VBA_Project(ole_file, *project_entry)

                # parse_modules() is a generator. Iterating it populates
                # project.modules with VBA_Module objects.
                list(project.parse_modules())

                for module in project.modules:
                    name = getattr(module, "name", "")
                    if not name:
                        continue

                    module_type = getattr(module, "type", None)
                    source = getattr(module, "code_str", "") or ""

                    if module_type == 0x0021:
                        classification = "standard"
                    elif module_type == 0x0022:
                        classification = _classify_document_or_class(source)
                    else:
                        continue

                    module_map[name.lower()] = classification

            except Exception:
                log.exception("Unable to read VBA module metadata")

    return module_map


def _classify_document_or_class(code: str) -> str:
    """Distinguish Excel document modules from ordinary class modules."""
    source = code or ""

    base_match = None
    predeclared_match = None

    for line in source.splitlines():
        stripped = line.strip()
        lower = stripped.lower()

        if lower.startswith("attribute vb_base"):
            base_match = stripped

        elif lower.startswith("attribute vb_predeclaredid"):
            predeclared_match = stripped

    if base_match:
        normalized_base = (
            base_match.upper()
            .replace('"', "")
            .replace("{", "")
            .replace("}", "")
        )

        if (
            EXCEL_DOCUMENT_GUID in normalized_base
            and predeclared_match
            and predeclared_match.strip().lower().endswith("true")
        ):
            return "sheet"

    return "class"


def _classify(
    name: str,
    code: str,
    project_map: dict[str, str],
    module_map: dict[str, str] | None = None,
) -> str:
    """Classify a VBA module using project and parsed module metadata."""
    bare = os.path.splitext(name)[0].lower()

    if bare == "thisworkbook":
        return "thisworkbook"

    # Explicit PROJECT stream records take precedence.
    if bare in project_map:
        return project_map[bare]

    # Parsed VBA_Project module metadata is the next source.
    if module_map and bare in module_map:
        return module_map[bare]

    # Fallback for exported class-module source.
    if code.lstrip().startswith("VERSION 1.0 CLASS"):
        return "class"

    # Retain a conservative fallback for common worksheet names.
    if any(
        bare.startswith(prefix)
        for prefix in ("sheet", "blad", "feuil", "tabelle")
    ):
        return "sheet"

    return "standard"


def extract_vba(
    path: Path,
) -> tuple[list[VbaModule], list[ExtractException]]:
    """Extract VBA modules and report extraction failures."""
    path = Path(path)

    modules: list[VbaModule] = []
    exceptions: list[ExtractException] = []

    vp = None
    handler = None

    oletools_loggers = (
        logging.getLogger("olevba"),
        logging.getLogger("oletools.olevba"),
    )

    try:
        vp = VBA_Parser(str(path))

        if not vp.detect_vba_macros():
            return [], []

        project_map = _read_project_stream(vp)
        module_map = _read_module_metadata(vp)

        # Some oletools versions log and swallow extraction failures.
        swallowed_errors: list[str] = []

        class _ExceptionCapture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                message = record.getMessage()

                if (
                    record.levelno >= logging.ERROR
                    and (
                        "extract_vba" in message.lower()
                        or "_extract_vba" in message.lower()
                    )
                ):
                    swallowed_errors.append(message)

        handler = _ExceptionCapture()

        for oletools_logger in oletools_loggers:
            oletools_logger.addHandler(handler)

        try:
            for _filename, _stream, name, code in vp.extract_macros():
                if not name and not code:
                    exceptions.append(ExtractException(
                        code="E_OLE_PARSE_FAILED",
                        severity="warn",
                        sheet=None,
                        detail=(
                            "VBA module skipped: both name and code "
                            "are empty."
                        ),
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
                    type=_classify(
                        name,
                        code,
                        project_map,
                        module_map,
                    ),
                    source=code,
                    sha256=sha,
                    line_count=code.count("\n") + 1,
                ))

        finally:
            for oletools_logger in oletools_loggers:
                oletools_logger.removeHandler(handler)

            handler = None

        for error in swallowed_errors:
            exceptions.append(ExtractException(
                code="E_OLE_PARSE_FAILED",
                severity="warn",
                sheet=None,
                detail=(
                    "VBA module parse failure (logged by oletools): "
                    f"{error}"
                ),
            ))

        if not modules and not exceptions:
            exceptions.append(ExtractException(
                code="E_OLE_PARSE_FAILED",
                severity="warn",
                sheet=None,
                detail=(
                    "VBA project detected but no modules "
                    "could be extracted."
                ),
            ))

    except Exception as error:
        error_message = str(error).lower()

        if "locked" in error_message or "password" in error_message:
            exceptions.append(ExtractException(
                code="E_VBA_LOCKED",
                severity="warn",
                sheet=None,
                detail=f"VBA project is password-locked: {error}",
            ))
        else:
            raise

    finally:
        if handler is not None:
            for oletools_logger in oletools_loggers:
                oletools_logger.removeHandler(handler)

        if vp is not None:
            vp.close()

    return modules, exceptions
