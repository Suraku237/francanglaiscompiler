import type { ReactNode } from 'react'
import { Icon } from './components'
import type { CorpusTest, GrammarAnalysis, LexicalReport, LexicalStatistics, LexicalToken, ParseResult, Rules, TokenCount } from './courseworkTypes'

export function TableScroll({ label, children }: { label: string; children: ReactNode }) {
  return <div className="lab-table-scroll" role="region" aria-label={label} tabIndex={0}>{children}</div>
}

function productionText(symbols: string[]) {
  return symbols.length ? symbols.join(' ') : 'ε'
}

function RuleList({ rules }: { rules: Rules }) {
  return <div className="lab-rules">{Object.entries(rules).map(([name, productions]) =>
    <div key={name}><strong>{name}</strong><span aria-label="produces"> → </span><code>{productions.map(productionText).join(' | ') || '∅'}</code></div>,
  )}</div>
}

export function GrammarResults({ grammar }: { grammar: GrammarAnalysis }) {
  const columns = [...new Set([...grammar.terminals, '$', ...Object.values(grammar.table).flatMap(Object.keys)])]
  return <div className="lab-results">
    <div className="lab-result-heading"><h3>Computed grammar</h3><span className={`lab-status ${grammar.is_ll1 ? 'ready' : 'needs_input'}`}>{grammar.is_ll1 ? 'LL(1) · no table conflicts' : 'Not LL(1) · inspect conflicts'}</span></div>
    <p className="lab-copy">Start symbol: <code>{grammar.start_symbol}</code> · {grammar.nonterminals.length} nonterminals · {grammar.terminals.length} terminals. These are rule-based algorithm results, not judgments about a speaker’s language.</p>
    {grammar.warnings.length > 0 && <div className="notice notice-subtle"><Icon name="info" size={18} /><ul className="lab-list">{grammar.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></div>}
    <details className="lab-disclosure" open>
      <summary>Original → transformed grammar</summary>
      <div className="lab-disclosure-body lab-two-columns"><div><h4>Original rules</h4><RuleList rules={grammar.original} /></div><div><h4>Transformed rules</h4><RuleList rules={grammar.transformed} /></div></div>
    </details>
    <details className="lab-disclosure" open>
      <summary>Left-recursion removal & left factoring · {grammar.steps.length} steps</summary>
      <div className="lab-disclosure-body">
        {!grammar.steps.length && <p className="lab-copy">No transformations were required for this grammar.</p>}
        {grammar.steps.map((step, index) => <details className="lab-step" key={index}>
          <summary><span className="lab-step-number">{index + 1}</span>{step.operation.replaceAll('_', ' ')}</summary>
          <p className="lab-copy">{step.description}</p>
          <div className="lab-two-columns"><div><h4>Before</h4><RuleList rules={step.before} /></div><div><h4>After</h4><RuleList rules={step.after} /></div></div>
        </details>)}
      </div>
    </details>
    <details className="lab-disclosure" open>
      <summary>FIRST & FOLLOW sets</summary>
      <div className="lab-disclosure-body">
        <p className="lab-copy">ε (returned as “epsilon”) is the empty production; $ is the end-of-input marker. Sets below describe the transformed grammar.</p>
        <TableScroll label="Computed FIRST and FOLLOW sets"><table className="lab-table"><thead><tr><th scope="col">Nonterminal</th><th scope="col">FIRST</th><th scope="col">FOLLOW</th></tr></thead><tbody>
          {grammar.nonterminals.map((symbol) => <tr key={symbol}><th scope="row"><code>{symbol}</code></th><td><code>{`{ ${(grammar.first[symbol] ?? []).join(', ')} }`}</code></td><td><code>{`{ ${(grammar.follow[symbol] ?? []).join(', ')} }`}</code></td></tr>)}
        </tbody></table></TableScroll>
      </div>
    </details>
    <details className="lab-disclosure" open>
      <summary>Predictive parsing table · {grammar.conflicts.length} conflicts</summary>
      <div className="lab-disclosure-body">
        <p className="lab-copy">Rows are nonterminals; columns are lookahead tokens. — means no production: reject that configuration. Scroll horizontally to inspect every terminal.</p>
        <TableScroll label="LL(1) predictive parsing table, scroll horizontally"><table className="lab-table lab-predictive-table"><thead><tr><th scope="col">Nonterminal ↓ / Lookahead →</th>{columns.map((terminal) => <th scope="col" key={terminal}><code>{terminal}</code></th>)}</tr></thead><tbody>
          {grammar.nonterminals.map((symbol) => <tr key={symbol}><th scope="row"><code>{symbol}</code></th>{columns.map((terminal) => {
            const conflict = grammar.conflicts.find((item) => item.nonterminal === symbol && item.terminal === terminal)
            const production = grammar.table[symbol]?.[terminal]
            return <td key={terminal} className={conflict ? 'lab-conflict-cell' : ''}>{conflict
              ? <><strong>Conflict</strong>{conflict.productions.map((rule, index) => <code key={index}>{symbol} → {productionText(rule)}</code>)}</>
              : production !== undefined ? <code>{symbol} → {productionText(production)}</code> : <span aria-label="No production">—</span>}</td>
          })}</tr>)}
        </tbody></table></TableScroll>
        {grammar.conflicts.length > 0 && <div className="notice notice-error"><Icon name="info" size={18} /><div><strong>A deterministic LL(1) choice is not available.</strong><ul className="lab-list">{grammar.conflicts.map((item, index) => <li key={index}><code>M[{item.nonterminal}, {item.terminal}]</code>: {item.productions.map((rule) => `${item.nonterminal} → ${productionText(rule)}`).join(' versus ')}</li>)}</ul><p>Revise the grammar and analyze again. Do not treat a conflicting table as a valid LL(1) parser.</p></div></div>}
      </div>
    </details>
  </div>
}

export function TokenTable({ tokens }: { tokens: LexicalToken[] }) {
  if (!tokens.length) return <p className="lab-copy">No lexical tokens. The parser will see only $.</p>
  return <TableScroll label="Lexical tokens in source order"><table className="lab-table"><thead><tr><th scope="col">#</th><th scope="col">Observed text</th><th scope="col">Lexer category</th></tr></thead><tbody>
    {tokens.map((token, index) => <tr key={index}><td>{index + 1}</td><td>{token.text}</td><td><code>{token.category}</code></td></tr>)}
  </tbody></table></TableScroll>
}

export function ParseTrace({ result }: { result: ParseResult }) {
  return <div className="lab-trace">
    <div className="lab-result-heading"><span className={`lab-status ${result.accepted ? 'ready' : 'needs_input'}`}>{result.accepted ? 'ACCEPT' : 'REJECT'}</span><span className="lab-copy">{result.consumed} tokens consumed</span></div>
    {result.error && <p className="lab-parse-error">{result.error}</p>}
    <p className="lab-copy">Stack and remaining input are shown in the order reported by the local parser; actions describe each match, expansion, or stop.</p>
    {result.trace.length ? <TableScroll label="Table-driven parser step trace"><table className="lab-table lab-trace-table"><thead><tr><th scope="col">Step</th><th scope="col">Stack</th><th scope="col">Remaining input</th><th scope="col">Action</th></tr></thead><tbody>
      {result.trace.map((step, index) => <tr key={index}><td>{index + 1}</td><td><code>{step.stack.join(' ') || '∅'}</code></td><td><code>{step.remaining.join(' ') || '∅'}</code></td><td>{step.action}</td></tr>)}
    </tbody></table></TableScroll> : <p className="lab-copy">No parsing steps were returned. Check the grammar and any error above.</p>}
  </div>
}

function CountTable({ rows, label }: { rows: TokenCount[]; label: string }) {
  return rows.length ? <TableScroll label={label}><table className="lab-table"><thead><tr><th scope="col">Token</th><th scope="col">Count</th></tr></thead><tbody>
    {rows.map((row, index) => <tr key={index}><td>{row.token}</td><td>{row.count}</td></tr>)}
  </tbody></table></TableScroll> : <p className="lab-copy">No observations in this analysis.</p>
}

export function LexicalResults({ lexical }: { lexical: LexicalReport }) {
  return <div className="lab-results">
    <div className="lab-result-heading"><h3>Saved-statement token analysis</h3><span className="lab-status review">{lexical.total_tokens.toLocaleString()} tokens · rule-based labels</span></div>
    <p className="lab-copy">Only saved collection entries in the selected project are analyzed. Category labels and code-mixing candidates need linguistic review; they are not proof of a speaker’s intent.</p>
    <details className="lab-disclosure" open>
      <summary>Statement token tables, verbs, slang & code mixing · {lexical.statements.length} records</summary>
      <div className="lab-disclosure-body">
        {!lexical.statements.length && <p className="lab-copy">No saved records. Add your real, manually transcribed statements in Collection.</p>}
        {lexical.statements.map((statement, index) => <details className="lab-statement" key={`${statement.id}-${index}`}>
          <summary><span className="lab-step-number">{index + 1}</span><span>{statement.text || '(empty record)'}<small>{statement.category || 'Uncategorized'}</small></span></summary>
          <div className="lab-disclosure-body"><p className="lab-record-id">Record: {statement.id}</p><TokenTable tokens={statement.tokens} />
            <dl className="lab-observations"><div><dt>Verb phrases</dt><dd>{statement.verb_phrases.join(' · ') || 'None detected'}</dd></div><div><dt>Slang expressions</dt><dd>{statement.slang_expressions.join(' · ') || 'None detected'}</dd></div><div><dt>Code-mixed spans</dt><dd>{statement.code_mixed_spans.join(' · ') || 'None detected'}</dd></div></dl>
          </div>
        </details>)}
      </div>
    </details>
    <TokenStatistics statistics={lexical} />
  </div>
}

export function TokenStatistics({ statistics }: { statistics: LexicalStatistics }) {
  return <div className="lab-results">
    <div className="lab-result-heading"><h3>Token statistics</h3><span className="lab-copy">{statistics.total_tokens.toLocaleString()} tokens · {statistics.frequencies.length.toLocaleString()} distinct forms</span></div>
    <p className="lab-copy">Frequencies combine letter case. Numbers, punctuation and UNKNOWN tokens are included. Original spelling is preserved in token tables and variation groups.</p>
    <TableScroll label="Token category frequencies"><table className="lab-table"><thead><tr><th scope="col">Category</th><th scope="col">Count</th></tr></thead><tbody>
      {Object.entries(statistics.category_counts).map(([category, count]) => <tr key={category}><th scope="row"><code>{category}</code></th><td>{count}</td></tr>)}
      {!statistics.total_tokens && <tr><td colSpan={2}>No token categories were observed.</td></tr>}
    </tbody></table></TableScroll>
    <div className="lab-two-columns">
      <details className="lab-disclosure" open><summary>Token frequencies · {statistics.frequencies.length} forms</summary><div className="lab-disclosure-body"><CountTable rows={statistics.frequencies} label="Observed token frequencies" /></div></details>
      <details className="lab-disclosure"><summary>Unknown tokens · {statistics.unknown_tokens.length} forms</summary><div className="lab-disclosure-body"><p className="lab-copy">UNKNOWN means the custom lexer has no matching category, not that the word is invalid.</p><CountTable rows={statistics.unknown_tokens} label="Unknown token frequencies" /></div></details>
    </div>
    <details className="lab-disclosure" open>
      <summary>Observed spelling-variation candidates · {statistics.variations.length} groups</summary>
      <div className="lab-disclosure-body"><p className="lab-copy">These are observed orthographic candidates grouped by normalization, not verified semantic equivalents. Explain any equivalence using your own context and evidence.</p>
        {statistics.variations.length ? <TableScroll label="Observed orthographic variation candidates"><table className="lab-table"><thead><tr><th scope="col">Normalized form</th><th scope="col">Observed spellings (counts)</th></tr></thead><tbody>
          {statistics.variations.map((variation, index) => <tr key={index}><td><code>{variation.normalized}</code></td><td>{variation.forms.map((form) => `${form.text} (${form.count})`).join(' · ')}</td></tr>)}
        </tbody></table></TableScroll> : <p className="lab-copy">No variation candidates were observed in these tokens.</p>}
      </div>
    </details>
  </div>
}

export function CorpusResults({ tests, summary, onUseText }: {
  tests: CorpusTest[]
  summary: { total: number; accepted: number; rejected: number }
  onUseText: (text: string) => void
}) {
  return <div className="lab-results" role="region" aria-label="Saved Collection parser results">
    <div className="lab-result-heading"><h3>Own-data acceptance tests</h3><span className="lab-copy">{summary.total} tested · {summary.accepted} accepted · {summary.rejected} rejected</span></div>
    <p className="lab-copy">Acceptance means “matches this grammar over these token categories.” Rejection does not mean the speaker or their Francanglais is wrong. Inspect the grammar’s scope and lexer limitations.</p>
    {!tests.length && <div className="notice notice-subtle"><Icon name="collection" size={19} /><span>No corpus test cases yet. No demo or generated statements are substituted for your own data.</span></div>}
    {tests.map((test, index) => <details className="lab-statement" key={`${test.id}-${index}`}>
      <summary><span className={`lab-status ${test.accepted ? 'ready' : 'needs_input'}`}>{test.accepted ? 'ACCEPT' : 'REJECT'}</span><span>{test.text || '(empty record)'}</span></summary>
      <div className="lab-disclosure-body"><div className="lab-result-heading"><span className="lab-record-id">Record: {test.id}</span><button type="button" className="text-button" onClick={() => onUseText(test.text)}>Use as analyzer input<Icon name="arrow" size={15} /></button></div><ParseTrace result={test} /></div>
    </details>)}
  </div>
}
