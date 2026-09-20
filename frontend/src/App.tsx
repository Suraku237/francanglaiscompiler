import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import { Assistant } from './Assistant'
import { Collection } from './Collection'
import { Dictionary } from './Dictionary'
import { Imports } from './Imports'
import { ErrorNotice, Icon, Modal, Spinner } from './components'
import type { IconName } from './components'
import { Translator } from './Translator'
import type { Health, IncomingText, Page } from './types'
import { useRequest } from './useRequest'
import { useReadAloud } from './voice'

const navigation: { page: Page; label: string; icon: IconName }[] = [
  { page: 'translator', label: 'Translate', icon: 'translate' },
  { page: 'assistant', label: 'Assistant', icon: 'sparkles' },
  { page: 'collection', label: 'Terminology', icon: 'collection' },
  { page: 'dictionary', label: 'Dictionary', icon: 'search' },
  { page: 'imports', label: 'Documents & audio', icon: 'upload' },
]

function currentPage(): Page {
  const hash = window.location.hash.slice(1)
  return hash === 'assistant' || hash === 'dictionary' || hash === 'collection' || hash === 'imports' ? hash : 'translator'
}

function PrivacyDialog({ onClose }: { onClose: () => void }) {
  return <Modal title="Workspace settings & privacy" onClose={onClose} className="privacy-modal">
    <p className="modal-description">A local language workspace with optional cloud assistance. This installation has no user accounts or role-based access; do not expose it as a public service.</p>
    <div className="privacy-sections">
      <section><span className="privacy-section-icon"><Icon name="collection" size={21} /></span><div><h3>Terminology and storage</h3><p>Saved terms, notes and attached recordings stay on your backend's disk. Search, editing, exports and exact local translations do not contact Gemini. Only explicitly approved terminology is used for approved-source matching. Approval records your review, not independent certification.</p><p>Translation drafts and conversation history remain in this browser tab and are lost on reload. Export terminology regularly and keep backups restricted to authorized people.</p></div></section>
      <section><span className="privacy-section-icon"><Icon name="sparkles" size={21} /></span><div><h3>Optional AI processing</h3><p>When enabled, an explicit translation or assistant request can send your text, selected terminology or dictionary matches, and recent conversation to Gemini. Stored contributor names, locations, private notes and full reference files are not included in retrieved matches. Personal information typed into your message is still part of that request.</p><p>AI output requires review before use. Dictionary citations identify references, not verified business terminology. New output is never saved or approved automatically. Provider retention policies apply.</p></div></section>
      <section><span className="privacy-section-icon"><Icon name="upload" size={21} /></span><div><h3>Documents and audio</h3><p>Text documents are extracted locally. Images, scanned PDFs and media need explicit cloud consent and a separate Preview action for transcription. Raw import files are temporary; recording alone never uploads audio. Saving an audio attachment stores it locally.</p><p>Browser dictation may use the browser vendor's speech service. French/English recognition and read-aloud are approximations for Francanglais and Cameroon Pidgin. Record only with permission and review transcripts and pronunciation.</p></div></section>
      <section><span className="privacy-section-icon"><Icon name="shield" size={21} /></span><div><h3>Connection configuration</h3><p>The backend must remain bound to localhost or a trusted private environment. Configure <code>GEMINI_API_KEY</code> on the backend and restart it to enable AI features. A configured key does not confirm provider access. Never place credentials in the frontend or exported files.</p></div></section>
    </div>
    <div className="modal-footer"><button type="button" className="button button-primary" onClick={onClose}>Done<Icon name="check" size={17} /></button></div>
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
    const handleHash = () => {
      const next = currentPage()
      const hash = window.location.hash.slice(1)
      if (hash && !navigation.some((item) => item.page === hash)) {
        window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}#translator`)
      }
      setPage(next)
    }
    handleHash()
    window.addEventListener('hashchange', handleHash)
    return () => window.removeEventListener('hashchange', handleHash)
  }, [])

  useEffect(() => {
    void checkHealth((signal) => api<Health>('/health', { signal }), setHealth)
  }, [checkHealth])

  useEffect(() => {
    document.title = `${navigation.find((item) => item.page === page)?.label ?? 'Translate'} — Mboa Workspace`
    if (previousPage.current !== page) {
      stop()
      main.current?.focus({ preventScroll: true })
      window.scrollTo({ top: 0, behavior: 'instant' })
      previousPage.current = page
    }
  }, [page, stop])

  const aiAvailable = Boolean(health?.ai_configured && !healthError)
  const statusText = checkingHealth ? 'Connecting' : healthError ? 'Backend offline' : health?.ai_configured ? 'AI configured' : 'Local mode'
  const pageLabel = navigation.find((item) => item.page === page)?.label ?? 'Translate'

  return <div className="app-shell">
    <a className="skip-link" href="#main-content" onClick={(event) => { event.preventDefault(); main.current?.focus() }}>Skip to content</a>
    <aside className="sidebar" aria-label="Workspace navigation">
      <a className="brand" href="#translator" aria-label="Mboa home, translator">
        <span className="brand-mark" aria-hidden="true"><svg width="29" height="28" viewBox="0 0 32 30" fill="none"><path d="M3 26V5h6l7 10 7-10h6v21h-7V16l-6 9-6-9v10H3Z" fill="currentColor" /><circle cx="28" cy="3" r="2.5" fill="#edb975" /></svg></span>
        <span className="brand-word">Mboa</span>
      </a>
      <p className="brand-tagline">Language workspace</p>
      <span className="sidebar-section-label">WORKSPACE</span>
      <nav className="main-nav" aria-label="Main navigation">
        {navigation.map((item) => <a key={item.page} href={`#${item.page}`} className={`nav-link ${page === item.page ? 'is-active' : ''}`} aria-current={page === item.page ? 'page' : undefined}>
          <Icon name={item.icon} size={20} /><span>{item.label}</span>
        </a>)}
      </nav>
      <div className="sidebar-bottom">
        <div className="workspace-scope"><span className="scope-indicator" /><div><strong>Local workspace</strong><span>Local storage · Optional AI</span></div></div>
        <button type="button" className="sidebar-privacy" onClick={() => setPrivacyOpen(true)}><Icon name="shield" size={17} />Settings & privacy<Icon name="chevron" size={13} /></button>
        <span className="sidebar-version">French · English · Francanglais · Pidgin</span>
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
          <button type="button" className="mobile-privacy icon-button" aria-label="Workspace settings and privacy" onClick={() => setPrivacyOpen(true)}><Icon name="shield" size={18} /></button>
        </div>
      </header>
      <main id="main-content" className="main-content" ref={main} tabIndex={-1}>
        {healthError && <div className="connection-banner"><ErrorNotice message={healthError} onRetry={() => void checkHealth((signal) => api<Health>('/health', { signal }), setHealth)} /><p>AI requests are paused until the connection is restored. Start your local backend and check the connection again.</p></div>}
        {!healthError && health && !health.ai_configured && <div className="configuration-banner" role="status"><span className="configuration-icon"><Icon name="info" size={18} /></span><div><strong>Local mode</strong><p>Terminology, dictionary lookup and text documents are available. AI translation, assistant replies and media transcription require configuration.</p></div><button className="text-button" type="button" onClick={() => setPrivacyOpen(true)}>Settings</button></div>}
        {speech.error && <ErrorNotice message={speech.error} />}
        {speech.activeId && <div className="playback-banner" role="status"><Icon name="volume" size={18} /><span>Reading with a browser voice</span><button type="button" className="text-button" onClick={speech.stop}><Icon name="stop" size={14} />Stop reading</button></div>}
        <div hidden={page !== 'translator'}><Translator active={page === 'translator'} aiAvailable={aiAvailable} speech={speech} incomingText={translationDraft} onOpenAssistant={() => { window.location.hash = 'assistant' }} onOpenCollection={() => { window.location.hash = 'collection' }} onOpenImports={() => { window.location.hash = 'imports' }} /></div>
        <div hidden={page !== 'assistant'}><Assistant active={page === 'assistant'} aiAvailable={aiAvailable} speech={speech} incomingText={assistantDraft} /></div>
        <div hidden={page !== 'collection'}><Collection active={page === 'collection'} /></div>
        <div hidden={page !== 'dictionary'}><Dictionary active={page === 'dictionary'} onTranslate={(text) => {
          setTranslationDraft({ id: nextHandoffId.current++, text, source: 'francanglais', target: 'en', kind: 'dictionary' })
          window.location.hash = 'translator'
        }} /></div>
        <div hidden={page !== 'imports'}><Imports active={page === 'imports'} aiAvailable={aiAvailable} onUseText={(text) => {
          setTranslationDraft({ id: nextHandoffId.current++, text })
          window.location.hash = 'translator'
        }} onAskAI={(text) => {
          setAssistantDraft({ id: nextHandoffId.current++, text })
          window.location.hash = 'assistant'
        }} onOpenCollection={() => { window.location.hash = 'collection' }} /></div>
        <footer className="page-footer"><span>Mboa · Language Workspace</span><button type="button" onClick={() => setPrivacyOpen(true)}>Data & privacy<Icon name="arrow" size={14} /></button></footer>
      </main>
    </div>
    {privacyOpen && <PrivacyDialog onClose={() => setPrivacyOpen(false)} />}
  </div>
}
