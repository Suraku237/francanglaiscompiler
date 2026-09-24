import type { BrowserContext, Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import type { RecordedTest, TestReport } from '../../src/analyzerTypes'
import type { RecordedReading } from '../../src/voice'
import { installSyntheticMicrophone } from '../browserAudio'
import { openGrammarSettings } from '../browserGrammar'
import { signIn, signUp } from './accountWorkflows'
import { downloadedBytes, playMuted, silence, tracksReleased } from './audioWorkflows'
import { expect, test } from './fixtures'

async function protectTestContext(context: BrowserContext) {
  await context.route(/^https?:\/\/(?!127\.0\.0\.1:4190\/).*/, (route) => route.abort('blockedbyclient'))
  await context.addInitScript(() => {
    for (const name of ['speechSynthesis', 'SpeechRecognition', 'webkitSpeechRecognition']) {
      Object.defineProperty(window, name, { configurable: true, get() { throw new Error('Synthetic voices and recognition must not be used.') } })
    }
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: {
      getUserMedia: () => Promise.reject(new Error('Physical microphones are not used by automated tests.')),
    } })
  })
}

async function openShibaReading(page: Page) {
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Dictionary', exact: true }).click()
  await page.getByRole('searchbox', { name: 'Search reference dictionary' }).fill('shiba')
  const card = page.getByRole('article').filter({ has: page.getByRole('heading', { name: 'shiba', exact: true }) })
  await card.getByRole('button', { name: 'Read aloud with a recorded voice', exact: true }).click()
  return page.getByRole('dialog', { name: 'Recorded read-aloud' })
}

test.beforeEach(async ({ context }) => protectTestContext(context))

test('Camfranglais uses the supplied logo and persists actual shared voice recordings with creator-only changes', async ({ page, browser }, testInfo) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const email = await signUp(page)
  await expect(page).toHaveTitle('Franc Analyzer — Camfranglais Compiler')
  const brand = page.getByRole('link', { name: 'Camfranglais home, Franc Analyzer', exact: true })
  await expect(brand).toBeVisible()
  await expect(brand.locator('img')).toHaveAttribute('src', '/camfranglais-logo.png')
  await expect.poll(() => brand.locator('img').evaluate((element) => element instanceof HTMLImageElement && element.naturalWidth)).toBe(256)
  expect((await page.request.get('/camfranglais-icon.png')).headers()['content-type']).toContain('image/png')
  await installSyntheticMicrophone(page)
  const dialog = await openShibaReading(page)
  await expect(dialog.getByText(/No voice recording is saved/)).toBeVisible()
  await expect(dialog.getByLabel('Text for this reading')).toHaveText('shiba')
  const uploads: string[] = []
  page.on('request', (request) => {
    if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/readings/audio') uploads.push(request.url())
  })
  await dialog.getByRole('button', { name: 'Record audio', exact: true }).click()
  await expect(dialog.getByRole('button', { name: 'Save voice recording', exact: true })).toBeDisabled()
  await expect.poll(() => page.evaluate(() => window.recordedTestBytes ?? 0)).toBeGreaterThan(0)
  expect(uploads).toEqual([])
  await dialog.getByRole('button', { name: 'Stop recording', exact: true }).click()
  await tracksReleased(page)
  const localAudio = await downloadedBytes(page, dialog.getByRole('link', { name: 'Download audio' }))
  expect(localAudio.length).toBeGreaterThan(100)
  expect(uploads).toEqual([])
  await expect(dialog.getByRole('button', { name: 'Save voice recording', exact: true })).toBeDisabled()
  await dialog.getByRole('checkbox', { name: /permission to share/ }).check()
  const saving = page.waitForResponse((response) => response.url().endsWith('/api/readings/audio') && response.request().method() === 'POST')
  await dialog.getByRole('button', { name: 'Save voice recording', exact: true }).click()
  const savedResponse = await saving
  expect(savedResponse.status(), await savedResponse.text()).toBe(201)
  const saved: RecordedReading = await savedResponse.json()
  expect(saved.text).toBe('shiba')
  expect(saved.ownership.can_edit).toBe(true)
  await expect(dialog.getByText(/Your voice recording is saved/)).toBeVisible()
  expect(await (await page.request.get(saved.audio_url)).body()).toEqual(localAudio)
  const partial = await page.request.get(saved.audio_url, { headers: { Range: 'bytes=0-15' } })
  expect(partial.status()).toBe(206)
  expect(await partial.body()).toEqual(localAudio.subarray(0, 16))
  await playMuted(dialog.getByLabel(`Play recording: ${saved.audio_filename}`, { exact: true }))
  expect((await (await page.request.get('/api/dataset')).json()).total).toBe(0)
  expect((await (await page.request.get('/api/analyzer/tests')).json()).summary.total).toBe(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  expect(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
  await expect(dialog.getByRole('heading', { name: 'Recorded read-aloud', exact: true })).toBeInViewport()
  await page.screenshot({ path: testInfo.outputPath('recorded-voice.png') })
  await dialog.getByRole('button', { name: 'Done', exact: true }).click()
  await page.reload()
  const reopened = await openShibaReading(page)
  await expect(reopened.getByRole('heading', { name: 'Saved reading', exact: true })).toBeVisible()
  await reopened.getByLabel('Attach an audio file').setInputFiles(silence)
  await reopened.getByRole('checkbox', { name: /permission to share/ }).check()
  const replacing = page.waitForResponse((response) => response.url().endsWith(`/api/readings/${saved.id}/audio`) && response.request().method() === 'PATCH')
  await reopened.getByRole('button', { name: 'Replace saved reading', exact: true }).click()
  const replaced = await replacing
  expect(replaced.status(), await replaced.text()).toBe(200)
  const replacement: RecordedReading = await replaced.json()
  expect(replacement.id).toBe(saved.id)
  expect(replacement.audio_filename).not.toBe(saved.audio_filename)
  // Browser interactions can outlast the API client's pooled connection; retry only a reset GET.
  expect(await (await page.request.get(saved.audio_url, { maxRetries: 1 })).body()).toEqual(await readFile(silence))
  await playMuted(reopened.getByLabel(`Play recording: ${replacement.audio_filename}`, { exact: true }))
  await reopened.getByRole('button', { name: 'Done', exact: true }).click()

  const otherContext = await browser.newContext({ baseURL: 'http://127.0.0.1:4190', viewport: page.viewportSize() ?? undefined })
  try {
    await protectTestContext(otherContext)
    const other = await otherContext.newPage()
    other.on('pageerror', (error) => errors.push(error.message))
    await signUp(other)
    const shared = await openShibaReading(other)
    await expect(shared.getByText(/Only its creator can replace or remove/)).toBeVisible()
    await expect(shared.getByRole('button', { name: /Record audio|Replace saved reading|Remove saved reading/ })).toHaveCount(0)
    expect(await (await other.request.get(saved.audio_url)).body()).toEqual(await readFile(silence))
    const session = await (await other.request.get('/api/auth/session')).json()
    const denied = await other.request.delete(`/api/readings/${saved.id}`, {
      headers: { Origin: 'http://127.0.0.1:4190', 'X-CSRF-Token': session.csrf_token },
    })
    expect(denied.status()).toBe(403)
    await shared.getByRole('button', { name: 'Done', exact: true }).click()
  } finally {
    await otherContext.close()
  }

  page.once('dialog', (prompt) => prompt.accept())
  await page.getByRole('button', { name: 'Sign out', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Sign in to Camfranglais', exact: true })).toBeVisible()
  expect((await page.request.get(saved.audio_url)).status()).toBe(401)
  await signIn(page, email)
  const retained = await openShibaReading(page)
  await expect(retained.getByRole('heading', { name: 'Saved reading', exact: true })).toBeVisible()
  await retained.getByRole('button', { name: 'Remove saved reading', exact: true }).click()
  await retained.getByRole('button', { name: 'Yes, remove reading', exact: true }).click()
  await expect(retained.getByText(/The active reading was removed/)).toBeVisible()
  await expect(retained.getByText(/No voice recording is saved/)).toBeVisible()
  expect((await page.request.get(saved.audio_url)).status()).toBe(404)
  expect(errors).toEqual([])
})

test('recognized slang passes vocabulary approval while UNKNOWN fails even when its grammar accepts it', async ({ page }, testInfo) => {
  await signUp(page)
  for (const [text, grammar, approved, parsed] of [
    ['  wanda\t', 'S -> NOUN', true, false],
    ['sec souvent', 'S -> NOUN', true, false],
    ['mbindi', 'S -> NOUN', true, false],
    ['zqxyl', 'S -> UNKNOWN', false, true],
  ] as const) {
    await openGrammarSettings(page)
    await page.getByLabel('Context-free grammar').fill(grammar)
    await page.getByRole('link', { name: 'Back to Franc Analyzer' }).click()
    await page.getByLabel('Statement to analyze').fill(text)
    const saving = page.waitForResponse((response) => response.url().endsWith('/api/analyzer/tests') && response.request().method() === 'POST')
    await page.getByRole('button', { name: 'Analyze', exact: true }).click()
    const record: RecordedTest = await (await saving).json()
    expect(record.approval.accepted).toBe(approved)
    expect(record.parse.accepted).toBe(parsed)
    expect(record.text).toBe(text)
    const verdict = page.getByRole('group', { name: 'Vocabulary approval', exact: true })
    await expect(verdict.getByText(approved ? 'ACCEPT' : 'REJECT', { exact: true })).toBeVisible()
    expect(await page.getByLabel('Analyzed source text').textContent()).toBe(text)
  }
  await page.getByRole('link', { name: 'View detailed analysis' }).click()
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
  await page.screenshot({ path: testInfo.outputPath('vocabulary-and-grammar.png'), fullPage: true })
  await page.reload()
  const report: TestReport = await (await page.request.get('/api/analyzer/tests')).json()
  expect(report.summary).toEqual({ total: 4, accepted: 3, rejected: 1, acceptance_rate: 75 })
  expect(report.grammar_summary).toEqual({ total: 4, accepted: 1, rejected: 3, acceptance_rate: 25 })
  await page.getByRole('button', { name: 'Inspect test 1', exact: true }).click()
  expect(await page.getByLabel('Analyzed source text').textContent()).toBe('  wanda\t')
  await expect(page.getByRole('group', { name: 'Vocabulary approval', exact: true })).toContainText('ACCEPT')
})
