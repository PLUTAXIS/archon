import sys
import time
import os
import shutil
import uuid
import json
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from ingestion_core import (
    analyze_workbook_structure, 
    extract_formulas, 
    extract_vba_macros, 
    extract_access_db, 
    is_password_protected
)

def wait_for_file_transfer(file_path, timeout=60):
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

def route_deliverables(deliverables):
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
    except Exception as e:
        print(f"[-] ERROR during hand-off routing: {str(e)}")
        return False

def archive_original_file(file_path):
    archive_folder = "Archive_Processed"
    base_name, ext = os.path.splitext(os.path.basename(file_path))
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    unique_name = f"{base_name}_{timestamp}{ext}"
    archive_path = os.path.join(archive_folder, unique_name)
    
    try:
        os.makedirs(archive_folder, exist_ok=True)
        shutil.move(file_path, archive_path)
    except Exception as e:
        raise RuntimeError(f"Archive directory failure: {str(e)}")

def process_file(file_path):
    if not wait_for_file_transfer(file_path):
        return

    print(f"\n[==================================================]")
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
    except Exception as e:
        ledger_exceptions.append({"code": "E_FATAL_CRASH", "severity": "error", "detail": str(e)})

    # ALWAYS ship the exception ledger, even if empty (Strict Brief Requirement)
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
        print(f"[-] CYCLE FAILED (Archive Error): {str(arch_err)}")

    print("[*] Waiting for the next file... (Press Ctrl+C to stop)")

class DropzoneHandler(FileSystemEventHandler):
    def __init__(self, callback):
        self.process_callback = callback

    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith(('.xlsx', '.xlsm', '.accdb')):
            self.process_callback(event.src_path)
            
    def on_moved(self, event):
        if not event.is_directory and event.dest_path.endswith(('.xlsx', '.xlsm', '.accdb')):
            self.process_callback(event.dest_path)

if __name__ == "__main__":
    dropzone_path = "Dropzone"
    os.makedirs(dropzone_path, exist_ok=True)
        
    observer = Observer()
    observer.schedule(DropzoneHandler(process_file), dropzone_path, recursive=False)
    observer.start()
    
    print(f"[*] 🚀 ENTERPRISE WATCHER ACTIVE: '{dropzone_path}' 24/7.")
    print(f"[*] V7.0 (Final Architecture): mdbtools Docker Ready, Exceptions Ledger Shipped, VBA SHA256.")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Shutting down gracefully...")
        observer.stop()
    observer.join()