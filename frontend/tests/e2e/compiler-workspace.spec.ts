import { readFile } from 'node:fs/promises'
import { test, expect } from './fixtures'
import { courseworkState, entry, project } from '../fixtures'

test('compiler navigation replaces retired AI routes and exposes honest corpus gaps', async ({ page, api }, testInfo) => {
  await page.goto('/#assistant')
  await expect(page).toHaveURL(/#compiler$/)
  const navigation = page.getByRole('navigation', { name: 'Main navigation' })
  await expect(navigation.getByRole('link')).toHaveText([
    'Compiler lab', 'Collection', 'Dictionary', 'Synthetic examples', 'Document import', 'History', 'Workspace settings',
  ])
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Compiler lab')
  await expect(page.getByRole('tab', { name: 'Lexical analysis', exact: true })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByLabel('Sentence to analyze')).toBeInViewport()
  await expect(page.getByRole('button', { name: 'Analyze tokens', exact: true })).toBeInViewport({ ratio: 1 })
  await expect(page.getByRole('tabpanel')).toHaveCount(1)
  await page.screenshot({ path: testInfo.outputPath('assignment-lexical-analysis.png') })
  await page.getByRole('tab', { name: 'Data collection', exact: true }).click()
  await expect(page.getByText('No collected corpus in this project yet.', { exact: true })).toBeVisible()
  await page.getByText('Collection notes for the report', { exact: true }).click()
  await expect(page.getByRole('checkbox', { name: /We manually transcribed/ })).not.toBeChecked()
  await page.getByRole('tab', { name: 'Report & presentation', exact: true }).click()
  await expect(page.getByLabel('Group member 1')).toHaveValue('')
  await expect(page.getByRole('button', { name: /Ask AI|Translate|Send|dictat/i })).toHaveCount(0)
  expect(api.calls('/api/examples')).toHaveLength(0)
  expect(api.calls('/api/coursework').length).toBeGreaterThan(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('assignment tabs support keyboard navigation and preserve the sentence without computation', async ({ page, api }) => {
  await page.goto('/')
  const tabs = page.getByRole('tablist', { name: 'Assignment sections' })
  await expect(tabs.getByRole('tab')).toHaveCount(5)
  await page.getByLabel('Sentence to analyze').fill('  Synthetic\tinput, not fieldwork.  ')
  await tabs.getByRole('tab', { name: 'Lexical analysis', exact: true }).focus()
  await page.keyboard.press('ArrowRight')
  await expect(page.getByRole('tab', { name: 'Syntactic analysis', exact: true })).toBeFocused()
  await expect(page.getByLabel('Context-free grammar')).toBeVisible()
  await expect(page.getByLabel('Sentence to analyze')).not.toBeVisible()
  await page.keyboard.press('End')
  await expect(page.getByRole('tab', { name: 'Report & presentation', exact: true })).toBeFocused()
  await page.keyboard.press('ArrowRight')
  await expect(page.getByRole('tab', { name: 'Data collection', exact: true })).toBeFocused()
  await page.keyboard.press('ArrowLeft')
  await expect(page.getByRole('tab', { name: 'Report & presentation', exact: true })).toBeFocused()
  await page.keyboard.press('Home')
  await expect(page.getByRole('tab', { name: 'Data collection', exact: true })).toBeFocused()
  await page.getByRole('tab', { name: 'Parser tests', exact: true }).click()
  await expect(page.getByLabel('Manual parser test')).toHaveValue('  Synthetic\tinput, not fieldwork.  ')
  await expect(page.getByRole('tabpanel')).toHaveCount(1)
  expect(api.calls('/api/analyze')).toHaveLength(0)
  expect(api.calls('/api/coursework/analyze')).toHaveLength(0)
  expect(api.calls('/api/coursework/parse')).toHaveLength(0)
  expect(api.calls('/api/coursework/project')).toHaveLength(0)
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
  api.on('GET', '/api/coursework', async (route, request) => {
    const other = request.headers['x-mboa-project'] === 'isolated-project'
    await route.fulfill({ json: courseworkState(project({ grammar: other ? 'S -> VERB' : 'S -> NOUN' })) })
  })
  await page.goto('/')
  await page.getByLabel('Sentence to analyze').fill('Unsaved private text')
  await page.getByRole('tab', { name: 'Report & presentation', exact: true }).click()
  await page.getByLabel('Group member 1').fill('Unsaved member')
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByLabel('Active project').selectOption('isolated-project')
  await expect(page.getByRole('tab', { name: 'Lexical analysis', exact: true })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByLabel('Sentence to analyze')).toHaveValue('')
  await page.getByRole('tab', { name: 'Syntactic analysis', exact: true }).click()
  await expect(page.getByLabel('Context-free grammar')).toHaveValue('S -> VERB')
  await page.getByRole('tab', { name: 'Report & presentation', exact: true }).click()
  await expect(page.getByLabel('Group member 1')).toHaveValue('')
  expect(api.calls('/api/coursework').at(-1)?.headers['x-mboa-project']).toBe('isolated-project')
  expect(api.calls('/api/coursework/project')).toHaveLength(0)
})
