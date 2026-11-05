import "./RiskGauge.css"

/**
 * Circular gauge showing a risk score out of a maximum (default 100).
 * Colour changes with the score: low, medium or high.
 */
function RiskGauge({ score = 0, max = 100 }) {
  const radius = 54
  const circumference = 2 * Math.PI * radius
  const pct = Math.min(Math.max(score / max, 0), 1)
  const offset = circumference * (1 - pct)
  const level = score >= 70 ? "high" : score >= 40 ? "medium" : "low"

  return (
    <div
      className={`gauge gauge-${level}`}
      role="img"
      aria-label={`Risk score ${score} out of ${max}`}
    >
      <svg viewBox="0 0 140 140" className="gauge-svg">
        <circle className="gauge-track" cx="70" cy="70" r={radius} />
        <circle
          className="gauge-value"
          cx="70"
          cy="70"
          r={radius}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform="rotate(-90 70 70)"
        />
      </svg>
      <div className="gauge-label">
        <span className="gauge-score">{score}</span>
        <span className="gauge-max">/{max}</span>
      </div>
    </div>
  )
}

export default RiskGauge