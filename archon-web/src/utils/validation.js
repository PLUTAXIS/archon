/**
 * Checks the login form values and returns an object of error messages.
 * An empty object means the form is valid.
 */
export function validateLogin({ email, password }) {
  const errors = {}

  if (!email.trim()) {
    errors.email = "Email is required."
  } else if (!/^\S+@\S+\.\S+$/.test(email)) {
    errors.email = "Enter a valid email address."
  }

  if (!password) {
    errors.password = "Password is required."
  } else if (password.length < 8) {
    errors.password = "Password must be at least 8 characters."
  }

  return errors
}