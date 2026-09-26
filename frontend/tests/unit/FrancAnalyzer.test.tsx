import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { FrancAnalyzer } from '../../src/FrancAnalyzer'
import { analyzerState, lexicalStatistics, manualParse, ownership, recordedTest, retainedTestReport, testReport, vocabularyApproval } from '../fixtures'
import { deferred, jsonResponse, requestBody } from '../helpers'

const onUseText = vi.fn()
const input = () => screen.getByLabelText('Statement to analyze')
const grammarInput = () => screen.getByLabelText('Context-free grammar')
const analyzeButton = () => screen.getByRole('button', { name: 'Analyze' })
const testRequests = () => vi.mocked(fetch).mock.calls.filter(([url, init]) => url === '/api/analyzer/tests' && init?.method === 'POST')

async function replaceText(user: ReturnType<typeof userEvent.setup>, field: HTMLElement, value: string) {
  await user.clear(field)
  await user.click(field)
  await user.paste(value)
}

async function renderAnalyzer(grammar = 'S -> NOUN', grammarOwnership = ownership()) {
  const fixtures = { state: analyzerState(grammar, grammarOwnership), report: testReport() }
  vi.mocked(fetch).mockImplementation(async (url) => {
    if (url === '/api/analyzer') return jsonResponse(fixtures.state)
    if (String(url).startsWith('/api/analyzer/tests?')) return jsonResponse(fixtures.report)
    throw new Error(`Unexpected synthetic request: ${String(url)}`)
  })
  const view = render(<FrancAnalyzer active onUseText={onUseText} />)
  await screen.findByLabelText('Statement to analyze')
  const user = userEvent.setup()
  const showAnalyzer = () => view.rerender(<FrancAnalyzer active onUseText={onUseText} />)
  const showAnalysis = async () => {
    view.rerender(<FrancAnalyzer active showAnalysis onUseText={onUseText} />)
    await screen.findByRole('heading', { name: 'Test statistics' })
  }
  const openSettings = async () => {
    await showAnalysis()
    if (!grammarInput().closest('details')?.open) await user.click(screen.getByText('Grammar settings'))
  }
  return { ...view, user, fixtures, showAnalyzer, showAnalysis, openSettings }
}

describe('Franc Analyzer with retained tests', () => {
  it('keeps input and one explicit Analyze action on the main page and read-only grammar on Analysis', async () => {
    const { openSettings } = await renderAnalyzer()
    expect(screen.queryByRole('tab')).not.toBeInTheDocument()
    expect(screen.queryByText('Grammar settings')).not.toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(analyzeButton()).toBeEnabled()
    expect(screen.getByText(/Analyze publicly retains this test/)).toHaveTextContent('Do not submit personal or confidential content')
    await openSettings()
    expect(grammarInput()).toBeVisible()
    expect(grammarInput()).toHaveAttribute('readonly')
    expect(screen.queryByRole('button', { name: 'Save grammar' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'No saved tests yet' })).toBeVisible()
    expect(testRequests()).toHaveLength(0)
  })

  it.each([
    { text: 'veux', tokens: [{ text: 'veux', category: 'VERB' }], accepted: true, grammarAccepted: true },
    { text: 'wanda', tokens: [{ text: 'wanda', category: 'SLANG' }], accepted: true, grammarAccepted: false },
    { text: '  je Veux\t+.\n', tokens: [{ text: 'je', category: 'FRENCH_FUNCTION_WORD' }, { text: 'Veux', category: 'VERB' }, { text: '+', category: 'UNKNOWN' }, { text: '.', category: 'PUNCTUATION' }], accepted: false, grammarAccepted: true },
    { text: '', tokens: [], accepted: true, grammarAccepted: true },
  ])('shows exact saved source, classification order and verdict for $text', async ({ text, tokens, accepted, grammarAccepted }) => {
    const { user, fixtures, showAnalysis } = await renderAnalyzer()
    if (text) await replaceText(user, input(), text)
    const response = recordedTest({ text })
    response.lexical.tokens = tokens
    response.approval = vocabularyApproval(tokens.filter((token) => token.category === 'UNKNOWN').length)
    response.parse.accepted = grammarAccepted
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(response))
    await user.click(analyzeButton())
    const verdict = within(await screen.findByRole('region', { name: 'Vocabulary result' }))
    expect(verdict.getByLabelText('Analyzed source text').textContent).toBe(text || '(empty input)')
    expect(verdict.getByText(accepted ? 'ACCEPT' : 'REJECT', { exact: true })).toBeVisible()
    if (tokens.length) {
      const rows = within(verdict.getByRole('region', { name: 'Lexical tokens in source order' })).getAllByRole('row').slice(1)
      expect(rows.map((row) => row.textContent)).toEqual(tokens.map((token, index) => `${index + 1}${token.text}${token.category}`))
    } else expect(verdict.getByText('No lexical tokens. The parser will see only $.')).toBeVisible()
    expect(screen.queryByRole('heading', { name: 'Test statistics' })).not.toBeInTheDocument()
    expect(requestBody(testRequests()[0])).toEqual({ request_id: expect.any(String), text, grammar: 'S -> NOUN' })
    fixtures.report = retainedTestReport()
    await showAnalysis()
    expect(screen.getByRole('group', { name: 'Tests recorded' })).toHaveTextContent('3')
    expect(screen.getByLabelText('Analyzed source text').textContent).toBe(text || '(empty input)')
    expect(testRequests()).toHaveLength(1)
    expect(vi.mocked(fetch).mock.calls.some(([url]) => url === '/api/analyzer/analyze')).toBe(false)
  })

  it('uses only the saved grammar and never changes Collection or grammar', async () => {
    const { user, showAnalyzer, openSettings } = await renderAnalyzer()
    await replaceText(user, input(), '  Mbom\t\n')
    await openSettings()
    await user.type(grammarInput(), 'S -> UNKNOWN')
    expect(grammarInput()).toHaveValue('S -> NOUN')
    showAnalyzer()
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(recordedTest()))
    await user.click(analyzeButton())
    await screen.findByRole('region', { name: 'Vocabulary result' })
    expect(requestBody(testRequests()[0])).toMatchObject({ text: '  Mbom\t\n', grammar: 'S -> NOUN' })
    expect(vi.mocked(fetch).mock.calls.some(([url, init]) => url === '/api/dataset' && init?.method === 'POST')).toBe(false)
    expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === 'PUT')).toBe(false)
    await openSettings()
    expect(grammarInput()).toHaveValue('S -> NOUN')
  })

  it.each([false, true])('does not offer grammar editing even with obsolete permission flags: %s', async (canEdit) => {
    const oldOwnership = ownership({ owner_id: 'historical-owner', owner_name: 'Historical name', can_edit: canEdit })
    const { user, fixtures, openSettings, showAnalyzer } = await renderAnalyzer('S -> NOUN', oldOwnership)
    await replaceText(user, input(), '  retained statement\t')
    await openSettings()
    expect(screen.queryByText(/Historical name|creator:/i)).not.toBeInTheDocument()
    expect(grammarInput()).toHaveAttribute('readonly')
    expect(screen.queryByRole('button', { name: 'Save grammar' })).not.toBeInTheDocument()
    expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === 'PUT')).toBe(false)
    fixtures.state = analyzerState('S -> VERB')
    await user.click(screen.getByRole('button', { name: 'Refresh saved grammar' }))
    await waitFor(() => expect(grammarInput()).toHaveValue('S -> VERB'))
    showAnalyzer()
    const saved = recordedTest({ text: '  retained statement\t', grammar_source: 'S -> VERB' })
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(saved))
    await user.click(analyzeButton())
    await screen.findByRole('region', { name: 'Vocabulary result' })
    expect(requestBody(testRequests()[0])).toEqual({ request_id: expect.any(String), text: saved.text, grammar: saved.grammar_source })
    expect(vi.mocked(fetch).mock.calls.some(([url, init]) => init?.method === 'PUT' || (url === '/api/dataset' && init?.method === 'POST'))).toBe(false)
    await openSettings()
    expect(grammarInput()).toHaveValue(saved.grammar_source)
    expect(screen.queryByRole('button', { name: 'Save grammar' })).not.toBeInTheDocument()
  })

  it('treats ownerless grammar as saved reference data, not an invitation to claim it', async () => {
    const { openSettings } = await renderAnalyzer()
    await openSettings()
    expect(screen.getByText(/The saved grammar is read-only/)).toBeVisible()
    expect(screen.queryByText(/unclaimed|first person|creator/i)).not.toBeInTheDocument()
    expect(grammarInput()).toHaveAttribute('readonly')
    expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === 'PUT')).toBe(false)
  })

  it('requires an explicit reload after a stale-grammar 409 without silently retrying or changing the input', async () => {
    const { user, fixtures } = await renderAnalyzer()
    await replaceText(user, input(), '  Keep this text\t')
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ detail: 'The saved grammar changed. Reload the saved grammar.' }, 409))
    await user.click(analyzeButton())
    expect(await screen.findByRole('alert')).toHaveTextContent('Reload the saved grammar')
    expect(input()).toHaveValue('  Keep this text\t')
    expect(analyzeButton()).toBeDisabled()
    expect(testRequests()).toHaveLength(1)
    expect(vi.mocked(fetch).mock.calls.filter(([url]) => url === '/api/analyzer')).toHaveLength(1)
    fixtures.state = analyzerState('S -> VERB')
    await user.click(screen.getByRole('button', { name: 'Reload saved grammar' }))
    await waitFor(() => expect(analyzeButton()).toBeEnabled())
    expect(testRequests()).toHaveLength(1)
    expect(input()).toHaveValue('  Keep this text\t')
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(recordedTest({ grammar_source: 'S -> VERB' })))
    await user.click(analyzeButton())
    await screen.findByRole('region', { name: 'Vocabulary result' })
    expect(requestBody(testRequests()[1])).toMatchObject({ text: '  Keep this text\t', grammar: 'S -> VERB' })
    expect(requestBody(testRequests()[1])).not.toEqual(requestBody(testRequests()[0]))
  })

  it('reuses an idempotency key on uncertain retry but counts a second successful click as a new test', async () => {
    const { user } = await renderAnalyzer()
    await replaceText(user, input(), 'veux')
    vi.mocked(fetch).mockRejectedValueOnce(new TypeError('Interrupted'))
    await user.click(analyzeButton())
    expect(await screen.findByRole('alert')).toHaveTextContent('The change may have completed.')
    expect(screen.getByRole('alert')).toHaveTextContent('refresh saved tests')
    const first = requestBody(testRequests()[0])
    expect(first).not.toMatchObject({ request_id: recordedTest().id })
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(recordedTest({ text: 'veux' })))
    await user.click(analyzeButton())
    await screen.findByRole('region', { name: 'Vocabulary result' })
    expect(requestBody(testRequests()[1])).toEqual(first)
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(recordedTest({ text: 'veux' })))
    await user.click(analyzeButton())
    await screen.findByRole('region', { name: 'Vocabulary result' })
    expect(requestBody(testRequests()[2])).not.toEqual(first)
  })

  it('changing an input after an uncertain request starts a distinct test', async () => {
    const { user } = await renderAnalyzer()
    await replaceText(user, input(), 'veux')
    vi.mocked(fetch).mockRejectedValueOnce(new TypeError('Interrupted'))
    await user.click(analyzeButton())
    await screen.findByRole('alert')
    const first = requestBody(testRequests()[0])
    await replaceText(user, input(), 'taxi')
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(recordedTest({ text: 'taxi' })))
    await user.click(analyzeButton())
    await screen.findByRole('region', { name: 'Vocabulary result' })
    expect(requestBody(testRequests()[1])).not.toEqual(first)
  })

  it('does not compute using stale settings after a failed grammar refresh', async () => {
    const { user, openSettings, showAnalyzer } = await renderAnalyzer()
    await replaceText(user, input(), 'Keep this statement')
    await openSettings()
    vi.mocked(fetch).mockRejectedValueOnce(new TypeError('Interrupted'))
    await user.click(screen.getByRole('button', { name: 'Refresh saved grammar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot reach the server')
    expect(grammarInput()).toHaveValue('S -> NOUN')
    showAnalyzer()
    expect(input()).toHaveValue('Keep this statement')
    expect(analyzeButton()).toBeDisabled()
    expect(testRequests()).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(analyzeButton()).toBeEnabled())
  })

  it('refresh loads the saved grammar and preserves manual text', async () => {
    const { user, fixtures, openSettings, showAnalyzer } = await renderAnalyzer()
    await replaceText(user, input(), 'Private draft')
    await openSettings()
    fixtures.state = analyzerState('S -> NUMBER')
    await user.click(screen.getByRole('button', { name: 'Refresh saved grammar' }))
    await waitFor(() => expect(grammarInput()).toHaveValue('S -> NUMBER'))
    showAnalyzer()
    expect(input()).toHaveValue('Private draft')
  })

  it.each([
    { grammar: '   ', message: 'The saved grammar is empty.' },
    { grammar: 'x'.repeat(12001), message: 'The saved grammar exceeds 12,000 characters.' },
  ])('explains unusable saved grammar without offering draft edits', async ({ grammar, message }) => {
    const { openSettings, showAnalyzer } = await renderAnalyzer(grammar)
    expect(screen.getByRole('alert')).toHaveTextContent(message)
    expect(analyzeButton()).toBeDisabled()
    await openSettings()
    expect(grammarInput()).toHaveAttribute('readonly')
    expect(screen.queryByRole('button', { name: 'Save grammar' })).not.toBeInTheDocument()
    showAnalyzer()
    expect(analyzeButton()).toBeDisabled()
    expect(testRequests()).toHaveLength(0)
  })

  it('applies raw handoffs once without running, approving or saving a test', async () => {
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
    expect(screen.getByText(/Synthetic example copied unchanged/)).toBeVisible()
    expect(testRequests()).toHaveLength(0)
  })

  it('preserves oversized source and prevents a recorded test', async () => {
    const { rerender } = await renderAnalyzer()
    const text = 'x'.repeat(4001)
    rerender(<FrancAnalyzer active incomingText={{ id: 1, text, kind: 'dictionary' }} onUseText={onUseText} />)
    expect(input()).toHaveValue(text)
    expect(screen.getByRole('alert')).toHaveTextContent('exceeds 4,000 characters')
    expect(analyzeButton()).toBeDisabled()
    expect(testRequests()).toHaveLength(0)
  })

  it('allows an empty-input test with real epsilon results', async () => {
    const { user } = await renderAnalyzer('S -> epsilon')
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(recordedTest({
      text: '', grammar_source: 'S -> epsilon', lexical: { tokens: [], verb_phrases: [], code_mixed_spans: [], slang_expressions: [], statistics: lexicalStatistics() }, parse: manualParse().parse,
    })))
    await user.click(analyzeButton())
    expect(requestBody(testRequests()[0])).toMatchObject({ text: '', grammar: 'S -> epsilon' })
    expect(await screen.findByText('ACCEPT', { exact: true })).toBeVisible()
    expect(screen.getByLabelText('Analyzed source text')).toHaveTextContent('(empty input)')
  })

  it('does not show stale success after a validation or recording failure', async () => {
    const { user } = await renderAnalyzer()
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(recordedTest()))
    await user.click(analyzeButton())
    await screen.findByRole('region', { name: 'Vocabulary result' })
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ detail: 'Cannot save recorded test.' }, 500))
    await user.click(analyzeButton())
    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot save recorded test.')
    expect(screen.queryByRole('region', { name: 'Vocabulary result' })).not.toBeInTheDocument()
  })

  it.each(['stop', 'text', 'refresh', 'navigate'])('ignores late response after %s without claiming saved tests were deleted', async (action) => {
    const { user, rerender, openSettings } = await renderAnalyzer()
    const pending = deferred<Response>()
    vi.mocked(fetch).mockReturnValueOnce(pending.promise)
    await user.click(analyzeButton())
    if (action === 'stop') {
      await user.click(screen.getByRole('button', { name: 'Stop waiting' }))
      expect(screen.getByText(/server may still finish and save this test/)).toBeVisible()
    }
    if (action === 'text') await replaceText(user, input(), 'Next input')
    if (action === 'refresh') {
      await openSettings()
      await user.click(screen.getByRole('button', { name: 'Refresh saved grammar' }))
    }
    if (action === 'navigate') rerender(<FrancAnalyzer active={false} onUseText={onUseText} />)
    expect(testRequests()[0]?.[1]?.signal?.aborted).toBe(true)
    await act(async () => pending.resolve(jsonResponse(recordedTest())))
    expect(screen.queryByRole('region', { name: 'Vocabulary result' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Analyzed source text')).not.toBeInTheDocument()
  })

  it('can move to Analysis while a test completes and refreshes totals once saved', async () => {
    const { user, fixtures, showAnalysis } = await renderAnalyzer()
    const pending = deferred<Response>()
    vi.mocked(fetch).mockReturnValueOnce(pending.promise)
    await user.click(analyzeButton())
    await showAnalysis()
    expect(testRequests()[0]?.[1]?.signal?.aborted).toBe(false)
    fixtures.report = retainedTestReport()
    await act(async () => pending.resolve(jsonResponse(recordedTest())))
    await waitFor(() => expect(screen.getByRole('group', { name: 'Tests recorded' })).toHaveTextContent('3'))
    expect(screen.getByLabelText('Analyzed source text')).toHaveTextContent('Mbom')
    expect(testRequests()).toHaveLength(1)
  })

  it('reloads retained totals after leaving the workspace without reusing transient details', async () => {
    const { user, fixtures, rerender, showAnalysis } = await renderAnalyzer()
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(recordedTest()))
    await user.click(analyzeButton())
    await screen.findByRole('region', { name: 'Vocabulary result' })
    rerender(<FrancAnalyzer active={false} onUseText={onUseText} />)
    fixtures.report = retainedTestReport()
    await showAnalysis()
    expect(screen.getByRole('group', { name: 'Tests recorded' })).toHaveTextContent('3')
    expect(screen.queryByLabelText('Analyzed source text')).not.toBeInTheDocument()
    expect(testRequests()).toHaveLength(1)
  })

  it('loads saved test details only when requested and never submits another test', async () => {
    const { user, fixtures, showAnalysis } = await renderAnalyzer()
    fixtures.report = retainedTestReport()
    await showAnalysis()
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(recordedTest({ text: 'Saved raw text' })))
    await user.click(screen.getByRole('button', { name: 'Inspect test 1' }))
    expect(await screen.findByLabelText('Analyzed source text')).toHaveTextContent('Saved raw text')
    expect(testRequests()).toHaveLength(0)
    expect(vi.mocked(fetch).mock.calls.at(-1)?.[0]).toBe(`/api/analyzer/tests/${recordedTest().id}`)
  })

  it('shows and retries a report load error without fabricating zeros', async () => {
    const { user, rerender, fixtures } = await renderAnalyzer()
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ detail: 'Cannot load recorded tests.' }, 503))
    rerender(<FrancAnalyzer active showAnalysis onUseText={onUseText} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot load recorded tests.')
    expect(screen.queryByRole('group', { name: 'Tests recorded' })).not.toBeInTheDocument()
    fixtures.report = retainedTestReport()
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('group', { name: 'Tests recorded' })).toHaveTextContent('3')
  })

  it('warns before unloading an unsubmitted draft', async () => {
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
