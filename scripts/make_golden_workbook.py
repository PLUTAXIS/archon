"""Generates the golden fixture workbook for the end-to-end run."""
from openpyxl import Workbook

wb = Workbook()
ws = wb.active
ws.title = "Model"

# Formulas with cached-result potential
ws["A1"] = 5
ws["B1"] = "=A1*2"                      # simple formula
ws["C1"] = '=A1&"x"'                    # string concat formula
ws["D1"] = "Acme Corp Confidential"     # confidential string - must not survive
ws["E1"] = 290001                       # sensitive-looking number
ws["F1"] = "=SUM(A1:B1)"                # range formula

wb.save("golden_input.xlsx")
print("golden_input.xlsx written")
