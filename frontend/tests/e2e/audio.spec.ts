import { test, expect } from './fixtures'
import { installSyntheticMicrophone } from '../browserAudio'
import { entry } from '../fixtures'

test('records synthetic audio locally and uploads it only with an explicit collection save', async ({ page, api }) => {
  api.entries = []
  const saved = entry({ text: 'Synthetic audio test', review_status: 'unreviewed', audio_filename: 'fixture-recording.webm' })
  api.on('POST', '/api/dataset/audio', async (route, request) => {
    expect(request.rawBody).toContain('name="fields"')
    expect(request.rawBody).toContain('"text":"Synthetic audio test"')
    expect(request.rawBody).toContain('"review_status":"unreviewed"')
    expect(request.rawBody).toMatch(/filename="recording-\d+\.webm"/)
    api.entries = [saved]
    await route.fulfill({ status: 201, json: saved })
  })
  await page.goto('/#collection')
  await installSyntheticMicrophone(page)
  await page.getByRole('button', { name: 'Add entry', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Add collection entry' })
  await dialog.getByRole('textbox', { name: /^Expression/ }).fill('Synthetic audio test')
  await dialog.getByRole('button', { name: 'Record audio', exact: true }).click()
  await expect(dialog.getByRole('button', { name: 'Save unreviewed' })).toBeDisabled()
  await expect(dialog.getByText('Recording 00:01', { exact: true })).toBeVisible()
  await expect.poll(() => page.evaluate(() => window.recordedTestBytes ?? 0)).toBeGreaterThan(0)
  expect(api.calls('/api/dataset/audio')).toHaveLength(0)
  await dialog.getByRole('button', { name: 'Stop recording', exact: true }).click()
  await expect(dialog.getByText(/recording-\d+\.webm \(/)).toBeVisible()
  await expect(dialog.getByText('Microphone off', { exact: true })).toBeVisible()
  await expect(dialog.getByRole('link', { name: 'Download audio' })).toHaveAttribute('href', /^blob:/)
  expect(api.calls('/api/imports/preview')).toHaveLength(0)
  await dialog.getByRole('button', { name: 'Save unreviewed' }).click()
  await expect(dialog).not.toBeVisible()
  await expect(page.getByRole('heading', { name: 'Synthetic audio test', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Download audio' })).toHaveAttribute('href', `/api/dataset/${saved.id}/audio`)
  expect(api.calls('/api/dataset/audio')).toHaveLength(1)
  expect(api.calls('/api/translate')).toHaveLength(0)
  expect(api.calls('/api/chat')).toHaveLength(0)
})

test('denied microphone permission is actionable and does not prevent text-only saving', async ({ page, api }) => {
  api.entries = []
  api.reply('POST', '/api/dataset', entry({ text: 'Text after denied permission', review_status: 'unreviewed' }), 201)
  await page.goto('/#collection')
  await page.evaluate(() => {
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: () => Promise.reject(new DOMException('Denied in isolated test', 'NotAllowedError')) },
    })
  })
  await page.getByRole('button', { name: 'Add entry', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Add collection entry' })
  await dialog.getByRole('button', { name: 'Record audio', exact: true }).click()
  await expect(dialog.getByRole('alert')).toContainText('Microphone permission was denied')
  await dialog.getByRole('textbox', { name: /^Expression/ }).fill('Text after denied permission')
  await dialog.getByRole('button', { name: 'Save unreviewed' }).click()
  await expect(dialog).not.toBeVisible()
  expect(api.calls('/api/dataset', 'POST')).toHaveLength(1)
  expect(api.calls('/api/dataset/audio')).toHaveLength(0)
})
