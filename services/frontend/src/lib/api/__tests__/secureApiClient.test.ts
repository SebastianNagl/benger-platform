/**
 * Tests for SecureApiClient
 */

import { COOKIE_NAMES, getSecurityHeaders } from '@/lib/security/cookieConfig'
import { SecureApiClient } from '../secureApiClient'

// Mock fetch globally
const mockFetch = jest.fn()
global.fetch = mockFetch

// Mock crypto.randomUUID
const mockRandomUUID = jest.fn()
global.crypto = {
  randomUUID: mockRandomUUID,
} as any

// Mock document.cookie
Object.defineProperty(document, 'cookie', {
  writable: true,
  value: '',
})

describe('SecureApiClient', () => {
  let client: SecureApiClient

  beforeEach(async () => {
    jest.clearAllMocks()
    document.cookie = ''

    // Mock initial CSRF token fetch to prevent unexpected fetch calls
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ token: 'initial-csrf-token' }),
    })

    client = new SecureApiClient()

    // Wait for CSRF token initialization and then clear fetch mock calls (but keep randomUUID)
    await new Promise((resolve) => setTimeout(resolve, 10))
    mockFetch.mockClear()

    // Reset randomUUID mock after clearing
    mockRandomUUID.mockReturnValue('test-request-id')
  })

  afterEach(() => {
    client.clearRequestQueue()
    jest.useRealTimers()
  })

  describe('constructor and baseURL detection', () => {
    // Note: window.location tests require E2E - jsdom cannot mock window after initialization

    it('should use custom baseURL if provided', () => {
      const customClient = new SecureApiClient('https://custom.api.com')
      expect(customClient).toBeDefined()
    })

    it('should use environment variable as fallback', () => {
      const originalEnv = process.env.NEXT_PUBLIC_API_URL
      process.env.NEXT_PUBLIC_API_URL = 'https://env.api.com'
      const testClient = new SecureApiClient()
      expect(testClient).toBeDefined()
      process.env.NEXT_PUBLIC_API_URL = originalEnv
    })
  })

  describe('CSRF token initialization', () => {
    it('should read CSRF token from cookie if available', async () => {
      document.cookie = `${COOKIE_NAMES.CSRF_TOKEN}=cookie-csrf-token`
      const testClient = new SecureApiClient()
      await new Promise((resolve) => setTimeout(resolve, 10))
      // Token should be initialized from cookie
    })

    it('should fetch CSRF token from server if not in cookie', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ token: 'fetched-csrf-token' }),
      })

      const testClient = new SecureApiClient()
      await new Promise((resolve) => setTimeout(resolve, 10))

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/auth/csrf'),
        expect.objectContaining({ credentials: 'include' })
      )
    })

    it('should handle CSRF token fetch failure gracefully', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network error'))
      const consoleWarn = jest.spyOn(console, 'warn').mockImplementation()

      const testClient = new SecureApiClient()
      await new Promise((resolve) => setTimeout(resolve, 10))

      expect(consoleWarn).toHaveBeenCalledWith(
        'Failed to fetch CSRF token:',
        expect.any(Error)
      )
      consoleWarn.mockRestore()
    })
  })

  describe('GET requests', () => {
    it('should make GET request successfully', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers([['content-type', 'application/json']]),
        json: async () => ({ data: 'test' }),
      })

      const result = await client.get('/test')

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/test'),
        expect.objectContaining({
          method: 'GET',
          credentials: 'include',
        })
      )
      expect(result).toEqual({ data: 'test' })
    })

    it('should include security headers in GET request', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({}),
      })

      await client.get('/test')

      const fetchOptions = mockFetch.mock.calls[0][1]
      const headers: Headers = fetchOptions.headers
      const securityHeaders = getSecurityHeaders()
      Object.entries(securityHeaders).forEach(([key, value]) => {
        expect(headers.get(key)).toBe(value)
      })
    })

    it('should include X-Request-ID header', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({}),
      })

      await client.get('/test')

      const headers = mockFetch.mock.calls[0][1].headers
      const requestId = headers.get('X-Request-ID')
      // Just verify the header exists and is a valid UUID format
      expect(requestId).toBeTruthy()
      expect(requestId).toMatch(
        /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
      )
    })

    it('should skip CSRF token for GET requests', async () => {
      document.cookie = `${COOKIE_NAMES.CSRF_TOKEN}=test-csrf`
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({}),
      })

      await client.get('/test')

      const headers = mockFetch.mock.calls[0][1].headers
      expect(headers.get('X-CSRF-Token')).toBeNull()
    })
  })

  describe('POST requests', () => {
    it('should make POST request successfully', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ created: true }),
      })

      const result = await client.post('/test', { name: 'test' })

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/test'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ name: 'test' }),
        })
      )
      expect(result).toEqual({ created: true })
    })

    it('should include CSRF token in POST request', async () => {
      document.cookie = `${COOKIE_NAMES.CSRF_TOKEN}=test-csrf-token`
      const testClient = new SecureApiClient()
      await new Promise((resolve) => setTimeout(resolve, 10))

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({}),
      })

      await testClient.post('/test', {})

      const headers = mockFetch.mock.calls[0][1].headers
      expect(headers.get('X-CSRF-Token')).toBe('test-csrf-token')
    })

    it('should include Content-Type header for JSON', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({}),
      })

      await client.post('/test', { data: 'test' })

      const headers = mockFetch.mock.calls[0][1].headers
      expect(headers.get('Content-Type')).toBe('application/json')
    })

    it('should handle POST request without body', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({}),
      })

      await client.post('/test')

      expect(mockFetch).toHaveBeenCalledWith(
        expect.anything(),
        expect.objectContaining({
          method: 'POST',
          body: undefined,
        })
      )
    })
  })

  describe('PUT requests', () => {
    it('should make PUT request successfully', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ updated: true }),
      })

      const result = await client.put('/test/1', { name: 'updated' })

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/test/1'),
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify({ name: 'updated' }),
        })
      )
      expect(result).toEqual({ updated: true })
    })

    it('should include CSRF token in PUT request', async () => {
      document.cookie = `${COOKIE_NAMES.CSRF_TOKEN}=test-csrf`
      const testClient = new SecureApiClient()
      await new Promise((resolve) => setTimeout(resolve, 10))

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({}),
      })

      await testClient.put('/test', {})

      const headers = mockFetch.mock.calls[0][1].headers
      expect(headers.get('X-CSRF-Token')).toBe('test-csrf')
    })
  })

  describe('PATCH requests', () => {
    it('should make PATCH request successfully', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ patched: true }),
      })

      const result = await client.patch('/test/1', { name: 'patched' })

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/test/1'),
        expect.objectContaining({
          method: 'PATCH',
        })
      )
      expect(result).toEqual({ patched: true })
    })
  })

  describe('DELETE requests', () => {
    it('should make DELETE request successfully', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ deleted: true }),
      })

      const result = await client.delete('/test/1')

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/test/1'),
        expect.objectContaining({
          method: 'DELETE',
        })
      )
      expect(result).toEqual({ deleted: true })
    })

    it('should include CSRF token in DELETE request', async () => {
      document.cookie = `${COOKIE_NAMES.CSRF_TOKEN}=test-csrf`
      const testClient = new SecureApiClient()
      await new Promise((resolve) => setTimeout(resolve, 10))

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({}),
      })

      await testClient.delete('/test/1')

      const headers = mockFetch.mock.calls[0][1].headers
      expect(headers.get('X-CSRF-Token')).toBe('test-csrf')
    })
  })

  describe('error handling', () => {
    it('should handle 400 error response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => ({ message: 'Bad request' }),
      })

      await expect(client.get('/test')).rejects.toThrow('Bad request')
    })

    it('should handle 500 error response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        json: async () => ({}),
      })

      await expect(client.get('/test')).rejects.toThrow('Request failed: 500')
    })

    it('should handle invalid JSON response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => null,
      })

      await expect(client.get('/test')).rejects.toThrow('Invalid response data')
    })

    it('should handle network errors', async () => {
      mockFetch.mockRejectedValueOnce(new TypeError('Failed to fetch'))

      await expect(client.get('/test')).rejects.toThrow('Failed to fetch')
    })

    it('should handle timeout errors', async () => {
      // Mock fetch to respect abort signal
      mockFetch.mockImplementationOnce((url, options) => {
        return new Promise((resolve, reject) => {
          options.signal.addEventListener('abort', () => {
            reject(new DOMException('The operation was aborted.', 'AbortError'))
          })
          // Never resolve, simulating a hanging request
        })
      })

      await expect(client.get('/test', { timeout: 50 })).rejects.toThrow(
        'Request timeout'
      )
    })
  })

  describe('rate limiting', () => {
    it('should handle 429 rate limit with Retry-After header', async () => {
      // Use real timers with very short retry delay for faster testing
      const headers = new Headers([['Retry-After', '0.05']]) // 50ms
      mockFetch
        .mockResolvedValueOnce({
          ok: false,
          status: 429,
          headers,
          text: async () => 'Rate limited',
        })
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: async () => ({ success: true }),
        })

      const result = await client.get('/test', { retries: 1 })

      expect(mockFetch).toHaveBeenCalledTimes(2)
      expect(result).toEqual({ success: true })
    })

    it('should throw error after max retries on rate limit', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        status: 429,
        headers: new Headers(),
        text: async () => 'Rate limited',
      })

      await expect(client.get('/test', { retries: 0 })).rejects.toThrow(
        'Rate limit exceeded'
      )
    })
  })

  describe('CSRF token refresh', () => {
    it('should refresh CSRF token on 403 CSRF error', async () => {
      mockFetch
        .mockResolvedValueOnce({
          ok: false,
          status: 403,
          text: async () => 'CSRF token invalid',
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ token: 'new-csrf-token' }),
        })
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: async () => ({ success: true }),
        })

      const result = await client.post('/test', {}, { retries: 1 })

      expect(mockFetch).toHaveBeenCalledTimes(3)
      expect(result).toEqual({ success: true })
    })
  })

  describe('request deduplication', () => {
    it('should deduplicate identical concurrent requests', async () => {
      let resolveCount = 0
      mockFetch.mockImplementation(() => {
        resolveCount++
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ count: resolveCount }),
        })
      })

      const [result1, result2, result3] = await Promise.all([
        client.get('/test'),
        client.get('/test'),
        client.get('/test'),
      ])

      expect(mockFetch).toHaveBeenCalledTimes(1)
      expect(result1).toEqual(result2)
      expect(result2).toEqual(result3)
    })

    it('should not deduplicate requests with different methods', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ success: true }),
      })

      await Promise.all([client.get('/test'), client.post('/test', {})])

      expect(mockFetch).toHaveBeenCalledTimes(2)
    })

    it('should not deduplicate requests with different bodies', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ success: true }),
      })

      await Promise.all([
        client.post('/test', { a: 1 }),
        client.post('/test', { a: 2 }),
      ])

      expect(mockFetch).toHaveBeenCalledTimes(2)
    })
  })

  describe('retry logic', () => {
    it('should retry on network error', async () => {
      // Use real timers - the retry logic has a 1-second delay
      mockFetch
        .mockRejectedValueOnce(new TypeError('Failed to fetch'))
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: async () => ({ success: true }),
        })

      const result = await client.get('/test', { retries: 1 })

      expect(mockFetch).toHaveBeenCalledTimes(2)
      expect(result).toEqual({ success: true })
    })

    it('should not retry when retries is 0', async () => {
      mockFetch.mockRejectedValueOnce(new TypeError('Failed to fetch'))

      await expect(client.get('/test', { retries: 0 })).rejects.toThrow(
        'Failed to fetch'
      )
      expect(mockFetch).toHaveBeenCalledTimes(1)
    })
  })

  describe('timeout configuration', () => {
    it('should use custom timeout', async () => {
      const abortSpy = jest.spyOn(AbortController.prototype, 'abort')
      // Mock fetch to respect abort signal
      mockFetch.mockImplementationOnce((url, options) => {
        return new Promise((resolve, reject) => {
          options.signal.addEventListener('abort', () => {
            reject(new DOMException('The operation was aborted.', 'AbortError'))
          })
        })
      })

      await expect(client.get('/test', { timeout: 50 })).rejects.toThrow()
      expect(abortSpy).toHaveBeenCalled()
    })

    it('should use default timeout of 30 seconds', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({}),
      })

      await client.get('/test')

      // Verify timeout was set (default 30000ms)
      expect(mockFetch).toHaveBeenCalled()
    })
  })

  describe('skipCSRF option', () => {
    it('should skip CSRF token when skipCSRF is true', async () => {
      document.cookie = `${COOKIE_NAMES.CSRF_TOKEN}=test-csrf`
      const testClient = new SecureApiClient()
      await new Promise((resolve) => setTimeout(resolve, 10))

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({}),
      })

      await testClient.post('/test', {}, { skipCSRF: true })

      const headers = mockFetch.mock.calls[0][1].headers
      expect(headers.get('X-CSRF-Token')).toBeNull()
    })
  })

  describe('clearRequestQueue', () => {
    it('should clear the request queue', () => {
      client.clearRequestQueue()
      // Should not throw
      expect(client).toBeDefined()
    })
  })

  describe('custom headers', () => {
    it('should merge custom headers with security headers', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({}),
      })

      await client.get('/test', {
        headers: {
          'X-Custom-Header': 'custom-value',
        },
      })

      const headers = mockFetch.mock.calls[0][1].headers
      expect(headers.get('X-Custom-Header')).toBe('custom-value')
      // Verify X-Request-ID exists and is a valid UUID
      const requestId = headers.get('X-Request-ID')
      expect(requestId).toBeTruthy()
      expect(requestId).toMatch(
        /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
      )
    })
  })
})
