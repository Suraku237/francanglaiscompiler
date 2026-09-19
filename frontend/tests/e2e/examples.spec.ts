import { test, expect } from './fixtures'
import { health, translation } from '../fixtures'

test('constructed examples support French practice without creating research records', async ({ page, api }) => {
  api.health = health(false)
  api.entries = []
  const example = {
    id: 'examples:fixture:1', text: 'Mon mbom, tu es where?', language: 'francanglais',
    french_gloss: 'Mon pote, tu es où ?', english_gloss: 'My guy, where are you?',
    topic: 'People', notes: 'Constructed example; not a verified real-speaker statement.',
    source_document: 'camfranglais_statements.csv', source_line: 2, constructed: true,
  }
  api.reply('GET', '/api/examples', {
    entries: [example], total: 26, matched: 1, offset: 0, limit: 25, sources: [example.source_document],
  })
  api.reply('POST', '/api/translate', translation({
    translation: example.french_gloss, source_language: 'francanglais', target_language: 'fr',
    origin: 'examples', model: 'local-examples',
    evidence: [{
      id: example.id, text: example.text, language: 'francanglais', french_gloss: example.french_gloss,
      english_gloss: example.english_gloss, source: 'examples', match_type: 'exact',
      source_document: example.source_document, source_line: example.source_line, aliases: [],
    }],
  }))
  await page.goto('/#examples')
  await expect(page).toHaveTitle('Practice examples — Mboa language learning')
  await expect(page.getByRole('heading', { name: example.text, exact: true })).toBeVisible()
  await expect(page.getByText('Constructed examples, not genuine fieldwork.')).toBeVisible()
  await page.getByRole('searchbox', { name: 'Search practice examples' }).fill('mbom')
  await expect.poll(() => api.calls('/api/examples').at(-1)?.url.searchParams.get('query')).toBe('mbom')
  await page.getByRole('button', { name: 'Practice in French' }).click()
  await expect(page).toHaveURL(/#translator$/)
  await expect(page.getByRole('combobox', { name: 'To', exact: true })).toHaveValue('fr')
  await expect(page.getByRole('checkbox', { name: 'Use constructed practice examples (not fieldwork)' })).toBeChecked()
  expect(api.calls('/api/translate')).toHaveLength(0)
  await page.getByRole('button', { name: 'Translate', exact: true }).click()
  await expect(page.getByText('Constructed practice example · local', { exact: true })).toBeVisible()
  await expect(page.getByText('Constructed example · camfranglais_statements.csv:2 · not fieldwork')).toBeVisible()
  expect(api.calls('/api/translate')[0]?.body).toMatchObject({ use_examples: true, allow_ai: false })
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Collection', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Add your first expression' })).toBeVisible()
  expect(api.calls('/api/dataset', 'POST')).toHaveLength(0)
})
