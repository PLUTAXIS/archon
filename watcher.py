import sys
import time
import os
import shutil
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
    """Waits until file size stops changing, ensuring the transfer is fully complete."""
    print(f"[*] Verifying file transfer integrity: {os.path.basename(file_path)}")
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
    return False

def route_deliverables(deliverables):
    """Routes ONLY the distinct deliverables produced for the current input."""
    if not deliverables:
        print("[-] No deliverables to route for this input.")
        return True

    mainak_folder = "For_Mainak"
    senpai_folder = "For_Senpai"
    os.makedirs(mainak_folder, exist_ok=True)
    os.makedirs(senpai_folder, exist_ok=True)
    
    print("\n--- Hand-Off Protocol 2 ---")
    try:
        for f in deliverables:
            if os.path.exists(f):
                shutil.copy(f, os.path.join(mainak_folder, f))
                shutil.move(f, os.path.join(senpai_folder, f))
        print(f"[+] Successfully pushed {len(deliverables)} secure deliverables.")
        return True
    except Exception as e:
        print(f"[-] ERROR during hand-off routing: {str(e)}")
        return False

def archive_original_file(file_path):
    """Archives input with a timestamp to prevent overwriting duplicate basenames."""
    archive_folder = "Archive_Processed"
    os.makedirs(archive_folder, exist_ok=True)
    
    base_name, ext = os.path.splitext(os.path.basename(file_path))
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    unique_name = f"{base_name}_{timestamp}{ext}"
    archive_path = os.path.join(archive_folder, unique_name)
    
    try:
        shutil.move(file_path, archive_path)
        print(f"[+] Input archived securely as '{unique_name}'")
    except Exception as e:
        print(f"[-] Could not archive file: {str(e)}")

def process_file(file_path):
    if not wait_for_file_transfer(file_path):
        print("[-] File transfer timed out or file disappeared.")
        return

    print(f"\n[==================================================]")
    print(f"[ALERT] New client file locked for processing: {os.path.basename(file_path)}")
    
    deliverables = []
    extraction_success = False
    
    try:
        if file_path.endswith(('.xlsx', '.xlsm')):
            if is_password_protected(file_path):
                print("[!] Audit Flag: Password-protected Excel file identified. Skipping core extraction.")
            else:
                deliverables.extend(analyze_workbook_structure(file_path))
                deliverables.extend(extract_formulas(file_path))
                deliverables.extend(extract_vba_macros(file_path))
                extraction_success = True
                
        elif file_path.endswith('.accdb'):
            deliverables.extend(extract_access_db(file_path))
            extraction_success = True
            
    except (ValueError, PermissionError) as e:
        print(f"[!] Validation Exception: {str(e)}. Handled gracefully.")
    except Exception as e:
        print(f"[-] FATAL EXCEPTION: {str(e)}. Caught at core level before reaching watcher.")

    # Archive the input ONLY after a successful extraction and hand-off
    if deliverables and extraction_success:
        if route_deliverables(deliverables):
            archive_original_file(file_path)
    elif not extraction_success:
        print("[!] Processing skipped or failed. Archiving to clear Dropzone.")
        archive_original_file(file_path)
        
    print(f"[SUCCESS] Execution cycle finished for {os.path.basename(file_path)}.")
    print("[*] Waiting for the next file... (Press Ctrl+C to stop)")

class DropzoneHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith(('.xlsx', '.xlsm', '.accdb')):
            process_file(event.src_path)
            
    def on_moved(self, event):
        # Trigger when a file is renamed directly INTO the Dropzone
        if not event.is_directory and event.dest_path.endswith(('.xlsx', '.xlsm', '.accdb')):
            process_file(event.dest_path)

if __name__ == "__main__":
    dropzone_path = "Dropzone"
    os.makedirs(dropzone_path, exist_ok=True)
        
    observer = Observer()
    observer.schedule(DropzoneHandler(), dropzone_path, recursive=False)
    observer.start()
    
    print(f"[*] 🚀 ENTERPRISE WATCHER ACTIVE: '{dropzone_path}' 24/7.")
    print(f"[*] Hardened Features: Transfer Lock, Rename Tracking, State Routing, Timestamps.")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Shutting down gracefully...")
        observer.stop()
    observer.join()