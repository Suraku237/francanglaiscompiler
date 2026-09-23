import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import { Analysis } from './Analysis'
import type { AnalyzerState, RecordedTest, TestReport } from './analyzerTypes'
import { ErrorNotice, Icon, Spinner } from './components'
import { AnalyzedSource, TokenTable } from './CourseworkResults'
import { MAX_TEXT } from './types'
import type { IncomingText } from './types'
import { useRequest } from './useRequest'
import './coursework.css'

const terminals = ['NOUN', 'VERB', 'SLANG', 'PIDGIN_MARKER', 'FRENCH_FUNCTION_WORD', 'ENGLISH_FUNCTION_WORD', 'ENGLISH_VERB_LIKE', 'FRENCH_VERB_LIKE', 'UNKNOWN', 'NUMBER', 'PUNCTUATION']
const MAX_GRAMMAR = 12000

export function FrancAnalyzer({ active, incomingText, showAnalysis = false, onUseText }: {
  active: boolean
  incomingText?: IncomingText
  showAnalysis?: boolean
  onUseText: (text: string) => void
}) {
  const [state, setState] = useState<AnalyzerState | null>(null)
  const [grammar, setGrammar] = useState<string | null>(null)
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
  const savedGrammar = useRef<string | null>(null)
  const appliedHandoff = useRef<number | null>(null)
  const input = useRef<HTMLTextAreaElement>(null)
  const { pending: loading, error: loadError, run: load, cancel: cancelLoad } = useRequest()
  const { pending: analyzing, error: analysisError, run: runAnalysis, cancel: cancelAnalysis, clearError: clearAnalysisError } = useRequest()
  const save = useRequest()
  const { pending: loadingTests, error: testLoadError, run: loadTests, cancel: cancelTests } = useRequest()
  const { pending: inspecting, error: inspectError, run: inspect, cancel: cancelInspection, clearError: clearInspectError } = useRequest()
  const dirty = grammar !== null && grammar !== state?.grammar

  useEffect(() => {
    if (!active) return
    void load((signal) => api<AnalyzerState>('/analyzer', { signal }), (response) => {
      const previousSaved = savedGrammar.current
      savedGrammar.current = response.grammar
      setGrammar((previous) => previous === null || previous === previousSaved ? response.grammar : previous)
      setState(response)
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
        ? 'Collection text copied unchanged. Select Analyze to record a shared test; the original entry and its ownership are unchanged.'
        : 'Reference text copied unchanged. Select Analyze to record a shared test; nothing has been added to Collection.')
    input.current?.focus({ preventScroll: true })
    input.current?.scrollIntoView({ block: 'nearest' })
  }, [active, showAnalysis, state, incomingText, cancelAnalysis, clearAnalysisError])

  useEffect(() => {
    if (!dirty && !text && !save.pending && !analyzing) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty, text, save.pending, analyzing])

  function invalidate() {
    if (analyzing) setNotice('The earlier request may still finish and save its test for all signed-in users. Refresh saved tests on Analysis to check.')
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

  function changeGrammar(value: string) {
    setNotice('')
    invalidate()
    save.clearError()
    setGrammar(value)
    pendingTest.current = null
  }

  function refresh() {
    invalidate()
    setRevision((value) => value + 1)
    setNotice('Refreshing saved grammar and collection counts. Your edited grammar and statement are kept.')
  }

  function saveCurrentGrammar() {
    if (!state?.grammar_ownership.can_edit || grammar === null || !grammar.trim() || grammar.length > MAX_GRAMMAR || loading || save.pending) return
    const snapshot = grammar
    setNotice('')
    void save.run((signal) => api<Pick<AnalyzerState, 'grammar' | 'grammar_ownership'>>('/analyzer/grammar', {
      method: 'PUT', body: { grammar: snapshot }, signal,
    }), (response) => {
      savedGrammar.current = response.grammar
      setState((previous) => previous ? { ...previous, ...response } : previous)
      setGrammar((previous) => previous === snapshot ? response.grammar : previous)
      setNotice('Grammar saved to the shared workspace. Any later edits remain local and unsaved.')
    })
  }

  function analyze() {
    if (grammar === null || !grammar.trim() || grammar.length > MAX_GRAMMAR || text.length > MAX_TEXT || loading || analyzing || save.pending) return
    setResult(null)
    setNotice('')
    const previous = pendingTest.current
    const request = previous && previous.text === text && previous.grammar === grammar
      ? previous : { request_id: crypto.randomUUID(), text, grammar }
    pendingTest.current = request
    void runAnalysis((signal) => api<RecordedTest>('/analyzer/tests', {
      method: 'POST', body: request, signal, timeout: 60000,
    }), (response) => {
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
    setNotice('Stopped waiting. The server may still finish and save this test for all signed-in users. Refresh saved tests on Analysis to check before retrying.')
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

  const computeDisabled = loading || analyzing || save.pending || !grammar?.trim() || grammar.length > MAX_GRAMMAR || text.length > MAX_TEXT
  const grammarStatus = dirty ? 'Using unsaved grammar' : 'Using saved grammar'
  const grammarError = grammar !== null && !grammar.trim()
    ? 'The grammar is empty. Enter rules in Grammar settings on Analysis before analyzing.'
    : grammar !== null && grammar.length > MAX_GRAMMAR
      ? 'The grammar exceeds 12,000 characters. Shorten it in Grammar settings on Analysis before saving or analyzing.'
      : ''

  return <section className={`page coursework-page ${showAnalysis ? 'analysis-page' : 'franc-analyzer'}`} aria-labelledby="analyzer-title">
    <div className="page-intro compact-intro lab-intro">
      <div><h1 id="analyzer-title">{showAnalysis ? 'Analysis' : 'Franc Analyzer'}</h1><p>{showAnalysis ? 'Statistics and original results from every user’s saved tests.' : 'Split into tokens, classify using the shared vocabulary, then test the grammar.'}</p></div>
    </div>
    <ErrorNotice message={loadError} onRetry={refresh} />
    {loading && <p className="lab-loading" role="status"><Spinner label="Loading analyzer" />Loading the shared saved grammar. Editor drafts are kept.</p>}
    {state && grammar !== null && <>
      <ErrorNotice message={grammarError} />
      <ErrorNotice message={save.error} />
      {notice && <p className="lab-save-notice" role="status">{notice}</p>}
      <ErrorNotice message={analysisError} />
      {showAnalysis ? <Analysis result={selectedTest} report={report} lexicalSpec={state.lexical_spec} analyzing={analyzing} loading={loadingTests} loadError={testLoadError} inspecting={inspecting} inspectError={inspectError} onCancel={stopWaiting} onRefresh={refreshTests} onPage={setReportOffset} onInspect={inspectTest} onRetryInspect={() => setInspectionRevision((value) => value + 1)} onUseText={onUseText} grammarSettings={
        <details className="lab-disclosure">
          <summary>Grammar settings</summary>
          <div className="lab-disclosure-body">
            <p className="lab-copy">The default is a <strong>starter, not a grammar derived from your data</strong>. Edit the rules to match the structures you observed.</p>
            <p className="lab-copy">Everyone can edit a local grammar draft and use it in Analyze without changing the shared grammar. Only its creator can save shared changes. Saved tests keep their original grammar and results.</p>
            <p id="grammar-ownership" className="lab-copy">{state.grammar_ownership.owner_id === null
              ? 'The shared grammar is unclaimed. The first person to save it becomes its creator.'
              : <>Shared grammar creator: {state.grammar_ownership.owner_name}. {state.grammar_ownership.can_edit ? 'You can save changes for everyone.' : 'Read-only shared settings; you can still edit and test a local draft.'}</>}</p>
            <div className="field"><label htmlFor="analyzer-grammar">Context-free grammar</label><textarea id="analyzer-grammar" className="lab-grammar-input" rows={7} maxLength={MAX_GRAMMAR} spellCheck={false} autoCapitalize="off" autoCorrect="off" value={grammar} onChange={(event) => changeGrammar(event.target.value)} aria-describedby="analyzer-grammar-hint grammar-ownership" /><span id="analyzer-grammar-hint" className="field-hint">{grammar.length.toLocaleString()} / 12,000 characters · Local draft until the creator explicitly saves</span></div>
            <div className="lab-actions">
              <button type="button" className="button button-secondary" onClick={saveCurrentGrammar} aria-describedby="grammar-ownership" disabled={!state.grammar_ownership.can_edit || (!dirty && state.grammar_ownership.owner_id !== null) || !grammar.trim() || grammar.length > MAX_GRAMMAR || loading || save.pending}>{save.pending ? <Spinner label="Saving grammar" /> : <Icon name="check" size={16} />}{save.pending ? 'Saving...' : 'Save grammar'}</button>
              <button type="button" className="text-button" onClick={refresh} disabled={loading || save.pending}><Icon name="refresh" size={16} />Refresh saved grammar</button>
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
          <p className="lab-copy analyzer-input-note">Analyze saves this test and its results in the shared workspace for all signed-in users, even when rejected. Repeated completed tests count separately. Nothing is added to Collection and local grammar edits are only shared with Save grammar, by the grammar’s creator.</p>
        </form>
      </section>
      {result && <section className="lab-card analyzer-verdict" aria-labelledby="analyzer-verdict-title">
        <h2 id="analyzer-verdict-title">Parser result</h2>
        <div className="analyzer-source"><h3>Analyzed sentence or word</h3><AnalyzedSource text={result.text} /></div>
        <div className="analyzer-classifications"><h3>Word classifications</h3><TokenTable tokens={result.lexical.tokens} /></div>
        <p role="status"><span className={`lab-status ${result.parse.accepted ? 'ready' : 'needs_input'}`}>{result.parse.accepted ? 'ACCEPT' : 'REJECT'}</span></p>
        <p className="lab-copy">Test saved. Creator: {result.ownership.owner_name}. Its counts are included in everyone’s Analysis. Saved tests are immutable.</p>
        <p className="lab-copy">This result describes the current grammar's coverage, not whether the speaker's language is correct.</p>
        <a className="button button-secondary" href="#analysis" onClick={() => { cancelInspection(); clearInspectError(); setInspectionId(null); setSelectedTest(result) }}>View detailed analysis<Icon name="arrow" size={16} /></a>
      </section>}
      </>}
    </>}
  </section>
}
