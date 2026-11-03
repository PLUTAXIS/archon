import Button from "./components/Button"
import Card from "./components/Card"
import Badge from "./components/Badge"

function App() {
  return (
    <main style={{ maxWidth: 720, margin: "40px auto", padding: "0 16px" }}>
      <Card title="Critical Findings">
        <p>
          <Badge level="high">High risk</Badge>{" "}
          <Badge level="medium">Medium</Badge>{" "}
          <Badge level="low">Low</Badge>
        </p>
        <Button>Download PDF</Button>{" "}
        <Button variant="secondary">View details</Button>
      </Card>
    </main>
  )
}

export default App