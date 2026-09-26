import { test, expect } from './fixtures'
import { dataset, entry, ownership } from '../fixtures'
import { deferred } from '../helpers'

test('collection details preserve raw data, remain read-only and restore keyboard focus on dismissal', async ({ page, api }) => {
  const original = entry({ text: '  Fixture\texpression\n', ownership: ownership({ can_edit: true, owner_name: 'Obsolete name' }) })
  api.entries = [original]
  await page.goto('/#collection')
  await expect(page.getByRole('button', { name: /Add entry|Edit expression|Delete expression|Approve/i })).toHaveCount(0)
  const trigger = page.getByRole('button', { name: /^View expression:\s+Fixture\s+expression\s*$/ })
  await trigger.click()
  const viewer = page.getByRole('dialog', { name: 'View collection entry', exact: true })
  const expression = viewer.getByRole('textbox', { name: 'Expression', exact: true })
  await expect(expression).toBeFocused()
  await expect(expression).toHaveValue(original.text)
  await expect(expression).not.toBeEditable()
  await page.keyboard.type('Cannot change this record')
  await expect(expression).toHaveValue(original.text)
  await expect(viewer.getByRole('textbox', { name: 'English meaning', exact: true })).toHaveValue(original.english_gloss)
  await expect(viewer.getByRole('button', { name: /save|record|upload|remove|delete/i })).toHaveCount(0)
  await expect(viewer.getByRole('checkbox')).toHaveCount(0)
  await expect(viewer.getByText(/creator:|Obsolete name/i)).toHaveCount(0)
  await page.keyboard.press('Escape')
  await expect(viewer).not.toBeVisible()
  await expect(trigger).toBeFocused()
  expect(api.requests.filter((request) => request.method !== 'GET')).toEqual([])
  expect(api.entries).toEqual([original])
})

test('empty and failed collections stay honest without offering write controls', async ({ page, api }) => {
  api.entries = []
  api.reply('GET', '/api/dataset', { detail: 'Collection storage is unavailable.' }, 503)
  await page.goto('/#collection')
  await expect(page.getByRole('heading', { name: 'Collection unavailable', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'No collected statements yet', exact: true })).toHaveCount(0)
  api.reply('GET', '/api/dataset', dataset([]))
  await page.getByRole('button', { name: 'Try again', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'No collected statements yet', exact: true })).toBeVisible()
  await expect(page.getByText(/The public collection is empty and read-only/)).toBeVisible()
  await expect(page.getByRole('button', { name: /add.*entry|record audio|upload/i })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Export results (JSON)', exact: true })).toBeDisabled()
  expect(api.requests.filter((request) => request.method !== 'GET')).toEqual([])
})

test('debounced search ignores stale results and client filters leave global counts intact', async ({ page, api }) => {
  api.entries.push(entry({
    id: 'fixture-record-2', text: 'Second fixture', language: 'pidgin', review_status: 'unreviewed', category: 'Other',
  }))
  const original = [...api.entries]
  const oldSearch = deferred<void>()
  const oldFulfilled = deferred<void>()
  api.on('GET', '/api/dataset', async (route, request) => {
    const query = request.url.searchParams.get('query')
    if (query === 'old') {
      await oldSearch.promise
      await route.fulfill({ json: dataset([entry({ text: 'Stale search result' })]) })
      oldFulfilled.resolve()
    } else {
      await route.fulfill({ json: { ...dataset(original), entries: query ? [original[1]] : original } })
    }
  })
  await page.goto('/#collection')
  await expect(page.getByRole('heading', { name: 'Fixture expression', exact: true })).toBeVisible()
  await page.getByRole('searchbox', { name: 'Search collection' }).fill('old')
  await expect.poll(() => api.calls('/api/dataset').filter((request) => request.url.searchParams.get('query') === 'old').length).toBe(1)
  await page.getByRole('searchbox', { name: 'Search collection' }).fill('Second')
  await expect(page.getByRole('heading', { name: 'Second fixture', exact: true })).toBeVisible()
  oldSearch.resolve()
  await oldFulfilled.promise
  await expect(page.getByRole('heading', { name: 'Stale search result', exact: true })).not.toBeVisible()
  await expect(page.getByRole('heading', { name: /Collected records 1 entry/ })).toBeVisible()
  await page.getByRole('button', { name: 'Clear filters', exact: true }).click()
  await page.getByLabel('Filter by review status').selectOption('approved')
  await expect(page.getByRole('heading', { name: 'Fixture expression', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Second fixture', exact: true })).not.toBeVisible()
  await expect(page.getByLabel('Counts across the public workspace')).toContainText('2Total entries')
})
