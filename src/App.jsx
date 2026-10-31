import { useEffect, useMemo, useState } from 'react'
import { ReactFlow, ReactFlowProvider, Background, Controls, useReactFlow } from '@xyflow/react'
import dagre from '@dagrejs/dagre'
import '@xyflow/react/dist/style.css'

const NODE_W = 160
const NODE_H = 40

function layout(nodes, edges) {
  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: 'LR', nodesep: 20, ranksep: 80 })
  g.setDefaultEdgeLabel(() => ({}))
  nodes.forEach(n => g.setNode(n.id, { width: NODE_W, height: NODE_H }))
  edges.forEach(e => g.setEdge(e.source, e.target))
  dagre.layout(g)
  return nodes.map(n => {
    const p = g.node(n.id)
    return { ...n, position: { x: p.x - NODE_W / 2, y: p.y - NODE_H / 2 } }
  })
}

const START_NODES = Array.from({ length: 13 }, (_, i) => ({ id: `n${i}` }))

function Map() {
  const [graph, setGraph] = useState(null)
  const [selected, setSelected] = useState(null)
  const [bugIndex, setBugIndex] = useState(-1)
  const { setCenter, fitView } = useReactFlow()

  useEffect(() => {
    fetch('/dag_graph.json').then(r => r.json()).then(setGraph)
  }, [])

  const { nodes, baseEdges, bugs } = useMemo(() => {
    if (!graph) return { nodes: [], baseEdges: [], bugs: [] }
    const rawNodes = graph.nodes.map(n => ({
      id: n.id,
      position: { x: 0, y: 0 },
      data: { label: n.label, raw: n },
      style: {
        background: n.risk === 'high' ? '#dc2626' : '#1e293b',
        color: 'white',
        border: n.risk === 'high' ? '2px solid #fecaca' : '1px solid #475569',
        boxShadow: n.risk === 'high' ? '0 0 14px 3px rgba(220,38,38,0.8)' : 'none',
        fontSize: 12,
        width: NODE_W,
        height: NODE_H,
      },
    }))
    const baseEdges = graph.edges.map((e, i) => ({
      id: `e${i}`,
      source: e.source,
      target: e.target,
      kind: e.kind,
    }))
    const laidOut = layout(rawNodes, baseEdges)
    const bugs = laidOut.filter(n => n.data.raw.risk === 'high')
    return { nodes: laidOut, baseEdges, bugs }
  }, [graph])

  const edges = useMemo(() => {
    return baseEdges.map(e => {
      const connected = selected && (e.source === selected.id || e.target === selected.id)
      const isVba = e.kind === 'vba'
      return {
        id: e.id,
        source: e.source,
        target: e.target,
        animated: isVba && connected,
        zIndex: connected ? 20 : isVba ? 5 : 0,
        style: isVba
          ? connected
            ? { stroke: '#fbbf24', strokeWidth: 5, strokeDasharray: '8 5' }
            : { stroke: '#f59e0b', strokeWidth: 1.5, strokeDasharray: '8 5', opacity: 0.3 }
          : connected
            ? { stroke: '#38bdf8', strokeWidth: 3 }
            : { stroke: '#64748b', strokeWidth: 1 },
      }
    })
  }, [baseEdges, selected])

  function jumpToNextBug() {
    if (bugs.length === 0) return
    const next = (bugIndex + 1) % bugs.length
    const b = bugs[next]
    setBugIndex(next)
    setSelected(b.data.raw)
    setCenter(b.position.x + NODE_W / 2, b.position.y + NODE_H / 2, { zoom: 1.2, duration: 800 })
  }

  function showAll() {
    setSelected(null)
    fitView({ duration: 800 })
  }

  const btn = {
    background: '#dc2626', color: 'white', border: 'none',
    padding: '8px 14px', borderRadius: 6, cursor: 'pointer',
    fontSize: 13, fontWeight: 600, marginRight: 8,
  }

  return (
    <div style={{ width: '100vw', height: '100vh', display: 'flex' }}>
      <div style={{ flex: 1, position: 'relative' }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodeClick={(_, node) => setSelected(node.data.raw)}
          onPaneClick={() => setSelected(null)}
          onlyRenderVisibleElements
          fitView
          fitViewOptions={{ nodes: START_NODES, padding: 0.3 }}
          minZoom={0.02}
        >
          <Background />
          <Controls />
        </ReactFlow>

        <div style={{
          position: 'absolute', top: 12, left: 12, zIndex: 20,
          background: '#0f172a', color: 'white', padding: 12,
          borderRadius: 8, fontSize: 13, lineHeight: 1.8,
        }}>
          <div><span style={{ background: '#dc2626', padding: '0 10px', marginRight: 8 }} /> Bug / high risk</div>
          <div><span style={{ borderTop: '3px dashed #f59e0b', display: 'inline-block', width: 28, marginRight: 8, verticalAlign: 'middle' }} /> Hidden VBA write</div>
          <div><span style={{ borderTop: '1px solid #64748b', display: 'inline-block', width: 28, marginRight: 8, verticalAlign: 'middle' }} /> Formula dependency</div>
          <div style={{ opacity: 0.7, marginTop: 4 }}>Click a node to light up its links</div>
        </div>

        <div style={{ position: 'absolute', top: 12, right: 12, zIndex: 20, textAlign: 'right' }}>
          <div style={{ background: '#0f172a', color: 'white', padding: '6px 12px', borderRadius: 6, marginBottom: 8, fontSize: 13 }}>
            {bugs.length} issues found
          </div>
          <button style={btn} onClick={jumpToNextBug}>Next bug →</button>
          <button style={{ ...btn, background: '#334155' }} onClick={showAll}>Show all</button>
        </div>
      </div>

      {selected && (
        <aside style={{ width: 340, padding: 16, background: '#0f172a', color: 'white', overflow: 'auto' }}>
          <button onClick={() => setSelected(null)}>Close</button>
          <h3>{selected.label}</h3>
          <pre style={{ whiteSpace: 'pre-wrap' }}>{selected.formula}</pre>
          {selected.risk === 'high' && <p style={{ color: '#f87171' }}>⚠ {selected.note}</p>}
        </aside>
      )}
    </div>
  )
}

export default function App() {
  return (
    <ReactFlowProvider>
      <Map />
    </ReactFlowProvider>
  )
}