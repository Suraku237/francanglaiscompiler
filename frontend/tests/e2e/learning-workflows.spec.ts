import { test, expect, emptyZip } from './fixtures'
import { courseworkAnalysis, courseworkState, importPreview, manualParse, project } from '../fixtures'

test('local import sends only one file and preserves manual handoff spacing without computation', async ({ page, api }) => {
  api.reply('POST', '/api/imports/preview', importPreview())
  await page.goto('/#imports')
  await page.getByLabel('Text document').setInputFiles({
    name: 'fixture.txt', mimeType: 'text/plain', buffer: Buffer.from('Synthetic local fixture, not fieldwork.'),
  })
  await expect(page.getByRole('checkbox')).toHaveCount(0)
  expect(api.calls('/api/imports/preview')).toHaveLength(0)
  await page.getByRole('button', { name: 'Preview source text' }).click()
  await expect(page.getByText(/fixture.txt · Extracted locally/)).toBeVisible()
  const body = api.calls('/api/imports/preview', 'POST')[0]?.rawBody
  expect(body).toContain('name="file"')
  expect(body).not.toContain('allow_cloud_processing')
  const raw = '  Mbom,\tTu  es where?\n\n'
  await page.getByLabel('Review and correct this passage').fill(raw)
  await page.getByRole('button', { name: 'Open in compiler' }).click()
  await expect(page).toHaveURL(/#compiler$/)
  await expect(page.getByLabel('Manual parser test')).toHaveValue(raw)
  await expect(page.getByLabel('Manual parser test')).toBeFocused()
  expect(api.calls('/api/coursework/parse')).toHaveLength(0)
  expect(api.calls('/api/analyze')).toHaveLength(0)
  expect(api.calls('/api/dataset', 'POST')).toHaveLength(0)
})

test('unsupported media is rejected locally and scanned PDFs demand a manual transcript', async ({ page, api }) => {
  api.reply('POST', '/api/imports/preview', { detail: 'No text layer. Supply a manual transcript; no OCR is available.' }, 422)
  await page.goto('/#imports')
  await page.getByLabel('Text document').setInputFiles({
    name: 'fixture.png', mimeType: 'image/png', buffer: Buffer.from('Mocked media, never decoded.'),
  })
  await expect(page.getByRole('alert')).toContainText('manual text transcript')
  await expect(page.getByRole('button', { name: 'Preview source text' })).toBeDisabled()
  expect(api.calls('/api/imports/preview')).toHaveLength(0)
  await page.getByLabel('Text document').setInputFiles({
    name: 'fixture.pdf', mimeType: 'application/pdf', buffer: Buffer.from('Mocked scanned PDF, never decoded.'),
  })
  await page.getByRole('button', { name: 'Preview source text' }).click()
  await expect(page.getByRole('alert')).toContainText('Supply a manual transcript')
  await expect(page.getByRole('button', { name: /AI|transcrib|dictat/i })).toHaveCount(0)
  await page.getByRole('button', { name: 'Open Collection for raw recordings' }).click()
  await expect(page).toHaveURL(/#collection$/)
})

test('grammar analysis shows transformations, sets, tables, warnings and manual traces without saving', async ({ page, api }) => {
  const result = courseworkAnalysis()
  result.grammar.steps = [{
    operation: 'Left recursion elimination', before: { S: [['S', 'NOUN'], ['NOUN']] },
    after: { S: [['NOUN', 'S_tail']], S_tail: [['NOUN', 'S_tail'], []] },
    description: 'Synthetic deterministic transformation fixture.',
  }]
  result.grammar.warnings = ['Fixture warning: grammar coverage still needs observed data.']
  api.reply('POST', '/api/coursework/analyze', result)
  api.reply('POST', '/api/coursework/parse', manualParse())
  await page.goto('/')
  await page.getByRole('tab', { name: 'Syntactic analysis', exact: true }).click()
  await page.getByLabel('Context-free grammar').fill('S -> S NOUN | NOUN')
  await page.getByRole('button', { name: 'Analyze grammar & saved corpus' }).click()
  await expect(page.getByRole('heading', { name: 'Computed grammar' })).toBeVisible()
  await expect(page.getByText('Fixture warning: grammar coverage still needs observed data.')).toBeVisible()
  await page.getByText('Left recursion elimination', { exact: false }).click()
  await expect(page.getByText('Synthetic deterministic transformation fixture.')).toBeVisible()
  expect(api.calls('/api/coursework/analyze')[0]?.body).toEqual({ grammar: 'S -> S NOUN | NOUN' })
  expect(api.calls('/api/coursework/project')).toHaveLength(0)
  await expect(page.getByRole('region', { name: 'Computed FIRST and FOLLOW sets' })).toBeVisible()
  await expect(page.getByRole('region', { name: 'LL(1) predictive parsing table, scroll horizontally' })).toBeVisible()
  await page.getByRole('tab', { name: 'Lexical analysis', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Saved-statement token analysis' })).toBeVisible()
  await expect(page.getByText('Token frequencies · 0 forms', { exact: true })).toBeVisible()
  await expect(page.getByText('No variation candidates were observed in this corpus.', { exact: true })).toBeVisible()
  await page.getByRole('tab', { name: 'Parser tests', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Own-data acceptance tests' })).toBeVisible()
  await page.getByRole('tab', { name: 'Report & presentation', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Download coursework draft (.zip)' })).toBeDisabled()
  await page.getByRole('tab', { name: 'Syntactic analysis', exact: true }).click()
  await page.getByLabel('Context-free grammar').fill('S -> epsilon')
  await expect(page.getByRole('heading', { name: 'Computed grammar' })).toHaveCount(0)
  await page.getByRole('tab', { name: 'Parser tests', exact: true }).click()
  await page.getByRole('button', { name: 'Parse test input' }).click()
  expect(api.calls('/api/coursework/parse')[0]?.body).toEqual({ grammar: 'S -> epsilon', text: '' })
  await expect(page.getByRole('heading', { name: 'Manual test result' })).toBeVisible()
  await expect(page.getByText('S → epsilon', { exact: true })).toBeVisible()
  await page.getByLabel('Manual parser test').fill('Changed synthetic input, not fieldwork.')
  await expect(page.getByRole('heading', { name: 'Manual test result' })).toHaveCount(0)
  await expect(page.getByRole('region', { name: 'Table-driven parser step trace' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Parse test input' }).click()
  await expect(page.getByRole('heading', { name: 'Manual test result' })).toBeVisible()
  await page.getByLabel('Manual parser test').fill('')
  await expect(page.getByRole('heading', { name: 'Manual test result' })).toHaveCount(0)
  await expect(page.getByRole('region', { name: 'Table-driven parser step trace' })).toHaveCount(0)
  expect(api.calls('/api/coursework/parse')).toHaveLength(2)
})

test('explicit project save enables only a saved-evidence ZIP export', async ({ page, api }) => {
  const saved = project({ grammar_rationale: 'Synthetic fixture rationale, not fieldwork.' })
  api.on('PUT', '/api/coursework/project', async (route, request) => {
    expect(request.body).toEqual(saved)
    api.coursework = courseworkState(saved)
    await route.fulfill({ json: { saved: true } })
  })
  api.on('GET', '/api/coursework/export', async (route) => route.fulfill({
    body: emptyZip, contentType: 'application/zip',
  }))
  await page.goto('/')
  await page.getByRole('tab', { name: 'Syntactic analysis', exact: true }).click()
  await page.getByText('Grammar notation & rationale', { exact: true }).click()
  await page.getByLabel('Why this grammar fits your observations').fill(saved.grammar_rationale)
  await page.getByRole('tab', { name: 'Report & presentation', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Download coursework draft (.zip)' })).toBeDisabled()
  await page.getByRole('button', { name: 'Save project', exact: true }).click()
  await expect(page.getByText('No unsaved editor changes', { exact: true })).toBeVisible()
  const downloading = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download coursework draft (.zip)' }).click()
  const download = await downloading
  expect(download.suggestedFilename()).toBe('francanglais-coursework.zip')
  expect(await download.failure()).toBeNull()
  expect(api.calls('/api/coursework/export')).toHaveLength(1)
  await page.getByRole('tab', { name: 'Data collection', exact: true }).click()
  await page.getByText('Collection notes for the report', { exact: true }).click()
  await expect(page.getByRole('checkbox', { name: /We manually transcribed/ })).not.toBeChecked()
})
