/**
 * Downloads a list of row objects as an .xlsx file.
 * The Excel library loads only when this is called, which keeps the
 * first page load small.
 */
export async function downloadExcel(rows, filename = "report.xlsx", sheetName = "Report") {
  const XLSX = await import("xlsx")
  const sheet = XLSX.utils.json_to_sheet(rows)
  const book = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(book, sheet, sheetName)
  XLSX.writeFile(book, filename)
}