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
  details: [
    { id: 1, area: "Payroll", issue: "Unprotected formulas", level: "high" },
    { id: 2, area: "Payroll", issue: "Hardcoded tax rate", level: "high" },
    { id: 3, area: "Finance", issue: "No date validation", level: "medium" },
    { id: 4, area: "Finance", issue: "Merged cells in totals", level: "medium" },
    { id: 5, area: "HR", issue: "Duplicate employee IDs", level: "medium" },
    { id: 6, area: "HR", issue: "Inconsistent naming", level: "low" },
    { id: 7, area: "Inventory", issue: "Unused hidden sheets", level: "low" },
    { id: 8, area: "Inventory", issue: "Manual stock counts", level: "low" },
  ],
}