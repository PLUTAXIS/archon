import json
import os
import shutil
import time
import uuid

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from archon.ingest.ingestion_core import (
    analyze_workbook_structure,
    extract_access_db,
    extract_formulas,
    extract_vba_macros,
    is_password_protected,
)


def wait_for_file_transfer(file_path, timeout=60):
    """
    Monitors a file to ensure it has completely finished transferring to the dropzone.
    
    Args:
        file_path (str): The path of the file to monitor.
        timeout (int): Maximum time in seconds to wait for file size stabilization.
        
    Returns:
        bool: True if the file transfer is complete and stable, False otherwise.
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
        except Exception:  # noqa: BLE001
            time.sleep(1)
            retries += 1
    return False

def route_deliverables(deliverables):
    """
    Routes the extracted output files to designated downstream folders for Mainak and Senpai.
    
    Args:
        deliverables (list): A list of generated file paths to be routed.
        
    Returns:
        bool: True if all files were successfully routed, False if an error occurred.
    """
    if not deliverables:
        return True
    
    mainak_folder = "For_Mainak"
    senpai_folder = "For_Senpai"
    
    try:
        os.makedirs(mainak_folder, exist_ok=True)
        os.makedirs(senpai_folder, exist_ok=True)
        for f in deliverables:
            if os.path.exists(f):
                shutil.copy(f, os.path.join(mainak_folder, f))
                shutil.move(f, os.path.join(senpai_folder, f))
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[-] ERROR during hand-off routing: {e!s}")
        return False

def archive_original_file(file_path):
    """
    Moves the processed original client file into a secure archive directory with a timestamp.
    
    Args:
        file_path (str): Path to the original file to be archived.
        
    Raises:
        RuntimeError: If the archival movement operation fails.
    """
    archive_folder = "Archive_Processed"
    base_name, ext = os.path.splitext(os.path.basename(file_path))
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    unique_name = f"{base_name}_{timestamp}{ext}"
    archive_path = os.path.join(archive_folder, unique_name)
    
    try:
        os.makedirs(archive_folder, exist_ok=True)
        shutil.move(file_path, archive_path)
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Archive directory failure: {e!s}")

def process_file(file_path):
    """
    Core controller function that processes a single file dropped into the watched directory.
    Executes password checks, initiates extraction functions, records exceptions, and routes results.
    
    Args:
        file_path (str): Path of the newly detected file.
    """
    if not wait_for_file_transfer(file_path):
        return

    print("\n[==================================================]")
    print(f"[ALERT] Processing locked client file: {os.path.basename(file_path)}")
    
    run_id = uuid.uuid4().hex[:8]
    deliverables = []
    ledger_exceptions = []
    extraction_success = False
    
    try:
        if file_path.endswith(('.xlsx', '.xlsm')):
            if is_password_protected(file_path):
                ledger_exceptions.append({"code": "E_PASSWORD_PROTECTED", "severity": "warn", "detail": "File is password protected"})
            else:
                deliverables.extend(analyze_workbook_structure(file_path, run_id))
                deliverables.extend(extract_formulas(file_path, run_id))
                deliverables.extend(extract_vba_macros(file_path, run_id))
                extraction_success = True
                
        elif file_path.endswith('.accdb'):
            deliverables.extend(extract_access_db(file_path, run_id))
            extraction_success = True
            
    except (ValueError, PermissionError) as e:
        ledger_exceptions.append({"code": "E_VALIDATION_ERROR", "severity": "error", "detail": str(e)})
    except RuntimeError as e:
        ledger_exceptions.append({"code": "E_RUNTIME_FAILURE", "severity": "error", "detail": str(e)})
    except Exception as e:  # noqa: BLE001
        ledger_exceptions.append({"code": "E_FATAL_CRASH", "severity": "error", "detail": str(e)})

    ledger_file = f"exceptions_ledger_{run_id}.json"
    with open(ledger_file, "w") as lf:
        json.dump(ledger_exceptions, lf, indent=4)
    deliverables.append(ledger_file)

    try:
        if extraction_success or ledger_exceptions:
            if route_deliverables(deliverables):
                archive_original_file(file_path)
                status = "[SUCCESS]" if extraction_success else "[PARTIAL/FAILED]"
                print(f"{status} Execution cycle finished for {os.path.basename(file_path)}.")
            else:
                print(f"[-] Execution cycle FAILED (Routing Error) for {os.path.basename(file_path)}.")
    except RuntimeError as arch_err:
        print(f"[-] CYCLE FAILED (Archive Error): {arch_err!s}")

    print("[*] Waiting for the next file... (Press Ctrl+C to stop)")

class DropzoneHandler(FileSystemEventHandler):
    """
    Watchdog event handler that monitors directory state and triggers processing on file creation or movement.
    """
    def __init__(self, callback):
        """
        Initializes the event handler with a specified callback function.
        
        Args:
            callback (function): The function to execute when a valid file is detected.
        """
        self.process_callback = callback

    def on_created(self, event):
        """
        Triggered when a file or directory is created. Filters for targeted extensions.
        
        Args:
            event (FileSystemEvent): Event representing file/directory creation.
        """
        if not event.is_directory and event.src_path.endswith(('.xlsx', '.xlsm', '.accdb')):
            self.process_callback(event.src_path)
            
    def on_moved(self, event):
        """
        Triggered when a file or directory is moved/renamed. Filters for targeted extensions.
        
        Args:
            event (FileSystemEvent): Event representing file/directory movement.
        """
        if not event.is_directory and event.dest_path.endswith(('.xlsx', '.xlsm', '.accdb')):
            self.process_callback(event.dest_path)

if __name__ == "__main__":
    dropzone_path = "Dropzone"
    os.makedirs(dropzone_path, exist_ok=True)
        
    observer = Observer()
    observer.schedule(DropzoneHandler(process_file), dropzone_path, recursive=False)
    observer.start()
    
    print(f"[*] 🚀 ENTERPRISE WATCHER ACTIVE: '{dropzone_path}' 24/7.")
    print("[*] V7.2 (Reconciliation Applied): Processing pre-existing files.")
    
    # NEW FIX: Reconcile existing files that were dropped before the observer started
    for filename in os.listdir(dropzone_path):
        filepath = os.path.join(dropzone_path, filename)
        if os.path.isfile(filepath) and filepath.endswith(('.xlsx', '.xlsm', '.accdb')):
            print(f"[*] Reconciling existing file found in dropzone: {filename}")
            process_file(filepath)
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Shutting down gracefully...")
        observer.stop()
    observer.join()