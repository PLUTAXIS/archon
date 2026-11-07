// Address of the backend API. Empty means "use sample data" (mock mode).
const BASE_URL = import.meta.env.VITE_API_BASE_URL || ""

export const USE_MOCK = !BASE_URL

/**
 * Sends a request to the backend and returns the JSON response.
 * Throws an Error with a readable message if the request fails.
 */
export async function request(path, options = {}) {
  let response
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    })
  } catch {
    throw new Error("Could not reach the server. Please try again.")
  }

  if (!response.ok) {
    throw new Error(`Request failed (${response.status}).`)
  }
  return response.json()
}