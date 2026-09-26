import { StrictMode } from 'react'
import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import PublicSession from '../../src/PublicSession'
import { api, configureSession } from '../../src/api'
import { deferred, jsonResponse } from '../helpers'
import { publicSession } from '../fixtures'

vi.mock('../../src/App', () => ({ default: () => <main>Public analyzer ready</main> }))

beforeEach(() => configureSession(null))
afterEach(() => configureSession(null))

describe('public browser initialization', () => {
  it('waits for a valid bootstrap, then uses its CSRF token and same-origin cookies without an account', async () => {
    const bootstrap = deferred<Response>()
    vi.mocked(fetch).mockReturnValueOnce(bootstrap.promise)
    render(<PublicSession />)
    expect(screen.getByText('Preparing public access…', { exact: true })).toBeVisible()
    expect(screen.queryByText('Public analyzer ready')).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/email|password/i)).not.toBeInTheDocument()
    await act(async () => bootstrap.resolve(jsonResponse(publicSession())))
    expect(await screen.findByText('Public analyzer ready')).toBeVisible()
    expect(vi.mocked(fetch).mock.calls[0]).toEqual(['/api/public/session', expect.objectContaining({ credentials: 'same-origin', cache: 'no-store', method: 'GET' })])
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ saved: true }))
    await api('/analyzer/tests', { method: 'POST', body: { text: 'Fixture' } })
    expect(vi.mocked(fetch).mock.calls[1]?.[1]).toMatchObject({
      credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': 'test-csrf' },
    })
    expect(vi.mocked(fetch).mock.calls.some(([url]) => /auth|workspace/.test(String(url)))).toBe(false)
  })

  it('shows a real error and explicit retry instead of pretending initialization succeeded', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ detail: 'Public access temporarily unavailable.' }, 503))
    const user = userEvent.setup()
    render(<PublicSession />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Public access temporarily unavailable.')
    expect(screen.queryByText('Public analyzer ready')).not.toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(publicSession()))
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('Public analyzer ready')).toBeVisible()
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it.each([
    { ...publicSession(), csrf_token: '' },
    { ...publicSession(), csrf_token: 42 },
    { ...publicSession(), access_mode: 'authenticated' },
    { ...publicSession(), capabilities: undefined },
    { ...publicSession(), capabilities: { ...publicSession().capabilities, edit_collection: true } },
  ])('rejects malformed or incompatible bootstrap data without displaying login: %j', async (session) => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(session))
    render(<PublicSession />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Public access could not be initialized.')
    expect(screen.getByRole('button', { name: 'Try again' })).toBeEnabled()
    expect(screen.queryByText('Public analyzer ready')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /sign in|register/i })).not.toBeInTheDocument()
  })

  it('does not consume legacy account links or follow session-expired events', async () => {
    window.history.replaceState(null, '', '#verify-email?token=obsolete-bookmark')
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(publicSession()))
    render(<PublicSession />)
    await screen.findByText('Public analyzer ready')
    act(() => window.dispatchEvent(new Event('mboa:session-expired')))
    expect(screen.getByText('Public analyzer ready')).toBeVisible()
    expect(fetch).toHaveBeenCalledOnce()
    expect(vi.mocked(fetch).mock.calls[0]?.[0]).toBe('/api/public/session')
  })

  it('ignores the cancelled StrictMode initialization instead of losing the valid token', async () => {
    const first = deferred<Response>()
    vi.mocked(fetch).mockReturnValueOnce(first.promise).mockResolvedValueOnce(jsonResponse(publicSession()))
    render(<StrictMode><PublicSession /></StrictMode>)
    expect(await screen.findByText('Public analyzer ready')).toBeVisible()
    expect(vi.mocked(fetch).mock.calls[0]?.[1]?.signal?.aborted).toBe(true)
    await act(async () => first.resolve(jsonResponse({ ...publicSession(), csrf_token: 'obsolete-token' })))
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ reading: null }))
    await api('/readings/lookup', { method: 'POST', body: { text: 'Fixture', language: 'en' } })
    expect(vi.mocked(fetch).mock.calls.at(-1)?.[1]?.headers).toMatchObject({ 'X-CSRF-Token': 'test-csrf' })
  })
})
