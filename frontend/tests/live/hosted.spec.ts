import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { readFile, readdir } from 'node:fs/promises'
import { join } from 'node:path'
import { randomUUID } from 'node:crypto'
import type { Dataset } from '../../src/types'
import type { RecordedTest, TestReport } from '../../src/analyzerTypes'
import type { CourseworkState } from '../../src/courseworkTypes'
import { checkAudioErrorsAndManualDrafts, recordPrivateAudio } from './audioWorkflows'
import { openGrammarSettings } from '../browserGrammar'

const password = 'Live-browser-test-passphrase-2026!'

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

async function importedDataset(page: Page): Promise<Dataset> {
  const response = await page.request.get('/api/dataset')
  expect(response.ok()).toBe(true)
  return response.json()
}

function processingRequests(page: Page): string[] {
  const requests: string[] = []
  page.on('request', (request) => {
    const path = new URL(request.url()).pathname
    if (['/api/translate', '/api/chat', '/api/imports/suggest', '/api/coursework/explain', '/api/coursework/export'].includes(path)) requests.push(path)
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
  const email = await signUp(page)
  await exerciseCompiler(page)
  const privateTests: TestReport = await (await page.request.get('/api/analyzer/tests')).json()
  const privateTest = privateTests.tests[0]
  if (!privateTest) throw new Error('Expected a retained private compiler test.')
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
    const otherTests = await other.request.get('/api/analyzer/tests')
    expect(otherTests.ok()).toBe(true)
    expect((await otherTests.json()).summary.total).toBe(0)
    expect((await other.request.get(`/api/analyzer/tests/${privateTest.id}`)).status()).toBe(404)
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
    expect((await page.request.get('/api/analyzer/tests')).status()).toBe(401)
  } finally {
    await sharedTab.close()
  }
  await page.getByLabel('Email address').fill(email)
  await page.getByLabel(/^Password/).fill(password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Analysis', exact: true }).click()
  await expect(page.getByRole('group', { name: 'Tests recorded', exact: true })).toContainText('3')
  await page.getByRole('button', { name: 'Inspect test 1', exact: true }).click()
  expect(await page.getByLabel('Analyzed source text').textContent()).toBe('  123\t')
})

test('grammar-only saving preserves legacy project notes, history and project isolation without report tools', async ({ page }) => {
  await signUp(page)
  const submitted = processingRequests(page)
  const navigation = page.getByRole('navigation', { name: 'Main navigation' })
  const session = await (await page.request.get('/api/auth/session')).json()
  const headers = { 'X-CSRF-Token': session.csrf_token, Origin: 'http://127.0.0.1:4190' }
  const originalResponse = await page.request.get('/api/coursework')
  expect(originalResponse.status()).toBe(200)
  const original: CourseworkState = await originalResponse.json()
  const legacyProfile = {
    ...original.project,
    grammar: 'S -> NOUN',
    discussion: 'Existing synthetic report notes, not fieldwork.',
    collection_method: 'Existing synthetic provenance notes.',
    grammar_rationale: 'Existing synthetic grammar rationale.',
  }
  const savedProfile = await page.request.put('/api/coursework/project', { headers, data: legacyProfile })
  expect(savedProfile.status(), await savedProfile.text()).toBe(200)
  const legacy = await page.request.post('/api/workspace/history', {
    headers,
    data: { kind: 'translation', title: 'Legacy synthetic item', content: {
      source_text: '  Tchop\t ', source_language: 'francanglais', target_language: 'en',
      translation: 'to eat', explanation: 'Synthetic old history fixture, not generated during this run.', note: 'Not fieldwork.',
    } },
  })
  expect(legacy.status(), await legacy.text()).toBe(201)
  const historyBefore = await (await page.request.get('/api/workspace/history')).json()
  expect(historyBefore.entries).toHaveLength(1)
  const otherProject = await page.request.post('/api/workspace/projects', { headers, data: { name: 'Synthetic second project' } })
  expect(otherProject.status(), await otherProject.text()).toBe(201)
  for (const retired of ['history', 'settings', 'imports']) {
    await page.goto(`/#${retired}`)
    await expect(page).toHaveURL(/#compiler$/)
    await expect(navigation.getByRole('link')).toHaveText(['Franc Analyzer', 'Analysis', 'Collection', 'Dictionary', 'Synthetic examples'])
  }
  await openGrammarSettings(page)
  await page.getByLabel('Context-free grammar').fill('S -> VERB')
  await page.getByRole('button', { name: 'Save grammar', exact: true }).click()
  await expect(page.getByText(/Grammar saved privately/)).toBeVisible()
  const retainedProfile: CourseworkState = await (await page.request.get('/api/coursework')).json()
  expect(retainedProfile.project).toEqual({ ...legacyProfile, grammar: 'S -> VERB' })
  await expect(page.getByRole('button', { name: /Download coursework|Upload screenshot|Save project/ })).toHaveCount(0)
  await expect(page.getByLabel(/Linguistic discussion|Group member/)).toHaveCount(0)
  await page.getByRole('link', { name: 'Back to Franc Analyzer' }).click()
  await page.getByLabel('Statement to analyze').fill('Veux')
  const recordedResponse = page.waitForResponse((response) => response.url().endsWith('/api/analyzer/tests') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Analyze', exact: true }).click()
  const recorded: RecordedTest = await (await recordedResponse).json()
  await expect(page.getByText('ACCEPT', { exact: true })).toBeVisible()
  await addEntry(page, 'Synthetic persistent term')
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Synthetic persistent term', exact: true })).toBeVisible()
  await openGrammarSettings(page)
  await expect(page.getByLabel('Context-free grammar')).toHaveValue('S -> VERB')
  await expect(page.getByLabel('Active project')).toContainText('Synthetic second project')
  page.once('dialog', (dialog) => dialog.accept())
  const [otherProjectId] = await page.getByLabel('Active project').selectOption({ label: 'Synthetic second project' })
  if (!otherProjectId) throw new Error('Expected the isolated second project selection.')
  await navigation.getByRole('link', { name: 'Collection', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'No collected statements yet' })).toBeVisible()
  await navigation.getByRole('link', { name: 'Franc Analyzer', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Franc Analyzer', exact: true })).toBeVisible()
  await expect(page.getByLabel('Statement to analyze')).toHaveValue('')
  await expect(page.getByLabel('Context-free grammar')).toHaveCount(0)
  await openGrammarSettings(page)
  await expect(page.getByLabel('Context-free grammar')).not.toHaveValue('S -> VERB')
  await expect(page.getByRole('heading', { name: 'No saved tests yet' })).toBeVisible()
  const inaccessibleTest = await page.request.get(`/api/analyzer/tests/${recorded.id}`, { headers: { 'X-Mboa-Project': otherProjectId } })
  expect(inaccessibleTest.status()).toBe(404)
  const retainedHistory = await page.request.get('/api/workspace/history', { headers: { 'X-Mboa-Project': 'default' } })
  expect(retainedHistory.status()).toBe(200)
  expect((await retainedHistory.json()).entries).toEqual(historyBefore.entries)
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByLabel('Active project').selectOption('default')
  await expect(page.getByRole('group', { name: 'Tests recorded', exact: true })).toContainText('1')
  await page.getByRole('button', { name: 'Inspect test 1', exact: true }).click()
  await expect(page.getByLabel('Analyzed source text')).toHaveText('Veux')
  expect(submitted).toEqual([])
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('real password recovery revokes existing sessions and replaces the old password', async ({ page, browser }) => {
  const email = await signUp(page)
  const recoveryContext = await browser.newContext({ baseURL: 'http://127.0.0.1:4190' })
  try {
    const recovery = await recoveryContext.newPage()
    await recovery.goto('/#forgot-password')
    await recovery.getByLabel('Email address').fill(email)
    await recovery.getByRole('button', { name: 'Send email', exact: true }).click()
    await expect(recovery.getByRole('status').filter({ hasText: 'reset link' })).toBeVisible()
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
  await expect(page.getByRole('heading', { name: 'Franc Analyzer', exact: true })).toBeVisible()
  await expect(page.getByRole('tab')).toHaveCount(0)
  await expect(page.getByLabel('Statement to analyze')).toBeVisible()
  await expect(page.getByText('Grammar settings', { exact: true })).toHaveCount(0)
  await page.getByLabel('Statement to analyze').fill('  123\t')
  await openGrammarSettings(page)
  await page.getByLabel('Context-free grammar').fill('S -> S NUMBER | NUMBER')
  await page.getByRole('link', { name: 'Back to Franc Analyzer' }).click()
  const firstRun = page.waitForResponse((response) => response.url().endsWith('/api/analyzer/tests') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Analyze', exact: true }).click()
  const response = await firstRun
  expect(response.status(), await response.text()).toBe(200)
  const analyzed: RecordedTest = await response.json()
  expect(response.request().postDataJSON()).toEqual({ request_id: expect.any(String), text: '  123\t', grammar: 'S -> S NUMBER | NUMBER' })
  expect(analyzed.text).toBe('  123\t')
  expect(analyzed.lexical.tokens).toEqual([{ text: '123', category: 'NUMBER' }])
  expect(analyzed.parse.accepted).toBe(true)
  expect(analyzed.grammar.is_ll1).toBe(true)
  expect(analyzed.metadata.matching_entries).toBe(0)
  const session = await (await page.request.get('/api/auth/session')).json()
  const retried = await page.request.post('/api/analyzer/tests', {
    headers: { 'X-CSRF-Token': session.csrf_token, Origin: 'http://127.0.0.1:4190' },
    data: response.request().postDataJSON(),
  })
  expect(retried.status(), await retried.text()).toBe(200)
  expect(await retried.json()).toEqual(analyzed)
  await expect(page.getByRole('heading', { name: 'Parser result', exact: true })).toBeVisible()
  expect(await page.getByLabel('Analyzed source text').textContent()).toBe('  123\t')
  await expect(page.getByRole('region', { name: 'Lexical tokens in source order' })).toContainText('123NUMBER')
  await page.getByRole('link', { name: 'View detailed analysis' }).click()
  await expect(page.getByRole('heading', { name: 'Analyzed sentence or word', exact: true })).toBeVisible()
  await expect(page.getByRole('group', { name: 'Tests recorded', exact: true })).toContainText('1')
  await page.getByText('Parser trace for this input', { exact: true }).click()
  await expect(page.getByRole('region', { name: 'Table-driven parser step trace' })).toBeVisible()
  await page.getByText('Saved grammar, transformations & FIRST/FOLLOW', { exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Computed grammar' })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Computed FIRST and FOLLOW sets' })).toBeVisible()
  await expect(page.getByText('LL(1) · no table conflicts', { exact: true })).toBeVisible()
  await openGrammarSettings(page)
  await page.getByLabel('Context-free grammar').fill('S -> A NUMBER\nA -> NUMBER | epsilon')
  await page.getByRole('link', { name: 'Back to Franc Analyzer' }).click()
  await page.getByRole('button', { name: 'Analyze', exact: true }).click()
  await expect(page.getByText('REJECT', { exact: true })).toBeVisible()
  await page.getByRole('link', { name: 'View detailed analysis' }).click()
  await page.getByText('Saved grammar, transformations & FIRST/FOLLOW', { exact: true }).click()
  await expect(page.getByText('Not LL(1) · inspect conflicts', { exact: true })).toBeVisible()
  await expect(page.getByText('A deterministic LL(1) choice is not available.', { exact: true })).toBeVisible()
  await openGrammarSettings(page)
  await page.getByLabel('Context-free grammar').fill('S -> epsilon')
  await page.getByRole('link', { name: 'Back to Franc Analyzer' }).click()
  await page.getByLabel('Statement to analyze').fill('')
  await page.getByRole('button', { name: 'Analyze', exact: true }).click()
  await expect(page.getByText('ACCEPT', { exact: true })).toBeVisible()
  await expect(page.getByLabel('Analyzed source text')).toHaveText('(empty input)')
  await page.getByRole('link', { name: 'View detailed analysis' }).click()
  await page.getByText('Token details for this test', { exact: true }).click()
  await expect(page.getByText('No lexical tokens. The parser will see only $.')).toBeVisible()
  await openGrammarSettings(page)
  await page.getByRole('button', { name: 'Save grammar', exact: true }).click()
  await expect(page.getByText(/Grammar saved privately/)).toBeVisible()
  await page.reload()
  await openGrammarSettings(page)
  await expect(page.getByLabel('Context-free grammar')).toHaveValue('S -> epsilon')
  await expect(page.getByRole('group', { name: 'Tests recorded', exact: true })).toContainText('3')
  const allTestsResponse = await page.request.get('/api/analyzer/tests')
  expect(allTestsResponse.ok()).toBe(true)
  const allTests: TestReport = await allTestsResponse.json()
  expect(allTests.summary).toMatchObject({ total: 3, accepted: 2, rejected: 1 })
  expect(allTests.statistics.total_tokens).toBe(2)
  await page.getByRole('button', { name: 'Inspect test 1', exact: true }).click()
  expect(await page.getByLabel('Analyzed source text').textContent()).toBe('  123\t')
  await page.getByText('Saved grammar, transformations & FIRST/FOLLOW', { exact: true }).click()
  await expect(page.getByRole('region', { name: 'Analyzed sentence or word' })).toContainText('S -> S NUMBER | NUMBER')
  await expect(page.getByRole('button', { name: /Download coursework|Save project|Upload screenshot/ })).toHaveCount(0)
  expect((await importedDataset(page)).total).toBe(0)
  expect(submitted).toEqual([])
}

test('manual statement and French meaning persist unreviewed while all explicit tests remain recorded', async ({ page }) => {
  await signUp(page)
  const submitted = processingRequests(page)
  const navigation = page.getByRole('navigation', { name: 'Main navigation' })
  const text = '  Le taxi\tdon refuse.\n'
  const meaning = '  Le taxi a refus\u00e9.\n'
  await navigation.getByRole('link', { name: 'Collection', exact: true }).click()
  await page.getByRole('button', { name: 'Add entry', exact: true }).click()
  const editor = page.getByRole('dialog', { name: 'Add collection entry' })
  await editor.getByRole('textbox', { name: /^Expression/ }).fill(text)
  await editor.getByLabel(/^French meaning/).fill(meaning)
  await editor.getByRole('combobox', { name: 'Language', exact: true }).selectOption('francanglais')
  await editor.getByLabel(/^Context & notes/).fill('Synthetic test fixture, not fieldwork.')
  expect((await importedDataset(page)).total).toBe(0)
  await editor.getByRole('button', { name: 'Save unreviewed', exact: true }).click()
  await expect(editor).not.toBeVisible()
  await page.reload()
  const saved = await importedDataset(page)
  expect(saved.total).toBe(1)
  expect(saved.entries).toHaveLength(1)
  const entry = saved.entries[0]
  if (!entry) throw new Error('Expected the explicitly saved synthetic statement.')
  expect(entry).toMatchObject({
    text, review_status: 'unreviewed', french_gloss: meaning, english_gloss: '', entry_type: 'Sentence',
    language: 'francanglais', source_location: '', contributor: '', notes: 'Synthetic test fixture, not fieldwork.',
  })
  await page.getByRole('button', { name: /^Edit expression:/ }).click()
  const review = page.getByRole('dialog', { name: 'Review collection entry' })
  await expect(review.getByRole('textbox', { name: /^Expression/ })).toHaveValue(text)
  await expect(review.getByLabel(/^French meaning/)).toHaveValue(meaning)
  await review.getByRole('button', { name: 'Cancel', exact: true }).click()
  const beforeTests = await page.request.get('/api/analyzer/tests')
  expect((await beforeTests.json()).summary.total).toBe(0)
  await navigation.getByRole('link', { name: 'Franc Analyzer', exact: true }).click()
  await page.getByLabel('Statement to analyze').fill(text)
  await openGrammarSettings(page)
  await page.getByLabel('Context-free grammar').fill('S -> NOUN')
  await page.getByRole('link', { name: 'Back to Franc Analyzer' }).click()
  const computation = page.waitForResponse((response) => response.url().endsWith('/api/analyzer/tests') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Analyze', exact: true }).click()
  const response = await computation
  expect(response.status(), await response.text()).toBe(200)
  const analysis: RecordedTest = await response.json()
  expect(analysis.text).toBe(text)
  expect(analysis.parse.accepted).toBe(false)
  expect(analysis.lexical.statistics.total_tokens).toBe(5)
  expect(analysis.metadata.matching_entries).toBe(1)
  expect(analysis.metadata.languages).toEqual(['francanglais'])
  await page.getByRole('link', { name: 'View detailed analysis' }).click()
  await expect(page.getByRole('group', { name: 'Tests recorded', exact: true })).toContainText('1')
  expect(await page.getByLabel('Analyzed source text').textContent()).toBe(text)
  expect((await importedDataset(page)).entries[0]?.review_status).toBe('unreviewed')
  await exerciseTokenAnalysis(page)
  expect(submitted).toEqual([])
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

async function exerciseTokenAnalysis(page: Page) {
  const saved = await importedDataset(page)
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Franc Analyzer', exact: true }).click()
  await page.getByLabel('Statement to analyze').fill('je Veux acheter')
  await openGrammarSettings(page)
  await page.getByLabel('Context-free grammar').fill('S -> FRENCH_FUNCTION_WORD VERB VERB')
  await page.getByRole('link', { name: 'Back to Franc Analyzer' }).click()
  const acceptedRun = page.waitForResponse((response) => response.url().endsWith('/api/analyzer/tests') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Analyze', exact: true }).click()
  const accepted: RecordedTest = await (await acceptedRun).json()
  expect(accepted.lexical.tokens).toEqual([
    { text: 'je', category: 'FRENCH_FUNCTION_WORD' },
    { text: 'Veux', category: 'VERB' },
    { text: 'acheter', category: 'VERB' },
  ])
  expect(accepted.parse.accepted).toBe(true)
  await expect(page.getByText('ACCEPT', { exact: true })).toBeVisible()
  await expect(page.getByLabel('Analyzed source text')).toHaveText('je Veux acheter')
  await expect(page.getByRole('region', { name: 'Lexical tokens in source order' }).getByRole('row')).toHaveText(['#Observed textLexer category', '1jeFRENCH_FUNCTION_WORD', '2VeuxVERB', '3acheterVERB'])

  await openGrammarSettings(page)
  await page.getByLabel('Context-free grammar').fill('S -> VERB')
  await page.getByRole('link', { name: 'Back to Franc Analyzer' }).click()
  await page.getByLabel('Statement to analyze').fill('Veux')
  const wordRun = page.waitForResponse((response) => response.url().endsWith('/api/analyzer/tests') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Analyze', exact: true }).click()
  const word: RecordedTest = await (await wordRun).json()
  expect(word.lexical.tokens).toEqual([{ text: 'Veux', category: 'VERB' }])
  expect(word.parse.accepted).toBe(true)
  await expect(page.getByLabel('Analyzed source text')).toHaveText('Veux')
  await expect(page.getByText('ACCEPT', { exact: true })).toBeVisible()
  const repeatedRun = page.waitForResponse((response) => response.url().endsWith('/api/analyzer/tests') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Analyze', exact: true }).click()
  const repeated: RecordedTest = await (await repeatedRun).json()
  expect(repeated.id).not.toBe(word.id)
  expect(repeated.text).toBe(word.text)
  await expect(page.getByRole('region', { name: 'Parser result' })).toBeVisible()
  await page.getByRole('link', { name: 'View detailed analysis' }).click()
  await expect(page.getByLabel('Analyzed source text')).toHaveText('Veux')

  const text = '  Je veux veux, VEUX + + 12\t'
  await openGrammarSettings(page)
  await page.getByLabel('Context-free grammar').fill('S -> NOUN')
  await page.getByRole('link', { name: 'Back to Franc Analyzer' }).click()
  await page.getByLabel('Statement to analyze').fill(text)
  const frequencyRun = page.waitForResponse((response) => response.url().endsWith('/api/analyzer/tests') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Analyze', exact: true }).click()
  const response = await frequencyRun
  expect(response.status(), await response.text()).toBe(200)
  const result: RecordedTest = await response.json()
  expect(result.text).toBe(text)
  expect(result.parse.accepted).toBe(false)
  expect(result.lexical.statistics.total_tokens).toBe(8)
  expect(result.lexical.statistics.frequencies).toEqual([
    { token: 'veux', count: 3 }, { token: '+', count: 2 }, { token: 'je', count: 1 },
    { token: ',', count: 1 }, { token: '12', count: 1 },
  ])
  await expect(page.getByText('REJECT', { exact: true })).toBeVisible()
  expect(await page.getByLabel('Analyzed source text').textContent()).toBe(text)
  await expect(page.getByRole('region', { name: 'Lexical tokens in source order' }).getByRole('row')).toHaveCount(9)
  await page.getByRole('link', { name: 'View detailed analysis' }).click()
  const sentence = page.getByRole('region', { name: 'Analyzed sentence or word' })
  expect(await sentence.getByLabel('Analyzed source text').textContent()).toBe(text)
  await sentence.getByText('Token details for this test', { exact: true }).click()
  await expect(sentence.getByText('8 tokens · 5 distinct forms', { exact: true })).toBeVisible()
  await expect(sentence.getByRole('region', { name: 'Lexical tokens in source order' }).getByRole('row')).toHaveCount(9)
  await expect(sentence.getByRole('region', { name: 'Observed token frequencies' }).getByRole('row')).toHaveText(['TokenCount', 'veux3', '+2', 'je1', ',1', '121'])
  await expect(sentence.getByRole('region', { name: 'Token category frequencies' }).getByRole('row')).toHaveText(['CategoryCount', 'FRENCH_FUNCTION_WORD1', 'VERB3', 'PUNCTUATION1', 'UNKNOWN2', 'NUMBER1'])
  const reportResponse = await page.request.get('/api/analyzer/tests')
  expect(reportResponse.ok()).toBe(true)
  const report: TestReport = await reportResponse.json()
  expect(report.summary).toMatchObject({ total: 5, accepted: 3, rejected: 2, acceptance_rate: 60 })
  expect(report.statistics.total_tokens).toBe(18)
  expect(report.statistics.frequencies).toContainEqual({ token: 'veux', count: 6 })
  expect(report.statistics.raw_frequencies).toContainEqual({ token: 'Veux', count: 3 })
  expect(report.statistics.raw_frequencies).toContainEqual({ token: 'veux', count: 2 })
  expect(report.statistics.raw_frequencies).toContainEqual({ token: 'VEUX', count: 1 })
  expect(report.unknown_review).toContainEqual({ token: '+', count: 2, tests: 1, forms: ['+'] })
  await expect(page.getByRole('group', { name: 'Tests recorded', exact: true })).toContainText('5')
  await expect(page.getByRole('group', { name: 'Acceptance rate' })).toContainText('60%')
  expect((await importedDataset(page)).entries).toEqual(saved.entries)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.goBack()
  await expect(page.getByLabel('Statement to analyze')).toHaveValue(text)
  await expect(page.getByText('REJECT', { exact: true })).toBeVisible()
  await page.goForward()
  await expect(page).toHaveTitle('Analysis — Mboa Compiler')
  await sentence.getByText('Token details for this test', { exact: true }).click()
  await expect(sentence.getByText('8 tokens · 5 distinct forms', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('group', { name: 'Tests recorded', exact: true })).toContainText('5')
  await page.getByRole('button', { name: 'Inspect test 5', exact: true }).click()
  expect(await page.getByLabel('Analyzed source text').textContent()).toBe(text)
  expect((await importedDataset(page)).entries).toEqual(saved.entries)
}

test('manual collection audio errors recover without importing or transcribing documents', async ({ page }) => {
  await signUp(page)
  const submitted = processingRequests(page)
  expect((await importedDataset(page)).total).toBe(0)
  await checkAudioErrorsAndManualDrafts(page)
  expect(submitted).toEqual([])
})
