import { expect } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { DatasetEntry } from '../../src/types'
import { installSyntheticMicrophone } from '../browserAudio'

const silence = join(fileURLToPath(new URL('.', import.meta.url)), '..', 'fixtures', 'imports', 'silence.wav')

async function playMuted(player: Locator) {
  await player.evaluate(async (element) => {
    if (!(element instanceof HTMLAudioElement)) throw new Error('Expected the actual audio player.')
    element.muted = true
    await element.play()
  })
  await expect.poll(() => player.evaluate((element) => {
    if (!(element instanceof HTMLAudioElement)) throw new Error('Expected the actual audio player.')
    if (element.error) throw new Error(`Audio decoding failed: ${element.error.message}`)
    return element.currentTime
  })).toBeGreaterThan(0)
}

async function tracksReleased(page: Page) {
  await expect.poll(() => page.evaluate(() => {
    const tracks = window.syntheticAudioTracks
    return Boolean(tracks?.length && tracks.every((track) => track.readyState === 'ended'))
  })).toBe(true)
}

async function downloadedBytes(page: Page, link: Locator): Promise<Buffer> {
  const pending = page.waitForEvent('download')
  await link.click()
  const download = await pending
  const path = await download.path()
  if (!path) throw new Error('Expected a real browser audio download.')
  return readFile(path)
}

export async function recordPrivateAudio(page: Page): Promise<string> {
  const requests: string[] = []
  page.on('request', (request) => {
    if (request.method() === 'POST') requests.push(new URL(request.url()).pathname)
  })
  await installSyntheticMicrophone(page)
  await page.getByRole('button', { name: 'Add entry', exact: true }).click()
  const editor = page.getByRole('dialog', { name: 'Add terminology' })
  const text = 'Synthetic private audio'
  await editor.getByRole('textbox', { name: /^Expression/ }).fill(text)
  await editor.getByRole('button', { name: 'Record audio', exact: true }).click()
  await expect(editor.getByRole('button', { name: 'Save unreviewed' })).toBeDisabled()
  await expect(editor.getByLabel('Attach an audio file')).toBeDisabled()
  await expect.poll(() => page.evaluate(() => window.recordedTestBytes ?? 0)).toBeGreaterThan(0)
  expect(requests).toEqual([])
  await editor.getByRole('button', { name: 'Stop recording', exact: true }).click()
  await expect(editor.getByText('Microphone off', { exact: true })).toBeVisible()
  await tracksReleased(page)
  await expect(editor.getByRole('link', { name: 'Download audio' })).toHaveAttribute('href', /^blob:/)
  const local = await downloadedBytes(page, editor.getByRole('link', { name: 'Download audio' }))
  expect(local.subarray(0, 4)).toEqual(Buffer.from([0x1a, 0x45, 0xdf, 0xa3]))
  expect(local.length).toBeGreaterThan(100)
  await playMuted(editor.getByLabel(/^Play recording:/))
  expect(requests).toEqual([])
  const saving = page.waitForResponse((response) =>
    new URL(response.url()).pathname === '/api/dataset/audio' && response.request().method() === 'POST')
  await editor.getByRole('button', { name: 'Save unreviewed', exact: true }).click()
  const response = await saving
  expect(response.status(), await response.text()).toBe(201)
  const saved: DatasetEntry = await response.json()
  expect(saved.review_status).toBe('unreviewed')
  expect(saved.text).toBe(text)
  await expect(editor).not.toBeVisible()
  await page.reload()
  const card = page.getByRole('article').filter({ has: page.getByRole('heading', { name: text, exact: true }) })
  await expect(card).toBeVisible()
  const link = card.getByRole('link', { name: 'Download audio' })
  const url = await link.getAttribute('href')
  if (!url) throw new Error('Expected the private audio endpoint.')
  const stored = await page.request.get(url)
  expect(stored.status()).toBe(200)
  expect(stored.headers()['content-type']).toContain('audio/webm')
  expect(stored.headers()['cache-control']).toBe('private, no-store')
  expect(await stored.body()).toEqual(local)
  const ranged = await page.request.get(url, { headers: { Range: 'bytes=0-15' } })
  expect(ranged.status()).toBe(206)
  expect(ranged.headers()['content-range']).toBe(`bytes 0-15/${local.length}`)
  expect(await ranged.body()).toEqual(local.subarray(0, 16))
  expect(await downloadedBytes(page, link)).toEqual(local)
  const player = page.getByLabel(`Play recording: ${saved.audio_filename}`, { exact: true })
  await playMuted(player)
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Documents & audio', exact: true }).click()
  await expect(player).toHaveCount(1)
  await expect.poll(() => player.evaluate((element) => {
    if (!(element instanceof HTMLAudioElement)) throw new Error('Expected the actual audio player.')
    return element.paused
  })).toBe(true)
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Terminology', exact: true }).click()
  expect(requests).toEqual(['/api/dataset/audio'])
  return url
}

export async function checkAudioErrorsAndConsent(page: Page) {
  const navigation = page.getByRole('navigation', { name: 'Main navigation' })
  await navigation.getByRole('link', { name: 'Terminology', exact: true }).click()
  await page.evaluate(() => {
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: () => Promise.reject(new DOMException('Synthetic denial', 'NotAllowedError')) },
    })
  })
  await page.getByRole('button', { name: 'Add entry', exact: true }).click()
  const editor = page.getByRole('dialog', { name: 'Add terminology' })
  const text = 'Synthetic attachment after denied microphone'
  await editor.getByRole('textbox', { name: /^Expression/ }).fill(text)
  await editor.getByRole('button', { name: 'Record audio', exact: true }).click()
  await expect(editor.getByRole('alert').filter({ hasText: 'Microphone permission was denied' })).toBeVisible()
  await expect(editor.getByRole('button', { name: 'Save unreviewed' })).toBeEnabled()
  await editor.getByLabel('Attach an audio file').setInputFiles({
    name: 'invalid.wav', mimeType: 'audio/wav', buffer: Buffer.from('Not a valid WAV recording.'),
  })
  const failed = page.waitForResponse((response) => response.request().method() === 'POST' && response.url().endsWith('/api/dataset/audio'))
  await editor.getByRole('button', { name: 'Save unreviewed', exact: true }).click()
  expect((await failed).status()).toBe(422)
  await expect(editor.getByRole('alert').filter({ hasText: 'contents do not match' })).toBeVisible()
  await expect(editor.getByText(/invalid\.wav \(/)).toBeVisible()
  await expect(editor.getByRole('button', { name: 'Save unreviewed' })).toBeEnabled()
  const before = await page.request.get('/api/dataset')
  expect(before.status()).toBe(200)
  expect((await before.json()).total).toBe(0)
  await editor.getByLabel('Attach an audio file').setInputFiles(silence)
  const saving = page.waitForResponse((response) => response.request().method() === 'POST' && response.url().endsWith('/api/dataset/audio'))
  await editor.getByRole('button', { name: 'Save unreviewed', exact: true }).click()
  const response = await saving
  expect(response.status()).toBe(201)
  const saved: DatasetEntry = await response.json()
  expect(saved.review_status).toBe('unreviewed')
  await expect(editor).not.toBeVisible()
  const card = page.getByRole('article').filter({ has: page.getByRole('heading', { name: text, exact: true }) })
  const url = await card.getByRole('link', { name: 'Download audio' }).getAttribute('href')
  if (!url) throw new Error('Expected the saved WAV endpoint.')
  const stored = await page.request.get(url)
  expect(stored.status()).toBe(200)
  expect(stored.headers()['content-type']).toContain('audio/wav')
  expect(await stored.body()).toEqual(await readFile(silence))
  await playMuted(card.getByLabel(`Play recording: ${saved.audio_filename}`))
  await card.getByRole('button', { name: `Edit expression: ${text}` }).click()
  const review = page.getByRole('dialog', { name: 'Review terminology' })
  await review.getByRole('button', { name: 'Remove attachment on save', exact: true }).click()
  expect((await page.request.get(url)).status()).toBe(200)
  await review.getByRole('button', { name: 'Cancel', exact: true }).click()
  expect((await page.request.get(url)).status()).toBe(200)
  await card.getByRole('button', { name: `Edit expression: ${text}` }).click()
  await review.getByRole('button', { name: 'Remove attachment on save', exact: true }).click()
  await review.getByRole('button', { name: 'Save unreviewed', exact: true }).click()
  await expect(review).not.toBeVisible()
  await expect(card.getByRole('link', { name: 'Download audio' })).toHaveCount(0)
  expect((await page.request.get(url)).status()).toBe(404)

  await navigation.getByRole('link', { name: 'Documents & audio', exact: true }).click()
  await installSyntheticMicrophone(page)
  let previews = 0
  page.on('request', (request) => {
    if (request.url().endsWith('/api/imports/preview')) previews += 1
  })
  await page.getByRole('button', { name: 'Record audio', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Preview source text', exact: true })).toBeDisabled()
  await expect(page.getByLabel('Document, image, audio or video')).toBeDisabled()
  await expect.poll(() => page.evaluate(() => window.recordedTestBytes ?? 0)).toBeGreaterThan(0)
  await navigation.getByRole('link', { name: 'Terminology', exact: true }).click()
  await tracksReleased(page)
  await navigation.getByRole('link', { name: 'Documents & audio', exact: true }).click()
  await expect(page.getByText('Microphone off', { exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Download audio' })).toHaveAttribute('href', /^blob:/)
  expect(previews).toBe(0)
  const consent = page.getByRole('checkbox', { name: /^I consent to sending this file to Gemini/ })
  await expect(consent).not.toBeChecked()
  await expect(consent).toBeDisabled()
  const preview = page.waitForResponse((response) => response.url().endsWith('/api/imports/preview'))
  await page.getByRole('button', { name: 'Preview source text', exact: true }).click()
  expect((await preview).status()).toBe(422)
  await expect(page.getByRole('alert').filter({ hasText: 'Enable cloud processing only if you consent' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Download audio' })).toHaveAttribute('href', /^blob:/)
  await page.getByRole('button', { name: 'Discard draft audio', exact: true }).click()
  await expect(page.getByRole('link', { name: 'Download audio' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Preview source text', exact: true })).toBeDisabled()
  expect(previews).toBe(1)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
}
