export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message)
    this.name = 'ApiError'
  }
}

let csrfToken = ''
let projectId = 'default'
let accountVersion = 0

export function configureSession(token: string | null): void {
  csrfToken = token ?? ''
  projectId = 'default'
  accountVersion++
}

export function selectProject(id: string): void {
  projectId = id
  accountVersion++
}

export function nativeApiUrl(path: string): string {
  return `/api${path}${projectId === 'default' ? '' : `?project=${encodeURIComponent(projectId)}`}`
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
  const version = accountVersion
  const controller = new AbortController()
  const isMutation = options.method === 'PATCH' || options.method === 'DELETE' || options.method === 'PUT' ||
    ((path === '/dataset' || path === '/dataset/audio' || path === '/coursework/screenshots' ||
      path.startsWith('/workspace/') || path.startsWith('/auth/')) && options.method === 'POST')
  const recovery = path.startsWith('/coursework')
    ? 'Refresh the saved coursework evidence before trying again; your editor draft will be kept.'
    : path.startsWith('/workspace/') || path.startsWith('/auth/')
      ? 'Refresh the saved state before trying again; do not repeat a restore blindly.'
      : 'Close this dialog and refresh the collection before trying again.'
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
    if (projectId !== 'default' && !path.startsWith('/auth/')) headers['X-Mboa-Project'] = projectId
    const response = await fetch(`/api${path}`, {
      method: options.method ?? 'GET',
      headers: Object.keys(headers).length ? headers : undefined,
      body: multipart ? options.body as FormData : options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: controller.signal,
      cache: 'no-store',
      credentials: 'same-origin',
    })
    if (version !== accountVersion) throw new DOMException('Workspace changed', 'AbortError')
    if (response.status === 401 && (!path.startsWith('/auth/') || path === '/auth/profile' || path === '/auth/logout')) {
      window.dispatchEvent(new Event('mboa:session-expired'))
    }
    if (response.status === 204 && response.ok) return undefined as T
    const body: unknown = await response.json().catch(() => null)
    if (version !== accountVersion) throw new DOMException('Workspace changed', 'AbortError')
    if (!response.ok) {
      throw new ApiError(
        errorDetail(body) ??
          (response.status === 503
            ? 'The service is not ready. Check the backend configuration and try again.'
            : `The request could not be completed (${response.status}). Please try again.`),
        response.status,
      )
    }
    if (body === null) throw new Error('The server returned an unreadable response. Please try again.')
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
        : 'Cannot reach the server. Check your connection, then try again. For local testing, make sure Mboa is running.')
    }
    throw error
  } finally {
    window.clearTimeout(timer)
    options.signal?.removeEventListener('abort', cancel)
  }
}
