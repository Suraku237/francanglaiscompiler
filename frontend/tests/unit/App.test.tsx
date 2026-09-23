import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../../src/App'
import AuthGate from '../../src/AuthGate'
import { configureSession } from '../../src/api'
import { courseworkState, health, project } from '../fixtures'
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
    if (url === '/api/coursework') return jsonResponse(courseworkState())
    throw new Error(`Unexpected API request ${String(url)}`)
  })
}

describe('compiler-only navigation and account scope', () => {
  it.each(['', '#translator', '#assistant', '#coursework', '#unknown'])('defaults %s to the compiler without AI surfaces or network requests', async (hash) => {
    compilerApi()
    window.history.replaceState(null, '', `/${hash}`)
    render(<App />)
    await screen.findByLabelText('Context-free grammar')
    expect(window.location.hash).toBe('#compiler')
    expect(document.title).toBe('Compiler lab — Mboa Compiler')
    expect(screen.getByRole('heading', { level: 1, name: 'Compiler lab' })).toBeVisible()
    const links = within(screen.getByRole('navigation', { name: 'Main navigation' })).getAllByRole('link')
    expect(links.map((link) => link.textContent)).toEqual([
      'Compiler lab', 'Collection', 'Dictionary', 'Synthetic examples', 'Document import', 'History', 'Workspace settings',
    ])
    expect(links[0]).toHaveAttribute('aria-current', 'page')
    expect(screen.getByText('Compiler connected')).toBeVisible()
    expect(screen.queryByRole('button', { name: /translate|assistant|Ask AI|dictat/i })).not.toBeInTheDocument()
    expect(vi.mocked(fetch).mock.calls.map(([url]) => url).sort()).toEqual(['/api/coursework', '/api/health'])
  })

  it('requires authentication before loading coursework and remounts all drafts on project selection', async () => {
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
      if (url === '/api/coursework') {
        const selected = new Headers(init?.headers).get('X-Mboa-Project')
        return jsonResponse(courseworkState(project({ grammar: selected === 'other' ? 'S -> VERB' : 'S -> NOUN' })))
      }
      throw new Error(`Unexpected request ${String(url)}`)
    })
    const user = userEvent.setup()
    render(<AuthGate />)
    expect(screen.queryByLabelText('Context-free grammar')).not.toBeInTheDocument()
    await screen.findByLabelText('Context-free grammar')
    expect(vi.mocked(fetch).mock.calls[0]?.[0]).toBe('/api/auth/session')
    await user.click(screen.getByLabelText('Sentence to analyze'))
    await user.paste('Private unsaved text')
    await user.click(screen.getByRole('tab', { name: 'Report & presentation' }))
    await user.click(screen.getByLabelText('Group member 1'))
    await user.paste('Private member')
    await user.selectOptions(screen.getByLabelText('Active project'), 'other')
    await waitFor(() => expect(screen.getByLabelText('Context-free grammar')).toHaveValue('S -> VERB'))
    expect(screen.getByLabelText('Manual parser test')).toHaveValue('')
    expect(screen.getByLabelText('Group member 1')).toHaveValue('')
    const scope = vi.mocked(fetch).mock.calls.filter(([url]) => url === '/api/coursework').at(-1)
    expect(new Headers(scope?.[1]?.headers).get('X-Mboa-Project')).toBe('other')
    await user.click(screen.getByRole('tab', { name: 'Data collection' }))
    await user.click(screen.getByText('Collection notes for the report'))
    expect(screen.getByRole('checkbox', { name: /We manually transcribed/ })).not.toBeChecked()
    expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method && init.method !== 'GET')).toBe(false)
  })

  it('explains local processing and preserved backups without provider configuration or quotas', async () => {
    compilerApi()
    const user = userEvent.setup()
    render(<App />)
    await screen.findByLabelText('Context-free grammar')
    await user.click(screen.getByRole('button', { name: 'Settings & privacy' }))
    const dialog = screen.getByRole('dialog', { name: 'Workspace settings & privacy' })
    expect(dialog).toHaveTextContent('no OCR or automatic transcription')
    expect(dialog).toHaveTextContent('Google sign-in')
    expect(dialog).toHaveTextContent('Backups include your projects')
    expect(dialog).not.toHaveTextContent(/Gemini|API key|AI allowance|provider retention/i)
  })
})
