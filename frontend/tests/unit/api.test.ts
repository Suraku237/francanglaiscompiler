import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, errorDetail } from '../../src/api'
import { jsonResponse, rejectOnAbort } from '../helpers'

afterEach(() => vi.useRealTimers())

describe('API response and error contracts', () => {
  it('sends JSON only when there is a body, without caching API reads', async () => {
    const fetchMock = vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ saved: true }))
      .mockResolvedValueOnce(jsonResponse({ status: 'ok' }))

    await expect(api('/dataset', { method: 'POST', body: { text: 'Fixture' } })).resolves.toEqual({ saved: true })
    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/dataset', expect.objectContaining({
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

  it('leaves multipart boundaries to fetch and accepts an empty 204 deletion response', async () => {
    const body = new FormData()
    body.append('file', new File(['Fixture'], 'fixture.txt', { type: 'text/plain' }))
    const fetchMock = vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ text: 'Fixture' }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))

    await api('/imports/preview', { method: 'POST', body })
    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/imports/preview', expect.objectContaining({
      body, headers: undefined,
    }))
    await expect(api('/dataset/fixture', { method: 'DELETE' })).resolves.toBeUndefined()
  })

  it('retains HTTP status and readable field-validation errors', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({
      detail: [
        { loc: ['body', 'source_language'], msg: 'Choose a supported language' },
        { loc: ['body', 'text'], msg: 'An expression is required' },
      ],
    }, 422))

    await expect(api('/translate', { method: 'POST', body: {} })).rejects.toEqual(
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
    { path: '/translate', method: 'POST' as const, message: 'Cannot reach the local server.' },
    { path: '/dataset/fixture', method: 'PATCH' as const, message: 'The change may have completed. Close this dialog and refresh the collection' },
    { path: '/coursework/project', method: 'PUT' as const, message: 'The change may have completed. Refresh the saved coursework evidence' },
  ])('distinguishes read failures from uncertain mutations at $path', async ({ path, method, message }) => {
    vi.mocked(fetch).mockRejectedValue(new TypeError('Failed to fetch'))
    await expect(api(path, { method, body: {} })).rejects.toThrow(message)
  })

  it('discloses uncertain completion after an interrupted audio upload', async () => {
    vi.mocked(fetch).mockRejectedValue(new TypeError('Upload connection interrupted'))
    await expect(api('/dataset/audio', { method: 'POST', body: new FormData() }))
      .rejects.toThrow('The change may have completed. Close this dialog and refresh the collection')
  })
})

describe('API cancellation and time limits', () => {
  it('propagates an already aborted caller signal silently as AbortError', async () => {
    const controller = new AbortController()
    controller.abort()
    vi.mocked(fetch).mockImplementation(rejectOnAbort)
    await expect(api('/translate', { signal: controller.signal })).rejects.toMatchObject({ name: 'AbortError' })
    expect(vi.mocked(fetch).mock.calls[0]?.[1]?.signal?.aborted).toBe(true)
  })

  it('aborts an in-flight fetch when its caller cancels', async () => {
    const controller = new AbortController()
    vi.mocked(fetch).mockImplementation(rejectOnAbort)
    const request = expect(api('/translate', { signal: controller.signal })).rejects.toMatchObject({ name: 'AbortError' })
    controller.abort()
    await request
    expect(vi.mocked(fetch).mock.calls[0]?.[1]?.signal?.aborted).toBe(true)
  })

  it.each([
    { path: '/translate', method: 'POST' as const, message: 'This is taking longer than expected.' },
    { path: '/dataset', method: 'POST' as const, message: 'The change may have completed. Close this dialog and refresh the collection' },
    { path: '/coursework/project', method: 'PUT' as const, message: 'The change may have completed. Refresh the saved coursework evidence' },
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
