/**
 * Tests for BaseApiClient Enhanced Error Handling
 * Verifies the improved error response parsing and axios-like error structure
 */

// IMPORTANT: Unmock BaseApiClient to test the real implementation
// The global mock in setupTests.ts makes all methods return {} successfully
jest.unmock('@/lib/api/base')

import { BaseApiClient } from '../base'

// Mock fetch globally
global.fetch = jest.fn()

// Mock localStorage before importing anything
const localStorageMock = {
  getItem: jest.fn(() => null),
  setItem: jest.fn(),
  removeItem: jest.fn(),
  clear: jest.fn(),
}

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
  writable: true,
})

// Test helper class to expose protected methods
class TestApiClient extends BaseApiClient {
  public async get(endpoint: string, options?: RequestInit): Promise<any> {
    return this.request(endpoint, { ...options, method: 'GET' })
  }

  public async post(
    endpoint: string,
    body?: any,
    options?: RequestInit
  ): Promise<any> {
    const bodyStr = typeof body === 'string' ? body : JSON.stringify(body)
    return this.request(endpoint, {
      ...options,
      method: 'POST',
      body: bodyStr,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    })
  }

  public async testRequest(
    endpoint: string,
    options?: RequestInit
  ): Promise<any> {
    return this.request(endpoint, options)
  }
}

describe('BaseApiClient - Enhanced Error Handling', () => {
  let client: TestApiClient
  let originalFetch: typeof fetch

  beforeEach(() => {
    jest.clearAllMocks()

    // Store original fetch
    originalFetch = global.fetch

    // Reset localStorage mocks
    localStorageMock.getItem.mockReturnValue(null)
    localStorageMock.setItem.mockClear()

    // Create fresh client
    client = new TestApiClient()
  })

  afterEach(() => {
    // Restore original fetch
    global.fetch = originalFetch
    jest.restoreAllMocks()
  })

  describe('JSON Error Response Parsing', () => {
    it('should parse JSON error responses and extract detail message', async () => {
      // Mock the fetch response
      const errorResponse = {
        detail: 'An active invitation already exists for this email',
      }

      global.fetch = jest.fn().mockImplementation((...args) => {
        console.log('Fetch called with:', args)
        return Promise.resolve({
          ok: false,
          status: 400,
          statusText: 'Bad Request',
          headers: new Headers({ 'content-type': 'application/json' }),
          text: async () => JSON.stringify(errorResponse),
        })
      })

      try {
        const result = await client.get('/test-endpoint')
        console.log('Result received (should have thrown):', result)
        throw new Error('Should have thrown an error')
      } catch (error: any) {
        // Log what we got to debug
        console.log('Error caught:', error.message)
        if (error.message === 'Should have thrown an error') {
          throw error
        }
        // Should have axios-like error structure
        expect(error.message).toBe(
          'An active invitation already exists for this email'
        )
        expect(error.response).toBeDefined()
        expect(error.response.status).toBe(400)
        expect(error.response.statusText).toBe('Bad Request')
        expect(error.response.data).toEqual({
          detail: 'An active invitation already exists for this email',
        })
      }
    })

    it('should parse JSON error responses with message field', async () => {
      global.fetch = jest.fn().mockResolvedValueOnce({
        ok: false,
        status: 403,
        statusText: 'Forbidden',
        headers: new Headers({ 'content-type': 'application/json' }),
        text: async () =>
          JSON.stringify({
            message: 'You do not have permission to perform this action',
            code: 'PERMISSION_DENIED',
          }),
      })

      try {
        await client.post('/test-endpoint', { data: 'test' })
        throw new Error('Should have thrown an error')
      } catch (error: any) {
        if (error.message === 'Should have thrown an error') {
          throw error
        }
        expect(error.message).toBe(
          'You do not have permission to perform this action'
        )
        expect(error.response.status).toBe(403)
        expect(error.response.data.code).toBe('PERMISSION_DENIED')
      }
    })

    it('should handle plain text error responses', async () => {
      global.fetch = jest.fn().mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        headers: new Headers({ 'content-type': 'text/plain' }),
        text: async () => 'Internal server error occurred',
      })

      try {
        await client.get('/test-endpoint')
        throw new Error('Should have thrown an error')
      } catch (error: any) {
        if (error.message === 'Should have thrown an error') {
          throw error
        }
        expect(error.message).toBe(
          'HTTP error! status: 500 - Internal server error occurred'
        )
        expect(error.response.status).toBe(500)
        expect(error.response.data).toBeNull()
      }
    })

    it('should handle malformed JSON in error responses', async () => {
      global.fetch = jest.fn().mockResolvedValueOnce({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        headers: new Headers({ 'content-type': 'application/json' }),
        text: async () => '{"broken json',
      })

      try {
        await client.get('/test-endpoint')
        throw new Error('Should have thrown an error')
      } catch (error: any) {
        if (error.message === 'Should have thrown an error') {
          throw error
        }
        expect(error.message).toBe('HTTP error! status: 400 - {"broken json')
        expect(error.response.status).toBe(400)
        expect(error.response.data).toBeNull()
      }
    })

    it('should handle empty error responses', async () => {
      global.fetch = jest.fn().mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        headers: new Headers(),
        text: async () => '',
      })

      try {
        await client.get('/test-endpoint')
        throw new Error('Should have thrown an error')
      } catch (error: any) {
        if (error.message === 'Should have thrown an error') {
          throw error
        }
        expect(error.message).toBe('HTTP error! status: 404')
        expect(error.response.status).toBe(404)
        expect(error.response.data).toBeNull()
      }
    })
  })

  describe('Axios-like Error Structure', () => {
    it('should create axios-compatible error structure', async () => {
      global.fetch = jest.fn().mockResolvedValueOnce({
        ok: false,
        status: 422,
        statusText: 'Unprocessable Entity',
        headers: new Headers({ 'content-type': 'application/json' }),
        text: async () =>
          JSON.stringify({
            detail: 'Validation error',
            errors: [{ field: 'email', message: 'Invalid email format' }],
          }),
      })

      try {
        await client.post('/test-endpoint', { email: 'invalid' })
        throw new Error('Should have thrown an error')
      } catch (error: any) {
        if (error.message === 'Should have thrown an error') {
          throw error
        }
        // Verify axios-like structure
        expect(error).toBeInstanceOf(Error)
        expect(error.message).toBe('Validation error')

        // Check response property
        expect(error.response).toBeDefined()
        expect(error.response.status).toBe(422)
        expect(error.response.statusText).toBe('Unprocessable Entity')
        expect(error.response.data).toEqual({
          detail: 'Validation error',
          errors: [{ field: 'email', message: 'Invalid email format' }],
        })
      }
    })

    it('should maintain backward compatibility with error.response?.data?.detail pattern', async () => {
      global.fetch = jest.fn().mockResolvedValueOnce({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        headers: new Headers({ 'content-type': 'application/json' }),
        text: async () =>
          JSON.stringify({
            detail: 'Custom error message',
          }),
      })

      try {
        await client.get('/test-endpoint')
        throw new Error('Should have thrown an error')
      } catch (error: any) {
        if (error.message === 'Should have thrown an error') {
          throw error
        }
        // Frontend code expects this pattern
        expect(error.response?.data?.detail).toBe('Custom error message')
      }
    })
  })

  describe('Special Error Cases', () => {
    it('should handle 401 errors without triggering logout for specific endpoints', async () => {
      const mockAuthFailure = jest.fn()
      client.setAuthFailureHandler(mockAuthFailure)

      // Test auth/logout endpoint - should not trigger auth failure
      global.fetch = jest.fn().mockResolvedValueOnce({
        ok: false,
        status: 401,
        statusText: 'Unauthorized',
        headers: new Headers(),
        text: async () => '',
      })

      const result = await client.testRequest('/auth/logout')
      expect(result).toBeUndefined()
      expect(mockAuthFailure).not.toHaveBeenCalled()
    })

    it('should handle rate limiting with proper error structure', async () => {
      // Mock 4 responses: initial + 3 retries, all return 429
      // After 3 retries, it should throw the error
      global.fetch = jest
        .fn()
        .mockResolvedValueOnce({
          ok: false,
          status: 429,
          statusText: 'Too Many Requests',
          headers: new Headers({
            'content-type': 'application/json',
            'retry-after': '0.01', // Very short delay for testing
          }),
          text: async () =>
            JSON.stringify({
              detail: 'Rate limit exceeded',
            }),
        })
        .mockResolvedValueOnce({
          ok: false,
          status: 429,
          statusText: 'Too Many Requests',
          headers: new Headers({
            'content-type': 'application/json',
            'retry-after': '0.01',
          }),
          text: async () =>
            JSON.stringify({
              detail: 'Rate limit exceeded',
            }),
        })
        .mockResolvedValueOnce({
          ok: false,
          status: 429,
          statusText: 'Too Many Requests',
          headers: new Headers({
            'content-type': 'application/json',
            'retry-after': '0.01',
          }),
          text: async () =>
            JSON.stringify({
              detail: 'Rate limit exceeded',
            }),
        })
        .mockResolvedValueOnce({
          ok: false,
          status: 429,
          statusText: 'Too Many Requests',
          headers: new Headers({
            'content-type': 'application/json',
            'retry-after': '0.01',
          }),
          text: async () =>
            JSON.stringify({
              detail: 'Rate limit exceeded',
            }),
        })

      try {
        await client.post('/invitations', {})
        throw new Error('Should have thrown an error')
      } catch (error: any) {
        if (error.message === 'Should have thrown an error') {
          throw error
        }
        expect(error.message).toBe('Rate limit exceeded')
        expect(error.response.status).toBe(429)
        expect(error.response.data.detail).toBe('Rate limit exceeded')
      }
    })

    it('should handle network errors', async () => {
      // Mock fetch to throw TypeError with "fetch" in message
      // BaseApiClient will retry twice before throwing the network error
      const networkError = new TypeError('fetch failed')
      global.fetch = jest
        .fn()
        .mockRejectedValueOnce(networkError)
        .mockRejectedValueOnce(networkError)
        .mockRejectedValueOnce(networkError)

      try {
        await client.get('/test-endpoint')
        throw new Error('Should have thrown an error')
      } catch (error: any) {
        if (error.message === 'Should have thrown an error') {
          throw error
        }
        expect(error.message).toContain('Network error')
        expect(error.message).toContain('Unable to connect to API')
      }
    })

    it('should handle 502/503 service errors with retry', async () => {
      // First attempt fails with 503
      global.fetch = jest
        .fn()
        .mockResolvedValueOnce({
          ok: false,
          status: 503,
          statusText: 'Service Unavailable',
          headers: new Headers(),
          text: async () => 'Service temporarily unavailable',
        })
        // Retry succeeds
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'application/json' }),
          text: async () => JSON.stringify({ success: true }),
        })

      // Just verify the retry happens without fake timers
      // Fake timers cause issues with async/await in BaseApiClient
      const result = await client.get('/test-endpoint')

      expect(result).toEqual({ success: true })
      expect(global.fetch).toHaveBeenCalledTimes(2)
    })
  })

  describe('Error Message Priority', () => {
    it('should prioritize detail field over message field', async () => {
      global.fetch = jest.fn().mockResolvedValueOnce({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        headers: new Headers({ 'content-type': 'application/json' }),
        text: async () =>
          JSON.stringify({
            detail: 'Specific error detail',
            message: 'Generic error message',
          }),
      })

      try {
        await client.get('/test-endpoint')
        throw new Error('Should have thrown an error')
      } catch (error: any) {
        if (error.message === 'Should have thrown an error') {
          throw error
        }
        expect(error.message).toBe('Specific error detail')
      }
    })

    it('should use message field when detail is not available', async () => {
      global.fetch = jest.fn().mockResolvedValueOnce({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        headers: new Headers({ 'content-type': 'application/json' }),
        text: async () =>
          JSON.stringify({
            message: 'Only message available',
          }),
      })

      try {
        await client.get('/test-endpoint')
        throw new Error('Should have thrown an error')
      } catch (error: any) {
        if (error.message === 'Should have thrown an error') {
          throw error
        }
        expect(error.message).toBe('Only message available')
      }
    })

    it('should fall back to HTTP status when no error message available', async () => {
      global.fetch = jest.fn().mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        headers: new Headers({ 'content-type': 'application/json' }),
        text: async () => JSON.stringify({}),
      })

      try {
        await client.get('/test-endpoint')
        throw new Error('Should have thrown an error')
      } catch (error: any) {
        if (error.message === 'Should have thrown an error') {
          throw error
        }
        expect(error.message).toBe('HTTP error! status: 500')
      }
    })
  })

  describe('Error Response Data Preservation', () => {
    it('should preserve all error response data fields', async () => {
      const errorData = {
        detail: 'Main error message',
        code: 'ERR_DUPLICATE',
        field: 'email',
        metadata: {
          existing_id: 'inv-123',
          timestamp: '2024-01-01T00:00:00Z',
        },
      }

      global.fetch = jest.fn().mockResolvedValueOnce({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        headers: new Headers({ 'content-type': 'application/json' }),
        text: async () => JSON.stringify(errorData),
      })

      try {
        await client.post('/test-endpoint', {})
        throw new Error('Should have thrown an error')
      } catch (error: any) {
        if (error.message === 'Should have thrown an error') {
          throw error
        }
        // All error data should be preserved
        expect(error.response.data).toEqual(errorData)
        expect(error.response.data.code).toBe('ERR_DUPLICATE')
        expect(error.response.data.field).toBe('email')
        expect(error.response.data.metadata).toEqual({
          existing_id: 'inv-123',
          timestamp: '2024-01-01T00:00:00Z',
        })
      }
    })
  })
})
