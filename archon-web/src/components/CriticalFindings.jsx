import Card from "./Card"
import Badge from "./Badge"
import "./CriticalFindings.css"

/**
 * Lists the most serious audit findings, each with a risk badge.
 */
function CriticalFindings({ findings = [] }) {
  return (
    <Card title="Critical Findings">
      <ul className="findings">
        {findings.map((f) => (
          <li key={f.id} className="finding">
            <Badge level={f.level}>{f.level} risk</Badge>
            <h3 className="finding-title">{f.title}</h3>
            <p className="finding-detail">{f.detail}</p>
          </li>
        ))}
      </ul>
    </Card>
  )
}

export default CriticalFindings