import hashlib
import uuid
from pathlib import Path

import openpyxl

from archon.contracts.extract import (
    Cell,
    RawExtract,
    Sheet,
    Source,
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def extract(path: Path) -> RawExtract:
    path = Path(path)
    suffix = path.suffix.lower().lstrip(".")

    source = Source(
        filename=path.name,
        sha256=_sha256(path),
        format=suffix,
        bytes=path.stat().st_size,
    )

    wb = openpyxl.load_workbook(path, read_only=True, data_only=False)

    sheets = []
    cells = []

    for idx, ws in enumerate(wb.worksheets):
        sheet_state = getattr(ws, "sheet_state", "visible")
        sheets.append(Sheet(
            name=ws.title,
            index=idx,
            visibility=sheet_state,
            dimensions=getattr(ws, "dimensions", None) or "A1:A1",
            merged_cells=[],
            frozen_panes=None,
        ))

        for row in ws.iter_rows():
            for cell in row:
                if cell.value is None:
                    continue
                formula = None
                cached_value = None
                is_array = False

                if isinstance(cell.value, str) and cell.value.startswith("="):
                    formula = cell.value
                elif hasattr(cell.value, "text"):
                    formula = "=" + str(cell.value.text)
                    is_array = True
                else:
                    cached_value = cell.value

                cells.append(Cell(
                    sheet=ws.title,
                    address=cell.coordinate,
                    row=cell.row,
                    col=cell.column,
                    formula=formula,
                    cached_value=cached_value,
                    data_type="s" if isinstance(cached_value, str) else
                               "b" if isinstance(cached_value, bool) else
                               "n" if isinstance(cached_value, (int, float)) else "s",
                    number_format=None,
                    is_array_formula=is_array,
                    shared_group_id=None,
                ))

    wb.close()

    return RawExtract(
        schema_version="1.0",
        workbook_id=uuid.uuid4(),
        source=source,
        sheets=sheets,
        cells=cells,
        exceptions=[],
    )