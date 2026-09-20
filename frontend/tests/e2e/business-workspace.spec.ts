import { readFile } from 'node:fs/promises'
import { test, expect } from './fixtures'
import { entry, health } from '../fixtures'

test('business navigation excludes school features and retired practice links do not fetch their data', async ({ page, api }) => {
  api.health = health(false)
  await page.goto('/#examples')
  await expect(page).toHaveURL(/#translator$/)
  const navigation = page.getByRole('navigation', { name: 'Main navigation' })
  await expect(navigation.getByRole('link')).toHaveText([
    'Translate', 'Assistant', 'Terminology', 'Dictionary', 'Documents & audio',
  ])
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Translate')
  await expect(page.getByRole('checkbox', { name: /practice examples/ })).toHaveCount(0)
  await expect(page.getByText(/Compiler lab|coursework|matricule|CS4110|Campus life/i)).toHaveCount(0)
  expect(api.calls('/api/examples')).toHaveLength(0)
  expect(api.requests.filter((request) => request.path.startsWith('/api/coursework'))).toHaveLength(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('terminology export contains only displayed entries and preserves their review metadata', async ({ page, api }) => {
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
  expect(download.suggestedFilename()).toBe('mboa-terminology.json')
  expect(await download.failure()).toBeNull()
  const path = await download.path()
  if (!path) throw new Error('Expected a real downloaded JSON file.')
  const data = JSON.parse(await readFile(path, 'utf8'))
  expect(data.entries).toEqual([approved])
  expect(Number.isNaN(Date.parse(data.exported_at))).toBe(false)
  expect(api.calls('/api/dataset', 'POST')).toHaveLength(0)
})
