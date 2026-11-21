import { useEffect, useMemo, useState } from 'react'
import ReactFlow, { Background, Controls, Position, ReactFlowProvider, useReactFlow } from 'reactflow'
import 'reactflow/dist/style.css'

const COL_W = 250
const ROW_H = 72

// Left-to-right layers by longest path from an input; cycles are cut where first revisited.
function layout(nodes, edges) {
  const preds = new Map(nodes.map((n) => [n.id, []]))
  edges.forEach((e) => preds.get(e.target)?.push(e.source))
  const depth = new Map()
  const visiting = new Set()
  const depthOf = (id) => {
    if (depth.has(id)) return depth.get(id)
    if (visiting.has(id)) return 0
    visiting.add(id)
    const d = preds.get(id).reduce((m, p) => Math.max(m, depthOf(p) + 1), 0)
    visiting.delete(id)
    depth.set(id, d)
    return d
  }
  const layers = new Map()
  nodes.forEach((n) => {
    const d = depthOf(n.id)
    layers.set(d, [...(layers.get(d) ?? []), n.id])
  })
  const pos = new Map()
  layers.forEach((ids, d) => ids.sort().forEach((id, i) => pos.set(id, { x: d * COL_W, y: i * ROW_H })))
  return pos
}

// Every node reachable from start: the blast radius of a bug.
function downstreamOf(start, edges) {
  const next = new Map()
  edges.forEach((e) => next.set(e.source, [...(next.get(e.source) ?? []), e.target]))
  const seen = new Set([start])
  const queue = [start]
  while (queue.length) {
    for (const n of next.get(queue.shift()) ?? []) {
      if (!seen.has(n)) { seen.add(n); queue.push(n) }
    }
  }
  return seen
}

function kindOf(node, bugIds) {
  if (bugIds.has(node.id)) return 'bug'
  if (node.id.startsWith('VBA')) return 'vba'
  return node.kind
}

function label(node) {
  const title = node.header ? `${node.header}` : node.id
  const sub = node.kind === 'cluster'
    ? `${node.id} · ×${node.member_count}`
    : node.kind === 'input' && node.member_count ? `${node.member_count} input cells` : node.anchor
  return (
    <div className="map-node-label">
      <strong>{title}</strong>
      <span>{sub}</span>
    </div>
  )
}

function FlowMap({ graph, bugIds, focus, onSelect }) {
  const { fitView } = useReactFlow()
  const positions = useMemo(() => layout(graph.nodes, graph.edges), [graph])
  const reach = useMemo(() => (focus ? downstreamOf(focus, graph.edges) : null), [focus, graph])

  const nodes = useMemo(() => graph.nodes.map((n) => {
    const kind = kindOf(n, bugIds)
    const dim = reach && !reach.has(n.id)
    const risky = (n.risk?.score ?? 0) > 0
    return {
      id: n.id,
      position: positions.get(n.id),
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      data: { label: label(n) },
      className: `map-node map-node--${kind}${risky ? ' map-node--risky' : ''}${n.id === focus ? ' map-node--focus' : ''}${dim ? ' map-node--dim' : ''}`,
    }
  }), [graph, positions, bugIds, reach, focus])

  const edges = useMemo(() => graph.edges.map((e) => {
    const hot = reach && reach.has(e.source) && reach.has(e.target)
    return {
      id: `${e.source}->${e.target}`,
      source: e.source,
      target: e.target,
      animated: Boolean(hot),
      className: `map-edge map-edge--${e.origin}${hot ? ' map-edge--hot' : ''}${reach && !hot ? ' map-edge--dim' : ''}`,
    }
  }), [graph, reach])

  useEffect(() => {
    const ids = reach ? [...reach] : graph.nodes.map((n) => n.id)
    // wait a tick so freshly highlighted nodes are measured before framing them
    const t = setTimeout(() => fitView({ nodes: ids.map((id) => ({ id })), padding: 0.2, duration: 400 }), 60)
    return () => clearTimeout(t)
  }, [reach, graph, fitView])

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodeClick={(_, n) => onSelect(n.id)}
      onPaneClick={() => onSelect(null)}
      nodesConnectable={false}
      fitView
      minZoom={0.05}
      proOptions={{ hideAttribution: true }}
    >
      <Background gap={24} size={1} />
      <Controls showInteractive={false} />
    </ReactFlow>
  )
}

export default function DependencyMap({ graph, focus, onFocus }) {
  const bugIds = useMemo(() => new Set(graph.bugs.map((b) => `${b.sheet}!${b.address}`)), [graph])
  const [selected, setSelected] = useState(null)
  const picked = graph.nodes.find((n) => n.id === (selected ?? focus))
  const reachCount = focus ? downstreamOf(focus, graph.edges).size - 1 : 0

  function select(id) {
    setSelected(id)
    onFocus(id)
  }

  return (
    <div className="map-wrap">
      <div className="map-legend">
        <span className="map-key map-key--cluster">Logic block</span>
        <span className="map-key map-key--input">Inputs</span>
        <span className="map-key map-key--bug">Hardcoded override</span>
        <span className="map-key map-key--vba">VBA macro</span>
        {focus && (
          <button className="text-button" type="button" onClick={() => select(null)}>
            Clear highlight ({reachCount} downstream)
          </button>
        )}
      </div>
      <div className="map-canvas">
        <ReactFlowProvider>
          <FlowMap graph={graph} bugIds={bugIds} focus={focus} onSelect={select} />
        </ReactFlowProvider>
      </div>
      {picked && (
        <div className="map-detail">
          <strong>{picked.header ? `${picked.header} · ` : ''}{picked.id}</strong>
          {picked.r1c1 && <code>{picked.r1c1}</code>}
          {picked.member_ranges && <span>Cells: {picked.member_ranges.join(', ')}</span>}
          {picked.risk?.score > 0 && <span>Risk {picked.risk.score}/100: {picked.risk.flags.join(', ')}</span>}
        </div>
      )}
    </div>
  )
}
