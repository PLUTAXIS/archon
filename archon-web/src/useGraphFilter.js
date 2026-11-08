import { useMemo, useState } from "react"

/**
 * Handles the "Show High Risk Nodes Only" filter.
 * The high-risk list is built once when the nodes load, so toggling
 * only swaps which list is shown. No recalculation, no network call.
 */
export function useGraphFilter(nodes) {
  const [highRiskOnly, setHighRiskOnly] = useState(false)

  const highRiskNodes = useMemo(
    () => nodes.filter((n) => n.risk === "high"),
    [nodes]
  )

  const visibleNodes = highRiskOnly ? highRiskNodes : nodes

  return {
    visibleNodes,
    highRiskCount: highRiskNodes.length,
    highRiskOnly,
    setHighRiskOnly,
  }
}