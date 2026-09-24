import type { ReactNode } from 'react'
import { useEffect, useRef } from 'react'
import type { AnalyzerState, RecordedTest, TestReport } from './analyzerTypes'
import { ErrorNotice, Icon, Spinner } from './components'
import { AnalyzedSource, GrammarResults, ParseTrace, TableScroll, TokenStatistics, TokenTable } from './CourseworkResults'
import { TestStatistics } from './TestStatistics'
import { VocabularyVerdict } from './VocabularyVerdict'

export function Analysis({ result, report, lexicalSpec, analyzing, loading, loadError, inspecting, inspectError, grammarSettings, onCancel, onRefresh, onPage, onInspect, onRetryInspect, onUseText }: {
  result: RecordedTest | null
  report: TestReport | null
  lexicalSpec: AnalyzerState['lexical_spec']
  analyzing: boolean
  loading: boolean
  loadError: string
  inspecting: boolean
  inspectError: string
  grammarSettings?: ReactNode
  onCancel: () => void
  onRefresh: () => void
  onPage: (offset: number) => void
  onInspect: (id: string) => void
  onRetryInspect: () => void
  onUseText: (text: string) => void
}) {
  const details = useRef<HTMLElement>(null)
  const requestedInspection = useRef(false)
  useEffect(() => {
    if (result && requestedInspection.current) {
      requestedInspection.current = false
      details.current?.focus({ preventScroll: true })
      details.current?.scrollIntoView({ block: 'start', behavior: 'instant' })
    }
  }, [result])

  return <>
    <a className="text-button" href="#compiler">Back to Franc Analyzer<Icon name="arrow" size={16} /></a>
    {grammarSettings}
    {analyzing && <div className="lab-actions"><p className="lab-loading" role="status"><Spinner label="Running analysis" />Analyzing and recording this test...</p><button type="button" className="text-button" onClick={onCancel}>Stop waiting</button></div>}
    <ErrorNotice message={loadError} onRetry={onRefresh} />
    {loading && <p className="lab-loading" role="status"><Spinner label="Loading saved tests" />Loading all-test statistics...</p>}
    {report && <TestStatistics report={report} busy={loading} selectedId={result?.id} onRefresh={onRefresh} onPage={onPage} onInspect={(id) => { requestedInspection.current = true; onInspect(id) }} />}
    <ErrorNotice message={inspectError} onRetry={onRetryInspect} />
    {inspecting && <p className="lab-loading" role="status"><Spinner label="Loading recorded test" />Opening the saved snapshot...</p>}
    {result && <section ref={details} tabIndex={-1} className="lab-card selected-test" aria-labelledby="analysis-input-title">
      <div className="lab-card-heading"><div><span className="test-eyebrow">Selected saved test</span><h2 id="analysis-input-title">Analyzed sentence or word</h2><p>Recorded {new Date(result.created_at).toLocaleString()}. These are the original results, not a new analysis using today's settings.</p></div></div>
      <p className="lab-copy">Creator: {result.ownership.owner_name} · Shared with all signed-in users. Saved tests are immutable.</p>
      <AnalyzedSource text={result.text} />
      <VocabularyVerdict result={result.approval} empty={result.lexical.tokens.length === 0} />
      <div className="lab-actions"><button type="button" className="text-button" onClick={() => onUseText(result.text)}>Use as analyzer input<Icon name="arrow" size={16} /></button></div>
      <details className="lab-disclosure">
        <summary>Token details for this test</summary>
        <div className="lab-disclosure-body">
          <TokenTable tokens={result.lexical.tokens} />
          <dl className="lab-observations">
            <div><dt>Verb phrases</dt><dd>{result.lexical.verb_phrases.join(' / ') || 'None detected'}</dd></div>
            <div><dt>Slang expressions</dt><dd>{result.lexical.slang_expressions.join(' / ') || 'None detected'}</dd></div>
            <div><dt>Code-mixed spans</dt><dd>{result.lexical.code_mixed_spans.join(' / ') || 'None detected'}</dd></div>
          </dl>
          <TokenStatistics statistics={result.lexical.statistics} />
        </div>
      </details>
      <details className="lab-disclosure"><summary>Parser trace for this input</summary><div className="lab-disclosure-body"><h3>Separate CFG grammar check</h3><p className="lab-copy">This checks word order against the saved grammar. A grammar rejection does not change vocabulary approval.</p><ParseTrace result={result.parse} /></div></details>
      <details className="lab-disclosure">
        <summary>Saved grammar, transformations &amp; FIRST/FOLLOW</summary>
        <div className="lab-disclosure-body"><h3>Grammar used for this test</h3><pre className="lab-regex">{result.grammar_source}</pre><GrammarResults grammar={result.grammar} /></div>
      </details>
    </section>}
    <details className="lab-disclosure">
      <summary>Lexer rules &amp; limitations</summary>
      <div className="lab-disclosure-body">
        <h3>Current token boundary regex</h3><pre className="lab-regex">{lexicalSpec.token_pattern}</pre>
        <h3>Classification precedence</h3><ol className="lab-list">{lexicalSpec.classification_order.map((rule, index) => <li key={index}>{rule}</li>)}</ol>
        <TableScroll label="Lexer regular expression rules"><table className="lab-table"><thead><tr><th scope="col">Category</th><th scope="col">Regex pattern</th></tr></thead><tbody>{lexicalSpec.regex_rules.map((rule, index) => <tr key={index}><td><code>{rule.category}</code></td><td><code>{rule.pattern}</code></td></tr>)}</tbody></table></TableScroll>
        <div className="lab-two-columns"><div><h4>Verb-phrase lexicon</h4><p className="lab-copy">{lexicalSpec.verb_phrases.join(' / ') || 'No phrases specified'}</p></div><div><h4>Slang-phrase lexicon</h4><p className="lab-copy">{lexicalSpec.slang_phrases.join(' / ') || 'No phrases specified'}</p></div></div>
        <h3>Known limitations</h3><ul className="lab-list">{lexicalSpec.limitations.map((limitation, index) => <li key={index}>{limitation}</li>)}</ul>
      </div>
    </details>
  </>
}
