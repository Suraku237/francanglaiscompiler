import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { api, isCancelled, messageOf } from './api'
import { AudioPlayer, AudioRecorder } from './AudioRecorder'
import { ErrorNotice, Icon, Modal, Spinner } from './components'
import { defaultMetadata, languageLabels, MAX_TEXT } from './types'
import type { Dataset, DatasetEntry, DatasetLanguage, EditableEntry, Metadata, ReviewStatus } from './types'
import { useRequest } from './useRequest'
import { useDownload } from './useDownload'

const emptyEntry: EditableEntry = {
  text: '',
  entry_type: 'Sentence',
  language: 'unspecified',
  review_status: 'unreviewed',
  lexical_category: '',
  french_gloss: '',
  english_gloss: '',
  category: 'Other',
  source_location: '',
  notes: '',
  contributor: '',
}

function uniqueOptions(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))]
}

function editableFields(entry: DatasetEntry): EditableEntry {
  return {
    text: entry.text,
    entry_type: entry.entry_type,
    language: entry.language ?? 'unspecified',
    review_status: entry.review_status ?? 'unreviewed',
    lexical_category: entry.lexical_category ?? '',
    french_gloss: entry.french_gloss,
    english_gloss: entry.english_gloss,
    category: entry.category,
    source_location: entry.source_location,
    notes: entry.notes,
    contributor: entry.contributor,
  }
}

function displayDate(value: string): string {
  if (!value) return 'Date not recorded'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(date)
}

export function EntryEditor({ entry = null, metadata, initialDraft, onClose, onSaved }: {
  entry?: DatasetEntry | null
  metadata: Metadata
  initialDraft?: Partial<EditableEntry>
  onClose: () => void
  onSaved: (entry: DatasetEntry) => void
}) {
  const expressionInput = useRef<HTMLTextAreaElement>(null)
  const [draft, setDraft] = useState<EditableEntry>(() => entry ? editableFields(entry) : { ...emptyEntry, ...initialDraft, review_status: 'unreviewed' })
  const [validationError, setValidationError] = useState('')
  const [audioFile, setAudioFile] = useState<File | null>(null)
  const [removeAudio, setRemoveAudio] = useState(false)
  const [recording, setRecording] = useState(false)
  const { pending, error, run, clearError } = useRequest()
  const categories = uniqueOptions([...metadata.categories, draft.category])
  const entryTypes = uniqueOptions([...metadata.entry_types, draft.entry_type])
  const datasetLanguages = uniqueOptions([...(metadata.dataset_languages ?? defaultMetadata.dataset_languages), draft.language])

  function update<K extends keyof EditableEntry>(field: K, value: EditableEntry[K]) {
    clearError()
    setValidationError('')
    setDraft((previous) => ({
      ...previous,
      [field]: value,
      ...(field !== 'review_status' ? { review_status: 'unreviewed' as const } : {}),
      ...(field === 'entry_type' && value !== 'Word' ? { lexical_category: '' } : {}),
    }))
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending) return
    if (recording) {
      setValidationError('Stop recording before saving the expression.')
      return
    }
    if (!draft.text.trim()) {
      setValidationError('Please add an expression. It cannot contain only spaces.')
      return
    }
    const values = { ...draft, text: entry && draft.text === entry.text ? draft.text : draft.text.trim() }
    const original = entry ? editableFields(entry) : null
    const changes = original
      ? Object.fromEntries(Object.entries(values).filter(([field, value]) => original[field as keyof EditableEntry] !== value))
      : values
    if (entry && !Object.keys(changes).length && !audioFile && !removeAudio) {
      onClose()
      return
    }
    const body = { ...changes, review_status: values.review_status }
    const withAudio = Boolean(audioFile || removeAudio)
    const multipart = new FormData()
    if (withAudio) {
      multipart.append('fields', JSON.stringify(body))
      if (audioFile) multipart.append('file', audioFile)
      if (removeAudio) multipart.append('remove_audio', 'true')
    }
    const path = entry
      ? `/dataset/${encodeURIComponent(entry.id)}${withAudio ? '/audio' : ''}`
      : `/dataset${withAudio ? '/audio' : ''}`
    void run(
      (signal) => api<DatasetEntry>(path, {
        method: entry ? 'PATCH' : 'POST', body: withAudio ? multipart : body, signal,
      }),
      onSaved,
    )
  }

  return <Modal title={entry ? 'Review terminology' : 'Add terminology'} onClose={onClose} busy={pending} className="entry-modal" initialFocus={expressionInput}>
    <p className="modal-description">{entry ? 'Review wording, language and meanings. Unchanged metadata and existing attachments are preserved.' : 'Add a term, phrase or reusable sentence. Save it for review, or explicitly approve it after checking the wording.'} <span>Only source text is required. Record context when known.</span></p>
    <form onSubmit={submit}>
      <div className="form-fields">
        <div className="field">
          <label htmlFor="entry-text">Expression <span className="required-mark">*</span></label>
          <textarea ref={expressionInput} id="entry-text" rows={3} maxLength={MAX_TEXT} required value={draft.text} disabled={pending} onChange={(event) => update('text', event.target.value)} placeholder="Type the expression you want to document…" aria-describedby="entry-text-limit" />
          <span id="entry-text-limit" className="field-hint">{draft.text.length.toLocaleString()} / 4,000 characters</span>
        </div>
        <div className="field-grid">
          <div className="field"><label htmlFor="entry-language">Language</label><select id="entry-language" value={draft.language} disabled={pending} onChange={(event) => update('language', event.target.value as DatasetLanguage)}>{datasetLanguages.map((language) => <option key={language} value={language}>{languageLabels[language as DatasetLanguage] ?? language}</option>)}</select><span className="field-hint">Choose Mixed or Unspecified when appropriate; neither is treated as Francanglais or Pidgin.</span></div>
          <div className="field"><label htmlFor="entry-type">Entry type</label><select id="entry-type" value={draft.entry_type} disabled={pending} onChange={(event) => update('entry_type', event.target.value)}>{!draft.entry_type && <option value="">Not recorded (legacy)</option>}{entryTypes.map((type) => <option key={type} value={type}>{type}</option>)}</select></div>
        </div>
        <div className="field-grid">
          <div className="field"><label htmlFor="entry-category">Category</label><select id="entry-category" value={draft.category} disabled={pending} onChange={(event) => update('category', event.target.value)}>{!draft.category && <option value="">Not recorded (legacy)</option>}{categories.map((category) => <option key={category} value={category}>{category}</option>)}</select></div>
        </div>
        <div className="field-grid">
          <div className="field"><label htmlFor="entry-french">French meaning <span>optional</span></label><textarea id="entry-french" rows={3} maxLength={MAX_TEXT} value={draft.french_gloss} lang="fr" disabled={pending} onChange={(event) => update('french_gloss', event.target.value)} placeholder="Le sens en français…" /></div>
          <div className="field"><label htmlFor="entry-english">English meaning <span>optional</span></label><textarea id="entry-english" rows={3} maxLength={MAX_TEXT} value={draft.english_gloss} lang="en" disabled={pending} onChange={(event) => update('english_gloss', event.target.value)} placeholder="The meaning in English…" /></div>
        </div>
        <div className="field-grid">
          <div className="field"><label htmlFor="entry-location">Source location <span>optional</span></label><input id="entry-location" maxLength={200} value={draft.source_location} disabled={pending} onChange={(event) => update('source_location', event.target.value)} placeholder="Document, meeting or customer reference" /></div>
          <div className="field"><label htmlFor="entry-contributor">Contributor <span>optional</span></label><input id="entry-contributor" maxLength={200} value={draft.contributor} disabled={pending} onChange={(event) => update('contributor', event.target.value)} placeholder="Name or alias" /></div>
        </div>
        <div className="field"><label htmlFor="entry-notes">Context & notes <span>optional</span></label><textarea id="entry-notes" rows={3} maxLength={2000} value={draft.notes} disabled={pending} onChange={(event) => update('notes', event.target.value)} placeholder="When is it used? What makes it special?" /></div>
        <AudioRecorder disabled={pending} file={audioFile} onBusyChange={setRecording} onFile={(file) => {
          setAudioFile(file)
          setRemoveAudio(false)
          update('review_status', 'unreviewed')
        }} />
        <p className="helper-text">Audio stays a browser draft until you save. Saving attaches it to this local record without sending it to Gemini. Only record people who have given permission.</p>
        {entry?.audio_filename && !audioFile && <div>
          {removeAudio ? <p className="helper-text">The attachment will be removed from this entry when you save. The original file is retained locally.</p> : <>
            <p className="helper-text">Current attachment: {entry.audio_filename}</p>
            <AudioPlayer src={`/api/dataset/${encodeURIComponent(entry.id)}/audio`} filename={entry.audio_filename} disabled={pending || recording} />
          </>}
          <button type="button" className="text-button" disabled={pending || recording} onClick={() => {
            setRemoveAudio((previous) => !previous)
            update('review_status', 'unreviewed')
          }}>{removeAudio ? 'Keep the existing attachment' : 'Remove attachment on save'}</button>
        </div>}
        <div className="entry-review">
          <label className="checkbox-label"><input type="checkbox" checked={draft.review_status === 'approved'} disabled={pending} onChange={(event) => update('review_status', event.target.checked ? 'approved' : 'unreviewed')} /><span>I have reviewed the language, expression, and meanings. Approve this entry for terminology matching.</span></label>
          <p>Edits clear approval until you review the new version. <strong>Unreviewed</strong> entries are excluded from approved-source matching. Approval records your decision, not independent certification.</p>
          <p>Approved text and glosses may be selected for an explicitly submitted AI request with dataset use enabled. Names, locations, notes, and other record metadata stay local.</p>
        </div>
        {entry && <details className="record-details"><summary>Original record details <Icon name="chevron" size={15} /></summary><dl><div><dt>Record ID</dt><dd>{entry.id}</dd></div><div><dt>Added</dt><dd>{displayDate(entry.timestamp)}</dd></div><div><dt>Audio filename</dt><dd>{entry.audio_filename || 'No audio attached'}</dd></div></dl></details>}
        <ErrorNotice message={validationError || error} />
      </div>
      <div className="modal-footer"><span className="helper-text"><Icon name="shield" size={15} />This save stays local.</span><div className="submit-actions"><button type="button" className="button button-secondary" onClick={onClose} disabled={pending}>Cancel</button><button type="submit" className="button button-primary" disabled={pending || recording}>{pending ? <Spinner label="Saving expression" /> : <Icon name="check" size={17} />}{pending ? 'Saving…' : draft.review_status === 'approved' ? 'Save approved entry' : 'Save unreviewed'}</button></div></div>
    </form>
  </Modal>
}

function DeleteConfirmation({ entry, onClose, onDeleted }: { entry: DatasetEntry; onClose: () => void; onDeleted: () => void }) {
  const { pending, error, run } = useRequest()
  return <Modal title="Remove this expression?" onClose={onClose} busy={pending} className="delete-modal">
    <div className="delete-preview"><Icon name="trash" size={23} /><p>{entry.text}</p></div>
    <p className="modal-description">This removes the record from your local collection. This action cannot be undone here.</p>
    <ErrorNotice message={error} />
    <div className="modal-footer"><button type="button" className="button button-secondary" onClick={onClose} disabled={pending}>Keep expression</button><button type="button" className="button button-danger" disabled={pending} onClick={() => void run(
      (signal) => api<void>(`/dataset/${encodeURIComponent(entry.id)}`, { method: 'DELETE', signal }),
      onDeleted,
    )}>{pending ? <Spinner label="Deleting expression" /> : <Icon name="trash" size={16} />}{pending ? 'Removing…' : 'Yes, remove it'}</button></div>
  </Modal>
}

export function Collection({ active }: { active: boolean }) {
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
  const [editor, setEditor] = useState<{ entry: DatasetEntry | null } | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<DatasetEntry | null>(null)
  const [notice, setNotice] = useState('')
  const { download, error: downloadError } = useDownload()

  useEffect(() => {
    if (!active) {
      setEditor(null)
      setDeleteTarget(null)
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
      <div><div className="eyebrow">LANGUAGE ASSETS</div><h1 id="collection-title">Terminology</h1><p>Manage approved terms and reusable phrases, keep source context and track items awaiting review.</p></div>
      <button type="button" className="button button-primary" onClick={() => setEditor({ entry: null })}><Icon name="plus" size={18} />Add entry</button>
    </div>
    <div className="collection-stats" aria-label="Counts across the entire local dataset">
      <div><span className="stat-icon"><Icon name="collection" size={23} /></span><div><strong>{dataset ? dataset.total.toLocaleString() : '—'}</strong><span>Total entries</span></div></div>
      <div><span className="stat-icon"><Icon name="check" size={23} /></span><div><strong>{dataset?.by_review_status?.approved ?? '—'}</strong><span>Approved</span></div></div>
      <div><span className="stat-icon"><Icon name="edit" size={23} /></span><div><strong>{dataset?.by_review_status?.unreviewed ?? '—'}</strong><span>Awaiting review</span></div></div>
    </div>
    <div className="collection-summary"><span className="helper-text">Counts cover your whole collection, not just the search results.</span>{dataset && <div className="type-counts">{Object.entries(dataset.by_type).map(([type, count]) => <span key={type}>{type || 'Unspecified'} <strong>{count}</strong></span>)}</div>}</div>
    <p className="helper-text">Dictionary references are separate from your terminology. <a href="#dictionary">Search dictionary</a> or <a href="#imports">import a document</a> to review additional terms.</p>

    <div className="collection-tools">
      <div className="search-field"><Icon name="search" size={20} /><label className="sr-only" htmlFor="collection-query">Search terminology</label><input id="collection-query" type="search" maxLength={200} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search terms, meanings or context" /></div>
      <div className="collection-filters">
        <label className="sr-only" htmlFor="language-filter">Filter by dataset language</label><select id="language-filter" value={language} onChange={(event) => setLanguage(event.target.value as DatasetLanguage | '')}><option value="">All languages</option>{datasetLanguages.map((value) => <option key={value} value={value}>{languageLabels[value as DatasetLanguage] ?? value}</option>)}</select>
        <label className="sr-only" htmlFor="review-filter">Filter by review status</label><select id="review-filter" value={reviewStatus} onChange={(event) => setReviewStatus(event.target.value as ReviewStatus | '')}><option value="">All review statuses</option><option value="approved">Approved · trusted</option><option value="unreviewed">Unreviewed</option></select>
        <label className="sr-only" htmlFor="category-filter">Filter by category</label><select id="category-filter" value={category} onChange={(event) => setCategory(event.target.value)}><option value="">All categories</option>{categories.map((name) => <option key={name} value={name}>{name}</option>)}</select>
        <label className="sr-only" htmlFor="type-filter">Filter by entry type</label><select id="type-filter" value={entryType} onChange={(event) => setEntryType(event.target.value)}><option value="">All types</option>{entryTypes.map((type) => <option key={type} value={type}>{type}</option>)}</select>
        <button type="button" className="icon-button refresh-collection" onClick={() => setRevision((value) => value + 1)} disabled={loading} aria-label="Refresh local collection" title="Refresh collection"><Icon name="refresh" size={19} /></button>
      </div>
    </div>
    <ErrorNotice message={metadataError} onRetry={() => setRevision((value) => value + 1)} />
    {notice && <div className="notice notice-success" role="status"><Icon name="check" size={18} /><span>{notice}</span><button className="icon-button" type="button" aria-label="Dismiss notification" onClick={() => setNotice('')}><Icon name="close" size={16} /></button></div>}
    <div className="collection-list-heading"><h2>Terminology library <span>{loading ? 'Updating…' : error ? 'Unavailable' : `${entries.length.toLocaleString()} ${entries.length === 1 ? 'entry' : 'entries'}`}</span></h2><div className="submit-actions">{hasFilters && <button type="button" className="text-button" onClick={resetFilters}>Clear filters <Icon name="close" size={14} /></button>}<button type="button" className="button button-secondary" disabled={loading || Boolean(error) || !entries.length} onClick={() => {
      const data = { exported_at: new Date().toISOString(), entries }
      if (download(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json;charset=utf-8' }), 'mboa-terminology.json')) {
        setNotice(`Export started for ${entries.length} entries. Audio filenames are included, not the audio files themselves.`)
      }
    }}>Export results (JSON)<Icon name="arrow" size={15} /></button></div></div>
    <p className="helper-text">Exports include the displayed entries and their context/contributor details. Share only with authorized recipients.</p>
    <ErrorNotice message={downloadError} />

    <div className="collection-results" aria-busy={loading}>
      {loading ? <div className="collection-loading" role="status"><Spinner label="Loading terminology" /><p>Loading your terminology library…</p><div className="entry-skeletons" aria-hidden="true"><div /><div /><div /></div></div> :
        error ? <div className="collection-error"><Icon name="collection" size={34} /><h3>Terminology unavailable</h3><p>Check the connection and retry. No records were changed.</p><ErrorNotice message={error} onRetry={() => setRevision((value) => value + 1)} /></div> :
          !entries.length ? <div className="collection-empty"><span className="empty-collection-icon"><Icon name={hasFilters ? 'search' : 'collection'} size={35} /></span><h3>{hasFilters ? 'No matching terminology' : 'Build your terminology library'}</h3><p>{hasFilters ? 'Adjust your search or filters to see other entries.' : 'Add reusable terms, phrases and their meanings. Review entries before approving them for translation.'}</p><button type="button" className="button button-secondary" onClick={hasFilters ? resetFilters : () => setEditor({ entry: null })}>{hasFilters ? 'Clear all filters' : 'Add your first entry'}<Icon name={hasFilters ? 'refresh' : 'plus'} size={16} /></button></div> :
            <div className="entry-grid">{entries.map((entry) => <article className="entry-card" key={entry.id}>
              <div className="entry-topline"><div className="entry-badges"><span className="entry-type">{entry.entry_type || 'Unspecified'}</span><span className="entry-category">{entry.category || 'No category'}</span></div><div className="entry-actions"><button type="button" className="icon-button" aria-label={`Edit expression: ${entry.text.slice(0, 80)}`} title="Edit expression" onClick={() => setEditor({ entry })}><Icon name="edit" size={17} /></button><button type="button" className="icon-button delete-button" aria-label={`Delete expression: ${entry.text.slice(0, 80)}`} title="Delete expression" onClick={() => setDeleteTarget(entry)}><Icon name="trash" size={17} /></button></div></div>
              <div className="entry-trust-line"><span className="entry-language">{languageLabels[entry.language ?? 'unspecified'] ?? entry.language}</span><span className={`review-badge ${entry.review_status === 'approved' ? 'review-approved' : 'review-unreviewed'}`}>{entry.review_status === 'approved' ? 'Approved' : 'Unreviewed'}</span></div>
              <h3>{entry.text}</h3>
              <div className="entry-glosses">
                {entry.french_gloss && <p lang="fr"><span aria-label="French meaning">FR</span>{entry.french_gloss}</p>}
                {entry.english_gloss && <p lang="en"><span aria-label="English meaning">EN</span>{entry.english_gloss}</p>}
                {!entry.french_gloss && !entry.english_gloss && <p className="no-gloss">A meaning waiting to be shared.</p>}
              </div>
              {entry.audio_filename && <AudioPlayer src={`/api/dataset/${encodeURIComponent(entry.id)}/audio`} filename={entry.audio_filename} active={active} />}
              <details className="entry-context"><summary>Context & record details<Icon name="chevron" size={14} /></summary>{entry.notes && <p>{entry.notes}</p>}{entry.contributor && <p><strong>Contributor:</strong> {entry.contributor}</p>}{entry.audio_filename && <p><strong>Audio file:</strong> {entry.audio_filename}</p>}<p className="record-id"><strong>ID:</strong> {entry.id}</p></details>
              <div className="entry-footer"><span><Icon name="location" size={14} />{entry.source_location || 'Location not recorded'}</span><time title={entry.timestamp}>{displayDate(entry.timestamp)}</time></div>
            </article>)}</div>}
    </div>
    <p className="privacy-caption"><Icon name="shield" size={15} /><span>Terminology is stored on your local backend. Browsing, saving and exporting do not contact Gemini. Explicit AI requests may use selected approved terms and meanings, not stored contributor details, private notes or the full library.</span></p>

    {active && editor && <EntryEditor entry={editor.entry} metadata={metadata} onClose={() => setEditor(null)} onSaved={(saved) => {
      setNotice(saved.review_status === 'approved' ? 'Saved locally as approved terminology.' : 'Saved locally. This entry is awaiting review.')
      setEditor(null)
      setRevision((value) => value + 1)
    }} />}
    {active && deleteTarget && <DeleteConfirmation entry={deleteTarget} onClose={() => setDeleteTarget(null)} onDeleted={() => {
      setNotice('Expression removed from your local collection.')
      setDeleteTarget(null)
      setRevision((value) => value + 1)
    }} />}
  </section>
}
