import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../../src/App'
import AuthGate from '../../src/AuthGate'
import { configureSession } from '../../src/api'
import { analyzerState, dataset, entry, health, metadata, ownership, recordedTest, retainedTestReport, sharedWorkspace, testReport } from '../fixtures'
import { jsonResponse } from '../helpers'

beforeEach(() => {
  configureSession(null)
  window.history.replaceState(null, '', '/')
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
})
afterEach(() => configureSession(null))

function compilerApi() {
  vi.mocked(fetch).mockImplementation(async (url) => {
    if (url === '/api/health') return jsonResponse(health())
    if (url === '/api/analyzer') return jsonResponse(analyzerState())
    if (String(url).startsWith('/api/analyzer/tests?')) return jsonResponse(testReport())
    throw new Error(`Unexpected API request ${String(url)}`)
  })
}

describe('compiler-only navigation and account scope', () => {
  it.each(['', '#translator', '#assistant', '#coursework', '#unknown', '#history', '#settings', '#imports'])('defaults %s to the compiler without retired screens or network requests', async (hash) => {
    compilerApi()
    window.history.replaceState(null, '', `/${hash}`)
    render(<App />)
    await screen.findByLabelText('Statement to analyze')
    expect(window.location.hash).toBe('#compiler')
    expect(document.title).toBe('Franc Analyzer — Camfranglais Compiler')
    expect(screen.getByRole('heading', { level: 1, name: 'Franc Analyzer' })).toBeVisible()
    const links = within(screen.getByRole('navigation', { name: 'Main navigation' })).getAllByRole('link')
    expect(links.map((link) => link.textContent)).toEqual([
      'Franc Analyzer', 'Analysis', 'Collection', 'Dictionary', 'Synthetic examples',
    ])
    expect(links[0]).toHaveAttribute('aria-current', 'page')
    expect(screen.getByText('Compiler connected')).toBeVisible()
    expect(screen.queryByRole('button', { name: /translate|assistant|Ask AI|dictat/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /History|Workspace settings|Document import/ })).not.toBeInTheDocument()
    expect(vi.mocked(fetch).mock.calls.map(([url]) => url).sort()).toEqual(['/api/analyzer', '/api/health'])
  })

  it('opens the Analysis route with an honest empty state and no automatic computation', async () => {
    compilerApi()
    window.history.replaceState(null, '', '/#analysis')
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'No saved tests yet' })).toBeVisible()
    expect(document.title).toBe('Analysis — Camfranglais Compiler')
    expect(screen.getByRole('heading', { level: 1, name: 'Analysis' })).toBeVisible()
    expect(within(screen.getByRole('navigation', { name: 'Main navigation' })).getByRole('link', { name: 'Analysis' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByText('Grammar settings')).toBeVisible()
    expect(screen.getByLabelText('Context-free grammar')).not.toBeVisible()
    expect(screen.getByRole('region', { name: 'Lexer regular expression rules' })).not.toBeVisible()
    expect(vi.mocked(fetch).mock.calls.map(([url]) => url).sort()).toEqual(['/api/analyzer', '/api/analyzer/tests?offset=0&limit=25', '/api/health'])
  })

  it('resets account-specific drafts and permissions while preserving shared records, test totals and grammar', async () => {
    const firstSession = {
      user: { id: 'fixture-user', email: 'fixture@example.com', display_name: 'Fixture', email_verified: true, google_linked: false },
      csrf_token: 'fixture-csrf', google_enabled: true, email_enabled: true, development_mail: false,
    }
    const secondSession = { ...firstSession, csrf_token: 'second-csrf', user: { ...firstSession.user, id: 'second-user', email: 'second@example.com', display_name: 'Second' } }
    let session = firstSession
    const firstEntry = entry({ text: '  Shared\tstatement\n', ownership: ownership({ owner_id: firstSession.user.id, owner_name: 'Fixture' }) })
    const secondEntry = entry({ id: 'second-entry', text: 'Second shared statement', ownership: ownership({ owner_id: secondSession.user.id, owner_name: 'Second', can_edit: false }) })
    const savedTest = recordedTest({ ownership: firstEntry.ownership, text: firstEntry.text })
    vi.mocked(fetch).mockImplementation(async (url) => {
      if (url === '/api/auth/session') return jsonResponse(session)
      if (url === '/api/workspace/projects') return jsonResponse(sharedWorkspace())
      if (url === '/api/health') return jsonResponse(health())
      if (url === '/api/metadata') return jsonResponse(metadata)
      if (url === '/api/dataset') return jsonResponse(dataset([firstEntry, secondEntry].map((item) => ({
        ...item, ownership: { ...item.ownership, can_edit: item.ownership.owner_id === session.user.id },
      }))))
      if (url === '/api/analyzer') return jsonResponse(analyzerState('S -> NOUN', { ...firstEntry.ownership, can_edit: session.user.id === firstSession.user.id }))
      if (url === `/api/analyzer/tests/${savedTest.id}`) return jsonResponse({ ...savedTest, ownership: { ...savedTest.ownership, can_edit: session.user.id === firstSession.user.id } })
      if (String(url).startsWith('/api/analyzer/tests?')) return jsonResponse(retainedTestReport())
      throw new Error(`Unexpected request ${String(url)}`)
    })
    const user = userEvent.setup()
    render(<AuthGate />)
    expect(screen.queryByLabelText('Statement to analyze')).not.toBeInTheDocument()
    await screen.findByLabelText('Statement to analyze')
    expect(vi.mocked(fetch).mock.calls[0]?.[0]).toBe('/api/auth/session')
    expect(await screen.findByLabelText('Registered users')).toHaveTextContent('2 registered users')
    expect(screen.queryByLabelText('Active project')).not.toBeInTheDocument()
    const navigation = within(screen.getByRole('navigation', { name: 'Main navigation' }))
    await user.click(navigation.getByRole('link', { name: 'Collection' }))
    const firstCard = () => screen.getByRole('heading', { name: /^Shared\s+statement$/ }).closest('article')!
    await screen.findByRole('heading', { name: /^Second shared statement$/ })
    expect(within(firstCard()).getByRole('button', { name: /^Edit expression/ })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'View expression: Second shared statement' })).toBeEnabled()
    await user.click(within(firstCard()).getByRole('button', { name: 'Use as analyzer input' }))
    expect(await screen.findByLabelText('Statement to analyze')).toHaveValue(firstEntry.text)
    await user.click(navigation.getByRole('link', { name: 'Analysis' }))
    expect(await screen.findByRole('group', { name: 'Tests recorded' })).toHaveTextContent('3')
    await user.click(screen.getByRole('button', { name: 'Inspect test 1' }))
    expect(await screen.findByLabelText('Analyzed source text')).toHaveTextContent('Shared statement')
    await user.click(screen.getByText('Grammar settings'))
    await user.clear(screen.getByLabelText('Context-free grammar'))
    await user.paste('S -> NUMBER')
    expect(screen.getByRole('button', { name: 'Save grammar' })).toBeEnabled()
    session = secondSession
    act(() => window.dispatchEvent(new StorageEvent('storage', { key: 'mboa-session-change' })))
    expect(await screen.findByRole('group', { name: 'Tests recorded' })).toHaveTextContent('3')
    expect(screen.queryByLabelText('Analyzed source text')).not.toBeInTheDocument()
    await user.click(screen.getByText('Grammar settings'))
    await waitFor(() => expect(screen.getByLabelText('Context-free grammar')).toHaveValue('S -> NOUN'))
    expect(screen.getByRole('button', { name: 'Save grammar' })).toBeDisabled()
    expect(screen.getByText(/Shared grammar creator: Fixture/)).toBeVisible()
    await user.click(within(screen.getByRole('navigation', { name: 'Main navigation' })).getByRole('link', { name: 'Collection' }))
    await screen.findByRole('button', { name: 'Edit expression: Second shared statement' })
    expect(within(firstCard()).queryByRole('button', { name: /^Edit expression|^Delete expression/ })).not.toBeInTheDocument()
    expect(within(firstCard()).getByRole('button', { name: /^View expression/ })).toBeEnabled()
    expect(screen.getByLabelText('Counts across the shared workspace')).toHaveTextContent('2Total entries')
    await user.click(within(screen.getByRole('navigation', { name: 'Main navigation' })).getByRole('link', { name: 'Franc Analyzer' }))
    expect(screen.queryByLabelText('Context-free grammar')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Statement to analyze')).toHaveValue('')
    expect(screen.queryByLabelText('Group member 1')).not.toBeInTheDocument()
    session = firstSession
    act(() => window.dispatchEvent(new StorageEvent('storage', { key: 'mboa-session-change' })))
    await screen.findByLabelText('Statement to analyze')
    await user.click(within(screen.getByRole('navigation', { name: 'Main navigation' })).getByRole('link', { name: 'Analysis' }))
    expect(await screen.findByRole('group', { name: 'Tests recorded' })).toHaveTextContent('3')
    await user.click(screen.getByText('Grammar settings'))
    await user.clear(screen.getByLabelText('Context-free grammar'))
    await user.paste('S -> VERB')
    expect(screen.getByRole('button', { name: 'Save grammar' })).toBeEnabled()
    expect(vi.mocked(fetch).mock.calls.every(([, init]) => !new Headers(init?.headers).has('X-Mboa-Project'))).toBe(true)
    expect(vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(0)
    expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === 'PUT')).toBe(false)
  })

  it('explains local processing and preserved backups without provider configuration or quotas', async () => {
    compilerApi()
    const user = userEvent.setup()
    render(<App />)
    await screen.findByLabelText('Statement to analyze')
    const sidebar = within(screen.getByRole('complementary', { name: 'Workspace navigation' }))
    await user.click(sidebar.getByRole('button', { name: 'Privacy information' }))
    const dialog = screen.getByRole('dialog', { name: 'Data & privacy' })
    expect(dialog).toHaveTextContent('no OCR or automatic transcription')
    expect(dialog).toHaveTextContent('Google sign-in')
    expect(dialog).toHaveTextContent('Existing backups and legacy records remain on the server')
    expect(dialog).toHaveTextContent('Analyze records each completed test')
    expect(dialog).toHaveTextContent('remain after refresh or sign-out')
    expect(dialog).toHaveTextContent('Only the creator can edit or delete')
    expect(dialog).toHaveTextContent('every user’s retained tests')
    expect(dialog).toHaveTextContent('credentials are not shared')
    expect(dialog).not.toHaveTextContent('private account and selected project')
    expect(within(dialog).queryByRole('textbox')).not.toBeInTheDocument()
    expect(within(dialog).queryByRole('checkbox')).not.toBeInTheDocument()
    expect(dialog).not.toHaveTextContent(/Gemini|API key|AI allowance|provider retention/i)
  })

  it('keeps password sign-in guidance without linking to the removed Settings page', async () => {
    window.history.replaceState(null, '', '/#signin?error=google-link-required')
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({
      user: null, csrf_token: null, google_enabled: true, email_enabled: true, development_mail: false,
    }))
    render(<AuthGate />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Sign in with your existing password')
    expect(screen.getByRole('alert')).not.toHaveTextContent('Workspace settings')
    expect(screen.getByRole('link', { name: 'Forgot password?' })).toHaveAttribute('href', '#forgot-password')
    expect(screen.getByRole('link', { name: 'Continue with Google' })).toBeInTheDocument()
  })
})
