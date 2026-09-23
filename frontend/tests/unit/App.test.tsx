import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../../src/App'
import AuthGate from '../../src/AuthGate'
import { configureSession } from '../../src/api'
import { analyzerResult, analyzerState, health } from '../fixtures'
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
    expect(document.title).toBe('Franc Analyzer — Mboa Compiler')
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
    expect(await screen.findByRole('heading', { name: 'No completed analysis' })).toBeVisible()
    expect(document.title).toBe('Analysis — Mboa Compiler')
    expect(screen.getByRole('heading', { level: 1, name: 'Analysis' })).toBeVisible()
    expect(within(screen.getByRole('navigation', { name: 'Main navigation' })).getByRole('link', { name: 'Analysis' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByText('Grammar settings')).toBeVisible()
    expect(screen.getByLabelText('Context-free grammar')).not.toBeVisible()
    expect(screen.getByRole('region', { name: 'Lexer regular expression rules' })).not.toBeVisible()
    expect(vi.mocked(fetch).mock.calls.map(([url]) => url).sort()).toEqual(['/api/analyzer', '/api/health'])
  })

  it('requires authentication before loading the analyzer and remounts all drafts on project selection', async () => {
    const session = {
      user: { id: 'fixture-user', email: 'fixture@example.com', display_name: 'Fixture', email_verified: true, google_linked: false },
      csrf_token: 'fixture-csrf', google_enabled: true, email_enabled: true, development_mail: false,
    }
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    vi.mocked(fetch).mockImplementation(async (url, init) => {
      if (url === '/api/auth/session') return jsonResponse(session)
      if (url === '/api/workspace/projects') return jsonResponse({
        projects: [{ id: 'default', name: 'General', created_at: '' }, { id: 'other', name: 'Other project', created_at: '' }],
        default_project_id: 'default',
      })
      if (url === '/api/health') return jsonResponse(health())
      if (url === '/api/analyzer') {
        const selected = new Headers(init?.headers).get('X-Mboa-Project')
        return jsonResponse(analyzerState(selected === 'other' ? 'S -> VERB' : 'S -> NOUN'))
      }
      if (url === '/api/analyzer/analyze') return jsonResponse(analyzerResult({ text: 'Private unsaved text' }))
      throw new Error(`Unexpected request ${String(url)}`)
    })
    const user = userEvent.setup()
    render(<AuthGate />)
    expect(screen.queryByLabelText('Statement to analyze')).not.toBeInTheDocument()
    await screen.findByLabelText('Statement to analyze')
    expect(vi.mocked(fetch).mock.calls[0]?.[0]).toBe('/api/auth/session')
    await user.click(screen.getByLabelText('Statement to analyze'))
    await user.paste('Private unsaved text')
    const navigation = within(screen.getByRole('navigation', { name: 'Main navigation' }))
    await user.click(navigation.getByRole('link', { name: 'Analysis' }))
    await user.click(screen.getByText('Grammar settings'))
    await user.clear(screen.getByLabelText('Context-free grammar'))
    await user.paste('S -> NUMBER')
    await user.click(navigation.getByRole('link', { name: 'Franc Analyzer' }))
    await user.click(screen.getByRole('button', { name: 'Analyze' }))
    await user.click(await screen.findByRole('link', { name: 'View detailed analysis' }))
    expect(await screen.findByLabelText('Analyzed source text')).toHaveTextContent('Private unsaved text')
    await user.selectOptions(screen.getByLabelText('Active project'), 'other')
    expect(await screen.findByRole('heading', { name: 'No completed analysis' })).toBeVisible()
    expect(screen.queryByLabelText('Analyzed source text')).not.toBeInTheDocument()
    await user.click(screen.getByText('Grammar settings'))
    await waitFor(() => expect(screen.getByLabelText('Context-free grammar')).toHaveValue('S -> VERB'))
    await user.click(within(screen.getByRole('navigation', { name: 'Main navigation' })).getByRole('link', { name: 'Franc Analyzer' }))
    expect(screen.queryByLabelText('Context-free grammar')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Statement to analyze')).toHaveValue('')
    expect(screen.queryByLabelText('Group member 1')).not.toBeInTheDocument()
    const scope = vi.mocked(fetch).mock.calls.filter(([url]) => url === '/api/analyzer').at(-1)
    expect(new Headers(scope?.[1]?.headers).get('X-Mboa-Project')).toBe('other')
    expect(vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === 'POST').map(([url]) => url)).toEqual(['/api/analyzer/analyze'])
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
