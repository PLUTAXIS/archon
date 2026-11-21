import { useEffect, useMemo, useState } from 'react'
import ReactFlow, { Background, Controls, Position, ReactFlowProvider, useReactFlow } from 'reactflow'
import 'reactflow/dist/style.css'

const COL_W = 250
const ROW_H = 72
const LAYERS_PER_ROW = 8 // a longer chain wraps onto a new band instead of a thin endless strip
const LAYERS_PER_ROW_NARROW = 2 // phones: wrap sooner so blocks stay legible
const NARROW = '(max-width: 650px)'
const GAP = 60

// Left-to-right layers by longest path from an input (cycles are cut where first
// revisited). Separate groups are packed into a grid, biggest first, and a chain
// longer than LAYERS_PER_ROW steps wraps, so large maps stay readable.
function layout(nodes, edges, perRow) {
  const preds = new Map(nodes.map((n) => [n.id, []]))
  const links = new Map(nodes.map((n) => [n.id, []]))
  edges.forEach((e) => {
    if (!links.has(e.source) || !links.has(e.target)) return
    preds.get(e.target).push(e.source)
    links.get(e.source).push(e.target)
    links.get(e.target).push(e.source)
  })
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
  // connected groups, in a stable order: biggest first, then by first id
  const seen = new Set()
  const groups = []
  for (const id of nodes.map((n) => n.id).sort()) {
    if (seen.has(id)) continue
    const group = []
    const queue = [id]
    seen.add(id)
    while (queue.length) {
      const cur = queue.shift()
      group.push(cur)
      for (const nxt of links.get(cur)) if (!seen.has(nxt)) { seen.add(nxt); queue.push(nxt) }
    }
    groups.push(group)
  }
  groups.sort((a, b) => b.length - a.length)

  const pos = new Map()
  const maxWidth = perRow * COL_W
  let x = 0
  let y = 0
  let shelf = 0
  for (const group of groups) {
    const layers = new Map()
    group.forEach((id) => {
      const d = depthOf(id)
      layers.set(d, [...(layers.get(d) ?? []), id])
    })
    const deepest = Math.max(...layers.keys())
    const tallest = Math.max(...[...layers.values()].map((ids) => ids.length))
    const band = tallest * ROW_H + GAP
    const width = Math.min(deepest + 1, perRow) * COL_W
    const height = Math.ceil((deepest + 1) / perRow) * band
    if (x > 0 && x + width > maxWidth) { x = 0; y += shelf + GAP; shelf = 0 }
    layers.forEach((ids, d) => ids.sort().forEach((id, i) => pos.set(id, {
      x: x + (d % perRow) * COL_W,
      y: y + Math.floor(d / perRow) * band + i * ROW_H,
    })))
    x += width + GAP
    shelf = Math.max(shelf, height)
  }
  return pos
}

// Every node reachable from start along the map's links.
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

function useNarrow() {
  const [narrow, setNarrow] = useState(() => window.matchMedia(NARROW).matches)
  useEffect(() => {
    const query = window.matchMedia(NARROW)
    const update = () => setNarrow(query.matches)
    query.addEventListener('change', update)
    return () => query.removeEventListener('change', update)
  }, [])
  return narrow
}

function FlowMap({ graph, bugIds, focus, reach, onSelect }) {
  const { fitView } = useReactFlow()
  const perRow = useNarrow() ? LAYERS_PER_ROW_NARROW : LAYERS_PER_ROW
  const positions = useMemo(() => layout(graph.nodes, graph.edges, perRow), [graph, perRow])

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

// Above this many blocks the map opens on the risky ones, so it stays readable.
const LARGE_GRAPH = 250

export default function DependencyMap({ graph, bugs, focus, onFocus }) {
  const bugIds = useMemo(() => new Set(graph.bugs.map((b) => `${b.sheet}!${b.address}`)), [graph])
  const [selected, setSelected] = useState(null)
  const [riskyOnly, setRiskyOnly] = useState(graph.nodes.length > LARGE_GRAPH)
  const picked = graph.nodes.find((n) => n.id === (selected ?? focus))
  // A bug highlights exactly the blocks its downstream cells live in (measured
  // on cells); any other block highlights everything downstream of it.
  const reach = useMemo(() => {
    if (!focus) return null
    const bug = bugs.find((b) => `${b.sheet}!${b.address}` === focus)
    return bug?.affected_nodes ? new Set([focus, ...bug.affected_nodes]) : downstreamOf(focus, graph.edges)
  }, [focus, bugs, graph])

  // Flagged: a risk score, an override, part of a circular reference, VBA, or unparsed.
  const flagged = useMemo(() => {
    const inCycle = new Set(graph.cycles.flatMap((c) => c.nodes))
    return new Set(graph.nodes.filter((n) => (n.risk?.score ?? 0) > 0 || bugIds.has(n.id)
      || inCycle.has(n.id) || n.id.startsWith('VBA') || n.kind === 'cell').map((n) => n.id))
  }, [graph, bugIds])

  // In risky-only mode a highlighted bug still shows everything it affects.
  const shown = useMemo(() => {
    if (!riskyOnly) return graph
    const keep = new Set(flagged)
    reach?.forEach((id) => keep.add(id))
    return {
      ...graph,
      nodes: graph.nodes.filter((n) => keep.has(n.id)),
      edges: graph.edges.filter((e) => keep.has(e.source) && keep.has(e.target)),
    }
  }, [graph, riskyOnly, flagged, reach])

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
        <button
          className={`text-button${riskyOnly ? ' is-selected' : ''}`}
          type="button"
          aria-pressed={riskyOnly}
          onClick={() => setRiskyOnly(!riskyOnly)}
        >
          {riskyOnly ? `Risky only (${shown.nodes.length} of ${graph.nodes.length})` : `Show risky only (${flagged.size})`}
        </button>
        {focus && (
          <button className="text-button" type="button" onClick={() => select(null)}>
            Clear highlight ({reach.size - 1} block{reach.size === 2 ? '' : 's'} affected)
          </button>
        )}
      </div>
      <div className="map-canvas">
        <ReactFlowProvider>
          <FlowMap graph={shown} bugIds={bugIds} focus={focus} reach={reach} onSelect={select} />
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
