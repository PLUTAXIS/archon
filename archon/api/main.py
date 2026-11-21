import os
import tempfile
import threading
import uuid
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from zipfile import BadZipFile

from fastapi import FastAPI, File, HTTPException, UploadFile
from openpyxl.utils.exceptions import InvalidFileException
from starlette.concurrency import run_in_threadpool
from starlette.middleware.cors import CORSMiddleware

from archon.ingest.xlsx import extract
from archon.pipeline import STAGES, run_extract

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


READ_ERRORS = (InvalidFileException, BadZipFile, KeyError, OSError, ValueError)
LIMITATIONS = [
    "Access (.accdb/.mdb) and binary .xlsb files are not analysed yet.",
    "VBA writes are traced only for static Range/Cells targets; dynamic ones are listed, not resolved.",
]


def _audit_bytes(
    content: bytes, suffix: str, progress: Callable[[str], None] | None = None
) -> dict:
    """Extract (Contract A) and run the full pipeline on uploaded bytes."""
    if progress:
        progress(STAGES[0])
    fd, tmp = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(content)
        return run_extract(extract(Path(tmp)), progress)
    finally:
        os.unlink(tmp)


def _response(filename: str, size: int, analysis: dict) -> dict:
    return {
        "status": "success",
        "audit_level": "full_pipeline",
        "filename": filename,
        "file_size_bytes": size,
        "analysis": analysis,
        "limitations": LIMITATIONS,
    }


async def _read_upload(file: UploadFile) -> tuple[str, str, bytes]:
    """Validate an upload (type, size, not empty, not encrypted); return its parts."""
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
    return filename, suffix, content


@app.post("/audit")
async def audit_workbook(file: UploadFile = File(...)):  # noqa: B008 - FastAPI idiom
    """Audit and wait for the result (kept for simple clients)."""
    filename, suffix, content = await _read_upload(file)
    try:
        analysis = await run_in_threadpool(_audit_bytes, content, suffix)
    except READ_ERRORS as exc:
        raise HTTPException(status_code=400, detail="Could not read this Excel workbook.") from exc
    return _response(filename, len(content), analysis)


# ---- Background jobs: start an audit, then poll for its stage and result ----
# shortcut: jobs live in this process's memory (lost on restart, one server only); move to a queue/store for multi-instance hosting.
MAX_JOBS = 16
_jobs: OrderedDict[str, dict] = OrderedDict()
_jobs_lock = threading.Lock()
_workers = ThreadPoolExecutor(max_workers=2)


def _run_job(job_id: str, filename: str, suffix: str, content: bytes) -> None:
    def progress(stage: str) -> None:
        _update(job_id, status="running", stage=stage, step=STAGES.index(stage) + 1)

    try:
        result = _response(filename, len(content), _audit_bytes(content, suffix, progress))
        update = {"status": "done", "result": result}
    except READ_ERRORS:
        update = {"status": "error", "error": "Could not read this Excel workbook."}
    except Exception:  # noqa: BLE001 - any crash must reach the user as a failed job, not a hang
        update = {"status": "error", "error": "The audit failed unexpectedly."}
    _update(job_id, **update)


def _update(job_id: str, **fields: object) -> None:
    """Record job progress; a job already forgotten (evicted) is simply skipped."""
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(fields)


@app.post("/audit/jobs", status_code=202)
async def start_audit(file: UploadFile = File(...)):  # noqa: B008 - FastAPI idiom
    """Start an audit in the background; poll GET /audit/jobs/{job_id}."""
    filename, suffix, content = await _read_upload(file)
    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {"status": "queued", "stage": "Waiting to start", "step": 0, "steps": len(STAGES)}
        while len(_jobs) > MAX_JOBS:  # forget the oldest job
            _jobs.popitem(last=False)
    _workers.submit(_run_job, job_id, filename, suffix, content)
    return {"job_id": job_id, "status": "queued"}


@app.get("/audit/jobs/{job_id}")
def audit_job(job_id: str):
    """A job's stage while it runs; its full result once done."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Unknown or expired audit job.")
        return {"job_id": job_id, **job}
