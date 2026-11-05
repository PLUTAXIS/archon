import os
import hashlib
import platform
import subprocess
import openpyxl
from openpyxl.worksheet.formula import ArrayFormula
from openpyxl.utils.exceptions import InvalidFileException
from oletools.olevba import VBA_Parser
import msoffcrypto

# Now only importing the data models, NOT using ExtractException as a throwable error
from archon.contracts.extract import RawExtract, Cell, Sheet

class IngestionError(Exception):
    """Custom standard exception for ingestion failures to avoid Pydantic clashes."""
    def __init__(self, code, detail):
        super().__init__(detail)
        self.code = code
        self.detail = detail

def is_password_protected(file_path):
    """
    Checks if a Microsoft Office file is encrypted with a password.
    """
    try:
        with open(file_path, "rb") as f:
            office_file = msoffcrypto.OfficeFile(f)
            return office_file.is_encrypted()
    except msoffcrypto.exceptions.InvalidFileException:
        raise IngestionError(code="E_CORRUPT_ZIP", detail="Malformed or unsupported file format.")
    except Exception as e:
        raise IngestionError(code="E_OLE_PARSE_FAILED", detail=f"Cannot securely inspect file: {str(e)}")

def extract_vba_macros(file_path):
    """
    Extracts embedded VBA macros from the Office file and generates verifiable metadata.
    """
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
        raise IngestionError(code="E_OLE_PARSE_FAILED", detail=f"VBA extraction failed explicitly: {str(e)}")

def parse_excel_workbook(file_path, run_id):
    """
    Parses workbook into a unified Contract A RawExtract object safely.
    """
    if is_password_protected(file_path):
        raise IngestionError(code="E_UNSUPPORTED_FEATURE", detail="Password protected file.")

    with open(file_path, 'rb') as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()

    try:
        # Re-enabled read_only=True to fix memory exhaustion risk flagged by CodeRabbit
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=False)
        
        sheets_data = []
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            cells_data = []
            
            for row in ws.iter_rows():
                for cell in row:
                    formula_str = None
                    # We are in read-only mode, we can only safely extract formulas.
                    # Senpai's compute parity will require a separate tool or engine later.
                    if isinstance(cell.value, ArrayFormula):
                        formula_str = cell.value.text
                    elif cell.data_type == 'f' or (isinstance(cell.value, str) and cell.value.startswith('=')):
                        formula_str = str(cell.value)
                    
                    if formula_str is not None:
                        cells_data.append(Cell(
                            reference=cell.coordinate,
                            formula=formula_str,
                            cached_value=None # Cached values are unreliable in read-only mode
                        ))
                        
            sheets_data.append(Sheet(
                name=sheet_name,
                state="visible", # read_only mode doesn't support sheet_state property natively
                cells=cells_data
            ))
        
        wb.close()
        vba_metadata = extract_vba_macros(file_path)

        return RawExtract(
            schema_version="1.0",
            workbook_id=run_id,
            source={"filename": os.path.basename(file_path), "sha256": file_hash, "vba": vba_metadata},
            sheets=sheets_data
        )
        
    except InvalidFileException as e:
        raise IngestionError(code="E_CORRUPT_ZIP", detail=f"FileFormatError in openpyxl: {str(e)}")
    except IngestionError:
        raise
    except Exception as e:
        raise IngestionError(code="E_OLE_PARSE_FAILED", detail=f"Unexpected parsing error: {str(e)}")

def extract_access_db(file_path):
    """
    Extracts table schemas from an MS Access database safely.
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
            raise IngestionError(code="E_UNSUPPORTED_FEATURE", detail=f"mdbtools extraction failed: {str(e)}")
    else:
        import pyodbc
        conn_str = r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=' + file_path + ';'
        try:
            conn = pyodbc.connect(conn_str)
            cursor = conn.cursor()
            tables = sorted([row.table_name for row in cursor.tables(tableType='TABLE')])
            for table in tables:
                cols = cursor.columns(table=table)
                column_names = [col.column_name for col in cols]
                extracted_tables.append({"table_name": table, "columns": column_names})
            conn.close()
            return extracted_tables
        except pyodbc.Error as e:
            err_text = str(e.args[1]).lower() if len(e.args) > 1 else str(e).lower()
            if "password" in err_text:
                raise IngestionError(code="E_UNSUPPORTED_FEATURE", detail="Access DB is password protected.")
            raise IngestionError(code="E_OLE_PARSE_FAILED", detail=f"Connection failed: {err_text}")
        except Exception as e:
            raise IngestionError(code="E_OLE_PARSE_FAILED", detail=f"Access extraction failed: {str(e)}")