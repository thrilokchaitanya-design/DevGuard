export type ApiErrorKind = 'network' | 'timeout' | 'http' | 'invalid-response'

export class ApiError extends Error {
  constructor(
    message: string,
    readonly kind: ApiErrorKind,
    readonly status?: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

function normalizeApiBase(value: string | undefined): string {
  const configured = value?.trim()
  if (!configured || configured === '/') {
    return import.meta.env.PROD ? '' : 'http://localhost:8000'
  }
  return configured.replace(/\/$/, '')
}

const API_BASE = normalizeApiBase(import.meta.env.VITE_API_URL)
const DEFAULT_TIMEOUT_MS = 15_000

function safeText(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined
  const clean = value.replace(/[\u0000-\u001f\u007f]/g, ' ').replace(/\s+/g, ' ').trim()
  return clean ? clean.slice(0, 180) : undefined
}

function statusMessage(status: number, detail: unknown): string {
  if (status === 401) return 'Your DevGuard session has expired. Sign in again.'
  if (status === 403) return 'DevGuard rejected this request. Refresh the page and sign in again.'
  if (status === 404) return 'The requested DevGuard API route was not found.'
  if (status === 429) return 'DevGuard is receiving too many requests. Try again shortly.'
  if (status >= 500) return `DevGuard API returned a server error (${status}). Try again shortly.`
  return safeText(detail) ?? `DevGuard API could not process this request (${status}).`
}

function csrfToken(): string {
  const value = document.cookie.split('; ').find(row => row.startsWith('devguard_csrf='))?.split('=').slice(1).join('=')
  if (!value) return ''
  try { return decodeURIComponent(value) } catch { return '' }
}

async function request<T>(path: string, init: RequestInit = {}, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
  const method = (init.method || 'GET').toUpperCase()
  const headers = new Headers(init.headers)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method) && csrfToken()) {
    headers.set('X-CSRF-Token', csrfToken())
  }
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    let response: Response
    try {
      response = await fetch(`${API_BASE}${path}`, {
        ...init,
        method,
        headers,
        credentials: 'include',
        signal: controller.signal,
      })
    } catch (error) {
      if (controller.signal.aborted) throw new ApiError('The DevGuard API request timed out. Try again.', 'timeout')
      throw new ApiError('Cannot connect to the DevGuard API. Check the service, network, and browser CORS settings.', 'network')
    }
    const contentType = response.headers.get('content-type') || ''
    let body: unknown
    try {
      body = contentType.includes('application/json') ? await response.json() : undefined
    } catch {
      body = undefined
    }
    if (!response.ok) {
      const detail = body && typeof body === 'object' && 'detail' in body ? (body as { detail?: unknown }).detail : undefined
      throw new ApiError(statusMessage(response.status, detail), 'http', response.status)
    }
    if (!contentType.includes('application/json') || body === undefined) {
      throw new ApiError('DevGuard returned an unreadable API response.', 'invalid-response', response.status)
    }
    return body as T
  } finally {
    window.clearTimeout(timer)
  }
}

export function api<T>(path: string, init?: RequestInit): Promise<T> {
  return request<T>(path, init)
}

export async function checkApiHealth(
  fetcher: typeof fetch = fetch,
  wait: (ms: number) => Promise<void> = ms => new Promise(resolve => window.setTimeout(resolve, ms)),
  timeoutMs = 4_000,
): Promise<void> {
  let lastError: ApiError = new ApiError('DevGuard health check failed.', 'invalid-response')
  for (let attempt = 0; attempt < 2; attempt++) {
    const controller = new AbortController()
    const timer = window.setTimeout(() => controller.abort(), timeoutMs)
    try {
      let response: Response
      try {
        response = await fetcher(`${API_BASE}/api/health`, { method: 'GET', credentials: 'include', signal: controller.signal })
      } catch {
        lastError = controller.signal.aborted
          ? new ApiError('The DevGuard health check timed out.', 'timeout')
          : new ApiError('Cannot reach the DevGuard API. Check the service, network, and browser CORS settings.', 'network')
        if (attempt === 0) { await wait(500); continue }
        throw lastError
      }
      if (!response.ok) {
        lastError = new ApiError(statusMessage(response.status, undefined), 'http', response.status)
        if (response.status >= 500 && attempt === 0) { await wait(500); continue }
        throw lastError
      }
      let body: unknown
      try { body = await response.json() } catch { throw new ApiError('DevGuard returned an invalid health response.', 'invalid-response', response.status) }
      if (!body || typeof body !== 'object' || !('status' in body) || (body as { status?: unknown }).status !== 'ok') {
        throw new ApiError('DevGuard returned an invalid health response.', 'invalid-response', response.status)
      }
      return
    } finally {
      window.clearTimeout(timer)
    }
  }
  throw lastError
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  return 'The request failed unexpectedly. Try again.'
}

export function isConnectivityFailure(error: unknown): boolean {
  return error instanceof ApiError && (error.kind === 'network' || error.kind === 'timeout')
}
