import os
import hashlib
import platform
import subprocess
import openpyxl
from openpyxl.worksheet.formula import ArrayFormula
from openpyxl.utils.exceptions import InvalidFileException
from oletools.olevba import VBA_Parser
import msoffcrypto

# FIX 1: Imported Contract A directly as demanded by Wrik
from archon.contracts.extract import RawExtract, Cell, Sheet, ExtractException

def is_password_protected(file_path):
    """Checks if a Microsoft Office file is encrypted with a password."""
    try:
        with open(file_path, "rb") as f:
            office_file = msoffcrypto.OfficeFile(f)
            return office_file.is_encrypted()
    except msoffcrypto.exceptions.InvalidFileException:
        # FIX 2: Using Strict Contract Exception Codes
        raise ExtractException(code="E_CORRUPT_ZIP", detail="Malformed or unsupported file format.")
    except Exception as e:
        raise ExtractException(code="E_OLE_PARSE_FAILED", detail=f"Cannot securely inspect file: {str(e)}")

def extract_vba_macros(file_path):
    """Extracts embedded VBA macros from the Office file and generates verifiable metadata."""
    metadata = []
    try:
        vba_parser = VBA_Parser(file_path)
        if vba_parser.detect_vba_macros():
            for index, (filename, stream_path, vba_filename, vba_code) in enumerate(vba_parser.extract_macros()):
                safe_name = "".join([c for c in vba_filename if c.isalpha() or c.isdigit()]).rstrip()
                code_bytes = vba_code.encode('utf-8', errors='replace')
                metadata.append({
                    "module_name": safe_name,
                    "sha256": hashlib.sha256(code_bytes).hexdigest(),
                    "line_count": vba_code.count('\n') + 1
                })
        return metadata
    except Exception as e:
        raise ExtractException(code="E_OLE_PARSE_FAILED", detail=f"VBA extraction failed explicitly: {str(e)}")

def parse_excel_workbook(file_path, run_id):
    """
    Parses workbook into a unified Contract A RawExtract object.
    Includes both formula and cached_value for Senpai parity.
    """
    if is_password_protected(file_path):
        raise ExtractException(code="E_UNSUPPORTED_FEATURE", detail="Password protected file.")

    with open(file_path, 'rb') as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()

    try:
        # FIX 5: Removed read_only=True for formulas to prevent Shared Formula collapse (the 10,000 dragged rows trap)
        wb_formulas = openpyxl.load_workbook(file_path, data_only=False)
        # FIX 3: Second pass with data_only=True to strictly fetch cached_value
        wb_values = openpyxl.load_workbook(file_path, data_only=True)
        
        sheets_data = []
        for sheet_name in wb_formulas.sheetnames:
            ws_f = wb_formulas[sheet_name]
            ws_v = wb_values[sheet_name]
            
            cells_data = []
            for row_f, row_v in zip(ws_f.iter_rows(), ws_v.iter_rows()):
                for cell_f, cell_v in zip(row_f, row_v):
                    formula_str = None
                    
                    # FIX 4: Correctly extracting ArrayFormula using .text instead of str()
                    if isinstance(cell_f.value, ArrayFormula):
                        formula_str = cell_f.value.text
                    elif cell_f.data_type == 'f' or (isinstance(cell_f.value, str) and cell_f.value.startswith('=')):
                        formula_str = str(cell_f.value)
                    
                    cached_val = cell_v.value
                    
                    if formula_str is not None or cached_val is not None:
                        cells_data.append(Cell(
                            reference=cell_f.coordinate,
                            formula=formula_str,
                            cached_value=cached_val
                        ))
                        
            sheets_data.append(Sheet(
                name=sheet_name,
                state=ws_f.sheet_state,
                cells=cells_data
            ))
        
        wb_formulas.close()
        wb_values.close()

        vba_metadata = extract_vba_macros(file_path)

        # FIX 1: Returning a validated Contract A object (no ad-hoc dict arrays)
        return RawExtract(
            schema_version="1.0",
            workbook_id=run_id,
            source={"filename": os.path.basename(file_path), "sha256": file_hash, "vba": vba_metadata},
            sheets=sheets_data
        )
        
    except InvalidFileException as e:
        raise ExtractException(code="E_CORRUPT_ZIP", detail=f"FileFormatError in openpyxl: {str(e)}")
    except ExtractException:
        raise
    except Exception as e:
        raise ExtractException(code="E_OLE_PARSE_FAILED", detail=f"Unexpected parsing error: {str(e)}")

def extract_access_db(file_path):
    """
    Extracts table schemas from MS Access database.
    """
    extracted_tables = []
    if platform.system() != "Windows":
        try:
            tables_out = subprocess.run(["mdb-tables", "-1", str(file_path)], capture_output=True, text=True, check=True, timeout=60)
            tables = sorted([t for t in tables_out.stdout.splitlines() if len(t) > 0])
            for t in tables:
                extracted_tables.append({"table_name": t, "status": "Extracted via mdbtools"})
            return extracted_tables
        except Exception as e:
            raise ExtractException(code="E_UNSUPPORTED_FEATURE", detail=f"mdbtools extraction failed: {str(e)}")
    else:
        import pyodbc
        conn_str = r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=' + file_path + ';'
        try:
            conn = pyodbc.connect(conn_str)
            cursor = conn.cursor()
            tables = sorted([row.table_name for row in cursor.tables(tableType='TABLE')])
            for table in tables:
                # FIX 6: Using cursor.columns() instead of loading entire table data into memory with SELECT *
                cols = cursor.columns(table=table)
                column_names = [col.column_name for col in cols]
                extracted_tables.append({"table_name": table, "columns": column_names})
            conn.close()
            return extracted_tables
        except pyodbc.Error as e:
            err_text = str(e.args[1]).lower() if len(e.args) > 1 else str(e).lower()
            if "password" in err_text:
                raise ExtractException(code="E_UNSUPPORTED_FEATURE", detail="Access DB is password protected.")
            raise ExtractException(code="E_OLE_PARSE_FAILED", detail=f"Connection failed: {err_text}")
        except Exception as e:
            raise ExtractException(code="E_OLE_PARSE_FAILED", detail=f"Access extraction failed: {str(e)}")