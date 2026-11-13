import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import Card from "../components/Card"
import Button from "../components/Button"
import GraphGrid from "../components/GraphGrid"
import { fetchGraph, normalizeGraph } from "../api/graph"
import { useGraphFilter } from "../hooks/useGraphFilter"
import "./GraphView.css"

const NO_NODES = []

/**
 * Risk graph page with a one-click "high risk only" filter.
 * Graph data comes from the API layer, or from a file chosen by the user.
 */
function GraphView() {
  const [nodes, setNodes] = useState(null)
  const [error, setError] = useState("")

  useEffect(() => {
    let cancelled = false
    fetchGraph()
      .then((graph) => {
        if (!cancelled) setNodes(graph.nodes)
      })
      .catch((e) => {
        if (!cancelled) setError(e.message)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const { visibleNodes, highRiskCount, highRiskOnly, setHighRiskOnly } =
    useGraphFilter(nodes ?? NO_NODES)

  function handleFile(e) {
    const file = e.target.files[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      try {
        setNodes(normalizeGraph(JSON.parse(reader.result)).nodes)
        setError("")
      } catch {
        setError("That file could not be read as a graph.")
      }
    }
    reader.readAsText(file)
  }

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
            disabled={!nodes}
          >
            {highRiskOnly ? "Show all nodes" : "Show High Risk Nodes Only"}
          </Button>
          <label className="graph-file">
            Load graph file{" "}
            <input type="file" accept=".json" onChange={handleFile} />
          </label>
        </div>

        {error && (
          <p className="graph-error" role="alert">
            {error}
          </p>
        )}

        {!nodes && !error && <p>Loading graph…</p>}

        {nodes && (
          <>
            <p className="graph-count">
              Showing {visibleNodes.length} of {nodes.length} nodes
              {" · "}
              {highRiskCount} high risk
            </p>
            <GraphGrid nodes={visibleNodes} />
          </>
        )}
      </Card>
    </main>
  )
}

export default GraphView