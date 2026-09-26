import type { Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import type { TestReport } from '../../src/analyzerTypes'
import type { RecordedReading } from '../../src/voice'
import { downloadedBytes, playMuted, silence } from './audioWorkflows'
import { expect, test } from './fixtures'
import { analyzePublicInput, origin, protectPublicContext, publicHeaders, readOnlyOwnership } from './publicWorkflows'

async function openDictionaryReading(page: Page, word: string) {
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Dictionary', exact: true }).click()
  await page.getByRole('searchbox', { name: 'Search reference dictionary' }).fill(word)
  const card = page.getByRole('article').filter({ has: page.getByRole('heading', { name: word, exact: true }) }).first()
  await card.getByRole('button', { name: 'Read aloud with a recorded voice', exact: true }).click()
  return page.getByRole('dialog', { name: 'Recorded read-aloud', exact: true })
}

test.beforeEach(async ({ context }) => protectPublicContext(context))

test.describe('public recorded playback', () => {
  test.use({ seed: {
    entries: [{ text: 'Fixture with preserved audio', entry_type: 'Sentence', audio: true }],
    readings: [{ text: 'shiba', language: 'fr' }],
  } })

  test('the supplied logo and existing recordings remain public, playable and read-only across fresh browsers', async ({ page, browser }, testInfo) => {
    const errors: string[] = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.goto('/')
    await expect(page).toHaveTitle('Franc Analyzer — Camfranglais Compiler')
    const brand = page.getByRole('link', { name: 'Camfranglais home, Franc Analyzer', exact: true })
    await expect(brand.locator('img')).toHaveAttribute('src', '/camfranglais-logo.png')
    await expect.poll(() => brand.locator('img').evaluate((element) => element instanceof HTMLImageElement && element.naturalWidth)).toBe(256)
    expect((await page.request.get('/camfranglais-icon.png')).headers()['content-type']).toContain('image/png')
    const bytes = await readFile(silence)
    const dialog = await openDictionaryReading(page, 'shiba')
    await expect(dialog.getByRole('heading', { name: 'Saved reading', exact: true })).toBeVisible()
    await expect(dialog.getByLabel('Text for this reading')).toHaveText('shiba')
    await expect(dialog.getByRole('button', { name: /Record audio|Replace saved reading|Remove saved reading|Save voice/ })).toHaveCount(0)
    await expect(dialog.getByLabel('Attach an audio file')).toHaveCount(0)
    const headers = await publicHeaders(page.request)
    const lookup = await page.request.post('/api/readings/lookup', { headers, data: { text: 'SHIBA', language: 'fr' } })
    expect(lookup.status(), await lookup.text()).toBe(200)
    const saved: RecordedReading = (await lookup.json()).reading
    expect(saved.ownership).toEqual(readOnlyOwnership)
    expect(await (await page.request.get(saved.audio_url)).body()).toEqual(bytes)
    const partial = await page.request.get(saved.audio_url, { headers: { Range: 'bytes=0-15' } })
    expect(partial.status()).toBe(206)
    expect(await partial.body()).toEqual(bytes.subarray(0, 16))
    await playMuted(dialog.getByLabel(`Play recording: ${saved.audio_filename}`, { exact: true }))
    expect(await downloadedBytes(page, dialog.getByRole('link', { name: 'Download audio', exact: true }))).toEqual(bytes)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    expect(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
    await page.screenshot({ path: testInfo.outputPath('public-recorded-voice.png') })
    await dialog.getByRole('button', { name: 'Done', exact: true }).click()
    await page.reload()
    const reopened = await openDictionaryReading(page, 'shiba')
    await expect(reopened.getByRole('heading', { name: 'Saved reading', exact: true })).toBeVisible()
    expect((await page.request.patch(`/api/readings/${saved.id}/audio`, { headers, data: {} })).status()).toBe(403)
    expect((await page.request.delete(`/api/readings/${saved.id}`, { headers })).status()).toBe(403)
    expect((await page.request.post('/api/readings/audio', { headers, data: {} })).status()).toBe(403)
    await reopened.getByRole('button', { name: 'Done', exact: true }).click()
    const missing = await openDictionaryReading(page, 'mola')
    await expect(missing.getByText(/No voice recording is available/)).toContainText('read-only; recording and uploads are unavailable')
    await expect(missing.getByRole('button', { name: /Record audio|Save voice recording|Upload/i })).toHaveCount(0)
    await missing.getByRole('button', { name: 'Done', exact: true }).click()
    await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Collection', exact: true }).click()
    const collection = await (await page.request.get('/api/dataset')).json()
    const entry = collection.entries[0]
    expect(entry.ownership).toEqual(readOnlyOwnership)
    await playMuted(page.getByLabel(`Play recording: ${entry.audio_filename}`, { exact: true }))
    expect(await downloadedBytes(page, page.getByRole('link', { name: 'Download audio', exact: true }))).toEqual(bytes)
    const otherContext = await browser.newContext({ baseURL: origin, viewport: page.viewportSize() ?? undefined })
    try {
      await protectPublicContext(otherContext)
      const other = await otherContext.newPage()
      other.on('pageerror', (error) => errors.push(error.message))
      expect(await (await other.request.get(saved.audio_url)).body()).toEqual(bytes)
      expect(await (await other.request.get(`/api/dataset/${entry.id}/audio`)).body()).toEqual(bytes)
      await other.goto('/')
      const shared = await openDictionaryReading(other, 'shiba')
      await expect(shared.getByRole('heading', { name: 'Saved reading', exact: true })).toBeVisible()
      await expect(shared.getByRole('button', { name: /Record audio|Replace|Remove|Save voice/ })).toHaveCount(0)
      await expect(shared.getByText(/Creator:/)).toHaveCount(0)
      await playMuted(shared.getByLabel(`Play recording: ${saved.audio_filename}`, { exact: true }))
    } finally {
      await otherContext.close()
    }
    expect(await (await page.request.get(saved.audio_url)).body()).toEqual(bytes)
    expect(await (await page.request.get('/api/dataset')).json()).toEqual(collection)
    expect((await (await page.request.get('/api/analyzer/tests')).json()).summary.total).toBe(0)
    expect(errors).toEqual([])
  })
})

test.describe('vocabulary approval separate from read-only grammar', () => {
  test.use({ seed: { grammar: 'S -> UNKNOWN' } })

  test('recognized slang passes vocabulary approval while UNKNOWN fails even when the saved grammar accepts it', async ({ page }, testInfo) => {
    await page.goto('/')
    for (const [text, approved, parsed] of [
      ['  wanda\t', true, false],
      ['sec souvent', true, false],
      ['mbindi', true, false],
      ['zqxyl', false, true],
    ] as const) {
      const record = await analyzePublicInput(page, text)
      expect(record.approval.accepted).toBe(approved)
      expect(record.parse.accepted).toBe(parsed)
      expect(record.text).toBe(text)
      expect(record.grammar_source).toBe('S -> UNKNOWN')
      await expect(page.getByRole('group', { name: 'Vocabulary approval', exact: true }).getByText(approved ? 'ACCEPT' : 'REJECT', { exact: true })).toBeVisible()
      expect(await page.getByLabel('Analyzed source text').textContent()).toBe(text)
    }
    await page.getByRole('link', { name: 'View detailed analysis', exact: true }).click()
    await expect(page.getByRole('group', { name: 'Accepted', exact: true })).toContainText('3')
    await expect(page.getByRole('group', { name: 'Rejected', exact: true })).toContainText('1')
    await expect(page.getByRole('group', { name: 'Acceptance rate', exact: true })).toContainText('75%')
    await expect(page.getByRole('group', { name: 'Grammar matches', exact: true })).toContainText('1')
    await expect(page.getByRole('group', { name: 'Grammar match rate', exact: true })).toContainText('25%')
    await page.getByText('Parser trace for this input', { exact: true }).click()
    const selected = page.getByRole('region', { name: 'Analyzed sentence or word', exact: true })
    await expect(selected.getByRole('group', { name: 'Vocabulary approval', exact: true })).toContainText('REJECT')
    await expect(selected.getByRole('region', { name: 'Table-driven parser step trace' })).toContainText('Accept: input fully consumed.')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.screenshot({ path: testInfo.outputPath('vocabulary-and-saved-grammar.png'), fullPage: true })
    await page.reload()
    const report: TestReport = await (await page.request.get('/api/analyzer/tests')).json()
    expect(report.summary).toEqual({ total: 4, accepted: 3, rejected: 1, acceptance_rate: 75 })
    expect(report.grammar_summary).toEqual({ total: 4, accepted: 1, rejected: 3, acceptance_rate: 25 })
    await page.getByRole('button', { name: 'Inspect test 1', exact: true }).click()
    expect(await page.getByLabel('Analyzed source text').textContent()).toBe('  wanda\t')
    await expect(page.getByRole('group', { name: 'Vocabulary approval', exact: true })).toContainText('ACCEPT')
  })
})
