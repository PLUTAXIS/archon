import { useEffect, useRef, useState } from 'react'
import './App.css'
import DependencyMap from './components/DependencyMap'

const API_BASE = (
  import.meta.env.VITE_API_BASE_URL ||
  'https://archon-api-rd8c.onrender.com'
).replace(/\/+$/, '')

const MAX_FILE_BYTES = 20 * 1024 * 1024

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

function Icon({ name, size = 20 }) {
  const common = {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.8,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    'aria-hidden': true,
  }

  if (name === 'upload') return <svg {...common}><path d="M12 16V4m0 0L7 9m5-5 5 5" /><path d="M20 16.5v2A1.5 1.5 0 0 1 18.5 20h-13A1.5 1.5 0 0 1 4 18.5v-2" /></svg>
  if (name === 'file') return <svg {...common}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6M8 13h8M8 17h8" /></svg>
  if (name === 'check') return <svg {...common}><path d="m5 12 4 4L19 6" /></svg>
  if (name === 'arrow') return <svg {...common}><path d="M5 12h14m-6-6 6 6-6 6" /></svg>
  if (name === 'sheet') return <svg {...common}><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M3 9h18M9 3v18M15 9v12" /></svg>
  if (name === 'activity') return <svg {...common}><path d="M3 12h4l3-8 4 16 3-8h4" /></svg>
  if (name === 'alert') return <svg {...common}><path d="M12 9v4m0 4h.01" /><path d="M10.3 3.9 2.5 18a2 2 0 0 0 1.7 3h15.6a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" /></svg>
  return <svg {...common}><circle cx="12" cy="12" r="9" /></svg>
}

const FLAG_TEXT = {
  APPROX_LOOKUP_DEFAULT: 'Lookup falls back to approximate match because no match type is given',
  APPROX_LOOKUP: 'Lookup uses approximate match',
  ERROR_SUPPRESSED: 'Errors are hidden and replaced with a fixed value',
  VOLATILE_FUNCTION: 'Recalculates on every change',
  EMBEDDED_CONSTANT: 'Business number typed into the formula, not an input cell',
  RUNNING_BALANCE: 'Running balance: one wrong row carries forward',
  UNVERIFIED_FORMULA: 'Not explained yet',
}

function flagText(flag) {
  const levels = flag.match(/^NESTED_IF_DEPTH_(\d+)$/)
  if (levels) return `${levels[1]} nested IF levels`
  return FLAG_TEXT[flag] ?? flag
}

function ScoreCard({ card }) {
  return (
    <div className="result-block scorecard">
      <div className="scorecard-total">
        <span className="scorecard-label">Workbook risk</span>
        <strong>{card.score}<small>/100</small></strong>
        <span className={`scorecard-band band-${card.band.toLowerCase()}`}>{card.band}</span>
      </div>
      <div className="scorecard-axes">
        {card.axes.map((axis) => (
          <div className="scorecard-axis" key={axis.id}>
            <div className="scorecard-axis-head">
              <span>{axis.title} <small>· weight {axis.weight}%</small></span>
              <strong>{axis.score}</strong>
            </div>
            <div className="scorecard-bar" role="img" aria-label={`${axis.title}: ${axis.score} out of 100`}>
              <span style={{ width: `${axis.score}%` }} />
            </div>
            {axis.contributions.length > 0 ? (
              <ul>
                {axis.contributions.map((c) => (
                  <li key={c.signal}>{c.label[0].toUpperCase() + c.label.slice(1)}: {c.count} <span>+{c.points}</span></li>
                ))}
                {axis.capped && <li className="scorecard-capped">Capped at 100</li>}
              </ul>
            ) : <p>Nothing found.</p>}
          </div>
        ))}
      </div>
    </div>
  )
}

const MACRO_FINDING = {
  error_suppression: { title: 'Errors are silenced', detail: 'After this line, failures are skipped without warning.' },
  overwrites_formula: { title: 'Macro overwrites a formula', detail: 'Running the macro replaces a calculation with a fixed value.' },
  dynamic_write: { title: 'Writes to a cell chosen at run time', detail: 'Which cell changes cannot be known without running the macro.' },
}

function MacroFindings({ findings }) {
  return (
    <div className="result-block">
      <div className="block-heading"><h4>Macro findings</h4><span>{findings.length} found</span></div>
      <div className="explain-list">
        {findings.map((f, i) => (
          <div className="explain-row" key={`${f.kind}-${f.module}-${f.procedure}-${f.line ?? f.cell}-${i}`}>
            <div className="explain-meta">
              <strong>{MACRO_FINDING[f.kind]?.title ?? f.kind}</strong>
              <code>{f.module} · {f.procedure}{f.line ? `, line ${f.line}` : ''}{f.cell ? ` · ${f.cell}` : ''}</code>
            </div>
            <p className="explain-flags">{MACRO_FINDING[f.kind]?.detail}{f.reason ? ` (${f.reason})` : ''}</p>
            <code className="spec-formula">{f.text}</code>
          </div>
        ))}
      </div>
    </div>
  )
}

const VERDICT_TEXT = { logic: 'Intended calculation', error: 'Error to fix' }

// Reviewer verdicts are kept in this browser, per workbook, so re-uploading
// the same file restores them. Storage can be unavailable; the page still works.
function loadVerdicts(key) {
  try {
    return JSON.parse(localStorage.getItem(key) ?? '{}')
  } catch {
    return {}
  }
}

function CycleReview({ cycles, workbookId }) {
  const storageKey = `archon:cycle-verdicts:${workbookId}`
  const [verdicts, setVerdicts] = useState(() => loadVerdicts(storageKey))
  const reviewed = cycles.filter((c) => verdicts[c.members.join('|')]).length

  function decide(id, verdict) {
    const next = { ...verdicts }
    if (next[id] === verdict) delete next[id]
    else next[id] = verdict
    setVerdicts(next)
    try {
      localStorage.setItem(storageKey, JSON.stringify(next))
    } catch {
      // storage blocked: the verdict still shows for this session
    }
  }

  return (
    <div className="result-block">
      <div className="block-heading">
        <h4>Circular references</h4>
        <span>{reviewed} of {cycles.length} reviewed</span>
      </div>
      <div className="explain-list">
        {cycles.map((c) => {
          const id = c.members.join('|')
          const verdict = verdicts[id]
          return (
            <div className="explain-row cycle-row" key={id}>
              <div className="explain-meta">
                <code>{c.members.join(' → ')}</code>
                {verdict && <span className={`cycle-verdict cycle-verdict--${verdict}`}>Reviewed: {VERDICT_TEXT[verdict]}</span>}
              </div>
              <p className="explain-flags">
                Suggested: {c.suggested_classification === 'logic' ? 'intended calculation' : 'error'} ({c.reason})
              </p>
              <div className="cycle-actions no-print" role="group" aria-label={`Verdict for ${c.members.join(', ')}`}>
                {Object.entries(VERDICT_TEXT).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    className={`text-button${verdict === value ? ' is-selected' : ''}`}
                    aria-pressed={verdict === value}
                    onClick={() => decide(id, value)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function AuditReport({ analysis }) {
  const { summary, bugs, cycles, report, graph, scorecard } = analysis
  const [focus, setFocus] = useState(null)
  const mapRef = useRef(null)
  const section = (kind) => report.sections.find((s) => s.kind === kind)?.entries ?? []
  const risky = section('risk')
  const explained = section('explanations')
  const unverified = section('unverified_appendix')

  return (
    <>
      {scorecard && <ScoreCard card={scorecard} />}

      <div className="metric-grid">
        <div className="metric-card">
          <span className="metric-icon"><Icon name="activity" size={18} /></span>
          <strong>{summary.clusters.toLocaleString()}</strong>
          <span>Logic blocks ({summary.compression_ratio.toFixed(1)}× compression)</span>
        </div>
        <div className="metric-card">
          <span className="metric-icon"><Icon name="alert" size={18} /></span>
          <strong>{summary.override_bugs}</strong>
          <span>Hardcoded overrides</span>
        </div>
        <div className="metric-card">
          <span className="metric-icon"><Icon name="alert" size={18} /></span>
          <strong>{summary.cycles}</strong>
          <span>Circular references</span>
        </div>
      </div>

      <div className="result-block">
        <div className="block-heading"><h4>Critical findings: bug ledger</h4><span>{bugs.length} found</span></div>
        {bugs.length ? (
          <div className="table-wrap">
            <table>
              <thead><tr><th>ID</th><th>Cell</th><th>Typed value</th><th>Expected formula (R1C1)</th><th>Cells affected</th><th>Severity</th><th className="no-print"><span className="sr-only">Map</span></th></tr></thead>
              <tbody>
                {bugs.map((b) => (
                  <tr key={b.bug_id}>
                    <td>{b.bug_id}</td>
                    <td><code>{b.sheet}!{b.address}</code></td>
                    <td><code>{String(b.observed)}</code></td>
                    <td><code>{b.expected_r1c1}</code></td>
                    <td title={b.downstream_sample.join(', ')}>{b.downstream_node_count}</td>
                    <td>
                      <strong>{b.severity}/5</strong>
                      {b.severity_reasons?.length > 0 && (
                        <ul className="sev-reasons">{b.severity_reasons.map((r) => <li key={r}>{r}</li>)}</ul>
                      )}
                    </td>
                    <td className="no-print">
                      <button
                        className="text-button"
                        type="button"
                        onClick={() => { setFocus(`${b.sheet}!${b.address}`); mapRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }) }}
                      >
                        Show on map
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p className="empty-state">No hardcoded values found inside copied formula ranges.</p>}
      </div>

      <div className="result-block no-print" ref={mapRef}>
        <div className="block-heading">
          <h4>Dependency map</h4>
          <span>{graph.stats.nodes_out.toLocaleString()} blocks from {graph.stats.cells_in.toLocaleString()} cells · click a block for its formula</span>
        </div>
        <DependencyMap graph={graph} bugs={bugs} focus={focus} onFocus={setFocus} />
      </div>

      {cycles.length > 0 && <CycleReview cycles={cycles} workbookId={graph.workbook_id} />}

      {analysis.vba_findings?.length > 0 && <MacroFindings findings={analysis.vba_findings} />}

      <div className="result-block">
        <div className="block-heading"><h4>Risky formulas</h4><span>{risky.length} flagged · highest first</span></div>
        {risky.length ? (
          <div className="explain-list">
            {risky.map((e) => (
              <div className="explain-row" key={e.node_id}>
                <div className="explain-meta"><strong>{e.risk_score}/100</strong><code>{e.node_id}</code></div>
                <p className="explain-flags">{e.risk_flags.map(flagText).join(' · ')}</p>
                <p>{e.plain_english}</p>
              </div>
            ))}
          </div>
        ) : <p className="empty-state">No risky formula patterns found.</p>}
      </div>

      <div className="result-block">
        <div className="block-heading"><h4>What the formulas do</h4><span>{explained.length} explained · {unverified.length} unverified</span></div>
        {explained.length ? (
          <div className="explain-list">
            {explained.map((e) => (
              <div className="explain-row" key={e.node_id}>
                <div className="explain-meta"><code>{e.node_id}</code></div>
                <p>{e.plain_english}</p>
              </div>
            ))}
          </div>
        ) : <p className="empty-state">No formulas matched a known pattern yet.</p>}
        {unverified.length > 0 && (
          <p className="result-footnote">
            Not explained (no known pattern, shown rather than guessed): {unverified.map((e) => e.node_id).join(', ')}
          </p>
        )}
      </div>

      {analysis.spec && <Specification spec={analysis.spec} />}
    </>
  )
}

function Specification({ spec }) {
  const total = spec.sheets.reduce((n, s) => n + s.calculations.length, 0)
  const ref = useRef(null)

  // The printed audit pack always includes the full specification.
  useEffect(() => {
    const open = () => ref.current?.setAttribute('open', '')
    window.addEventListener('beforeprint', open)
    return () => window.removeEventListener('beforeprint', open)
  }, [])

  return (
    <details className="result-block spec" ref={ref}>
      <summary className="block-heading">
        <h4>Specification</h4>
        <span>{spec.sheets.length} sheets · {total} calculations · in dependency order</span>
      </summary>
      {spec.sheets.map((sheet) => (
        <section className="spec-sheet" key={sheet.name}>
          <h5>{sheet.name}</h5>
          {sheet.inputs.length > 0 && (
            <>
              <h6>Inputs</h6>
              <ul className="spec-inputs">
                {sheet.inputs.map((i) => (
                  <li key={i.id}>
                    <strong>{i.label ?? i.id}</strong> <code>{i.id}</code> · {i.cells} cell{i.cells === 1 ? '' : 's'}
                    {i.used_by.length > 0 && <> · used by {i.used_by.join(', ')}</>}
                  </li>
                ))}
              </ul>
            </>
          )}
          {sheet.calculations.length > 0 && (
            <>
              <h6>Calculations</h6>
              <ol className="spec-calcs">
                {sheet.calculations.map((c) => (
                  <li key={c.id} className={c.kind === 'override' ? 'spec-override' : undefined}>
                    <div className="spec-head">
                      <strong>{c.label ?? c.id}</strong>
                      <code>{c.cells.join(', ')}</code>
                      {c.is_output && <span className="spec-tag">Output</span>}
                      {c.risk_score > 0 && <span className="spec-tag spec-risk">Risk {c.risk_score}</span>}
                    </div>
                    <p>{c.explanation ?? 'Not explained yet: no verified pattern matches this formula.'}</p>
                    {c.formula && <code className="spec-formula">{c.formula}</code>}
                    {c.depends_on.length > 0 && <p className="spec-links">Uses {c.depends_on.join(', ')}</p>}
                  </li>
                ))}
              </ol>
            </>
          )}
        </section>
      ))}
      {spec.macros.length > 0 && (
        <section className="spec-sheet">
          <h5>Macros that write to the workbook</h5>
          <ul className="spec-inputs">
            {spec.macros.map((m) => (
              <li key={m.procedure}>
                <strong>{m.procedure}</strong>
                {m.reads_from?.length > 0 && <> reads {m.reads_from.join(', ')};</>}
                {m.writes_to.length > 0 ? <> writes to {m.writes_to.join(', ')}</> : <> writes nothing traceable</>}
              </li>
            ))}
          </ul>
        </section>
      )}
    </details>
  )
}

function ExtractSummary({ extract, summary }) {
  const hidden = extract.sheets.filter((s) => s.visibility !== 'visible')
  // very hidden sheets already appear in `hidden`; don't list them twice
  const warnings = extract.exceptions.filter((w) => w.code !== 'E_VERY_HIDDEN_SHEET')
  return (
    <>
      <div className="metric-grid">
        <div className="metric-card">
          <span className="metric-icon"><Icon name="sheet" size={18} /></span>
          <strong>{extract.sheets.length}</strong>
          <span>Worksheets{hidden.length ? ` (${hidden.length} hidden)` : ''}</span>
        </div>
        <div className="metric-card">
          <span className="metric-icon"><span className="fx-small">ƒx</span></span>
          <strong>{extract.formula_count.toLocaleString()}</strong>
          <span>Formulas in {extract.cell_count.toLocaleString()} cells</span>
        </div>
        <div className="metric-card">
          <span className="metric-icon"><Icon name="file" size={18} /></span>
          <strong>{extract.vba_modules.length}</strong>
          <span>VBA modules{summary.vba_dynamic_writes ? ` · ${summary.vba_dynamic_writes} untraceable writes` : ''}</span>
        </div>
      </div>

      {(hidden.length > 0 || warnings.length > 0) && (
        <div className="result-block">
          <div className="block-heading"><h4>File-level findings</h4><span>{hidden.length + warnings.length} flagged</span></div>
          <div className="formula-list">
            {hidden.map((s) => (
              <div className="formula-row" key={`sheet-${s.name}`}>
                <div className="formula-location"><strong>{s.visibility === 'veryHidden' ? 'Very hidden sheet' : 'Hidden sheet'}</strong><span>{s.dimensions}</span></div>
                <code>{s.name}</code>
              </div>
            ))}
            {warnings.map((w, i) => (
              <div className="formula-row" key={`warn-${i}`}>
                <div className="formula-location"><strong>{w.code}</strong><span>{w.detail}</span></div>
                <code>{w.sheet ?? ''}</code>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  )
}

function App() {
  const inputRef = useRef(null)
  const [file, setFile] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [status, setStatus] = useState('idle')
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  function chooseFile(nextFile) {
    if (!nextFile) return

    setResult(null)
    setError('')

    if (!/\.(xlsx|xlsm)$/i.test(nextFile.name)) {
      setFile(null)
      setStatus('error')
      setError('Please select an Excel workbook (.xlsx or .xlsm).')
      return
    }

    if (nextFile.size > MAX_FILE_BYTES) {
      setFile(null)
      setStatus('error')
      setError('This file exceeds the 20 MB upload limit.')
      return
    }

    if (nextFile.size === 0) {
      setFile(null)
      setStatus('error')
      setError('This file is empty. Choose another workbook.')
      return
    }

    setFile(nextFile)
    setStatus('idle')
  }

  async function uploadWorkbook() {
    if (!file || status === 'uploading') return

    setStatus('uploading')
    setError('')
    setResult(null)

    try {
      const formData = new FormData()
      formData.append('file', file)

      const response = await fetch(`${API_BASE}/audit`, {
        method: 'POST',
        body: formData,
      })

      const data = await response.json().catch(() => ({}))

      if (!response.ok) {
        throw new Error(data.detail || `Upload failed (${response.status}).`)
      }

      setResult(data)
      setStatus('success')
    } catch (err) {
      setError(
        err instanceof TypeError
          ? 'Could not connect to ARCHON. Please check your connection and try again.'
          : err.message || 'Something went wrong. Please try again.'
      )
      setStatus('error')
    }
  }

  function reset() {
    setFile(null)
    setResult(null)
    setError('')
    setStatus('idle')
    if (inputRef.current) inputRef.current.value = ''
  }

  function handleDrop(event) {
    event.preventDefault()
    setDragging(false)
    chooseFile(event.dataTransfer.files?.[0])
  }

  return (
    <div className="site-shell">
      <header className="topbar">
        <a className="brand" href="#" aria-label="ARCHON home">
          <span className="brand-mark">A</span>
          <span>ARCHON</span>
        </a>

        <nav className="top-nav" aria-label="Main navigation">
          <a href="#how-it-works">How it works</a>
          <a href="https://archon-api-rd8c.onrender.com/docs" target="_blank" rel="noreferrer">API docs</a>
          <a className="nav-cta" href="#workspace">Open workspace <Icon name="arrow" size={15} /></a>
        </nav>
      </header>

      <main>
        <section className="hero">
          <div className="hero-copy">
            <div className="eyebrow"><span className="status-dot" /> WORKBOOK EXTRACTION, SIMPLIFIED</div>
            <h1>See what’s<br />inside your <span>workbook.</span></h1>
            <p className="hero-description">
              Bring your Excel workbooks into focus. ARCHON extracts worksheet
              structure and formulas into one clear, readable view.
            </p>
            <a className="primary-link" href="#workspace">
              Explore your workbook <Icon name="arrow" size={18} />
            </a>
            <div className="hero-note">
              <Icon name="check" size={15} />
              .xlsx and .xlsm up to 20 MB
              <span className="note-divider" />
              No spreadsheet edits
            </div>
          </div>

          <div className="hero-art" aria-label="Illustration of a workbook and extracted data">
            <div className="orbit orbit-one" />
            <div className="orbit orbit-two" />
            <div className="float-card float-card-top">
              <span className="mini-icon"><Icon name="sheet" size={17} /></span>
              <span><strong>Workbook</strong><small>Structure detected</small></span>
              <span className="tiny-check"><Icon name="check" size={13} /></span>
            </div>
            <div className="visual-sheet">
              <div className="sheet-top"><span /><span /><span /></div>
              <div className="sheet-title">Revenue overview</div>
              <div className="sheet-grid">
                {Array.from({ length: 20 }, (_, index) => (
                  <span key={index} className={index === 13 ? 'cell-highlight' : ''}>
                    {['', 'A', 'B', 'C', 'D'][index % 5]}
                  </span>
                ))}
              </div>
              <div className="sheet-formula"><span>fx</span> =SUM(B2:B8)</div>
            </div>
            <div className="float-card float-card-bottom">
              <span className="formula-symbol">ƒx</span>
              <span><strong>Formula found</strong><small>Extraction complete</small></span>
              <span className="tiny-check"><Icon name="check" size={13} /></span>
            </div>
            <div className="hero-glow" />
          </div>
        </section>

        <section className="workspace-section" id="workspace">
          <div className="section-heading">
            <div>
              <div className="eyebrow">YOUR WORKSPACE</div>
              <h2>Start with a workbook.</h2>
              <p>Upload an Excel file to extract its structure and formulas.</p>
            </div>
            <div className="workspace-badge"><span className="status-dot" /> API operational</div>
          </div>

          <div className="workspace-card">
            <div
              className={`dropzone ${dragging ? 'is-dragging' : ''} ${file ? 'has-file' : ''}`}
              onDragOver={(event) => { event.preventDefault(); setDragging(true) }}
              onDragLeave={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget)) setDragging(false)
              }}
              onDrop={handleDrop}
            >
              <input
                ref={inputRef}
                className="file-input"
                type="file"
                accept=".xlsx,.xlsm,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel.sheet.macroEnabled.12"
                onChange={(event) => chooseFile(event.target.files?.[0])}
                aria-label="Choose an Excel workbook"
              />

              <div className="upload-icon"><Icon name="upload" size={25} /></div>
              <h3>{file ? file.name : 'Drop your Excel workbook here'}</h3>
              <p>{file ? `${formatBytes(file.size)} · Ready to extract` : 'or choose a file from your device'}</p>
              <button className="browse-button" type="button" onClick={() => inputRef.current?.click()}>
                {file ? 'Choose another file' : 'Browse files'}
              </button>
              <div className="file-hint">SUPPORTED: .XLSX, .XLSM <span>•</span> MAXIMUM SIZE: 20 MB</div>
            </div>

            {file && status !== 'success' && (
              <div className="selected-file">
                <div className="selected-file-icon"><Icon name="file" size={19} /></div>
                <div className="selected-file-info">
                  <strong>{file.name}</strong>
                  <span>{formatBytes(file.size)} · Excel workbook</span>
                </div>
                <button className="text-button" type="button" onClick={reset} disabled={status === 'uploading'}>Remove</button>
              </div>
            )}

            {file && status !== 'success' && (
              <button className="analyze-button" type="button" onClick={uploadWorkbook} disabled={status === 'uploading'}>
                {status === 'uploading' ? (
                  <><span className="spinner" /> Auditing workbook...</>
                ) : (
                  <>Audit workbook <Icon name="arrow" size={18} /></>
                )}
              </button>
            )}

            {status === 'error' && (
              <div className="message error-message" role="alert">
                <Icon name="alert" size={18} />
                <span>{error}</span>
              </div>
            )}

            {status === 'success' && result && (
              <div className="results" aria-live="polite">
                <div className="result-heading">
                  <div>
                    <div className="success-label"><Icon name="check" size={15} /> AUDIT COMPLETE</div>
                    <h3>{result.filename}</h3>
                    <p>Formulas, dependencies and VBA macros analysed.</p>
                  </div>
                  <div className="result-actions no-print">
                    <button className="text-button" type="button" onClick={() => window.print()}>Download PDF</button>
                    <button className="text-button" type="button" onClick={reset}>New workbook</button>
                  </div>
                </div>

                <ExtractSummary extract={result.analysis.extract} summary={result.analysis.summary} />

                <AuditReport analysis={result.analysis} />

                {result.limitations?.length > 0 && (
                  <div className="limitations">
                    <strong>Current scope</strong>
                    <p>{result.limitations.join(' ')}</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </section>

        <section className="how-section" id="how-it-works">
          <div className="eyebrow">SIMPLE BY DESIGN</div>
          <h2>From file to clarity in three steps.</h2>
          <div className="steps-grid">
            <article className="step-card">
              <span className="step-number">01</span>
              <div className="step-icon"><Icon name="upload" size={22} /></div>
              <h3>Upload</h3>
              <p>Select an .xlsx or .xlsm workbook from your device. Your original file stays unchanged.</p>
            </article>
            <article className="step-card">
              <span className="step-number">02</span>
              <div className="step-icon"><Icon name="activity" size={22} /></div>
              <h3>Extract</h3>
              <p>ARCHON reads worksheet structure, scans cells, and collects formula samples.</p>
            </article>
            <article className="step-card">
              <span className="step-number">03</span>
              <div className="step-icon"><Icon name="file" size={22} /></div>
              <h3>Review</h3>
              <p>See worksheet dimensions, scan totals, and extracted formulas in one place.</p>
            </article>
          </div>
        </section>
      </main>

      <footer className="footer">
        <a className="brand footer-brand" href="#"><span className="brand-mark">A</span><span>ARCHON</span></a>
        <p>Workbook clarity starts here.</p>
        <span className="footer-status"><span className="status-dot" /> Extraction API online</span>
      </footer>
    </div>
  )
}

export default App
