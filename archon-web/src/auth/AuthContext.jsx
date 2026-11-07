import { createContext, useContext, useState } from "react"

const AuthContext = createContext(null)

// Placeholder login for the demo. Real login comes from the API (Part 8).
const DEMO_USER = { email: "demo@example.com", password: "demo12345" }

/**
 * Keeps track of who is logged in and shares login/logout with the app.
 */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      const saved = sessionStorage.getItem("archon_user")
      return saved ? JSON.parse(saved) : null
    } catch {
      return null
    }
  })

  function login(email, password) {
    if (email === DEMO_USER.email && password === DEMO_USER.password) {
      const next = { email }
      setUser(next)
      try {
        sessionStorage.setItem("archon_user", JSON.stringify(next))
      } catch {
        // storage unavailable: login still works for this visit
      }
      return { ok: true }
    }
    return { ok: false, error: "Incorrect email or password." }
  }

  function logout() {
    setUser(null)
    try {
      sessionStorage.removeItem("archon_user")
    } catch {
      // nothing to clear
    }
  }

  return (
    <AuthContext.Provider value={{ user, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

/**
 * Gives any component access to the logged-in user and login/logout.
 */
export function useAuth() {
  return useContext(AuthContext)
}