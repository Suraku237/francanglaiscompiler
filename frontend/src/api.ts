export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message)
    this.name = 'ApiError'
  }
}

let csrfToken = ''
let sessionVersion = 0

export function configureSession(token: string | null): void {
  csrfToken = token ?? ''
  sessionVersion++
}

export function nativeApiUrl(path: string): string {
  return `/api${path}`
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

export function errorDetail(value: unknown): string | null {
  if (!isRecord(value)) return null
  if (typeof value.detail === 'string') return value.detail
  if (!Array.isArray(value.detail)) return null
  const messages = value.detail.flatMap((item: unknown) => {
    if (!isRecord(item) || typeof item.msg !== 'string') return []
    const field = Array.isArray(item.loc)
      ? item.loc.filter((part: unknown) => typeof part === 'string' && part !== 'body').join(' → ')
      : ''
    return [field ? `${field.replaceAll('_', ' ')}: ${item.msg}` : item.msg]
  })
  return messages.length ? messages.join('. ') : null
}

export function isCancelled(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

export function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong. Please try again.'
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  signal?: AbortSignal
  timeout?: number
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const version = sessionVersion
  const controller = new AbortController()
  const isMutation = options.method === 'PATCH' || options.method === 'DELETE' || options.method === 'PUT' ||
    (path === '/analyzer/tests' && options.method === 'POST')
  const recovery = path === '/analyzer/tests'
    ? 'Open Analysis and refresh saved tests to check the public workspace. Retrying an unchanged test in this tab will not record it twice.'
    : 'Refresh the saved state before trying again.'
  let timedOut = false
  const cancel = () => controller.abort()
  if (options.signal?.aborted) controller.abort()
  options.signal?.addEventListener('abort', cancel, { once: true })
  const timer = window.setTimeout(() => {
    timedOut = true
    controller.abort()
  }, options.timeout ?? 15000)

  try {
    const multipart = options.body instanceof FormData
    const headers: Record<string, string> = {}
    if (options.body !== undefined && !multipart) headers['Content-Type'] = 'application/json'
    if (csrfToken && options.method && options.method !== 'GET') headers['X-CSRF-Token'] = csrfToken
    const response = await fetch(`/api${path}`, {
      method: options.method ?? 'GET',
      headers: Object.keys(headers).length ? headers : undefined,
      body: multipart ? options.body as FormData : options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: controller.signal,
      cache: 'no-store',
      credentials: 'same-origin',
    })
    if (version !== sessionVersion) throw new DOMException('Browser session changed', 'AbortError')
    if (response.status === 204 && response.ok) return undefined as T
    const body: unknown = await response.json().catch(() => null)
    if (version !== sessionVersion) throw new DOMException('Browser session changed', 'AbortError')
    if (!response.ok) {
      throw new ApiError(
        errorDetail(body) ??
          (response.status === 503
            ? 'The service is not ready. Check the backend configuration and try again.'
            : `The request could not be completed (${response.status}). Please try again.`),
        response.status,
      )
    }
    if (body === null) throw new Error(isMutation
      ? `The server returned an unreadable response. The change may have completed. ${recovery}`
      : 'The server returned an unreadable response. Please try again.')
    return body as T
  } catch (error: unknown) {
    if (timedOut) {
      throw new Error(
        isMutation
          ? `The request timed out. The change may have completed. ${recovery}`
          : 'This is taking longer than expected. Check your connection and try again.',
      )
    }
    if (controller.signal.aborted) throw new DOMException('Request cancelled', 'AbortError')
    if (error instanceof TypeError) {
      throw new Error(isMutation
        ? `The connection was interrupted. The change may have completed. ${recovery}`
        : 'Cannot reach the server. Check your connection, then try again. For local testing, make sure Camfranglais is running.')
    }
    throw error
  } finally {
    window.clearTimeout(timer)
    options.signal?.removeEventListener('abort', cancel)
  }
}
