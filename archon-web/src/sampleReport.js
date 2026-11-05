export const sampleReport = {
  client: "Sample Client Ltd",
  date: "November 2026",
  riskScore: 88,
  findings: [
    {
      id: 1,
      level: "high",
      title: "Unprotected formulas in payroll sheet",
      detail: "Cells can be overwritten without any record of who changed them.",
    },
    {
      id: 2,
      level: "high",
      title: "Hardcoded tax rate in 14 cells",
      detail: "A rate change would silently break totals across the workbook.",
    },
    {
      id: 3,
      level: "medium",
      title: "No input validation on date columns",
      detail: "Text entries in date fields produce wrong month-end figures.",
    },
  ],
}