import fs from 'fs'

const nodes = []
const edges = []
for (let i = 0; i < 1000; i++) {
  nodes.push({
    id: `n${i}`,
    label: `Sheet1!C${i + 1}`,
    formula: `=A${i + 1}*B${i + 1}`,
    risk: i % 97 === 0 && i > 0 ? 'high' : 'normal',
    note: i % 97 === 0 && i > 0 ? 'Hardcoded value typed over formula' : '',
  })
  if (i > 0) {
    edges.push({ source: `n${Math.floor((i - 1) / 3)}`, target: `n${i}`, kind: 'formula' })
  }
  if (i % 50 === 0 && i > 0) {
    edges.push({ source: 'n0', target: `n${i}`, kind: 'vba' })
  }
}
fs.mkdirSync('public', { recursive: true })
fs.writeFileSync('public/dag_graph.json', JSON.stringify({ nodes, edges }))
console.log('done')