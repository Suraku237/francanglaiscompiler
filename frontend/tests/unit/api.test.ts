import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, configureSession, errorDetail, nativeApiUrl } from '../../src/api'
import { deferred, jsonResponse, rejectOnAbort } from '../helpers'

afterEach(() => { vi.useRealTimers(); configureSession(null) })

describe('public CSRF browser transport', () => {
  it.each(['/analyze', '/analyzer/analyze', '/analyzer/tests', '/readings/lookup'])('sends CSRF and same-origin cookies on POST %s without project or account headers', async (path) => {
    configureSession('test-csrf')
    vi.mocked(fetch).mockImplementation(async () => jsonResponse({ id: 'entry' }))
    await api(path, { method: 'POST', body: { text: 'Public phrase' } })
    expect(vi.mocked(fetch).mock.calls[0]?.[1]?.headers).toEqual({
      'Content-Type': 'application/json', 'X-CSRF-Token': 'test-csrf',
    })
    expect(vi.mocked(fetch).mock.calls[0]?.[1]?.credentials).toBe('same-origin')
    expect(nativeApiUrl('/dataset/entry/audio')).toBe('/api/dataset/entry/audio')
    configureSession('second-csrf')
    await api(path, { method: 'POST', body: { text: 'Another public phrase' } })
    expect(vi.mocked(fetch).mock.calls[1]?.[1]?.headers).toEqual({
      'Content-Type': 'application/json', 'X-CSRF-Token': 'second-csrf',
    })
    expect(nativeApiUrl('/dataset/entry/audio')).toBe('/api/dataset/entry/audio')
  })

  it.each(['/analyzer/tests', '/readings/lookup'])('surfaces a 401 at %s without a forced login event or retry', async (path) => {
    const expired = vi.fn()
    window.addEventListener('mboa:session-expired', expired)
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: 'Request could not be authorized.' }, 401))
    await expect(api(path, { method: 'POST', body: {} })).rejects.toMatchObject({ status: 401 })
    expect(expired).not.toHaveBeenCalled()
    expect(fetch).toHaveBeenCalledOnce()
    window.removeEventListener('mboa:session-expired', expired)
  })

  it('discards a late response when the public browser session is reinitialized', async () => {
    configureSession('original-session')
    const body = deferred<unknown>()
    const response = jsonResponse({})
    vi.spyOn(response, 'json').mockImplementation(() => body.promise)
    vi.mocked(fetch).mockResolvedValue(response)
    const pending = api('/dataset')
    await vi.waitFor(() => expect(response.json).toHaveBeenCalledOnce())
    configureSession('replacement-session')
    body.resolve({ entries: [{ text: 'Public reference data', ownership: { can_edit: false } }] })
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' })
  })
})

describe('API response and error contracts', () => {
  it('sends JSON only when there is a body, without caching API reads', async () => {
    const fetchMock = vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ saved: true }))
      .mockResolvedValueOnce(jsonResponse({ status: 'ok' }))

    await expect(api('/analyzer/tests', { method: 'POST', body: { text: 'Fixture' } })).resolves.toEqual({ saved: true })
    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/analyzer/tests', expect.objectContaining({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{"text":"Fixture"}',
      cache: 'no-store',
      signal: expect.any(AbortSignal),
    }))
    await api('/health')
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/health', expect.objectContaining({
      method: 'GET', body: undefined, headers: undefined, cache: 'no-store',
    }))
  })

  it('retains HTTP status and readable field-validation errors', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({
      detail: [
        { loc: ['body', 'source_language'], msg: 'Choose a supported language' },
        { loc: ['body', 'text'], msg: 'An expression is required' },
      ],
    }, 422))

    await expect(api('/analyze', { method: 'POST', body: {} })).rejects.toEqual(
      new ApiError('source language: Choose a supported language. text: An expression is required', 422),
    )
  })

  it.each([
    { body: { detail: 'Review consent first.' }, expected: 'Review consent first.' },
    { body: { detail: [null, {}, { msg: 'Invalid input' }, { loc: ['body', 'items', 0, 'name'], msg: 'Required' }] }, expected: 'Invalid input. items → name: Required' },
    { body: { detail: [{ loc: ['body', 'text'] }] }, expected: null },
    { body: null, expected: null },
    { body: 'not an error object', expected: null },
  ])('extracts safe detail text from $body', ({ body, expected }) => {
    expect(errorDetail(body)).toBe(expected)
  })

  it.each([
    { status: 503, message: 'The service is not ready.' },
    { status: 500, message: 'The request could not be completed (500).' },
  ])('gives an actionable fallback for non-JSON HTTP $status', async ({ status, message }) => {
    vi.mocked(fetch).mockResolvedValue(new Response('<html>unavailable</html>', { status }))
    await expect(api('/health')).rejects.toThrow(message)
  })

  it('rejects an unreadable successful response rather than treating it as data', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response('not JSON', { status: 200 }))
    await expect(api('/metadata')).rejects.toThrow('The server returned an unreadable response.')
  })

  it.each([
    { path: '/analyze', method: 'POST' as const, message: 'Cannot reach the server.' },
    { path: '/readings/lookup', method: 'POST' as const, message: 'Cannot reach the server.' },
    { path: '/analyzer/tests', method: 'POST' as const, message: 'The change may have completed. Open Analysis and refresh saved tests' },
  ])('distinguishes read failures from uncertain mutations at $path', async ({ path, method, message }) => {
    vi.mocked(fetch).mockRejectedValue(new TypeError('Failed to fetch'))
    await expect(api(path, { method, body: {} })).rejects.toThrow(message)
  })

  it('preserves the explicit stale-grammar conflict rather than retrying with other grammar', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: 'Saved grammar changed. Reload the saved grammar.' }, 409))
    await expect(api('/analyzer/tests', { method: 'POST', body: { text: 'Fixture', grammar: 'S -> NOUN' } }))
      .rejects.toMatchObject({ status: 409, message: 'Saved grammar changed. Reload the saved grammar.' })
    expect(fetch).toHaveBeenCalledOnce()
  })

  it('discloses uncertain recorded-test completion after an unreadable success response', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response('not JSON', { status: 200 }))
    await expect(api('/analyzer/tests', { method: 'POST', body: {} })).rejects.toThrow('The change may have completed. Open Analysis and refresh saved tests')
  })
})

describe('API cancellation and time limits', () => {
  it('propagates an already aborted caller signal silently as AbortError', async () => {
    const controller = new AbortController()
    controller.abort()
    vi.mocked(fetch).mockImplementation(rejectOnAbort)
    await expect(api('/analyze', { signal: controller.signal })).rejects.toMatchObject({ name: 'AbortError' })
    expect(vi.mocked(fetch).mock.calls[0]?.[1]?.signal?.aborted).toBe(true)
  })

  it('aborts an in-flight fetch when its caller cancels', async () => {
    const controller = new AbortController()
    vi.mocked(fetch).mockImplementation(rejectOnAbort)
    const request = expect(api('/analyze', { signal: controller.signal })).rejects.toMatchObject({ name: 'AbortError' })
    controller.abort()
    await request
    expect(vi.mocked(fetch).mock.calls[0]?.[1]?.signal?.aborted).toBe(true)
  })

  it.each([
    { path: '/analyze', method: 'POST' as const, message: 'This is taking longer than expected.' },
    { path: '/readings/lookup', method: 'POST' as const, message: 'This is taking longer than expected.' },
    { path: '/analyzer/tests', method: 'POST' as const, message: 'The change may have completed. Open Analysis and refresh saved tests' },
  ])('aborts timed-out $path requests with the correct recovery guidance', async ({ path, method, message }) => {
    vi.useFakeTimers()
    vi.mocked(fetch).mockImplementation(rejectOnAbort)
    const request = expect(api(path, { method, timeout: 50 })).rejects.toThrow(message)
    await vi.advanceTimersByTimeAsync(50)
    await request
    expect(vi.mocked(fetch).mock.calls[0]?.[1]?.signal?.aborted).toBe(true)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('cleans up the deadline and caller abort listener on success', async () => {
    vi.useFakeTimers()
    const controller = new AbortController()
    const remove = vi.spyOn(controller.signal, 'removeEventListener')
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ ok: true }))
    await api('/health', { signal: controller.signal })
    expect(remove).toHaveBeenCalledWith('abort', expect.any(Function))
    expect(vi.getTimerCount()).toBe(0)
  })
})
