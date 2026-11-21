"""Background audit jobs: start, watch the stages, get the result."""

import asyncio
import time
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from openpyxl import Workbook

from archon.api import main
from archon.pipeline import STAGES


def _xlsx() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws["A1"], ws["B1"] = "Price", "Amount"
    for r in range(2, 8):
        ws[f"A{r}"], ws[f"B{r}"] = r, f"=A{r}*2"
    ws["B5"] = 999
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _start(data: bytes, name: str = "book.xlsx") -> str:
    started = asyncio.run(main.start_audit(UploadFile(file=BytesIO(data), filename=name)))
    assert started["status"] == "queued"
    return started["job_id"]


def _wait(job_id: str) -> dict:
    for _ in range(200):
        job = main.audit_job(job_id)
        if job["status"] in ("done", "error"):
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_job_runs_to_a_result():
    job = _wait(_start(_xlsx()))
    assert job["status"] == "done"
    assert job["result"]["analysis"]["bugs"][0]["address"] == "B5"
    assert job["stage"] == STAGES[-1] and job["step"] == len(STAGES) == job["steps"]


def test_every_stage_is_reported_in_order(monkeypatch):
    seen = []
    real = main._audit_bytes

    def spy(content, suffix, progress=None):
        return real(content, suffix, lambda stage: (seen.append(stage), progress(stage)))

    monkeypatch.setattr(main, "_audit_bytes", spy)
    assert _wait(_start(_xlsx()))["status"] == "done"
    assert seen == list(STAGES)


def test_unreadable_file_fails_the_job_instead_of_hanging():
    job = _wait(_start(b"this is not a workbook"))
    assert (job["status"], job["error"]) == ("error", "Could not read this Excel workbook.")


def test_unknown_job_is_404():
    with pytest.raises(HTTPException) as err:
        main.audit_job("nope")
    assert err.value.status_code == 404


def test_old_jobs_are_forgotten(monkeypatch):
    monkeypatch.setattr(main, "MAX_JOBS", 2)
    ids = [_start(_xlsx()) for _ in range(3)]
    for job_id in ids[1:]:
        _wait(job_id)
    with pytest.raises(HTTPException):
        main.audit_job(ids[0])


def test_a_running_job_that_was_forgotten_does_not_crash_its_worker(monkeypatch):
    errors = []
    real = main._run_job

    def guarded(*args):
        try:
            real(*args)
        except Exception as exc:  # noqa: BLE001 - the test records any crash
            errors.append(exc)

    monkeypatch.setattr(main, "_run_job", guarded)
    job_id = _start(_xlsx())
    with main._jobs_lock:
        main._jobs.pop(job_id)  # evicted while still running
    main._workers.submit(lambda: None).result()  # let queued work drain
    time.sleep(0.5)
    assert errors == []
