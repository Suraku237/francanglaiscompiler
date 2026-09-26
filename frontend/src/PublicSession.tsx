import { useEffect, useState } from 'react'
import App from './App'
import { api, configureSession } from './api'
import { Brand } from './Brand'
import { ErrorNotice, Spinner } from './components'
import { useRequest } from './useRequest'

export interface PublicSessionInfo {
  access_mode: 'public_read_only'
  csrf_token: string
  capabilities: {
    analyze: true
    save_tests: true
    edit_collection: false
    edit_grammar: false
    edit_recordings: false
  }
}

export default function PublicSession() {
  const [ready, setReady] = useState(false)
  const [revision, setRevision] = useState(0)
  const { error, run, cancel } = useRequest()

  useEffect(() => {
    configureSession(null)
    void run(async (signal) => {
      const session = await api<PublicSessionInfo>('/public/session', { signal })
      if (session.access_mode !== 'public_read_only' || typeof session.csrf_token !== 'string' || !session.csrf_token.trim() ||
        session.capabilities?.analyze !== true || session.capabilities.save_tests !== true ||
        session.capabilities.edit_collection !== false || session.capabilities.edit_grammar !== false ||
        session.capabilities.edit_recordings !== false) {
        throw new Error('Public access could not be initialized. Please retry.')
      }
      return session
    }, (session) => {
      configureSession(session.csrf_token)
      setReady(true)
    })
    return cancel
  }, [revision, run, cancel])

  if (ready) return <App />
  return <main className="public-session">
    <Brand />
    <h1>Public compiler workspace</h1>
    <p>No account is needed. Collection, saved grammar and recordings are read-only.</p>
    {error ? <ErrorNotice message={error} onRetry={() => setRevision((value) => value + 1)} />
      : <p role="status"><Spinner label="Preparing public access" />Preparing public access…</p>}
    <p>Analysis text and results are publicly retained. Do not submit personal or confidential content.</p>
  </main>
}
