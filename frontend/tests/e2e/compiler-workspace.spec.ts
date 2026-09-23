import { readFile } from 'node:fs/promises'
import { test, expect } from './fixtures'
import { analyzerState, entry } from '../fixtures'
import { openGrammarSettings } from '../browserGrammar'

test('Franc Analyzer replaces the lab with one visible analysis action and no collection or report sections', async ({ page, api }, testInfo) => {
  await page.goto('/#assistant')
  await expect(page).toHaveURL(/#compiler$/)
  const navigation = page.getByRole('navigation', { name: 'Main navigation' })
  await expect(navigation.getByRole('link')).toHaveText([
    'Franc Analyzer', 'Analysis', 'Collection', 'Dictionary', 'Synthetic examples',
  ])
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Franc Analyzer')
  await expect(page.getByLabel('Statement to analyze')).toBeInViewport()
  await expect(page.getByRole('button', { name: 'Analyze', exact: true })).toBeInViewport({ ratio: 1 })
  await expect(page.getByRole('button', { name: 'Analyze', exact: true })).toHaveCount(1)
  await expect(page.getByRole('tab')).toHaveCount(0)
  await expect(page.getByRole('tabpanel')).toHaveCount(0)
  await expect(page.getByText('Grammar settings', { exact: true })).toHaveCount(0)
  await expect(page.getByLabel('Context-free grammar')).toHaveCount(0)
  await page.screenshot({ path: testInfo.outputPath('franc-analyzer.png') })
  await expect(page.getByRole('heading', { name: /Data collection|Report|Presentation/i })).toHaveCount(0)
  await expect(page.getByLabel(/Group member|Linguistic discussion|Collection method/)).toHaveCount(0)
  await expect(page.getByRole('button', { name: /Add entry|Upload screenshot|Download coursework|Ask AI|Translate/i })).toHaveCount(0)
  expect(api.calls('/api/examples')).toHaveLength(0)
  expect(api.calls('/api/analyzer')).toHaveLength(1)
  expect(api.calls('/api/analyzer/analyze')).toHaveLength(0)
  expect(api.calls('/api/coursework')).toHaveLength(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

for (const retired of ['history', 'settings', 'imports', 'lab-collection', 'lab-submission']) {
  test(`retired ${retired} route returns to Franc Analyzer without loading removed-screen data`, async ({ page, api }) => {
    await page.goto(`/#${retired}`)
    await expect(page).toHaveURL(/#compiler$/)
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Franc Analyzer')
    await expect(page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link')).toHaveCount(5)
    await expect(page.getByRole('heading', { name: /History|Workspace settings|Document import/ })).toHaveCount(0)
    expect(api.calls('/api/workspace/history')).toHaveLength(0)
    expect(api.calls('/api/workspace/revisions')).toHaveLength(0)
    expect(api.calls('/api/workspace/backups')).toHaveLength(0)
    expect(api.calls('/api/imports/preview')).toHaveLength(0)
    expect(api.calls('/api/auth/profile')).toHaveLength(0)
    expect(api.calls('/api/coursework/export')).toHaveLength(0)
    await expect(page.getByRole('link', { name: 'Import a transcript' })).toHaveCount(0)
    await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Collection', exact: true }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Collection' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Import a document' })).toHaveCount(0)
  })
}

test('grammar controls remain keyboard accessible without losing input or computing automatically', async ({ page, api }) => {
  await page.goto('/')
  const raw = '  Synthetic\tinput, not fieldwork.  '
  await page.getByLabel('Statement to analyze').fill(raw)
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Analysis', exact: true }).click()
  const settings = page.getByText('Grammar settings', { exact: true })
  await settings.focus()
  await page.keyboard.press('Enter')
  await expect(page.getByLabel('Context-free grammar')).toBeVisible()
  await page.getByLabel('Context-free grammar').fill('S -> VERB')
  await settings.focus()
  await page.keyboard.press('Enter')
  await expect(page.getByLabel('Context-free grammar')).not.toBeVisible()
  await page.getByRole('link', { name: 'Back to Franc Analyzer' }).click()
  await expect(page.getByLabel('Statement to analyze')).toHaveValue(raw)
  await expect(page.getByLabel('Context-free grammar')).toHaveCount(0)
  await openGrammarSettings(page)
  await expect(page.getByLabel('Context-free grammar')).toHaveValue('S -> VERB')
  expect(api.calls('/api/analyzer/analyze')).toHaveLength(0)
  expect(api.calls('/api/analyzer/grammar')).toHaveLength(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('collection export preserves legacy categories and only includes displayed review metadata', async ({ page, api }) => {
  const approved = entry({ text: 'Approved customer greeting', notes: 'Source reviewed', category: 'Customer Service' })
  const draft = entry({ id: 'draft-id', text: 'Pending delivery phrase', review_status: 'unreviewed', category: 'Logistics' })
  api.entries = [approved, draft]
  await page.goto('/#collection')
  await expect(page.getByRole('heading', { name: approved.text, exact: true })).toBeVisible()
  await page.getByLabel('Filter by review status').selectOption('approved')
  await expect(page.getByRole('heading', { name: draft.text, exact: true })).toHaveCount(0)
  const event = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export results (JSON)' }).click()
  const download = await event
  expect(download.suggestedFilename()).toBe('mboa-collection.json')
  expect(await download.failure()).toBeNull()
  const path = await download.path()
  if (!path) throw new Error('Expected a real downloaded JSON file.')
  const data = JSON.parse(await readFile(path, 'utf8'))
  expect(data.entries).toEqual([approved])
  expect(Number.isNaN(Date.parse(data.exported_at))).toBe(false)
  expect(api.calls('/api/dataset', 'POST')).toHaveLength(0)
})

test('authenticated project selection remounts grammar, manual input and source context', async ({ page, api }) => {
  api.reply('GET', '/api/workspace/projects', {
    projects: [{ id: 'default', name: 'General', created_at: '' }, { id: 'isolated-project', name: 'Separate project', created_at: '' }],
    default_project_id: 'default',
  })
  api.on('GET', '/api/analyzer', async (route, request) => {
    const other = request.headers['x-mboa-project'] === 'isolated-project'
    await route.fulfill({ json: analyzerState(other ? 'S -> VERB' : 'S -> NOUN') })
  })
  await page.goto('/')
  await page.getByLabel('Statement to analyze').fill('Unsaved private text')
  await openGrammarSettings(page)
  await page.getByLabel('Context-free grammar').fill('S -> NUMBER')
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByLabel('Active project').selectOption('isolated-project')
  await expect(page.getByRole('heading', { name: 'No completed analysis' })).toBeVisible()
  await openGrammarSettings(page)
  await expect(page.getByLabel('Context-free grammar')).toHaveValue('S -> VERB')
  await page.getByRole('link', { name: 'Back to Franc Analyzer' }).click()
  await expect(page.getByLabel('Statement to analyze')).toHaveValue('')
  await expect(page.getByLabel('Context-free grammar')).toHaveCount(0)
  await expect(page.getByLabel('Group member 1')).toHaveCount(0)
  expect(api.calls('/api/analyzer').at(-1)?.headers['x-mboa-project']).toBe('isolated-project')
  expect(api.calls('/api/analyzer/grammar')).toHaveLength(0)
})
