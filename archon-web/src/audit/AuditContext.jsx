import { createContext, useContext, useState } from "react"
import { useAuth } from "../auth/AuthContext"

const AuditContext = createContext(null)
const STORAGE_KEY = "archon_audit"

/**
 * Keeps a list of who did what and when, shared across the app.
 */
export function AuditProvider({ children }) {
  const { user } = useAuth()
  const [entries, setEntries] = useState(() => {
    try {
      const saved = sessionStorage.getItem(STORAGE_KEY)
      return saved ? JSON.parse(saved) : []
    } catch {
      return []
    }
  })

  function record(action, actor) {
    const entry = {
      id: `${Date.now()}-${Math.random()}`,
      time: new Date().toISOString(),
      user: actor || user?.email || "anonymous",
      action,
    }
    setEntries((prev) => {
      const next = [entry, ...prev]
      try {
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next))
      } catch {
        // storage unavailable: the log still works for this visit
      }
      return next
    })
  }

  return (
    <AuditContext.Provider value={{ entries, record }}>
      {children}
    </AuditContext.Provider>
  )
}

/**
 * Gives any component the audit entries and a record() function.
 */
export function useAudit() {
  return useContext(AuditContext)
}