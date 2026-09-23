import type { AnalyzerResult, AnalyzerState } from './analyzerTypes'
import { Icon, Spinner } from './components'
import { CorpusResults, GrammarResults, LexicalResults, ParseTrace, TableScroll, TokenStatistics, TokenTable } from './CourseworkResults'

export function Analysis({ result, lexicalSpec, analyzing, onCancel, onUseText }: {
  result: AnalyzerResult | null
  lexicalSpec: AnalyzerState['lexical_spec']
  analyzing: boolean
  onCancel: () => void
  onUseText: (text: string) => void
}) {
  return <>
    <a className="text-button" href="#compiler">Back to Franc Analyzer<Icon name="arrow" size={16} /></a>
    {analyzing && <div className="lab-actions"><p className="lab-loading" role="status"><Spinner label="Running analysis" />Analyzing the input and saved Collection...</p><button type="button" className="text-button" onClick={onCancel}>Cancel analysis</button></div>}
    {!result && !analyzing && <div className="lab-empty-panel">
      <Icon name="chart" size={28} /><h2>No completed analysis</h2>
      <p>Enter a sentence and select Analyze in Franc Analyzer. Its token details and saved Collection statistics will appear here separately. Nothing is saved or computed just by opening this page.</p>
      <a className="button button-primary" href="#compiler">Analyze a sentence<Icon name="arrow" size={16} /></a>
    </div>}
    {result && <>
      <p className="lab-copy">Results from your latest run in this tab. The sentence below is not added to Collection. Run Analyze again after changing your input, vocabulary or grammar.</p>
      <section className="lab-card" aria-labelledby="analysis-input-title">
        <div className="lab-card-heading"><div><h2 id="analysis-input-title">Analyzed sentence</h2><p>Tokens appear in source order with the exact categories passed to the parser.</p></div></div>
        <p className="analysis-source" aria-label="Analyzed source text">{result.text || '(empty input)'}</p>
        <TokenTable tokens={result.lexical.tokens} />
        <dl className="lab-observations">
          <div><dt>Verb phrases</dt><dd>{result.lexical.verb_phrases.join(' / ') || 'None detected'}</dd></div>
          <div><dt>Slang expressions</dt><dd>{result.lexical.slang_expressions.join(' / ') || 'None detected'}</dd></div>
          <div><dt>Code-mixed spans</dt><dd>{result.lexical.code_mixed_spans.join(' / ') || 'None detected'}</dd></div>
        </dl>
        <TokenStatistics statistics={result.lexical.statistics} />
        <details className="lab-disclosure">
          <summary>Parser trace for this sentence</summary>
          <div className="lab-disclosure-body"><ParseTrace result={result.parse} /></div>
        </details>
      </section>
      <details className="lab-disclosure analysis-corpus">
        <summary>Saved Collection - {result.corpus.lexical.statements.length} records</summary>
        <div className="lab-disclosure-body" role="region" aria-label="Saved Collection results">
          <p className="lab-copy">A separate snapshot of all saved entries in this project, including Words, Phrases and Sentences. These counts do not include the unsaved analyzer input.</p>
          <LexicalResults lexical={result.corpus.lexical} />
          <CorpusResults tests={result.corpus.tests} summary={result.corpus.summary} onUseText={onUseText} />
        </div>
      </details>
      <section className="lab-card" aria-labelledby="analysis-grammar-title">
        <div className="lab-card-heading"><div><h2 id="analysis-grammar-title">Syntactic analysis</h2><p>{result.grammar.is_ll1 ? 'The transformed grammar has no LL(1) table conflicts.' : 'The grammar has conflicts or unresolved recursion. Inspect the details before relying on a parse.'}</p></div></div>
        <details className="lab-disclosure"><summary>Transformations, FIRST/FOLLOW &amp; LL(1) table</summary><div className="lab-disclosure-body"><GrammarResults grammar={result.grammar} /></div></details>
      </section>
    </>}
    <details className="lab-disclosure">
      <summary>Lexer rules &amp; limitations</summary>
      <div className="lab-disclosure-body">
        <h3>Token boundary regex</h3><pre className="lab-regex">{lexicalSpec.token_pattern}</pre>
        <h3>Classification precedence</h3><ol className="lab-list">{lexicalSpec.classification_order.map((rule, index) => <li key={index}>{rule}</li>)}</ol>
        <TableScroll label="Lexer regular expression rules"><table className="lab-table"><thead><tr><th scope="col">Category</th><th scope="col">Regex pattern</th></tr></thead><tbody>{lexicalSpec.regex_rules.map((rule, index) => <tr key={index}><td><code>{rule.category}</code></td><td><code>{rule.pattern}</code></td></tr>)}</tbody></table></TableScroll>
        <div className="lab-two-columns"><div><h4>Verb-phrase lexicon</h4><p className="lab-copy">{lexicalSpec.verb_phrases.join(' / ') || 'No phrases specified'}</p></div><div><h4>Slang-phrase lexicon</h4><p className="lab-copy">{lexicalSpec.slang_phrases.join(' / ') || 'No phrases specified'}</p></div></div>
        <h3>Known limitations</h3><ul className="lab-list">{lexicalSpec.limitations.map((limitation, index) => <li key={index}>{limitation}</li>)}</ul>
      </div>
    </details>
  </>
}
