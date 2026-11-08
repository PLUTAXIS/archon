import { useMemo } from "react"
import { Link } from "react-router-dom"
import Card from "../components/Card"
import Button from "../components/Button"
import GraphGrid from "../components/GraphGrid"
import { buildSampleGraph } from "../data/sampleGraph"
import { useGraphFilter } from "../hooks/useGraphFilter"
import "./GraphView.css"

/**
 * Risk graph page with a one-click "high risk only" filter.
 */
function GraphView() {
  const graph = useMemo(() => buildSampleGraph(1000), [])
  const { visibleNodes, highRiskCount, highRiskOnly, setHighRiskOnly } =
    useGraphFilter(graph.nodes)

  return (
    <main className="graph-page">
      <p>
        <Link to="/">Back to dashboard</Link>
      </p>
      <Card title="Risk Graph">
        <div className="graph-toolbar">
          <Button
            aria-pressed={highRiskOnly}
            onClick={() => setHighRiskOnly(!highRiskOnly)}
          >
            {highRiskOnly ? "Show all nodes" : "Show High Risk Nodes Only"}
          </Button>
          <p className="graph-count">
            Showing {visibleNodes.length} of {graph.nodes.length} nodes
            {" · "}
            {highRiskCount} high risk
          </p>
        </div>
        <GraphGrid nodes={visibleNodes} />
      </Card>
    </main>
  )
}

export default GraphView