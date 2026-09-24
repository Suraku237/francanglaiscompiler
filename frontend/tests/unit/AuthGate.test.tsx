import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AuthGate from '../../src/AuthGate'
import { configureSession } from '../../src/api'
import { jsonResponse } from '../helpers'
import { sharedWorkspace } from '../fixtures'
import type { Account } from '../../src/accountTypes'

vi.mock('../../src/App', () => ({
  default: ({ account, registeredUsers }: { account: Account; registeredUsers: number | null }) => <main>Shared workspace signed in as {account.email} · {registeredUsers} registered users</main>,
}))

const guest = { user: null, csrf_token: null, google_enabled: true, email_enabled: true, development_mail: false }
const signedIn = {
  ...guest, csrf_token: 'session-specific-csrf',
  user: { id: 'first-id', email: 'first@example.com', display_name: 'First', email_verified: true, google_linked: false },
}

beforeEach(() => {
  configureSession(null)
  window.history.replaceState(null, '', '#signin')
})
afterEach(() => configureSession(null))

describe('authenticated shared workspace gate', () => {
  it('never renders shared app data before a session is verified', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(guest))
    render(<AuthGate />)
    expect(screen.queryByText(/Shared workspace signed in as/)).not.toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Sign in to Camfranglais' })).toBeVisible()
    expect(screen.getByRole('link', { name: 'Continue with Google' })).toHaveAttribute('href', '/api/auth/google/start')
    expect(vi.mocked(fetch).mock.calls.every(([url]) => url === '/api/auth/session')).toBe(true)
    expect(screen.getByText(/All signed-in users can view the shared collection/)).toHaveTextContent('Your email, password and session remain personal.')
  })

  it('shows an actionable error instead of exposing shared app data when session loading fails', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: 'Account service unavailable.' }, 503))
    render(<AuthGate />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Account service unavailable.')
    expect(screen.queryByText(/Shared workspace signed in as/)).not.toBeInTheDocument()
  })

  it('signs in explicitly and sends no password to saved-work endpoints', async () => {
    vi.mocked(fetch).mockImplementation(async (url) => {
      if (url === '/api/auth/session') return jsonResponse(guest)
      if (url === '/api/auth/login') return jsonResponse(signedIn)
      if (url === '/api/workspace/projects') return jsonResponse(sharedWorkspace())
      throw new Error(`Unexpected request: ${String(url)}`)
    })
    const user = userEvent.setup()
    render(<AuthGate />)
    await user.type(await screen.findByLabelText('Email address'), 'first@example.com')
    await user.type(screen.getByLabelText(/^Password/), 'Secret test passphrase')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('main')).toHaveTextContent('Shared workspace signed in as first@example.com')
    await waitFor(() => expect(screen.getByRole('main')).toHaveTextContent('2 registered users'))
    const login = vi.mocked(fetch).mock.calls.find(([url]) => url === '/api/auth/login')
    expect(login?.[1]?.body).toBe('{"email":"first@example.com","password":"Secret test passphrase"}')
    expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes('/history'))).toBe(false)
  })

  it('clears authenticated UI when another tab signs out without claiming shared records are erased', async () => {
    let current = signedIn as typeof signedIn | typeof guest
    vi.mocked(fetch).mockImplementation(async (url) => {
      if (url === '/api/auth/session') return jsonResponse(current)
      if (url === '/api/workspace/projects') return jsonResponse(sharedWorkspace())
      throw new Error(`Unexpected request: ${String(url)}`)
    })
    render(<AuthGate />)
    await screen.findByText(/Shared workspace signed in as first@example.com/)
    current = guest
    act(() => window.dispatchEvent(new StorageEvent('storage', { key: 'mboa-session-change', newValue: 'changed' })))
    await screen.findByRole('heading', { name: 'Sign in to Camfranglais' })
    expect(screen.queryByText(/Shared workspace signed in as first@example.com/)).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Unsaved drafts were cleared; shared records and tests remain.')
  })

  it('refreshes registered accounts on focus without treating the count as online users', async () => {
    let count = 2
    vi.mocked(fetch).mockImplementation(async (url) => {
      if (url === '/api/auth/session') return jsonResponse(signedIn)
      if (url === '/api/workspace/projects') return jsonResponse(sharedWorkspace(count))
      throw new Error(`Unexpected request: ${String(url)}`)
    })
    render(<AuthGate />)
    await screen.findByText(/2 registered users/)
    count = 3
    act(() => window.dispatchEvent(new Event('focus')))
    await screen.findByText(/3 registered users/)
    expect(vi.mocked(fetch).mock.calls.filter(([url]) => url === '/api/auth/session')).toHaveLength(1)
  })

  it('verification links require an explicit button and consume no token on load', async () => {
    window.history.replaceState(null, '', '#verify-email?token=synthetic-token-for-testing')
    vi.mocked(fetch).mockImplementation(async (url) => {
      if (url === '/api/auth/session') return jsonResponse(guest)
      if (url === '/api/auth/verify-email') return jsonResponse({ message: 'Email verified. You can now sign in.' })
      throw new Error(`Unexpected request: ${String(url)}`)
    })
    const user = userEvent.setup()
    render(<AuthGate />)
    await screen.findByRole('heading', { name: 'Verify your email' })
    expect(vi.mocked(fetch).mock.calls.some(([url]) => url === '/api/auth/verify-email')).toBe(false)
    await user.click(screen.getByRole('button', { name: 'Verify email' }))
    await waitFor(() => expect(window.location.hash).toBe('#signin'))
    expect(screen.getByRole('status')).toHaveTextContent('Email verified.')
  })
})
