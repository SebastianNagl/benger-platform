/**
 * Comprehensive tests for BaseApiClient
 * Covers uncovered code paths to improve coverage from 54.86% to 85%+
 */

// IMPORTANT: Unmock BaseApiClient to test the real implementation
jest.unmock('@/lib/api/base')

import { BaseApiClient } from '../base'

// Mock fetch globally
global.fetch = jest.fn()

// Mock logger to avoid console spam
jest.mock('@/lib/utils/logger', () => {
  const mockLogger = {
    debug: jest.fn(),
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  }
  return {
    __esModule: true,
    default: mockLogger,
  }
})

// Mock localStorage
const localStorageMock = {
  getItem: jest.fn(),
  setItem: jest.fn(),
  removeItem: jest.fn(),
  clear: jest.fn(),
}

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
  writable: true,
})

// Test helper class
class TestApiClient extends BaseApiClient {
  public async testAuthCheck(
    endpoint: string,
    options?: RequestInit
  ): Promise<any> {
    return (this as any).authCheckRequest(endpoint, options)
  }

  public async testRequest(
    endpoint: string,
    options?: RequestInit,
    isRetry?: boolean,
    retryCount?: number
  ): Promise<any> {
    return (this as any).request(endpoint, options, isRetry, retryCount)
  }

  public getActiveRequestsSize(): number {
    return (this as any).activeRequests.size
  }

  public getRequestQueueLength(): number {
    return (this as any).requestQueue.length
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

  public async put(
    endpoint: string,
    data?: any,
    options?: RequestInit
  ): Promise<any> {
    return this.testRequest(endpoint, {
      ...options,
      method: 'PUT',
      body: data ? JSON.stringify(data) : undefined,
    })
  }

  public async patch(
    endpoint: string,
    data?: any,
    options?: RequestInit
  ): Promise<any> {
    return this.testRequest(endpoint, {
      ...options,
      method: 'PATCH',
      body: data ? JSON.stringify(data) : undefined,
    })
  }

  public async delete(endpoint: string, options?: RequestInit): Promise<any> {
    return this.testRequest(endpoint, { ...options, method: 'DELETE' })
  }

  public getCacheSize(): number {
    return (this as any).responseCache.size
  }
}

describe('BaseApiClient - Comprehensive Coverage', () => {
  let client: TestApiClient

  beforeEach(() => {
    jest.clearAllMocks()
    localStorageMock.getItem.mockReturnValue(null)
    client = new TestApiClient()
  })

  describe('Edge cases and error paths', () => {
    it('should handle retry-after header with integer value for rate limiting', async () => {
      ;(global.fetch as jest.Mock)
        .mockResolvedValueOnce({
          ok: false,
          status: 429,
          statusText: 'Too Many Requests',
          headers: new Headers({
            'content-type': 'application/json',
            'retry-after': '2',
          }),
          text: async () => JSON.stringify({ detail: 'Rate limited' }),
        })
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'application/json' }),
          text: async () => JSON.stringify({ success: true }),
        })

      const result = await client.get('/test')
      expect(result).toEqual({ success: true })
    })

    it('should handle 502 error and retry successfully', async () => {
      ;(global.fetch as jest.Mock)
        .mockResolvedValueOnce({
          ok: false,
          status: 502,
          statusText: 'Bad Gateway',
          headers: new Headers(),
          text: async () => 'Service temporarily unavailable',
        })
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'application/json' }),
          text: async () => JSON.stringify({ success: true }),
        })

      const result = await client.get('/test')
      expect(result).toEqual({ success: true })
    })

    it('should handle octet-stream content type as blob', async () => {
      const mockBlob = new Blob(['binary data'], {
        type: 'application/octet-stream',
      })

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/octet-stream' }),
        blob: async () => mockBlob,
      })

      const result = await client.get('/binary')
      expect(result).toBeInstanceOf(Blob)
    })

    it('should handle video content type as blob', async () => {
      const mockBlob = new Blob(['video data'], { type: 'video/mp4' })

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'video/mp4' }),
        blob: async () => mockBlob,
      })

      const result = await client.get('/video.mp4')
      expect(result).toBeInstanceOf(Blob)
    })

    it('should handle audio content type as blob', async () => {
      const mockBlob = new Blob(['audio data'], { type: 'audio/mpeg' })

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'audio/mpeg' }),
        blob: async () => mockBlob,
      })

      const result = await client.get('/audio.mp3')
      expect(result).toBeInstanceOf(Blob)
    })

    it('should handle refresh access token failure', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 401,
        statusText: 'Unauthorized',
        headers: new Headers(),
      })

      const refreshPromise = (client as any).refreshAccessToken()
      const result = await refreshPromise

      expect(result).toBe(false)
    })

    it('should handle refresh access token network error', async () => {
      ;(global.fetch as jest.Mock).mockRejectedValueOnce(
        new Error('Network error')
      )

      const refreshPromise = (client as any).refreshAccessToken()
      const result = await refreshPromise

      expect(result).toBe(false)
    })
  })

  describe('clearUserCache method', () => {
    it('should clear cache entries for specific user by userId in key', async () => {
      // Create fresh client to avoid cache pollution
      const freshClient = new TestApiClient()

      // Set up cache with user1
      localStorageMock.getItem.mockReturnValue('user1')
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        text: async () => JSON.stringify({ data: 'test1' }),
      })

      await freshClient.get('/endpoint1')

      // Change to user2 - this will clear the cache due to user change detection
      localStorageMock.getItem.mockReturnValue('user2')
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        text: async () => JSON.stringify({ data: 'test2' }),
      })

      await freshClient.get('/endpoint2')

      // After user change, cache should only have user2 data
      expect(freshClient.getCacheSize()).toBe(1)

      // Clear user2 cache
      freshClient.clearUserCache('user2')

      // Should have no cache left
      expect(freshClient.getCacheSize()).toBe(0)
    })

    it('should clear cache entries by userId in entry metadata', async () => {
      localStorageMock.getItem.mockReturnValue('test-user')
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        text: async () => JSON.stringify({ data: 'test' }),
      })

      await client.get('/endpoint')

      expect(client.getCacheSize()).toBe(1)

      client.clearUserCache('test-user')

      expect(client.getCacheSize()).toBe(0)
    })
  })

  describe('validateCacheEntry', () => {
    it('should invalidate cache entry with no userId for safety', async () => {
      // Manually inject cache entry without userId
      const cacheEntry = {
        data: { test: 'data' },
        timestamp: Date.now(),
        userId: undefined as any,
      }

      localStorageMock.getItem.mockReturnValue('current-user')

      // Access private method through bracket notation
      const isValid = (client as any).validateCacheEntry(
        cacheEntry,
        'current-user'
      )

      expect(isValid).toBe(false)
    })

    it('should clear entire cache on user mismatch', async () => {
      localStorageMock.getItem.mockReturnValue('user1')
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        text: async () => JSON.stringify({ data: 'test' }),
      })

      await client.get('/endpoint')
      expect(client.getCacheSize()).toBe(1)

      // Create entry with different user
      const cacheEntry = {
        data: { test: 'data' },
        timestamp: Date.now(),
        userId: 'different-user',
      }

      const isValid = (client as any).validateCacheEntry(cacheEntry, 'user1')

      expect(isValid).toBe(false)
      expect(client.getCacheSize()).toBe(0) // Cache cleared
    })

    it('should invalidate expired cache entries', async () => {
      const expiredEntry = {
        data: { test: 'data' },
        timestamp: Date.now() - 31000, // 31 seconds ago (expired)
        userId: 'test-user',
      }

      const isValid = (client as any).validateCacheEntry(
        expiredEntry,
        'test-user'
      )

      expect(isValid).toBe(false)
    })
  })

  describe('Token expiration checking', () => {
    it('should detect expired tokens', () => {
      const expiredToken = `header.${btoa(
        JSON.stringify({ exp: Math.floor(Date.now() / 1000) - 3600 })
      )}.signature`

      const isExpired = (client as any).isTokenExpired(expiredToken)

      expect(isExpired).toBe(true)
    })

    it('should detect tokens expiring within 30 seconds', () => {
      const soonToExpireToken = `header.${btoa(
        JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 20 })
      )}.signature`

      const isExpired = (client as any).isTokenExpired(soonToExpireToken)

      expect(isExpired).toBe(true)
    })

    it('should treat malformed tokens as expired', () => {
      const malformedToken = 'not.a.valid.jwt'

      const isExpired = (client as any).isTokenExpired(malformedToken)

      expect(isExpired).toBe(true)
    })
  })

  describe('Organization context provider', () => {
    it('should include organization context header when provider is set', async () => {
      const orgProvider = jest.fn(() => 'org-123')
      client.setOrganizationContextProvider(orgProvider)
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        text: async () => JSON.stringify({ success: true }),
      })

      await client.get('/test')

      expect(global.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            'X-Organization-Context': 'org-123',
          }),
        })
      )
    })

    it('should not include header when provider returns null', async () => {
      const orgProvider = jest.fn(() => null)
      client.setOrganizationContextProvider(orgProvider)
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        text: async () => JSON.stringify({ success: true }),
      })

      await client.get('/test')

      const fetchCall = (global.fetch as jest.Mock).mock.calls[0][1]
      expect(fetchCall.headers['X-Organization-Context']).toBeUndefined()
    })
  })

  describe('authCheckRequest method', () => {
    it('should handle 401 as expected for auth checks', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 401,
        statusText: 'Unauthorized',
        headers: new Headers(),
        text: async () => '',
      })

      await expect(client.testAuthCheck('/auth/check')).rejects.toThrow(
        'Unauthenticated'
      )
    })

    it('should handle 204 No Content in authCheckRequest', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 204,
        headers: new Headers(),
      })

      const result = await client.testAuthCheck('/test', { method: 'POST' })

      expect(result).toBeUndefined()
    })

    it('should handle FormData in authCheckRequest', async () => {
      const formData = new FormData()
      formData.append('key', 'value')
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        text: async () => JSON.stringify({ success: true }),
      })

      await client.testAuthCheck('/test', {
        method: 'POST',
        body: formData,
      })

      const fetchCall = (global.fetch as jest.Mock).mock.calls[0][1]
      expect(fetchCall.headers['Content-Type']).toBeUndefined()
    })

    it('should handle network errors in authCheckRequest', async () => {
      ;(global.fetch as jest.Mock).mockRejectedValueOnce(
        new TypeError('fetch failed')
      )

      await expect(client.testAuthCheck('/test')).rejects.toThrow(
        'Network error'
      )
    })

    it('should return null for empty JSON response', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        text: async () => '',
      })

      const result = await client.testAuthCheck('/test')

      expect(result).toBeNull()
    })

    it('should throw on invalid JSON in authCheckRequest', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        text: async () => '{invalid json',
      })

      await expect(client.testAuthCheck('/test')).rejects.toThrow(
        'Invalid JSON response'
      )
    })

    it('should return text for non-JSON responses', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'text/plain' }),
        text: async () => 'Plain text response',
      })

      const result = await client.testAuthCheck('/test')

      expect(result).toBe('Plain text response')
    })

    it('should handle errors with error text in authCheckRequest', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        headers: new Headers(),
        text: async () => 'Error details',
      })

      await expect(client.testAuthCheck('/test')).rejects.toThrow(
        'HTTP error! status: 400 - Error details'
      )
    })

    it('should handle errors when text reading fails', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        headers: new Headers(),
        text: async () => {
          throw new Error('Cannot read text')
        },
      })

      await expect(client.testAuthCheck('/test')).rejects.toThrow(
        'HTTP error! status: 500'
      )
    })
  })

  describe('Request queue management', () => {
    it('should queue requests when max concurrent limit reached', async () => {
      // Create 15 simultaneous requests (max is 10)
      const requests: Promise<any>[] = []

      for (let i = 0; i < 15; i++) {
        ;(global.fetch as jest.Mock).mockResolvedValueOnce({
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'application/json' }),
          text: async () => JSON.stringify({ id: i }),
        })

        requests.push(client.get(`/endpoint${i}`))
      }

      // Some requests should be queued
      await new Promise((resolve) => setTimeout(resolve, 50))

      // All should eventually complete
      await Promise.all(requests)

      expect(global.fetch).toHaveBeenCalledTimes(15)
    })

    it('should process request queue as requests complete', async () => {
      // Mock slow responses
      ;(global.fetch as jest.Mock).mockImplementation(
        () =>
          new Promise((resolve) =>
            setTimeout(
              () =>
                resolve({
                  ok: true,
                  status: 200,
                  headers: new Headers({ 'content-type': 'application/json' }),
                  text: async () => JSON.stringify({ success: true }),
                }),
              10
            )
          )
      )

      const requests = []
      for (let i = 0; i < 12; i++) {
        requests.push(client.get(`/endpoint${i}`))
      }

      await Promise.all(requests)

      expect(global.fetch).toHaveBeenCalledTimes(12)
    })
  })

  describe('Token refresh logic', () => {
    it('should refresh token on 401 and retry request', async () => {
      const mockAuthFailure = jest.fn()
      client.setAuthFailureHandler(mockAuthFailure)

      // First call fails with 401
      ;(global.fetch as jest.Mock)
        .mockResolvedValueOnce({
          ok: false,
          status: 401,
          statusText: 'Unauthorized',
          headers: new Headers(),
          text: async () => '',
        })
        // Refresh succeeds
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          headers: new Headers(),
        })
        // Retry succeeds
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'application/json' }),
          text: async () => JSON.stringify({ success: true }),
        })

      const result = await client.get('/test')

      expect(result).toEqual({ success: true })
      expect(global.fetch).toHaveBeenCalledTimes(3)
      expect(mockAuthFailure).not.toHaveBeenCalled()
    })

    it('should trigger auth failure when refresh fails', async () => {
      const mockAuthFailure = jest.fn()
      client.setAuthFailureHandler(mockAuthFailure)

      // First call fails with 401
      ;(global.fetch as jest.Mock)
        .mockResolvedValueOnce({
          ok: false,
          status: 401,
          statusText: 'Unauthorized',
          headers: new Headers(),
          text: async () => '',
        })
        // Refresh fails
        .mockResolvedValueOnce({
          ok: false,
          status: 401,
          headers: new Headers(),
        })

      await expect(client.get('/test')).rejects.toThrow()

      expect(mockAuthFailure).toHaveBeenCalled()
    })

    it('should not trigger auth failure for /auth/refresh endpoint', async () => {
      const mockAuthFailure = jest.fn()
      client.setAuthFailureHandler(mockAuthFailure)
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 401,
        statusText: 'Unauthorized',
        headers: new Headers(),
        text: async () => '',
      })

      await expect(client.post('/auth/refresh')).rejects.toThrow()

      expect(mockAuthFailure).not.toHaveBeenCalled()
    })

    it('should not trigger auth failure for /feature-flags endpoint', async () => {
      const mockAuthFailure = jest.fn()
      client.setAuthFailureHandler(mockAuthFailure)
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 401,
        statusText: 'Unauthorized',
        headers: new Headers(),
        text: async () => '',
      })

      await expect(client.get('/feature-flags')).rejects.toThrow()

      expect(mockAuthFailure).not.toHaveBeenCalled()
    })

    it('should use valid access token from localStorage', async () => {
      const validToken = `header.${btoa(
        JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 3600 })
      )}.signature`

      localStorageMock.getItem.mockImplementation((key) => {
        if (key === 'access_token') return validToken
        return null
      })
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        text: async () => JSON.stringify({ success: true }),
      })

      await client.get('/test')

      expect(global.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            Authorization: `Bearer ${validToken}`,
          }),
        })
      )
    })

    it('should not use expired token from localStorage', async () => {
      const expiredToken = `header.${btoa(
        JSON.stringify({ exp: Math.floor(Date.now() / 1000) - 3600 })
      )}.signature`

      localStorageMock.getItem.mockImplementation((key) => {
        if (key === 'access_token') return expiredToken
        return null
      })
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        text: async () => JSON.stringify({ success: true }),
      })

      await client.get('/test')

      const fetchCall = (global.fetch as jest.Mock).mock.calls[0][1]
      expect(fetchCall.headers.Authorization).toBeUndefined()
    })
  })

  describe('Blob responses', () => {
    it('should handle application/zip responses as blob', async () => {
      const mockBlob = new Blob(['test data'], { type: 'application/zip' })

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/zip' }),
        blob: async () => mockBlob,
      })

      const result = await client.get('/download')

      expect(result).toBeInstanceOf(Blob)
      expect(result.type).toBe('application/zip')
    })

    it('should handle application/pdf responses as blob', async () => {
      const mockBlob = new Blob(['pdf data'], { type: 'application/pdf' })

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/pdf' }),
        blob: async () => mockBlob,
      })

      const result = await client.get('/document.pdf')

      expect(result).toBeInstanceOf(Blob)
      expect(result.type).toBe('application/pdf')
    })

    it('should handle image responses as blob', async () => {
      const mockBlob = new Blob(['image data'], { type: 'image/png' })

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'image/png' }),
        blob: async () => mockBlob,
      })

      const result = await client.get('/image.png')

      expect(result).toBeInstanceOf(Blob)
    })
  })

  describe('Text responses', () => {
    it('should handle plain text responses', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'text/plain' }),
        text: async () => 'Plain text response',
      })

      const result = await client.get('/text')

      expect(result).toBe('Plain text response')
    })

    it('should cache text responses for GET requests', async () => {
      localStorageMock.getItem.mockReturnValue('user1')
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'text/plain' }),
        text: async () => 'Cached text',
      })

      const result1 = await client.get('/text')
      expect(result1).toBe('Cached text')

      // Second request should use cache
      const result2 = await client.get('/text')
      expect(result2).toBe('Cached text')
      expect(global.fetch).toHaveBeenCalledTimes(1)
    })

    it('should invalidate cache after PUT mutation on text endpoint', async () => {
      localStorageMock.getItem.mockReturnValue('user1')
      ;(global.fetch as jest.Mock)
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'text/plain' }),
          text: async () => 'Original text',
        })
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'text/plain' }),
          text: async () => 'Updated',
        })

      await client.get('/document')

      await client.put('/document', { content: 'new' })

      expect(client.getCacheSize()).toBe(0)
    })
  })

  describe('HTTP convenience methods', () => {
    it('should handle POST with FormData', async () => {
      const formData = new FormData()
      formData.append('file', 'test')
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        text: async () => JSON.stringify({ success: true }),
      })

      const result = await client.post('/upload', formData)

      expect(result).toEqual({ success: true })
      const fetchCall = (global.fetch as jest.Mock).mock.calls[0][1]
      expect(fetchCall.body).toBeInstanceOf(FormData)
    })

    it('should handle POST with undefined data', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        text: async () => JSON.stringify({ success: true }),
      })

      await client.post('/endpoint', undefined)

      const fetchCall = (global.fetch as jest.Mock).mock.calls[0][1]
      expect(fetchCall.body).toBeUndefined()
    })

    it('should handle PUT with data', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        text: async () => JSON.stringify({ updated: true }),
      })

      const result = await client.put('/resource', { field: 'value' })

      expect(result).toEqual({ updated: true })
    })

    it('should handle PATCH method', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        text: async () => JSON.stringify({ patched: true }),
      })

      const result = await client.patch('/resource', { field: 'value' })

      expect(result).toEqual({ patched: true })
    })

    it('should handle DELETE method', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 204,
        headers: new Headers(),
      })

      const result = await client.delete('/resource')

      expect(result).toBeUndefined()
    })
  })

  describe('User change detection', () => {
    it('should clear cache when user changes', async () => {
      localStorageMock.getItem.mockReturnValue('user1')
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        text: async () => JSON.stringify({ data: 'user1' }),
      })

      await client.get('/data')
      expect(client.getCacheSize()).toBe(1)

      // User changes
      localStorageMock.getItem.mockReturnValue('user2')
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        text: async () => JSON.stringify({ data: 'user2' }),
      })

      await client.get('/data')

      // Cache should be cleared and repopulated with user2 data
      expect(client.getCacheSize()).toBe(1)
    })
  })

  describe('Request timeout', () => {
    it('should use custom signal if provided', async () => {
      const controller = new AbortController()
      const customSignal = controller.signal

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        text: async () => JSON.stringify({ success: true }),
      })

      await client.get('/test', { signal: customSignal })

      const fetchCall = (global.fetch as jest.Mock).mock.calls[0][1]
      expect(fetchCall.signal).toBe(customSignal)
    })
  })

  describe('Error response text reading failures', () => {
    it('should handle error when reading error text fails', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        headers: new Headers(),
        text: async () => {
          throw new Error('Cannot read text')
        },
      })

      await expect(client.get('/test')).rejects.toThrow(
        'HTTP error! status: 500'
      )
    })
  })

  describe('Empty JSON handling', () => {
    it('should return null for empty JSON text in successful response', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        text: async () => '',
      })

      const result = await client.get('/test')

      expect(result).toBeNull()
    })

    it('should throw error for invalid JSON in successful response', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        text: async () => '{invalid json',
      })

      try {
        await client.get('/test')
        fail('Should have thrown an error')
      } catch (error: any) {
        expect(error.message).toContain('Invalid JSON response')
      }
    })
  })

  describe('Network retry logic', () => {
    it('should retry on network errors and eventually succeed', async () => {
      const networkError = new TypeError('fetch failed')

      ;(global.fetch as jest.Mock)
        .mockRejectedValueOnce(networkError)
        .mockRejectedValueOnce(networkError)
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'application/json' }),
          text: async () => JSON.stringify({ success: true }),
        })

      const result = await client.get('/test')

      expect(result).toEqual({ success: true })
      expect(global.fetch).toHaveBeenCalledTimes(3)
    })

    it('should throw network error after max retries', async () => {
      const networkError = new TypeError('fetch failed')

      ;(global.fetch as jest.Mock)
        .mockRejectedValueOnce(networkError)
        .mockRejectedValueOnce(networkError)
        .mockRejectedValueOnce(networkError)

      await expect(client.get('/test')).rejects.toThrow('Network error')

      expect(global.fetch).toHaveBeenCalledTimes(3)
    })
  })
})
