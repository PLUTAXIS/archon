import os
import hashlib
import platform
import subprocess
import openpyxl
from openpyxl.worksheet.formula import ArrayFormula
from openpyxl.utils.exceptions import InvalidFileException
from oletools.olevba import VBA_Parser
import msoffcrypto

# Importing all required models strictly according to Contract A
from archon.contracts.extract import RawExtract, Cell, Sheet, Source, ExtractException

class ExtractError(Exception):
    """Standard exception wrapper for the Pydantic ExtractException model."""
    def __init__(self, exc: ExtractException):
        super().__init__(exc.detail)
        self.exc = exc

def is_password_protected(file_path):
    """Checks if a Microsoft Office file is encrypted with a password."""
    try:
        with open(file_path, "rb") as f:
            office_file = msoffcrypto.OfficeFile(f)
            return office_file.is_encrypted()
    except msoffcrypto.exceptions.FileFormatError:
        raise ExtractError(ExtractException(code="E_CORRUPT_ZIP", severity="error", detail="Malformed or unsupported file format."))
    except Exception as e:
        raise ExtractError(ExtractException(code="E_OLE_PARSE_FAILED", severity="error", detail=f"Cannot securely inspect file: {str(e)}"))

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
        raise ExtractError(ExtractException(code="E_OLE_PARSE_FAILED", severity="error", detail=f"VBA extraction failed explicitly: {str(e)}"))

def parse_excel_workbook(file_path, full_uuid):
    """
    Parses workbook safely into a Contract A RawExtract object.
    Implements memory-safe chunked hashing and strict Pydantic model fields.
    """
    if is_password_protected(file_path):
        raise ExtractError(ExtractException(code="E_UNSUPPORTED_FEATURE", severity="error", detail="Password protected file."))

    file_hash_obj = hashlib.sha256()
    file_bytes = 0
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            file_hash_obj.update(chunk)
            file_bytes += len(chunk)
    file_hash = file_hash_obj.hexdigest()

    try:
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=False)
        
        sheets_data = []
        cells_data = []
        
        for idx, sheet_name in enumerate(wb.sheetnames):
            ws = wb[sheet_name]
            dim = ws.calculate_dimension() if hasattr(ws, 'calculate_dimension') else "A1"
            
            sheets_data.append(Sheet(
                name=sheet_name,
                index=idx,
                visibility="visible",
                dimensions=dim
            ))
            
            for row in ws.iter_rows():
                for cell in row:
                    formula_str = None
                    is_array = False
                    
                    if isinstance(cell.value, ArrayFormula):
                        formula_str = cell.value.text
                        is_array = True
                    elif cell.data_type == 'f' or (isinstance(cell.value, str) and cell.value.startswith('=')):
                        formula_str = str(cell.value)
                    
                    if formula_str is not None:
                        cells_data.append(Cell(
                            sheet=sheet_name,
                            address=cell.coordinate,
                            row=cell.row,
                            col=cell.column,
                            data_type="formula", # Correct data_type for formulas in Contract A
                            is_array_formula=is_array
                        ))
                        
        wb.close()

        # Contract A Source requires format and bytes. vba is NOT part of Source.
        source_obj = Source(
            filename=os.path.basename(file_path), 
            sha256=file_hash,
            format="xlsx", 
            bytes=file_bytes
        )

        return RawExtract(
            schema_version="1.0",
            workbook_id=full_uuid,
            source=source_obj,
            sheets=sheets_data,
            cells=cells_data,
            exceptions=[]
        )
        
    except InvalidFileException as e:
        raise ExtractError(ExtractException(code="E_CORRUPT_ZIP", severity="error", detail=f"FileFormatError in openpyxl: {str(e)}"))
    except ExtractError:
        raise
    except Exception as e:
        raise ExtractError(ExtractException(code="E_OLE_PARSE_FAILED", severity="error", detail=f"Unexpected parsing error: {str(e)}"))

def extract_access_db(file_path):
    """Extracts table schemas from an MS Access database safely."""
    extracted_tables = []
    if platform.system() != "Windows":
        try:
            tables_out = subprocess.run(["mdb-tables", "-1", str(file_path)], capture_output=True, text=True, check=True, timeout=60)
            tables = sorted([t for t in tables_out.stdout.splitlines() if len(t) > 0])
            for t in tables:
                extracted_tables.append({"table_name": t, "status": "Extracted via mdbtools"})
            return extracted_tables
        except Exception as e:
            raise ExtractError(ExtractException(code="E_UNSUPPORTED_FEATURE", severity="error", detail=f"mdbtools extraction failed: {str(e)}"))
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
                raise ExtractError(ExtractException(code="E_UNSUPPORTED_FEATURE", severity="error", detail="Access DB is password protected."))
            raise ExtractError(ExtractException(code="E_OLE_PARSE_FAILED", severity="error", detail=f"Connection failed: {err_text}"))
        except Exception as e:
            raise ExtractError(ExtractException(code="E_OLE_PARSE_FAILED", severity="error", detail=f"Access extraction failed: {str(e)}"))