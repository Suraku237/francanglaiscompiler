import { CopyButton, ErrorNotice, Icon, ReadButton, Spinner } from './components'
import type { PracticeResult } from './types'
import type { ReadAloud } from './voice'
import { REFERENCE_PAGE_SIZE as PAGE_SIZE, useReferenceSearch } from './useReferenceSearch'
import './dictionary.css'

export function Examples({ active, onUseText, speech }: {
  active: boolean
  onUseText: (text: string) => void
  speech?: ReadAloud
}) {
  const { query, setQuery, offset, setOffset, result, pending, error, refresh, loading } =
    useReferenceSearch<PracticeResult>('/examples', active)

  return <section className="page dictionary-page" aria-labelledby="examples-title">
    <div className="page-intro compact-intro"><div><div className="eyebrow"><span className="eyebrow-line" />ILLUSTRATIVE REFERENCE ONLY</div><h1 id="examples-title">Synthetic examples</h1><p>The supplied constructed statements include French and English meanings. Search the text, either meaning, or a topic.</p></div></div>
    <div className="notice notice-subtle"><Icon name="info" size={20} /><p><strong>Constructed examples, not genuine fieldwork.</strong> These statements were built from vocabulary lists, not recorded or verified with speakers. They do not populate Collection, train the lexer, approve records or increase research counts. Use them only as clearly labelled manual experiments, never as a substitute for your own transcript.</p></div>
    <div className="collection-tools">
      <div className="search-field"><Icon name="search" size={20} /><label className="sr-only" htmlFor="examples-query">Search practice examples</label><input id="examples-query" type="search" maxLength={200} value={query} placeholder="Search mbom, manger, connection, or a topic" onChange={(event) => { setQuery(event.target.value); setOffset(0) }} /></div>
      <button type="button" className="icon-button" aria-label="Refresh practice examples" disabled={pending} onClick={refresh}><Icon name="refresh" size={19} /></button>
    </div>
    <ErrorNotice message={error} onRetry={refresh} />
    <div className="dictionary-results" aria-busy={loading}>
      {loading ? <div className="collection-loading"><Spinner label="Loading practice examples" /><p>Reading the supplied statements...</p></div> : result && <>
        <p className="dictionary-summary" role="status"><strong>{result.matched} matching {result.matched === 1 ? 'example' : 'examples'}</strong> out of {result.total} supplied practice statements.</p>
        {result.entries.length ? <div className="dictionary-grid">{result.entries.map((entry) => <article className="dictionary-card" key={entry.id}>
          <span className="local-badge">CONSTRUCTED EXAMPLE</span>
          <div className="dictionary-heading"><h2>{entry.text}</h2><CopyButton text={entry.text} compact /></div>
          <dl>
            <div><dt>French meaning</dt><dd lang="fr">{entry.french_gloss}</dd></div>
            <div><dt>English meaning</dt><dd lang="en">{entry.english_gloss}</dd></div>
            <div><dt>Topic</dt><dd>{entry.topic}</dd></div>
            <div><dt>Source</dt><dd><code>{entry.source_document}:{entry.source_line}</code></dd></div>
            <div><dt>Original note</dt><dd>{entry.notes}</dd></div>
          </dl>
          <div className="import-actions">
            <button type="button" className="button button-secondary" onClick={() => onUseText(entry.text)}>Open in Franc Analyzer<Icon name="arrow" size={16} /></button>
            {speech && <ReadButton speech={speech} id={`example:${entry.id}`} text={entry.text} language="fr" />}
          </div>
        </article>)}</div> : <div className="collection-empty"><h2>No practice examples found.</h2><p>Try another word, meaning or topic.</p></div>}
        <nav className="dictionary-pagination" aria-label="Practice example pages">
          <button type="button" className="button button-secondary" disabled={offset === 0 || pending} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous examples</button>
          <span>{result.matched ? `${offset + 1}-${Math.min(offset + result.entries.length, result.matched)} of ${result.matched}` : '0 results'}</span>
          <button type="button" className="button button-secondary" disabled={offset + PAGE_SIZE >= result.matched || pending} onClick={() => setOffset(offset + PAGE_SIZE)}>Next examples</button>
        </nav>
      </>}
    </div>
    <p className="helper-text">Opening an example fills Franc Analyzer only. Nothing is computed or saved until you explicitly act. Read-aloud uses a saved voice recording or lets you record your reading. Supplied meanings and these pronunciation recordings are not collected fieldwork.</p>
  </section>
}
