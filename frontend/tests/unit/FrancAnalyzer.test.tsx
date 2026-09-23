import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { FrancAnalyzer } from '../../src/FrancAnalyzer'
import { analyzerResult, analyzerState, lexicalStatistics, manualParse } from '../fixtures'
import { deferred, jsonResponse, requestBody } from '../helpers'

const onUseText = vi.fn()

async function renderAnalyzer(grammar = 'S -> NOUN') {
  vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(analyzerState(grammar)))
  const view = render(<FrancAnalyzer active onUseText={onUseText} />)
  await screen.findByLabelText('Statement to analyze')
  const user = userEvent.setup()
  const showAnalyzer = () => view.rerender(<FrancAnalyzer active onUseText={onUseText} />)
  const openSettings = async () => {
    view.rerender(<FrancAnalyzer active showAnalysis onUseText={onUseText} />)
    await user.click(screen.getByText('Grammar settings'))
  }
  return { ...view, user, showAnalyzer, openSettings }
}

const input = () => screen.getByLabelText('Statement to analyze')
const grammarInput = () => screen.getByLabelText('Context-free grammar')
const analyzeButton = () => screen.getByRole('button', { name: 'Analyze' })
const saveButton = () => screen.getByRole('button', { name: 'Save grammar' })

async function replaceText(user: ReturnType<typeof userEvent.setup>, field: HTMLElement, value: string) {
  await user.clear(field)
  await user.click(field)
  await user.paste(value)
}

describe('unified Franc Analyzer', () => {
  it('has one analysis action without tabs, duplicate collection or report/presentation tools', async () => {
    await renderAnalyzer()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Franc Analyzer')
    expect(screen.queryByRole('tab')).not.toBeInTheDocument()
    expect(screen.queryByRole('tabpanel')).not.toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Analyze' })).toHaveLength(1)
    expect(analyzeButton()).toBeEnabled()
    expect(screen.queryByRole('button', { name: /Add entry|Download coursework|Upload screenshot|Save project/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /Collection|Report|Presentation/i })).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/Group member|Linguistic discussion|Collection method/)).not.toBeInTheDocument()
    expect(screen.queryByText('Grammar settings')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Context-free grammar')).not.toBeInTheDocument()
    expect(vi.mocked(fetch).mock.calls.map(([url]) => url)).toEqual(['/api/analyzer'])
  })

  it.each([
    { text: 'veux', accepted: true },
    { text: '  je Veux\tun taxi.\n', accepted: false },
    { text: '', accepted: true },
  ])('shows the exact analyzed input beside its verdict: $text', async ({ text, accepted }) => {
    const { user, rerender } = await renderAnalyzer()
    if (text) await replaceText(user, input(), text)
    const response = analyzerResult({ text })
    response.parse.accepted = accepted
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(response))
    await user.click(analyzeButton())
    const verdict = within(await screen.findByRole('region', { name: 'Parser result' }))
    expect(verdict.getByRole('heading', { name: 'Analyzed sentence or word' })).toBeVisible()
    expect(verdict.getByLabelText('Analyzed source text')).toBeVisible()
    expect(verdict.getByLabelText('Analyzed source text').textContent).toBe(text || '(empty input)')
    expect(verdict.getByText(accepted ? 'ACCEPT' : 'REJECT', { exact: true })).toBeVisible()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    rerender(<FrancAnalyzer active showAnalysis onUseText={onUseText} />)
    expect(screen.getByRole('heading', { name: 'Analyzed sentence or word' })).toBeVisible()
    expect(screen.getByLabelText('Analyzed source text').textContent).toBe(text || '(empty input)')
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('runs all stages once but keeps detailed results exclusively on the Analysis page', async () => {
    const { user, rerender, openSettings, showAnalyzer } = await renderAnalyzer()
    const text = '  Mbom\t\n'
    await replaceText(user, input(), text)
    await openSettings()
    await replaceText(user, grammarInput(), 'S -> NOUN\nTail -> epsilon')
    expect(screen.getByText('Using unsaved grammar')).toBeInTheDocument()
    showAnalyzer()
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(analyzerResult({ text })))
    await user.click(analyzeButton())
    expect(await screen.findByRole('heading', { name: 'Parser result' })).toBeVisible()
    expect(screen.getByText('ACCEPT', { exact: true })).toBeVisible()
    expect(screen.getByRole('link', { name: 'View detailed analysis' })).toHaveAttribute('href', '#analysis')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.queryByText('Lexer rules & limitations')).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Token statistics' })).not.toBeInTheDocument()
    rerender(<FrancAnalyzer active showAnalysis onUseText={onUseText} />)
    expect(screen.getByRole('heading', { level: 1, name: 'Analysis' })).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Analyzed sentence or word' })).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Syntactic analysis' })).toBeVisible()
    expect(within(screen.getByRole('region', { name: 'Lexical tokens in source order' })).getByText('Mbom')).toBeVisible()
    expect(screen.getByLabelText('Analyzed source text').textContent).toBe(text)
    await user.click(screen.getByText('Parser trace for this input'))
    expect(screen.getByRole('region', { name: 'Table-driven parser step trace' })).toBeVisible()
    await user.click(screen.getByText('Transformations, FIRST/FOLLOW & LL(1) table'))
    expect(screen.getByRole('region', { name: 'Computed FIRST and FOLLOW sets' })).toBeVisible()
    await user.click(screen.getByText('Saved Collection - 0 records'))
    expect(screen.getByRole('heading', { name: 'Saved-statement token analysis' })).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Own-data acceptance tests' })).toBeVisible()
    expect(vi.mocked(fetch).mock.calls[1]?.[0]).toBe('/api/analyzer/analyze')
    expect(requestBody(vi.mocked(fetch).mock.calls[1])).toEqual({ text, grammar: 'S -> NOUN\nTail -> epsilon' })
    expect(fetch).toHaveBeenCalledTimes(2)
    rerender(<FrancAnalyzer active onUseText={onUseText} />)
    expect(input()).toHaveValue(text)
    expect(screen.queryByLabelText('Context-free grammar')).not.toBeInTheDocument()
    expect(screen.getByText('Using unsaved grammar')).toBeInTheDocument()
    expect(screen.getByText('ACCEPT', { exact: true })).toBeVisible()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    await openSettings()
    expect(grammarInput()).toHaveValue('S -> NOUN\nTail -> epsilon')
  })

  it('keeps grammar editing and disclosure navigation separate from computation and saving', async () => {
    const { user, rerender, openSettings } = await renderAnalyzer()
    await replaceText(user, input(), 'Draft only')
    await openSettings()
    await replaceText(user, grammarInput(), 'S -> VERB')
    await user.click(screen.getByText('Grammar settings'))
    rerender(<FrancAnalyzer active showAnalysis onUseText={onUseText} />)
    await user.click(screen.getByText('Lexer rules & limitations'))
    expect(screen.getByRole('region', { name: 'Lexer regular expression rules' })).toBeVisible()
    rerender(<FrancAnalyzer active onUseText={onUseText} />)
    expect(input()).toHaveValue('Draft only')
    expect(screen.queryByLabelText('Context-free grammar')).not.toBeInTheDocument()
    await openSettings()
    expect(grammarInput()).toHaveValue('S -> VERB')
    expect(fetch).toHaveBeenCalledOnce()
  })

  it('applies each reference handoff once, preserves raw text, and never auto-analyzes or collects it', async () => {
    const { user, rerender } = await renderAnalyzer()
    const incoming = { id: 1, text: '  Mbom,\tTu es where?\n', kind: 'dictionary' as const }
    rerender(<FrancAnalyzer active incomingText={incoming} onUseText={onUseText} />)
    expect(input()).toHaveValue(incoming.text)
    expect(input()).toHaveFocus()
    await replaceText(user, input(), 'My later draft')
    rerender(<FrancAnalyzer active incomingText={{ ...incoming }} onUseText={onUseText} />)
    expect(input()).toHaveValue('My later draft')
    rerender(<FrancAnalyzer active incomingText={{ ...incoming, id: 2, kind: 'examples' }} onUseText={onUseText} />)
    expect(input()).toHaveValue(incoming.text)
    expect(screen.getByText(/Synthetic example copied unchanged/)).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledOnce()
  })

  it.each(['text', 'grammar'])('clears every dependent result when %s changes', async (field) => {
    const { user, rerender, openSettings } = await renderAnalyzer()
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(analyzerResult()))
    await user.click(analyzeButton())
    await screen.findByRole('heading', { name: 'Parser result' })
    if (field === 'grammar') await openSettings()
    await replaceText(user, field === 'text' ? input() : grammarInput(), field === 'text' ? 'Changed' : 'S -> VERB')
    if (field === 'grammar') expect(grammarInput()).toBeVisible()
    expect(screen.queryByRole('heading', { name: 'Parser result' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Analyzed source text')).not.toBeInTheDocument()
    rerender(<FrancAnalyzer active showAnalysis onUseText={onUseText} />)
    expect(screen.getByRole('heading', { name: 'No completed analysis' })).toBeVisible()
    expect(screen.queryByRole('heading', { name: 'Token statistics' })).not.toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('saves only a grammar snapshot and keeps edits made while saving unsaved', async () => {
    const { user, openSettings, showAnalyzer } = await renderAnalyzer()
    await openSettings()
    await replaceText(user, grammarInput(), 'S -> VERB')
    const saving = deferred<Response>()
    vi.mocked(fetch).mockReturnValueOnce(saving.promise)
    await user.click(saveButton())
    expect(vi.mocked(fetch).mock.calls[1]?.[0]).toBe('/api/analyzer/grammar')
    expect(vi.mocked(fetch).mock.calls[1]?.[1]?.method).toBe('PUT')
    expect(requestBody(vi.mocked(fetch).mock.calls[1])).toEqual({ grammar: 'S -> VERB' })
    await replaceText(user, grammarInput(), 'S -> NUMBER')
    showAnalyzer()
    expect(analyzeButton()).toBeDisabled()
    await act(async () => saving.resolve(jsonResponse({ grammar: 'S -> VERB' })))
    expect(await screen.findByText(/Grammar saved privately/)).toBeInTheDocument()
    expect(analyzeButton()).toBeEnabled()
    await openSettings()
    expect(grammarInput()).toHaveValue('S -> NUMBER')
    expect(screen.getByText('Using unsaved grammar')).toBeInTheDocument()
    expect(saveButton()).toBeEnabled()
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('uses the saved canonical grammar after saving an unchanged snapshot', async () => {
    const { user, openSettings } = await renderAnalyzer()
    await openSettings()
    await replaceText(user, grammarInput(), '  S -> VERB  ')
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ grammar: 'S -> VERB' }))
    await user.click(saveButton())
    expect(await screen.findByText('Using saved grammar')).toBeInTheDocument()
    expect(grammarInput()).toHaveValue('S -> VERB')
    expect(saveButton()).toBeDisabled()
  })

  it('preserves grammar on an uncertain failed save and explains the correct recovery action', async () => {
    const { user, openSettings } = await renderAnalyzer()
    await openSettings()
    await replaceText(user, grammarInput(), 'S -> VERB')
    vi.mocked(fetch).mockRejectedValueOnce(new TypeError('Failed to fetch'))
    await user.click(saveButton())
    expect(await screen.findByRole('alert')).toHaveTextContent('The change may have completed.')
    expect(screen.getByRole('alert')).toHaveTextContent('Refresh saved grammar')
    expect(grammarInput()).toHaveValue('S -> VERB')
    expect(screen.getByText('Using unsaved grammar')).toBeInTheDocument()
  })

  it('refreshes server state without replacing edited grammar or the manual statement', async () => {
    const { user, openSettings, showAnalyzer } = await renderAnalyzer()
    await replaceText(user, input(), 'Private draft')
    await openSettings()
    await replaceText(user, grammarInput(), 'S -> VERB')
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(analyzerState('S -> NUMBER')))
    await user.click(screen.getByRole('button', { name: 'Refresh saved grammar' }))
    expect(await screen.findByText(/Your edited grammar and statement are kept/)).toBeInTheDocument()
    expect(grammarInput()).toHaveValue('S -> VERB')
    showAnalyzer()
    expect(input()).toHaveValue('Private draft')
  })

  it('adopts a newly saved grammar on refresh when its local grammar has not been edited', async () => {
    const { user, openSettings } = await renderAnalyzer()
    await openSettings()
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(analyzerState('S -> NUMBER')))
    await user.click(screen.getByRole('button', { name: 'Refresh saved grammar' }))
    expect(grammarInput()).toHaveValue('S -> NUMBER')
    expect(screen.getByText('Using saved grammar')).toBeInTheDocument()
  })

  it.each([
    { name: 'blank', grammar: '   ', message: 'The grammar is empty.' },
    { name: 'oversized', grammar: 'x'.repeat(12001), message: 'The grammar exceeds 12,000 characters.' },
  ])('explains a $name grammar on both pages and permits correction in Analysis', async ({ grammar, message }) => {
    const { user, openSettings, showAnalyzer } = await renderAnalyzer(grammar)
    expect(analyzeButton()).toBeDisabled()
    expect(screen.getByRole('alert')).toHaveTextContent(message)
    expect(screen.getByRole('alert')).toHaveTextContent('Grammar settings on Analysis')
    await openSettings()
    expect(screen.getByRole('alert')).toBeVisible()
    expect(grammarInput()).toHaveValue(grammar)
    expect(saveButton()).toBeDisabled()
    await replaceText(user, grammarInput(), 'S -> VERB')
    expect(saveButton()).toBeEnabled()
    showAnalyzer()
    expect(analyzeButton()).toBeEnabled()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(fetch).toHaveBeenCalledOnce()
  })

  it('allows an explicit empty-input run and moves its zero counts and trace to Analysis', async () => {
    const { user, rerender } = await renderAnalyzer('S -> epsilon')
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(analyzerResult({
      text: '', lexical: { tokens: [], verb_phrases: [], code_mixed_spans: [], slang_expressions: [], statistics: lexicalStatistics() }, parse: manualParse().parse,
    })))
    await user.click(analyzeButton())
    expect(requestBody(vi.mocked(fetch).mock.calls[1])).toEqual({ text: '', grammar: 'S -> epsilon' })
    expect(await screen.findByText('ACCEPT', { exact: true })).toBeVisible()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    rerender(<FrancAnalyzer active showAnalysis onUseText={onUseText} />)
    expect(screen.getByText('No lexical tokens. The parser will see only $.')).toBeVisible()
    expect(within(screen.getByRole('region', { name: 'Analyzed sentence or word' })).getByText('0 tokens · 0 distinct forms')).toBeVisible()
    await user.click(screen.getByText('Parser trace for this input'))
    expect(screen.getByText('S → epsilon')).toBeVisible()
  })

  it('keeps an oversized handoff unchanged and blocks analysis with an explicit error', async () => {
    const { rerender } = await renderAnalyzer()
    const text = 'x'.repeat(4001)
    rerender(<FrancAnalyzer active incomingText={{ id: 1, text, kind: 'dictionary' }} onUseText={onUseText} />)
    expect(input()).toHaveValue(text)
    expect(analyzeButton()).toBeDisabled()
    expect(screen.getByRole('alert')).toHaveTextContent('exceeds 4,000 characters')
    expect(fetch).toHaveBeenCalledOnce()
  })

  it('shows an analysis error instead of keeping success-shaped results from a prior run', async () => {
    const { user } = await renderAnalyzer()
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(analyzerResult()))
    await user.click(analyzeButton())
    await screen.findByRole('heading', { name: 'Parser result' })
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ detail: 'Invalid grammar notation.' }, 422))
    await user.click(analyzeButton())
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid grammar notation.')
    expect(screen.queryByRole('heading', { name: 'Parser result' })).not.toBeInTheDocument()
  })

  it.each(['cancel', 'edit', 'grammar', 'navigate'])('ignores a stale complete result after %s', async (action) => {
    const { user, rerender, openSettings } = await renderAnalyzer()
    const waiting = deferred<Response>()
    vi.mocked(fetch).mockReturnValueOnce(waiting.promise)
    await user.click(analyzeButton())
    if (action === 'cancel') await user.click(screen.getByRole('button', { name: 'Cancel analysis' }))
    if (action === 'edit') await replaceText(user, input(), 'Newer draft')
    if (action === 'grammar') {
      await openSettings()
      await replaceText(user, grammarInput(), 'S -> VERB')
    }
    if (action === 'navigate') rerender(<FrancAnalyzer active={false} onUseText={onUseText} />)
    expect(vi.mocked(fetch).mock.calls[1]?.[1]?.signal?.aborted).toBe(true)
    await act(async () => waiting.resolve(jsonResponse(analyzerResult())))
    expect(screen.queryByRole('heading', { name: 'Parser result' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Analyzed source text')).not.toBeInTheDocument()
    if (action === 'edit') expect(input()).toHaveValue('Newer draft')
  })

  it('can open Analysis during a run without cancelling or repeating the pipeline', async () => {
    const { user, rerender } = await renderAnalyzer()
    const waiting = deferred<Response>()
    vi.mocked(fetch).mockReturnValueOnce(waiting.promise)
    await user.click(analyzeButton())
    rerender(<FrancAnalyzer active showAnalysis onUseText={onUseText} />)
    expect(screen.getByRole('button', { name: 'Cancel analysis' })).toBeVisible()
    expect(screen.queryByRole('heading', { name: 'No completed analysis' })).not.toBeInTheDocument()
    expect(vi.mocked(fetch).mock.calls[1]?.[1]?.signal?.aborted).toBe(false)
    await act(async () => waiting.resolve(jsonResponse(analyzerResult())))
    expect(screen.getByRole('heading', { name: 'Analyzed sentence or word' })).toBeVisible()
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('drops completed statistics when leaving the analyzer workspace for other pages', async () => {
    const { user, rerender } = await renderAnalyzer()
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(analyzerResult()))
    await user.click(analyzeButton())
    await screen.findByRole('heading', { name: 'Parser result' })
    rerender(<FrancAnalyzer active={false} onUseText={onUseText} />)
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(analyzerState()))
    rerender(<FrancAnalyzer active showAnalysis onUseText={onUseText} />)
    expect(await screen.findByRole('heading', { name: 'No completed analysis' })).toBeVisible()
    expect(screen.queryByRole('heading', { name: 'Token statistics' })).not.toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(3)
  })

  it('shows a load error on a direct Analysis visit and permits an explicit retry', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ detail: 'Workspace temporarily unavailable.' }, 503))
    const user = userEvent.setup()
    render(<FrancAnalyzer active showAnalysis onUseText={onUseText} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Workspace temporarily unavailable.')
    expect(screen.queryByRole('heading', { name: 'Token statistics' })).not.toBeInTheDocument()
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(analyzerState()))
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('heading', { name: 'No completed analysis' })).toBeVisible()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('warns before unloading an unsaved statement even without a grammar edit', async () => {
    const { user } = await renderAnalyzer()
    const clean = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(clean)
    expect(clean.defaultPrevented).toBe(false)
    await replaceText(user, input(), 'Do not lose this statement')
    const dirty = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(dirty)
    expect(dirty.defaultPrevented).toBe(true)
  })
})
