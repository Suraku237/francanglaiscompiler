import { readFile } from 'node:fs/promises'
import { test, expect } from './fixtures'
import type { MockApi } from './fixtures'
import { entry, ownership } from '../fixtures'
import { playMuted, silence } from '../live/audioWorkflows'

function serveRecording(api: MockApi, path: string, bytes: Buffer) {
  api.on('GET', path, (route, request) => {
    const range = request.headers.range?.match(/^bytes=(\d+)-(\d*)$/)
    const start = range ? Number(range[1]) : 0
    const end = range?.[2] ? Math.min(Number(range[2]), bytes.length - 1) : bytes.length - 1
    return route.fulfill({
      status: range ? 206 : 200,
      headers: {
        'Content-Type': 'audio/wav', 'Content-Disposition': 'attachment; filename="fixture.wav"', 'Accept-Ranges': 'bytes',
        ...(range ? { 'Content-Range': `bytes ${start}-${end}/${bytes.length}` } : {}),
      },
      body: bytes.subarray(start, end + 1),
    })
  })
}

test('existing Collection audio plays and links to its download without offering recording or attachment edits', async ({ page, api }) => {
  const bytes = await readFile(silence)
  api.entries = [entry({ audio_filename: 'fixture.wav', ownership: ownership({ can_edit: true }) })]
  serveRecording(api, '/api/dataset/fixture-record-1/audio', bytes)
  await page.goto('/#collection')
  const player = page.getByLabel('Play recording: fixture.wav', { exact: true })
  await playMuted(player)
  const download = page.getByRole('link', { name: 'Download audio', exact: true })
  await expect(download).toHaveAttribute('href', '/api/dataset/fixture-record-1/audio')
  await expect(download).toHaveAttribute('download', 'fixture.wav')
  await page.getByRole('button', { name: 'View expression: Fixture expression', exact: true }).click()
  const viewer = page.getByRole('dialog', { name: 'View collection entry', exact: true })
  await expect(viewer.getByLabel('Play recording: fixture.wav', { exact: true })).toBeVisible()
  await expect(viewer.getByRole('button', { name: /record|upload|remove|save/i })).toHaveCount(0)
  await expect(viewer.getByLabel('Attach an audio file', { exact: true })).toHaveCount(0)
  await viewer.getByRole('button', { name: 'Done', exact: true }).click()
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Franc Analyzer', exact: true }).click()
  expect(await player.evaluate((element) => (element as HTMLAudioElement).paused)).toBe(true)
  expect(api.requests.filter((request) => request.method !== 'GET')).toEqual([])
})

test('missing and unavailable recorded readings stay explicit, with no microphone or upload fallback', async ({ page, api }) => {
  api.reply('GET', '/api/dictionary', {
    entries: [{ id: 'fixture-word', text: 'shiba', aliases: ['shiba'], language: 'francanglais', english_gloss: 'to eat', origin: '', topic: '', source_document: 'fixture.csv', source_line: 1 }],
    total: 1, matched: 1, offset: 0, limit: 25, sources: ['fixture.csv'],
  })
  api.reply('POST', '/api/readings/lookup', { detail: 'Recording storage is unavailable.' }, 503)
  await page.goto('/#dictionary')
  await page.getByRole('button', { name: 'Read aloud with a recorded voice', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Recorded read-aloud', exact: true })
  await expect(dialog.getByRole('alert')).toContainText('Recording storage is unavailable')
  await expect(dialog.getByText(/No voice recording is available/)).toHaveCount(0)
  api.reply('POST', '/api/readings/lookup', { reading: null })
  await dialog.getByRole('button', { name: 'Try again', exact: true }).click()
  await expect(dialog.getByText(/No voice recording is available/)).toContainText('read-only; recording and uploads are unavailable')
  await expect(dialog.getByRole('button', { name: /record audio|save voice|upload|replace|remove/i })).toHaveCount(0)
  await expect(dialog.getByLabel('Attach an audio file', { exact: true })).toHaveCount(0)
  await dialog.getByRole('button', { name: 'Done', exact: true }).click()
  expect(api.calls('/api/readings/lookup', 'POST')).toHaveLength(2)
  expect(api.calls('/api/readings/lookup', 'POST')[0]?.body).toEqual({ text: 'shiba', language: 'fr' })
})

test('saved pronunciation audio remains playable and read-only even with obsolete edit flags', async ({ page, api }) => {
  const bytes = await readFile(silence)
  api.reply('GET', '/api/dictionary', {
    entries: [{ id: 'fixture-word', text: 'shiba', aliases: ['shiba'], language: 'francanglais', english_gloss: 'to eat', origin: '', topic: '', source_document: 'fixture.csv', source_line: 1 }],
    total: 1, matched: 1, offset: 0, limit: 25, sources: ['fixture.csv'],
  })
  api.reply('POST', '/api/readings/lookup', { reading: {
    id: 'fixture-reading', text: 'shiba', language: 'fr', audio_filename: 'reading.wav',
    audio_url: '/api/readings/fixture-reading/audio', created_at: '', updated_at: '',
    ownership: ownership({ can_edit: true, owner_name: 'Historical name' }),
  } })
  serveRecording(api, '/api/readings/fixture-reading/audio', bytes)
  await page.goto('/#dictionary')
  await page.getByRole('button', { name: 'Read aloud with a recorded voice', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Recorded read-aloud', exact: true })
  await expect(dialog.getByRole('heading', { name: 'Saved reading', exact: true })).toBeVisible()
  await playMuted(dialog.getByLabel('Play recording: reading.wav', { exact: true }))
  // Native HTTP download bytes are verified with the isolated live backend, not browser routing.
  const download = dialog.getByRole('link', { name: 'Download audio', exact: true })
  await expect(download).toHaveAttribute('href', '/api/readings/fixture-reading/audio')
  await expect(download).toHaveAttribute('download', 'reading.wav')
  await expect(dialog.getByRole('button', { name: /record audio|replace|remove|save/i })).toHaveCount(0)
  await expect(dialog.getByText(/creator:|Historical name/i)).toHaveCount(0)
})
