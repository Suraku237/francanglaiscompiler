import { expect } from '@playwright/test'
import type { APIRequestContext, BrowserContext, Page } from '@playwright/test'
import type { PublicSessionInfo } from '../../src/PublicSession'
import type { RecordedTest } from '../../src/analyzerTypes'

export const origin = 'http://127.0.0.1:4190'
export const readOnlyOwnership = { owner_id: null, owner_name: '', can_edit: false }

export async function publicHeaders(request: APIRequestContext) {
  const response = await request.get('/api/public/session')
  expect(response.status(), await response.text()).toBe(200)
  const session: PublicSessionInfo = await response.json()
  expect(session.access_mode).toBe('public_read_only')
  expect(session.capabilities).toEqual({ analyze: true, save_tests: true, edit_collection: false, edit_grammar: false, edit_recordings: false })
  expect(session.csrf_token).toBeTruthy()
  return { Origin: origin, 'X-CSRF-Token': session.csrf_token }
}

export async function protectPublicContext(context: BrowserContext) {
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

export async function analyzePublicInput(page: Page, text: string): Promise<RecordedTest> {
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Franc Analyzer', exact: true }).click()
  await page.getByLabel('Statement to analyze').fill(text)
  const response = page.waitForResponse((item) => new URL(item.url()).pathname === '/api/analyzer/tests' && item.request().method() === 'POST')
  await page.getByRole('button', { name: 'Analyze', exact: true }).click()
  const saved = await response
  expect(saved.status(), await saved.text()).toBe(200)
  await expect(page.getByRole('region', { name: 'Vocabulary result', exact: true })).toBeVisible()
  const record: RecordedTest = await saved.json()
  expect(record.ownership).toEqual(readOnlyOwnership)
  return record
}
