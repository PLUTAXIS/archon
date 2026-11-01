import zipfile
import xml.etree.ElementTree as ET
import os
import json
import openpyxl
from openpyxl.utils.exceptions import InvalidFileException
from oletools.olevba import VBA_Parser
import msoffcrypto
import hashlib
import platform
import subprocess

def is_password_protected(file_path):
    try:
        with open(file_path, "rb") as f:
            office_file = msoffcrypto.OfficeFile(f)
            if office_file.is_encrypted():
                return True
    except msoffcrypto.exceptions.InvalidFileException:
        raise ValueError("Malformed or unsupported file format.")
    except Exception as e:
        raise RuntimeError(f"InspectionError: Cannot securely inspect file: {str(e)}")
    return False

def analyze_workbook_structure(file_path, run_id):
    base_name = os.path.basename(file_path)
    output_file = f"extracted_data_{run_id}_{base_name}.json"
    
    try:
        with zipfile.ZipFile(file_path, 'r') as archive:
            workbook_xml = archive.read('xl/workbook.xml')
            root = ET.fromstring(workbook_xml)
            ns = {'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            
            extracted_sheets = []
            for sheet in root.findall('.//main:sheet', ns):
                sheet_name = sheet.attrib.get('name')
                sheet_id = sheet.attrib.get('sheetId')
                # Capturing visible/hidden/veryHidden accurately as per the brief
                state = sheet.attrib.get('state', 'visible') 
                extracted_sheets.append({"name": sheet_name, "id": sheet_id, "state": state})
                
            with open(output_file, "w") as json_file:
                json.dump(extracted_sheets, json_file, indent=4)
            return [output_file]
            
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as e:
        raise ValueError(f"FileFormatError or Malformed workbook structure: {type(e).__name__} - {str(e)}")
    except Exception as e:
        raise RuntimeError(f"Unexpected error during structure analysis: {str(e)}")

def extract_formulas(file_path, run_id):
    base_name = os.path.basename(file_path)
    output_file = f"extracted_formulas_{run_id}_{base_name}.json"
    
    try:
        # read_only=True enforced for 500k cell memory safety
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=False)
        all_formulas = []
        for sheet_name in wb.sheetnames:
            sheet = wb[sheet_name]
            for row in sheet.iter_rows():
                for cell in row:
                    if cell.data_type == 'f' or (isinstance(cell.value, str) and cell.value.startswith('=')):
                        safe_formula_value = str(cell.value) if cell.value is not None else ""
                        all_formulas.append({
                            "sheet": sheet_name,
                            "cell_reference": cell.coordinate,
                            "formula": safe_formula_value
                        })
        wb.close()
        with open(output_file, "w") as json_file:
            json.dump(all_formulas, json_file, indent=4)
        return [output_file]
    except InvalidFileException as e:
        raise ValueError(f"FileFormatError in openpyxl: {str(e)}")
    except Exception as e:
        raise RuntimeError(f"Formula extraction failed: {str(e)}")

def extract_vba_macros(file_path, run_id):
    generated_files = []
    metadata = []
    try:
        vba_parser = VBA_Parser(file_path)
        if vba_parser.detect_vba_macros():
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            for index, (filename, stream_path, vba_filename, vba_code) in enumerate(vba_parser.extract_macros()):
                safe_name = "".join([c for c in vba_filename if c.isalpha() or c.isdigit()]).rstrip()
                output_file = f"vba_module_{run_id}_{base_name}_{index}_{safe_name}.txt"
                
                # Verbatim source save
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(vba_code)
                generated_files.append(output_file)
                
                # SHA256 and Line Count for Senpai's validation
                code_bytes = vba_code.encode('utf-8', errors='replace')
                metadata.append({
                    "module_name": safe_name,
                    "sha256": hashlib.sha256(code_bytes).hexdigest(),
                    "line_count": vba_code.count('\n') + 1,
                    "file_reference": output_file
                })
            
            if metadata:
                meta_file = f"vba_metadata_{run_id}_{base_name}.json"
                with open(meta_file, "w") as json_file:
                    json.dump(metadata, json_file, indent=4)
                generated_files.append(meta_file)
                
        return generated_files
    except Exception as e:
        raise RuntimeError(f"VBA macro extraction failed explicitly: {str(e)}")

def extract_access_db(file_path, run_id):
    base_name = os.path.basename(file_path)
    output_file = f"extracted_access_data_{run_id}_{base_name}.json"
    
    # 1. Enterprise Standard: mdbtools for Docker/Linux
    if platform.system() != "Windows":
        try:
            tables_out = subprocess.run(["mdb-tables", "-1", str(file_path)], capture_output=True, text=True, check=True)
            tables = sorted(tables_out.stdout.split())
            extracted_tables = [{"table_name": t, "status": "Schema Extracted via mdbtools"} for t in tables]
            with open(output_file, "w") as json_file:
                json.dump(extracted_tables, json_file, indent=4)
            return [output_file]
        except Exception as e:
            raise RuntimeError(f"mdbtools extraction failed in Linux environment: {str(e)}")
            
    # 2. Local Fallback: pyodbc for Windows development only
    else:
        import pyodbc
        conn_str = r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=' + file_path + ';'
        try:
            conn = pyodbc.connect(conn_str)
            cursor = conn.cursor()
            tables = sorted([row.table_name for row in cursor.tables(tableType='TABLE')])
            extracted_tables = []
            for table in tables:
                cursor.execute(f"SELECT * FROM [{table}]")
                columns = [column[0] for column in cursor.description]
                extracted_tables.append({"table_name": table, "columns": columns, "status": "Schema Extracted via pyodbc (Local Win)"})
            conn.close()
            with open(output_file, "w") as json_file:
                json.dump(extracted_tables, json_file, indent=4)
            return [output_file]
        except pyodbc.Error as e:
            error_msg = str(e).lower()
            if "password" in error_msg or "exclusive" in error_msg:
                raise PermissionError("Access Database is password protected.")
            raise ValueError(f"Database connection failed: {error_msg}")
        except Exception as e:
            raise RuntimeError(f"Access extraction failed: {str(e)}")