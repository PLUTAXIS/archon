import { Link } from "react-router-dom"
import Card from "../components/Card"
import Button from "../components/Button"
import { useAuth } from "../auth/AuthContext"
import { useAudit } from "../audit/AuditContext"
import "./Dashboard.css"

/**
 * Home screen after login, with links to the app's pages.
 */
function Dashboard() {
  const { user, logout } = useAuth()
  const { record } = useAudit()

  function handleLogout() {
    record("Signed out")
    logout()
  }

  return (
    <main className="dashboard">
      <header className="dashboard-header">
        <h1 className="dashboard-title">Dashboard</h1>
        <div className="dashboard-user">
          <span>{user.email}</span>
          <Button variant="secondary" onClick={handleLogout}>
            Log out
          </Button>
        </div>
      </header>

      <Card title="Reports">
        <p>
          <Link to="/report" onClick={() => record("Opened audit report")}>
            Open the audit report
          </Link>
        </p>
        <p>
          <Link to="/audit">View audit trail</Link>
        </p>
        <p>
          <Link to="/graph">Open the risk graph</Link>
        </p>
      </Card>
    </main>
  )
}

export default Dashboard