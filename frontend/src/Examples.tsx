import { CopyButton, ErrorNotice, Icon, Spinner } from './components'
import type { Language, PracticeResult } from './types'
import { REFERENCE_PAGE_SIZE as PAGE_SIZE, useReferenceSearch } from './useReferenceSearch'
import './dictionary.css'

export function Examples({ active, onTranslate }: {
  active: boolean
  onTranslate: (text: string, target: Language) => void
}) {
  const { query, setQuery, offset, setOffset, result, pending, error, refresh, loading } =
    useReferenceSearch<PracticeResult>('/examples', active)

  return <section className="page dictionary-page" aria-labelledby="examples-title">
    <div className="page-intro compact-intro"><div><div className="eyebrow"><span className="eyebrow-line" />CONSTRUCTED PRACTICE MATERIAL</div><h1 id="examples-title">Explore a sentence.<br /><em>Compare its meanings.</em></h1><p>The supplied practice statements include French and English meanings. Search the original text, either meaning, or a topic.</p></div></div>
    <div className="notice notice-subtle"><Icon name="info" size={20} /><p><strong>Constructed examples, not genuine fieldwork.</strong> These supplied statements were built from vocabulary lists, not recorded or verified with speakers. They do not populate Collection, train the lexer, approve records or increase research counts. Their translation source is off by default and requires an explicit choice.</p></div>
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
            <button type="button" className="button button-secondary" onClick={() => onTranslate(entry.text, 'fr')}>Practice in French<Icon name="arrow" size={16} /></button>
            <button type="button" className="button button-secondary" onClick={() => onTranslate(entry.text, 'en')}>Practice in English<Icon name="arrow" size={16} /></button>
          </div>
        </article>)}</div> : <div className="collection-empty"><h2>No practice examples found.</h2><p>Try another word, meaning or topic.</p></div>}
        <nav className="dictionary-pagination" aria-label="Practice example pages">
          <button type="button" className="button button-secondary" disabled={offset === 0 || pending} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous examples</button>
          <span>{result.matched ? `${offset + 1}-${Math.min(offset + result.entries.length, result.matched)} of ${result.matched}` : '0 results'}</span>
          <button type="button" className="button button-secondary" disabled={offset + PAGE_SIZE >= result.matched || pending} onClick={() => setOffset(offset + PAGE_SIZE)}>Next examples</button>
        </nav>
      </>}
    </div>
    <p className="helper-text">Practice buttons fill a translation draft and enable constructed examples for that lookup. Nothing is submitted or saved until you explicitly act. The supplied meanings are not independently certified translations.</p>
  </section>
}
