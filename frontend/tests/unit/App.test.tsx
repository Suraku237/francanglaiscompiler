import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../../src/App'
import PublicSession from '../../src/PublicSession'
import { configureSession } from '../../src/api'
import { analyzerState, dataset, entry, health, metadata, publicSession, recordedTest, retainedTestReport, testReport } from '../fixtures'
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

describe('public compiler navigation', () => {
  it.each(['', '#translator', '#assistant', '#coursework', '#unknown', '#history', '#settings', '#imports',
    '#signin', '#register', '#forgot-password', '#reset-password?token=old', '#verify-email?token=old', '#profile', '#logout',
  ])('defaults %s to the compiler without retired screens or network requests', async (hash) => {
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
    expect(screen.queryByRole('button', { name: /translate|assistant|Ask AI|dictat|sign out|sign in/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /History|Workspace settings|Document import|Sign in/ })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Registered users')).not.toBeInTheDocument()
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

  it('initializes public access once and preserves input and immutable history through navigation', async () => {
    const original = entry({ text: '  Shared\tstatement\n' })
    const savedTest = recordedTest({ text: original.text })
    vi.mocked(fetch).mockImplementation(async (url) => {
      if (url === '/api/public/session') return jsonResponse(publicSession())
      if (url === '/api/health') return jsonResponse(health())
      if (url === '/api/metadata') return jsonResponse(metadata)
      if (url === '/api/dataset') return jsonResponse(dataset([original]))
      if (url === '/api/analyzer') return jsonResponse(analyzerState('S -> NOUN'))
      if (url === `/api/analyzer/tests/${savedTest.id}`) return jsonResponse(savedTest)
      if (String(url).startsWith('/api/analyzer/tests?')) return jsonResponse(retainedTestReport())
      throw new Error(`Unexpected request ${String(url)}`)
    })
    const user = userEvent.setup()
    render(<PublicSession />)
    await screen.findByLabelText('Statement to analyze')
    expect(vi.mocked(fetch).mock.calls[0]?.[0]).toBe('/api/public/session')
    expect(screen.queryByLabelText('Registered users')).not.toBeInTheDocument()
    const navigation = within(screen.getByRole('navigation', { name: 'Main navigation' }))
    await user.click(navigation.getByRole('link', { name: 'Collection' }))
    const viewButton = await screen.findByRole('button', { name: /^View expression:\s+Shared\s+statement\s*$/ })
    await user.click(viewButton)
    expect(screen.getByLabelText('Expression', { exact: true })).toHaveValue(original.text)
    expect(screen.getByLabelText('Expression', { exact: true })).toHaveAttribute('readonly')
    await user.click(screen.getByRole('button', { name: 'Done' }))
    expect(screen.getByLabelText('Counts across the public workspace')).toHaveTextContent('1Total entries')
    expect(screen.queryByRole('button', { name: /add entry|edit expression|delete expression/i })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Use as analyzer input' }))
    expect(await screen.findByLabelText('Statement to analyze')).toHaveValue(original.text)
    await user.click(navigation.getByRole('link', { name: 'Analysis' }))
    expect(await screen.findByRole('group', { name: 'Tests recorded' })).toHaveTextContent('3')
    await user.click(screen.getByRole('button', { name: 'Inspect test 1' }))
    expect(await screen.findByLabelText('Analyzed source text')).toHaveTextContent('Shared statement')
    await user.click(screen.getByText('Grammar settings', { exact: true }))
    expect(screen.getByLabelText('Context-free grammar')).toHaveAttribute('readonly')
    expect(screen.queryByRole('button', { name: 'Save grammar' })).not.toBeInTheDocument()
    await user.click(navigation.getByRole('link', { name: 'Franc Analyzer' }))
    expect(screen.getByLabelText('Statement to analyze')).toHaveValue(original.text)
    act(() => window.dispatchEvent(new Event('mboa:session-expired')))
    expect(screen.getByLabelText('Statement to analyze')).toHaveValue(original.text)
    expect(vi.mocked(fetch).mock.calls.filter(([url]) => url === '/api/public/session')).toHaveLength(1)
    expect(vi.mocked(fetch).mock.calls.every(([, init]) => init?.method === 'GET')).toBe(true)
    expect(vi.mocked(fetch).mock.calls.some(([url]) => /\/auth\/|\/workspace\//.test(String(url)))).toBe(false)
  })

  it('explains public retention, read-only data and browser protection without account controls', async () => {
    compilerApi()
    const user = userEvent.setup()
    render(<App />)
    await screen.findByLabelText('Statement to analyze')
    await user.click(within(screen.getByRole('complementary', { name: 'Workspace navigation' })).getByRole('button', { name: 'Privacy information' }))
    const dialog = screen.getByRole('dialog', { name: 'Data & privacy' })
    expect(dialog).toHaveTextContent('no OCR or automatic transcription')
    expect(dialog).toHaveTextContent('Existing backups and legacy records remain on the server')
    expect(dialog).toHaveTextContent('Analyze publicly retains each completed test')
    expect(dialog).toHaveTextContent('Do not submit personal or confidential content')
    expect(dialog).toHaveTextContent('saved grammar and recordings are read-only')
    expect(dialog).toHaveTextContent('cookie and request token protect submissions against cross-site requests')
    expect(dialog).toHaveTextContent('A stopped request may still finish and become publicly visible')
    expect(within(dialog).queryByRole('textbox')).not.toBeInTheDocument()
    expect(within(dialog).queryByRole('checkbox')).not.toBeInTheDocument()
    expect(dialog).not.toHaveTextContent(/signed-in|creator-only|sign-out|Google sign-in|user count|Gemini|API key|AI allowance/i)
  })
})
