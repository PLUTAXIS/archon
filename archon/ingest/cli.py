
# archon/ingest/cli.py
# Watches a folder for new Excel/Access files and processes them.
# The watcher only adds files to a queue.
# A separate worker performs the extraction.

import argparse
import logging
import queue
import threading
import time
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from archon.ingest.xlsx import extract as extract_xlsx
from archon.ingest.accdb import extract_accdb
from archon.ingest.recovery import UnprocessableWorkbook


# ------------------------------------------------
# LOGGING
# ------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
)
log = logging.getLogger(__name__)


# ------------------------------------------------
# SETTINGS
# ------------------------------------------------

SUPPORTED = {".xlsx", ".xlsm", ".accdb"}

work_queue = queue.Queue()

# Prevent the same file from being queued more than once
queued_files = set()
queue_lock = threading.Lock()


def add_to_queue(path: Path):
    """Add a supported file to the queue only once."""
    path = path.resolve()

    if path.suffix.lower() not in SUPPORTED:
        return

    with queue_lock:
        if path in queued_files:
            return

        queued_files.add(path)

    log.info("Adding to queue: %s", path.name)
    work_queue.put(path)


# ------------------------------------------------
# STEP 1 — WAIT FOR FILE COPY TO FINISH
# ------------------------------------------------

def wait_for_file_stable(path: Path, timeout: int = 60) -> bool:
    """
    Wait until the file size stops changing.
    Returns True when the file appears stable.
    """
    last_size = -1
    waited = 0

    while waited < timeout:
        try:
            current_size = path.stat().st_size
        except FileNotFoundError:
            return False

        if current_size > 0 and current_size == last_size:
            return True

        last_size = current_size
        time.sleep(1)
        waited += 1

    return False


# ------------------------------------------------
# STEP 2 — WATCHER
# ------------------------------------------------

class IngestHandler(FileSystemEventHandler):
    """
    Detect files and add them to the queue.
    Never performs extraction itself.
    """

    def on_created(self, event):
        if event.is_directory:
            return

        add_to_queue(Path(event.src_path))

    def on_moved(self, event):
        if event.is_directory:
            return

        add_to_queue(Path(event.dest_path))


# ------------------------------------------------
# STEP 3 — WORKER
# ------------------------------------------------

def worker():
    """
    Process queued files one by one.
    """

    log.info("Worker started — waiting for files...")

    while True:
        path = work_queue.get()

        # None is the signal to stop the worker
        if path is None:
            work_queue.task_done()
            break

        try:
            log.info("Processing: %s", path.name)

            if not wait_for_file_stable(path):
                log.error("File did not stabilise: %s", path.name)
                continue

            if path.suffix.lower() in {".xlsx", ".xlsm"}:
                result = extract_xlsx(path)

                log.info(
                    "Done: %s — %s sheets, %s cells, %s exceptions",
                    path.name,
                    len(result.sheets),
                    len(result.cells),
                    len(result.exceptions),
                )

            elif path.suffix.lower() == ".accdb":
                tables, queries, exceptions = extract_accdb(path)

                log.info(
                    "Done: %s — %s tables, %s queries, %s exceptions",
                    path.name,
                    len(tables),
                    len(queries),
                    len(exceptions),
                )

        except UnprocessableWorkbook as error:
            log.error("UNPROCESSABLE: %s — %s", path.name, error)

        except Exception:
            log.exception("Unexpected error while processing %s", path.name)

        finally:
            with queue_lock:
                queued_files.discard(path)

            work_queue.task_done()


# ------------------------------------------------
# STEP 4 — START WATCHING
# ------------------------------------------------

def watch(folder: str):
    """Start watching a folder for supported files."""

    watch_path = Path(folder)

    if not watch_path.exists():
        raise FileNotFoundError(f"Folder not found: {folder}")

    if not watch_path.is_dir():
        raise NotADirectoryError(f"Not a folder: {folder}")

    log.info("Watching folder: %s", watch_path.resolve())

    # Start the extraction worker
    worker_thread = threading.Thread(
        target=worker,
        daemon=True,
    )
    worker_thread.start()

    # Start the folder watcher
    observer = Observer()
    event_handler = IngestHandler()

    observer.schedule(
        event_handler,
        str(watch_path.resolve()),
        recursive=False,
    )
    observer.start()

    # Also process supported files already in the folder
    for path in watch_path.iterdir():
        if path.is_file():
            add_to_queue(path)

    try:
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        log.info("Stopping folder watcher...")

    finally:
        observer.stop()
        observer.join()

        # Tell the worker to finish and stop
        work_queue.put(None)
        worker_thread.join()

        log.info("Folder watcher stopped.")


# ------------------------------------------------
# STEP 5 — COMMAND-LINE ENTRY POINT
# ------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Watch a folder and extract Excel/Access files."
    )

    parser.add_argument(
        "folder",
        help="Path of the folder to watch",
    )

    args = parser.parse_args()
    watch(args.folder)


if __name__ == "__main__":
    main()
