import { Link } from "react-router-dom"
import Card from "../components/Card"
import Button from "../components/Button"
import { useAuth } from "../auth/AuthContext"
import "./Dashboard.css"

/**
 * Home screen after login, with links to the app's pages.
 */
function Dashboard() {
  const { user, logout } = useAuth()

  return (
    <main className="dashboard">
      <header className="dashboard-header">
        <h1 className="dashboard-title">Dashboard</h1>
        <div className="dashboard-user">
          <span>{user.email}</span>
          <Button variant="secondary" onClick={logout}>
            Log out
          </Button>
        </div>
      </header>

      <Card title="Reports">
        <p>
          <Link to="/report">Open the audit report</Link>
        </p>
      </Card>
    </main>
  )
}

export default Dashboard