import { test, expect } from './fixtures'
import { health, importPreview, translation } from '../fixtures'

test('local import hands reviewed text to the translator without submitting or approving it automatically', async ({ page, api }) => {
  api.health = health(false)
  api.reply('POST', '/api/imports/preview', importPreview())
  api.reply('POST', '/api/translate', translation())
  await page.goto('/#imports')
  await page.getByLabel('Document, image, audio or video').setInputFiles({
    name: 'fixture.txt', mimeType: 'text/plain', buffer: Buffer.from('Synthetic local fixture, not fieldwork.'),
  })
  await expect(page.getByRole('checkbox', { name: /I consent to sending this file to Gemini/ })).toBeDisabled()
  expect(api.calls('/api/imports/preview')).toHaveLength(0)
  await page.getByRole('button', { name: 'Preview source text' }).click()
  await expect(page.getByText(/fixture.txt · Extracted locally/)).toBeVisible()
  expect(api.calls('/api/imports/preview', 'POST')[0]?.rawBody)
    .toMatch(/name="allow_cloud_processing"\r?\n\r?\nfalse/)
  await page.getByLabel('Review and correct this passage').fill('Sens de test')
  await page.getByRole('button', { name: 'Open in translator' }).click()
  await expect(page).toHaveURL(/#translator$/)
  await expect(page.getByRole('textbox', { name: 'French text to translate' })).toHaveValue('Sens de test')
  expect(api.calls('/api/translate')).toHaveLength(0)
  expect(api.calls('/api/dataset', 'POST')).toHaveLength(0)

  await page.getByRole('button', { name: 'Translate', exact: true }).click()
  await expect(page.getByText('Exact approved match · local', { exact: true })).toBeVisible()
  expect(api.calls('/api/translate', 'POST')[0]?.body).toMatchObject({
    text: 'Sens de test', use_dataset: true, allow_ai: false,
  })
})

test('media import requires explicit consent and a separate retry before a cloud-labelled preview', async ({ page, api }) => {
  api.reply('POST', '/api/imports/preview', { detail: 'Fixture cloud consent is required.' }, 422)
  await page.goto('/#imports')
  await page.getByLabel('Document, image, audio or video').setInputFiles({
    name: 'fixture.png', mimeType: 'image/png', buffer: Buffer.from('Synthetic mocked media, never decoded.'),
  })
  await page.getByRole('button', { name: 'Preview source text' }).click()
  await expect(page.getByRole('alert')).toHaveText('Fixture cloud consent is required.')
  expect(api.calls('/api/imports/preview', 'POST')[0]?.rawBody)
    .toMatch(/name="allow_cloud_processing"\r?\n\r?\nfalse/)

  api.reply('POST', '/api/imports/preview', importPreview({
    filename: 'fixture.png', format: 'png', method: 'gemini',
  }))
  await page.getByRole('checkbox', { name: /I consent to sending this file to Gemini/ }).check()
  expect(api.calls('/api/imports/preview')).toHaveLength(1)
  await page.getByRole('button', { name: 'Preview source text' }).click()
  await expect(page.getByText(/Unreviewed AI transcript/)).toBeVisible()
  expect(api.calls('/api/imports/preview', 'POST')[1]?.rawBody)
    .toMatch(/name="allow_cloud_processing"\r?\n\r?\ntrue/)
  expect(api.calls('/api/dataset', 'POST')).toHaveLength(0)
})

test('old coursework links redirect without reading or exposing academic records', async ({ page, api }) => {
  await page.goto('/#coursework')
  await expect(page).toHaveURL(/#translator$/)
  await expect(page).toHaveTitle('Translate — Mboa Workspace')
  await expect(page.getByLabel('Group member 1')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Download coursework draft (.zip)' })).toHaveCount(0)
  expect(api.requests.filter((request) => request.path.startsWith('/api/coursework'))).toHaveLength(0)
})
