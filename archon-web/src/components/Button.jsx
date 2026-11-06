import "./Button.css"
/**
 * Reusable button with a primary or secondary style variant.
 * Extra props (onClick, disabled, etc.) are passed to the button element.
 */
function Button({ children, variant = "primary", className = "", ...props }) {
  return (
    <button className={`btn btn-${variant} ${className}`.trim()} {...props}>
      {children}
    </button>
  )
}

export default Button