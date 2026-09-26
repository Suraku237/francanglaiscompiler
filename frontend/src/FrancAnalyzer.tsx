import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from './api'
import { Analysis } from './Analysis'
import type { AnalyzerState, RecordedTest, TestReport } from './analyzerTypes'
import { ErrorNotice, Icon, Spinner } from './components'
import { AnalyzedSource, TokenTable } from './CourseworkResults'
import { defaultMetadata, MAX_TEXT } from './types'
import type { IncomingText } from './types'
import { useRequest } from './useRequest'
import { VocabularyVerdict } from './VocabularyVerdict'
import './coursework.css'

const terminals = defaultMetadata.lexical_categories
const MAX_GRAMMAR = 12000

export function FrancAnalyzer({ active, incomingText, showAnalysis = false, onUseText }: {
  active: boolean
  incomingText?: IncomingText
  showAnalysis?: boolean
  onUseText: (text: string) => void
}) {
  const [state, setState] = useState<AnalyzerState | null>(null)
  const [grammarStale, setGrammarStale] = useState(false)
  const [text, setText] = useState('')
  const [revision, setRevision] = useState(0)
  const [notice, setNotice] = useState('')
  const [handoffNote, setHandoffNote] = useState('')
  const [result, setResult] = useState<RecordedTest | null>(null)
  const [selectedTest, setSelectedTest] = useState<RecordedTest | null>(null)
  const [report, setReport] = useState<TestReport | null>(null)
  const [reportOffset, setReportOffset] = useState(0)
  const [reportRevision, setReportRevision] = useState(0)
  const [inspectionId, setInspectionId] = useState<string | null>(null)
  const [inspectionRevision, setInspectionRevision] = useState(0)
  const pendingTest = useRef<{ request_id: string; text: string; grammar: string } | null>(null)
  const appliedHandoff = useRef<number | null>(null)
  const input = useRef<HTMLTextAreaElement>(null)
  const { pending: loading, error: loadError, run: load, cancel: cancelLoad } = useRequest()
  const { pending: analyzing, error: analysisError, run: runAnalysis, cancel: cancelAnalysis, clearError: clearAnalysisError } = useRequest()
  const { pending: loadingTests, error: testLoadError, run: loadTests, cancel: cancelTests } = useRequest()
  const { pending: inspecting, error: inspectError, run: inspect, cancel: cancelInspection, clearError: clearInspectError } = useRequest()
  const grammar = state?.grammar ?? null

  useEffect(() => {
    if (!active) return
    void load((signal) => api<AnalyzerState>('/analyzer', { signal }), (response) => {
      setState(response)
      setGrammarStale(false)
    })
    return cancelLoad
  }, [active, revision, load, cancelLoad])

  useEffect(() => {
    if (!active || !showAnalysis) return
    setReport(null)
    void loadTests((signal) => api<TestReport>(`/analyzer/tests?offset=${reportOffset}&limit=25`, { signal }), (response) => {
      if (response.summary.total > 0 && response.offset >= response.summary.total) {
        setReportOffset(Math.floor((response.summary.total - 1) / response.limit) * response.limit)
      } else {
        setReport(response)
      }
    })
    return cancelTests
  }, [active, showAnalysis, reportOffset, reportRevision, loadTests, cancelTests])

  useEffect(() => {
    if (!active || !showAnalysis || !inspectionId) return
    setSelectedTest(null)
    void inspect((signal) => api<RecordedTest>(`/analyzer/tests/${encodeURIComponent(inspectionId)}`, { signal }), setSelectedTest)
    return cancelInspection
  }, [active, showAnalysis, inspectionId, inspectionRevision, inspect, cancelInspection])

  useEffect(() => {
    if (active) return
    cancelAnalysis()
    clearAnalysisError()
    setResult(null)
    setSelectedTest(null)
    setReport(null)
    setInspectionId(null)
  }, [active, cancelAnalysis, clearAnalysisError])

  useEffect(() => {
    if (!active || showAnalysis || !state || !incomingText || appliedHandoff.current === incomingText.id) return
    appliedHandoff.current = incomingText.id
    cancelAnalysis()
    clearAnalysisError()
    setResult(null)
    setText(incomingText.text)
    setHandoffNote(incomingText.kind === 'examples'
      ? 'Synthetic example copied unchanged. It is not fieldwork and has not been added to Collection.'
      : incomingText.kind === 'collection'
        ? 'Collection text copied unchanged. Select Analyze to record a public test; the original entry is unchanged.'
        : 'Reference text copied unchanged. Select Analyze to record a shared test; nothing has been added to Collection.')
    input.current?.focus({ preventScroll: true })
    input.current?.scrollIntoView({ block: 'nearest' })
  }, [active, showAnalysis, state, incomingText, cancelAnalysis, clearAnalysisError])

  useEffect(() => {
    if (!text && !analyzing) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [text, analyzing])

  function invalidate() {
    if (analyzing) setNotice('The earlier request may still finish and save its test publicly. Refresh saved tests on Analysis to check.')
    cancelAnalysis()
    clearAnalysisError()
    setResult(null)
  }

  function changeText(value: string) {
    invalidate()
    setHandoffNote('')
    setText(value)
    pendingTest.current = null
  }

  function refresh() {
    invalidate()
    setRevision((value) => value + 1)
    setNotice('Reloading saved grammar and collection counts. Your statement is kept.')
  }

  function analyze() {
    if (grammar === null || !grammar.trim() || grammar.length > MAX_GRAMMAR || text.length > MAX_TEXT || loading || loadError || analyzing || grammarStale) return
    setResult(null)
    setNotice('')
    const previous = pendingTest.current
    const request = previous && previous.text === text && previous.grammar === grammar
      ? previous : { request_id: crypto.randomUUID(), text, grammar }
    pendingTest.current = request
    void runAnalysis(async (signal) => {
      try {
        return await api<RecordedTest>('/analyzer/tests', {
          method: 'POST', body: request, signal, timeout: 60000,
        })
      } catch (error) {
        if (!signal.aborted && error instanceof ApiError && error.status === 409) setGrammarStale(true)
        throw error
      }
    }, (response) => {
      pendingTest.current = null
      setResult(response)
      setSelectedTest(response)
      setInspectionId(null)
      clearInspectError()
      setReportOffset(0)
      setReportRevision((value) => value + 1)
    })
  }

  function stopWaiting() {
    cancelAnalysis()
    setNotice('Stopped waiting. The server may still finish and save this test publicly. Refresh saved tests on Analysis to check before retrying.')
  }

  function refreshTests() {
    setReportRevision((value) => value + 1)
  }

  function inspectTest(id: string) {
    cancelInspection()
    clearInspectError()
    setSelectedTest(null)
    setInspectionId(id)
    setInspectionRevision((value) => value + 1)
  }

  const computeDisabled = loading || Boolean(loadError) || analyzing || grammarStale || !grammar?.trim() || grammar.length > MAX_GRAMMAR || text.length > MAX_TEXT
  const grammarStatus = grammarStale ? 'Saved grammar needs reloading' : 'Using saved grammar'
  const grammarError = grammar !== null && !grammar.trim()
    ? 'The saved grammar is empty. Contact the server operator; grammar is read-only on this website.'
    : grammar !== null && grammar.length > MAX_GRAMMAR
      ? 'The saved grammar exceeds 12,000 characters. Contact the server operator; grammar is read-only on this website.'
      : ''

  return <section className={`page coursework-page ${showAnalysis ? 'analysis-page' : 'franc-analyzer'}`} aria-labelledby="analyzer-title">
    <div className="page-intro compact-intro lab-intro">
      <div><h1 id="analyzer-title">{showAnalysis ? 'Analysis' : 'Franc Analyzer'}</h1><p>{showAnalysis ? 'Statistics and original results from all publicly saved tests.' : 'Split into tokens, classify using the shared vocabulary, then test the saved grammar.'}</p></div>
    </div>
    <ErrorNotice message={loadError} onRetry={refresh} />
    {loading && <p className="lab-loading" role="status"><Spinner label="Loading analyzer" />Loading the saved grammar. Your statement is kept.</p>}
    {state && grammar !== null && <>
      <ErrorNotice message={grammarError} />
      {notice && <p className="lab-save-notice" role="status">{notice}</p>}
      <ErrorNotice message={analysisError} />
      {grammarStale && <div className="notice notice-subtle" role="status"><p>The saved grammar has changed. Reload the saved grammar before analyzing again. Your statement has been kept.</p><button type="button" className="button button-secondary" onClick={refresh} disabled={loading}>Reload saved grammar</button></div>}
      {showAnalysis ? <Analysis result={selectedTest} report={report} lexicalSpec={state.lexical_spec} analyzing={analyzing} loading={loadingTests} loadError={testLoadError} inspecting={inspecting} inspectError={inspectError} onCancel={stopWaiting} onRefresh={refreshTests} onPage={setReportOffset} onInspect={inspectTest} onRetryInspect={() => setInspectionRevision((value) => value + 1)} onUseText={onUseText} grammarSettings={
        <details className="lab-disclosure">
          <summary>Grammar settings</summary>
          <div className="lab-disclosure-body">
            <p className="lab-copy">These saved rules are used for every new test. The illustrative starter is not fieldwork evidence. Saved tests keep their original grammar and results.</p>
            <p id="grammar-access" className="lab-copy">The saved grammar is read-only. There are no local grammar drafts or save controls on this website.</p>
            <div className="field"><label htmlFor="analyzer-grammar">Context-free grammar</label><textarea id="analyzer-grammar" className="lab-grammar-input" rows={7} spellCheck={false} value={grammar} readOnly aria-describedby="analyzer-grammar-hint grammar-access" /><span id="analyzer-grammar-hint" className="field-hint">{grammar.length.toLocaleString()} / 12,000 characters · Saved grammar · Read-only</span></div>
            <div className="lab-actions">
              <button type="button" className="text-button" onClick={refresh} disabled={loading}><Icon name="refresh" size={16} />Refresh saved grammar</button>
              <span className="field-hint">{grammarStatus}</span>
            </div>
            <p className="lab-copy">One rule per line: <code>Nonterminal -&gt; symbol symbol | epsilon</code>. The first rule is the start symbol. Terminals are token categories, not literal words.</p>
            <div className="lab-terminal-list">{terminals.map((terminal) => <code key={terminal}>{terminal}</code>)}</div>
          </div>
        </details>
      } /> : <>
      <section className="lab-card analyzer-input" aria-label="Analyzer input">
        <form onSubmit={(event) => { event.preventDefault(); analyze() }}>
          {handoffNote && <p className="notice notice-subtle" role="status">{handoffNote}</p>}
          <div className="field"><label htmlFor="analyzer-text">Statement to analyze</label><textarea ref={input} id="analyzer-text" rows={3} maxLength={MAX_TEXT} value={text} onChange={(event) => changeText(event.target.value)} placeholder="Type or paste a sentence or word. Leave blank to test empty input (epsilon)." aria-describedby="analyzer-text-hint" /><span id="analyzer-text-hint" className="field-hint">{text.length.toLocaleString()} / 4,000 characters · not saved to Collection</span></div>
          {text.length > MAX_TEXT && <ErrorNotice message="This source exceeds 4,000 characters. It was kept unchanged; select a shorter passage before analyzing." />}
          <div className="lab-actions analyzer-actions">
            <button type="submit" className="button button-primary" disabled={computeDisabled}>{analyzing ? <Spinner label="Running all analysis stages" /> : <Icon name="code" size={17} />}{analyzing ? 'Analyzing...' : 'Analyze'}</button>
            {analyzing && <button type="button" className="text-button" onClick={stopWaiting}>Stop waiting</button>}
            <span className="field-hint">{grammarStatus}</span>
          </div>
          <p className="lab-copy analyzer-input-note">Analyze publicly retains this test’s original text, saved grammar and results, even when rejected. Do not submit personal or confidential content. Repeated completed tests count separately. Nothing is added to Collection.</p>
        </form>
      </section>
      {result && <section className="lab-card analyzer-verdict" aria-labelledby="analyzer-verdict-title">
        <h2 id="analyzer-verdict-title">Vocabulary result</h2>
        <div className="analyzer-source"><h3>Analyzed sentence or word</h3><AnalyzedSource text={result.text} /></div>
        <div className="analyzer-classifications"><h3>Word classifications</h3><TokenTable tokens={result.lexical.tokens} /></div>
        <VocabularyVerdict result={result.approval} empty={result.lexical.tokens.length === 0} />
        <p className="lab-copy">Test saved publicly. Its counts are included in Analysis. Saved tests are immutable.</p>
        <a className="button button-secondary" href="#analysis" onClick={() => { cancelInspection(); clearInspectError(); setInspectionId(null); setSelectedTest(result) }}>View detailed analysis<Icon name="arrow" size={16} /></a>
      </section>}
      </>}
    </>}
  </section>
}
