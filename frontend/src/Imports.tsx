import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { api } from './api'
import { AudioRecorder, isAudioFile } from './AudioRecorder'
import { EntryEditor } from './Collection'
import { CopyButton, ErrorNotice, Icon, Spinner } from './components'
import { IMPORT_ACCEPT, MAX_IMPORT_BYTES } from './importTypes'
import type { ImportDraft, ImportPreview, ImportReview, ImportSuggestions } from './importTypes'
import { defaultMetadata, MAX_TEXT } from './types'
import type { Metadata } from './types'
import { useRequest } from './useRequest'
import './imports.css'

export function Imports({ active, aiAvailable, onUseText, onAskAI, onOpenCollection }: {
  active: boolean
  aiAvailable: boolean
  onUseText: (text: string) => void
  onAskAI: (text: string) => void
  onOpenCollection: () => void
}) {
  const [file, setFile] = useState<File | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const [recording, setRecording] = useState(false)
  const [allowCloud, setAllowCloud] = useState(false)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [segment, setSegment] = useState(0)
  const [text, setText] = useState('')
  const [language, setLanguage] = useState<'francanglais' | 'pidgin' | 'mixed'>('francanglais')
  const [suggestions, setSuggestions] = useState<ImportSuggestions | null>(null)
  const [metadata, setMetadata] = useState<Metadata>(defaultMetadata)
  const [review, setReview] = useState<ImportReview | null>(null)
  const [saved, setSaved] = useState<Set<string>>(new Set())
  const [notice, setNotice] = useState('')
  const [validation, setValidation] = useState('')
  const { pending, error, run, cancel, clearError } = useRequest()
  const { pending: suggesting, error: suggestionError, run: runSuggestion, cancel: cancelSuggestion, clearError: clearSuggestionError } = useRequest()
  const { error: metadataError, run: loadMetadata, cancel: cancelMetadata } = useRequest()

  useEffect(() => {
    if (active) void loadMetadata((signal) => api<Metadata>('/metadata', { signal }), setMetadata)
    else {
      cancel()
      cancelSuggestion()
      cancelMetadata()
    }
  }, [active, loadMetadata, cancel, cancelSuggestion, cancelMetadata])

  function clearSuggestions() {
    cancelSuggestion()
    clearSuggestionError()
    setSuggestions(null)
    setSaved((previous) => new Set([...previous].filter((key) => !key.startsWith('ai:'))))
  }

  function selectFile(next: File | null) {
    cancel()
    clearError()
    setAllowCloud(false)
    clearSuggestions()
    setPreview(null)
    setText('')
    setSaved(new Set())
    setNotice('')
    setFile(next)
    setValidation(next && next.size > MAX_IMPORT_BYTES ? 'This file exceeds 12 MB. Split or compress it before importing.' : '')
  }

  function extract(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!file || pending) return
    if (recording) {
      setValidation('Stop recording before previewing the source.')
      return
    }
    if (!file.size || file.size > MAX_IMPORT_BYTES) {
      setValidation(file.size ? 'This file exceeds 12 MB.' : 'This file is empty.')
      return
    }
    const body = new FormData()
    body.append('file', file)
    body.append('allow_cloud_processing', String(allowCloud && aiAvailable))
    clearSuggestions()
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

  function suggest() {
    if (!text.trim() || !aiAvailable || suggesting) return
    setNotice('')
    void runSuggestion(
      (signal) => api<ImportSuggestions>('/imports/suggest', { method: 'POST', body: { text, language }, signal, timeout: 60000 }),
      (result) => {
        setSuggestions(result)
        setSaved((previous) => new Set([...previous].filter((key) => !key.startsWith('ai:'))))
      },
    )
  }

  function openReview(key: string, draft?: ImportDraft) {
    if (!preview) return
    const origin = draft ? (key.startsWith('ai:') ? 'AI-proposed glosses; human review required.' : 'Imported alignment; human review required.') : 'Manual selection from the imported text; check meanings before approving.'
    setReview({
      key,
      fields: {
        text: draft?.text ?? text,
        entry_type: draft?.entry_type ?? 'Sentence',
        language: draft?.language ?? language,
        french_gloss: draft?.french_gloss ?? '',
        english_gloss: draft?.english_gloss ?? '',
        lexical_category: draft?.lexical_category ?? '',
        review_status: 'unreviewed',
        notes: `Source file: ${preview.filename}. ${preview.method === 'gemini' ? 'AI transcript/OCR; check against the original.' : 'Locally extracted text; source and context need review.'} ${origin}`,
      },
    })
  }

  const candidates = [
    ...(preview?.drafts ?? []).map((draft, index) => ({ key: `file:${index}`, draft, kind: 'Imported alignment' })),
    ...(suggestions?.drafts ?? []).map((draft, index) => ({ key: `ai:${index}`, draft, kind: 'AI suggestion' })),
  ]

  return <section className="page imports-page" aria-labelledby="imports-title">
    <div className="page-intro">
      <div><div className="eyebrow">CONTENT PROCESSING</div><h1 id="imports-title">Documents & audio</h1><p>Extract text, transcribe permitted media and prepare content for translation or terminology review.</p></div>
    </div>
    <form className="import-card" onSubmit={extract}>
      <div className="import-heading"><Icon name="upload" size={23} /><div><h2>Source file</h2><p>Up to 12 MB per file · 40 PDF pages · 40,000 extracted characters</p></div></div>
      <div className="field"><label htmlFor="language-file">Document, image, audio or video</label><input ref={fileInput} id="language-file" type="file" accept={IMPORT_ACCEPT} disabled={pending || recording} onChange={(event) => selectFile(event.target.files?.[0] ?? null)} /></div>
      <AudioRecorder active={active} disabled={pending} file={file && isAudioFile(file) ? file : null} showPicker={false} onBusyChange={setRecording} onFile={(recorded) => {
        if (fileInput.current) fileInput.current.value = ''
        selectFile(recorded)
      }} />
      <div className="import-formats"><p><strong>Server-side extraction without AI:</strong> TXT, Markdown, CSV, JSON, text PDFs and DOCX. Preview uploads your selected file to this server.</p><p><strong>Gemini transcription / OCR:</strong> PNG, JPEG, WebP, MP3, WAV, M4A, OGG, FLAC, MP4, WebM, MOV and scanned PDFs. Use short clips; long transcripts can exceed the AI response limit. Unsupported files are rejected, not silently converted.</p></div>
      <label className="import-consent"><input type="checkbox" checked={allowCloud} disabled={pending || recording || !aiAvailable} onChange={(event) => setAllowCloud(event.target.checked)} /><span>I consent to sending this file to Gemini when transcription or OCR is needed. I have permission to process its content.</span></label>
      {!aiAvailable && <p className="helper-text">Gemini is unavailable. Local documents still work; media transcription needs a configured API key.</p>}
      <p className="helper-text">Source files are processed temporarily. No terminology is saved and no translation is submitted automatically. Provider data policies apply to cloud processing.</p>
      <ErrorNotice message={validation || error} />
      <div className="import-actions"><button type="submit" className="button button-primary" disabled={!file || pending || recording || file.size > MAX_IMPORT_BYTES}>{pending ? <Spinner label="Extracting or transcribing" /> : <Icon name="code" size={18} />}{pending ? 'Processing source...' : 'Preview source text'}</button>{pending && <button type="button" className="text-button" onClick={cancel}>Cancel</button>}</div>
    </form>

    {preview && <section className="import-card" aria-labelledby="import-preview-title">
      <div className="import-heading"><Icon name="collection" size={23} /><div><h2 id="import-preview-title">Content preview</h2><p>{preview.filename} · {preview.method === 'local' ? 'Extracted locally' : 'Unreviewed AI transcript'} · {preview.text.length.toLocaleString()} characters</p></div></div>
      {preview.warnings.map((warning, index) => <div className="notice notice-subtle" key={index}><Icon name="info" size={17} /><span>{warning}</span></div>)}
      <details className="import-original"><summary>Original extracted text (read-only)</summary><pre>{preview.text}</pre><CopyButton text={preview.text} /></details>
      <div className="field"><label htmlFor="import-segment">Choose a passage</label><select id="import-segment" value={segment} onChange={(event) => {
        const next = Number(event.target.value)
        clearSuggestions()
        setSegment(next)
        setText(preview.segments[next] ?? '')
        setNotice('')
      }}>{preview.segments.map((part, index) => <option key={index} value={index}>Passage {index + 1} of {preview.segments.length} ({part.length.toLocaleString()} characters)</option>)}</select></div>
      <p className="helper-text">Each passage fits one translation or AI request. Review every passage of a longer file separately. Corrections below are not written back to the original file; changing passage discards those corrections.</p>
      <div className="field"><label htmlFor="import-reviewed-text">Review and correct this passage</label><textarea id="import-reviewed-text" rows={7} maxLength={MAX_TEXT} value={text} onChange={(event) => { clearSuggestions(); setText(event.target.value); setNotice('') }} /><span className="field-hint">{text.length.toLocaleString()} / 4,000 characters</span></div>
      <div className="import-actions"><button type="button" className="button button-primary" disabled={!text.trim()} onClick={() => onUseText(text)}><Icon name="translate" size={18} />Open in translator</button><button type="button" className="button button-secondary" disabled={!text.trim()} onClick={() => onAskAI(text)}><Icon name="sparkles" size={18} />Open in assistant</button></div>
      <p className="helper-text">These buttons fill a draft. Review the language direction and press Translate or Send there to submit it. Previews remain only in this tab until reload.</p>
    </section>}

    {preview && <section className="import-card" aria-labelledby="import-learn-title">
      <div className="import-heading"><Icon name="collection" size={23} /><div><h2 id="import-learn-title">Terminology extraction</h2><p>Review source expressions and their meanings before adding them to your terminology library.</p></div></div>
      <ErrorNotice message={metadataError} />
      <div className="field"><label htmlFor="import-language">Language context for new entries</label><select id="import-language" value={language} onChange={(event) => {
        const next = event.target.value
        if (next === 'francanglais' || next === 'pidgin' || next === 'mixed') { clearSuggestions(); setLanguage(next) }
      }}><option value="francanglais">Francanglais / Camfranglais</option><option value="pidgin">Cameroon Pidgin</option><option value="mixed">Mixed / compare both</option></select></div>
      <div className="import-actions"><button type="button" className="button button-secondary" disabled={!text.trim()} onClick={() => openReview('manual')}><Icon name="plus" size={18} />Review passage as an entry</button><button type="button" className="button button-primary" disabled={!text.trim() || !aiAvailable || suggesting} onClick={suggest}>{suggesting ? <Spinner label="Suggesting vocabulary" /> : <Icon name="sparkles" size={18} />}{suggesting ? 'Finding candidates...' : 'Ask AI for vocabulary candidates'}</button>{suggesting && <button type="button" className="text-button" onClick={cancelSuggestion}>Cancel</button>}</div>
      <p className="helper-text">Asking for candidates sends the corrected passage and selected language context to Gemini. Proposed glosses are not verified meanings. No extra file, corpus or contributor metadata is attached, but any personal details left in the passage will be sent.</p>
      <ErrorNotice message={suggestionError} />
      {suggestions?.warnings.map((warning) => <p className="helper-text" key={warning}>{warning}</p>)}
      {suggestions && !suggestions.drafts.length && <p className="import-empty" role="status">No relevant vocabulary candidates were suggested for this passage. You can still add an entry manually.</p>}
      {candidates.length > 0 && <div className="import-candidates">{candidates.map(({ key, draft, kind }) => <article className="import-candidate" key={key}>
        <div className="import-candidate-heading"><span className="small-caps">{kind} · {draft.language}</span><span className="small-caps">{saved.has(key) ? 'SAVED LOCALLY' : 'UNREVIEWED'}</span></div>
        <h3>{draft.text}</h3><dl><div><dt>French</dt><dd>{draft.french_gloss || 'Meaning not supplied'}</dd></div><div><dt>English</dt><dd>{draft.english_gloss || 'Meaning not supplied'}</dd></div></dl>
        <button type="button" className="button button-secondary" disabled={saved.has(key)} onClick={() => openReview(key, draft)}><Icon name={saved.has(key) ? 'check' : 'edit'} size={17} />{saved.has(key) ? 'Saved - manage in Collection' : 'Review and save candidate'}</button>
      </article>)}</div>}
      {notice && <p className="import-save-notice" role="status">{notice}</p>}
      <button type="button" className="text-button" onClick={onOpenCollection}>Open collection to review saved records</button>
      <p className="helper-text">Approval records your review, not universal correctness. Keep regional context, source restrictions and uncertainty in the entry notes.</p>
    </section>}
    {review && <EntryEditor entry={null} metadata={metadata} initialDraft={review.fields} onClose={() => setReview(null)} onSaved={(entry) => {
      setSaved((previous) => new Set(previous).add(review.key))
      setNotice(`Saved record ${entry.id}. ${entry.review_status === 'approved' ? 'Approved terminology is now available for matching.' : 'Review this entry before using it as approved terminology.'}`)
      setReview(null)
    }} />}
  </section>
}
