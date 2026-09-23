import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import { Collection } from './Collection'
import { FrancAnalyzer } from './FrancAnalyzer'
import { Dictionary } from './Dictionary'
import { Examples } from './Examples'
import { ErrorNotice, Icon, Modal, Spinner } from './components'
import type { IconName } from './components'
import type { Health, IncomingText, Page } from './types'
import { useRequest } from './useRequest'
import { useReadAloud } from './voice'
import type { Account } from './accountTypes'

const navigation: { page: Page; label: string; icon: IconName }[] = [
  { page: 'compiler', label: 'Franc Analyzer', icon: 'code' },
  { page: 'analysis', label: 'Analysis', icon: 'chart' },
  { page: 'collection', label: 'Collection', icon: 'collection' },
  { page: 'dictionary', label: 'Dictionary', icon: 'search' },
  { page: 'examples', label: 'Synthetic examples', icon: 'info' },
]

function currentPage(): Page {
  const hash = window.location.hash.slice(1)
  return navigation.find((item) => item.page === hash)?.page ?? 'compiler'
}

function PrivacyDialog({ onClose }: { onClose: () => void }) {
  return <Modal title="Data & privacy" onClose={onClose} className="privacy-modal">
    <p className="modal-description">There is one shared workspace. All signed-in users can view its collection, recorded tests, grammar and recordings. Only the creator can edit or delete their records; saved tests are immutable.</p>
    <div className="privacy-sections">
      <section><span className="privacy-section-icon"><Icon name="collection" size={21} /></span><div><h3>Collection and storage</h3><p>Analyze records each completed test, its text, grammar and results in the shared workspace, separately from Collection. Analysis statistics include every user’s retained tests, including repeats, and remain after refresh or sign-out. A stopped request may still finish and become visible to all signed-in users; refresh saved tests to check.</p><p>Unsubmitted drafts stay in this tab and are lost on reload, account switch or sign-out. Everyone can edit and test a local grammar draft. Only the grammar’s creator can save shared changes; the first save claims unowned grammar. Approval records the creator’s review, not verified fieldwork.</p><p>Exports can include source context and contributor details. Share only with permission. Existing backups and legacy records remain on the server; removing their screens does not delete stored data. Contact the server operator for recovery.</p></div></section>
      <section><span className="privacy-section-icon"><Icon name="code" size={21} /></span><div><h3>Rule-based computation and audio</h3><p>The lexer and parser run on this server without AI. ACCEPT / REJECT describes grammar coverage, not whether the speaker is correct. The starter grammar and synthetic examples are not fieldwork.</p><p>Transcribe recordings manually and record only with permission. There is no OCR or automatic transcription. Optional read-aloud uses installed local browser voices and may mispronounce words.</p></div></section>
      <section><span className="privacy-section-icon"><Icon name="shield" size={21} /></span><div><h3>Account safety</h3><p>Your email, password, profile and session remain account-specific; credentials are not shared. The user count is registered accounts, not people currently online, and no email directory is exposed. Hosted access requires HTTPS. Password and Google sign-in remain available when configured; password recovery is on the sign-in screen. Sign out on shared devices and keep verification links private.</p></div></section>
    </div>
    <div className="modal-footer"><button type="button" className="button button-primary" onClick={onClose}>Done<Icon name="check" size={17} /></button></div>
  </Modal>
}

export default function App({ account, registeredUsers = null, onSignOut }: {
  account?: Account
  registeredUsers?: number | null
  onSignOut?: () => void
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
    document.title = `${navigation.find((item) => item.page === page)?.label ?? 'Franc Analyzer'} — Mboa Compiler`
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
  const pageLabel = navigation.find((item) => item.page === page)?.label ?? 'Franc Analyzer'

  function openCompiler(text: string, kind: IncomingText['kind']) {
    handoffFocusPending.current = true
    setCompilerDraft({ id: nextHandoffId.current++, text, kind })
    window.location.hash = 'compiler'
  }

  return <div className="app-shell">
    <a className="skip-link" href="#main-content" onClick={(event) => { event.preventDefault(); main.current?.focus() }}>Skip to content</a>
    <aside className="sidebar" aria-label="Workspace navigation">
      <a className="brand" href="#compiler" aria-label="Mboa home, Franc Analyzer">
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
        <div className="workspace-scope"><span className="scope-indicator" /><div><strong>Shared workspace</strong><span>Everyone can view · Creator-only edits</span></div></div>
        <button type="button" className="sidebar-privacy" onClick={() => setPrivacyOpen(true)}><Icon name="shield" size={17} />Privacy information<Icon name="chevron" size={13} /></button>
        <span className="sidebar-version">French · English · Francanglais · Pidgin</span>
      </div>
    </aside>

    <div className="main-shell">
      <header className="topbar">
        <div className="breadcrumb"><span>Workspace</span><span className="breadcrumb-slash">/</span><strong>{pageLabel}</strong></div>
        {account && <div className="account-controls"><span className="account-email">{account.email}</span>
          <span className="shared-workspace-summary">Shared workspace <span aria-label="Registered users">{registeredUsers === null ? 'Registered users: unavailable' : `${registeredUsers.toLocaleString()} registered ${registeredUsers === 1 ? 'user' : 'users'}`}</span></span>
          <button className="text-button" type="button" onClick={onSignOut}>Sign out</button>
        </div>}
        <div className="topbar-actions">
          <div className={`connection-status ${connected ? 'is-connected' : ''}`} title="Application server connection">
            {checkingHealth ? <Spinner label="Checking backend connection" /> : <span className="status-dot" />}<span>{statusText}</span>
          </div>
          <button type="button" className="icon-button" aria-label="Check backend connection" title="Check connection" disabled={checkingHealth} onClick={() => void checkHealth((signal) => api<Health>('/health', { signal }), setHealth)}><Icon name="refresh" size={16} /></button>
          <button type="button" className="mobile-privacy icon-button" aria-label="Privacy information" onClick={() => setPrivacyOpen(true)}><Icon name="shield" size={18} /></button>
        </div>
      </header>
      <main id="main-content" className="main-content" ref={main} tabIndex={-1}>
        {healthError && <div className="connection-banner"><ErrorNotice message={healthError} onRetry={() => void checkHealth((signal) => api<Health>('/health', { signal }), setHealth)} /><p>Server computation and saving may be unavailable. Your current editor drafts are kept; check the connection before retrying.</p></div>}
        {speech.error && <ErrorNotice message={speech.error} />}
        {speech.activeId && <div className="playback-banner" role="status"><Icon name="volume" size={18} /><span>Reading with a browser voice</span><button type="button" className="text-button" onClick={speech.stop}><Icon name="stop" size={14} />Stop reading</button></div>}
        <div hidden={page !== 'compiler' && page !== 'analysis'}><FrancAnalyzer active={page === 'compiler' || page === 'analysis'} showAnalysis={page === 'analysis'} incomingText={compilerDraft} onUseText={(text) => openCompiler(text, undefined)} /></div>
        <div hidden={page !== 'collection'}><Collection active={page === 'collection'} onUseText={(text) => openCompiler(text, 'collection')} /></div>
        <div hidden={page !== 'dictionary'}><Dictionary active={page === 'dictionary'} speech={speech} onUseText={(text) => openCompiler(text, 'dictionary')} /></div>
        <div hidden={page !== 'examples'}><Examples active={page === 'examples'} speech={speech} onUseText={(text) => openCompiler(text, 'examples')} /></div>
        <footer className="page-footer"><span>Mboa · Compiler Workspace</span><button type="button" onClick={() => setPrivacyOpen(true)}>Data & privacy<Icon name="arrow" size={14} /></button></footer>
      </main>
    </div>
    {privacyOpen && <PrivacyDialog onClose={() => setPrivacyOpen(false)} />}
  </div>
}
