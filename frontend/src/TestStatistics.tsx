import type { TestReport } from './analyzerTypes'
import type { TokenCount } from './courseworkTypes'
import { Icon } from './components'
import { TableScroll } from './CourseworkResults'

function FrequencyChart({ title, description, rows }: { title: string; description: string; rows: TokenCount[] }) {
  const maximum = rows.reduce((value, row) => Math.max(value, row.count), 0)
  return <section className="test-frequency-panel" aria-label={title}>
    <h3>{title}</h3><p className="lab-copy">{description}</p>
    {rows.length ? <TableScroll label={`${title} counts`}><table className="lab-table test-frequency-table">
      <thead><tr><th scope="col">Term</th><th scope="col">Count</th></tr></thead>
      <tbody>{rows.map((row) => <tr key={row.token}>
        <th scope="row"><code>{row.token}</code></th>
        <td><span className="test-frequency-value"><span className="test-frequency-bar" aria-hidden="true" style={{ width: `${maximum ? row.count / maximum * 100 : 0}%` }} /><strong>{row.count.toLocaleString()}</strong></span></td>
      </tr>)}</tbody>
    </table></TableScroll> : <p className="lab-copy">No observations recorded.</p>}
  </section>
}

function countRows(counts: Record<string, number>): TokenCount[] {
  return Object.entries(counts).map(([token, count]) => ({ token, count })).sort((a, b) => b.count - a.count || a.token.localeCompare(b.token))
}

export function TestStatistics({ report, busy, selectedId, onRefresh, onPage, onInspect }: {
  report: TestReport
  busy: boolean
  selectedId?: string
  onRefresh: () => void
  onPage: (offset: number) => void
  onInspect: (id: string) => void
}) {
  const { summary, statistics } = report
  const unknownCount = report.unknown_review.reduce((total, row) => total + row.count, 0)
  const metrics = [
    { label: 'Tests recorded', value: summary.total.toLocaleString(), tone: '' },
    { label: 'Accepted', value: summary.accepted.toLocaleString(), tone: 'accepted' },
    { label: 'Rejected', value: summary.rejected.toLocaleString(), tone: 'rejected' },
    { label: 'Acceptance rate', value: summary.acceptance_rate === null ? 'Not available' : `${summary.acceptance_rate.toLocaleString(undefined, { maximumFractionDigits: 1 })}%`, tone: '' },
  ]
  return <section className="test-dashboard" aria-labelledby="test-dashboard-title">
    <header className="test-dashboard-heading">
      <div><span className="test-eyebrow">Shared workspace / retained tests</span><h2 id="test-dashboard-title">Test statistics</h2><p className="lab-copy">All completed tests by every user, including repeated inputs. Results remain after refresh, sign-out and account switches. Untested Collection entries are not included.</p></div>
      <button type="button" className="button button-secondary" onClick={onRefresh} disabled={busy}><Icon name="refresh" size={16} />Refresh saved tests</button>
    </header>
    <dl className="test-metrics">{metrics.map((metric) => <div key={metric.label} className={`test-metric ${metric.tone}`} role="group" aria-label={metric.label}>
      <dt>{metric.label}</dt><dd>{metric.value}</dd>
    </div>)}</dl>
    <dl className="test-token-totals">
      <div><dt>Total tokens</dt><dd>{statistics.total_tokens.toLocaleString()}</dd></div>
      <div><dt>Raw spellings</dt><dd>{statistics.raw_frequencies.length.toLocaleString()}</dd></div>
      <div><dt>Normalized forms</dt><dd>{statistics.normalized_frequencies.length.toLocaleString()}</dd></div>
      <div><dt>Unknown occurrences</dt><dd>{unknownCount.toLocaleString()}</dd></div>
    </dl>
    <p className="lab-copy">Acceptance measures each test against the grammar and vocabulary used at that time, not the correctness of a speaker's language. Changing grammar settings does not rewrite past results.</p>
    {!summary.total ? <div className="lab-empty-panel">
      <Icon name="chart" size={28} /><h3>No saved tests yet</h3>
      <p>No one has recorded a test in the shared workspace yet. Analyze a sentence or word to add the first one for everyone to view. Earlier runs made before test storage was introduced cannot be recovered.</p>
      <a className="button button-primary" href="#compiler">Analyze a sentence or word<Icon name="arrow" size={16} /></a>
    </div> : <>
      <section className="test-review-panel" aria-labelledby="unknown-review-title">
        <div className="lab-result-heading"><h3 id="unknown-review-title">Unknown-word review</h3><span className="lab-status review">{report.unknown_review.length.toLocaleString()} {report.unknown_review.length === 1 ? 'form' : 'forms'} to review</span></div>
        <p className="lab-copy">UNKNOWN means no lexer category matched in that test. It does not mean the word is invalid. Counts combine letter case, but only occurrences classified UNKNOWN are counted here.</p>
        {report.unknown_review.length ? <TableScroll label="Unknown-word review counts"><table className="lab-table">
          <thead><tr><th scope="col">Form</th><th scope="col">Observed spellings</th><th scope="col">Occurrences</th><th scope="col">Tests affected</th></tr></thead>
          <tbody>{report.unknown_review.map((row) => <tr key={row.token}><th scope="row"><code>{row.token}</code></th><td>{row.forms.join(' / ')}</td><td>{row.count.toLocaleString()}</td><td>{row.tests.toLocaleString()}</td></tr>)}</tbody>
        </table></TableScroll> : <p className="test-positive-note"><Icon name="check" size={17} />No unknown tokens in the saved tests.</p>}
      </section>
      <div className="test-chart-grid">
        <FrequencyChart title="Raw token frequency" description="Every observed spelling, preserving case. Punctuation and numbers also count." rows={statistics.raw_frequencies} />
        <FrequencyChart title="Normalized token frequency" description="Case, accents and apostrophe variants are grouped. These are spelling keys, not synonyms or verified canonical meanings." rows={statistics.normalized_frequencies} />
      </div>
      <FrequencyChart title="Grammatical category frequency" description="The exact lexer terminals passed to the parser, across all saved tests." rows={countRows(statistics.category_counts)} />
      <div className="test-chart-grid">
        <FrequencyChart title="Recorded topics" description="Labels from exact matching Collection entries when the test was saved. Missing context is Not recorded." rows={countRows(report.topic_counts)} />
        <FrequencyChart title="Declared input languages" description="Collection labels, not detected word origins. Multiple labels can contribute more than once per test." rows={countRows(report.language_counts)} />
      </div>
      <details className="lab-disclosure">
        <summary>Observed spelling variations - {statistics.variations.length} groups</summary>
        <div className="lab-disclosure-body"><p className="lab-copy">Normalization finds spelling candidates, not proven linguistic equivalence. Each count comes from saved test tokens.</p>
          {statistics.variations.length ? <TableScroll label="Saved-test spelling variations"><table className="lab-table">
            <thead><tr><th scope="col">Normalized form</th><th scope="col">Observed spellings and counts</th></tr></thead>
            <tbody>{statistics.variations.map((row) => <tr key={row.normalized}><th scope="row"><code>{row.normalized}</code></th><td>{row.forms.map((form) => `${form.text} (${form.count})`).join(' / ')}</td></tr>)}</tbody>
          </table></TableScroll> : <p className="lab-copy">No spelling-variation groups in these tests.</p>}
        </div>
      </details>
      <section className="test-records" aria-labelledby="test-records-title">
        <div className="lab-result-heading"><h3 id="test-records-title">Saved tests</h3><span className="lab-copy">Newest first / all tests retained</span></div>
        <p className="lab-copy">Inspect a test to see its original input, token classifications, grammar and parser trace without running it again.</p>
        <ol className="test-record-list">{report.tests.map((test, index) => <li key={test.id} className={test.id === selectedId ? 'is-selected' : ''}>
          <div className="test-record-topline"><span className={`lab-status ${test.accepted ? 'ready' : 'needs_input'}`}>{test.accepted ? 'ACCEPT' : 'REJECT'}</span><span>{test.token_count.toLocaleString()} tokens</span><time dateTime={test.created_at}>{new Date(test.created_at).toLocaleString()}</time></div>
          <p className="test-record-source">{test.text || '(empty input)'}</p>
          <p className="lab-copy">Creator: {test.ownership.owner_name} · Immutable saved test</p>
          <button type="button" className="text-button" aria-label={`Inspect test ${summary.total - report.offset - index}`} onClick={() => onInspect(test.id)} disabled={busy}>Inspect test<Icon name="arrow" size={16} /></button>
        </li>)}</ol>
        <nav className="test-pagination" aria-label="Saved tests pages">
          <button type="button" className="button button-secondary" disabled={busy || report.offset === 0} onClick={() => onPage(Math.max(0, report.offset - report.limit))}>Previous tests</button>
          <span className="lab-copy">{report.tests.length ? report.offset + 1 : 0}-{report.offset + report.tests.length} of {summary.total.toLocaleString()} tests / statistics include all {summary.total.toLocaleString()}</span>
          <button type="button" className="button button-secondary" disabled={busy || report.offset + report.tests.length >= summary.total} onClick={() => onPage(report.offset + report.limit)}>Next tests</button>
        </nav>
      </section>
    </>}
  </section>
}
