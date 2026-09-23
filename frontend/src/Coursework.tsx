import { useCallback, useEffect, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { api } from './api'
import { ErrorNotice, Icon, Spinner, TokenAnalysis } from './components'
import { CourseworkExport, CourseworkScreenshots } from './CourseworkEvidence'
import { CorpusResults, GrammarResults, LexicalResults, ParseTrace, TableScroll, TokenTable } from './CourseworkResults'
import type { CourseworkAnalysis, CourseworkState, ManualParse, Project, Screenshot } from './courseworkTypes'
import { defaultMetadata, MAX_TEXT } from './types'
import type { Analysis, IncomingText } from './types'
import { useRequest } from './useRequest'
import './coursework.css'

const terminals = ['NOUN', 'VERB', 'SLANG', 'PIDGIN_MARKER', 'FRENCH_FUNCTION_WORD', 'ENGLISH_FUNCTION_WORD', 'ENGLISH_VERB_LIKE', 'FRENCH_VERB_LIKE', 'UNKNOWN', 'NUMBER', 'PUNCTUATION']
const sections = [
  { id: 'lab-collection', label: 'Data collection' },
  { id: 'lab-lexical', label: 'Lexical analysis' },
  { id: 'lab-grammar', label: 'Syntactic analysis' },
  { id: 'lab-parser', label: 'Parser tests' },
  { id: 'lab-submission', label: 'Report & presentation' },
] as const
type SectionId = typeof sections[number]['id']

export function Coursework({ active, incomingText }: { active: boolean; incomingText?: IncomingText }) {
  const [state, setState] = useState<CourseworkState | null>(null)
  const [draft, setDraft] = useState<Project | null>(null)
  const [saved, setSaved] = useState<Project | null>(null)
  const [revision, setRevision] = useState(0)
  const [notice, setNotice] = useState('')
  const [analysis, setAnalysis] = useState<CourseworkAnalysis | null>(null)
  const [testText, setTestText] = useState('')
  const [manual, setManual] = useState<ManualParse | null>(null)
  const [lexical, setLexical] = useState<Analysis | null>(null)
  const [handoffNote, setHandoffNote] = useState('')
  const [section, setSection] = useState<SectionId>('lab-lexical')
  const focusTarget = useRef<string | null>(null)
  const appliedHandoff = useRef<number | null>(null)
  const [screenshotBusy, setScreenshotBusy] = useState(false)
  const [resultsNote, setResultsNote] = useState('')
  const loaded = useRef(false)
  const { pending: loading, error: loadError, run: load, cancel: cancelLoad } = useRequest()
  const save = useRequest()
  const { pending: analyzing, error: analysisError, run: runAnalysis, cancel: cancelAnalysis, clearError: clearAnalysisError } = useRequest()
  const { pending: parsing, error: parseError, run: runParse, cancel: cancelParse, clearError: clearParseError } = useRequest()
  const { pending: lexing, error: lexicalError, run: runLexical, cancel: cancelLexical, clearError: clearLexicalError } = useRequest()
  const dirty = draft !== null && saved !== null && JSON.stringify(draft) !== JSON.stringify(saved)

  useEffect(() => {
    if (!active) return
    void load((signal) => api<CourseworkState>('/coursework', { signal }), (response) => {
      setState(response)
      setSaved(response.project)
      setDraft((previous) => previous ?? response.project)
      loaded.current = true
    })
    return cancelLoad
  }, [active, revision, load, cancelLoad])

  useEffect(() => {
    if (active) return
    cancelAnalysis()
    cancelParse()
    cancelLexical()
    setAnalysis(null)
    if (loaded.current) setResultsNote('Saved collection evidence is refreshed when you return. Run the analysis again to test the current collection; your editor draft is kept.')
  }, [active, cancelAnalysis, cancelParse, cancelLexical])

  useEffect(() => {
    if (!active || !draft || !incomingText || appliedHandoff.current === incomingText.id) return
    appliedHandoff.current = incomingText.id
    cancelParse()
    cancelLexical()
    clearParseError()
    clearLexicalError()
    setTestText(incomingText.text)
    setManual(null)
    setLexical(null)
    setHandoffNote(incomingText.kind === 'examples'
      ? 'Synthetic example copied unchanged. It is not fieldwork and has not been added to your collection.'
      : 'Reference text copied unchanged into this manual draft. Run the lexer or parser explicitly; nothing has been saved to Collection.')
    focusTarget.current = 'lab-test-text'
    setSection('lab-parser')
  }, [active, draft, incomingText, cancelParse, cancelLexical, clearParseError, clearLexicalError])

  useEffect(() => {
    if (!active || !draft || !focusTarget.current) return
    const target = document.getElementById(focusTarget.current)
    if (!target || target.closest('[hidden]')) return
    target.focus({ preventScroll: true })
    target.scrollIntoView({ block: 'nearest' })
    focusTarget.current = null
  }, [active, draft, incomingText, section, testText])

  useEffect(() => {
    if (!dirty && !save.pending) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty, save.pending])

  const refreshEvidence = useCallback(() => {
    setRevision((value) => value + 1)
  }, [])

  function refreshAll() {
    cancelAnalysis()
    clearAnalysisError()
    setAnalysis(null)
    setResultsNote('Evidence refreshed without replacing your editor draft. Analyze again to compute results from this project’s saved collection.')
    refreshEvidence()
  }

  function update<K extends keyof Project>(field: K, value: Project[K]) {
    setDraft((previous) => previous ? { ...previous, [field]: value } : previous)
    save.clearError()
    setNotice('')
    if (field === 'grammar') {
      cancelAnalysis()
      cancelParse()
      clearAnalysisError()
      clearParseError()
      setAnalysis(null)
      setManual(null)
      setResultsNote('Grammar edited: previous computations have been cleared. Analyze again for results from this version. Saving is a separate action.')
    }
  }

  function saveProject() {
    if (!draft || save.pending || loading) return
    const snapshot = draft
    setNotice('')
    void save.run((signal) => api<unknown>('/coursework/project', { method: 'PUT', body: snapshot, signal }), () => {
      setSaved(snapshot)
      setNotice('Project saved privately on this server, including the grammar. Later edits remain unsaved until you save again.')
      refreshEvidence()
    })
  }

  function analyze() {
    if (!draft || !draft.grammar.trim() || analyzing || loading) return
    setAnalysis(null)
    setResultsNote('')
    void runAnalysis((signal) => api<CourseworkAnalysis>('/coursework/analyze', { method: 'POST', body: { grammar: draft.grammar }, signal, timeout: 60000 }), setAnalysis)
  }

  function analyzeTokens() {
    if (!testText.trim() || testText.length > MAX_TEXT || lexing) return
    setLexical(null)
    void runLexical((signal) => api<Analysis>('/analyze', { method: 'POST', body: { text: testText }, signal }), setLexical)
  }

  function selectSection(next: SectionId, targetId?: string) {
    focusTarget.current = targetId ?? null
    setSection(next)
    if (section === next && targetId) {
      const target = document.getElementById(targetId)
      target?.focus({ preventScroll: true })
      target?.scrollIntoView({ block: 'nearest' })
      focusTarget.current = null
    }
  }

  function moveTab(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let nextIndex: number
    if (event.key === 'ArrowRight') nextIndex = (index + 1) % sections.length
    else if (event.key === 'ArrowLeft') nextIndex = (index - 1 + sections.length) % sections.length
    else if (event.key === 'Home') nextIndex = 0
    else if (event.key === 'End') nextIndex = sections.length - 1
    else return
    event.preventDefault()
    const next = sections[nextIndex]
    if (next) {
      selectSection(next.id)
      document.getElementById(`${next.id}-tab`)?.focus()
    }
  }

  function changeTestText(value: string) {
    cancelParse()
    cancelLexical()
    clearParseError()
    clearLexicalError()
    setManual(null)
    setLexical(null)
    setHandoffNote('')
    setTestText(value)
  }

  function updateScreenshots(updateItems: (items: Screenshot[]) => Screenshot[]) {
    setState((previous) => previous ? { ...previous, screenshots: updateItems(previous.screenshots) } : previous)
    refreshEvidence()
  }

  const suggestedTopics = defaultMetadata.categories.filter((name) => name !== 'Other')
  const computeDisabled = !draft?.grammar.trim() || analyzing || loading
  const showProjectActions = dirty || save.pending || ['lab-collection', 'lab-grammar', 'lab-submission'].includes(section)

  return <section className="page coursework-page" aria-labelledby="coursework-title">
    <div className="page-intro compact-intro lab-intro">
      <div><h1 id="coursework-title">Compiler lab</h1><p>CS4110 · Five sections from the assignment.</p></div>
    </div>
    <div className="lab-section-nav" role="tablist" aria-label="Assignment sections">{sections.map((item, index) => <button type="button" role="tab" key={item.id} id={`${item.id}-tab`} aria-controls={item.id} aria-selected={section === item.id} tabIndex={section === item.id ? 0 : -1} disabled={!state} onClick={() => selectSection(item.id)} onKeyDown={(event) => moveTab(event, index)}><span aria-hidden="true">{index + 1}</span>{item.label}</button>)}</div>
    <ErrorNotice message={loadError} onRetry={refreshAll} />
    {loading && <p className="lab-loading" role="status"><Spinner label="Loading saved coursework evidence" />Refreshing local evidence. Editor changes are kept.</p>}
    {!state || !draft ? !loading && !loadError ? <p className="lab-copy">Open Compiler lab to load your private project.</p> : null : <>
      <div className="lab-savebar" hidden={!showProjectActions}>
        <strong>{dirty ? 'Unsaved project changes' : 'No unsaved editor changes'}</strong>
        <div className="lab-actions"><button type="button" className="icon-button" aria-label="Refresh saved coursework evidence, preserve editor draft" title="Refresh saved evidence; preserve draft" disabled={loading || save.pending} onClick={refreshAll}><Icon name="refresh" size={18} /></button><button type="button" className="button button-secondary" onClick={saveProject} disabled={save.pending || loading}>{save.pending ? <Spinner label="Saving coursework project" /> : <Icon name="check" size={17} />}{save.pending ? 'Saving…' : 'Save project'}</button></div>
      </div>
      <ErrorNotice message={save.error} />
      {notice && <p className="lab-save-notice" role="status">{notice}</p>}
      <ErrorNotice message={analysisError} />
      {resultsNote && !analysis && <p className="lab-copy" role="status">{resultsNote}</p>}
      {analyzing && <p className="lab-loading" role="status"><Spinner label="Computing grammar and corpus tests" />Computing saved-statement results… <button type="button" className="text-button" onClick={cancelAnalysis}>Cancel</button></p>}

      <section id="lab-collection" className="lab-card" role="tabpanel" aria-labelledby="lab-collection-tab" tabIndex={0} hidden={section !== 'lab-collection'}>
        <div className="lab-card-heading"><div><h2>Data collection</h2><p>Collect {state.brief.statement_target.join('–')} real statements in Yaoundé. Manually transcribe the exact words, including slang, accents and mistakes.</p></div></div>
        <p className="lab-copy"><strong>{state.stats.sentences} / {state.brief.statement_target.join('–')} statements saved</strong> · {state.stats.total} total collection records.</p>
        {state.stats.total === 0 && <p className="lab-copy">No collected corpus in this project yet.</p>}
        <div className="lab-actions"><a className="button button-primary" href="#collection">Open Collection<Icon name="arrow" size={15} /></a></div>
        <p className="lab-copy">Use Add entry in Collection to save each manual transcript and its meaning. Manual compiler tests do not save statements.</p>
        <details className="lab-disclosure"><summary>Suggested topics from the assignment</summary><div className="lab-disclosure-body"><p className="lab-copy">{suggestedTopics.join(' · ')}.</p></div></details>
        <details className="lab-disclosure"><summary>Collection notes for the report</summary><div className="lab-disclosure-body">
          <div className="field"><label htmlFor="lab-method">Collection method & provenance</label><textarea id="lab-method" rows={3} maxLength={6000} value={draft.collection_method} onChange={(event) => update('collection_method', event.target.value)} placeholder="Where and when you heard the statements, how you transcribed them, and who collected them. Leave unknown facts blank." /></div>
          <label className="lab-attestation"><input type="checkbox" checked={draft.manual_transcription_confirmed} onChange={(event) => update('manual_transcription_confirmed', event.target.checked)} /><span>We manually transcribed real statements; generated/demo text is not research data<strong>Confirm only if true for your collection.</strong></span></label>
        </div></details>
      </section>

      <section id="lab-lexical" className="lab-card" role="tabpanel" aria-labelledby="lab-lexical-tab" tabIndex={0} hidden={section !== 'lab-lexical'}>
        <div className="lab-card-heading"><div><h2 id="lab-lexical-title" tabIndex={-1}>Lexical analysis</h2><p>Identify nouns, verbs, slang and code-mixed expressions using the custom lexer.</p></div></div>
        <form onSubmit={(event) => { event.preventDefault(); analyzeTokens() }}>
          <div className="field"><label htmlFor="lab-lexical-text">Sentence to analyze</label><textarea id="lab-lexical-text" rows={3} maxLength={MAX_TEXT} value={testText} onChange={(event) => changeTestText(event.target.value)} placeholder="Type or paste one statement." aria-describedby="lab-lexical-hint" /><span id="lab-lexical-hint" className="field-hint">{testText.length.toLocaleString()} / 4,000 characters · not saved to Collection</span></div>
          {testText.length > MAX_TEXT && <ErrorNotice message="This source exceeds 4,000 characters. It was kept unchanged; select a shorter passage before computing." />}
          <div className="lab-actions"><button type="submit" className="button button-primary" disabled={!testText.trim() || testText.length > MAX_TEXT || lexing}>{lexing ? <Spinner label="Analyzing manual tokens" /> : <Icon name="code" size={17} />}{lexing ? 'Lexing…' : 'Analyze tokens'}</button><button type="button" className="text-button" onClick={() => selectSection('lab-parser', 'lab-test-text')}>Open parser test<Icon name="arrow" size={15} /></button>{lexing && <button type="button" className="text-button" onClick={cancelLexical}>Cancel computation</button>}</div>
        </form>
        <ErrorNotice message={lexicalError} />
        {lexical && <div className="lab-results"><h3>Manual lexical result</h3><TokenAnalysis analysis={lexical} /></div>}
        <details className="lab-disclosure">
          <summary>Regular expressions & classification rules</summary>
          <div className="lab-disclosure-body">
            <h4>Token boundary regex</h4><pre className="lab-regex">{state.lexical_spec.token_pattern}</pre>
            <h4>Classification precedence</h4><ol className="lab-list">{state.lexical_spec.classification_order.map((rule, index) => <li key={index}>{rule}</li>)}</ol>
            <TableScroll label="Lexer regular expression rules"><table className="lab-table"><thead><tr><th scope="col">Category</th><th scope="col">Regex pattern</th></tr></thead><tbody>{state.lexical_spec.regex_rules.map((rule, index) => <tr key={index}><td><code>{rule.category}</code></td><td><code>{rule.pattern}</code></td></tr>)}</tbody></table></TableScroll>
            <div className="lab-two-columns"><div><h4>Verb-phrase lexicon</h4><p className="lab-copy">{state.lexical_spec.verb_phrases.join(' · ') || 'No phrases specified'}</p></div><div><h4>Slang-phrase lexicon</h4><p className="lab-copy">{state.lexical_spec.slang_phrases.join(' · ') || 'No phrases specified'}</p></div></div>
            <h4>Known limitations</h4><ul className="lab-list">{state.lexical_spec.limitations.map((limitation, index) => <li key={index}>{limitation}</li>)}</ul>
          </div>
        </details>
        <div className="lab-result-heading"><h3>Token tables, frequency & variation</h3></div>
        <p className="lab-copy">{state.stats.total ? `${state.stats.sentences} saved statements in this project.` : 'No saved statements yet. Add them in Data collection for corpus results.'} Corpus computation also uses the grammar in Syntactic analysis.</p>
        <button type="button" className="button button-secondary" disabled={computeDisabled || state.stats.total === 0} onClick={analyze}>Analyze saved statements</button>
        {analysis && <LexicalResults lexical={analysis.lexical} />}
      </section>

      <section id="lab-grammar" className="lab-card" role="tabpanel" aria-labelledby="lab-grammar-tab" tabIndex={0} hidden={section !== 'lab-grammar'}>
        <div className="lab-card-heading"><div><h2 id="lab-grammar-title" tabIndex={-1}>Syntactic analysis</h2><p>Build a CFG, remove left recursion, apply left factoring, compute FIRST/FOLLOW and build the LL(1) table.</p></div></div>
        <p className="lab-copy">The supplied default is a <strong>starter, not a grammar derived from your data</strong>. Base your rules on the collected statements.</p>
        <div className="field"><label htmlFor="lab-grammar-input">Context-free grammar</label><textarea id="lab-grammar-input" className="lab-grammar-input" value={draft.grammar} rows={7} maxLength={12000} spellCheck={false} autoCapitalize="off" autoCorrect="off" onChange={(event) => update('grammar', event.target.value)} aria-describedby="lab-grammar-hint" /><span id="lab-grammar-hint" className="field-hint">{draft.grammar.length.toLocaleString()} / 12,000 characters · Save project to keep edits</span></div>
        <div className="lab-actions"><button type="button" className="button button-primary" disabled={computeDisabled} onClick={analyze}>{analyzing ? 'Computing…' : 'Analyze grammar & saved corpus'}</button></div>
        <p className="lab-copy">Uses the <strong>current editor grammar + saved collection in this project</strong>. Computation does not save edits.</p>
        <details className="lab-disclosure"><summary>Grammar notation & rationale</summary><div className="lab-disclosure-body">
          <p className="lab-copy">One rule per line: <code>Nonterminal -&gt; symbol symbol | epsilon</code>. The first rule is the start symbol. Terminals are the categories below, not literal words. Use PUNCTUATION for punctuation and epsilon for an empty production.</p>
          <div className="lab-terminal-list">{terminals.map((terminal) => <code key={terminal}>{terminal}</code>)}</div>
          <div className="field"><label htmlFor="lab-rationale">Why this grammar fits your observations</label><textarea id="lab-rationale" rows={3} maxLength={6000} value={draft.grammar_rationale} onChange={(event) => update('grammar_rationale', event.target.value)} placeholder="Link grammar rules to patterns in your collected statements." /></div>
        </div></details>
        {analysis && <GrammarResults grammar={analysis.grammar} />}
      </section>

      <section id="lab-parser" className="lab-card" role="tabpanel" aria-labelledby="lab-parser-tab" tabIndex={0} hidden={section !== 'lab-parser'}>
        <div className="lab-card-heading"><div><h2>Parser tests</h2><p>Run the implemented LL(1) parser. Inspect tokens, ACCEPT / REJECT and each stack operation.</p></div></div>
        <form onSubmit={(event) => {
          event.preventDefault()
          if (!draft.grammar.trim() || parsing || testText.length > MAX_TEXT) return
          setManual(null)
          void runParse((signal) => api<ManualParse>('/coursework/parse', { method: 'POST', body: { grammar: draft.grammar, text: testText }, signal, timeout: 30000 }), setManual)
        }}>
          {handoffNote && <p className="notice notice-subtle" role="status">{handoffNote}</p>}
          <div className="field"><label htmlFor="lab-test-text">Manual parser test</label><textarea id="lab-test-text" rows={3} maxLength={MAX_TEXT} value={testText} onChange={(event) => changeTestText(event.target.value)} placeholder="Type or paste one input. Leave it empty to test epsilon." aria-describedby="lab-test-hint" /><span id="lab-test-hint" className="field-hint">{testText.length.toLocaleString()} / 4,000 characters · raw spacing preserved · not saved</span></div>
          {testText.length > MAX_TEXT && <ErrorNotice message="This source exceeds 4,000 characters. It was kept unchanged; select a shorter passage before computing." />}
          <div className="lab-actions">
            <button type="submit" className="button button-primary" disabled={!draft.grammar.trim() || parsing || testText.length > MAX_TEXT}>{parsing ? <Spinner label="Parsing manual test" /> : <Icon name="code" size={17} />}{parsing ? 'Parsing…' : 'Parse test input'}</button>
            <button type="button" className="button button-secondary" disabled={!testText.trim() || testText.length > MAX_TEXT || lexing} onClick={() => { selectSection('lab-lexical', 'lab-lexical-title'); analyzeTokens() }}>Analyze tokens</button>
            {parsing && <button type="button" className="text-button" onClick={cancelParse}>Cancel computation</button>}
          </div>
        </form>
        <p className="lab-copy">Uses your current CFG. <button type="button" className="text-button" onClick={() => selectSection('lab-grammar', 'lab-grammar-input')}>Edit grammar</button></p>
        <ErrorNotice message={parseError} />
        {manual && <div className="lab-results"><h3>Manual test result</h3><TokenTable tokens={manual.tokens} /><ParseTrace result={manual.parse} /><p className="lab-copy">ACCEPT / REJECT describes this grammar’s coverage of the token stream, not whether the speaker’s language is correct.</p></div>}
        <div className="lab-result-heading"><h3>Test your collected statements</h3><button type="button" className="button button-secondary" disabled={computeDisabled || state.stats.total === 0} onClick={analyze}>Run saved-statement tests</button></div>
        {analysis ? <CorpusResults tests={analysis.tests} summary={analysis.summary} onUseText={(text) => { changeTestText(text); selectSection('lab-parser', 'lab-test-text') }} /> : <p className="lab-copy">Save your statements in Collection, then run these tests to show which fit the grammar.</p>}
      </section>

      <section id="lab-submission" className="lab-card" role="tabpanel" aria-labelledby="lab-submission-tab" tabIndex={0} hidden={section !== 'lab-submission'}>
        <div className="lab-card-heading"><div><h2>Report & presentation</h2><p>{state.brief.report_pages.join('–')}-page report (maximum 30), lexer/parser source code and own-data tests, plus a {state.brief.presentation_minutes}-minute presentation.</p></div></div>
        <p className="lab-copy">Group of {state.brief.group_size} · {state.brief.per_student_minutes} minutes per student{state.brief.due ? ` · Due ${state.brief.due}` : ''}.</p>
        <div className="lab-members">{Array.from({ length: state.brief.group_size }, (_, index) => <div className="field" key={index}><label htmlFor={`lab-member-${index}`}>Group member {index + 1}</label><input id={`lab-member-${index}`} value={draft.group_members[index] ?? ''} maxLength={100} onChange={(event) => update('group_members', Array.from({ length: state.brief.group_size }, (_, member) => member === index ? event.target.value : draft.group_members[member] ?? ''))} placeholder="Name and matricule" /></div>)}</div>
        <div className="field"><label htmlFor="lab-discussion">Linguistic discussion</label><textarea id="lab-discussion" rows={4} maxLength={12000} value={draft.discussion} onChange={(event) => update('discussion', event.target.value)} placeholder="Explain why Yaoundé communication is linguistically complex, using your collected examples: slang, code mixing, variation and context." /><span className="field-hint">{draft.discussion.length.toLocaleString()} / 12,000 characters · Save project to include this writing</span></div>
        {saved?.limitations && <details className="lab-disclosure"><summary>Previously saved additional report notes</summary><div className="lab-disclosure-body"><div className="field"><label htmlFor="lab-limitations">Limitations & critical evaluation</label><textarea id="lab-limitations" rows={3} maxLength={6000} value={draft.limitations} onChange={(event) => update('limitations', event.target.value)} /></div></div></details>}
        <CourseworkScreenshots screenshots={state.screenshots} onChanged={updateScreenshots} busy={loading || save.pending} onBusyChange={setScreenshotBusy} />
        <CourseworkExport active={active} dirty={dirty} busy={loading || save.pending || screenshotBusy || Boolean(loadError)} />
      </section>
    </>}
  </section>
}
