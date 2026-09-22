import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api } from './api'
import { EntryEditor } from './Collection'
import { CopyButton, ErrorNotice, Icon, Spinner } from './components'
import { IMPORT_ACCEPT, MAX_IMPORT_BYTES } from './importTypes'
import type { ImportDraft, ImportPreview, ImportReview } from './importTypes'
import { defaultMetadata, languageLabels, MAX_TEXT } from './types'
import type { DatasetLanguage, Metadata } from './types'
import { useRequest } from './useRequest'
import './imports.css'

function fileError(file: File | null): string {
  if (!file) return ''
  if (!/\.(txt|md|csv|json|docx|pdf)$/i.test(file.name)) {
    return 'Choose TXT, Markdown, CSV, JSON, DOCX or a text-layer PDF. Images, scans and recordings need a manual text transcript. Attach raw audio in Collection instead.'
  }
  if (!file.size) return 'This file is empty.'
  if (file.size > MAX_IMPORT_BYTES) return 'This file exceeds 12 MB. Split it before importing.'
  return ''
}

export function Imports({ active, onUseText, onOpenCollection }: {
  active: boolean
  onUseText: (text: string) => void
  onOpenCollection: () => void
}) {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [segment, setSegment] = useState(0)
  const [text, setText] = useState('')
  const [language, setLanguage] = useState<DatasetLanguage>('unspecified')
  const [metadata, setMetadata] = useState<Metadata>(defaultMetadata)
  const [review, setReview] = useState<ImportReview | null>(null)
  const [saved, setSaved] = useState<Set<string>>(new Set())
  const [notice, setNotice] = useState('')
  const [validation, setValidation] = useState('')
  const { pending, error, run, cancel, clearError } = useRequest()
  const { error: metadataError, run: loadMetadata, cancel: cancelMetadata } = useRequest()

  useEffect(() => {
    if (active) void loadMetadata((signal) => api<Metadata>('/metadata', { signal }), (value) => setMetadata({ ...defaultMetadata, ...value }))
    else {
      cancel()
      cancelMetadata()
      setReview(null)
    }
  }, [active, loadMetadata, cancel, cancelMetadata])

  function selectFile(next: File | null) {
    cancel()
    clearError()
    setPreview(null)
    setReview(null)
    setText('')
    setSaved(new Set())
    setNotice('')
    setFile(next)
    setValidation(fileError(next))
  }

  function extract(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!file || pending) return
    const invalid = fileError(file)
    if (invalid) { setValidation(invalid); return }
    const body = new FormData()
    body.append('file', file)
    setPreview(null)
    setText('')
    setSaved(new Set())
    setValidation('')
    setNotice('')
    void run(
      (signal) => api<ImportPreview>('/imports/preview', { method: 'POST', body, signal, timeout: 65000 }),
      (result) => {
        setPreview(result)
        setSegment(0)
        setText(result.segments[0] ?? '')
      },
    )
  }

  function openReview(key: string, draft?: ImportDraft) {
    if (!preview) return
    setReview({
      key,
      fields: {
        text: draft?.text ?? text,
        entry_type: draft?.entry_type ?? 'Sentence',
        language: draft?.language ?? language,
        french_gloss: draft?.french_gloss ?? '',
        english_gloss: draft?.english_gloss ?? '',
        lexical_category: draft?.lexical_category ?? '',
        category: draft?.category ?? 'Other',
        source_location: draft?.source_location ?? '',
        contributor: draft?.contributor ?? '',
        review_status: 'unreviewed',
        notes: draft?.notes ?? `Source file: ${preview.filename}. Locally extracted text; verify the manual transcription, source, context and permissions. Importing does not establish authenticity.`,
      },
    })
  }

  return <section className="page imports-page" aria-labelledby="imports-title">
    <div className="page-intro">
      <div><div className="eyebrow">MANUAL CORPUS PREPARATION</div><h1 id="imports-title">Document import</h1><p>Bring your own transcript, inspect the extracted text, then annotate statements and words yourself.</p></div>
    </div>
    <div className="notice notice-subtle"><Icon name="info" size={20} /><div><strong>Extraction is not transcription or fieldwork verification.</strong><p>Use text you transcribed manually from genuine observations. No missing statements, glosses or provenance are generated. Scanned PDFs need a manual transcript; a mixed PDF may omit image-only pages and will show a warning.</p></div></div>
    <form className="import-card" onSubmit={extract}>
      <div className="import-heading"><Icon name="upload" size={23} /><div><h2>Source document</h2><p>One file · up to 12 MB · 40 PDF pages · 40,000 extracted characters</p></div></div>
      <div className="field"><label htmlFor="language-file">Text document</label><input id="language-file" type="file" accept={IMPORT_ACCEPT} disabled={pending} onChange={(event) => selectFile(event.target.files?.[0] ?? null)} /></div>
      <div className="import-formats"><p><strong>Local server extraction:</strong> TXT, Markdown, CSV, JSON, DOCX and text-layer PDF. Preview uploads only this file to your application server, not to an external processing provider.</p><p>CSV and JSON annotation fields are preserved for review. Plain text remains a passage; split it into real statements yourself rather than treating a whole file as one statement.</p></div>
      <p className="helper-text">No collection entry is saved automatically. The source upload is not retained as an attachment; keep your own original. Previews and corrections remain in this tab only.</p>
      <ErrorNotice message={validation || error} />
      <div className="import-actions"><button type="submit" className="button button-primary" disabled={!file || pending || Boolean(fileError(file))}>{pending ? <Spinner label="Extracting local document" /> : <Icon name="code" size={18} />}{pending ? 'Extracting text…' : 'Preview source text'}</button>{pending && <button type="button" className="text-button" onClick={cancel}>Cancel</button>}</div>
    </form>
    <div className="import-card"><h2>Have a recording instead?</h2><p>Keep raw audio with a Collection entry. Listen, type the transcript manually, and record source context and permission. Recording never fills or verifies the text for you.</p><button type="button" className="button button-secondary" onClick={onOpenCollection}><Icon name="mic" size={18} />Open Collection for raw recordings</button></div>

    {preview && <section className="import-card" aria-labelledby="import-preview-title">
      <div className="import-heading"><Icon name="collection" size={23} /><div><h2 id="import-preview-title">Content preview</h2><p>{preview.filename} · Extracted locally · {preview.text.length.toLocaleString()} characters</p></div></div>
      {preview.warnings.map((warning, index) => <div className="notice notice-subtle" role="status" key={index}><Icon name="info" size={17} /><span>{warning}</span></div>)}
      <details className="import-original"><summary>Original extracted text (read-only)</summary><pre>{preview.text}</pre><CopyButton text={preview.text} /></details>
      <div className="field"><label htmlFor="import-segment">Choose a passage</label><select id="import-segment" value={segment} onChange={(event) => {
        const next = Number(event.target.value)
        setSegment(next)
        setText(preview.segments[next] ?? '')
        setNotice('')
      }}>{preview.segments.map((part, index) => <option key={index} value={index}>Passage {index + 1} of {preview.segments.length} ({part.length.toLocaleString()} characters)</option>)}</select></div>
      <p className="helper-text">Passages fit the manual compiler input. Review each passage of a longer file separately. Changing passage discards unsaved corrections below; the original file is not changed.</p>
      <div className="field"><label htmlFor="import-reviewed-text">Review and correct this passage</label><textarea id="import-reviewed-text" rows={7} maxLength={MAX_TEXT} value={text} onChange={(event) => { setText(event.target.value); setNotice('') }} /><span className="field-hint">{text.length.toLocaleString()} / 4,000 characters · spacing preserved</span></div>
      <div className="import-actions"><button type="button" className="button button-primary" disabled={!text.trim() || text.length > MAX_TEXT} onClick={() => onUseText(text)}><Icon name="code" size={18} />Open in compiler</button></div>
      <p className="helper-text">This fills the manual test draft unchanged. It does not parse, save, approve or add anything to the corpus.</p>
    </section>}

    {preview && <section className="import-card" aria-labelledby="import-learn-title">
      <div className="import-heading"><Icon name="collection" size={23} /><div><h2 id="import-learn-title">Manual statement & word annotation</h2><p>Review one statement or word, its topic and provenance before explicitly saving it.</p></div></div>
      <ErrorNotice message={metadataError} />
      <div className="field"><label htmlFor="import-language">Language context for new entries</label><select id="import-language" value={language} onChange={(event) => setLanguage(event.target.value as DatasetLanguage)}>{defaultMetadata.dataset_languages.map((value) => <option key={value} value={value}>{languageLabels[value as DatasetLanguage]}</option>)}</select></div>
      <div className="import-actions"><button type="button" className="button button-secondary" disabled={!text.trim() || text.length > MAX_TEXT} onClick={() => openReview('manual')}><Icon name="plus" size={18} />Review passage as an entry</button></div>
      {preview.drafts.length > 0 && <div className="import-candidates">{preview.drafts.map((draft, index) => {
        const key = `file:${index}`
        return <article className="import-candidate" key={key}>
          <div className="import-candidate-heading"><span className="small-caps">Imported annotation · {draft.language}</span><span className="small-caps">{saved.has(key) ? 'SAVED IN PROJECT' : 'UNREVIEWED'}</span></div>
          <h3>{draft.text}</h3><dl><div><dt>French</dt><dd>{draft.french_gloss || 'Meaning not supplied'}</dd></div><div><dt>English</dt><dd>{draft.english_gloss || 'Meaning not supplied'}</dd></div></dl>
          <button type="button" className="button button-secondary" disabled={saved.has(key)} onClick={() => openReview(key, draft)}><Icon name={saved.has(key) ? 'check' : 'edit'} size={17} />{saved.has(key) ? 'Saved - manage in Collection' : 'Review and save candidate'}</button>
        </article>
      })}</div>}
      {notice && <p className="import-save-notice" role="status">{notice}</p>}
      <button type="button" className="text-button" onClick={onOpenCollection}>Open collection to review saved records</button>
      <p className="helper-text">Approval records your review, not authenticity. Importing never changes the project’s manual-transcription declaration. Keep source restrictions and uncertainty in the notes.</p>
    </section>}
    {review && <EntryEditor metadata={metadata} initialDraft={review.fields} onClose={() => setReview(null)} onSaved={(entry) => {
      setSaved((previous) => new Set(previous).add(review.key))
      setNotice(`Saved record ${entry.id}. ${entry.review_status === 'approved' ? 'Your review is recorded; source authenticity is not certified.' : 'This entry remains unreviewed. Check its transcription and provenance.'}`)
      setReview(null)
    }} />}
  </section>
}
