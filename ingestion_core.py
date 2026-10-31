import zipfile
import xml.etree.ElementTree as ET
import os
import json
import openpyxl
from oletools.olevba import VBA_Parser
import pyodbc
import msoffcrypto

def is_password_protected(file_path):
    try:
        with open(file_path, "rb") as f:
            office_file = msoffcrypto.OfficeFile(f)
            if office_file.is_encrypted():
                print(f"\n[!] CRITICAL EXCEPTION: The file '{os.path.basename(file_path)}' is PASSWORD PROTECTED.")
                print("[!] Flagging separately for the client. Skipping internal extraction.")
                return True
    except Exception:
        pass
    return False

def analyze_workbook_structure(file_path):
    print(f"[*] Processing file: {file_path}")
    if not os.path.exists(file_path):
        print("[!] Error: File not found.")
        return None

    try:
        with zipfile.ZipFile(file_path, 'r') as archive:
            workbook_xml = archive.read('xl/workbook.xml')
            root = ET.fromstring(workbook_xml)
            ns = {'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            
            extracted_sheets = []
            print("\n--- Sheet Geometry Extraction ---")
            for sheet in root.findall('.//main:sheet', ns):
                sheet_name = sheet.attrib.get('name')
                sheet_id = sheet.attrib.get('sheetId')
                state = sheet.attrib.get('state', 'visible') 
                
                extracted_sheets.append({"name": sheet_name, "id": sheet_id, "state": state})
                
                if state in ['hidden', 'veryHidden']:
                    print(f"[!] EXCEPTION FLAGGED: Found {state} sheet -> '{sheet_name}'")
                else:
                    print(f"[+] Found visible sheet: '{sheet_name}'")
                    
            with open("extracted_data.json", "w") as json_file:
                json.dump(extracted_sheets, json_file, indent=4)
            print("[+] Sheet geometry saved to extracted_data.json")
            return extracted_sheets
            
    except zipfile.BadZipFile:
        print("[-] EXCEPTION FLAGGED: File is not a valid zip archive.")
        return None

def extract_formulas(file_path):
    print(f"\n--- Formula Extraction ---")
    try:
        wb = openpyxl.load_workbook(file_path, data_only=False)
        all_formulas = []
        for sheet_name in wb.sheetnames:
            sheet = wb[sheet_name]
            for row in sheet.iter_rows():
                for cell in row:
                    if cell.data_type == 'f' or (isinstance(cell.value, str) and cell.value.startswith('=')):
                        all_formulas.append({
                            "sheet": sheet_name,
                            "cell_reference": cell.coordinate,
                            "formula": cell.value
                        })
        
        with open("extracted_formulas.json", "w") as json_file:
            json.dump(all_formulas, json_file, indent=4)
        print("[+] All formulas saved to extracted_formulas.json")
        return all_formulas
    except Exception as e:
        print(f"[-] EXCEPTION FLAGGED during formula extraction: {str(e)}")
        return None

def extract_vba_macros(file_path):
    print(f"\n--- VBA Macro Extraction ---")
    try:
        vba_parser = VBA_Parser(file_path)
        if vba_parser.detect_vba_macros():
            print("[+] VBA Macros found! Extracting source code...")
            for (filename, stream_path, vba_filename, vba_code) in vba_parser.extract_macros():
                safe_name = "".join([c for c in vba_filename if c.isalpha() or c.isdigit()]).rstrip()
                output_file = f"vba_module_{safe_name}.txt"
                
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(vba_code)
                print(f"[+] Exported VBA module to: {output_file}")
        else:
            print("[-] No VBA macros found in this file.")
    except Exception as e:
        print(f"[-] EXCEPTION FLAGGED during VBA extraction: {str(e)}")

def extract_access_db(file_path):
    print(f"\n--- Access Database (.accdb) Extraction ---")
    if not os.path.exists(file_path):
        print("[!] Error: File not found.")
        return None

    conn_str = r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=' + file_path + ';'
    extracted_tables = []
    
    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        tables = [row.table_name for row in cursor.tables(tableType='TABLE')]
        if not tables:
            print("[-] No user tables found in the Access database.")
            return None
            
        print(f"[+] Found {len(tables)} tables. Extracting schema...")
        for table in tables:
            cursor.execute(f"SELECT * FROM [{table}]")
            columns = [column[0] for column in cursor.description]
            extracted_tables.append({
                "table_name": table,
                "columns": columns,
                "status": "Schema Extracted"
            })
            print(f"[+] Extracted schema for table: {table}")
            
        conn.close()
        
        output_file = "extracted_access_data.json"
        with open(output_file, "w") as json_file:
            json.dump(extracted_tables, json_file, indent=4)
            
        print(f"\n[+] Access database schema saved to {output_file}")
        return extracted_tables

    except pyodbc.Error as e:
        print("[-] EXCEPTION FLAGGED: Database connection failed. Ensure 64-bit Access Database Engine is installed.")
        return None
    except Exception as e:
        print(f"[-] UNEXPECTED EXCEPTION: {str(e)}")
        return None