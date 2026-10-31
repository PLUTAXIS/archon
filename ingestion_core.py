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
                print(f"\n[!] CRITICAL: The file '{os.path.basename(file_path)}' is PASSWORD PROTECTED.")
                return True
    except msoffcrypto.exceptions.InvalidFileException:
        print(f"[-] WARNING: '{os.path.basename(file_path)}' is malformed or not a valid Office file.")
        raise ValueError("Malformed or unsupported file format.")
    except Exception as e:
        print(f"[-] ERROR checking protection for '{os.path.basename(file_path)}': {str(e)}")
        raise

    return False

def analyze_workbook_structure(file_path):
    print(f"[*] Analyzing structure: {os.path.basename(file_path)}")
    base_name = os.path.basename(file_path)
    output_file = f"extracted_data_{base_name}.json"
    
    try:
        with zipfile.ZipFile(file_path, 'r') as archive:
            workbook_xml = archive.read('xl/workbook.xml')
            root = ET.fromstring(workbook_xml)
            ns = {'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            
            extracted_sheets = []
            for sheet in root.findall('.//main:sheet', ns):
                sheet_name = sheet.attrib.get('name')
                sheet_id = sheet.attrib.get('sheetId')
                state = sheet.attrib.get('state', 'visible') 
                
                extracted_sheets.append({"name": sheet_name, "id": sheet_id, "state": state})
                if state in ['hidden', 'veryHidden']:
                    print(f"[!] EXCEPTION: Found {state} sheet -> '{sheet_name}'")
                    
            with open(output_file, "w") as json_file:
                json.dump(extracted_sheets, json_file, indent=4)
            return [output_file]
            
    except zipfile.BadZipFile:
        print("[-] EXCEPTION: File is not a valid zip archive (Malformed workbook).")
        raise ValueError("Malformed workbook.")
    except Exception as e:
        print(f"[-] EXCEPTION during structure analysis: {str(e)}")
        raise

def extract_formulas(file_path):
    print(f"[*] Extracting formulas: {os.path.basename(file_path)}")
    base_name = os.path.basename(file_path)
    output_file = f"extracted_formulas_{base_name}.json"
    
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
        
        with open(output_file, "w") as json_file:
            json.dump(all_formulas, json_file, indent=4)
        return [output_file]
    except Exception as e:
        print(f"[-] EXCEPTION during formula extraction: {str(e)}")
        raise ValueError(f"Formula extraction failed: {str(e)}")

def extract_vba_macros(file_path):
    print(f"[*] Extracting VBA macros: {os.path.basename(file_path)}")
    generated_files = []
    try:
        vba_parser = VBA_Parser(file_path)
        if vba_parser.detect_vba_macros():
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            for (filename, stream_path, vba_filename, vba_code) in vba_parser.extract_macros():
                safe_name = "".join([c for c in vba_filename if c.isalpha() or c.isdigit()]).rstrip()
                # Added base_name to ensure distinct VBA files per client input
                output_file = f"vba_module_{base_name}_{safe_name}.txt"
                
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(vba_code)
                generated_files.append(output_file)
        return generated_files
    except Exception as e:
        print(f"[-] EXCEPTION during VBA extraction: {str(e)}")
        return []

def extract_access_db(file_path):
    print(f"[*] Extracting Access DB: {os.path.basename(file_path)}")
    base_name = os.path.basename(file_path)
    output_file = f"extracted_access_data_{base_name}.json"
    
    conn_str = r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=' + file_path + ';'
    
    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        tables = [row.table_name for row in cursor.tables(tableType='TABLE')]
        extracted_tables = []
        
        for table in tables:
            cursor.execute(f"SELECT * FROM [{table}]")
            columns = [column[0] for column in cursor.description]
            extracted_tables.append({
                "table_name": table,
                "columns": columns,
                "status": "Schema Extracted"
            })
            
        conn.close()
        with open(output_file, "w") as json_file:
            json.dump(extracted_tables, json_file, indent=4)
        return [output_file]
        
    except pyodbc.Error as e:
        error_msg = str(e).lower()
        # Explicit check for Access Database password protection
        if "password" in error_msg or "not a valid password" in error_msg or "exclusive" in error_msg:
            print(f"[!] CRITICAL: The Access database '{base_name}' is PASSWORD PROTECTED.")
            raise PermissionError("Access Database is password protected.")
        else:
            print(f"[-] EXCEPTION: DB connection failed. {error_msg}")
            raise ValueError(f"Database connection failed: {error_msg}")
    except Exception as e:
        print(f"[-] UNEXPECTED EXCEPTION: {str(e)}")
        raise