import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import { Assistant } from './Assistant'
import { Collection } from './Collection'
import { Coursework } from './Coursework'
import { Imports } from './Imports'
import { ErrorNotice, Icon, Modal, Spinner } from './components'
import type { IconName } from './components'
import { Translator } from './Translator'
import type { Health, IncomingText, Page } from './types'
import { useRequest } from './useRequest'
import { useReadAloud } from './voice'

const navigation: { page: Page; label: string; icon: IconName; number: string }[] = [
  { page: 'translator', label: 'Translator', icon: 'translate', number: '01' },
  { page: 'assistant', label: 'Learning assistant', icon: 'sparkles', number: '02' },
  { page: 'collection', label: 'Collection', icon: 'collection', number: '03' },
  { page: 'imports', label: 'Import & learn', icon: 'upload', number: '04' },
  { page: 'coursework', label: 'Compiler lab', icon: 'code', number: '05' },
]

function currentPage(): Page {
  const hash = window.location.hash.slice(1)
  return hash === 'assistant' || hash === 'collection' || hash === 'imports' || hash === 'coursework' ? hash : 'translator'
}

function PrivacyDialog({ onClose }: { onClose: () => void }) {
  return <Modal title="Your words. Your choice." onClose={onClose} className="privacy-modal">
    <p className="modal-description">Here’s what stays local, what leaves your device, and when.</p>
    <div className="privacy-sections">
      <section><span className="privacy-section-icon"><Icon name="collection" size={21} /></span><div><h3>Local storage, selected evidence</h3><p>Expressions live on your backend’s local disk. Browsing, searching, saving, deleting, and lexer analysis do not send records to Gemini. Exact approved translations also run locally, without an AI key. Unreviewed records are excluded from trusted matches; legacy records are not assumed approved.</p><p>For an explicitly submitted AI request with dataset use enabled, selected approved expression text and French/English glosses may be shared. Contributor names, source locations, notes, other record metadata, and the full corpus are excluded from retrieved evidence. Turn dataset use off to exclude those matches.</p></div></section>
      <section><span className="privacy-section-icon"><Icon name="sparkles" size={21} /></span><div><h3>AI suggestions, not automatic approval</h3><p>When there is no exact approved translation and AI fallback is enabled, Translate sends your text, direction, explanation language, tone, and any selected matches to Gemini. Send in the learning assistant shares your message, direction, language, up to six recent successful exchanges, and enabled dataset matches. Retrieved evidence does not verify every generated word.</p><p>AI answers and import suggestions are not saved automatically. Review language, wording, and meanings yourself before approving an entry. Never invent fieldwork or provenance to fill a gap.</p></div></section>
      <section><span className="privacy-section-icon"><Icon name="upload" size={21} /></span><div><h3>Preview imports before using them</h3><p>TXT, Markdown, CSV, JSON, DOCX, and text-based PDF previews are processed locally. Images, audio, video, and scanned PDFs require the cloud consent checkbox and an explicit Preview action before content is sent to Gemini for transcription. Limits are 12 MB per file, 40 PDF pages, and 40,000 extracted characters.</p><p>The app does not retain raw import files. Preview text is not automatically saved, translated, or submitted again. Choosing Translate or Ask AI only fills a draft; generating AI collection suggestions is a separate explicit request. Review any transcription and suggested records before saving. Provider-side retention is outside this app’s control. Remove sensitive information from any content you explicitly submit.</p></div></section>
      <section><span className="privacy-section-icon"><Icon name="code" size={21} /></span><div><h3>Your Compiler lab is still here</h3><p>Compiler lab AI explanations send only the grammar, manual test text, question, language, and locally recomputed results. Group profiles and explicitly uploaded coursework screenshots stay on the local backend. They are separate from import previews.</p><p>Drafts and chat stay in this browser tab’s memory and are lost on reload. Clearing a conversation removes local history, not records a service provider may retain.</p></div></section>
      <section><span className="privacy-section-icon"><Icon name="mic" size={21} /></span><div><h3>The microphone is always opt-in</h3><p>Dictation starts only when you press “Use your voice.” Your browser may send audio to its speech-recognition provider. Francanglais uses a French recognizer and Cameroon Pidgin uses an English recognizer as approximations. Stop recording, review the text and spellings, then explicitly press Translate or Send.</p></div></section>
      <section><span className="privacy-section-icon"><Icon name="volume" size={21} /></span><div><h3>A browser voice, not a native voice</h3><p>Read-aloud uses French or English browser speech synthesis—not a guaranteed native Francanglais or Cameroon Pidgin voice. Pronunciation may be imperfect, and some voices use an online service. Stop playback at any time; automatic reading of assistant replies is off by default.</p></div></section>
      <section><span className="privacy-section-icon"><Icon name="shield" size={21} /></span><div><h3>Your API key belongs on the backend</h3><p>Set <code>GEMINI_API_KEY</code> in <code>backend\.env</code> and restart the backend. Never enter a key into this interface or add one to frontend code. AI wording may need a human check, especially for cultural nuance.</p></div></section>
    </div>
    <div className="modal-footer"><button type="button" className="button button-primary" onClick={onClose}>Got it<Icon name="check" size={17} /></button></div>
  </Modal>
}

export default function App() {
  const [page, setPage] = useState<Page>(currentPage)
  const [privacyOpen, setPrivacyOpen] = useState(false)
  const [health, setHealth] = useState<Health | null>(null)
  const [translationDraft, setTranslationDraft] = useState<IncomingText>()
  const [assistantDraft, setAssistantDraft] = useState<IncomingText>()
  const nextHandoffId = useRef(1)
  const { pending: checkingHealth, error: healthError, run: checkHealth } = useRequest()
  const speech = useReadAloud()
  const { stop } = speech
  const main = useRef<HTMLElement>(null)
  const previousPage = useRef(page)

  useEffect(() => {
    const handleHash = () => setPage(currentPage())
    window.addEventListener('hashchange', handleHash)
    return () => window.removeEventListener('hashchange', handleHash)
  }, [])

  useEffect(() => {
    void checkHealth((signal) => api<Health>('/health', { signal }), setHealth)
  }, [checkHealth])

  useEffect(() => {
    document.title = `${navigation.find((item) => item.page === page)?.label ?? 'Translator'} — Mboa language learning`
    if (previousPage.current !== page) {
      stop()
      main.current?.focus({ preventScroll: true })
      window.scrollTo({ top: 0, behavior: 'instant' })
      previousPage.current = page
    }
  }, [page, stop])

  const aiAvailable = Boolean(health?.ai_configured && !healthError)
  const statusText = checkingHealth ? 'Checking connection' : healthError ? 'Backend offline' : health?.ai_configured ? 'Gemini configured' : 'Local tools ready · AI off'
  const pageLabel = navigation.find((item) => item.page === page)?.label ?? 'Translator'

  return <div className="app-shell">
    <a className="skip-link" href="#main-content" onClick={(event) => { event.preventDefault(); main.current?.focus() }}>Skip to content</a>
    <aside className="sidebar" aria-label="Workspace navigation">
      <a className="brand" href="#translator" aria-label="Mboa home, translator">
        <span className="brand-mark" aria-hidden="true"><svg width="29" height="28" viewBox="0 0 32 30" fill="none"><path d="M3 26V5h6l7 10 7-10h6v21h-7V16l-6 9-6-9v10H3Z" fill="currentColor" /><circle cx="28" cy="3" r="2.5" fill="#edb975" /></svg></span>
        <span className="brand-word">mboa<span className="brand-period">.</span></span>
      </a>
      <p className="brand-tagline">CAMEROON FRANCANGLAIS<br />& CAMEROON PIDGIN.</p>
      <span className="sidebar-section-label">YOUR WORKSPACE</span>
      <nav className="main-nav" aria-label="Main navigation">
        {navigation.map((item) => <a key={item.page} href={`#${item.page}`} className={`nav-link ${page === item.page ? 'is-active' : ''}`} aria-current={page === item.page ? 'page' : undefined}>
          <Icon name={item.icon} size={21} /><span>{item.label}</span><span className="nav-number" aria-hidden="true">{item.number}</span>
        </a>)}
      </nav>
      <div className="sidebar-bottom">
        <div className="sidebar-note"><span className="sidebar-note-star" aria-hidden="true">✳</span><span className="small-caps">THE MBOA MINDSET</span><p>On est<br /><em>ensemble.</em></p><span>Different words.<br />Same connection.</span><div className="cameroon-colors" aria-hidden="true"><i /><i /><i /></div></div>
        <button type="button" className="sidebar-privacy" onClick={() => setPrivacyOpen(true)}><Icon name="shield" size={17} />Privacy & voice<Icon name="chevron" size={13} /></button>
        <span className="sidebar-version">Learn · Compare · Collect · Review</span>
      </div>
    </aside>

    <div className="main-shell">
      <header className="topbar">
        <div className="breadcrumb"><span>Workspace</span><span className="breadcrumb-slash">/</span><strong>{pageLabel}</strong></div>
        <div className="topbar-actions">
          <div className={`connection-status ${aiAvailable ? 'is-connected' : ''}`} title={health?.model ? `Backend AI model: ${health.model}` : 'Local backend connection'}>
            {checkingHealth ? <Spinner label="Checking backend connection" /> : <span className="status-dot" />}<span>{statusText}</span>
          </div>
          <button type="button" className="icon-button" aria-label="Check backend connection" title="Check connection" disabled={checkingHealth} onClick={() => void checkHealth((signal) => api<Health>('/health', { signal }), setHealth)}><Icon name="refresh" size={16} /></button>
          <button type="button" className="mobile-privacy icon-button" aria-label="Privacy and voice information" onClick={() => setPrivacyOpen(true)}><Icon name="shield" size={18} /></button>
        </div>
      </header>
      <main id="main-content" className="main-content" ref={main} tabIndex={-1}>
        {healthError && <div className="connection-banner"><ErrorNotice message={healthError} onRetry={() => void checkHealth((signal) => api<Health>('/health', { signal }), setHealth)} /><p>AI requests are paused until the connection is restored. Start your local backend and check the connection again.</p></div>}
        {!healthError && health && !health.ai_configured && <div className="configuration-banner" role="status"><span className="configuration-icon"><Icon name="collection" size={20} /></span><div><strong>Dataset-first learning is ready without AI.</strong><p>Exact approved translations, collection review, local document previews, and Compiler lab work without an AI key. To enable AI suggestions and consented media transcription, set <code>GEMINI_API_KEY</code> in <code>backend\.env</code>, restart the backend, then check the connection.</p></div></div>}
        {speech.error && <ErrorNotice message={speech.error} />}
        {speech.activeId && <div className="playback-banner" role="status"><Icon name="volume" size={18} /><span>Reading with a browser voice</span><button type="button" className="text-button" onClick={speech.stop}><Icon name="stop" size={14} />Stop reading</button></div>}
        <div hidden={page !== 'translator'}><Translator active={page === 'translator'} aiAvailable={aiAvailable} speech={speech} incomingText={translationDraft} onOpenAssistant={() => { window.location.hash = 'assistant' }} onOpenCollection={() => { window.location.hash = 'collection' }} onOpenImports={() => { window.location.hash = 'imports' }} /></div>
        <div hidden={page !== 'assistant'}><Assistant active={page === 'assistant'} aiAvailable={aiAvailable} speech={speech} incomingText={assistantDraft} /></div>
        <div hidden={page !== 'collection'}><Collection active={page === 'collection'} /></div>
        <div hidden={page !== 'imports'}><Imports active={page === 'imports'} aiAvailable={aiAvailable} onUseText={(text) => {
          setTranslationDraft({ id: nextHandoffId.current++, text })
          window.location.hash = 'translator'
        }} onAskAI={(text) => {
          setAssistantDraft({ id: nextHandoffId.current++, text })
          window.location.hash = 'assistant'
        }} onOpenCollection={() => { window.location.hash = 'collection' }} /></div>
        <div hidden={page !== 'coursework'}><Coursework active={page === 'coursework'} aiAvailable={aiAvailable} /></div>
        <footer className="page-footer"><span>Many languages. <strong>One conversation.</strong></span><button type="button" onClick={() => setPrivacyOpen(true)}>Made with care. Used with context.<Icon name="arrow" size={14} /></button></footer>
      </main>
    </div>
    {privacyOpen && <PrivacyDialog onClose={() => setPrivacyOpen(false)} />}
  </div>
}
