import os
import tempfile
from pathlib import Path
from zipfile import BadZipFile

from fastapi import FastAPI, File, HTTPException, UploadFile
from openpyxl.utils.exceptions import InvalidFileException
from starlette.concurrency import run_in_threadpool
from starlette.middleware.cors import CORSMiddleware

from archon.ingest.xlsx import extract
from archon.pipeline import run_extract

app = FastAPI(
    title="ARCHON API",
    description="Deterministic spreadsheet extraction and audit MVP",
    version="0.3.0",
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
SUPPORTED = (".xlsx", ".xlsm")
# Encrypted .xlsx/.xlsm files are OLE containers, not ZIP archives.
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "archon-api",
        "version": "0.3.0",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


def _audit_bytes(content: bytes, suffix: str) -> dict:
    """Extract (Contract A) and run the full pipeline on uploaded bytes."""
    fd, tmp = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(content)
        return run_extract(extract(Path(tmp)))
    finally:
        os.unlink(tmp)


@app.post("/audit")
async def audit_workbook(file: UploadFile = File(...)):  # noqa: B008 - FastAPI idiom
    filename = file.filename or "workbook.xlsx"
    suffix = Path(filename).suffix.lower()

    if suffix not in SUPPORTED:
        raise HTTPException(
            status_code=400,
            detail="Only .xlsx and .xlsm files are supported by this MVP.",
        )

    content = await file.read(MAX_UPLOAD_BYTES + 1)

    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="File exceeds the 20 MB upload limit.",
        )

    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    if content.startswith(OLE_MAGIC):
        raise HTTPException(
            status_code=400,
            detail="This workbook is password-protected. Remove the password and upload it again.",
        )

    try:
        analysis = await run_in_threadpool(_audit_bytes, content, suffix)
    except (InvalidFileException, BadZipFile, KeyError, OSError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail="Could not read this Excel workbook.",
        ) from exc

    return {
        "status": "success",
        "audit_level": "full_pipeline",
        "filename": filename,
        "file_size_bytes": len(content),
        "analysis": analysis,
        "limitations": [
            "Access (.accdb/.mdb) and binary .xlsb files are not analysed yet.",
            "VBA writes are traced only for static Range/Cells targets; dynamic ones are listed, not resolved.",
        ],
    }
