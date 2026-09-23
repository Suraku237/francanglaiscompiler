import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import { Analysis } from './Analysis'
import type { AnalyzerResult, AnalyzerState } from './analyzerTypes'
import { ErrorNotice, Icon, Spinner } from './components'
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
  const [result, setResult] = useState<AnalyzerResult | null>(null)
  const savedGrammar = useRef<string | null>(null)
  const appliedHandoff = useRef<number | null>(null)
  const input = useRef<HTMLTextAreaElement>(null)
  const { pending: loading, error: loadError, run: load, cancel: cancelLoad } = useRequest()
  const { pending: analyzing, error: analysisError, run: runAnalysis, cancel: cancelAnalysis, clearError: clearAnalysisError } = useRequest()
  const save = useRequest()
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
    if (active) return
    cancelAnalysis()
    clearAnalysisError()
    setResult(null)
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
      : 'Reference text copied unchanged. Select Analyze to test it; nothing has been saved to Collection.')
    input.current?.focus({ preventScroll: true })
    input.current?.scrollIntoView({ block: 'nearest' })
  }, [active, showAnalysis, state, incomingText, cancelAnalysis, clearAnalysisError])

  useEffect(() => {
    if (!dirty && !text && !save.pending) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty, text, save.pending])

  function invalidate() {
    cancelAnalysis()
    clearAnalysisError()
    setResult(null)
  }

  function changeText(value: string) {
    invalidate()
    setHandoffNote('')
    setText(value)
  }

  function changeGrammar(value: string) {
    invalidate()
    save.clearError()
    setNotice('')
    setGrammar(value)
  }

  function refresh() {
    invalidate()
    setRevision((value) => value + 1)
    setNotice('Refreshing saved grammar and collection counts. Your edited grammar and statement are kept.')
  }

  function saveCurrentGrammar() {
    if (grammar === null || !grammar.trim() || grammar.length > MAX_GRAMMAR || loading || save.pending) return
    const snapshot = grammar
    setNotice('')
    void save.run((signal) => api<{ grammar: string }>('/analyzer/grammar', {
      method: 'PUT', body: { grammar: snapshot }, signal,
    }), (response) => {
      savedGrammar.current = response.grammar
      setState((previous) => previous ? { ...previous, grammar: response.grammar } : previous)
      setGrammar((previous) => previous === snapshot ? response.grammar : previous)
      setNotice('Grammar saved privately. Any later edits remain unsaved.')
    })
  }

  function analyze() {
    if (grammar === null || !grammar.trim() || grammar.length > MAX_GRAMMAR || text.length > MAX_TEXT || loading || analyzing || save.pending) return
    setResult(null)
    void runAnalysis((signal) => api<AnalyzerResult>('/analyzer/analyze', {
      method: 'POST', body: { text, grammar }, signal, timeout: 60000,
    }), setResult)
  }

  const computeDisabled = loading || analyzing || save.pending || !grammar?.trim() || grammar.length > MAX_GRAMMAR || text.length > MAX_TEXT

  return <section className={`page coursework-page ${showAnalysis ? 'analysis-page' : 'franc-analyzer'}`} aria-labelledby="analyzer-title">
    <div className="page-intro compact-intro lab-intro">
      <div><h1 id="analyzer-title">{showAnalysis ? 'Analysis' : 'Franc Analyzer'}</h1><p>{showAnalysis ? 'Token frequencies, categories and detailed compiler results.' : 'Split into tokens, classify using your vocabulary, then test the grammar.'}</p></div>
    </div>
    <ErrorNotice message={loadError} onRetry={refresh} />
    {loading && <p className="lab-loading" role="status"><Spinner label="Loading analyzer" />Loading your saved grammar. Editor drafts are kept.</p>}
    {state && grammar !== null && <>
      {showAnalysis ? <Analysis result={result} lexicalSpec={state.lexical_spec} analyzing={analyzing} onCancel={cancelAnalysis} onUseText={onUseText} /> : <>
      <section className="lab-card analyzer-input" aria-label="Analyzer input">
        <form onSubmit={(event) => { event.preventDefault(); analyze() }}>
          {handoffNote && <p className="notice notice-subtle" role="status">{handoffNote}</p>}
          <div className="field"><label htmlFor="analyzer-text">Statement to analyze</label><textarea ref={input} id="analyzer-text" rows={3} maxLength={MAX_TEXT} value={text} onChange={(event) => changeText(event.target.value)} placeholder="Type or paste a statement. Leave blank to test empty input (epsilon)." aria-describedby="analyzer-text-hint" /><span id="analyzer-text-hint" className="field-hint">{text.length.toLocaleString()} / 4,000 characters · not saved to Collection</span></div>
          {text.length > MAX_TEXT && <ErrorNotice message="This source exceeds 4,000 characters. It was kept unchanged; select a shorter passage before analyzing." />}
          <div className="lab-actions analyzer-actions">
            <button type="submit" className="button button-primary" disabled={computeDisabled}>{analyzing ? <Spinner label="Running all analysis stages" /> : <Icon name="code" size={17} />}{analyzing ? 'Analyzing...' : 'Analyze'}</button>
            {analyzing && <button type="button" className="text-button" onClick={cancelAnalysis}>Cancel analysis</button>}
            <span className="field-hint">{dirty ? 'Using unsaved grammar' : 'Using saved grammar'}</span>
          </div>
          <p className="lab-copy analyzer-input-note">One run checks this input and your saved statements using the current grammar. It does not save or approve anything.</p>
        </form>
        <details className="lab-disclosure">
          <summary>Grammar settings</summary>
          <div className="lab-disclosure-body">
            <p className="lab-copy">The default is a <strong>starter, not a grammar derived from your data</strong>. Edit the rules to match the structures you observed.</p>
            <div className="field"><label htmlFor="analyzer-grammar">Context-free grammar</label><textarea id="analyzer-grammar" className="lab-grammar-input" rows={7} maxLength={MAX_GRAMMAR} spellCheck={false} autoCapitalize="off" autoCorrect="off" value={grammar} onChange={(event) => changeGrammar(event.target.value)} aria-describedby="analyzer-grammar-hint" /><span id="analyzer-grammar-hint" className="field-hint">{grammar.length.toLocaleString()} / 12,000 characters · Save grammar to keep edits</span></div>
            {grammar.length > MAX_GRAMMAR && <ErrorNotice message="The grammar exceeds 12,000 characters. Shorten it before saving or analyzing." />}
            <div className="lab-actions">
              <button type="button" className="button button-secondary" onClick={saveCurrentGrammar} disabled={!dirty || !grammar.trim() || grammar.length > MAX_GRAMMAR || loading || save.pending}>{save.pending ? <Spinner label="Saving grammar" /> : <Icon name="check" size={16} />}{save.pending ? 'Saving...' : 'Save grammar'}</button>
              <button type="button" className="text-button" onClick={refresh} disabled={loading || save.pending}><Icon name="refresh" size={16} />Refresh saved grammar</button>
            </div>
            <p className="lab-copy">One rule per line: <code>Nonterminal -&gt; symbol symbol | epsilon</code>. The first rule is the start symbol. Terminals are token categories, not literal words.</p>
            <div className="lab-terminal-list">{terminals.map((terminal) => <code key={terminal}>{terminal}</code>)}</div>
          </div>
        </details>
      </section>
      {result && <section className="lab-card analyzer-verdict" aria-labelledby="analyzer-verdict-title">
        <h2 id="analyzer-verdict-title">Parser result</h2>
        <p role="status"><span className={`lab-status ${result.parse.accepted ? 'ready' : 'needs_input'}`}>{result.parse.accepted ? 'ACCEPT' : 'REJECT'}</span></p>
        <p className="lab-copy">This result describes the current grammar's coverage, not whether the speaker's language is correct.</p>
        <a className="button button-secondary" href="#analysis">View detailed analysis<Icon name="arrow" size={16} /></a>
      </section>}
      </>}
      <ErrorNotice message={save.error} />
      {notice && <p className="lab-save-notice" role="status">{notice}</p>}
      <ErrorNotice message={analysisError} />
    </>}
  </section>
}
