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
import type { Account, Project, Session } from './accountTypes'
import { SavedWork } from './SavedWork'
import { WorkspaceSettings } from './WorkspaceSettings'

const navigation: { page: Page; label: string; icon: IconName }[] = [
  { page: 'translator', label: 'Translate', icon: 'translate' },
  { page: 'assistant', label: 'Assistant', icon: 'sparkles' },
  { page: 'collection', label: 'Terminology', icon: 'collection' },
  { page: 'dictionary', label: 'Dictionary', icon: 'search' },
  { page: 'imports', label: 'Documents & audio', icon: 'upload' },
  { page: 'history', label: 'History', icon: 'collection' },
  { page: 'settings', label: 'Workspace settings', icon: 'shield' },
]

function currentPage(): Page {
  const hash = window.location.hash.slice(1)
  return hash === 'assistant' || hash === 'dictionary' || hash === 'collection' || hash === 'imports' || hash === 'history' || hash === 'settings' ? hash : 'translator'
}

function PrivacyDialog({ onClose }: { onClose: () => void }) {
  return <Modal title="Workspace settings & privacy" onClose={onClose} className="privacy-modal">
    <p className="modal-description">Your private language workspace with optional AI assistance. Account access is required; each account has separate projects, terminology, recordings and saved work.</p>
    <div className="privacy-sections">
      <section><span className="privacy-section-icon"><Icon name="collection" size={21} /></span><div><h3>Terminology and storage</h3><p>Saved terms, notes and recordings are stored privately on the application server. Search, editing, exports and exact terminology lookups do not contact Gemini. Approval records your review, not independent certification.</p><p>Unsaved drafts remain in this browser tab and are lost on reload. Save translation or conversation results explicitly to retain them in History. Backups include all of your projects and may retain deleted records. Restrict exported files to authorized recipients. The server operator controls the underlying infrastructure.</p></div></section>
      <section><span className="privacy-section-icon"><Icon name="sparkles" size={21} /></span><div><h3>Optional AI processing</h3><p>When enabled, an explicit translation or assistant request can send your text, selected terminology or dictionary matches, and recent conversation to Gemini. Stored contributor names, locations, private notes and full reference files are not included in retrieved matches. Personal information typed into your message is still part of that request.</p><p>AI output requires review before use. Dictionary citations identify references, not verified business terminology. New output is never saved or approved automatically. Provider retention policies apply.</p></div></section>
      <section><span className="privacy-section-icon"><Icon name="upload" size={21} /></span><div><h3>Documents and audio</h3><p>Uploaded text documents are extracted on this server without AI. Images, scanned PDFs and media need explicit provider consent and a separate Preview action for transcription. Raw import files are temporary; recording alone never uploads audio. Saving an attachment uploads it privately to your account.</p><p>Browser dictation may use the browser vendor's speech service. French/English recognition and read-aloud are approximations for Francanglais and Cameroon Pidgin. Record only with permission and review transcripts and pronunciation.</p></div></section>
      <section><span className="privacy-section-icon"><Icon name="shield" size={21} /></span><div><h3>Connection and account safety</h3><p>Hosted access requires HTTPS. Configure provider credentials only on the backend. A configured key does not confirm provider access. Sign out on shared devices, keep verification links private and never put credentials in exported files. AI allowances protect provider usage; exact dictionary lookups do not consume them.</p></div></section>
    </div>
    <div className="modal-footer"><button type="button" className="button button-primary" onClick={onClose}>Done<Icon name="check" size={17} /></button></div>
  </Modal>
}

export default function App({ account, googleEnabled, projects = [], selectedProject = 'default', onSelectProject, onSignOut, onProfileChanged }: {
  account?: Account
  googleEnabled?: boolean
  projects?: Project[]
  selectedProject?: string
  onSelectProject?: (id: string) => void
  onSignOut?: () => void
  onProfileChanged?: (session: Session) => void
}) {
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
  const statusText = checkingHealth ? 'Connecting' : healthError ? 'Backend offline' : health?.ai_configured ? 'AI configured' : 'AI unavailable'
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
        <div className="workspace-scope"><span className="scope-indicator" /><div><strong>Private workspace</strong><span>Your account · Optional AI</span></div></div>
        <button type="button" className="sidebar-privacy" onClick={() => setPrivacyOpen(true)}><Icon name="shield" size={17} />Settings & privacy<Icon name="chevron" size={13} /></button>
        <span className="sidebar-version">French · English · Francanglais · Pidgin</span>
      </div>
    </aside>

    <div className="main-shell">
      <header className="topbar">
        <div className="breadcrumb"><span>Workspace</span><span className="breadcrumb-slash">/</span><strong>{pageLabel}</strong></div>
        {account && <div className="account-controls"><span className="account-email">{account.email}</span>
          <label className="sr-only" htmlFor="active-project">Active project</label><select id="active-project" value={selectedProject} onChange={(event) => onSelectProject?.(event.target.value)}>
            {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
          </select><button className="text-button" type="button" onClick={onSignOut}>Sign out</button>
        </div>}
        <div className="topbar-actions">
          <div className={`connection-status ${aiAvailable ? 'is-connected' : ''}`} title={health?.model ? `Backend AI model: ${health.model}` : 'Application server connection'}>
            {checkingHealth ? <Spinner label="Checking backend connection" /> : <span className="status-dot" />}<span>{statusText}</span>
          </div>
          <button type="button" className="icon-button" aria-label="Check backend connection" title="Check connection" disabled={checkingHealth} onClick={() => void checkHealth((signal) => api<Health>('/health', { signal }), setHealth)}><Icon name="refresh" size={16} /></button>
          <button type="button" className="mobile-privacy icon-button" aria-label="Workspace settings and privacy" onClick={() => setPrivacyOpen(true)}><Icon name="shield" size={18} /></button>
        </div>
      </header>
      <main id="main-content" className="main-content" ref={main} tabIndex={-1}>
        {healthError && <div className="connection-banner"><ErrorNotice message={healthError} onRetry={() => void checkHealth((signal) => api<Health>('/health', { signal }), setHealth)} /><p>AI requests are paused until the connection is restored. Check your connection or contact the operator.</p></div>}
        {!healthError && health && !health.ai_configured && <div className="configuration-banner" role="status"><span className="configuration-icon"><Icon name="info" size={18} /></span><div><strong>Dictionary and terminology mode</strong><p>Terminology, dictionary lookup and text documents are available. AI translation, assistant replies and media transcription require configuration.</p></div><button className="text-button" type="button" onClick={() => setPrivacyOpen(true)}>Settings</button></div>}
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
        <div hidden={page !== 'history'}><SavedWork active={page === 'history'} onUseText={(text) => {
          setTranslationDraft({ id: nextHandoffId.current++, text })
          window.location.hash = 'translator'
        }} /></div>
        <div hidden={page !== 'settings'}><WorkspaceSettings active={page === 'settings'} account={account} googleEnabled={googleEnabled} projects={projects} selectedProject={selectedProject} onProfileChanged={onProfileChanged} /></div>
        <footer className="page-footer"><span>Mboa · Language Workspace</span><button type="button" onClick={() => setPrivacyOpen(true)}>Data & privacy<Icon name="arrow" size={14} /></button></footer>
      </main>
    </div>
    {privacyOpen && <PrivacyDialog onClose={() => setPrivacyOpen(false)} />}
  </div>
}
