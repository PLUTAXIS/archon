import { useRef, useState } from 'react'
import './App.css'

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

    if (!nextFile.name.toLowerCase().endsWith('.xlsx')) {
      setFile(null)
      setStatus('error')
      setError('Please select an Excel workbook with the .xlsx extension.')
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
              XLSX files up to 20 MB
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
                accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                onChange={(event) => chooseFile(event.target.files?.[0])}
                aria-label="Choose an Excel workbook"
              />

              <div className="upload-icon"><Icon name="upload" size={25} /></div>
              <h3>{file ? file.name : 'Drop your Excel workbook here'}</h3>
              <p>{file ? `${formatBytes(file.size)} · Ready to extract` : 'or choose a file from your device'}</p>
              <button className="browse-button" type="button" onClick={() => inputRef.current?.click()}>
                {file ? 'Choose another file' : 'Browse files'}
              </button>
              <div className="file-hint">SUPPORTED FORMAT: .XLSX <span>•</span> MAXIMUM SIZE: 20 MB</div>
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
                  <><span className="spinner" /> Extracting workbook...</>
                ) : (
                  <>Extract workbook <Icon name="arrow" size={18} /></>
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
                    <div className="success-label"><Icon name="check" size={15} /> EXTRACTION COMPLETE</div>
                    <h3>{result.filename}</h3>
                    <p>{result.scan_complete ? 'Workbook scan completed.' : 'Partial scan completed due to the scan limit.'}</p>
                  </div>
                  <button className="text-button" type="button" onClick={reset}>New workbook</button>
                </div>

                <div className="metric-grid">
                  <div className="metric-card">
                    <span className="metric-icon"><Icon name="sheet" size={18} /></span>
                    <strong>{result.sheet_count}</strong>
                    <span>Worksheets</span>
                  </div>
                  <div className="metric-card">
                    <span className="metric-icon"><Icon name="activity" size={18} /></span>
                    <strong>{result.cells_scanned.toLocaleString()}</strong>
                    <span>Cells scanned</span>
                  </div>
                  <div className="metric-card">
                    <span className="metric-icon"><span className="fx-small">ƒx</span></span>
                    <strong>{result.formula_count.toLocaleString()}</strong>
                    <span>Formulas found</span>
                  </div>
                </div>

                <div className="result-block">
                  <h4>Worksheet overview</h4>
                  <div className="table-wrap">
                    <table>
                      <thead><tr><th>Worksheet</th><th>Dimensions</th><th>Rows</th><th>Columns</th></tr></thead>
                      <tbody>
                        {result.sheets.map((sheet) => (
                          <tr key={sheet.name}>
                            <td>{sheet.name}</td>
                            <td><code>{sheet.dimensions}</code></td>
                            <td>{sheet.max_row.toLocaleString()}</td>
                            <td>{sheet.max_column.toLocaleString()}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div className="result-block">
                  <div className="block-heading">
                    <h4>Formula samples</h4>
                    <span>{result.formula_samples.length} shown</span>
                  </div>
                  {result.formula_samples.length ? (
                    <div className="formula-list">
                      {result.formula_samples.map((sample, index) => (
                        <div className="formula-row" key={`${sample.sheet}-${sample.cell}-${index}`}>
                          <div className="formula-location">
                            <strong>{sample.cell}</strong>
                            <span>{sample.sheet}</span>
                          </div>
                          <code>{sample.formula}</code>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="empty-state">No formulas were found in the scanned cells.</p>
                  )}
                  {result.formula_samples_truncated && (
                    <p className="result-footnote">Only the first 500 formula samples are displayed.</p>
                  )}
                </div>

                {result.limitations?.length > 0 && (
                  <div className="limitations">
                    <strong>Current extraction scope</strong>
                    <p>{result.limitations[0]} Full bug detection and VBA analysis are not part of this version.</p>
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
              <p>Select an `.xlsx` workbook from your device. Your original file stays unchanged.</p>
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
