from io import BytesIO
from zipfile import BadZipFile

from fastapi import FastAPI, File, HTTPException, UploadFile
from starlette.middleware.cors import CORSMiddleware
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

app = FastAPI(
    title="ARCHON API",
    description="Deterministic spreadsheet extraction and audit MVP",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_SCANNED_CELLS = 250_000
MAX_FORMULA_SAMPLES = 500


@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "archon-api",
        "version": "0.2.0",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/audit")
async def audit_workbook(file: UploadFile = File(...)):
    filename = file.filename or "workbook.xlsx"

    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=400,
            detail="Only .xlsx files are supported by this MVP.",
        )

    content = await file.read(MAX_UPLOAD_BYTES + 1)

    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="File exceeds the 20 MB upload limit.",
        )

    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        workbook = load_workbook(
            BytesIO(content),
            read_only=True,
            data_only=False,
        )
    except (InvalidFileException, BadZipFile, OSError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail="Could not read this Excel workbook.",
        ) from exc

    sheets = []
    formula_samples = []
    formula_count = 0
    cells_scanned = 0
    scan_complete = True

    try:
        for worksheet in workbook.worksheets:
            sheets.append({
                "name": worksheet.title,
                "dimensions": worksheet.calculate_dimension(),
                "max_row": worksheet.max_row,
                "max_column": worksheet.max_column,
            })

            for row in worksheet.iter_rows():
                for cell in row:
                    if cells_scanned >= MAX_SCANNED_CELLS:
                        scan_complete = False
                        break

                    cells_scanned += 1

                    if cell.data_type == "f":
                        formula_count += 1

                        if len(formula_samples) < MAX_FORMULA_SAMPLES:
                            formula_samples.append({
                                "sheet": worksheet.title,
                                "cell": cell.coordinate,
                                "formula": str(cell.value),
                            })

                if not scan_complete:
                    break

            if not scan_complete:
                break
    finally:
        workbook.close()

    return {
        "status": "success",
        "audit_level": "extraction_mvp",
        "filename": filename,
        "file_size_bytes": len(content),
        "sheet_count": len(sheets),
        "sheets": sheets,
        "cells_scanned": cells_scanned,
        "formula_count": formula_count,
        "formula_samples": formula_samples,
        "formula_samples_truncated": formula_count > len(formula_samples),
        "scan_complete": scan_complete,
        "limitations": [
            "This endpoint currently extracts workbook structure and formulas.",
            "Full bug detection, VBA analysis, and risk scoring are not yet integrated.",
            "Workbooks exceeding the scan limit receive a partial extraction.",
        ],
    }
