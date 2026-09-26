import type { Dataset } from '../../src/types'
import type { TestReport } from '../../src/analyzerTypes'
import { openGrammarSettings } from '../browserGrammar'
import { expect, test } from './fixtures'
import { analyzePublicInput, origin, protectPublicContext, publicHeaders, readOnlyOwnership } from './publicWorkflows'

const raw = '  mola shiba sec zqxyl\t'
test.use({ seed: {
  grammar: 'S -> NOUN VERB ADJECTIVE UNKNOWN | AMBIGUOUS',
  entries: [{ text: raw, entry_type: 'Sentence', french_gloss: 'Exemple de test manuel' }],
} })

test('independent public visitors share immutable tests, read-only Collection and classified CSV vocabulary', async ({ page, browser }, testInfo) => {
  await protectPublicContext(page.context())
  await page.goto('/')
  const before: Dataset = await (await page.request.get('/api/dataset')).json()
  expect(before.total).toBe(1)
  const entry = before.entries[0]
  if (!entry) throw new Error('The isolated fixture must have its seeded Collection record.')
  expect(entry.ownership).toEqual(readOnlyOwnership)
  const saved = await analyzePublicInput(page, raw)
  expect(saved.lexical.tokens.map((token) => token.category)).toEqual(['NOUN', 'VERB', 'ADJECTIVE', 'UNKNOWN'])
  expect(saved.approval).toEqual({ basis: 'no_unknown_tokens', accepted: false, unknown_count: 1 })
  expect(saved.parse.accepted).toBe(true)
  await expect(page.getByRole('group', { name: 'Vocabulary approval', exact: true })).toContainText('REJECT')
  expect(await page.getByLabel('Analyzed source text').textContent()).toBe(raw)
  const otherContext = await browser.newContext({ baseURL: origin, viewport: page.viewportSize() ?? undefined })
  try {
    await protectPublicContext(otherContext)
    const other = await otherContext.newPage()
    await other.goto('/#collection')
    const card = other.getByRole('article').filter({ has: other.getByRole('heading', { name: raw.trim(), exact: true }) })
    await expect(card).toBeVisible()
    await expect(other.getByLabel('Registered users')).toHaveCount(0)
    await expect(other.getByLabel('Active project')).toHaveCount(0)
    await expect(other.getByRole('button', { name: /Add entry|Edit expression|Delete expression/ })).toHaveCount(0)
    await card.getByRole('button', { name: /^View expression:/ }).click()
    const viewer = other.getByRole('dialog', { name: 'View collection entry', exact: true })
    await expect(viewer.getByRole('textbox', { name: 'Expression', exact: true })).toHaveValue(raw)
    await expect(viewer.getByRole('textbox', { name: 'Expression', exact: true })).not.toBeEditable()
    await expect(viewer.getByRole('button', { name: /Save|Record audio|Remove attachment/ })).toHaveCount(0)
    await viewer.getByRole('button', { name: 'Done', exact: true }).click()
    const headers = await publicHeaders(other.request)
    expect((await other.request.patch(`/api/dataset/${entry.id}`, { headers, data: { notes: 'Forbidden edit' } })).status()).toBe(403)
    expect((await other.request.delete(`/api/dataset/${entry.id}`, { headers })).status()).toBe(403)
    expect(await (await other.request.get(`/api/analyzer/tests/${saved.id}`)).json()).toEqual(saved)
    await openGrammarSettings(other)
    await expect(other.getByLabel('Context-free grammar')).not.toBeEditable()
    await expect(other.getByRole('button', { name: 'Save grammar', exact: true })).toHaveCount(0)
    expect((await other.request.put('/api/analyzer/grammar', { headers, data: { grammar: 'S -> AMBIGUOUS' } })).status()).toBe(403)
    await expect(other.getByRole('group', { name: 'Tests recorded', exact: true })).toContainText('1')
    const second = await analyzePublicInput(other, 'mbindi')
    expect(second.approval.accepted).toBe(true)
    expect(second.parse.accepted).toBe(true)
    await expect(other.getByRole('region', { name: 'Lexical tokens in source order' })).toContainText('AMBIGUOUS')
    await other.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Dictionary', exact: true }).click()
    await other.getByRole('searchbox', { name: 'Search reference dictionary' }).fill('shiba')
    const dictionaryCard = other.getByRole('article').filter({ has: other.getByRole('heading', { name: 'shiba', exact: true }) })
    await expect(dictionaryCard.getByText('verb', { exact: true })).toBeVisible()
    await expect(dictionaryCard.getByText(/full_lexicon_classified.csv:/)).toBeVisible()
    expect((await (await other.request.get('/api/dictionary')).json()).total).toBe(938)
    expect(await other.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await other.screenshot({ path: testInfo.outputPath('public-dictionary.png'), fullPage: true })
  } finally {
    await otherContext.close()
  }
  await page.reload()
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Analysis', exact: true }).click()
  const report: TestReport = await (await page.request.get('/api/analyzer/tests')).json()
  expect(report.summary).toMatchObject({ total: 2, accepted: 1, rejected: 1 })
  await expect(page.getByRole('group', { name: 'Tests recorded', exact: true })).toContainText('2')
  await page.getByRole('button', { name: 'Inspect test 1', exact: true }).click()
  expect(await page.getByLabel('Analyzed source text').textContent()).toBe(raw)
  expect(await (await page.request.get('/api/dataset')).json()).toEqual(before)
  expect(await (await page.request.get(`/api/analyzer/tests/${saved.id}`)).json()).toEqual(saved)
})
