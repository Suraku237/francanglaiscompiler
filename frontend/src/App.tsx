import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import { Collection } from './Collection'
import { Coursework } from './Coursework'
import { Dictionary } from './Dictionary'
import { Examples } from './Examples'
import { Imports } from './Imports'
import { ErrorNotice, Icon, Modal, Spinner } from './components'
import type { IconName } from './components'
import type { Health, IncomingText, Page } from './types'
import { useRequest } from './useRequest'
import { useReadAloud } from './voice'
import type { Account, Project, Session } from './accountTypes'
import { SavedWork } from './SavedWork'
import { WorkspaceSettings } from './WorkspaceSettings'

const navigation: { page: Page; label: string; icon: IconName }[] = [
  { page: 'compiler', label: 'Compiler lab', icon: 'code' },
  { page: 'collection', label: 'Collection', icon: 'collection' },
  { page: 'dictionary', label: 'Dictionary', icon: 'search' },
  { page: 'examples', label: 'Synthetic examples', icon: 'info' },
  { page: 'imports', label: 'Document import', icon: 'upload' },
  { page: 'history', label: 'History', icon: 'collection' },
  { page: 'settings', label: 'Workspace settings', icon: 'shield' },
]

function currentPage(): Page {
  const hash = window.location.hash.slice(1)
  return navigation.find((item) => item.page === hash)?.page ?? 'compiler'
}

function PrivacyDialog({ onClose }: { onClose: () => void }) {
  return <Modal title="Workspace settings & privacy" onClose={onClose} className="privacy-modal">
    <p className="modal-description">Your private compiler workspace. Account access is required; each project has its own collection, grammar, report, screenshots, recordings and saved history.</p>
    <div className="privacy-sections">
      <section><span className="privacy-section-icon"><Icon name="collection" size={21} /></span><div><h3>Collection and storage</h3><p>Saved statements, words, provenance and recordings are stored privately on this application server. Approval records your review, not verified authenticity. Importing or recording never certifies fieldwork.</p><p>Unsaved drafts stay in this browser tab and are lost on reload, project switch or sign-out. Save your project and collection explicitly. Legacy history remains readable and exportable. Backups include your projects and may retain deleted records. The server operator controls the underlying infrastructure; share exports only with authorized recipients.</p></div></section>
      <section><span className="privacy-section-icon"><Icon name="code" size={21} /></span><div><h3>Rule-based computation</h3><p>Lexing, grammar transformations, FIRST/FOLLOW sets, predictive tables and parsing run on this server without model or provider calls. ACCEPT and REJECT describe your grammar’s coverage, not the correctness of a speaker’s language.</p><p>The starter grammar and synthetic examples are illustrative references, not your collected corpus. Record genuine sources and uncertainty yourself. No missing research data is generated.</p></div></section>
      <section><span className="privacy-section-icon"><Icon name="upload" size={21} /></span><div><h3>Local documents and raw audio</h3><p>Preview uploads one text document for extraction on this server. TXT, Markdown, CSV, JSON, DOCX and text-layer PDFs are supported. Scanned pages require a manual transcript; there is no OCR or automatic transcription. Source uploads are not retained as attachments.</p><p>Recordings stay in this tab until you explicitly save an attachment to your collection. Transcribe by hand and record only with permission. Optional read-aloud uses installed local browser voices; pronunciation is approximate and it never transcribes audio.</p></div></section>
      <section><span className="privacy-section-icon"><Icon name="shield" size={21} /></span><div><h3>Account safety</h3><p>Hosted access requires HTTPS. Password, Google sign-in and account recovery remain available when configured. Sign out on shared devices, keep verification links private and never put credentials in exported files.</p></div></section>
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
  const [compilerDraft, setCompilerDraft] = useState<IncomingText>()
  const nextHandoffId = useRef(1)
  const handoffFocusPending = useRef(false)
  const { pending: checkingHealth, error: healthError, run: checkHealth } = useRequest()
  const speech = useReadAloud()
  const { stop } = speech
  const main = useRef<HTMLElement>(null)
  const previousPage = useRef(page)

  useEffect(() => {
    const handleHash = () => {
      const next = currentPage()
      const hash = window.location.hash.slice(1)
      if (!navigation.some((item) => item.page === hash)) {
        window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}#compiler`)
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
    document.title = `${navigation.find((item) => item.page === page)?.label ?? 'Compiler lab'} — Mboa Compiler`
    if (previousPage.current !== page) {
      stop()
      if (page === 'compiler' && handoffFocusPending.current) {
        handoffFocusPending.current = false
      } else {
        main.current?.focus({ preventScroll: true })
        window.scrollTo({ top: 0, behavior: 'instant' })
      }
      previousPage.current = page
    }
  }, [page, stop])

  const connected = Boolean(health?.status === 'ok' && !healthError)
  const statusText = checkingHealth ? 'Connecting' : healthError ? 'Backend offline' : connected ? 'Compiler connected' : 'Not connected'
  const pageLabel = navigation.find((item) => item.page === page)?.label ?? 'Compiler lab'

  function openCompiler(text: string, kind: IncomingText['kind']) {
    handoffFocusPending.current = true
    setCompilerDraft({ id: nextHandoffId.current++, text, kind })
    window.location.hash = 'compiler'
  }

  return <div className="app-shell">
    <a className="skip-link" href="#main-content" onClick={(event) => { event.preventDefault(); main.current?.focus() }}>Skip to content</a>
    <aside className="sidebar" aria-label="Workspace navigation">
      <a className="brand" href="#compiler" aria-label="Mboa home, compiler lab">
        <span className="brand-mark" aria-hidden="true"><svg width="29" height="28" viewBox="0 0 32 30" fill="none"><path d="M3 26V5h6l7 10 7-10h6v21h-7V16l-6 9-6-9v10H3Z" fill="currentColor" /><circle cx="28" cy="3" r="2.5" fill="#edb975" /></svg></span>
        <span className="brand-word">Mboa</span>
      </a>
      <p className="brand-tagline">Compiler workspace</p>
      <span className="sidebar-section-label">WORKSPACE</span>
      <nav className="main-nav" aria-label="Main navigation">
        {navigation.map((item) => <a key={item.page} href={`#${item.page}`} className={`nav-link ${page === item.page ? 'is-active' : ''}`} aria-current={page === item.page ? 'page' : undefined}>
          <Icon name={item.icon} size={20} /><span>{item.label}</span>
        </a>)}
      </nav>
      <div className="sidebar-bottom">
        <div className="workspace-scope"><span className="scope-indicator" /><div><strong>Private workspace</strong><span>Your account · Your corpus</span></div></div>
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
          <div className={`connection-status ${connected ? 'is-connected' : ''}`} title="Application server connection">
            {checkingHealth ? <Spinner label="Checking backend connection" /> : <span className="status-dot" />}<span>{statusText}</span>
          </div>
          <button type="button" className="icon-button" aria-label="Check backend connection" title="Check connection" disabled={checkingHealth} onClick={() => void checkHealth((signal) => api<Health>('/health', { signal }), setHealth)}><Icon name="refresh" size={16} /></button>
          <button type="button" className="mobile-privacy icon-button" aria-label="Workspace settings and privacy" onClick={() => setPrivacyOpen(true)}><Icon name="shield" size={18} /></button>
        </div>
      </header>
      <main id="main-content" className="main-content" ref={main} tabIndex={-1}>
        {healthError && <div className="connection-banner"><ErrorNotice message={healthError} onRetry={() => void checkHealth((signal) => api<Health>('/health', { signal }), setHealth)} /><p>Server computation and saving may be unavailable. Your current editor drafts are kept; check the connection before retrying.</p></div>}
        {speech.error && <ErrorNotice message={speech.error} />}
        {speech.activeId && <div className="playback-banner" role="status"><Icon name="volume" size={18} /><span>Reading with a browser voice</span><button type="button" className="text-button" onClick={speech.stop}><Icon name="stop" size={14} />Stop reading</button></div>}
        <div hidden={page !== 'compiler'}><Coursework active={page === 'compiler'} incomingText={compilerDraft} /></div>
        <div hidden={page !== 'collection'}><Collection active={page === 'collection'} /></div>
        <div hidden={page !== 'dictionary'}><Dictionary active={page === 'dictionary'} speech={speech} onUseText={(text) => openCompiler(text, 'dictionary')} /></div>
        <div hidden={page !== 'examples'}><Examples active={page === 'examples'} speech={speech} onUseText={(text) => openCompiler(text, 'examples')} /></div>
        <div hidden={page !== 'imports'}><Imports active={page === 'imports'} onUseText={(text) => openCompiler(text, 'import')} onOpenCollection={() => { window.location.hash = 'collection' }} /></div>
        <div hidden={page !== 'history'}><SavedWork active={page === 'history'} onUseText={(text) => openCompiler(text, 'history')} /></div>
        <div hidden={page !== 'settings'}><WorkspaceSettings active={page === 'settings'} account={account} googleEnabled={googleEnabled} projects={projects} selectedProject={selectedProject} onProfileChanged={onProfileChanged} /></div>
        <footer className="page-footer"><span>Mboa · Compiler Workspace</span><button type="button" onClick={() => setPrivacyOpen(true)}>Data & privacy<Icon name="arrow" size={14} /></button></footer>
      </main>
    </div>
    {privacyOpen && <PrivacyDialog onClose={() => setPrivacyOpen(false)} />}
  </div>
}
