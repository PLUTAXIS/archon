import time
import os
import shutil
import uuid
import json
from concurrent.futures import ThreadPoolExecutor
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from archon.ingest.ingestion_core import parse_excel_workbook, extract_access_db
from archon.contracts.extract import ExtractException

executor = ThreadPoolExecutor(max_workers=4)

def wait_for_file_transfer(file_path, timeout=60):
    """
    Monitors a file to ensure it has completely finished transferring to the dropzone.
    
    Args:
        file_path (str): The absolute or relative path to the file being monitored.
        timeout (int): Maximum time in seconds to wait for the file size to stabilize.
        
    Returns:
        bool: True if the file transfer is complete and stable, False if it times out or fails.
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
    
    Args:
        deliverable_path (str): The path to the successfully generated extraction JSON file.
        
    Returns:
        bool: True if the file was successfully copied and moved to downstream folders, False otherwise.
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
    
    Args:
        file_path (str): Path to the original source file to be archived.
    """
    archive_folder = "Archive_Processed"
    base_name, ext = os.path.splitext(os.path.basename(file_path))
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    archive_path = os.path.join(archive_folder, f"{base_name}_{timestamp}{ext}")
    try:
        os.makedirs(archive_folder, exist_ok=True)
        shutil.move(file_path, archive_path)
    except Exception as e:
        print(f"[-] Archive directory failure: {str(e)}")

def process_file_task(file_path):
    """
    Worker task that runs on a separate thread to process files without blocking the observer.
    Handles extraction, error logging, and downstream routing.
    
    Args:
        file_path (str): The path of the newly detected file in the dropzone.
    """
    if not wait_for_file_transfer(file_path):
        return

    print(f"\n[ALERT] Processing locked client file: {os.path.basename(file_path)}")
    run_id = uuid.uuid4().hex[:8]
    ledger_exceptions = []
    extraction_success = False
    deliverable_path = None
    
    try:
        if file_path.endswith(('.xlsx', '.xlsm')):
            raw_extract = parse_excel_workbook(file_path, run_id)
            deliverable_path = f"extract_{run_id}.json"
            with open(deliverable_path, "w") as f:
                f.write(raw_extract.model_dump_json(indent=4))
            extraction_success = True
                
        elif file_path.endswith('.accdb'):
            access_data = extract_access_db(file_path)
            deliverable_path = f"access_schema_{run_id}.json"
            with open(deliverable_path, "w") as f:
                json.dump(access_data, f, indent=4)
            extraction_success = True
            
    except ExtractException as e:
        ledger_exceptions.append({"code": e.code, "severity": "error", "detail": str(e.detail)})
    except Exception as e:
        # NEW FIX: Catching ANY unexpected crash and logging it as a FATAL error before failing
        ledger_exceptions.append({"code": "E_FATAL_CRASH", "severity": "fatal", "detail": f"Unexpected ingestion crash: {str(e)}"})

    if ledger_exceptions:
        ledger_file = f"exceptions_ledger_{run_id}.json"
        with open(ledger_file, "w") as lf:
            json.dump(ledger_exceptions, lf, indent=4)
        print(f"[-] Exceptions logged for {os.path.basename(file_path)}.")

    if extraction_success and deliverable_path:
        if route_deliverables(deliverable_path):
            archive_original_file(file_path)
            print(f"[SUCCESS] Execution cycle finished for {os.path.basename(file_path)}.")
        else:
            print(f"[-] Execution cycle FAILED (Routing Error) for {os.path.basename(file_path)}.")

class DropzoneHandler(FileSystemEventHandler):
    """
    Watchdog event handler that monitors directory state and triggers multi-threaded processing.
    """
    
    def on_created(self, event):
        """
        Triggered when a file or directory is created. Filters for targeted file extensions.
        
        Args:
            event (FileSystemEvent): Event representing file or directory creation.
        """
        if not event.is_directory and event.src_path.endswith(('.xlsx', '.xlsm', '.accdb')):
            executor.submit(process_file_task, event.src_path)
            
    def on_moved(self, event):
        """
        Triggered when a file or directory is moved or renamed. Filters for targeted file extensions.
        
        Args:
            event (FileSystemEvent): Event representing file or directory movement.
        """
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