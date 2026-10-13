/**
 * Tests for the AccessKeysClient: every management route of
 * routers/access_keys.py, cache clearing after mutations, the CSV URLs and
 * the connection test against /api/v1/me.
 */

import { ACCESS_KEY_WHOAMI_PATH, AccessKeysClient } from '../accessKeys'

const mockCalls: Array<{ method: string; url: string; body?: unknown }> = []
const mockClearCache = jest.fn()
let mockNextResult: unknown = undefined

jest.mock('../base', () => ({
  BaseApiClient: class MockBaseApiClient {
    clearCache() {
      mockClearCache()
    }
    async get(url: string) {
      mockCalls.push({ method: 'GET', url })
      return mockNextResult
    }
    async post(url: string, body?: unknown) {
      mockCalls.push({ method: 'POST', url, body })
      return mockNextResult
    }
    async patch(url: string, body?: unknown) {
      mockCalls.push({ method: 'PATCH', url, body })
      return mockNextResult
    }
  },
}))

describe('AccessKeysClient', () => {
  let client: AccessKeysClient

  beforeEach(() => {
    mockCalls.length = 0
    mockClearCache.mockClear()
    mockNextResult = { ok: 1 }
    client = new AccessKeysClient()
  })

  it('reads the scope catalog', async () => {
    await client.scopes()
    expect(mockCalls[0]).toEqual({ method: 'GET', url: '/access-keys/scopes' })
  })

  describe('organization keys', () => {
    it('lists keys and falls back to an empty list', async () => {
      mockNextResult = null
      expect(await client.listOrgKeys('org 1')).toEqual([])
      expect(mockCalls[0].url).toBe('/organizations/org%201/access-keys')
    })

    it('creates a key and clears the cache', async () => {
      const body = { name: 'Runner', scopes: ['org:read'] }
      await client.createOrgKey('org-1', body)
      expect(mockCalls[0]).toEqual({
        method: 'POST',
        url: '/organizations/org-1/access-keys',
        body,
      })
      expect(mockClearCache).toHaveBeenCalled()
    })

    it('updates a key', async () => {
      await client.updateOrgKey('org-1', 'k1', { name: 'New' })
      expect(mockCalls[0]).toEqual({
        method: 'PATCH',
        url: '/organizations/org-1/access-keys/k1',
        body: { name: 'New' },
      })
      expect(mockClearCache).toHaveBeenCalled()
    })

    it('revokes a key with and without a reason', async () => {
      await client.revokeOrgKey('org-1', 'k1', 'leaked')
      await client.revokeOrgKey('org-1', 'k1')
      expect(mockCalls[0]).toEqual({
        method: 'POST',
        url: '/organizations/org-1/access-keys/k1/revoke',
        body: { reason: 'leaked' },
      })
      expect(mockCalls[1].body).toEqual({ reason: null })
      expect(mockClearCache).toHaveBeenCalledTimes(2)
    })

    it('reads usage with the query parameters', async () => {
      await client.orgKeyUsage('org-1', 'k1', {
        granularity: 'route',
        from: '2026-10-01',
      })
      await client.orgKeyUsage('org-1', 'k1')
      expect(mockCalls[0].url).toBe(
        '/organizations/org-1/access-keys/k1/usage?granularity=route&from=2026-10-01',
      )
      expect(mockCalls[1].url).toBe('/organizations/org-1/access-keys/k1/usage')
    })

    it('reads usage events with a cursor', async () => {
      await client.orgKeyUsageEvents('org-1', 'k1', { cursor: 5, limit: 10 })
      await client.orgKeyUsageEvents('org-1', 'k1')
      expect(mockCalls[0].url).toBe(
        '/organizations/org-1/access-keys/k1/usage/events?cursor=5&limit=10',
      )
      expect(mockCalls[1].url).toBe(
        '/organizations/org-1/access-keys/k1/usage/events',
      )
    })

    it('builds the CSV URL through the Next proxy', () => {
      expect(client.orgUsageExportUrl('org-1')).toBe(
        '/api/organizations/org-1/access-keys/usage/export.csv',
      )
      expect(client.orgUsageExportUrl('org-1', { from: 'a', to: '' })).toBe(
        '/api/organizations/org-1/access-keys/usage/export.csv?from=a',
      )
    })
  })

  describe('personal keys', () => {
    it('lists, creates, revokes and reads usage', async () => {
      mockNextResult = undefined
      expect(await client.listMyKeys()).toEqual([])
      mockNextResult = { key: {}, secret: 's' }
      await client.createMyKey({ name: 'Mine', scopes: ['projects:read'] })
      await client.revokeMyKey('k2', 'old')
      await client.revokeMyKey('k2')
      await client.myKeyUsage('k2', { granularity: 'day' })
      await client.myKeyUsage('k2')
      expect(mockCalls.map((c) => `${c.method} ${c.url}`)).toEqual([
        'GET /users/me/access-keys',
        'POST /users/me/access-keys',
        'POST /users/me/access-keys/k2/revoke',
        'POST /users/me/access-keys/k2/revoke',
        'GET /users/me/access-keys/k2/usage?granularity=day',
        'GET /users/me/access-keys/k2/usage',
      ])
      expect(mockCalls[3].body).toEqual({ reason: null })
      expect(mockClearCache).toHaveBeenCalledTimes(3)
    })
  })

  describe('superadmin', () => {
    it('lists with filters and an empty fallback', async () => {
      mockNextResult = null
      expect(await client.adminListKeys()).toEqual({
        items: [],
        next_cursor: null,
      })
      mockNextResult = { items: [{ id: 'k' }], next_cursor: 'c' }
      await client.adminListKeys({
        organization_id: 'org-1',
        owner_type: 'org',
        status: 'active',
        cursor: 'abc',
        limit: 20,
      })
      expect(mockCalls[0].url).toBe('/admin/access-keys')
      expect(mockCalls[1].url).toBe(
        '/admin/access-keys?organization_id=org-1&owner_type=org&status=active&cursor=abc&limit=20',
      )
    })

    it('revokes any key', async () => {
      await client.adminRevokeKey('k3', 'abuse')
      await client.adminRevokeKey('k3')
      expect(mockCalls[0]).toEqual({
        method: 'POST',
        url: '/admin/access-keys/k3/revoke',
        body: { reason: 'abuse' },
      })
      expect(mockCalls[1].body).toEqual({ reason: null })
      expect(mockClearCache).toHaveBeenCalledTimes(2)
    })

    it('builds the admin CSV URL', () => {
      expect(client.adminUsageExportUrl()).toBe(
        '/api/admin/access-keys/usage/export.csv',
      )
      expect(client.adminUsageExportUrl({ organization_id: 'o' })).toBe(
        '/api/admin/access-keys/usage/export.csv?organization_id=o',
      )
    })
  })

  describe('testConnection', () => {
    const originalFetch = global.fetch
    afterEach(() => {
      global.fetch = originalFetch
    })

    const respond = (status: number, body: unknown, json = true) => {
      global.fetch = jest.fn().mockResolvedValue({
        ok: status >= 200 && status < 300,
        status,
        json: json
          ? jest.fn().mockResolvedValue(body)
          : jest.fn().mockRejectedValue(new Error('not json')),
      }) as unknown as typeof fetch
    }

    it('sends the key as bearer token without cookies', async () => {
      const me = {
        principal: { kind: 'api_key', scopes: ['org:read'] },
        user: { id: 'u' },
      }
      respond(200, me)
      const result = await client.testConnection('bgr_live_abc_secret')
      expect(result).toEqual({ ok: true, me })
      const [url, init] = (global.fetch as jest.Mock).mock.calls[0]
      expect(url).toBe(ACCESS_KEY_WHOAMI_PATH)
      expect(init.credentials).toBe('omit')
      expect(init.headers.Authorization).toBe('Bearer bgr_live_abc_secret')
    })

    it('reads a structured error', async () => {
      respond(401, {
        detail: { code: 'invalid_key', message: 'Invalid access key' },
      })
      expect(await client.testConnection('x')).toEqual({
        ok: false,
        status: 401,
        code: 'invalid_key',
        message: 'Invalid access key',
      })
    })

    it('reads a string detail and a top-level message', async () => {
      respond(403, { detail: 'Forbidden' })
      expect(await client.testConnection('x')).toMatchObject({
        status: 403,
        code: null,
        message: 'Forbidden',
      })
      respond(500, { code: 'boom', message: 'Server error' })
      expect(await client.testConnection('x')).toMatchObject({
        code: 'boom',
        message: 'Server error',
      })
    })

    it('treats a non-JSON or principal-less answer as failure', async () => {
      respond(404, null, false)
      expect(await client.testConnection('x')).toEqual({
        ok: false,
        status: 404,
        code: null,
        message: 'HTTP 404',
      })
      respond(200, { hello: 'world' })
      expect(await client.testConnection('x')).toMatchObject({
        ok: false,
        status: 200,
      })
    })

    it('reports network errors as status 0', async () => {
      global.fetch = jest
        .fn()
        .mockRejectedValue(new Error('offline')) as unknown as typeof fetch
      expect(await client.testConnection('x')).toEqual({
        ok: false,
        status: 0,
        code: 'network_error',
        message: 'offline',
      })
      global.fetch = jest
        .fn()
        .mockRejectedValue('weird') as unknown as typeof fetch
      expect(await client.testConnection('x')).toMatchObject({
        message: 'weird',
      })
    })
  })
})
