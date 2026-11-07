import { request, USE_MOCK } from "./client"
import { sampleReport } from "../data/sampleReport"

/**
 * Loads the audit report. Uses sample data until a backend URL is set.
 */
export async function fetchReport() {
  if (USE_MOCK) {
    // Short pause so loading states can be seen while testing
    await new Promise((resolve) => setTimeout(resolve, 300))
    return sampleReport
  }
  return request("/report")
}