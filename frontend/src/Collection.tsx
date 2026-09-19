import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { api, isCancelled, messageOf } from './api'
import { ErrorNotice, Icon, Modal, Spinner, TokenAnalysis } from './components'
import { defaultMetadata, languageLabels, MAX_TEXT } from './types'
import type { Analysis, Dataset, DatasetEntry, DatasetLanguage, EditableEntry, Metadata, ReviewStatus } from './types'
import { useRequest } from './useRequest'

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
  const { pending, error, run, clearError } = useRequest()
  const categories = uniqueOptions([...metadata.categories, draft.category])
  const entryTypes = uniqueOptions([...metadata.entry_types, draft.entry_type])
  const datasetLanguages = uniqueOptions([...(metadata.dataset_languages ?? defaultMetadata.dataset_languages), draft.language])
  const lexicalCategories = uniqueOptions([...(metadata.lexical_categories ?? []), draft.lexical_category])

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
    if (!draft.text.trim()) {
      setValidationError('Please add an expression. It cannot contain only spaces.')
      return
    }
    const values = { ...draft, text: entry && draft.text === entry.text ? draft.text : draft.text.trim() }
    const original = entry ? editableFields(entry) : null
    const changes = original
      ? Object.fromEntries(Object.entries(values).filter(([field, value]) => original[field as keyof EditableEntry] !== value))
      : values
    if (entry && !Object.keys(changes).length) {
      onClose()
      return
    }
    const body = { ...changes, review_status: values.review_status }
    void run(
      (signal) => api<DatasetEntry>(entry ? `/dataset/${encodeURIComponent(entry.id)}` : '/dataset', {
        method: entry ? 'PATCH' : 'POST', body, signal,
      }),
      onSaved,
    )
  }

  return <Modal title={entry ? 'Review this expression' : 'Add an expression to learn'} onClose={onClose} busy={pending} className="entry-modal" initialFocus={expressionInput}>
    <p className="modal-description">{entry ? 'Review the wording, language, and meanings. Only changed fields and your review decision are submitted; other stored values are preserved.' : 'Keep Cameroon Francanglais and Cameroon Pidgin distinct. Save a draft, or approve after a human review.'} <span>An expression is required. Missing context is okay; never invent a speaker, location, or fieldwork source.</span></p>
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
          {draft.entry_type === 'Word' && <div className="field"><label htmlFor="entry-lexical-category">Lexical category <span>optional</span></label><select id="entry-lexical-category" value={draft.lexical_category} disabled={pending} onChange={(event) => update('lexical_category', event.target.value)}><option value="">No lexical category</option>{lexicalCategories.map((category) => <option value={category} key={category}>{category}</option>)}</select><span className="field-hint">A local lexer terminal, not proof of meaning or language.</span></div>}
        </div>
        <div className="field-grid">
          <div className="field"><label htmlFor="entry-french">French meaning <span>optional</span></label><textarea id="entry-french" rows={3} maxLength={MAX_TEXT} value={draft.french_gloss} lang="fr" disabled={pending} onChange={(event) => update('french_gloss', event.target.value)} placeholder="Le sens en français…" /></div>
          <div className="field"><label htmlFor="entry-english">English meaning <span>optional</span></label><textarea id="entry-english" rows={3} maxLength={MAX_TEXT} value={draft.english_gloss} lang="en" disabled={pending} onChange={(event) => update('english_gloss', event.target.value)} placeholder="The meaning in English…" /></div>
        </div>
        <div className="field-grid">
          <div className="field"><label htmlFor="entry-location">Source location <span>optional</span></label><input id="entry-location" maxLength={200} value={draft.source_location} disabled={pending} onChange={(event) => update('source_location', event.target.value)} placeholder="e.g. Yaoundé, campus" /></div>
          <div className="field"><label htmlFor="entry-contributor">Contributor <span>optional</span></label><input id="entry-contributor" maxLength={200} value={draft.contributor} disabled={pending} onChange={(event) => update('contributor', event.target.value)} placeholder="Name or alias" /></div>
        </div>
        <div className="field"><label htmlFor="entry-notes">Context & notes <span>optional</span></label><textarea id="entry-notes" rows={3} maxLength={2000} value={draft.notes} disabled={pending} onChange={(event) => update('notes', event.target.value)} placeholder="When is it used? What makes it special?" /></div>
        <div className="entry-review">
          <label className="checkbox-label"><input type="checkbox" checked={draft.review_status === 'approved'} disabled={pending} onChange={(event) => update('review_status', event.target.checked ? 'approved' : 'unreviewed')} /><span>I have reviewed the language, expression, and meanings. Approve this entry for dataset-backed learning.</span></label>
          <p>Changing a field clears approval so you can review the new version. Unchecked entries are saved as <strong>Unreviewed</strong> and excluded from trusted translation/chat matches. Approval is your review, not a claim that every usage is correct.</p>
          <p>Approved text and glosses may be selected for an explicitly submitted AI request with dataset use enabled. Names, locations, notes, and other record metadata stay local.</p>
        </div>
        {entry && <details className="record-details"><summary>Original record details <Icon name="chevron" size={15} /></summary><dl><div><dt>Record ID</dt><dd>{entry.id}</dd></div><div><dt>Added</dt><dd>{displayDate(entry.timestamp)}</dd></div><div><dt>Audio filename</dt><dd>{entry.audio_filename || 'No audio attached'} <span className="helper-text">(read-only; no upload needed)</span></dd></div></dl></details>}
        <ErrorNotice message={validationError || error} />
      </div>
      <div className="modal-footer"><span className="helper-text"><Icon name="shield" size={15} />This save stays local.</span><div className="submit-actions"><button type="button" className="button button-secondary" onClick={onClose} disabled={pending}>Cancel</button><button type="submit" className="button button-primary" disabled={pending}>{pending ? <Spinner label="Saving expression" /> : <Icon name="check" size={17} />}{pending ? 'Saving…' : draft.review_status === 'approved' ? 'Save approved entry' : 'Save unreviewed'}</button></div></div>
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

function LexerLab({ active }: { active: boolean }) {
  const [text, setText] = useState('')
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const { pending, error, run, cancel, clearError } = useRequest()
  useEffect(() => {
    if (!active) cancel()
  }, [active, cancel])
  return <details className="lexer-lab">
    <summary><span className="lexer-icon"><Icon name="code" size={22} /></span><span><strong>Look inside the language</strong><span>Explore tokens with the local lexer. No AI, no external request.</span></span><span className="local-badge">LOCAL TOOL</span><Icon name="chevron" size={18} /></summary>
    <div className="lexer-content">
      <form onSubmit={(event) => {
        event.preventDefault()
        if (!text.trim() || pending) return
        setAnalysis(null)
        void run((signal) => api<Analysis>('/analyze', { method: 'POST', body: { text: text.trim() }, signal }), setAnalysis)
      }}>
        <div className="field"><label htmlFor="lexer-text">An expression to inspect</label><textarea id="lexer-text" rows={3} value={text} maxLength={MAX_TEXT} onChange={(event) => { cancel(); clearError(); setAnalysis(null); setText(event.target.value) }} placeholder="Paste a Francanglais expression…" /><span className="field-hint">{text.length.toLocaleString()} / 4,000 characters</span></div>
        <div className="lexer-submit"><p className="helper-text">Only sent to your local backend. Your collection isn’t analyzed automatically.</p><div className="submit-actions">{pending && <button type="button" className="text-button" onClick={cancel}>Cancel</button>}<button type="submit" className="button button-primary" disabled={!text.trim() || pending}>{pending ? <Spinner label="Analyzing expression" /> : <Icon name="code" size={18} />}{pending ? 'Analyzing…' : 'Analyze expression'}</button></div></div>
      </form>
      <ErrorNotice message={error} />
      {analysis && <TokenAnalysis analysis={analysis} />}
    </div>
  </details>
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
      <div><div className="eyebrow"><span className="eyebrow-line" />COLLECT · COMPARE · REVIEW</div><h1 id="collection-title">Build what<br /><em>we can learn.</em></h1><p>Your local Francanglais and Cameroon Pidgin collection, aligned with French and English meanings. Only human-approved entries support trusted retrieval.</p></div>
      <button type="button" className="button button-primary" onClick={() => setEditor({ entry: null })}><Icon name="plus" size={18} />Add expression</button>
    </div>
    <div className="collection-stats" aria-label="Counts across the entire local dataset">
      <div><span className="stat-icon"><Icon name="collection" size={23} /></span><div><strong>{dataset ? dataset.total.toLocaleString() : '—'}</strong><span>expressions collected</span></div><span className="stat-index" aria-hidden="true">01</span></div>
      <div><span className="stat-icon peach"><Icon name="globe" size={23} /></span><div><strong>{dataset ? Object.values(dataset.by_category).filter((count) => count > 0).length : '—'}</strong><span>everyday categories</span></div><span className="stat-index" aria-hidden="true">02</span></div>
      <div><span className="stat-icon lavender"><Icon name="shield" size={23} /></span><div><strong className="stat-word">Yours.</strong><span>stored locally, always in reach</span></div><span className="stat-index" aria-hidden="true">03</span></div>
    </div>
    <div className="collection-summary"><span className="helper-text">Counts cover your whole collection, not just the search results.</span>{dataset && <div className="type-counts">{Object.entries(dataset.by_type).map(([type, count]) => <span key={type}>{type || 'Unspecified'} <strong>{count}</strong></span>)}</div>}</div>
    <div className="notice notice-subtle"><Icon name="shield" size={18} /><p><strong>Saved is not the same as approved.</strong> Legacy records without a review status remain unreviewed; records without a language remain unspecified. Mixed-language entries are distinct. Review missing details rather than guessing. <a href="#imports">Import material to preview and review</a>.</p></div>

    <div className="collection-tools">
      <div className="search-field"><Icon name="search" size={20} /><label className="sr-only" htmlFor="collection-query">Search your collection</label><input id="collection-query" type="search" maxLength={200} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search expressions, meanings, stories…" /></div>
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
    <div className="collection-list-heading"><h2>The collection <span>{loading ? 'Updating…' : error ? 'Unavailable' : `${entries.length.toLocaleString()} ${entries.length === 1 ? 'expression' : 'expressions'}`}</span></h2>{hasFilters && <button type="button" className="text-button" onClick={resetFilters}>Clear filters <Icon name="close" size={14} /></button>}</div>

    <div className="collection-results" aria-busy={loading}>
      {loading ? <div className="collection-loading" role="status"><Spinner label="Loading your collection" /><p>Finding the stories in your collection…</p><div className="entry-skeletons" aria-hidden="true"><div /><div /><div /></div></div> :
        error ? <div className="collection-error"><Icon name="collection" size={34} /><h3>Your collection is still yours.</h3><p>We just couldn’t load it right now.</p><ErrorNotice message={error} onRetry={() => setRevision((value) => value + 1)} /></div> :
          !entries.length ? <div className="collection-empty"><span className="empty-collection-icon"><Icon name={hasFilters ? 'search' : 'collection'} size={35} /></span><h3>{hasFilters ? 'No expressions found.' : 'A language lives in its stories.'}</h3><p>{hasFilters ? 'Try another word or a different category. There might be a story just around the corner.' : 'Your collection is ready for its first expression. Start with something you hear every day.'}</p><button type="button" className="button button-secondary" onClick={hasFilters ? resetFilters : () => setEditor({ entry: null })}>{hasFilters ? 'Clear all filters' : 'Add your first expression'}<Icon name={hasFilters ? 'refresh' : 'plus'} size={16} /></button></div> :
            <div className="entry-grid">{entries.map((entry) => <article className="entry-card" key={entry.id}>
              <div className="entry-topline"><div className="entry-badges"><span className="entry-type">{entry.entry_type || 'Unspecified'}</span><span className="entry-category">{entry.category || 'No category'}</span></div><div className="entry-actions"><button type="button" className="icon-button" aria-label={`Edit expression: ${entry.text.slice(0, 80)}`} title="Edit expression" onClick={() => setEditor({ entry })}><Icon name="edit" size={17} /></button><button type="button" className="icon-button delete-button" aria-label={`Delete expression: ${entry.text.slice(0, 80)}`} title="Delete expression" onClick={() => setDeleteTarget(entry)}><Icon name="trash" size={17} /></button></div></div>
              <div className="entry-trust-line"><span className="entry-language">{languageLabels[entry.language ?? 'unspecified'] ?? entry.language}</span><span className={`review-badge ${entry.review_status === 'approved' ? 'review-approved' : 'review-unreviewed'}`}>{entry.review_status === 'approved' ? 'Approved · trusted' : 'Unreviewed'}</span>{entry.lexical_category && <code>{entry.lexical_category}</code>}</div>
              <h3>{entry.text}</h3>
              <div className="entry-glosses">
                {entry.french_gloss && <p lang="fr"><span aria-label="French meaning">FR</span>{entry.french_gloss}</p>}
                {entry.english_gloss && <p lang="en"><span aria-label="English meaning">EN</span>{entry.english_gloss}</p>}
                {!entry.french_gloss && !entry.english_gloss && <p className="no-gloss">A meaning waiting to be shared.</p>}
              </div>
              <details className="entry-context"><summary>Context & record details<Icon name="chevron" size={14} /></summary>{entry.notes && <p>{entry.notes}</p>}{entry.contributor && <p><strong>Contributor:</strong> {entry.contributor}</p>}{entry.audio_filename && <p><strong>Audio file:</strong> {entry.audio_filename} <span className="helper-text">(reference only)</span></p>}<p className="record-id"><strong>ID:</strong> {entry.id}</p></details>
              <div className="entry-footer"><span><Icon name="location" size={14} />{entry.source_location || 'Location not recorded'}</span><time title={entry.timestamp}>{displayDate(entry.timestamp)}</time></div>
            </article>)}</div>}
    </div>
    <LexerLab active={active} />
    <p className="privacy-caption"><Icon name="shield" size={15} /><span>Collection records are stored on your backend’s local disk. Browsing, saving, and local lexer analysis do not send them to Gemini. Explicit AI requests with dataset use enabled may share selected approved text/gloss matches only; contributor, provenance, notes, and the full corpus are not included.</span></p>

    {active && editor && <EntryEditor entry={editor.entry} metadata={metadata} onClose={() => setEditor(null)} onSaved={(saved) => {
      setNotice(saved.review_status === 'approved' ? 'Saved locally as approved. This entry is eligible for trusted dataset matching.' : 'Saved locally as unreviewed. Review and approve before trusted dataset matching.')
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
