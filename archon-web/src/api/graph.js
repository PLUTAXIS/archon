import { request, USE_MOCK } from "./client"
import { buildSampleGraph } from "../data/sampleGraph"

/**
 * Turns graph data into the shape the app uses: nodes with an id,
 * a label and a risk of high, medium or low.
 * Adjust the field names here once the real dag_graph.json is confirmed.
 */
export function normalizeGraph(raw) {
  const list = Array.isArray(raw) ? raw : raw?.nodes
  if (!Array.isArray(list)) {
    throw new Error("No nodes found in graph data.")
  }

  const nodes = list.map((n, i) => {
    const risk = String(n.risk ?? n.risk_level ?? n.severity ?? "low").toLowerCase()
    return {
      id: String(n.id ?? i),
      label: String(n.label ?? n.name ?? n.id ?? i),
      risk: ["high", "critical", "red"].includes(risk)
        ? "high"
        : risk === "medium"
          ? "medium"
          : "low",
    }
  })

  return { nodes, edges: raw?.edges ?? [] }
}

/**
 * Loads the graph. Uses sample data until a backend URL is set.
 */
export async function fetchGraph() {
  if (USE_MOCK) {
    await new Promise((resolve) => setTimeout(resolve, 300))
    return buildSampleGraph(1000)
  }
  return normalizeGraph(await request("/graph"))
}