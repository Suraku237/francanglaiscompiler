import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { readFile, readdir } from 'node:fs/promises'
import { join } from 'node:path'
import { randomUUID } from 'node:crypto'
import { fileURLToPath } from 'node:url'
import type { ImportPreview } from '../../src/importTypes'
import type { Dataset } from '../../src/types'
import { checkAudioErrorsAndManualDrafts, recordPrivateAudio } from './audioWorkflows'

const password = 'Live-browser-test-passphrase-2026!'
const importDocuments = join(fileURLToPath(new URL('.', import.meta.url)), '..', 'fixtures', 'imports')
type ImportFile = string | { name: string; mimeType: string; buffer: Buffer }

async function emailLink(email: string, kind: string): Promise<string> {
  const directory = process.env.MBOA_LIVE_DATA_DIR
  if (!directory) throw new Error('Missing isolated browser fixture directory.')
  const files = await readdir(join(directory, 'mail'))
  for (const name of files.reverse()) {
    const raw = await readFile(join(directory, 'mail', name), 'utf8')
    const text = raw.replace(/=\r?\n/g, '').replace(/=([0-9A-F]{2})/g, (_, hex: string) => String.fromCharCode(parseInt(hex, 16)))
    if (text.includes(`To: ${email}`)) {
      const match = text.match(new RegExp(`http://127\\.0\\.0\\.1:4190/#${kind}\\?token=[A-Za-z0-9_-]+`))
      if (match) return match[0]
    }
  }
  throw new Error('The test verification email was not delivered to the isolated outbox.')
}

async function signUp(page: Page): Promise<string> {
  const email = `test-${randomUUID()}@example.com`
  await page.goto('/#register')
  await page.getByLabel('Your name', { exact: true }).fill('Synthetic compiler user')
  await page.getByLabel('Email address').fill(email)
  await page.getByLabel(/^Password/).fill(password)
  await page.getByRole('button', { name: 'Create account', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('verification link')
  await page.goto(await emailLink(email, 'verify-email'))
  await page.getByRole('button', { name: 'Verify email', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Sign in to Mboa' })).toBeVisible()
  await page.getByLabel('Email address').fill(email)
  await page.getByLabel(/^Password/).fill(password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeVisible()
  return email
}

async function addEntry(page: Page, text: string) {
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Collection', exact: true }).click()
  await page.getByRole('button', { name: 'Add entry', exact: true }).click()
  const editor = page.getByRole('dialog', { name: 'Add collection entry' })
  await editor.getByRole('textbox', { name: /^Expression/ }).fill(text)
  await editor.getByRole('button', { name: 'Save unreviewed' }).click()
  await expect(editor).not.toBeVisible()
  await expect(page.getByRole('heading', { name: text, exact: true })).toBeVisible()
}

async function previewDocument(page: Page, file: ImportFile, status = 200) {
  await page.getByLabel('Text document').setInputFiles(file)
  await expect(page.getByRole('checkbox')).toHaveCount(0)
  const result = page.waitForResponse((response) =>
    response.url().endsWith('/api/imports/preview') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Preview source text', exact: true }).click()
  const response = await result
  expect(response.status(), await response.text()).toBe(status)
  return response
}

async function importedDataset(page: Page): Promise<Dataset> {
  const response = await page.request.get('/api/dataset')
  expect(response.ok()).toBe(true)
  return response.json()
}

function processingRequests(page: Page): string[] {
  const requests: string[] = []
  page.on('request', (request) => {
    const path = new URL(request.url()).pathname
    if (['/api/translate', '/api/chat', '/api/imports/suggest', '/api/coursework/explain'].includes(path)) requests.push(path)
  })
  return requests
}

test.beforeEach(async ({ context }) => {
  await context.route(/^https?:\/\/(?!127\.0\.0\.1:4190\/).*/, (route) => route.abort('blockedbyclient'))
  await context.addInitScript(() => {
    const forbiddenRecognition = () => { throw new Error('Speech recognition is not part of manual transcription.') }
    Object.defineProperty(window, 'SpeechRecognition', { configurable: true, value: forbiddenRecognition })
    Object.defineProperty(window, 'webkitSpeechRecognition', { configurable: true, value: forbiddenRecognition })
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: {
      getUserMedia: () => Promise.reject(new Error('Physical hardware is not used in automated tests.')),
    } })
  })
})

test('real registration, compiler workflows, private data, sessions and reload persistence', async ({ page, browser }) => {
  await signUp(page)
  await exerciseCompiler(page)
  await addEntry(page, 'Synthetic customer greeting')
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Synthetic customer greeting', exact: true })).toBeVisible()
  const privateAudio = await recordPrivateAudio(page)
  const otherContext = await browser.newContext({ baseURL: 'http://127.0.0.1:4190' })
  try {
    const other = await otherContext.newPage()
    await signUp(other)
    await other.goto('/#collection')
    await expect(other.getByRole('heading', { name: 'No collected statements yet' })).toBeVisible()
    await expect(other.getByRole('heading', { name: 'Synthetic customer greeting', exact: true })).toHaveCount(0)
    expect((await other.request.get(privateAudio)).status()).toBe(404)
  } finally {
    await otherContext.close()
  }
  const sharedTab = await page.context().newPage()
  try {
    await sharedTab.goto('/#collection')
    await expect(sharedTab.getByRole('heading', { name: 'Synthetic customer greeting', exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.cookie)).not.toContain('mboa_session')
    page.once('dialog', (dialog) => dialog.accept())
    await page.getByRole('button', { name: 'Sign out', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Sign in to Mboa' })).toBeVisible()
    await expect(sharedTab.getByRole('heading', { name: 'Sign in to Mboa' })).toBeVisible()
    await expect(page.getByText('Synthetic customer greeting', { exact: true })).toHaveCount(0)
    await expect(sharedTab.getByText('Synthetic customer greeting', { exact: true })).toHaveCount(0)
    expect((await page.request.get(privateAudio)).status()).toBe(401)
  } finally {
    await sharedTab.close()
  }
})

test('legacy history, coursework, projects, revision recovery and verified backup restoration', async ({ page }) => {
  await signUp(page)
  const submitted = processingRequests(page)
  const navigation = page.getByRole('navigation', { name: 'Main navigation' })
  const session = await (await page.request.get('/api/auth/session')).json()
  const legacy = await page.request.post('/api/workspace/history', {
    headers: { 'X-CSRF-Token': session.csrf_token, Origin: 'http://127.0.0.1:4190' },
    data: { kind: 'translation', title: 'Legacy synthetic item', content: {
      source_text: '  Tchop\t ', source_language: 'francanglais', target_language: 'en',
      translation: 'to eat', explanation: 'Synthetic old history fixture, not generated during this run.', note: 'Not fieldwork.',
    } },
  })
  expect(legacy.status(), await legacy.text()).toBe(201)
  await navigation.getByRole('link', { name: 'History', exact: true }).click()
  await page.getByRole('button', { name: 'Open Legacy synthetic item', exact: true }).click()
  await expect(page.getByLabel('Saved work details')).toContainText('to eat')
  await page.getByRole('button', { name: 'Use source in compiler', exact: true }).click()
  await expect(page.getByLabel('Manual parser test')).toHaveValue('  Tchop\t ')
  await page.getByRole('tab', { name: 'Syntactic analysis', exact: true }).click()
  await page.getByLabel('Context-free grammar').fill('S -> NOUN')
  await page.getByText('Grammar notation & rationale', { exact: true }).click()
  await page.getByLabel('Why this grammar fits your observations').fill('Synthetic backup test rationale. No genuine corpus supplied.')
  await page.getByRole('button', { name: 'Save project', exact: true }).click()
  await expect(page.getByText(/Project saved privately on this server/)).toBeVisible()
  await page.getByRole('tab', { name: 'Report & presentation', exact: true }).click()
  await page.getByLabel('Choose PNG or JPEG · max 2 MB').setInputFiles(join(importDocuments, 'image.png'))
  await page.getByLabel('Screenshot caption').fill('Synthetic screenshot fixture')
  await page.getByRole('button', { name: 'Save screenshot to project' }).click()
  await expect(page.getByRole('link', { name: 'Open screenshot: Synthetic screenshot fixture' })).toBeVisible()
  await addEntry(page, 'Synthetic recoverable term')
  await page.getByRole('button', { name: 'Delete expression: Synthetic recoverable term' }).click()
  await page.getByRole('button', { name: 'Yes, remove it' }).click()
  await navigation.getByRole('link', { name: 'Workspace settings', exact: true }).click()
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Restore revision', exact: true }).first().click()
  await expect(page.getByRole('status').filter({ hasText: 'Revision restored as unreviewed' })).toBeVisible()
  await page.getByRole('button', { name: 'Create verified backup' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'Backup created and verified' })).toBeVisible()
  const downloaded = page.waitForEvent('download')
  await page.getByRole('link', { name: 'Download backup' }).first().click()
  const download = await downloaded
  const path = await download.path()
  if (!path) throw new Error('Expected a real private backup download.')
  await addEntry(page, 'Synthetic post-backup term')
  await navigation.getByRole('link', { name: 'Workspace settings', exact: true }).click()
  await page.getByLabel('Backup ZIP (maximum 32 MB)').setInputFiles(path)
  await page.getByRole('button', { name: 'Validate and preview backup' }).click()
  await expect(page.getByRole('heading', { name: 'Restore preview', exact: true })).toBeVisible()
  await expect(page.getByLabel('Backup contents')).toContainText('1 coursework profiles')
  await expect(page.getByLabel('Backup contents')).toContainText('1 coursework screenshots')
  await expect(page.getByLabel('Restore warnings')).toContainText(/coursework|grammar|screenshots/i)
  await expect(page.getByRole('button', { name: 'Replace my workspace' })).toBeDisabled()
  await page.getByLabel('Type REPLACE to confirm').fill('REPLACE')
  await page.getByRole('button', { name: 'Replace my workspace' }).click()
  await expect(page.getByText('Workspace restored. Review the restored information before using it.')).toBeVisible()
  await navigation.getByRole('link', { name: 'Collection', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Synthetic recoverable term', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Synthetic post-backup term', exact: true })).toHaveCount(0)
  await navigation.getByRole('link', { name: 'Compiler lab', exact: true }).click()
  await page.getByRole('tab', { name: 'Syntactic analysis', exact: true }).click()
  await expect(page.getByLabel('Context-free grammar')).toHaveValue('S -> NOUN')
  await expect(page.getByLabel('Why this grammar fits your observations')).toHaveValue('Synthetic backup test rationale. No genuine corpus supplied.')
  await page.getByRole('tab', { name: 'Report & presentation', exact: true }).click()
  await expect(page.getByRole('link', { name: 'Open screenshot: Synthetic screenshot fixture' })).toBeVisible()
  await navigation.getByRole('link', { name: 'Workspace settings', exact: true }).click()
  await page.getByLabel('New project name').fill('Synthetic second project')
  await page.getByRole('button', { name: 'Create project', exact: true }).click()
  await expect(page.getByLabel('Active project')).toContainText('Synthetic second project')
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByLabel('Active project').selectOption({ label: 'Synthetic second project' })
  await navigation.getByRole('link', { name: 'Collection', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'No collected statements yet' })).toBeVisible()
  await navigation.getByRole('link', { name: 'Compiler lab', exact: true }).click()
  await expect(page.getByRole('tab', { name: 'Lexical analysis', exact: true })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByLabel('Why this grammar fits your observations')).toHaveValue('')
  await expect(page.getByLabel('Sentence to analyze')).toHaveValue('')
  await expect(page.getByRole('link', { name: 'Open screenshot: Synthetic screenshot fixture' })).toHaveCount(0)
  expect(submitted).toEqual([])
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('real password recovery revokes existing sessions and replaces the old password', async ({ page, browser }) => {
  const email = await signUp(page)
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Workspace settings', exact: true }).click()
  await page.getByRole('button', { name: 'Email password reset', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: 'reset link' })).toBeVisible()
  const recoveryContext = await browser.newContext({ baseURL: 'http://127.0.0.1:4190' })
  try {
    const recovery = await recoveryContext.newPage()
    await recovery.goto(await emailLink(email, 'reset-password'))
    const replacement = 'Replacement-live-test-passphrase-2026!'
    await recovery.getByLabel(/^Password/).fill(replacement)
    await recovery.getByRole('button', { name: 'Update password', exact: true }).click()
    await expect(recovery.getByRole('heading', { name: 'Sign in to Mboa' })).toBeVisible()
    await page.reload()
    await expect(page.getByRole('heading', { name: 'Sign in to Mboa' })).toBeVisible()
    await recovery.getByLabel('Email address').fill(email)
    await recovery.getByLabel(/^Password/).fill(password)
    await recovery.getByRole('button', { name: 'Sign in', exact: true }).click()
    await expect(recovery.getByRole('alert')).toContainText('email or password is incorrect')
    await recovery.getByLabel(/^Password/).fill(replacement)
    await recovery.getByRole('button', { name: 'Sign in', exact: true }).click()
    await expect(recovery.getByRole('navigation', { name: 'Main navigation' })).toBeVisible()
  } finally {
    await recoveryContext.close()
  }
})

async function exerciseCompiler(page: Page) {
  const submitted = processingRequests(page)
  await expect(page).toHaveURL(/#compiler$/)
  await expect(page.getByLabel('Sentence to analyze')).toBeVisible()
  await page.getByRole('tab', { name: 'Data collection', exact: true }).click()
  await expect(page.getByText('No collected corpus in this project yet.', { exact: true })).toBeVisible()
  await page.getByRole('tab', { name: 'Syntactic analysis', exact: true }).click()
  await page.getByLabel('Context-free grammar').fill('S -> S NOUN | NOUN')
  await page.getByRole('button', { name: 'Analyze grammar & saved corpus' }).click()
  await expect(page.getByRole('heading', { name: 'Computed grammar' })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Computed FIRST and FOLLOW sets' })).toBeVisible()
  await expect(page.getByText('LL(1) · no table conflicts', { exact: true })).toBeVisible()
  await page.getByRole('tab', { name: 'Lexical analysis', exact: true }).click()
  await page.getByLabel('Sentence to analyze').fill('  Mbom\t')
  await page.getByRole('button', { name: 'Analyze tokens' }).click()
  await expect(page.getByRole('heading', { name: 'Manual lexical result' })).toBeVisible()
  await page.getByRole('button', { name: 'Open parser test', exact: true }).click()
  const parsing = page.waitForResponse((response) => response.url().endsWith('/api/coursework/parse'))
  await page.getByRole('button', { name: 'Parse test input' }).click()
  const parsed = await parsing
  expect(parsed.status(), await parsed.text()).toBe(200)
  expect(parsed.request().postDataJSON().text).toBe('  Mbom\t')
  await expect(page.getByRole('region', { name: 'Table-driven parser step trace' })).toBeVisible()

  await page.getByRole('tab', { name: 'Syntactic analysis', exact: true }).click()
  await page.getByLabel('Context-free grammar').fill('S -> A NOUN\nA -> NOUN | epsilon')
  await page.getByRole('button', { name: 'Analyze grammar & saved corpus' }).click()
  await expect(page.getByText('Not LL(1) · inspect conflicts', { exact: true })).toBeVisible()
  await expect(page.getByText('A deterministic LL(1) choice is not available.', { exact: true })).toBeVisible()
  await page.getByLabel('Context-free grammar').fill('S -> epsilon')
  await page.getByRole('tab', { name: 'Parser tests', exact: true }).click()
  await page.getByLabel('Manual parser test').fill('')
  await page.getByRole('button', { name: 'Parse test input' }).click()
  await expect(page.getByText('ACCEPT', { exact: true })).toBeVisible()
  await page.getByRole('tab', { name: 'Report & presentation', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Download coursework draft (.zip)' })).toBeDisabled()
  await page.getByRole('button', { name: 'Save project', exact: true }).click()
  await expect(page.getByText(/Project saved privately on this server/)).toBeVisible()
  const downloaded = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download coursework draft (.zip)' }).click()
  expect((await downloaded).suggestedFilename()).toBe('francanglais-coursework.zip')
  await page.reload()
  await expect(page.getByLabel('Context-free grammar')).toHaveValue('S -> epsilon')
  await page.getByRole('tab', { name: 'Data collection', exact: true }).click()
  await page.getByText('Collection notes for the report', { exact: true }).click()
  await expect(page.getByRole('checkbox', { name: /We manually transcribed/ })).not.toBeChecked()
  expect((await importedDataset(page)).total).toBe(0)
  expect(submitted).toEqual([])
}

test('local documents preserve all six formats, hand off drafts and save only after review', async ({ page }) => {
  await signUp(page)
  const submitted = processingRequests(page)
  const navigation = page.getByRole('navigation', { name: 'Main navigation' })
  await navigation.getByRole('link', { name: 'Document import', exact: true }).click()
  await expect(page.getByRole('checkbox')).toHaveCount(0)
  const term = {
    text: 'synthetic-import-term', entry_type: 'Word', language: 'francanglais',
    english_gloss: 'delivery', french_gloss: 'exp\u00e9dition', review_status: 'approved',
    category: 'Campus Life', source_location: 'Original transcript line 8', contributor: 'TEST-CONTRIBUTOR', notes: 'TEST-NOTE',
  }
  const json = JSON.stringify({ entries: [term] })
  const csv = `${Object.keys(term).join(',')}\r\n${Object.values(term).join(',')}\r\n`
  const text = 'Commande TEST-1042.\r\nLivraison \u00e0 Yaound\u00e9.'
  const markdown = '# Commande TEST-1042\n\nLivraison \u00e0 Yaound\u00e9.'
  const documents: { file: ImportFile; text: string; structured?: boolean }[] = [
    { file: { name: 'business.txt', mimeType: 'text/plain', buffer: Buffer.from('\ufeff' + text) }, text },
    { file: { name: 'business.md', mimeType: 'text/markdown', buffer: Buffer.from(markdown) }, text: markdown },
    { file: join(importDocuments, 'business.docx'), text: 'Commande TEST-1042.\nExp\u00e9dition\tmardi.\n3 articles.' },
    { file: join(importDocuments, 'business.pdf'), text: 'Order TEST-1042 contains 3 items. Do not send before Tuesday.' },
    { file: { name: 'terms.json', mimeType: 'application/json', buffer: Buffer.from(json) }, text: json, structured: true },
    { file: { name: 'terms.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) }, text: csv, structured: true },
  ]
  for (const document of documents) {
    const response = await previewDocument(page, document.file)
    const preview: ImportPreview = await response.json()
    expect(preview.method).toBe('local')
    expect(preview.text).toBe(document.text)
    expect(preview.segments.join('')).toBe(document.text)
    await expect(page.getByLabel('Review and correct this passage')).toHaveValue(document.text.replace(/\r\n/g, '\n'))
    await page.getByText('Original extracted text (read-only)', { exact: true }).click()
    expect(await page.locator('.import-original pre').textContent()).toBe(document.text)
    if (document.structured) {
      expect(preview.drafts).toEqual([expect.objectContaining({
        text: term.text, english_gloss: term.english_gloss, french_gloss: term.french_gloss,
        review_status: 'unreviewed',
      })])
      expect(preview.drafts[0]).toMatchObject({
        category: term.category, source_location: term.source_location, contributor: term.contributor, notes: term.notes,
      })
      await expect(page.getByRole('heading', { name: term.text, exact: true })).toBeVisible()
    } else expect(preview.drafts).toEqual([])
    expect((await importedDataset(page)).total).toBe(0)
  }
  await expect(page.getByRole('button', { name: /AI|suggest|translat/i })).toHaveCount(0)
  const correction = '  Please\tdeliver order TEST-1042.\n\n'
  await page.getByLabel('Review and correct this passage').fill(correction)
  expect(await page.locator('.import-original pre').textContent()).toBe(csv)
  await page.getByRole('button', { name: 'Open in compiler', exact: true }).click()
  await expect(page.getByLabel('Manual parser test')).toHaveValue(correction)
  await navigation.getByRole('link', { name: 'Document import', exact: true }).click()
  await expect(page.getByLabel('Review and correct this passage')).toHaveValue(correction)
  expect(submitted).toEqual([])
  expect((await importedDataset(page)).total).toBe(0)
  await navigation.getByRole('link', { name: 'Document import', exact: true }).click()
  await page.getByRole('button', { name: 'Review and save candidate', exact: true }).click()
  const editor = page.getByRole('dialog', { name: 'Add collection entry' })
  await expect(editor.getByRole('textbox', { name: /^Expression/ })).toHaveValue(term.text)
  expect((await importedDataset(page)).total).toBe(0)
  await editor.getByRole('button', { name: 'Save unreviewed', exact: true }).click()
  await expect(editor).not.toBeVisible()
  await expect(page.getByRole('button', { name: 'Saved - manage in Collection' })).toBeDisabled()
  const saved = await importedDataset(page)
  expect(saved.total).toBe(1)
  expect(saved.entries).toHaveLength(1)
  const entry = saved.entries[0]
  if (!entry) throw new Error('Expected the explicitly saved synthetic import.')
  expect(entry).toMatchObject({
    text: term.text, review_status: 'unreviewed', french_gloss: term.french_gloss, english_gloss: term.english_gloss,
  })
  expect(entry).toMatchObject({
    contributor: term.contributor, notes: term.notes, category: term.category, source_location: term.source_location,
  })
  await navigation.getByRole('link', { name: 'Collection', exact: true }).click()
  await page.reload()
  await expect(page.getByRole('heading', { name: term.text, exact: true })).toBeVisible()
  expect(submitted).toEqual([])
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('local document limits, invalid files and scanned PDF manual-transcript errors recover clearly', async ({ page }) => {
  await signUp(page)
  const submitted = processingRequests(page)
  let previews = 0
  page.on('request', (request) => {
    if (request.url().endsWith('/api/imports/preview')) previews += 1
  })
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Document import', exact: true }).click()
  const boundary = 'A'.repeat(39996) + 'END!'
  for (const file of [
    join(importDocuments, 'at-limit.pdf'),
    { name: 'at-limit.txt', mimeType: 'text/plain', buffer: Buffer.from(boundary) },
  ]) {
    const response = await previewDocument(page, file)
    const preview: ImportPreview = await response.json()
    expect(preview.text).toBe(boundary)
    expect(preview.segments).toHaveLength(10)
    expect(preview.segments.every((segment) => segment.length === 4000)).toBe(true)
    expect(preview.segments.join('')).toBe(boundary)
    await page.getByLabel('Choose a passage').selectOption('9')
    await expect(page.getByLabel('Review and correct this passage')).toHaveValue(boundary.slice(36000))
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  }
  const invalid: { file: ImportFile; status: number; error: string }[] = [
    { file: join(importDocuments, 'over-limit.pdf'), status: 413, error: '40,000 characters' },
    { file: { name: 'over-limit.txt', mimeType: 'text/plain', buffer: Buffer.from(boundary + '!') }, status: 413, error: '40,000 characters' },
    { file: { name: 'blank.txt', mimeType: 'text/plain', buffer: Buffer.from(' \n') }, status: 422, error: 'No readable text' },
    { file: { name: 'encoding.txt', mimeType: 'text/plain', buffer: Buffer.from([255]) }, status: 422, error: 'UTF-8 encoding' },
    { file: { name: 'invalid.json', mimeType: 'application/json', buffer: Buffer.from('{broken') }, status: 422, error: 'JSON file is invalid' },
    { file: { name: 'invalid.csv', mimeType: 'text/csv', buffer: Buffer.from('text,text\none,two') }, status: 422, error: 'column names must not be repeated' },
    { file: join(importDocuments, 'no-text-layer.pdf'), status: 422, error: 'Manually transcribe' },
  ]
  for (const { file, status, error } of invalid) {
    await previewDocument(page, file, status)
    await expect(page.getByRole('alert')).toContainText(error)
    await expect(page.getByRole('heading', { name: 'Content preview', exact: true })).toHaveCount(0)
  }
  const before = previews
  const input = page.getByLabel('Text document')
  const button = page.getByRole('button', { name: 'Preview source text', exact: true })
  await input.setInputFiles({ name: 'empty.txt', mimeType: 'text/plain', buffer: Buffer.alloc(0) })
  await expect(button).toBeDisabled()
  await expect(page.getByRole('alert')).toContainText('This file is empty.')
  await input.setInputFiles({ name: 'maximum-bytes.txt', mimeType: 'text/plain', buffer: Buffer.alloc(12 * 1024 * 1024, 65) })
  await expect(button).toBeEnabled()
  await input.setInputFiles({ name: 'too-many-bytes.txt', mimeType: 'text/plain', buffer: Buffer.alloc(12 * 1024 * 1024 + 1, 65) })
  await expect(page.getByRole('alert')).toContainText('This file exceeds 12 MB.')
  await expect(button).toBeDisabled()
  await input.setInputFiles(join(importDocuments, 'image.png'))
  await expect(page.getByRole('alert')).toContainText('manual text transcript')
  await expect(button).toBeDisabled()
  expect(previews).toBe(before)
  await previewDocument(page, { name: 'recovery.txt', mimeType: 'text/plain', buffer: Buffer.from('Recovery works.') })
  await expect(page.getByRole('alert')).toHaveCount(0)
  await expect(page.getByLabel('Review and correct this passage')).toHaveValue('Recovery works.')
  expect((await importedDataset(page)).total).toBe(0)
  expect(submitted).toEqual([])
  await checkAudioErrorsAndManualDrafts(page)
  expect(submitted).toEqual([])
})
