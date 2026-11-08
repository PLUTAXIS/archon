/**
 * Builds a sample graph of spreadsheet cells for testing.
 * About 1 in 8 cells is flagged high risk.
 */
export function buildSampleGraph(count = 1000) {
  const nodes = []
  for (let i = 0; i < count; i++) {
    const row = Math.floor(i / 25)
    const col = i % 25
    const risk = i % 8 === 0 ? "high" : i % 5 === 0 ? "medium" : "low"
    nodes.push({
      id: `cell-${i}`,
      label: `${String.fromCharCode(65 + col)}${row + 1}`,
      risk,
    })
  }
  return { nodes, edges: [] }
}