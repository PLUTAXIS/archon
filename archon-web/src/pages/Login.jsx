import { useState } from "react"
import { useNavigate } from "react-router-dom"
import Card from "../components/Card"
import Button from "../components/Button"
import TextField from "../components/TextField"
import { useAuth } from "../auth/AuthContext"
import { validateLogin } from "../utils/validation"
import "./Login.css"

/**
 * Login screen with email and password validation.
 */
function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [values, setValues] = useState({ email: "", password: "" })
  const [errors, setErrors] = useState({})
  const [formError, setFormError] = useState("")

  function handleChange(e) {
    setValues({ ...values, [e.target.name]: e.target.value })
  }

  function handleSubmit(e) {
    e.preventDefault()
    const found = validateLogin(values)
    setErrors(found)
    setFormError("")
    if (Object.keys(found).length > 0) return

    const result = login(values.email.trim(), values.password)
    if (result.ok) {
      navigate("/")
    } else {
      setFormError(result.error)
    }
  }

  return (
    <main className="login">
      <Card title="Sign in">
        <form onSubmit={handleSubmit} noValidate>
          <TextField
            label="Email"
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            value={values.email}
            onChange={handleChange}
            error={errors.email}
          />
          <TextField
            label="Password"
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            value={values.password}
            onChange={handleChange}
            error={errors.password}
          />
          {formError && (
            <p className="login-error" role="alert">
              {formError}
            </p>
          )}
          <Button type="submit">Sign in</Button>
        </form>
        <p className="login-hint">Demo: demo@example.com / demo12345</p>
      </Card>
    </main>
  )
}

export default Login