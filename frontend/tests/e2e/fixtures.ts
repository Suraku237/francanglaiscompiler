import { test as base, expect } from '@playwright/test'
import type { Route } from '@playwright/test'
import { analyzerState, dataset, entry, health, metadata, publicSession, testReport } from '../fixtures'

export interface RecordedRequest {
  method: string
  path: string
  url: URL
  body: unknown
  rawBody: string | null
  headers: Record<string, string>
}

type Handler = (route: Route, request: RecordedRequest) => Promise<void>

export class MockApi {
  readonly requests: RecordedRequest[] = []
  readonly unexpected: string[] = []
  health = health()
  entries = [entry()]
  analyzer = analyzerState()
  testReport = testReport()
  private readonly handlers = new Map<string, Handler>()

  on(method: string, path: string, handler: Handler) {
    this.handlers.set(`${method} ${path}`, handler)
  }

  reply(method: string, path: string, body: unknown, status = 200) {
    this.on(method, path, (route) => route.fulfill({ status, json: body }))
  }

  calls(path: string, method?: string) {
    return this.requests.filter((request) => request.path === path && (!method || request.method === method))
  }

  async handle(route: Route) {
    const request = route.request()
    const url = new URL(request.url())
    const rawBody = request.postData()
    const body: unknown = request.headers()['content-type']?.includes('application/json') && rawBody
      ? JSON.parse(rawBody)
      : null
    const recorded: RecordedRequest = { method: request.method(), path: url.pathname, url, body, rawBody, headers: request.headers() }
    this.requests.push(recorded)
    const handler = this.handlers.get(`${recorded.method} ${recorded.path}`)
    if (handler) {
      await handler(route, recorded)
      return
    }
    if (recorded.method === 'GET') {
      if (recorded.path === '/api/public/session') return route.fulfill({ json: publicSession() })
      if (recorded.path === '/api/health') return route.fulfill({ json: this.health })
      if (recorded.path === '/api/metadata') return route.fulfill({ json: metadata })
      if (recorded.path === '/api/analyzer') return route.fulfill({ json: this.analyzer })
      if (recorded.path === '/api/analyzer/tests') return route.fulfill({ json: this.testReport })
      if (recorded.path === '/api/dataset') {
        const query = url.searchParams.get('query')?.toLowerCase() ?? ''
        const entries = this.entries.filter((item) => [item.text, item.french_gloss, item.english_gloss]
          .some((value) => value.toLowerCase().includes(query)))
        return route.fulfill({ json: { ...dataset(this.entries), entries } })
      }
    }
    this.unexpected.push(`${recorded.method} ${recorded.path}`)
    await route.fulfill({ status: 501, json: { detail: 'Unexpected API request in isolated browser test.' } })
  }
}

export const test = base.extend<{ api: MockApi }>({
  api: [async ({ context, baseURL }, use) => {
    const api = new MockApi()
    const externalRequests: string[] = []
    const pageErrors: string[] = []
    const origin = new URL(baseURL ?? '').origin
    context.on('page', (page) => page.on('pageerror', (error) => pageErrors.push(error.message)))
    await context.addInitScript(() => {
      Object.defineProperty(window, 'SpeechRecognition', { configurable: true, value: undefined })
      Object.defineProperty(window, 'webkitSpeechRecognition', { configurable: true, value: undefined })
      Object.defineProperty(window, 'speechSynthesis', {
        configurable: true,
        value: {
          cancel() {},
          getVoices() { return [] },
          speak() { throw new Error('Real speech output is forbidden in browser tests.') },
        },
      })
      Object.defineProperty(navigator, 'mediaDevices', {
        configurable: true,
        value: { getUserMedia: () => Promise.reject(new Error('Real microphone access is forbidden in browser tests.')) },
      })
    })
    await context.route('**/*', async (route) => {
      const url = new URL(route.request().url())
      if (url.origin !== origin) {
        externalRequests.push(url.origin)
        await route.abort('blockedbyclient')
      } else if (url.pathname.startsWith('/api/')) {
        await api.handle(route)
      } else {
        await route.continue()
      }
    })
    await use(api)
    await context.unrouteAll({ behavior: 'ignoreErrors' })
    expect(api.unexpected, 'Every API request must have an isolated fixture; no backend passthrough is allowed.').toEqual([])
    expect(api.requests.filter((request) => /^\/api\/(?:auth|workspace|coursework|imports?|translate|chat)(?:\/|$)/.test(request.path)),
      'Public workflows must never call account, maintenance or retired generation endpoints.').toEqual([])
    expect(api.requests.filter((request) => request.method !== 'GET' && !['/api/analyzer/tests', '/api/analyzer/analyze', '/api/analyze', '/api/readings/lookup'].includes(request.path)),
      'Only analysis, immutable tests and recording lookup may use POST requests.').toEqual([])
    for (const request of api.requests.filter((request) => request.method === 'POST')) {
      expect(request.headers['x-csrf-token'], 'Every POST needs the public browser CSRF token.').toBe('test-csrf')
      expect(request.headers.origin, 'Every POST is same-origin.').toBe(origin)
    }
    expect(externalRequests, 'No provider, external asset, or other origin may be contacted.').toEqual([])
    expect(pageErrors, 'The browser must not encounter uncaught application errors.').toEqual([])
  }, { auto: true }],
})

export { expect }
