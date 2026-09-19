import { test, expect } from './fixtures'
import { dataset, entry } from '../fixtures'
import { deferred } from '../helpers'

test('collection review validates text, invalidates approval and submits only changed fields', async ({ page, api }) => {
  await page.goto('/#collection')
  await page.getByRole('button', { name: 'Add expression', exact: true }).click()
  const addDialog = page.getByRole('dialog', { name: 'Add an expression to learn' })
  const expression = addDialog.getByRole('textbox', { name: /^Expression/ })
  await expect(expression).toBeFocused()
  await expression.fill('   ')
  await addDialog.getByRole('button', { name: 'Save unreviewed' }).click()
  await expect(addDialog.getByRole('alert')).toContainText('It cannot contain only spaces.')
  expect(api.calls('/api/dataset', 'POST')).toHaveLength(0)
  await page.keyboard.press('Escape')
  await expect(addDialog).not.toBeVisible()
  await expect(page.getByRole('button', { name: 'Add expression', exact: true })).toBeFocused()

  const editTrigger = page.getByRole('button', { name: 'Edit expression: Fixture expression' })
  await editTrigger.click()
  const editor = page.getByRole('dialog', { name: 'Review this expression' })
  const approval = editor.getByRole('checkbox', { name: /I have reviewed the language/ })
  await expect(approval).toBeChecked()
  await editor.getByRole('textbox', { name: /^English meaning/ }).fill('Reviewed fixture meaning')
  await expect(approval).not.toBeChecked()

  const saved = entry({ english_gloss: 'Reviewed fixture meaning', review_status: 'unreviewed' })
  const saveResponse = deferred<void>()
  api.on('PATCH', '/api/dataset/fixture-record-1', async (route) => {
    await saveResponse.promise
    api.entries = [saved]
    await route.fulfill({ json: saved })
  })
  await editor.getByRole('button', { name: 'Save unreviewed' }).click()
  await expect.poll(() => api.calls('/api/dataset/fixture-record-1', 'PATCH').length).toBe(1)
  expect(api.calls('/api/dataset/fixture-record-1', 'PATCH')[0]?.body).toEqual({
    english_gloss: 'Reviewed fixture meaning', review_status: 'unreviewed',
  })
  await expect(editor.getByRole('button', { name: 'Close dialog' })).toBeDisabled()
  await expect(editor.getByRole('textbox', { name: /^Expression/ })).toBeDisabled()
  await page.keyboard.press('Escape')
  await expect(editor).toBeVisible()
  saveResponse.resolve()
  await expect(editor).not.toBeVisible()
  await expect(page.getByText('Saved locally as unreviewed. Review and approve before trusted dataset matching.')).toBeVisible()
  await expect(page.getByRole('article').filter({ has: page.getByRole('heading', { name: 'Fixture expression', exact: true }) }).getByText('Unreviewed', { exact: true })).toBeVisible()
})

test('delete confirmation never mutates on dismissal and reports server errors without hiding the record', async ({ page, api }) => {
  await page.goto('/#collection')
  const remove = page.getByRole('button', { name: 'Delete expression: Fixture expression' })
  await remove.click()
  const dialog = page.getByRole('dialog', { name: 'Remove this expression?' })
  await dialog.getByRole('button', { name: 'Keep expression' }).click()
  await expect(dialog).not.toBeVisible()
  await expect(remove).toBeFocused()
  expect(api.calls('/api/dataset/fixture-record-1', 'DELETE')).toHaveLength(0)

  api.reply('DELETE', '/api/dataset/fixture-record-1', { detail: 'Fixture record is currently locked.' }, 409)
  await remove.click()
  await dialog.getByRole('button', { name: 'Yes, remove it' }).click()
  await expect(dialog.getByRole('alert')).toHaveText('Fixture record is currently locked.')
  await expect(dialog.getByRole('button', { name: 'Yes, remove it' })).toBeEnabled()
  await page.keyboard.press('Escape')
  await expect(remove).toBeVisible()
  expect(api.calls('/api/dataset/fixture-record-1', 'DELETE')).toHaveLength(1)
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
  await page.getByRole('searchbox', { name: 'Search your collection' }).fill('old')
  await expect.poll(() => api.calls('/api/dataset').filter((request) => request.url.searchParams.get('query') === 'old').length).toBe(1)
  await page.getByRole('searchbox', { name: 'Search your collection' }).fill('Second')
  await expect(page.getByRole('heading', { name: 'Second fixture', exact: true })).toBeVisible()
  oldSearch.resolve()
  await oldFulfilled.promise
  await expect(page.getByRole('heading', { name: 'Stale search result', exact: true })).not.toBeVisible()
  await expect(page.getByRole('heading', { name: /The collection 1 expression/ })).toBeVisible()
  await page.getByRole('button', { name: 'Clear filters', exact: true }).click()
  await page.getByLabel('Filter by review status').selectOption('approved')
  await expect(page.getByRole('heading', { name: 'Fixture expression', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Second fixture', exact: true })).not.toBeVisible()
  await expect(page.getByLabel('Counts across the entire local dataset')).toContainText('2expressions collected')
})
