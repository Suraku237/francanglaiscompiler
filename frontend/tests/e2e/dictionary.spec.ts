import { test, expect } from './fixtures'
import { health, translation } from '../fixtures'
import type { DictionaryEntry, DictionaryResult } from '../../src/types'

const reference: DictionaryEntry = {
  id: 'dictionary:fixture.md:4', text: 'tchop', aliases: ['tchop'],
  language: 'francanglais', english_gloss: 'to eat', origin: 'Pidgin chop',
  topic: 'Fixture verbs', source_document: 'fixture.md', source_line: 4,
}
const dictionary: DictionaryResult = {
  entries: [reference], total: 1, matched: 1, offset: 0, limit: 25, sources: ['fixture.md'],
}

test('dictionary lookup hands off a draft and translates locally without populating collection', async ({ page, api }) => {
  api.health = health(false)
  api.entries = []
  api.reply('GET', '/api/dictionary', dictionary)
  api.reply('POST', '/api/translate', translation({
    translation: reference.english_gloss, source_language: 'francanglais', target_language: 'en',
    origin: 'dictionary', model: 'local-dictionary',
    evidence: [{
      id: reference.id, text: reference.text, language: 'francanglais', french_gloss: '',
      english_gloss: reference.english_gloss, match_type: 'exact', source: 'dictionary',
      source_document: reference.source_document, source_line: reference.source_line, aliases: reference.aliases,
    }],
  }))
  await page.goto('/#dictionary')
  await expect(page).toHaveTitle('Dictionary — Mboa Workspace')
  await expect(page.getByRole('heading', { name: 'tchop', exact: true })).toBeVisible()
  await expect(page.getByText(/No French translations were supplied/)).toBeVisible()
  await page.getByRole('searchbox', { name: 'Search reference dictionary' }).fill('tchop')
  await expect.poll(() => api.calls('/api/dictionary').at(-1)?.url.searchParams.get('query')).toBe('tchop')
  await page.getByRole('button', { name: 'Open tchop in translator' }).click()
  await expect(page).toHaveURL(/#translator$/)
  await expect(page.getByRole('combobox', { name: 'From', exact: true })).toHaveValue('francanglais')
  await expect(page.getByRole('combobox', { name: 'To', exact: true })).toHaveValue('en')
  await expect(page.getByRole('textbox', { name: 'Cameroon Francanglais text to translate' })).toHaveValue('tchop')
  expect(api.calls('/api/translate')).toHaveLength(0)
  await page.getByRole('button', { name: 'Translate', exact: true }).click()
  await expect(page.getByText('Reference dictionary · local', { exact: true })).toBeVisible()
  await expect(page.getByText(/fixture.md:4 · not reviewed terminology/)).toBeVisible()
  await expect(page.getByText(/No Gemini translation request was needed/)).toBeVisible()
  expect(api.calls('/api/translate')[0]?.body).toMatchObject({
    text: 'tchop', source_language: 'francanglais', target_language: 'en', use_dictionary: true, allow_ai: false,
  })
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Terminology', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Add your first entry' })).toBeVisible()
  expect(api.calls('/api/dataset', 'POST')).toHaveLength(0)
})

test('dictionary failures are visible and retry recovers without an AI request', async ({ page, api }) => {
  api.reply('GET', '/api/dictionary', { detail: 'Reference dictionary is unavailable.' }, 503)
  await page.goto('/#dictionary')
  await expect(page.getByRole('alert')).toContainText('Reference dictionary is unavailable.')
  api.reply('GET', '/api/dictionary', dictionary)
  await page.getByRole('button', { name: 'Try again', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'tchop', exact: true })).toBeVisible()
  await expect(page.getByRole('alert')).not.toBeVisible()
  expect(api.calls('/api/translate')).toHaveLength(0)
  expect(api.calls('/api/chat')).toHaveLength(0)
})
