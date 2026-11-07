import { Link } from "react-router-dom"
import Card from "../components/Card"
import { useAudit } from "../audit/AuditContext"
import "./AuditTrail.css"

/**
 * Table of recorded actions, newest first.
 */
function AuditTrail() {
  const { entries } = useAudit()

  return (
    <main className="audit">
      <p>
        <Link to="/">Back to dashboard</Link>
      </p>
      <Card title="Audit Trail">
        {entries.length === 0 ? (
          <p>No activity recorded yet.</p>
        ) : (
          <div className="audit-table-wrap">
            <table className="audit-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>User</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => (
                  <tr key={e.id}>
                    <td>{new Date(e.time).toLocaleString()}</td>
                    <td>{e.user}</td>
                    <td>{e.action}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </main>
  )
}

export default AuditTrail