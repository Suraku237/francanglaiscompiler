import { execFileSync } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { RecordedTest, TestReport } from '../../src/analyzerTypes'
import { openGrammarSettings } from '../browserGrammar'
import { expect, test } from './fixtures'
import { publicHeaders, readOnlyOwnership } from './publicWorkflows'

const root = fileURLToPath(new URL('../../../', import.meta.url))
const python = process.platform === 'win32' ? join(root, '.venv', 'Scripts', 'python.exe') : 'python'
const fixture: {
  grammar: string
  cases: { text: string; categories: string[]; accepted: boolean; reason: string }[]
} = JSON.parse(execFileSync(python, ['-c', [
  'import json',
  'from dataclasses import asdict',
  'from compiler.parser.yaounde import GRAMMAR',
  'from compiler.tests.yaounde_cases import CORPUS_CASES',
  'print(json.dumps({"grammar": GRAMMAR, "cases": [asdict(case) for case in CORPUS_CASES]}))',
].join('\n')], { cwd: root, encoding: 'utf8', timeout: 30000 }))

test.use({ seed: { corpus: 'yaounde' } })

test('the read-only collected-sentence CFG records all twelve exact inputs with visible transformations and honest rejections', async ({ page, context }, testInfo) => {
  await context.route(/^https?:\/\/(?!127\.0\.0\.1:4190\/).*/, (route) => route.abort('blockedbyclient'))
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/')
  await expect(page.getByLabel('Statement to analyze')).toBeVisible()
  const headers = await publicHeaders(page.request)
  expect(fixture.cases).toHaveLength(12)
  const before = await (await page.request.get('/api/dataset')).json()
  expect(before.total).toBe(12)
  const state = await (await page.request.get('/api/analyzer')).json()
  expect(state.grammar).toBe(fixture.grammar.trim())
  expect(state.grammar_ownership).toEqual(readOnlyOwnership)
  await openGrammarSettings(page)
  await expect(page.getByLabel('Context-free grammar')).toHaveValue(state.grammar)
  await expect(page.getByLabel('Context-free grammar')).not.toBeEditable()
  await expect(page.getByRole('button', { name: 'Save grammar', exact: true })).toHaveCount(0)
  await page.getByRole('link', { name: 'Back to Franc Analyzer', exact: true }).click()
  const first = fixture.cases[0]
  if (!first) throw new Error('The corpus fixture must contain its first sentence.')
  await page.getByLabel('Statement to analyze').fill(first.text)
  const saving = page.waitForResponse((response) => response.url().endsWith('/api/analyzer/tests') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Analyze', exact: true }).click()
  const saved: RecordedTest[] = [await (await saving).json()]
  await expect(page.getByRole('group', { name: 'Vocabulary approval', exact: true })).toContainText('ACCEPT')
  for (const row of fixture.cases.slice(1)) {
    const response = await page.request.post('/api/analyzer/tests', {
      headers, data: { request_id: randomUUID(), text: row.text, grammar: state.grammar },
    })
    expect(response.status(), await response.text()).toBe(200)
    saved.push(await response.json())
  }
  for (const [index, row] of fixture.cases.entries()) {
    const record = saved[index]
    expect(record?.text).toBe(row.text)
    expect(record?.grammar_source).toBe(state.grammar)
    expect(record?.ownership).toEqual(readOnlyOwnership)
    expect(record?.lexical.tokens.map((token) => token.category)).toEqual(row.categories)
    expect(record?.parse.accepted, row.reason).toBe(row.accepted)
    expect(record?.approval.accepted).toBe(row.accepted)
    expect(record?.grammar.is_ll1).toBe(true)
    expect(record?.grammar.conflicts).toEqual([])
    expect(record?.metadata.matching_entries).toBe(1)
  }
  const report: TestReport = await (await page.request.get('/api/analyzer/tests')).json()
  expect(report.summary).toMatchObject({ total: 12, accepted: 10, rejected: 2 })
  expect(report.grammar_summary).toMatchObject({ total: 12, accepted: 10, rejected: 2 })
  expect(await (await page.request.get('/api/dataset')).json()).toEqual(before)
  const probe = await page.request.post('/api/analyze', { headers, data: { text: 'Je go au march\u00e9.' } })
  expect((await probe.json()).code_mixed_spans).toEqual(['Je ... go', 'go ... au'])

  await page.getByRole('link', { name: 'View detailed analysis', exact: true }).click()
  await expect(page.getByRole('group', { name: 'Tests recorded', exact: true })).toContainText('12')
  await expect(page.getByRole('group', { name: 'Grammar matches', exact: true })).toContainText('10')
  await expect(page.getByRole('group', { name: 'Grammar mismatches', exact: true })).toContainText('2')
  await page.getByRole('button', { name: 'Inspect test 2', exact: true }).click()
  const selected = page.getByRole('region', { name: 'Analyzed sentence or word', exact: true })
  await selected.getByText('Token details for this test', { exact: true }).click()
  await expect(selected.getByText('je ... go', { exact: true })).toBeVisible()
  await selected.getByText('Saved grammar, transformations & FIRST/FOLLOW', { exact: true }).click()
  await expect(selected.getByRole('region', { name: 'Computed FIRST and FOLLOW sets', exact: true })).toBeVisible()
  await selected.getByText('eliminate direct left recursion', { exact: false }).click()
  await expect(selected.getByText(/Replace Nominal -> Nominal alpha/)).toBeVisible()
  await expect(selected.getByRole('region', { name: 'LL(1) predictive parsing table, scroll horizontally', exact: true })).toBeVisible()
  for (const [index, row] of fixture.cases.entries()) {
    if (row.accepted) continue
    await page.getByRole('button', { name: `Inspect test ${index + 1}`, exact: true }).click()
    await expect(page.getByLabel('Analyzed source text')).toHaveText(row.text)
    await expect(selected.getByRole('group', { name: 'Vocabulary approval', exact: true })).toContainText('REJECT')
    await selected.getByText('Parser trace for this input', { exact: true }).click()
    await expect(selected.getByRole('paragraph').filter({ hasText: /lookahead UNKNOWN at token 6/ })).toBeVisible()
    await expect(selected.getByRole('cell', { name: /Reject: .*lookahead UNKNOWN at token 6/ })).toBeVisible()
  }
  await selected.getByRole('heading', { name: 'Analyzed sentence or word', exact: true }).scrollIntoViewIfNeeded()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('collected-grammar-rejection.png') })
  await page.reload()
  await openGrammarSettings(page)
  await expect(page.getByLabel('Context-free grammar')).toHaveValue(fixture.grammar.trim())
  const retained: TestReport = await (await page.request.get('/api/analyzer/tests')).json()
  expect(retained).toEqual(report)
  expect(await (await page.request.get('/api/dataset')).json()).toEqual(before)
  expect(errors).toEqual([])
})
