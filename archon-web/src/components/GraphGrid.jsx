import "./GraphGrid.css"

/**
 * Shows each graph node as a small colored cell labelled with its cell name.
 */
function GraphGrid({ nodes }) {
  return (
    <ul className="graph-grid">
      {nodes.map((n) => (
        <li
          key={n.id}
          className={`graph-node graph-node-${n.risk}`}
          title={`${n.label}: ${n.risk} risk`}
        >
          {n.label}
        </li>
      ))}
    </ul>
  )
}

export default GraphGrid