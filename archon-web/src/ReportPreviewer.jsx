import Card from "../components/Card"
import Button from "../components/Button"
import RiskGauge from "../components/RiskGauge"
import CriticalFindings from "../components/CriticalFindings"
import { sampleReport } from "../data/sampleReport"
import "./ReportPreviewer.css"

/**
 * Report page: Critical Findings first, then the risk score.
 */
function ReportPreviewer() {
  const { client, date, riskScore, findings } = sampleReport

  return (
    <main className="report">
      <header className="report-header">
        <div>
          <h1 className="report-title">Audit Report</h1>
          <p className="report-meta">{client} · {date}</p>
        </div>
        <Button variant="secondary">Download PDF</Button>
      </header>

      <div className="report-summary">
        <CriticalFindings findings={findings} />
        <Card title="Risk Score">
          <RiskGauge score={riskScore} />
          <p className="report-score-note">High risk. Immediate action advised.</p>
        </Card>
      </div>
    </main>
  )
}

export default ReportPreviewer