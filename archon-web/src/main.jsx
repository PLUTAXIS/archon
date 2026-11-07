import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './styles/tokens.css'
import './index.css'
import './styles/print.css'
import App from './App.jsx'
import { AuthProvider } from './auth/AuthContext.jsx'
import { AuditProvider } from './audit/AuditContext.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <AuditProvider>
          <App />
        </AuditProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)