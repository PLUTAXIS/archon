import { Routes, Route } from "react-router-dom"
import ProtectedRoute from "./components/ProtectedRoute"
import Login from "./pages/Login"
import Dashboard from "./pages/Dashboard"
import ReportPreviewer from "./pages/ReportPreviewer"

function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Dashboard />
          </ProtectedRoute>
        }
      />
      <Route
        path="/report"
        element={
          <ProtectedRoute>
            <ReportPreviewer />
          </ProtectedRoute>
        }
      />
    </Routes>
  )
}

export default App