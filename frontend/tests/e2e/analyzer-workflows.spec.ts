import { test, expect } from './fixtures'
import { analyzerState, lexicalStatistics, manualParse, ownership, recordedTest, retainedTestReport, testReport, tokenAnalysisResult } from '../fixtures'
import { openGrammarSettings } from '../browserGrammar'
import type { RecordedTest } from '../../src/analyzerTypes'

test('Franc Analyzer classifies every word directly while Analysis retains all-test statistics', async ({ page, api }, testInfo) => {
  const input = tokenAnalysisResult()
  const saved = recordedTest({ text: input.text, lexical: input.lexical, parse: input.parse })
  api.analyzer = analyzerState('S -> VERB')
  api.on('POST', '/api/analyzer/tests', async (route) => {
    api.testReport = retainedTestReport()
    await route.fulfill({ json: saved })
  })
  await page.goto('/')
  await page.getByLabel('Statement to analyze').fill(saved.text)
  await openGrammarSettings(page)
  await expect(page.getByLabel('Context-free grammar')).toHaveValue('S -> VERB')
  await expect(page.getByLabel('Context-free grammar')).not.toBeEditable()
  await page.getByRole('link', { name: 'Back to Franc Analyzer' }).click()
  await page.getByRole('button', { name: 'Analyze', exact: true }).click()
  const verdict = page.getByRole('region', { name: 'Vocabulary result' })
  await expect(verdict.getByText('REJECT', { exact: true })).toBeVisible()
  expect(await verdict.getByLabel('Analyzed source text').textContent()).toBe(saved.text)
  await expect(verdict.getByRole('region', { name: 'Lexical tokens in source order' }).getByRole('row')).toHaveText([
    '#Observed textLexer category', '1veuxVERB', '2VEUXVERB', '3+UNKNOWN', '4+UNKNOWN',
  ])
  await expect(page.getByRole('heading', { name: 'Test statistics' })).toHaveCount(0)
  await expect(page.getByText('Grammar settings', { exact: true })).toHaveCount(0)
  await verdict.scrollIntoViewIfNeeded()
  await page.screenshot({ path: testInfo.outputPath('direct-word-classifications.png') })
  await page.getByRole('link', { name: 'View detailed analysis' }).click()
  await expect(page).toHaveTitle('Analysis — Camfranglais Compiler')
  const stats = page.getByRole('region', { name: 'Test statistics' })
  await expect(stats.getByRole('group', { name: 'Tests recorded', exact: true })).toContainText('3')
  await expect(stats.getByRole('group', { name: 'Accepted', exact: true })).toContainText('2')
  await expect(stats.getByRole('group', { name: 'Rejected', exact: true })).toContainText('1')
  await expect(stats.getByRole('group', { name: 'Acceptance rate' })).toContainText('66.7%')
  await expect(stats.getByRole('region', { name: 'Raw token frequency counts' }).getByRole('row')).toHaveText(['TermCount', 'veux2', '+2', 'taxi2', 'VEUX1'])
  await expect(stats.getByRole('region', { name: 'Normalized token frequency counts' }).getByRole('row')).toHaveText(['TermCount', 'veux3', '+2', 'taxi2'])
  await expect(stats.getByRole('region', { name: 'Unknown-word review counts' }).getByRole('row')).toHaveText(['FormObserved spellingsOccurrencesTests affected', '++21'])
  await stats.scrollIntoViewIfNeeded()
  await page.screenshot({ path: testInfo.outputPath('all-test-statistics.png'), fullPage: true })
  const selected = page.getByRole('region', { name: 'Analyzed sentence or word' })
  await selected.getByText('Token details for this test', { exact: true }).click()
  await expect(selected.getByText('4 tokens · 2 distinct forms', { exact: true })).toBeVisible()
  await selected.getByText('Parser trace for this input', { exact: true }).click()
  await expect(selected.getByRole('region', { name: 'Table-driven parser step trace' })).toBeVisible()
  await selected.getByText('Saved grammar, transformations & FIRST/FOLLOW', { exact: true }).click()
  await expect(selected.getByRole('region', { name: 'Computed FIRST and FOLLOW sets' })).toBeVisible()
  expect(api.calls('/api/analyzer/tests', 'POST')).toHaveLength(1)
  expect(api.calls('/api/analyzer/tests', 'POST')[0]?.body).toEqual({ request_id: expect.any(String), text: saved.text, grammar: 'S -> VERB' })
  expect(api.calls('/api/analyzer/analyze')).toHaveLength(0)
  expect(api.calls('/api/dataset', 'POST')).toHaveLength(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('saved tests survive reload and can be inspected or handed off without another computation', async ({ page, api }) => {
  api.testReport = retainedTestReport()
  const saved = recordedTest({ text: '  veux VEUX + +\t', grammar_source: 'S -> NOUN' })
  api.reply('GET', `/api/analyzer/tests/${saved.id}`, saved)
  await page.goto('/#analysis')
  await expect(page.getByRole('group', { name: 'Tests recorded', exact: true })).toContainText('3')
  await page.reload()
  await expect(page.getByRole('group', { name: 'Tests recorded', exact: true })).toContainText('3')
  await expect(page.getByLabel('Analyzed source text')).toHaveCount(0)
  await page.getByRole('button', { name: 'Inspect test 1', exact: true }).click()
  expect(await page.getByLabel('Analyzed source text').textContent()).toBe(saved.text)
  await page.getByRole('button', { name: 'Use as analyzer input' }).click()
  await expect(page).toHaveURL(/#compiler$/)
  await expect(page.getByLabel('Statement to analyze')).toHaveValue(saved.text)
  await expect(page.getByLabel('Statement to analyze')).toBeFocused()
  await expect(page.getByRole('heading', { name: 'Vocabulary result' })).toHaveCount(0)
  expect(api.calls('/api/analyzer/tests', 'POST')).toHaveLength(0)
  expect(api.calls('/api/dataset', 'POST')).toHaveLength(0)
})

test('test-list pagination never narrows the dashboard aggregate to one page', async ({ page, api }) => {
  const base = retainedTestReport()
  const sample = base.tests[0]
  if (!sample) throw new Error('The synthetic report must contain a test.')
  const tests = Array.from({ length: 26 }, (_, index) => ({ ...sample, id: `test-${index}`, text: `Synthetic test ${index + 1}` }))
  api.on('GET', '/api/analyzer/tests', async (route, request) => {
    const offset = Number(request.url.searchParams.get('offset'))
    await route.fulfill({ json: { ...base, summary: { total: 26, accepted: 25, rejected: 1, acceptance_rate: 2500 / 26 }, tests: tests.slice(offset, offset + 25), offset, limit: 25 } })
  })
  await page.goto('/#analysis')
  await expect(page.getByText('1-25 of 26 tests / statistics include all 26', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Next tests' }).click()
  await expect(page.getByText('26-26 of 26 tests / statistics include all 26', { exact: true })).toBeVisible()
  await expect(page.getByRole('group', { name: 'Tests recorded', exact: true })).toContainText('26')
  await expect(page.getByRole('button', { name: 'Next tests' })).toBeDisabled()
  await expect(page.getByRole('region', { name: 'Normalized token frequency counts' }).getByRole('row')).toHaveText(['TermCount', 'veux3', '+2', 'taxi2'])
  await page.getByRole('button', { name: 'Previous tests' }).click()
  await expect(page.getByText('1-25 of 26 tests / statistics include all 26', { exact: true })).toBeVisible()
  expect(api.calls('/api/analyzer/tests', 'POST')).toHaveLength(0)
})

test('complete frequency lists and long words stay readable without page overflow', async ({ page, api }) => {
  const unknown = [
    ...Array.from({ length: 119 }, (_, index) => ({
      token: `lexeme${String.fromCharCode(97 + Math.floor(index / 26), 97 + index % 26)}`, count: 1,
    })),
    { token: 'x'.repeat(4000), count: 1 },
  ]
  const frequencies = [{ token: 'je', count: 1 }, ...unknown]
  const total = frequencies.length
  api.testReport = testReport({
    summary: { total, accepted: 1, rejected: total - 1, acceptance_rate: 100 / total },
    grammar_summary: { total, accepted: 0, rejected: total, acceptance_rate: 0 },
    statistics: {
      ...lexicalStatistics({
        total_tokens: total, frequencies, unknown_tokens: unknown,
        category_counts: { FRENCH_FUNCTION_WORD: 1, UNKNOWN: unknown.length },
      }),
      raw_frequencies: frequencies, normalized_frequencies: frequencies,
    },
    unknown_review: unknown.map((row) => ({ ...row, tests: 1, forms: [row.token] })),
    topic_counts: { 'Not recorded': total }, language_counts: { 'Not recorded': total },
    tests: frequencies.slice(0, 25).map((row, index) => ({
      id: `large-vocabulary-test-${index}`, created_at: '2026-09-23T12:00:00Z',
      ownership: ownership(),
      text: row.token, accepted: index === 0, error: index === 0 ? null : '1 UNKNOWN token.', token_count: 1,
      unknown_count: index === 0 ? 0 : 1, grammar_accepted: false, grammar_error: 'No matching grammar rule.',
    })),
  })
  await page.goto('/#analysis')
  await expect(page.getByRole('group', { name: 'Tests recorded', exact: true })).toContainText('121')
  for (const name of ['Raw token frequency counts', 'Normalized token frequency counts']) {
    const counts = page.getByRole('region', { name, exact: true })
    await expect(counts.getByRole('row')).toHaveCount(122)
    await expect(counts.getByRole('row').last()).toHaveText(`${'x'.repeat(4000)}1`)
    expect(await counts.evaluate((node) => node.scrollHeight > node.clientHeight)).toBe(true)
  }
  await expect(page.getByRole('region', { name: 'Unknown-word review counts' }).getByRole('row')).toHaveCount(121)
  await expect(page.getByRole('region', { name: 'Grammatical category frequency counts' })).toContainText('FRENCH_FUNCTION_WORD')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  expect(api.calls('/api/analyzer/tests', 'POST')).toHaveLength(0)
})

test('saved grammar stays read-only and explicit refresh preserves original recorded statistics', async ({ page, api }) => {
  api.testReport = retainedTestReport()
  await page.goto('/')
  await openGrammarSettings(page)
  await expect(page.getByLabel('Context-free grammar')).not.toBeEditable()
  await expect(page.getByRole('button', { name: 'Save grammar', exact: true })).toHaveCount(0)
  api.analyzer = analyzerState('S -> VERB')
  await page.getByRole('button', { name: 'Refresh saved grammar', exact: true }).click()
  await expect(page.getByLabel('Context-free grammar')).toHaveValue('S -> VERB')
  await expect(page.getByText('Using saved grammar', { exact: true })).toBeVisible()
  await expect(page.getByRole('group', { name: 'Tests recorded', exact: true })).toContainText('3')
  await page.reload()
  await openGrammarSettings(page)
  await expect(page.getByLabel('Context-free grammar')).toHaveValue('S -> VERB')
  await expect(page.getByRole('group', { name: 'Tests recorded', exact: true })).toContainText('3')
  await expect(page.getByRole('button', { name: /Download coursework|Save project|Upload screenshot/ })).toHaveCount(0)
  expect(api.calls('/api/analyzer/tests', 'POST')).toHaveLength(0)
  expect(api.calls('/api/analyzer/grammar')).toHaveLength(0)
})

test('failed recording and failed statistics reads remain explicit without success-shaped fallback', async ({ page, api }) => {
  api.reply('POST', '/api/analyzer/tests', { detail: 'Cannot save recorded test.' }, 500)
  await page.goto('/')
  await page.getByLabel('Statement to analyze').fill('Mbom')
  await page.getByRole('button', { name: 'Analyze', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Cannot save recorded test.')
  await expect(page.getByRole('region', { name: 'Vocabulary result' })).toHaveCount(0)
  api.reply('GET', '/api/analyzer/tests', { detail: 'Cannot read saved statistics.' }, 503)
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Analysis', exact: true }).click()
  const error = page.getByRole('alert').filter({ hasText: 'Cannot read saved statistics.' })
  await expect(error).toBeVisible()
  await expect(page.getByRole('group', { name: 'Tests recorded', exact: true })).toHaveCount(0)
  api.reply('GET', '/api/analyzer/tests', testReport())
  await error.getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByRole('heading', { name: 'No saved tests yet' })).toBeVisible()
  expect(api.calls('/api/analyzer/tests', 'POST')).toHaveLength(1)
})

test('a stale saved grammar requires explicit reload before another test can be submitted', async ({ page, api }) => {
  api.reply('POST', '/api/analyzer/tests', { detail: 'The saved grammar changed. Reload the saved grammar.' }, 409)
  await page.goto('/')
  await page.getByLabel('Statement to analyze').fill('  Veux\t')
  await page.getByRole('button', { name: 'Analyze', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Reload the saved grammar')
  await expect(page.getByRole('button', { name: 'Analyze', exact: true })).toBeDisabled()
  await expect(page.getByLabel('Statement to analyze')).toHaveValue('  Veux\t')
  expect(api.calls('/api/analyzer')).toHaveLength(1)
  expect(api.calls('/api/analyzer/tests', 'POST')).toHaveLength(1)
  api.analyzer = analyzerState('S -> VERB')
  await page.getByRole('button', { name: 'Reload saved grammar', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Analyze', exact: true })).toBeEnabled()
  expect(api.calls('/api/analyzer/tests', 'POST')).toHaveLength(1)
  const saved = recordedTest({ text: '  Veux\t', grammar_source: 'S -> VERB' })
  api.reply('POST', '/api/analyzer/tests', saved)
  await page.getByRole('button', { name: 'Analyze', exact: true }).click()
  await expect(page.getByRole('region', { name: 'Vocabulary result', exact: true })).toBeVisible()
  expect(api.calls('/api/analyzer/tests', 'POST')[1]?.body).toEqual({ request_id: expect.any(String), text: saved.text, grammar: 'S -> VERB' })
  expect(api.calls('/api/analyzer/grammar')).toHaveLength(0)
})

test('empty input is a real saved epsilon test rather than a fabricated empty dashboard', async ({ page, api }) => {
  const saved: RecordedTest = recordedTest({
    text: '', grammar_source: 'S -> epsilon',
    lexical: { tokens: [], code_mixed_spans: [], verb_phrases: [], slang_expressions: [], statistics: lexicalStatistics() },
    parse: manualParse().parse,
  })
  api.analyzer = analyzerState('S -> epsilon')
  api.on('POST', '/api/analyzer/tests', async (route) => {
    api.testReport = testReport({
      summary: { total: 1, accepted: 1, rejected: 0, acceptance_rate: 100 },
      tests: [{ id: saved.id, ownership: saved.ownership, created_at: saved.created_at, text: '', accepted: true, error: null, token_count: 0, unknown_count: 0, grammar_accepted: true, grammar_error: null }],
      topic_counts: { 'Not recorded': 1 }, language_counts: { 'Not recorded': 1 },
    })
    await route.fulfill({ json: saved })
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'Analyze', exact: true }).click()
  await expect(page.getByText('ACCEPT', { exact: true })).toBeVisible()
  await expect(page.getByLabel('Analyzed source text')).toHaveText('(empty input)')
  await expect(page.getByText('No lexical tokens. The parser will see only $.')).toBeVisible()
  await page.getByRole('link', { name: 'View detailed analysis' }).click()
  await expect(page.getByRole('group', { name: 'Tests recorded', exact: true })).toContainText('1')
  await expect(page.getByRole('group', { name: 'Acceptance rate' })).toContainText('100%')
  await expect(page.getByRole('heading', { name: 'No saved tests yet' })).toHaveCount(0)
})
