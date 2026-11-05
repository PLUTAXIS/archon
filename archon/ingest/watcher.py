import time
import os
import shutil
import uuid
import json
from concurrent.futures import ThreadPoolExecutor
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from archon.ingest.ingestion_core import parse_excel_workbook, extract_access_db, IngestionError
# Now using ExtractException solely for writing to the ledger JSON as designed
from archon.contracts.extract import ExtractException

executor = ThreadPoolExecutor(max_workers=4)

def wait_for_file_transfer(file_path, timeout=60):
    """
    Monitors a file to ensure it has completely finished transferring to the dropzone.
    """
    historical_size = -1
    retries = 0
    while retries < timeout:
        try:
            current_size = os.path.getsize(file_path)
            if current_size == historical_size and current_size > 0:
                return True
            historical_size = current_size
            time.sleep(1)
            retries += 1
        except FileNotFoundError:
            return False
        except Exception:
            time.sleep(1)
            retries += 1
    return False

def route_deliverables(deliverable_path):
    """
    Routes the extracted JSON output files to designated downstream folders.
    """
    mainak_folder = "For_Mainak"
    senpai_folder = "For_Senpai"
    try:
        os.makedirs(mainak_folder, exist_ok=True)
        os.makedirs(senpai_folder, exist_ok=True)
        if os.path.exists(deliverable_path):
            shutil.copy(deliverable_path, os.path.join(mainak_folder, os.path.basename(deliverable_path)))
            shutil.move(deliverable_path, os.path.join(senpai_folder, os.path.basename(deliverable_path)))
        return True
    except Exception as e:
        print(f"[-] ERROR routing deliverable: {str(e)}")
        return False

def archive_original_file(file_path):
    """
    Moves the processed original client file into a secure archive directory with a timestamp.
    """
    archive_folder = "Archive_Processed"
    base_name, ext = os.path.splitext(os.path.basename(file_path))
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    archive_path = os.path.join(archive_folder, f"{base_name}_{timestamp}{ext}")
    try:
        os.makedirs(archive_folder, exist_ok=True)
        shutil.move(file_path, archive_path)
        return True
    except Exception as e:
        print(f"[-] Archive directory failure: {str(e)}")
        return False

def process_file_task(file_path):
    """
    Worker task that runs on a separate thread to process files without blocking the observer.
    """
    if not wait_for_file_transfer(file_path):
        return

    print(f"\n[ALERT] Processing locked client file: {os.path.basename(file_path)}")
    run_id = uuid.uuid4().hex[:8]
    ledger_exceptions = []
    deliverable_path = None
    
    try:
        if file_path.endswith(('.xlsx', '.xlsm')):
            raw_extract = parse_excel_workbook(file_path, run_id)
            deliverable_path = f"extract_{run_id}.json"
            with open(deliverable_path, "w") as f:
                f.write(raw_extract.model_dump_json(indent=4))
                
        elif file_path.endswith('.accdb'):
            access_data = extract_access_db(file_path)
            deliverable_path = f"access_schema_{run_id}.json"
            with open(deliverable_path, "w") as f:
                json.dump(access_data, f, indent=4)
                
    except IngestionError as e:
        # Use Pydantic ExtractException model only for serialization to ledger
        ex_model = ExtractException(code=e.code, detail=e.detail)
        ledger_exceptions.append(ex_model.model_dump())
    except Exception as e:
        ex_model = ExtractException(code="E_FATAL_CRASH", detail=f"Unexpected ingestion crash: {str(e)}")
        ledger_exceptions.append(ex_model.model_dump())

    if ledger_exceptions:
        ledger_file = f"exceptions_ledger_{run_id}.json"
        with open(ledger_file, "w") as lf:
            json.dump(ledger_exceptions, lf, indent=4)
        print(f"[-] Exceptions logged for {os.path.basename(file_path)}.")
        
        # If extraction failed, we still archive the bad file so it doesn't loop
        archive_original_file(file_path)

    elif deliverable_path:
        # Success path: atomic check to ensure duplicate processing loop doesn't occur
        if route_deliverables(deliverable_path):
            if archive_original_file(file_path):
                print(f"[SUCCESS] Execution cycle finished for {os.path.basename(file_path)}.")
            else:
                print(f"[-] WARNING: File processed and routed, but archive failed for {os.path.basename(file_path)}.")
        else:
            print(f"[-] Execution cycle FAILED (Routing Error) for {os.path.basename(file_path)}.")

class DropzoneHandler(FileSystemEventHandler):
    """Watchdog event handler that monitors directory state."""
    
    def on_created(self, event):
        """Triggered when a file or directory is created."""
        if not event.is_directory and event.src_path.endswith(('.xlsx', '.xlsm', '.accdb')):
            executor.submit(process_file_task, event.src_path)
            
    def on_moved(self, event):
        """Triggered when a file or directory is moved or renamed."""
        if not event.is_directory and event.dest_path.endswith(('.xlsx', '.xlsm', '.accdb')):
            executor.submit(process_file_task, event.dest_path)

if __name__ == "__main__":
    dropzone_path = "Dropzone"
    os.makedirs(dropzone_path, exist_ok=True)
        
    observer = Observer()
    observer.schedule(DropzoneHandler(), dropzone_path, recursive=False)
    observer.start()
    
    print(f"[*] 🚀 ENTERPRISE WATCHER ACTIVE: '{dropzone_path}' 24/7.")
    
    for filename in os.listdir(dropzone_path):
        filepath = os.path.join(dropzone_path, filename)
        if os.path.isfile(filepath) and filepath.endswith(('.xlsx', '.xlsm', '.accdb')):
            executor.submit(process_file_task, filepath)
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Shutting down gracefully...")
        observer.stop()
    observer.join()
    executor.shutdown(wait=True)