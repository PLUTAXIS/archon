import * as XLSX from "xlsx"

/**
 * Downloads a list of row objects as an .xlsx file.
 */
export function downloadExcel(rows, filename = "report.xlsx", sheetName = "Report") {
  const sheet = XLSX.utils.json_to_sheet(rows)
  const book = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(book, sheet, sheetName)
  XLSX.writeFile(book, filename)
}