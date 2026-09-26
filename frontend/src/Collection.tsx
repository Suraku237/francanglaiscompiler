import { useEffect, useMemo, useRef, useState } from 'react'
import { api, isCancelled, messageOf, nativeApiUrl } from './api'
import { AudioPlayer } from './AudioRecorder'
import { ErrorNotice, Icon, Modal, Spinner } from './components'
import { defaultMetadata, languageLabels } from './types'
import type { Dataset, DatasetEntry, DatasetLanguage, Metadata, ReviewStatus } from './types'
import { useDownload } from './useDownload'

function uniqueOptions(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))]
}

function displayDate(value: string): string {
  if (!value) return 'Date not recorded'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(date)
}

export function EntryViewer({ entry, onClose }: { entry: DatasetEntry; onClose: () => void }) {
  const expressionInput = useRef<HTMLTextAreaElement>(null)
  return <Modal title="View collection entry" onClose={onClose} className="entry-modal" initialFocus={expressionInput}>
    <p className="modal-description">Read the original transcript, annotations and provenance, or listen to its recording. Collection is read-only. Approval is a recorded review, not verified fieldwork.</p>
    <div className="form-fields">
      <div className="field">
        <label htmlFor="entry-text">Expression</label>
        <textarea ref={expressionInput} id="entry-text" rows={3} value={entry.text} readOnly aria-describedby="entry-text-hint" />
        <span id="entry-text-hint" className="field-hint">Original manual transcript · Read-only</span>
      </div>
      <div className="field-grid">
        <div className="field"><label htmlFor="entry-language">Language</label><input id="entry-language" value={languageLabels[entry.language ?? 'unspecified'] ?? entry.language} readOnly /></div>
        <div className="field"><label htmlFor="entry-type">Entry type</label><input id="entry-type" value={entry.entry_type || 'Not recorded (legacy)'} readOnly /></div>
      </div>
      <div className="field-grid">
        <div className="field"><label htmlFor="entry-category">Category</label><input id="entry-category" value={entry.category || 'Not recorded (legacy)'} readOnly /></div>
        {entry.entry_type === 'Word' && <div className="field"><label htmlFor="entry-lexical-category">Lexical category</label><input id="entry-lexical-category" value={entry.lexical_category || 'Not recorded'} readOnly /></div>}
      </div>
      <div className="field-grid">
        <div className="field"><label htmlFor="entry-french">French meaning</label><textarea id="entry-french" rows={3} value={entry.french_gloss} lang="fr" readOnly placeholder="Not recorded" /></div>
        <div className="field"><label htmlFor="entry-english">English meaning</label><textarea id="entry-english" rows={3} value={entry.english_gloss} lang="en" readOnly placeholder="Not recorded" /></div>
      </div>
      <div className="field-grid">
        <div className="field"><label htmlFor="entry-location">Source location</label><input id="entry-location" value={entry.source_location} readOnly placeholder="Not recorded" /></div>
        <div className="field"><label htmlFor="entry-contributor">Contributor</label><input id="entry-contributor" value={entry.contributor} readOnly placeholder="Not recorded" /></div>
      </div>
      <div className="field"><label htmlFor="entry-notes">Context & notes</label><textarea id="entry-notes" rows={3} value={entry.notes} readOnly placeholder="Not recorded" /></div>
      {entry.audio_filename ? <div>
        <p className="helper-text">Current attachment: {entry.audio_filename}</p>
        <AudioPlayer src={nativeApiUrl(`/dataset/${encodeURIComponent(entry.id)}/audio`)} filename={entry.audio_filename} />
      </div> : <p className="helper-text">No recording is available for this entry. Recordings are read-only; recording and uploads are unavailable.</p>}
      <div className="entry-review">
        <p>Review status: {entry.review_status === 'approved' ? 'Approved' : 'Unreviewed'} · Read-only.</p>
        <p>Saved sentence records may be used in corpus tests regardless of review status. Approval does not certify fieldwork.</p>
      </div>
      <details className="record-details"><summary>Original record details <Icon name="chevron" size={15} /></summary><dl><div><dt>Record ID</dt><dd>{entry.id}</dd></div><div><dt>Added</dt><dd>{displayDate(entry.timestamp)}</dd></div><div><dt>Audio filename</dt><dd>{entry.audio_filename || 'No audio attached'}</dd></div></dl></details>
    </div>
    <div className="modal-footer"><span className="helper-text"><Icon name="shield" size={15} />Public reference data · Read-only.</span><button type="button" className="button button-secondary" onClick={onClose}>Done</button></div>
  </Modal>
}

export function Collection({ active, onUseText }: { active: boolean; onUseText?: (text: string) => void }) {
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('')
  const [entryType, setEntryType] = useState('')
  const [language, setLanguage] = useState<DatasetLanguage | ''>('')
  const [reviewStatus, setReviewStatus] = useState<ReviewStatus | ''>('')
  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [metadata, setMetadata] = useState<Metadata>(defaultMetadata)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [metadataError, setMetadataError] = useState('')
  const [revision, setRevision] = useState(0)
  const [selectedEntry, setSelectedEntry] = useState<DatasetEntry | null>(null)
  const [notice, setNotice] = useState('')
  const { download, error: downloadError } = useDownload()

  useEffect(() => {
    if (!active) {
      setSelectedEntry(null)
      return
    }
    const controller = new AbortController()
    setLoading(true)
    setError('')
    const timer = window.setTimeout(() => {
      const params = new URLSearchParams()
      if (query.trim()) params.set('query', query.trim())
      const suffix = params.size ? `?${params.toString()}` : ''
      void api<Dataset>(`/dataset${suffix}`, { signal: controller.signal }).then((response) => {
        if (!controller.signal.aborted) setDataset(response)
      }).catch((cause: unknown) => {
        if (!controller.signal.aborted && !isCancelled(cause)) setError(messageOf(cause))
      }).finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    }, query ? 300 : 0)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [active, query, revision])

  useEffect(() => {
    if (!active) return
    const controller = new AbortController()
    setMetadataError('')
    void api<Metadata>('/metadata', { signal: controller.signal }).then((response) => {
      if (!controller.signal.aborted) setMetadata({ ...defaultMetadata, ...response })
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted && !isCancelled(cause)) {
        setMetadataError(`Entry metadata could not be loaded. Standard options and existing values are still available. ${messageOf(cause)}`)
      }
    })
    return () => controller.abort()
  }, [active, revision])

  useEffect(() => {
    if (!notice) return
    const timer = window.setTimeout(() => setNotice(''), 6000)
    return () => window.clearTimeout(timer)
  }, [notice])

  const categories = uniqueOptions([...metadata.categories, ...Object.keys(dataset?.by_category ?? {})])
  const entryTypes = uniqueOptions([...metadata.entry_types, ...Object.keys(dataset?.by_type ?? {})])
  const datasetLanguages = uniqueOptions([...metadata.dataset_languages, ...(dataset?.entries ?? []).map((entry) => entry.language ?? 'unspecified')])
  const entries = useMemo(() => (dataset?.entries ?? []).filter((entry) =>
    (!category || (entry.category || '(none)') === category) &&
    (!entryType || (entry.entry_type || '(none)') === entryType) &&
    (!language || (entry.language ?? 'unspecified') === language) &&
    (!reviewStatus || (entry.review_status ?? 'unreviewed') === reviewStatus),
  ), [dataset, category, entryType, language, reviewStatus])
  const hasFilters = Boolean(query || category || entryType || language || reviewStatus)

  function resetFilters() {
    setQuery('')
    setCategory('')
    setEntryType('')
    setLanguage('')
    setReviewStatus('')
  }

  return <section className="page collection-page" aria-labelledby="collection-title">
    <div className="page-intro compact-intro">
      <div><div className="eyebrow">READ-ONLY REFERENCE COLLECTION</div><h1 id="collection-title">Collection</h1><p>Browse saved statements, annotations and provenance, and listen to existing recordings. Entries cannot be added, edited or removed here.</p></div>
    </div>
    <div className="collection-stats" aria-label="Counts across the public workspace">
      <div><span className="stat-icon"><Icon name="collection" size={23} /></span><div><strong>{dataset ? dataset.total.toLocaleString() : '—'}</strong><span>Total entries</span></div></div>
      <div><span className="stat-icon"><Icon name="check" size={23} /></span><div><strong>{dataset?.by_review_status?.approved ?? '—'}</strong><span>Approved</span></div></div>
      <div><span className="stat-icon"><Icon name="edit" size={23} /></span><div><strong>{dataset?.by_review_status?.unreviewed ?? '—'}</strong><span>Awaiting review</span></div></div>
    </div>
    <div className="collection-summary"><span className="helper-text">Counts cover the whole collection, not just the search results.</span>{dataset && <div className="type-counts">{Object.entries(dataset.by_type).map(([type, count]) => <span key={type}>{type || 'Unspecified'} <strong>{count}</strong></span>)}</div>}</div>
    <p className="helper-text">Use a record as analyzer input without changing Collection. Dictionary and synthetic references are not fieldwork evidence.</p>
    <div className="collection-tools">
      <div className="search-field"><Icon name="search" size={20} /><label className="sr-only" htmlFor="collection-query">Search collection</label><input id="collection-query" type="search" maxLength={200} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search statements, words, meanings or context" /></div>
      <div className="collection-filters">
        <label className="sr-only" htmlFor="language-filter">Filter by dataset language</label><select id="language-filter" value={language} onChange={(event) => setLanguage(event.target.value as DatasetLanguage | '')}><option value="">All languages</option>{datasetLanguages.map((value) => <option key={value} value={value}>{languageLabels[value as DatasetLanguage] ?? value}</option>)}</select>
        <label className="sr-only" htmlFor="review-filter">Filter by review status</label><select id="review-filter" value={reviewStatus} onChange={(event) => setReviewStatus(event.target.value as ReviewStatus | '')}><option value="">All review statuses</option><option value="approved">Approved · recorded review</option><option value="unreviewed">Unreviewed</option></select>
        <label className="sr-only" htmlFor="category-filter">Filter by category</label><select id="category-filter" value={category} onChange={(event) => setCategory(event.target.value)}><option value="">All categories</option>{categories.map((name) => <option key={name} value={name}>{name}</option>)}</select>
        <label className="sr-only" htmlFor="type-filter">Filter by entry type</label><select id="type-filter" value={entryType} onChange={(event) => setEntryType(event.target.value)}><option value="">All types</option>{entryTypes.map((type) => <option key={type} value={type}>{type}</option>)}</select>
        <button type="button" className="icon-button refresh-collection" onClick={() => setRevision((value) => value + 1)} disabled={loading} aria-label="Refresh collection" title="Refresh collection"><Icon name="refresh" size={19} /></button>
      </div>
    </div>
    <ErrorNotice message={metadataError} onRetry={() => setRevision((value) => value + 1)} />
    {notice && <div className="notice notice-success" role="status"><Icon name="check" size={18} /><span>{notice}</span><button className="icon-button" type="button" aria-label="Dismiss notification" onClick={() => setNotice('')}><Icon name="close" size={16} /></button></div>}
    <div className="collection-list-heading"><h2>Collected records <span>{loading ? 'Updating…' : error ? 'Unavailable' : `${entries.length.toLocaleString()} ${entries.length === 1 ? 'entry' : 'entries'}`}</span></h2><div className="submit-actions">{hasFilters && <button type="button" className="text-button" onClick={resetFilters}>Clear filters <Icon name="close" size={14} /></button>}<button type="button" className="button button-secondary" disabled={loading || Boolean(error) || !entries.length} onClick={() => {
      const data = { exported_at: new Date().toISOString(), entries }
      if (download(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json;charset=utf-8' }), 'camfranglais-collection.json')) {
        setNotice(`Export started for ${entries.length} entries. Audio filenames are included, not the audio files themselves.`)
      }
    }}>Export results (JSON)<Icon name="arrow" size={15} /></button></div></div>
    <p className="helper-text">Exports include the displayed entries and their context/contributor details. Share only with authorized recipients.</p>
    <ErrorNotice message={downloadError} />
    <div className="collection-results" aria-busy={loading}>
      {loading ? <div className="collection-loading" role="status"><Spinner label="Loading collection" /><p>Loading collected records…</p><div className="entry-skeletons" aria-hidden="true"><div /><div /><div /></div></div> :
        error ? <div className="collection-error"><Icon name="collection" size={34} /><h3>Collection unavailable</h3><p>Check the connection and retry. No records were changed.</p><ErrorNotice message={error} onRetry={() => setRevision((value) => value + 1)} /></div> :
          !entries.length ? <div className="collection-empty"><span className="empty-collection-icon"><Icon name={hasFilters ? 'search' : 'collection'} size={35} /></span><h3>{hasFilters ? 'No matching records' : 'No collected statements yet'}</h3><p>{hasFilters ? 'Adjust your search or filters to see other entries.' : 'The public collection is empty and read-only. No sample data is inserted for you. You can still analyze text without adding Collection entries.'}</p>{hasFilters && <button type="button" className="button button-secondary" onClick={resetFilters}>Clear all filters<Icon name="refresh" size={16} /></button>}</div> :
            <div className="entry-grid">{entries.map((entry) => <article className="entry-card" key={entry.id}>
              <div className="entry-topline"><div className="entry-badges"><span className="entry-type">{entry.entry_type || 'Unspecified'}</span><span className="entry-category">{entry.category || 'No category'}</span></div><div className="entry-actions"><button type="button" className="icon-button" aria-label={`View expression: ${entry.text.slice(0, 80)}`} title="View expression" onClick={() => setSelectedEntry(entry)}><Icon name="info" size={17} /></button></div></div>
              <div className="entry-trust-line"><span className="entry-language">{languageLabels[entry.language ?? 'unspecified'] ?? entry.language}</span><span className={`review-badge ${entry.review_status === 'approved' ? 'review-approved' : 'review-unreviewed'}`}>{entry.review_status === 'approved' ? 'Approved' : 'Unreviewed'}</span></div>
              <h3>{entry.text}</h3>
              <p className="helper-text">Public reference record · Read-only</p>
              <div className="entry-glosses">
                {entry.french_gloss && <p lang="fr"><span aria-label="French meaning">FR</span>{entry.french_gloss}</p>}
                {entry.english_gloss && <p lang="en"><span aria-label="English meaning">EN</span>{entry.english_gloss}</p>}
                {!entry.french_gloss && !entry.english_gloss && <p className="no-gloss">No meaning recorded.</p>}
              </div>
              {entry.audio_filename && <AudioPlayer src={nativeApiUrl(`/dataset/${encodeURIComponent(entry.id)}/audio`)} filename={entry.audio_filename} active={active} />}
              <details className="entry-context"><summary>Context & record details<Icon name="chevron" size={14} /></summary>{entry.notes && <p>{entry.notes}</p>}{entry.contributor && <p><strong>Contributor:</strong> {entry.contributor}</p>}{entry.audio_filename && <p><strong>Audio file:</strong> {entry.audio_filename}</p>}<p className="record-id"><strong>ID:</strong> {entry.id}</p></details>
              {onUseText && <div className="lab-actions"><button type="button" className="text-button" onClick={() => onUseText(entry.text)}>Use as analyzer input<Icon name="arrow" size={16} /></button></div>}
              <div className="entry-footer"><span><Icon name="location" size={14} />{entry.source_location || 'Location not recorded'}</span><time title={entry.timestamp}>{displayDate(entry.timestamp)}</time></div>
            </article>)}</div>}
    </div>
    <p className="privacy-caption"><Icon name="shield" size={15} /><span>Statements, annotations and recordings are public and read-only. No automatic transcription or generated data is added. Exports include provenance; share them only with permission.</span></p>
    {active && selectedEntry && <EntryViewer entry={selectedEntry} onClose={() => setSelectedEntry(null)} />}
  </section>
}
