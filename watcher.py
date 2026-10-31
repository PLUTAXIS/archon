import sys
import time
import os
import shutil
import glob
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from ingestion_core import analyze_workbook_structure, extract_formulas, extract_vba_macros, extract_access_db, is_password_protected

def route_deliverables():
    mainak_folder = "For_Mainak"
    senpai_folder = "For_Senpai"
    os.makedirs(mainak_folder, exist_ok=True)
    os.makedirs(senpai_folder, exist_ok=True)
    
    print("\n--- Hand-Off Protocol 2 ---")
    
    json_files = glob.glob("extracted_*.json")
    vba_files = glob.glob("vba_module_*.txt")
    all_files = json_files + vba_files
    
    if not all_files:
        print("[-] No deliverables found to route.")
        return

    for f in all_files:
        shutil.copy(f, os.path.join(mainak_folder, f))
        shutil.move(f, os.path.join(senpai_folder, f))
        
    print(f"[+] Successfully pushed {len(all_files)} deliverables into '{mainak_folder}' and '{senpai_folder}' folders.")

def archive_original_file(file_path):
    archive_folder = "Archive_Processed"
    os.makedirs(archive_folder, exist_ok=True)
    try:
        shutil.move(file_path, os.path.join(archive_folder, os.path.basename(file_path)))
        print(f"[+] Original file moved to '{archive_folder}' to keep the Dropzone clean.")
    except Exception as e:
        print(f"[-] Could not archive file: {str(e)}")

class ExcelHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith(('.xlsx', '.xlsm', '.accdb')):
            print(f"\n[==================================================]")
            print(f"[ALERT] New client file detected in Dropzone: {os.path.basename(event.src_path)}")
            time.sleep(1) # Wait for file to fully copy
            
            # Check for password protection first
            if event.src_path.endswith(('.xlsx', '.xlsm')) and is_password_protected(event.src_path):
                print("[!] Logging exception for the final audit report.")
            else:
                if event.src_path.endswith(('.xlsx', '.xlsm')):
                    analyze_workbook_structure(event.src_path)
                    extract_formulas(event.src_path)
                    extract_vba_macros(event.src_path)
                elif event.src_path.endswith('.accdb'):
                    extract_access_db(event.src_path)
                
                route_deliverables()
            
            # Clean up the Dropzone
            archive_original_file(event.src_path)
            
            print(f"\n[SUCCESS] Entire process finished for {os.path.basename(event.src_path)}.")
            print("[*] Waiting for the next file... (Press Ctrl+C to stop)")

if __name__ == "__main__":
    dropzone_path = "Dropzone"
    
    if not os.path.exists(dropzone_path):
        os.makedirs(dropzone_path)
        
    event_handler = ExcelHandler()
    observer = Observer()
    observer.schedule(event_handler, dropzone_path, recursive=False)
    observer.start()
    
    print(f"[*] 🚀 PRO-SYSTEM ACTIVE: Watching the '{dropzone_path}' folder 24/7.")
    print(f"[*] Features enabled: Password Detection, Auto-Extraction, Auto-Routing, and Auto-Archiving.")
    print(f"[*] Drop any .xlsx, .xlsm, or .accdb file into '{dropzone_path}' to trigger...")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Stopping watcher...")
        observer.stop()
    observer.join()