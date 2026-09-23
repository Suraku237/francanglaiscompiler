import { test, expect } from './fixtures'
import type { DictionaryEntry, DictionaryResult } from '../../src/types'

const reference: DictionaryEntry = {
  id: 'dictionary:fixture.md:4', text: 'tchop', aliases: ['  Tchop\t '],
  language: 'francanglais', english_gloss: 'to eat', origin: 'Pidgin chop',
  topic: 'Fixture verbs', source_document: 'fixture.md', source_line: 4,
}
const dictionary: DictionaryResult = {
  entries: [reference], total: 1, matched: 1, offset: 0, limit: 25, sources: ['fixture.md'],
}

test('dictionary hands a raw form to the compiler without populating or certifying collection', async ({ page, api }) => {
  api.entries = []
  api.reply('GET', '/api/dictionary', dictionary)
  api.reply('POST', '/api/analyze', {
    tokens: [{ text: 'Tchop', category: 'VERB' }], code_mixed_spans: [], verb_phrases: [],
  })
  await page.goto('/#dictionary')
  await expect(page).toHaveTitle('Dictionary — Mboa Compiler')
  await expect(page.getByRole('heading', { name: 'tchop', exact: true })).toBeVisible()
  await expect(page.getByText(/No French translations were supplied/)).toBeVisible()
  await page.getByRole('searchbox', { name: 'Search reference dictionary' }).fill('tchop')
  await expect.poll(() => api.calls('/api/dictionary').at(-1)?.url.searchParams.get('query')).toBe('tchop')
  await page.getByRole('button', { name: 'Open tchop in compiler' }).click()
  await expect(page).toHaveURL(/#compiler$/)
  await expect(page.getByLabel('Manual parser test')).toHaveValue('  Tchop\t ')
  await expect(page.getByLabel('Manual parser test')).toBeFocused()
  expect(api.calls('/api/analyze')).toHaveLength(0)
  expect(api.calls('/api/coursework/parse')).toHaveLength(0)
  await page.getByRole('button', { name: 'Analyze tokens', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Manual lexical result' })).toBeVisible()
  expect(api.calls('/api/analyze')[0]?.body).toEqual({ text: '  Tchop\t ' })
  await page.getByRole('tab', { name: 'Data collection', exact: true }).click()
  await page.getByText('Collection notes for the report', { exact: true }).click()
  await expect(page.getByRole('checkbox', { name: /We manually transcribed/ })).not.toBeChecked()
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Collection', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'No collected statements yet' })).toBeVisible()
  expect(api.calls('/api/dataset', 'POST')).toHaveLength(0)
})

test('dictionary errors support an explicit retry without a generation request', async ({ page, api }) => {
  api.reply('GET', '/api/dictionary', { detail: 'Reference dictionary is unavailable.' }, 503)
  await page.goto('/#dictionary')
  await expect(page.getByRole('alert')).toContainText('Reference dictionary is unavailable.')
  api.reply('GET', '/api/dictionary', dictionary)
  await page.getByRole('button', { name: 'Try again', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'tchop', exact: true })).toBeVisible()
  await expect(page.getByRole('alert')).not.toBeVisible()
})
