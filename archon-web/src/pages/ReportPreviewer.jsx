import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import Card from "../components/Card"
import Button from "../components/Button"
import Badge from "../components/Badge"
import RiskGauge from "../components/RiskGauge"
import CriticalFindings from "../components/CriticalFindings"
import { fetchReport } from "../api/reports"
import { useAudit } from "../audit/AuditContext"
import { downloadExcel } from "../utils/exportExcel"
import "./ReportPreviewer.css"

/**
 * Report page: loads the report, then shows Critical Findings first,
 * followed by the risk score and details.
 */
function ReportPreviewer() {
  const { record } = useAudit()
  const [report, setReport] = useState(null)
  const [error, setError] = useState("")

  useEffect(() => {
    let cancelled = false
    fetchReport()
      .then((data) => {
        if (!cancelled) setReport(data)
      })
      .catch((e) => {
        if (!cancelled) setError(e.message)
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (error) {
    return (
      <main className="report">
        <p>
          <Link to="/">Back to dashboard</Link>
        </p>
        <Card title="Could not load the report">
          <p role="alert">{error}</p>
        </Card>
      </main>
    )
  }

  if (!report) {
    return (
      <main className="report">
        <p>Loading report…</p>
      </main>
    )
  }

  const { client, date, riskScore, findings, details } = report

  function handlePdf() {
    record("Downloaded PDF")
    window.print()
  }

  function handleExcel() {
    record("Downloaded Excel")
    const rows = details.map((d) => ({
      Area: d.area,
      Issue: d.issue,
      Risk: d.level,
    }))
    downloadExcel(rows, "audit-report.xlsx", "Detailed Findings")
  }

  return (
    <main className="report">
      <p className="no-print">
        <Link to="/">Back to dashboard</Link>
      </p>
      <header className="report-header">
        <div>
          <h1 className="report-title">Audit Report</h1>
          <p className="report-meta">
            {client} · {date}
          </p>
        </div>
        <div className="no-print report-actions">
          <Button variant="secondary" onClick={handleExcel}>
            Download Excel
          </Button>
          <Button onClick={handlePdf}>Download PDF</Button>
        </div>
      </header>

      <div className="report-summary">
        <CriticalFindings findings={findings} />
        <Card title="Risk Score">
          <RiskGauge score={riskScore} />
          <p className="report-score-note">High risk. Immediate action advised.</p>
        </Card>
      </div>

      <div className="report-section">
        <Card title="Detailed Findings">
          <div className="report-table-wrap">
            <table className="report-table">
              <thead>
                <tr>
                  <th>Area</th>
                  <th>Issue</th>
                  <th>Risk</th>
                </tr>
              </thead>
              <tbody>
                {details.map((row) => (
                  <tr key={row.id}>
                    <td>{row.area}</td>
                    <td>{row.issue}</td>
                    <td>
                      <Badge level={row.level}>{row.level}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </main>
  )
}

export default ReportPreviewer