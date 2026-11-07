"""
Day 1 check: does openpyxl resolve shared/dragged formulas on its own,
or does it return formula=None for every cell except the first one?

Usage:
    uv run python check_shared_formula.py
"""
from pathlib import Path
import openpyxl

# Verified with openpyxl 3.1.5: shared formulas are expanded for every cell.
FIXTURE = Path(__file__).parent / "tests" / "ingest" / "fixtures" / "dragged_10k.xlsx"

def main():
    if not FIXTURE.exists():
        print(f"File not found: {FIXTURE}")
        print("Make sure dragged_10k.xlsx is saved at that exact path.")
        return

    wb = openpyxl.load_workbook(FIXTURE, read_only=True, data_only=False)
    ws = wb.active  # first sheet

    total_cells = 0
    cells_with_formula = 0
    examples_without_formula = []

    # Column G is column index 7
    for row in ws.iter_rows(min_col=7, max_col=7, min_row=1, max_row=10000):
        for cell in row:
            total_cells += 1
            if cell.value is not None and str(cell.value).startswith("="):
                cells_with_formula += 1
            else:
                if len(examples_without_formula) < 3:
                    examples_without_formula.append((cell.coordinate, repr(cell.value)))

    wb.close()

    print(f"Total cells checked in column G: {total_cells}")
    print(f"Cells with a formula string:      {cells_with_formula}")
    print()

    if cells_with_formula == total_cells:
        print("RESULT: 10,000 — openpyxl resolved every shared formula on its own.")
        print("Next step: write a short comment noting the openpyxl version, and move on.")
    elif cells_with_formula <= 1:
        print("RESULT: 1 — only the first cell has a formula. The rest came back empty.")
        print("Next step: you must resolve the shared formula group yourself (brief section 5).")
        print(f"Example empty cells: {examples_without_formula}")
    else:
        print(f"RESULT: partial ({cells_with_formula} of {total_cells}).")
        print("This is an unexpected in-between case. Report this exact number to Wrik.")
        print(f"Example empty cells: {examples_without_formula}")

if __name__ == "__main__":
    main()
