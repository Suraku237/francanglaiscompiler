import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'
import { ErrorNotice, Icon, Spinner, TokenAnalysis } from './components'
import { CourseworkExport, CourseworkScreenshots } from './CourseworkEvidence'
import { CorpusResults, GrammarResults, LexicalResults, ParseTrace, Requirements, TableScroll, TokenTable } from './CourseworkResults'
import type { CourseworkAnalysis, CourseworkState, ManualParse, Project, Screenshot } from './courseworkTypes'
import { defaultMetadata, MAX_TEXT } from './types'
import type { Analysis, IncomingText } from './types'
import { useRequest } from './useRequest'
import './coursework.css'

const terminals = ['NOUN', 'VERB', 'SLANG', 'PIDGIN_MARKER', 'FRENCH_FUNCTION_WORD', 'ENGLISH_FUNCTION_WORD', 'ENGLISH_VERB_LIKE', 'FRENCH_VERB_LIKE', 'UNKNOWN', 'NUMBER', 'PUNCTUATION']
const sections = [
  { id: 'lab-research', label: 'Research' },
  { id: 'lab-grammar', label: 'Grammar' },
  { id: 'lab-corpus', label: 'Corpus' },
  { id: 'lab-manual', label: 'Lexer & parser' },
  { id: 'lab-submission', label: 'Submission' },
]

function scrollToSection(id: string) {
  const section = document.getElementById(id)
  section?.scrollIntoView({ block: 'start' })
  section?.focus({ preventScroll: true })
}

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
  const appliedHandoff = useRef<number | null>(null)
  const manualInput = useRef<HTMLTextAreaElement>(null)
  const [screenshotBusy, setScreenshotBusy] = useState(false)
  const [resultsNote, setResultsNote] = useState('Run the local analysis to compute grammar steps, lexical tables and tests from your saved CSV.')
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
    if (loaded.current) setResultsNote('Saved collection evidence is refreshed when you return. Run the analysis again to test the current CSV; your editor draft is kept.')
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
      : incomingText.kind === 'history'
        ? 'Legacy source text copied unchanged. Historical output is not verified research data.'
        : 'Text copied unchanged into this manual draft. Review it, then explicitly run the lexer or parser; nothing has been saved.')
    manualInput.current?.scrollIntoView({ block: 'center' })
    manualInput.current?.focus({ preventScroll: true })
  }, [active, draft, incomingText, cancelParse, cancelLexical, clearParseError, clearLexicalError])

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
    setResultsNote('Evidence refreshed without replacing your editor draft. Analyze again to compute results from the current saved CSV.')
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

  const topicNames = [...new Set([...defaultMetadata.categories.filter((name) => name !== 'Other'), ...Object.keys(state?.stats.topic_counts ?? {}), ...(state?.stats.missing_topics ?? [])])]
  const suggestedTopics = defaultMetadata.categories.filter((name) => name !== 'Other')
  const observedTopics = suggestedTopics.filter((topic) => (state?.stats.topic_counts[topic] ?? 0) > 0).length

  return <section className="page coursework-page" aria-labelledby="coursework-title">
    <div className="page-intro compact-intro lab-intro">
      <div><div className="eyebrow"><span className="eyebrow-line" />REAL WORDS. TRACEABLE RULES.</div><h1 id="coursework-title">Compiler lab</h1><p>Your CS4110 workspace. Collect honestly, build a grammar, and inspect every step.</p></div>
      <span className="lab-local-seal"><Icon name="code" size={25} /><span>RULE-BASED COMPILER<strong>No model or provider calls</strong></span></span>
    </div>
    <div className="lab-toolbar"><nav className="lab-section-nav" aria-label="Compiler lab sections">{sections.map((section, index) => <button type="button" key={section.id} disabled={!state} onClick={() => scrollToSection(section.id)}><span>0{index + 1}</span>{section.label}</button>)}</nav><button type="button" className="icon-button" aria-label="Refresh saved coursework evidence, preserve editor draft" title="Refresh saved evidence; preserve draft" disabled={loading || save.pending} onClick={refreshAll}><Icon name="refresh" size={18} /></button></div>
    <ErrorNotice message={loadError} onRetry={refreshAll} />
    {loading && <p className="lab-loading" role="status"><Spinner label="Loading saved coursework evidence" />Refreshing local evidence. Editor changes are kept.</p>}
    {!state || !draft ? !loading && !loadError ? <p className="lab-copy">Open Compiler lab to load your private project.</p> : null : <>
      {state.stats.total === 0 && <div className="notice notice-subtle"><Icon name="info" size={20} /><div><strong>No collected corpus in this project yet.</strong><p>Import your manually transcribed text file or add genuine statements in Collection. The starter grammar and synthetic references do not count as collected evidence. You can still explore grammar computations and manual tests with this limitation visible.</p><div className="lab-actions"><a className="text-button" href="#imports">Import a transcript<Icon name="arrow" size={15} /></a><a className="text-button" href="#collection">Open Collection<Icon name="arrow" size={15} /></a></div></div></div>}
      <div className="lab-savebar">
        <div><strong>{dirty ? 'Unsaved project changes' : 'No unsaved editor changes'}</strong><span>Save includes group details, grammar and report writing. Save once before your first export; analysis does not save.</span></div>
        <button type="button" className="button button-primary" onClick={saveProject} disabled={save.pending || loading}>{save.pending ? <Spinner label="Saving coursework project" /> : <Icon name="check" size={17} />}{save.pending ? 'Saving…' : 'Save project'}</button>
      </div>
      <ErrorNotice message={save.error} />
      {notice && <p className="lab-save-notice" role="status">{notice}</p>}
      <div className="lab-metrics" aria-label="Saved coursework evidence counts">
        <div><span className="small-caps">SAVED STATEMENTS</span><strong>{state.stats.sentences}<small> / {state.brief.statement_target.join('–')}</small></strong><p>{state.stats.total} total CSV records · counts do not verify provenance</p></div>
        <div><span className="small-caps">SUGGESTED TOPIC COVERAGE</span><strong>{observedTopics}<small> / {suggestedTopics.length}</small></strong><p>{state.stats.missing_topics.length ? `${state.stats.missing_topics.length} suggested topics not yet represented` : 'Topic counts present; review the source evidence'}</p></div>
        <div><span className="small-caps">RESEARCH ATTESTATION</span><strong className="lab-metric-word">{state.project.manual_transcription_confirmed ? 'Declared' : 'Not yet'}</strong><p>A saved declaration, not independently verified authenticity</p></div>
      </div>

      <section id="lab-research" className="lab-card" tabIndex={-1} aria-labelledby="lab-research-title">
        <div className="lab-card-heading"><span className="lab-section-number">01</span><div><h2 id="lab-research-title">Start with the real words.</h2><p>The brief, your group, and the evidence you still need.</p></div></div>
        <div className="lab-brief"><strong>{state.brief.course} · {state.brief.title}</strong><span>{state.brief.due ? `Due: ${state.brief.due}` : 'Check the assignment for the submission date'}</span><ul className="lab-list"><li>{state.brief.group_size} students · {state.brief.statement_target.join('–')} manually transcribed real statements. Use the suggested topics to guide collection, not to invent missing data.</li><li>A {state.brief.report_pages.join('–')}-page report (maximum 30), source code and own-data tests.</li><li>{state.brief.presentation_minutes}-minute presentation and demo · about {state.brief.per_student_minutes} minutes per student.</li></ul></div>
        <details className="lab-disclosure">
          <summary>Coursework requirement map · saved evidence, not a grade</summary>
          <div className="lab-disclosure-body"><p className="lab-copy">These checks come from the server’s saved profile and CSV. “Evidence available” is not a claim of authenticity or a finished submission. Refresh after changing the collection; human review is still required.</p><Requirements items={state.requirements} /></div>
        </details>
        <div className="lab-result-heading"><h3>Suggested everyday topics</h3><a className="text-button" href="#collection">Open Collection<Icon name="arrow" size={15} /></a></div>
        <div className="lab-topics">{topicNames.map((topic) => {
          const count = state.stats.topic_counts[topic] ?? 0
          return <div key={topic} className={count ? 'has-evidence' : ''}><Icon name={count ? 'check' : 'plus'} size={15} /><span>{topic}</span><strong>{count}</strong></div>
        })}</div>
        <p className="lab-copy">Manage real statements in Collection; choose “Sentence,” annotate a topic, and record source context and contributor. Demo, translated or generated text must not be passed off as collected research data. Keep identifying information out of shared evidence unless appropriate permission is in place.</p>
        <div className="lab-members">{Array.from({ length: state.brief.group_size }, (_, index) => <div className="field" key={index}><label htmlFor={`lab-member-${index}`}>Group member {index + 1}</label><input id={`lab-member-${index}`} value={draft.group_members[index] ?? ''} maxLength={100} onChange={(event) => update('group_members', Array.from({ length: state.brief.group_size }, (_, member) => member === index ? event.target.value : draft.group_members[member] ?? ''))} placeholder="Name or student identifier" /></div>)}</div>
        <label className="lab-attestation"><input type="checkbox" checked={draft.manual_transcription_confirmed} onChange={(event) => update('manual_transcription_confirmed', event.target.checked)} /><span>We manually transcribed real statements; generated/demo text is not research data<strong>Check only if true for your submitted dataset. The application cannot verify this declaration.</strong></span></label>
        <div className="field"><label htmlFor="lab-method">Collection method & provenance</label><textarea id="lab-method" rows={4} maxLength={6000} value={draft.collection_method} onChange={(event) => update('collection_method', event.target.value)} placeholder="Describe where, when and how your group heard and manually transcribed the statements, the contexts, permissions, and each member’s contribution. Leave unknown facts unknown." /><span className="field-hint">{draft.collection_method.length.toLocaleString()} / 6,000 characters · saved privately with this project</span></div>
      </section>

      <section id="lab-grammar" className="lab-card" tabIndex={-1} aria-labelledby="lab-grammar-title">
        <div className="lab-card-heading"><span className="lab-section-number">02</span><div><h2 id="lab-grammar-title">Make the rules your own.</h2><p>An editable CFG, real transformations, and a computed predictive table.</p></div></div>
        <div className="notice notice-subtle"><Icon name="info" size={18} /><span>The supplied default grammar is a <strong>starter, not a grammar derived from your data</strong>. Replace or justify it using observed patterns. A broad grammar accepting everything is not evidence of meaningful syntax coverage.</span></div>
        <details className="lab-disclosure">
          <summary>Grammar notation & available lexical terminals</summary>
          <div className="lab-disclosure-body"><p className="lab-copy">Write one rule per line: <code>Nonterminal -&gt; symbol symbol | epsilon</code>. The first left-hand side is the start symbol. Nonterminals are identifiers; terminals must be the category names below. Do not use quoted words or literal punctuation.</p><div className="lab-terminal-list">{terminals.map((terminal) => <code key={terminal}>{terminal}</code>)}</div><p className="lab-copy">The parser operates over categories, not word spellings. Use PUNCTUATION for punctuation tokens. Write epsilon for an empty production, displayed as ε in results. UNKNOWN is a lexer coverage limitation, not a linguistic verdict.</p></div>
        </details>
        <div className="field"><label htmlFor="lab-grammar-input">Context-free grammar</label><textarea id="lab-grammar-input" className="lab-grammar-input" value={draft.grammar} rows={10} maxLength={12000} spellCheck={false} autoCapitalize="off" autoCorrect="off" onChange={(event) => update('grammar', event.target.value)} aria-describedby="lab-grammar-hint" /><span id="lab-grammar-hint" className="field-hint">{draft.grammar.length.toLocaleString()} / 12,000 characters · edits invalidate computations; Save project persists this grammar</span></div>
        <div className="field"><label htmlFor="lab-rationale">Why this grammar fits your observations</label><textarea id="lab-rationale" rows={3} maxLength={6000} value={draft.grammar_rationale} onChange={(event) => update('grammar_rationale', event.target.value)} placeholder="Link productions to patterns and record IDs in your own data. Explain scope, rejected forms, and any deliberate simplifications." /><span className="field-hint">{draft.grammar_rationale.length.toLocaleString()} / 6,000 characters</span></div>
        <div className="lab-compute-bar"><p>Uses the <strong>current editor grammar + saved CSV in this project</strong>. No generated samples or provider calls. Does not save project edits.</p><div className="lab-actions">{analyzing && <button type="button" className="text-button" onClick={cancelAnalysis}>Cancel</button>}<button type="button" className="button button-primary" disabled={!draft.grammar.trim() || analyzing || loading} onClick={analyze}>{analyzing ? <Spinner label="Computing grammar and corpus tests" /> : <Icon name="code" size={18} />}{analyzing ? 'Computing…' : 'Analyze grammar & saved corpus'}</button></div></div>
        <ErrorNotice message={analysisError} />
        {resultsNote && !analysis && <p className="lab-copy lab-empty" role="status">{resultsNote}</p>}
        {analysis && <><GrammarResults grammar={analysis.grammar} /><details className="lab-disclosure"><summary>Requirement checks for this analyzed grammar version</summary><div className="lab-disclosure-body"><p className="lab-copy">Computed using this editor grammar and the saved research profile. Export still uses the saved grammar, so save any edits before exporting.</p><Requirements items={analysis.requirements} /></div></details></>}
      </section>

      <section id="lab-corpus" className="lab-card" tabIndex={-1} aria-labelledby="lab-corpus-title">
        <div className="lab-card-heading"><span className="lab-section-number">03</span><div><h2 id="lab-corpus-title">Read the evidence.</h2><p>The custom lexer, observed variation, and your own-data acceptance tests.</p></div></div>
        <details className="lab-disclosure">
          <summary>Custom lexer specification · regex & classification order</summary>
          <div className="lab-disclosure-body">
            <h4>Token boundary regex</h4><pre className="lab-regex">{state.lexical_spec.token_pattern}</pre>
            <h4>Classification precedence</h4><ol className="lab-list">{state.lexical_spec.classification_order.map((rule, index) => <li key={index}>{rule}</li>)}</ol>
            <TableScroll label="Lexer regular expression rules"><table className="lab-table"><thead><tr><th scope="col">Category</th><th scope="col">Regex pattern</th></tr></thead><tbody>{state.lexical_spec.regex_rules.map((rule, index) => <tr key={index}><td><code>{rule.category}</code></td><td><code>{rule.pattern}</code></td></tr>)}</tbody></table></TableScroll>
            <div className="lab-two-columns"><div><h4>Verb-phrase lexicon</h4><p className="lab-copy">{state.lexical_spec.verb_phrases.join(' · ') || 'No phrases specified'}</p></div><div><h4>Slang-phrase lexicon</h4><p className="lab-copy">{state.lexical_spec.slang_phrases.join(' · ') || 'No phrases specified'}</p></div></div>
            <h4>Known limitations</h4><ul className="lab-list">{state.lexical_spec.limitations.map((limitation, index) => <li key={index}>{limitation}</li>)}</ul>
            <p className="lab-copy">These are the backend’s implemented lexer rules, not learned linguistic judgments. The actual lexer source is included in the export.</p>
          </div>
        </details>
        {analysis ? <><LexicalResults lexical={analysis.lexical} /><CorpusResults tests={analysis.tests} summary={analysis.summary} onUseText={(text) => { changeTestText(text); scrollToSection('lab-manual') }} /></> : <div className="lab-empty-panel"><Icon name="collection" size={28} /><h3>Your corpus, not a substitute.</h3><p>Run “Analyze grammar & saved corpus” above to populate token tables, frequencies, variation candidates, acceptance decisions and traces.</p><button type="button" className="text-button" onClick={() => scrollToSection('lab-grammar')}>Go to grammar<Icon name="arrow" size={15} /></button></div>}
      </section>

      <section id="lab-manual" className="lab-card" tabIndex={-1} aria-labelledby="lab-manual-title">
        <div className="lab-card-heading"><span className="lab-section-number">04</span><div><h2 id="lab-manual-title">Follow every decision.</h2><p>Try one input against the editor grammar. Nothing is added to your dataset.</p></div></div>
        <form onSubmit={(event) => {
          event.preventDefault()
          if (!draft.grammar.trim() || parsing || testText.length > MAX_TEXT) return
          setManual(null)
          void runParse((signal) => api<ManualParse>('/coursework/parse', { method: 'POST', body: { grammar: draft.grammar, text: testText }, signal, timeout: 30000 }), setManual)
        }}>
          {handoffNote && <p className="notice notice-subtle" role="status">{handoffNote}</p>}
          <div className="field"><label htmlFor="lab-test-text">Manual parser test</label><textarea ref={manualInput} id="lab-test-text" rows={4} maxLength={MAX_TEXT} value={testText} onChange={(event) => changeTestText(event.target.value)} placeholder="Type or paste one input. You can also leave it empty to test epsilon." aria-describedby="lab-test-hint" /><span id="lab-test-hint" className="field-hint">{testText.length.toLocaleString()} / 4,000 characters · raw spacing preserved · empty parser input allowed · this field is not saved</span></div>
          {testText.length > MAX_TEXT && <ErrorNotice message="This source exceeds 4,000 characters. It was kept unchanged; select a shorter passage before computing." />}
          <div className="lab-actions"><p className="lab-copy">Rule-based lexing and table-driven parsing on this server.</p><div className="lab-actions">
            {(parsing || lexing) && <button type="button" className="text-button" onClick={() => { cancelParse(); cancelLexical() }}>Cancel computation</button>}
            <button type="button" className="button button-secondary" disabled={!testText.trim() || testText.length > MAX_TEXT || lexing} onClick={() => {
              setLexical(null)
              void runLexical((signal) => api<Analysis>('/analyze', { method: 'POST', body: { text: testText }, signal }), setLexical)
            }}>{lexing ? <Spinner label="Analyzing manual tokens" /> : <Icon name="code" size={17} />}{lexing ? 'Lexing…' : 'Analyze tokens'}</button>
            <button type="submit" className="button button-primary" disabled={!draft.grammar.trim() || parsing || testText.length > MAX_TEXT}>{parsing ? <Spinner label="Parsing manual test" /> : <Icon name="code" size={17} />}{parsing ? 'Parsing…' : 'Parse test input'}</button>
          </div></div>
        </form>
        <ErrorNotice message={lexicalError} />
        {lexical && <div className="lab-results"><h3>Manual lexical result</h3><TokenAnalysis analysis={lexical} /></div>}
        <ErrorNotice message={parseError} />
        {manual && <div className="lab-results"><h3>Manual test result</h3><TokenTable tokens={manual.tokens} /><ParseTrace result={manual.parse} /><p className="lab-copy">ACCEPT / REJECT describes this grammar’s coverage of the token stream, not whether the speaker’s language is correct.</p></div>}
      </section>

      <section id="lab-submission" className="lab-card" tabIndex={-1} aria-labelledby="lab-submission-title">
        <div className="lab-card-heading"><span className="lab-section-number">05</span><div><h2 id="lab-submission-title">Tell the whole story.</h2><p>Write the linguistic discussion, attach actual screenshots, and prepare your deliverables.</p></div></div>
        <div className="field"><label htmlFor="lab-discussion">Linguistic discussion</label><textarea id="lab-discussion" rows={6} maxLength={12000} value={draft.discussion} onChange={(event) => update('discussion', event.target.value)} placeholder="Use observed examples and record IDs to discuss nouns, verbs, slang, code mixing, spelling variation, cultural context, and where lexer labels or grammar decisions need interpretation. Do not invent collection findings." /><span className="field-hint">{draft.discussion.length.toLocaleString()} / 12,000 characters</span></div>
        <div className="field"><label htmlFor="lab-limitations">Limitations & critical evaluation</label><textarea id="lab-limitations" rows={4} maxLength={6000} value={draft.limitations} onChange={(event) => update('limitations', event.target.value)} placeholder="Discuss sample size, topic balance, transcription uncertainty, lexicon coverage, grammar scope, ambiguous labels, and any unresolved table conflicts or parsing failures." /><span className="field-hint">{draft.limitations.length.toLocaleString()} / 6,000 characters</span></div>
        <div className="lab-actions lab-writing-save"><p className="lab-copy">Your writing is private to this project and is included in the report draft after saving.</p><button type="button" className="button button-secondary" disabled={save.pending || loading} onClick={saveProject}>{save.pending ? <Spinner label="Saving project writing" /> : <Icon name="check" size={17} />}Save project & writing</button></div>
        <CourseworkScreenshots screenshots={state.screenshots} onChanged={updateScreenshots} busy={loading || save.pending} onBusyChange={setScreenshotBusy} />
        <CourseworkExport active={active} dirty={dirty} busy={loading || save.pending || screenshotBusy || Boolean(loadError)} />
      </section>
    </>}
  </section>
}
