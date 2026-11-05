import "./Badge.css"
/**
 * Small colored pill showing a risk level: high, medium or low.
 */
function Badge({ level = "low", children }) {
  return <span className={`badge badge-${level}`}>{children}</span>
}

export default Badge