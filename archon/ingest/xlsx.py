from archon.ingest.vba import extract_vba
import hashlib
import uuid
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET
import openpyxl

from archon.contracts.extract import (
    Cell,
    RawExtract,
    Sheet,
    Source,
)


def _sha256(path: Path) -> str:
    """Return the hex SHA-256 digest of the file at path."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _to_cached(value) -> float | str | bool | None:
    """Convert a cell value to a type accepted by Cell.cached_value."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "total_seconds"):
        return value.total_seconds() / 86400
    return str(value)


def _sheet_visibility(path: Path) -> dict[str, str]:
    """Read sheet visibility states directly from xl/workbook.xml in the zip.

    Returns a dict of {sheet_name: visibility_state} where state is one of
    visible, hidden, veryHidden.
    """
    states: dict[str, str] = {}
    try:
        with zipfile.ZipFile(path, "r") as z:
            with z.open("xl/workbook.xml") as f:
                tree = ET.parse(f)
                ns = {"ms": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                for sheet in tree.findall(".//ms:sheet", ns):
                    name = sheet.get("name", "")
                    state = sheet.get("state", "visible")
                    states[name] = state
    except Exception:
        pass
    return states


def _sheet_rel_map(path: Path) -> dict[str, str]:
    """Build a mapping from sheet name to worksheet XML path using relationships.

    Reads xl/workbook.xml to get sheet rId, then xl/_rels/workbook.xml.rels
    to resolve each rId to its worksheet part path.
    Avoids filename sorting which breaks with 10+ sheets.
    Returns {sheet_name: part_path} e.g. {"Sheet1": "xl/worksheets/sheet1.xml"}
    """
    name_to_part: dict[str, str] = {}
    ns = {"ms": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    office_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

    try:
        with zipfile.ZipFile(path, "r") as z:
            # Step 1: Read workbook.xml to get sheet name -> rId mapping
            with z.open("xl/workbook.xml") as f:
                tree = ET.parse(f)
                sheets = tree.findall(".//ms:sheet", ns)
                rid_to_name: dict[str, str] = {}
                for sheet in sheets:
                    rid = sheet.get(f"{{{office_ns}}}id", "")
                    name = sheet.get("name", "")
                    if rid and name:
                        rid_to_name[rid] = name

            # Step 2: Read workbook.xml.rels to get rId -> worksheet path
            with z.open("xl/_rels/workbook.xml.rels") as f:
                tree = ET.parse(f)
                for rel in tree.findall(f"{{{rel_ns}}}Relationship"):
                    rid = rel.get("Id", "")
                    target = rel.get("Target", "")
                    rel_type = rel.get("Type", "")
                    if "worksheet" in rel_type and rid in rid_to_name:
                        # Target is relative to xl/ folder
                        if target.startswith("/"):
                            part = target.lstrip("/")
                        elif target.startswith("xl/"):
                            part = target
                        else:
                            part = f"xl/{target}"
                        name_to_part[rid_to_name[rid]] = part

    except Exception:
        pass

    return name_to_part


def _sheet_metadata(path: Path) -> dict[str, dict]:
    """Read merged cells and frozen panes for each sheet from the zip.

    Uses relationship mapping to correctly pair sheet names with their
    worksheet XML parts. Never relies on filename sorting.
    """
    metadata: dict[str, dict] = {}
    ns = {"ms": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

    try:
        rel_map = _sheet_rel_map(path)
        with zipfile.ZipFile(path, "r") as z:
            for sheet_name, part_path in rel_map.items():
                merged = []
                frozen = None
                try:
                    with z.open(part_path) as f:
                        tree = ET.parse(f)
                        for mc in tree.findall(".//ms:mergeCell", ns):
                            ref = mc.get("ref")
                            if ref:
                                merged.append(ref)
                        pane = tree.find(".//ms:pane", ns)
                        if pane is not None:
                            state = pane.get("state", "")
                            if state == "frozen":
                                frozen = pane.get("topLeftCell")
                except Exception:
                    pass
                metadata[sheet_name] = {
                    "merged_cells": merged,
                    "frozen_panes": frozen,
                }
    except Exception:
        pass

    return metadata


def _defined_names(path: Path) -> list:
    """Read defined names (named ranges) from xl/workbook.xml in the zip."""
    from archon.contracts.extract import DefinedName
    names = []
    ns = {"ms": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    try:
        with zipfile.ZipFile(path, "r") as z:
            with z.open("xl/workbook.xml") as f:
                tree = ET.parse(f)
                for dn in tree.findall(".//ms:definedName", ns):
                    name = dn.get("name", "")
                    scope = dn.get("localSheetId", "workbook")
                    refers_to = dn.text or ""
                    if name:
                        names.append(DefinedName(
                            name=name,
                            scope=str(scope),
                            refers_to=refers_to,
                        ))
    except Exception:
        pass
    return names


def _tables(path: Path) -> list:
    """Read table definitions from xl/tables/ in the zip.

    Uses relationship mapping to correctly pair tables with their sheet names.
    Never relies on filename sorting.
    """
    from archon.contracts.extract import Table
    tables = []

    try:
        with zipfile.ZipFile(path, "r") as z:
            # Use relationship mapping — never rely on filename sorting
            rel_map = _sheet_rel_map(path)
            # Invert to {part_path: sheet_name}
            part_to_sheet = {v: k for k, v in rel_map.items()}

            # Find table files
            table_files = [
                n for n in z.namelist()
                if n.startswith("xl/tables/") and n.endswith(".xml")
            ]

            for table_file in sorted(table_files):
                try:
                    with z.open(table_file) as f:
                        tree = ET.parse(f)
                        root = tree.getroot()
                        name = root.get("name", "")
                        ref = root.get("ref", "")

                        # Find which sheet this table belongs to
                        sheet_name = ""
                        for part_path, sn in part_to_sheet.items():
                            rel_file = (
                                part_path.replace(
                                    "xl/worksheets/",
                                    "xl/worksheets/_rels/"
                                ) + ".rels"
                            )
                            try:
                                with z.open(rel_file) as rf:
                                    rel_tree = ET.parse(rf)
                                    rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
                                    for rel in rel_tree.findall(
                                        f"{{{rel_ns}}}Relationship"
                                    ):
                                        target = rel.get("Target", "")
                                        if table_file.split("/")[-1] in target:
                                            sheet_name = sn
                            except Exception:
                                pass

                        if name and ref:
                            tables.append(Table(
                                name=name,
                                sheet=sheet_name,
                                ref=ref,
                                is_hidden=False,
                            ))
                except Exception:
                    pass
    except Exception:
        pass

    return tables


def extract(path: Path) -> RawExtract:
    """Extract a RawExtract from an xlsx/xlsm file at path."""
    path = Path(path)
    suffix = path.suffix.lower().lstrip(".")

    source = Source(
        filename=path.name,
        sha256=_sha256(path),
        format=suffix,
        bytes=path.stat().st_size,
    )

    # First pass — formulas (data_only=False)
    wb_formulas = openpyxl.load_workbook(
        path, read_only=True, data_only=False
    )

    # Second pass — cached values (data_only=True)
    wb_cached = openpyxl.load_workbook(
        path, read_only=True, data_only=True
    )

    sheets = []
    cells = []

    try:
        visibility_map = _sheet_visibility(path)
        sheet_meta = _sheet_metadata(path)

        for idx, ws in enumerate(wb_formulas.worksheets):
            sheet_state = visibility_map.get(ws.title, "visible")
            meta = sheet_meta.get(ws.title, {})
            sheets.append(Sheet(
                name=ws.title,
                index=idx,
                visibility=sheet_state,
                dimensions=ws.calculate_dimension() if getattr(ws, "dimensions", None) else "A1:A1",
                merged_cells=meta.get("merged_cells", []),
                frozen_panes=meta.get("frozen_panes", None),
            ))

        # Build a lookup of cached values from second pass
        cached_lookup: dict[tuple[str, str], object] = {}
        for ws_c in wb_cached.worksheets:
            for row in ws_c.iter_rows():
                for cell in row:
                    if cell.value is not None:
                        cached_lookup[(ws_c.title, cell.coordinate)] = cell.value

        # Now build cells using formula pass + cached lookup
        for ws in wb_formulas.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    if cell.value is None:
                        continue

                    formula = None
                    cached_value = None
                    is_array = False

                    if cell.data_type == "f":
                        if hasattr(cell.value, "text"):
                            # Array formula
                            array_text = str(cell.value.text)
                            formula = array_text if array_text.startswith("=") else "=" + array_text
                            is_array = True
                        elif isinstance(cell.value, str) and cell.value.startswith("="):
                            formula = cell.value
                        else:
                            formula = str(cell.value)
                        # Get cached value from second pass
                        raw = cached_lookup.get((ws.title, cell.coordinate))
                        cached_value = _to_cached(raw)
                    else:
                        cached_value = _to_cached(cell.value)

                    # Determine data type
                    if cell.data_type == "e":
                        data_type = "e"
                    elif cell.data_type == "f":
                        data_type = "n"
                    elif isinstance(cached_value, bool):
                        data_type = "b"
                    elif isinstance(cached_value, str):
                        data_type = "s"
                    elif isinstance(cached_value, (int, float)):
                        data_type = "n"
                    else:
                        data_type = "s"

                    cells.append(Cell(
                        sheet=ws.title,
                        address=cell.coordinate,
                        row=cell.row,
                        col=cell.column,
                        formula=formula,
                        cached_value=cached_value,
                        data_type=data_type,
                        number_format=getattr(cell, "number_format", None) or None,
                        is_array_formula=is_array,
                        shared_group_id=None,
                    ))

    finally:
        wb_formulas.close()
        wb_cached.close()

    # Sort deterministically
    sheets.sort(key=lambda s: s.index)
    cells.sort(key=lambda c: (c.sheet, c.row, c.col))

    # Extract VBA if present
    vba_modules: list = []
    vba_exceptions: list = []
    suffix_lower = path.suffix.lower()
    if suffix_lower in (".xlsm", ".xlsb"):
        try:
            vba_modules, vba_exceptions = extract_vba(path)
        except Exception as e:
            from archon.contracts.extract import ExtractException
            vba_exceptions.append(
                ExtractException(
                    code="E_OLE_PARSE_FAILED",
                    severity="error",
                    sheet=None,
                    detail=str(e),
                )
            )

    return RawExtract(
        schema_version="1.0",
        workbook_id=uuid.uuid4(),
        source=source,
        sheets=sheets,
        cells=cells,
        defined_names=_defined_names(path),
        tables=_tables(path),
        vba_modules=vba_modules,
        exceptions=vba_exceptions,
    )