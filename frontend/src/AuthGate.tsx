import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import App from './App'
import { Brand } from './Brand'
import { api, configureSession, isCancelled, messageOf } from './api'
import { ErrorNotice, Spinner } from './components'
import type { ProjectsResult, Session } from './accountTypes'
import { useRequest } from './useRequest'

function authRoute(): string {
  return window.location.hash.slice(1).split('?')[0] ?? ''
}

function announceSession(): void {
  try {
    localStorage.setItem('mboa-session-change', crypto.randomUUID())
  } catch {
    window.dispatchEvent(new Event('mboa:cross-tab-unavailable'))
  }
}

function AuthForm({ session, onSignedIn }: { session: Session; onSignedIn: (next: Session) => void }) {
  const [route, setRoute] = useState(authRoute)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [notice, setNotice] = useState('')
  const { pending, error, run } = useRequest()
  useEffect(() => {
    const changed = () => { setRoute(authRoute()); setNotice(''); setPassword('') }
    window.addEventListener('hashchange', changed)
    return () => window.removeEventListener('hashchange', changed)
  }, [])
  const mode = ['register', 'forgot-password', 'reset-password', 'verify-email', 'resend-verification'].includes(route) ? route : 'signin'
  const titles: Record<string, string> = {
    signin: 'Sign in to Camfranglais', register: 'Join the shared workspace', 'forgot-password': 'Reset your password',
    'reset-password': 'Choose a new password', 'verify-email': 'Verify your email', 'resend-verification': 'Send a verification link',
  }
  const errorCode = new URLSearchParams(window.location.hash.split('?')[1]).get('error')
  useEffect(() => { document.title = `${titles[mode]} — Camfranglais` }, [mode])
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setNotice('')
    if (mode === 'signin') {
      void run((signal) => api<Session>('/auth/login', { method: 'POST', body: { email, password }, signal }), onSignedIn)
      return
    }
    const token = new URLSearchParams(window.location.hash.split('?')[1]).get('token') ?? ''
    const body = mode === 'register' ? { email, password, display_name: name } :
      mode === 'reset-password' ? { token, password } : mode === 'verify-email' ? { token } : { email }
    void run((signal) => api<{ message: string }>(`/auth/${mode}`, { method: 'POST', body, signal }), (result) => {
      setNotice(result.message)
      setPassword('')
      if (mode === 'reset-password' || mode === 'verify-email') {
        window.history.replaceState(null, '', `${window.location.pathname}#signin`)
        setRoute('signin')
      }
    })
  }
  return <main className="auth-screen">
    <section className="auth-card">
      <Brand account />
      <p className="eyebrow">ONE SHARED COMPILER WORKSPACE</p>
      <h1>{titles[mode]}</h1>
      <p>Collect real statements, build a grammar and trace the compiler’s decisions.</p>
      {errorCode && <ErrorNotice message={errorCode === 'google-link-required'
        ? 'This email already has an account. Sign in with your existing password; matching emails are not automatically linked to Google.'
        : 'Google sign-in was cancelled. You can try again.'} />}
      {notice && <p className="notice notice-success" role="status">{notice}</p>}
      <ErrorNotice message={error} />
      <form className="account-form" onSubmit={submit}>
        {mode === 'register' && <label>Your name<input autoComplete="name" required maxLength={100} value={name} onChange={(event) => setName(event.target.value)} /></label>}
        {!['verify-email', 'reset-password'].includes(mode) && <label>Email address<input type="email" autoComplete="email" required maxLength={254} value={email} onChange={(event) => setEmail(event.target.value)} /></label>}
        {['signin', 'register', 'reset-password'].includes(mode) && <label>Password<input type="password" autoComplete={mode === 'signin' ? 'current-password' : 'new-password'} minLength={mode === 'signin' ? 1 : 12} maxLength={128} required value={password} onChange={(event) => setPassword(event.target.value)} /><span className="helper-text">{mode === 'signin' ? 'Enter your account password.' : 'Use at least 12 characters. A long, unique passphrase is recommended.'}</span></label>}
        <button className="button button-primary" disabled={pending} type="submit">{pending ? 'Please wait...' : mode === 'signin' ? 'Sign in' : mode === 'register' ? 'Create account' : mode === 'verify-email' ? 'Verify email' : mode === 'reset-password' ? 'Update password' : 'Send email'}</button>
      </form>
      {(mode === 'signin' || mode === 'register') && session.google_enabled && <a className="button button-secondary google-signin" href="/api/auth/google/start">Continue with Google</a>}
      <nav className="auth-links" aria-label="Account access">
        {mode !== 'signin' && <a href="#signin">Back to sign in</a>}
        {mode === 'signin' && <><a href="#register">Create an account</a><a href="#forgot-password">Forgot password?</a><a href="#resend-verification">Resend verification</a></>}
      </nav>
      {session.development_mail && <p className="notice notice-subtle">Local test mode: account emails are written to the server's private mail outbox. Ask the operator for your verification link. This mode is not used when hosted.</p>}
      <p className="helper-text">All signed-in users can view the shared collection, recordings, grammar and retained tests on this server. Only a record’s creator can edit or delete it; recorded tests are immutable. Your email, password and session remain personal. Record or share personal information only with permission.</p>
    </section>
  </main>
}

export default function AuthGate() {
  const [session, setSession] = useState<Session | null>(null)
  const [registeredUsers, setRegisteredUsers] = useState<number | null>(null)
  const [generation, setGeneration] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [route, setRoute] = useState(authRoute)
  const activeRequest = useRef<AbortController | null>(null)

  const accept = useCallback((next: Session) => {
    activeRequest.current?.abort()
    configureSession(next.csrf_token)
    setSession(next)
    setRegisteredUsers(null)
    setGeneration((value) => value + 1)
    setLoading(false)
    setError('')
  }, [])

  const load = useCallback(async () => {
    activeRequest.current?.abort()
    const controller = new AbortController()
    activeRequest.current = controller
    configureSession(null)
    setSession(null)
    setRegisteredUsers(null)
    setLoading(true)
    setError('')
    try {
      const next = await api<Session>('/auth/session', { signal: controller.signal })
      if (!controller.signal.aborted) accept(next)
    } catch (failure) {
      if (!isCancelled(failure)) { setError(messageOf(failure)); setLoading(false) }
    }
  }, [accept])

  useEffect(() => {
    void load()
    const expired = () => { setNotice('Your session ended. Sign in again to continue.'); void load() }
    const changed = (event: StorageEvent) => {
      if (event.key === 'mboa-session-change') { setNotice('The account changed in another tab. Unsaved drafts were cleared; shared records and tests remain.'); void load() }
    }
    const locationChanged = () => setRoute(authRoute())
    const unavailable = () => setNotice('Cross-tab notifications are unavailable in this browser. Close other Camfranglais tabs before changing accounts.')
    window.addEventListener('mboa:session-expired', expired)
    window.addEventListener('mboa:cross-tab-unavailable', unavailable)
    window.addEventListener('storage', changed)
    window.addEventListener('hashchange', locationChanged)
    return () => {
      activeRequest.current?.abort()
      window.removeEventListener('mboa:session-expired', expired)
      window.removeEventListener('mboa:cross-tab-unavailable', unavailable)
      window.removeEventListener('storage', changed)
      window.removeEventListener('hashchange', locationChanged)
    }
  }, [load])

  useEffect(() => {
    if (!session?.user) return
    let controller: AbortController | null = null
    const refresh = () => {
      controller?.abort()
      const request = new AbortController()
      controller = request
      void api<ProjectsResult>('/workspace/projects', { signal: request.signal })
        .then((value) => { if (!request.signal.aborted) setRegisteredUsers(value.registered_users) })
        .catch((failure: unknown) => { if (!isCancelled(failure)) setError(messageOf(failure)) })
    }
    const restored = () => {
      configureSession(session.csrf_token)
      setGeneration((value) => value + 1)
      setNotice('Shared workspace restored. Review the restored information before using it.')
      refresh()
    }
    refresh()
    window.addEventListener('focus', refresh)
    window.addEventListener('mboa:workspace-restored', restored)
    return () => {
      controller?.abort()
      window.removeEventListener('focus', refresh)
      window.removeEventListener('mboa:workspace-restored', restored)
    }
  }, [session?.user?.id, session?.csrf_token])

  if (loading) return <main className="auth-screen"><Spinner label="Checking your account" /></main>
  if (!session) return <main className="auth-screen"><section className="auth-card"><Brand account /><h1>Camfranglais is unavailable</h1><ErrorNotice message={error} onRetry={() => void load()} /></section></main>
  if (!session.user || ['verify-email', 'reset-password'].includes(route)) {
    return <>{notice && <p className="account-notice" role="status">{notice}</p>}<AuthForm session={session} onSignedIn={(next) => {
      accept(next)
      announceSession()
      setNotice('')
      window.location.hash = 'compiler'
    }} /></>
  }
  return <>
    {notice && <p className="account-notice" role="status">{notice}</p>}
    {error && <div className="account-notice"><ErrorNotice message={error} onRetry={() => void load()} /></div>}
    <App key={`${session.user.id}:${generation}`} account={session.user}
      registeredUsers={registeredUsers} onSignOut={() => {
        if (!window.confirm('Sign out? Unsaved drafts and recordings in this tab will be discarded. Shared records and all users’ saved tests remain on the server.')) return
        void api('/auth/logout', { method: 'POST' }).then(() => {
          configureSession(null)
          announceSession()
          setNotice('You have signed out.')
          void load()
        }).catch((failure: unknown) => { if (!isCancelled(failure)) setError(messageOf(failure)) })
      }} />
  </>
}
