import { CopyButton, ErrorNotice, Icon, Spinner } from './components'
import type { DictionaryResult } from './types'
import { REFERENCE_PAGE_SIZE as PAGE_SIZE, useReferenceSearch } from './useReferenceSearch'
import './dictionary.css'

export function Dictionary({ active, onTranslate }: { active: boolean; onTranslate: (text: string) => void }) {
  const { query, setQuery, offset, setOffset, result, pending, error, refresh, loading } =
    useReferenceSearch<DictionaryResult>('/dictionary', active)

  return <section className="page dictionary-page" aria-labelledby="dictionary-title">
    <div className="page-intro compact-intro">
      <div><div className="eyebrow"><span className="eyebrow-line" />REFERENCE VOCABULARY</div><h1 id="dictionary-title">Find the words.<br /><em>Keep the context.</em></h1><p>Search the supplied Camfranglais dictionaries by word, listed variant, or English meaning. Every entry keeps its source, topic, and original meaning.</p></div>
    </div>
    <div className="notice notice-subtle"><Icon name="info" size={20} /><p><strong>A dictionary, not collected fieldwork.</strong> These references do not populate the collection, approve records, or increase coursework totals. No French translations were supplied. Origins such as “French” describe etymology, not a French meaning or a grammatical label.</p></div>
    <div className="collection-tools">
      <div className="search-field"><Icon name="search" size={20} /><label className="sr-only" htmlFor="dictionary-query">Search reference dictionary</label><input id="dictionary-query" type="search" maxLength={200} value={query} placeholder="Try tchop, motard, pasho, or an English meaning" onChange={(event) => { setQuery(event.target.value); setOffset(0) }} /></div>
      <button type="button" className="icon-button" aria-label="Refresh reference dictionary" disabled={pending} onClick={refresh}><Icon name="refresh" size={19} /></button>
    </div>
    <ErrorNotice message={error} onRetry={refresh} />
    <div className="dictionary-results" aria-busy={loading}>
      {loading ? <div className="collection-loading"><Spinner label="Loading reference dictionary" /><p>Looking up the supplied vocabulary...</p></div> : result && <>
        <p className="dictionary-summary" role="status"><strong>{result.matched.toLocaleString()} matching {result.matched === 1 ? 'entry' : 'entries'}</strong> out of {result.total.toLocaleString()} source entries. Repeated words may have different senses.</p>
        <p className="helper-text">Sources: {result.sources.join(', ')}. This reference is not exhaustive; usage and spelling vary.</p>
        {result.entries.length ? <div className="dictionary-grid">{result.entries.map((entry) => <article className="dictionary-card" key={entry.id}>
          <div className="dictionary-heading"><h2>{entry.text}</h2><CopyButton text={entry.text} compact /></div>
          <dl>
            <div><dt>English meaning</dt><dd lang="en">{entry.english_gloss}</dd></div>
            {entry.aliases.length > 1 && <div><dt>Lookup forms</dt><dd>{entry.aliases.join(' / ')}</dd></div>}
            <div><dt>Topic</dt><dd>{entry.topic}</dd></div>
            <div><dt>Origin (as supplied)</dt><dd>{entry.origin}</dd></div>
            <div><dt>Source</dt><dd><code>{entry.source_document}:{entry.source_line}</code></dd></div>
          </dl>
          <button type="button" className="button button-secondary" onClick={() => onTranslate(entry.aliases[0] ?? entry.text)} aria-label={`Open ${entry.text} in translator`}>Open in translator<Icon name="arrow" size={16} /></button>
        </article>)}</div> : <div className="collection-empty"><Icon name="search" size={32} /><h2>No dictionary entries found.</h2><p>Try another spelling or an English meaning. A missing reference does not mean the word is invalid.</p></div>}
        <nav className="dictionary-pagination" aria-label="Dictionary pages">
          <button type="button" className="button button-secondary" disabled={offset === 0 || pending} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous entries</button>
          <span>{result.matched ? `${offset + 1}-${Math.min(offset + result.entries.length, result.matched)} of ${result.matched}` : '0 results'}</span>
          <button type="button" className="button button-secondary" disabled={offset + PAGE_SIZE >= result.matched || pending} onClick={() => setOffset(offset + PAGE_SIZE)}>Next entries</button>
        </nav>
      </>}
    </div>
    <p className="helper-text">Opening a word only fills a translation draft. It does not submit an AI request or save a collection entry. Conflicting senses remain visible instead of being silently replaced.</p>
  </section>
}
