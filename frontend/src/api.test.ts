import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, checkApiHealth, errorMessage, setSessionCsrfToken } from './api'

afterEach(() => {
  vi.unstubAllGlobals()
  document.cookie = 'devguard_csrf=; Max-Age=0; path=/'
})

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

describe('API client', () => {
  it('sends same-origin session credentials and the CSRF token on mutations', async () => {
    document.cookie = 'devguard_csrf=token-123; path=/'
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(api('/api/issues/3', { method: 'PATCH', body: '{"status":"resolved"}' })).resolves.toEqual({ ok: true })

    expect(fetchMock).toHaveBeenCalledOnce()
    const [, init] = fetchMock.mock.calls[0]
    expect(init.credentials).toBe('include')
    expect(new Headers(init.headers).get('X-CSRF-Token')).toBe('token-123')
  })

  it('sends a CSRF token returned by login when the API is on another origin', async () => {
    setSessionCsrfToken('cross-origin-token')
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)

    await api('/api/issues/3', { method: 'PATCH', body: '{"status":"resolved"}' })

    const [, init] = fetchMock.mock.calls[0]
    expect(new Headers(init.headers).get('X-CSRF-Token')).toBe('cross-origin-token')
    setSessionCsrfToken(undefined)
  })

  it('uses a safe message for object-valued error details', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: { reason: 'database down' } }, 503)))
    await expect(api('/api/overview')).rejects.toMatchObject({ kind: 'http', status: 503, message: expect.stringContaining('server error (503)') })
    expect(errorMessage({ detail: { reason: 'private' } })).not.toContain('[object Object]')
  })

  it('distinguishes expired sessions from network failures', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: 'Sign-in required.' }, 401)))
    await expect(api('/api/overview')).rejects.toMatchObject({ status: 401, message: expect.stringContaining('session has expired') })
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(api('/api/health')).rejects.toMatchObject({ kind: 'network', message: expect.stringContaining('Cannot connect') })
  })
})

describe('API health check', () => {
  it('accepts only a successful, valid health response', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ status: 'ok' }))
    await expect(checkApiHealth(fetchMock)).resolves.toBeUndefined()
    expect(fetchMock).toHaveBeenCalledOnce()
    await expect(checkApiHealth(vi.fn().mockResolvedValue(jsonResponse({ detail: 'not a health response' })))).rejects.toMatchObject({ kind: 'invalid-response' })
  })

  it('retries a transient network failure and recovers', async () => {
    const fetchMock = vi.fn().mockRejectedValueOnce(new TypeError('offline')).mockResolvedValueOnce(jsonResponse({ status: 'ok' }))
    const wait = vi.fn().mockResolvedValue(undefined)
    await expect(checkApiHealth(fetchMock, wait)).resolves.toBeUndefined()
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(wait).toHaveBeenCalledWith(500)
  })

  it('times out health requests and reports HTTP authorization errors as degraded API responses', async () => {
    const timeoutFetch = vi.fn((_url: RequestInfo | URL, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () => reject(new Error('aborted')), { once: true })
    }))
    await expect(checkApiHealth(timeoutFetch, vi.fn().mockResolvedValue(undefined), 5)).rejects.toMatchObject({ kind: 'timeout' })
    await expect(checkApiHealth(vi.fn().mockResolvedValue(jsonResponse({ detail: 'no access' }, 401)))).rejects.toMatchObject({ kind: 'http', status: 401 })
  })

  it('recovers on a later poll after an unhealthy response', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse({ detail: 'unavailable' }, 503)).mockResolvedValueOnce(jsonResponse({ detail: 'unavailable' }, 503)).mockResolvedValueOnce(jsonResponse({ status: 'ok' }))
    const wait = vi.fn().mockResolvedValue(undefined)
    await expect(checkApiHealth(fetchMock, wait)).rejects.toBeInstanceOf(ApiError)
    await expect(checkApiHealth(fetchMock, wait)).resolves.toBeUndefined()
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })
})
