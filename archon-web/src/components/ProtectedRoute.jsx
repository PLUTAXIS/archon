import { Navigate } from "react-router-dom"
import { useAuth } from "../auth/AuthContext"

/**
 * Shows the page only to logged-in users; others go to the login page.
 */
function ProtectedRoute({ children }) {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  return children
}

export default ProtectedRoute