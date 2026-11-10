# Design rules

- All colors, spacing, fonts and shadows come from src/styles/tokens.css. Do not hard-code them in components.
- Shared pieces live in src/components: Button, Card, Badge, TextField, RiskGauge, CriticalFindings, GraphGrid.
- Risk levels are always "high", "medium" or "low", shown red, amber and green.
- New client branding: change the values in tokens.css (for example --color-primary). No component edits needed.
- Anything hidden on paper gets the class no-print. Print rules are in src/styles/print.css.
- All backend calls go through src/api. Pages never call fetch directly.