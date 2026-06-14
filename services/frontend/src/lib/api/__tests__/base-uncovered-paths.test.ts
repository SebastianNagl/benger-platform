/**
 * Additional behavioral coverage for BaseApiClient.
 *
 * Targets paths NOT exercised by base-comprehensive.test.ts /
 * base-api-client-error-handling.test.ts:
 *  - requestRaw (success, error JSON `detail`, error plain-text, FormData,
 *    Bearer + org-context header application)
 *  - formatErrorDetail array (FastAPI validation) + object shapes, surfaced
 *    through request()'s thrown Error message
 *  - Content-Disposition: attachment → blob branch
 *  - invalidateRelatedCache pattern families (org members, invitations,
 *    api-keys, project sub-resources, notification mutations)
 *  - 502/503 retry exhaustion (error rethrown after retries) + 429 exhaustion
 *  - /auth/logout 401 → resolves undefined
 *  - invalidateCache string + RegExp matching
 */

// IMPORTANT: Unmock BaseApiClient to test the real implementation.
// setupTests.ts installs a global jest.mock('@/lib/api/base', ...) that
// replaces every method with a stub; unmock restores the real module.
jest.unmock('@/lib/api/base')

import { BaseApiClient } from '../base'

global.fetch = jest.fn()

jest.mock('@/lib/utils/logger', () => {
  const mockLogger = {
    debug: jest.fn(),
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  }
  return { __esModule: true, default: mockLogger }
})

const localStorageMock = {
  getItem: jest.fn() as jest.Mock,
  setItem: jest.fn(),
  removeItem: jest.fn(),
  clear: jest.fn(),
}

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
  writable: true,
})

class TestApiClient extends BaseApiClient {
  public async testRequest(
    endpoint: string,
    options?: RequestInit,
    isRetry?: boolean,
    retryCount?: number
  ): Promise<any> {
    return (this as any).request(endpoint, options, isRetry, retryCount)
  }

  public async get(endpoint: string, options?: RequestInit): Promise<any> {
    return this.testRequest(endpoint, { ...options, method: 'GET' })
  }

  public async post(
    endpoint: string,
    data?: any,
    options?: RequestInit
  ): Promise<any> {
    let body: any
    if (data instanceof FormData) {
      body = data
    } else if (data !== undefined) {
      body = JSON.stringify(data)
    }
    return this.testRequest(endpoint, { ...options, method: 'POST', body })
  }

  public seedCache(key: string, data: any, userId: string | null = 'user1') {
    ;(this as any).responseCache.set(key, {
      data,
      timestamp: Date.now(),
      userId,
    })
  }

  public cacheHas(key: string): boolean {
    return (this as any).responseCache.has(key)
  }

  public getCacheSize(): number {
    return (this as any).responseCache.size
  }

  public callInvalidateCache(pattern: string | RegExp) {
    ;(this as any).invalidateCache(pattern)
  }
}

function jsonResponse(status: number, payload: unknown, extraHeaders = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: 'OK',
    headers: new Headers({ 'content-type': 'application/json', ...extraHeaders }),
    text: async () => JSON.stringify(payload),
  }
}

describe('BaseApiClient - additional uncovered paths', () => {
  let client: TestApiClient

  beforeEach(() => {
    jest.clearAllMocks()
    localStorageMock.getItem.mockReturnValue(null)
    client = new TestApiClient()
  })

  describe('requestRaw', () => {
    it('returns the raw Response on success without buffering the body', async () => {
      const rawResponse = {
        ok: true,
        status: 200,
        statusText: 'OK',
        headers: new Headers({ 'content-type': 'application/zip' }),
        body: 'streaming-body',
      }
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(rawResponse)

      const result = await client.requestRaw('/projects/1/exports/job-1/download')

      // It returns the live Response untouched (no .blob()/.text() call).
      expect(result).toBe(rawResponse)
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/projects/1/exports/job-1/download'),
        expect.objectContaining({
          credentials: 'include',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
        })
      )
    })

    it('does not set Content-Type when the body is FormData', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers(),
      })

      const fd = new FormData()
      fd.append('k', 'v')
      await client.requestRaw('/upload', { method: 'POST', body: fd })

      const fetchCall = (global.fetch as jest.Mock).mock.calls[0][1]
      expect(fetchCall.headers['Content-Type']).toBeUndefined()
    })

    it('applies the Bearer token and organization context header', async () => {
      const validToken = `header.${btoa(
        JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 3600 })
      )}.signature`
      localStorageMock.getItem.mockImplementation((key) =>
        key === 'access_token' ? validToken : null
      )
      client.setOrganizationContextProvider(() => 'org-77')
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers(),
      })

      await client.requestRaw('/stream')

      const fetchCall = (global.fetch as jest.Mock).mock.calls[0][1]
      expect(fetchCall.headers.Authorization).toBe(`Bearer ${validToken}`)
      expect(fetchCall.headers['X-Organization-Context']).toBe('org-77')
    })

    it('throws an error with the formatted JSON detail on a non-ok response', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 422,
        statusText: 'Unprocessable Entity',
        headers: new Headers(),
        text: async () =>
          JSON.stringify({
            detail: [
              { loc: ['body', 'email'], msg: 'field required' },
              { loc: ['body', 'password'], msg: 'too short' },
            ],
          }),
      })

      await expect(client.requestRaw('/projects/1/exports')).rejects.toThrow(
        'email: field required; password: too short'
      )
    })

    it('appends plain-text error body when the response is not JSON', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        headers: new Headers(),
        text: async () => 'boom',
      })

      await expect(client.requestRaw('/x')).rejects.toThrow(
        'HTTP error! status: 500 - boom'
      )
    })

    it('attaches an axios-like response object to the thrown error', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        headers: new Headers(),
        text: async () => '',
      })

      try {
        await client.requestRaw('/missing')
        throw new Error('should have thrown')
      } catch (err: any) {
        expect(err.response.status).toBe(404)
        expect(err.response.statusText).toBe('Not Found')
      }
    })
  })

  describe('formatErrorDetail surfaced via request()', () => {
    it('flattens a FastAPI validation array into a readable message', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        jsonResponse(400, {
          detail: [
            { loc: ['body', 'username'], msg: 'field required' },
            { loc: ['query', 'page'], msg: 'must be positive' },
          ],
        })
      )

      await expect(client.get('/register')).rejects.toThrow(
        'username: field required; query.page: must be positive'
      )
    })

    it('uses message/JSON fallback for array items without loc/msg', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        jsonResponse(400, {
          detail: [{ message: 'plain message' }, 'just a string'],
        })
      )

      await expect(client.get('/x')).rejects.toThrow(
        'plain message; just a string'
      )
    })

    it('extracts msg from a single object detail', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        jsonResponse(409, { detail: { msg: 'conflict happened' } })
      )

      await expect(client.get('/x')).rejects.toThrow('conflict happened')
    })

    it('falls back to the top-level message field when detail is absent', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        jsonResponse(400, { message: 'top-level error' })
      )

      await expect(client.get('/x')).rejects.toThrow('top-level error')
    })
  })

  describe('Content-Disposition attachment branch', () => {
    it('returns a blob when Content-Disposition is attachment even for JSON-ish content', async () => {
      const mockBlob = new Blob(['report,data'], { type: 'text/plain' })
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({
          'content-type': 'text/plain',
          'content-disposition': 'attachment; filename="report.csv"',
        }),
        blob: async () => mockBlob,
      })

      const result = await client.get('/reports/1/download')
      expect(result).toBeInstanceOf(Blob)
    })

    it('returns a blob for text/csv content type', async () => {
      const mockBlob = new Blob(['a,b,c'], { type: 'text/csv' })
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'text/csv' }),
        blob: async () => mockBlob,
      })

      const result = await client.get('/export.csv')
      expect(result).toBeInstanceOf(Blob)
    })
  })

  describe('invalidateRelatedCache after mutations (204 path)', () => {
    function delete204() {
      return {
        ok: true,
        status: 204,
        statusText: 'No Content',
        headers: new Headers(),
      }
    }

    it('invalidates the org + members lists after an org-member mutation', async () => {
      localStorageMock.getItem.mockReturnValue('user1')
      client.seedCache('user1-GET-/organizations/abc', { org: true })
      client.seedCache('user1-GET-/organizations/abc/members', { members: [] })
      client.seedCache('user1-GET-/projects/other', { keep: true })
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(delete204())

      await client.testRequest('/organizations/abc/members/u9', {
        method: 'DELETE',
      })

      expect(client.cacheHas('user1-GET-/organizations/abc')).toBe(false)
      expect(client.cacheHas('user1-GET-/organizations/abc/members')).toBe(false)
      // Unrelated cache entry is preserved.
      expect(client.cacheHas('user1-GET-/projects/other')).toBe(true)
    })

    it('invalidates org + members + invitations lists after an invitation mutation', async () => {
      localStorageMock.getItem.mockReturnValue('user1')
      client.seedCache('user1-GET-/organizations/abc', { org: true })
      client.seedCache('user1-GET-/organizations/abc/invitations', { inv: [] })
      client.seedCache('user1-GET-/invitations', { all: [] })
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(delete204())

      await client.testRequest('/organizations/abc/invitations/inv-1', {
        method: 'DELETE',
      })

      expect(client.cacheHas('user1-GET-/organizations/abc')).toBe(false)
      expect(client.cacheHas('user1-GET-/organizations/abc/invitations')).toBe(
        false
      )
      expect(client.cacheHas('user1-GET-/invitations')).toBe(false)
    })

    it('invalidates the org list after a top-level org update', async () => {
      localStorageMock.getItem.mockReturnValue('user1')
      client.seedCache('user1-GET-/organizations', { list: [] })
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(delete204())

      await client.testRequest('/organizations/abc', { method: 'PUT' })

      expect(client.cacheHas('user1-GET-/organizations')).toBe(false)
    })

    it('invalidates the user api-keys status endpoint after a key mutation', async () => {
      localStorageMock.getItem.mockReturnValue('user1')
      client.seedCache('user1-GET-/users/api-keys/status', { ok: true })
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(delete204())

      await client.testRequest('/users/api-keys/openai', { method: 'DELETE' })

      expect(client.cacheHas('user1-GET-/users/api-keys/status')).toBe(false)
    })

    it('invalidates org api-keys after an org api-key mutation', async () => {
      localStorageMock.getItem.mockReturnValue('user1')
      client.seedCache('user1-GET-/organizations/abc/api-keys', { keys: [] })
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(delete204())

      await client.testRequest('/organizations/abc/api-keys/openai', {
        method: 'DELETE',
      })

      expect(client.cacheHas('user1-GET-/organizations/abc/api-keys')).toBe(
        false
      )
    })

    it('invalidates the parent project after a project sub-resource mutation', async () => {
      localStorageMock.getItem.mockReturnValue('user1')
      client.seedCache('user1-GET-/projects/proj-1', { stale: true })
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(delete204())

      await client.testRequest('/projects/proj-1/prompt-structures/ps-1', {
        method: 'DELETE',
      })

      expect(client.cacheHas('user1-GET-/projects/proj-1')).toBe(false)
    })

    it('invalidates notification list + unread count after mark-all-read', async () => {
      localStorageMock.getItem.mockReturnValue('user1')
      client.seedCache('user1-GET-/notifications/', { items: [] })
      client.seedCache('user1-GET-/notifications/unread-count', { count: 3 })
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(delete204())

      await client.testRequest('/notifications/mark-all-read', {
        method: 'POST',
      })

      expect(client.cacheHas('user1-GET-/notifications/')).toBe(false)
      expect(client.cacheHas('user1-GET-/notifications/unread-count')).toBe(
        false
      )
    })

    it('invalidates notification caches after a single mark-read mutation', async () => {
      localStorageMock.getItem.mockReturnValue('user1')
      client.seedCache('user1-GET-/notifications/', { items: [] })
      client.seedCache('user1-GET-/notifications/unread-count', { count: 1 })
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(delete204())

      await client.testRequest('/notifications/mark-read/notif-9', {
        method: 'POST',
      })

      expect(client.cacheHas('user1-GET-/notifications/')).toBe(false)
      expect(client.cacheHas('user1-GET-/notifications/unread-count')).toBe(
        false
      )
    })
  })

  describe('invalidateCache pattern matching', () => {
    it('removes entries whose endpoint includes a string pattern', () => {
      client.seedCache('user1-GET-/organizations/123', { a: 1 })
      client.seedCache('user1-GET-/organizations/456/members', { b: 2 })
      client.seedCache('user1-GET-/projects/789', { c: 3 })

      client.callInvalidateCache('/organizations')

      expect(client.cacheHas('user1-GET-/organizations/123')).toBe(false)
      expect(client.cacheHas('user1-GET-/organizations/456/members')).toBe(false)
      expect(client.cacheHas('user1-GET-/projects/789')).toBe(true)
    })

    it('removes entries matching a RegExp pattern', () => {
      client.seedCache('user1-GET-/projects/abc/tasks', { a: 1 })
      client.seedCache('user1-GET-/projects/def/tasks', { b: 2 })
      client.seedCache('user1-GET-/organizations/abc', { c: 3 })

      client.callInvalidateCache(/^\/projects\/[^/]+\/tasks$/)

      expect(client.cacheHas('user1-GET-/projects/abc/tasks')).toBe(false)
      expect(client.cacheHas('user1-GET-/projects/def/tasks')).toBe(false)
      expect(client.cacheHas('user1-GET-/organizations/abc')).toBe(true)
    })
  })

  describe('retry exhaustion', () => {
    it('rethrows after exhausting 503 retries', async () => {
      const unavailable = {
        ok: false,
        status: 503,
        statusText: 'Service Unavailable',
        headers: new Headers(),
        text: async () => 'down',
      }
      ;(global.fetch as jest.Mock)
        .mockResolvedValueOnce(unavailable)
        .mockResolvedValueOnce(unavailable)
        .mockResolvedValueOnce(unavailable)

      await expect(client.get('/flaky')).rejects.toThrow()
      // 1 original + 2 retries (retryCount < 2)
      expect(global.fetch).toHaveBeenCalledTimes(3)
    })

    it('rethrows after exhausting 429 rate-limit retries', async () => {
      const rateLimited = {
        ok: false,
        status: 429,
        statusText: 'Too Many Requests',
        headers: new Headers({ 'retry-after': '0' }),
        text: async () => JSON.stringify({ detail: 'slow down' }),
      }
      ;(global.fetch as jest.Mock)
        .mockResolvedValueOnce(rateLimited)
        .mockResolvedValueOnce(rateLimited)
        .mockResolvedValueOnce(rateLimited)
        .mockResolvedValueOnce(rateLimited)

      await expect(client.get('/limited')).rejects.toThrow('slow down')
      // 1 original + 3 retries (retryCount < 3)
      expect(global.fetch).toHaveBeenCalledTimes(4)
    })
  })

  describe('logout 401 special case', () => {
    it('resolves undefined when /auth/logout returns 401', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 401,
        statusText: 'Unauthorized',
        headers: new Headers(),
        text: async () => '',
      })

      const result = await client.post('/auth/logout')
      expect(result).toBeUndefined()
    })
  })

  describe('FormData request body (no Content-Type override)', () => {
    it('omits Content-Type for FormData and forwards the body to fetch', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        jsonResponse(200, { uploaded: true })
      )

      const fd = new FormData()
      fd.append('file', 'data')
      const result = await client.post('/projects/1/imports', fd)

      expect(result).toEqual({ uploaded: true })
      const fetchCall = (global.fetch as jest.Mock).mock.calls[0][1]
      expect(fetchCall.body).toBeInstanceOf(FormData)
      expect(fetchCall.headers['Content-Type']).toBeUndefined()
    })
  })
})
