import { useEffect, useId, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { languageLabels, translationLanguages } from './types'
import type { Analysis, AnswerOrigin, DatasetEvidence, Language, TranslationLanguage } from './types'
import type { Dictation, ReadAloud } from './voice'

export type IconName =
  | 'translate' | 'sparkles' | 'collection' | 'arrow' | 'mic' | 'stop'
  | 'volume' | 'copy' | 'check' | 'close' | 'search' | 'plus' | 'edit'
  | 'trash' | 'shield' | 'globe' | 'chevron' | 'refresh' | 'info' | 'code'
  | 'send' | 'location' | 'leaf' | 'headphones' | 'swap' | 'upload'

const iconPaths: Record<IconName, ReactNode> = {
  translate: <><path d="M3 5h12M9 3v2m-4 4c2 4 5 6 8 7M13 5c-1 5-5 9-10 12m11 4 4-10 4 10m-6.5-4h5" /></>,
  sparkles: <><path d="m12 3 2.7 6.3L21 12l-6.3 2.7L12 21l-2.7-6.3L3 12l6.3-2.7L12 3Z" /><path d="m20 2 .6 1.4L22 4l-1.4.6L20 6l-.6-1.4L18 4l1.4-.6L20 2Z" /></>,
  collection: <><rect x="4" y="3" width="16" height="18" rx="3" /><path d="M8 3v18m4-12h4m-4 4h4" /></>,
  arrow: <><path d="M4 12h16m-6-6 6 6-6 6" /></>,
  mic: <><rect x="9" y="3" width="6" height="12" rx="3" /><path d="M5 10v2a7 7 0 0 0 14 0v-2m-7 9v3m-4 0h8" /></>,
  stop: <rect x="6" y="6" width="12" height="12" rx="2" />,
  volume: <><path d="m11 4-6 5H2v6h3l6 5V4Zm4 4a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14" /></>,
  copy: <><rect x="8" y="8" width="12" height="13" rx="2" /><path d="M15 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3" /></>,
  check: <path d="m5 12 4 4L19 6" />,
  close: <path d="m6 6 12 12M6 18 18 6" />,
  search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  edit: <><path d="m15 5 4 4M4 20l5-1L20 8a3 3 0 0 0-4-4L5 15l-1 5Z" /></>,
  trash: <><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7" /></>,
  shield: <><path d="m12 3 8 3v6c0 4-4 7-8 9-4-2-8-5-8-9V6l8-3Z" /><path d="m8 12 3 3 5-6" /></>,
  globe: <><circle cx="12" cy="12" r="9" /><ellipse cx="12" cy="12" rx="4" ry="9" /><path d="M3 12h18" /></>,
  chevron: <path d="m8 5 7 7-7 7" />,
  refresh: <><path d="M20 8a8 8 0 0 0-14-3L3 8m0-5v5h5M4 16a8 8 0 0 0 14 3l3-3m0 5v-5h-5" /></>,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v6m0-10v.1" /></>,
  code: <><path d="m8 6-6 6 6 6m8-12 6 6-6 6m-3-14-2 16" /></>,
  send: <><path d="m21 3-7 18-4-7-7-4L21 3ZM10 14 21 3" /></>,
  location: <><path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 0 1 14 0Z" /><circle cx="12" cy="10" r="2" /></>,
  leaf: <><path d="M20 3c-8-1-15 2-15 9a7 7 0 0 0 7 7c7 0 9-8 8-16ZM3 21 15 9" /></>,
  headphones: <><path d="M4 14v-3a8 8 0 0 1 16 0v3" /><rect x="3" y="12" width="4" height="8" rx="2" /><rect x="17" y="12" width="4" height="8" rx="2" /></>,
  swap: <><path d="M4 7h16m-4-4 4 4-4 4M20 17H4m4-4-4 4 4 4" /></>,
  upload: <><path d="M12 16V3m-5 5 5-5 5 5M4 15v5a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5" /></>,
}

export function Icon({ name, size = 20, className = '' }: { name: IconName; size?: number; className?: string }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={className}>{iconPaths[name]}</svg>
}

export function Spinner({ label = 'Loading' }: { label?: string }) {
  return <span className="spinner" role="status"><span className="sr-only">{label}</span></span>
}

export function ErrorNotice({ message, onRetry }: { message: string; onRetry?: () => void }) {
  if (!message) return null
  return <div className="notice notice-error" role="alert"><Icon name="info" /><div>{message}</div>{onRetry && <button className="text-button" onClick={onRetry} type="button">Try again</button>}</div>
}

export function Modal({ title, children, onClose, busy = false, className = '' }: {
  title: string
  children: ReactNode
  onClose: () => void
  busy?: boolean
  className?: string
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const titleId = useId()
  useEffect(() => {
    const element = dialog.current
    element?.showModal()
    return () => element?.close()
  }, [])
  return (
    <dialog ref={dialog} className={`modal ${className}`} aria-labelledby={titleId} onCancel={(event) => {
      event.preventDefault()
      if (!busy) onClose()
    }}>
      <div className="modal-heading">
        <h2 id={titleId}>{title}</h2>
        <button type="button" className="icon-button" aria-label="Close dialog" onClick={onClose} disabled={busy}><Icon name="close" /></button>
      </div>
      {children}
    </dialog>
  )
}

export function LanguageToggle({ value, onChange, label = 'Source language', disabled = false }: {
  value: Language
  onChange: (language: Language) => void
  label?: string
  disabled?: boolean
}) {
  return <div className="language-toggle" role="group" aria-label={label}>
    <button type="button" aria-pressed={value === 'fr'} onClick={() => onChange('fr')} disabled={disabled}>French <span>FR</span></button>
    <button type="button" aria-pressed={value === 'en'} onClick={() => onChange('en')} disabled={disabled}>English <span>EN</span></button>
  </div>
}

export function TranslationDirection({ source, target, onChange, disabled = false }: {
  source: TranslationLanguage
  target: TranslationLanguage
  onChange: (source: TranslationLanguage, target: TranslationLanguage) => void
  disabled?: boolean
}) {
  return <div className="translation-direction" role="group" aria-label="Translation direction">
    <label className="direction-field"><span>From</span><select value={source} disabled={disabled} onChange={(event) => onChange(event.target.value as TranslationLanguage, target)}>
      {translationLanguages.map((language) => <option value={language} key={language} disabled={language === target}>{languageLabels[language]}</option>)}
    </select></label>
    <button type="button" className="icon-button swap-languages" disabled={disabled} onClick={() => onChange(target, source)} aria-label="Swap source and target languages" title="Swap languages"><Icon name="swap" size={20} /></button>
    <label className="direction-field"><span>To</span><select value={target} disabled={disabled} onChange={(event) => onChange(source, event.target.value as TranslationLanguage)}>
      {translationLanguages.map((language) => <option value={language} key={language} disabled={language === source}>{languageLabels[language]}</option>)}
    </select></label>
  </div>
}

export function OriginBadge({ origin, exact = false }: { origin?: AnswerOrigin; exact?: boolean }) {
  return <span className={`origin-badge ${origin === 'dataset' ? 'origin-local' : 'origin-ai'}`}>
    <Icon name={origin === 'dataset' ? 'collection' : 'sparkles'} size={14} />
    {origin === 'dataset' ? exact ? 'Exact approved match · local' : 'Local dataset lookup' : origin === 'ai_with_dataset' ? 'AI suggestion · with dataset matches' : 'AI suggestion · no dataset evidence'}
  </span>
}

export function EvidencePanel({ evidence, origin, compact = false }: {
  evidence: DatasetEvidence[]
  origin?: AnswerOrigin
  compact?: boolean
}) {
  return <details className={`evidence-panel ${compact ? 'evidence-compact' : ''}`} open={compact ? undefined : true}>
    <summary><Icon name="collection" size={17} /><span>Approved dataset matches <strong>({evidence.length})</strong></span><Icon name="chevron" size={15} /></summary>
    <div className="evidence-content">
      <p className="helper-text">{origin === 'dataset'
        ? 'These are the approved local records returned by this lookup. Approval records a human review, not universal correctness.'
        : 'These are retrieved records, not a verification of the entire AI answer. A phrase or token match does not establish the meaning of a whole sentence.'}</p>
      {evidence.length ? <div className="evidence-list">{evidence.map((entry, index) => <article className="evidence-record" key={`${entry.id}-${index}`}>
        <div className="evidence-byline"><code>ID: {entry.id}</code><span>{entry.match_type} match</span></div>
        <dl className="evidence-comparison">
          <div><dt>{languageLabels[entry.language] ?? entry.language}</dt><dd>{entry.text}</dd></div>
          <div><dt>French · FR</dt><dd lang="fr">{entry.french_gloss || 'No French gloss recorded'}</dd></div>
          <div><dt>English · EN</dt><dd lang="en">{entry.english_gloss || 'No English gloss recorded'}</dd></div>
        </dl>
      </article>)}</div> : <p className="evidence-empty">No approved matches were returned. The local collection does not cover every word or expression.</p>}
    </div>
  </details>
}

export function DictationButton({ voice, language, disabled = false, onStart }: { voice: Dictation; language: Language; disabled?: boolean; onStart?: () => void }) {
  return <button type="button" className={`voice-button ${voice.listening ? 'is-listening' : ''}`}
    disabled={disabled || !voice.supported}
    title={!voice.supported ? 'Voice input is not supported in this browser' : undefined}
    aria-label={voice.listening ? 'Stop dictation' : `Start ${language === 'fr' ? 'French' : 'English'} dictation`}
    aria-pressed={voice.listening} onClick={() => { if (!voice.listening) onStart?.(); voice.toggle() }}>
    <Icon name={voice.listening ? 'stop' : 'mic'} size={18} />
    <span>{voice.listening ? 'Stop dictation' : 'Use your voice'}</span>
  </button>
}

export function DictationStatus({ voice }: { voice: Dictation }) {
  return <>
    {voice.listening && <p className="listening-status" role="status"><span className="recording-dot" />{voice.interim || 'Listening… speak now. Stop dictation before submitting.'}</p>}
    <ErrorNotice message={voice.error} />
    {!voice.supported && <p className="helper-text voice-unsupported"><Icon name="info" size={14} />Voice input isn’t available in this browser. You can still type.</p>}
  </>
}

export function ReadButton({ speech, id, text, language, compact = false, disabled = false }: {
  speech: ReadAloud; id: string; text: string; language: Language; compact?: boolean; disabled?: boolean
}) {
  const active = speech.activeId === id
  return <button type="button" className={compact ? 'icon-button' : 'action-button'} disabled={!speech.supported || disabled}
    title={!speech.supported ? 'Read-aloud is not supported in this browser' : active ? 'Stop reading' : 'Read aloud with a browser voice'}
    aria-label={active ? 'Stop reading' : 'Read aloud with a browser voice'}
    onClick={() => active ? speech.stop() : speech.speak(id, text, language)}>
    <Icon name={active ? 'stop' : 'volume'} size={18} />{!compact && (active ? 'Stop reading' : 'Read aloud')}
  </button>
}

export function CopyButton({ text, compact = false }: { text: string; compact?: boolean }) {
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState('')
  const copyVersion = useRef(0)
  useEffect(() => {
    setCopied(false)
    setError('')
    copyVersion.current += 1
    return () => { copyVersion.current += 1 }
  }, [text])
  useEffect(() => {
    if (!copied) return
    const timer = window.setTimeout(() => setCopied(false), 2400)
    return () => window.clearTimeout(timer)
  }, [copied])
  const copy = async () => {
    const version = ++copyVersion.current
    try {
      if (!navigator.clipboard) throw new Error('Unavailable')
      await navigator.clipboard.writeText(text)
      if (version !== copyVersion.current) return
      setCopied(true)
      setError('')
    } catch {
      if (version === copyVersion.current) setError('Select the text and copy manually; clipboard access is unavailable.')
    }
  }
  return <span className="copy-control">
    <button type="button" className={compact ? 'icon-button' : 'action-button'} onClick={() => void copy()} aria-label={copied ? 'Copied' : 'Copy text'} title={copied ? 'Copied' : 'Copy text'}>
      <Icon name={copied ? 'check' : 'copy'} size={18} />{!compact && (copied ? 'Copied!' : 'Copy')}
    </button>
    <span className="sr-only" role="status">{copied ? 'Text copied to clipboard.' : ''}</span>
    {error && <span className="copy-error" role="alert">{error}</span>}
  </span>
}

export function TokenAnalysis({ analysis }: { analysis: Analysis }) {
  return <div className="token-analysis">
    {analysis.tokens.length ? <div className="tokens">{analysis.tokens.map((token, index) => (
      <span className="token" key={`${index}-${token.text}`}><strong>{token.text}</strong><span>{token.category}</span></span>
    ))}</div> : <p className="helper-text">No tokens were found in this text.</p>}
    {analysis.code_mixed_spans.length > 0 && <div className="analysis-row"><strong>Code-mixed spans</strong><span>{analysis.code_mixed_spans.join(' · ')}</span></div>}
    {analysis.verb_phrases.length > 0 && <div className="analysis-row"><strong>Verb phrases</strong><span>{analysis.verb_phrases.join(' · ')}</span></div>}
    <p className="helper-text">Local, rule-based analysis. Labels are clues, not a complete linguistic interpretation.</p>
  </div>
}
