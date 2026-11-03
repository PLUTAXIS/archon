import "./Badge.css"

function Badge({ level = "low", children }) {
  return <span className={`badge badge-${level}`}>{children}</span>
}

export default Badge