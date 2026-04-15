/**
 * Comprehensive tests for verify-email-enhanced API route
 * Tests token validation, email verification, and cookie management
 */

import { NextRequest } from 'next/server'
import { POST } from '../route'

// Helper to create NextRequest with proper host header
const createRequest = (url: string, options: RequestInit = {}) => {
  const parsedUrl = new URL(url)
  const headers = new Headers(options.headers)
  headers.set('host', parsedUrl.host)

  return new NextRequest(url, {
    ...options,
    headers,
  })
}

describe('/api/auth/verify-email-enhanced/[token]', () => {
  let originalFetch: typeof global.fetch

  beforeEach(() => {
    originalFetch = global.fetch
    global.fetch = jest.fn()
    jest.clearAllMocks()
    jest.spyOn(console, 'log').mockImplementation()
    jest.spyOn(console, 'error').mockImplementation()
  })

  afterEach(() => {
    global.fetch = originalFetch
    jest.restoreAllMocks()
  })

  describe('Successful Verification', () => {
    it('should verify email successfully with valid token', async () => {
      const mockResponse = {
        message: 'Email verified successfully',
        user: {
          id: 1,
          email: 'test@example.com',
          is_verified: true,
        },
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockResponse,
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email-enhanced/valid-token-123',
        {
          method: 'POST',
        }
      )

      const response = await POST(request, {
        params: Promise.resolve({ token: 'valid-token-123' }),
      })

      expect(response.status).toBe(200)
      const data = await response.json()
      expect(data).toEqual(mockResponse)
      expect(data.user.is_verified).toBe(true)
    })

    // E2E TEST REQUIRED: Cookie verification
    // See: /services/frontend/docs/testing/auth-api-routes-e2e.md
  })

  describe('Invalid Token', () => {
    it('should return 400 for invalid token format', async () => {
      const mockError = {
        detail: 'Invalid token format',
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => mockError,
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email-enhanced/invalid-token',
        {
          method: 'POST',
        }
      )

      const response = await POST(request, {
        params: Promise.resolve({ token: 'invalid-token' }),
      })

      expect(response.status).toBe(400)
      const data = await response.json()
      expect(data).toEqual(mockError)
    })

    it('should return 401 for expired token', async () => {
      const mockError = {
        detail: 'Token has expired',
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => mockError,
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email-enhanced/expired-token',
        {
          method: 'POST',
        }
      )

      const response = await POST(request, {
        params: Promise.resolve({ token: 'expired-token' }),
      })

      expect(response.status).toBe(401)
      const data = await response.json()
      expect(data.detail).toBe('Token has expired')
    })

    it('should return 404 for non-existent token', async () => {
      const mockError = {
        detail: 'Token not found',
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: async () => mockError,
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email-enhanced/nonexistent',
        {
          method: 'POST',
        }
      )

      const response = await POST(request, {
        params: Promise.resolve({ token: 'nonexistent' }),
      })

      expect(response.status).toBe(404)
      const data = await response.json()
      expect(data.detail).toBe('Token not found')
    })

    it('should return 409 for already verified email', async () => {
      const mockError = {
        detail: 'Email already verified',
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 409,
        json: async () => mockError,
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email-enhanced/already-used',
        {
          method: 'POST',
        }
      )

      const response = await POST(request, {
        params: Promise.resolve({ token: 'already-used' }),
      })

      expect(response.status).toBe(409)
      const data = await response.json()
      expect(data.detail).toBe('Email already verified')
    })
  })

  describe('API Base URL Detection', () => {
    it('should use localhost:8001 for localhost:3000', async () => {
      const mockResponse = { message: 'Email verified' }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockResponse,
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email-enhanced/token123',
        {
          method: 'POST',
        }
      )

      await POST(request, {
        params: Promise.resolve({ token: 'token123' }),
      })

      expect(global.fetch).toHaveBeenCalledWith(
        'http://localhost:8001/api/auth/verify-email-enhanced/token123',
        expect.any(Object)
      )
    })

    it('should use localhost:8001 for localhost:3001', async () => {
      const mockResponse = { message: 'Email verified' }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockResponse,
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest(
        'http://localhost:3001/api/auth/verify-email-enhanced/token123',
        {
          method: 'POST',
        }
      )

      await POST(request, {
        params: Promise.resolve({ token: 'token123' }),
      })

      expect(global.fetch).toHaveBeenCalledWith(
        'http://localhost:8001/api/auth/verify-email-enhanced/token123',
        expect.any(Object)
      )
    })

    it('should use Docker API URL for benger.localhost', async () => {
      const mockResponse = { message: 'Email verified' }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockResponse,
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest(
        'http://benger.localhost/api/auth/verify-email-enhanced/token123',
        {
          method: 'POST',
        }
      )

      await POST(request, {
        params: Promise.resolve({ token: 'token123' }),
      })

      expect(global.fetch).toHaveBeenCalledWith(
        'http://api:8000/api/auth/verify-email-enhanced/token123',
        expect.any(Object)
      )
    })

    it('should use staging API for staging.what-a-benger.net', async () => {
      const mockResponse = { message: 'Email verified' }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockResponse,
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest(
        'https://staging.what-a-benger.net/api/auth/verify-email-enhanced/token123',
        {
          method: 'POST',
        }
      )

      await POST(request, {
        params: Promise.resolve({ token: 'token123' }),
      })

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('api/auth/verify-email-enhanced/token123'),
        expect.any(Object)
      )
    })

    it('should use production API for what-a-benger.net', async () => {
      const mockResponse = { message: 'Email verified' }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockResponse,
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest(
        'https://what-a-benger.net/api/auth/verify-email-enhanced/token123',
        {
          method: 'POST',
        }
      )

      await POST(request, {
        params: Promise.resolve({ token: 'token123' }),
      })

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('api/auth/verify-email-enhanced/token123'),
        expect.any(Object)
      )
    })

    it('should use environment variable API_BASE_URL when set', async () => {
      const originalApiUrl = process.env.API_BASE_URL
      process.env.API_BASE_URL = 'http://custom-api:9000'

      const mockResponse = { message: 'Email verified' }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockResponse,
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest(
        'https://staging.what-a-benger.net/api/auth/verify-email-enhanced/token123',
        {
          method: 'POST',
        }
      )

      await POST(request, {
        params: Promise.resolve({ token: 'token123' }),
      })

      expect(global.fetch).toHaveBeenCalledWith(
        'http://custom-api:9000/api/auth/verify-email-enhanced/token123',
        expect.any(Object)
      )

      // Restore original
      if (originalApiUrl) {
        process.env.API_BASE_URL = originalApiUrl
      } else {
        delete process.env.API_BASE_URL
      }
    })

    it('should default to api:8000 for unknown hosts', async () => {
      const mockResponse = { message: 'Email verified' }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockResponse,
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest(
        'http://unknown.domain/api/auth/verify-email-enhanced/token123',
        {
          method: 'POST',
        }
      )

      await POST(request, {
        params: Promise.resolve({ token: 'token123' }),
      })

      expect(global.fetch).toHaveBeenCalledWith(
        'http://api:8000/api/auth/verify-email-enhanced/token123',
        expect.any(Object)
      )
    })
  })

  describe('Cookie Management', () => {
    it('should handle responses without cookies', async () => {
      const mockResponse = { message: 'Email verified' }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockResponse,
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email-enhanced/token123',
        {
          method: 'POST',
        }
      )

      const response = await POST(request, {
        params: Promise.resolve({ token: 'token123' }),
      })

      expect(response.status).toBe(200)
    })

    // E2E TEST REQUIRED: Cookie modification verification
    // See: /services/frontend/docs/testing/auth-api-routes-e2e.md

    // E2E TEST REQUIRED: SameSite attribute
    // See: /services/frontend/docs/testing/auth-api-routes-e2e.md

    // E2E TEST REQUIRED: Multiple cookies
    // See: /services/frontend/docs/testing/auth-api-routes-e2e.md
  })

  describe('Backend API Errors', () => {
    it('should handle 500 Internal Server Error from backend', async () => {
      const mockError = {
        detail: 'Internal server error',
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => mockError,
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email-enhanced/token123',
        {
          method: 'POST',
        }
      )

      const response = await POST(request, {
        params: Promise.resolve({ token: 'token123' }),
      })

      expect(response.status).toBe(500)
      const data = await response.json()
      expect(data).toEqual(mockError)
    })

    it('should handle 502 Bad Gateway', async () => {
      const mockError = {
        detail: 'Bad Gateway',
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 502,
        json: async () => mockError,
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email-enhanced/token123',
        {
          method: 'POST',
        }
      )

      const response = await POST(request, {
        params: Promise.resolve({ token: 'token123' }),
      })

      expect(response.status).toBe(502)
    })

    it('should handle 503 Service Unavailable', async () => {
      const mockError = {
        detail: 'Service temporarily unavailable',
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 503,
        json: async () => mockError,
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email-enhanced/token123',
        {
          method: 'POST',
        }
      )

      const response = await POST(request, {
        params: Promise.resolve({ token: 'token123' }),
      })

      expect(response.status).toBe(503)
    })
  })

  describe('Network Errors', () => {
    it('should handle network timeout', async () => {
      ;(global.fetch as jest.Mock).mockRejectedValueOnce(
        new Error('Network timeout')
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email-enhanced/token123',
        {
          method: 'POST',
        }
      )

      const response = await POST(request, {
        params: Promise.resolve({ token: 'token123' }),
      })

      expect(response.status).toBe(500)
      const data = await response.json()
      expect(data.error).toBe('Internal server error')
    })

    it('should handle connection refused', async () => {
      ;(global.fetch as jest.Mock).mockRejectedValueOnce(
        new Error('ECONNREFUSED')
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email-enhanced/token123',
        {
          method: 'POST',
        }
      )

      const response = await POST(request, {
        params: Promise.resolve({ token: 'token123' }),
      })

      expect(response.status).toBe(500)
      const data = await response.json()
      expect(data.error).toBe('Internal server error')
      expect(console.error).toHaveBeenCalledWith(
        '❌ Verify email enhanced error:',
        expect.any(Error)
      )
    })

    it('should handle DNS resolution failure', async () => {
      ;(global.fetch as jest.Mock).mockRejectedValueOnce(
        new Error('getaddrinfo ENOTFOUND')
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email-enhanced/token123',
        {
          method: 'POST',
        }
      )

      const response = await POST(request, {
        params: Promise.resolve({ token: 'token123' }),
      })

      expect(response.status).toBe(500)
    })

    it('should handle fetch rejection with non-Error object', async () => {
      ;(global.fetch as jest.Mock).mockRejectedValueOnce('String error')

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email-enhanced/token123',
        {
          method: 'POST',
        }
      )

      const response = await POST(request, {
        params: Promise.resolve({ token: 'token123' }),
      })

      expect(response.status).toBe(500)
      const data = await response.json()
      expect(data.error).toBe('Internal server error')
    })
  })

  describe('Request Headers', () => {
    it('should set correct Content-Type header', async () => {
      const mockResponse = { message: 'Email verified' }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockResponse,
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email-enhanced/token123',
        {
          method: 'POST',
        }
      )

      await POST(request, {
        params: Promise.resolve({ token: 'token123' }),
      })

      expect(global.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
        })
      )
    })
  })

  describe('Token Parameter Handling', () => {
    it('should handle token with special characters', async () => {
      const token = 'token-with-special_chars.123'
      const mockResponse = { message: 'Email verified' }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockResponse,
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest(
        `http://localhost:3000/api/auth/verify-email-enhanced/${token}`,
        {
          method: 'POST',
        }
      )

      await POST(request, {
        params: Promise.resolve({ token }),
      })

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining(token),
        expect.any(Object)
      )
    })

    it('should handle very long token', async () => {
      const longToken = 'a'.repeat(500)
      const mockResponse = { message: 'Email verified' }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockResponse,
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest(
        `http://localhost:3000/api/auth/verify-email-enhanced/${longToken}`,
        {
          method: 'POST',
        }
      )

      await POST(request, {
        params: Promise.resolve({ token: longToken }),
      })

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining(longToken),
        expect.any(Object)
      )
    })

    it('should handle token with URL encoding', async () => {
      const token = 'token%20with%20spaces'
      const mockResponse = { message: 'Email verified' }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockResponse,
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest(
        `http://localhost:3000/api/auth/verify-email-enhanced/${token}`,
        {
          method: 'POST',
        }
      )

      await POST(request, {
        params: Promise.resolve({ token }),
      })

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining(token),
        expect.any(Object)
      )
    })
  })

  describe('Response Data Handling', () => {
    it('should return user data in response', async () => {
      const mockResponse = {
        message: 'Email verified successfully',
        user: {
          id: 42,
          email: 'verified@example.com',
          is_verified: true,
          created_at: '2025-01-01T00:00:00Z',
        },
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockResponse,
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email-enhanced/token123',
        {
          method: 'POST',
        }
      )

      const response = await POST(request, {
        params: Promise.resolve({ token: 'token123' }),
      })

      const data = await response.json()
      expect(data.user).toBeDefined()
      expect(data.user.id).toBe(42)
      expect(data.user.email).toBe('verified@example.com')
      expect(data.user.is_verified).toBe(true)
    })

    it('should handle empty response body', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({}),
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email-enhanced/token123',
        {
          method: 'POST',
        }
      )

      const response = await POST(request, {
        params: Promise.resolve({ token: 'token123' }),
      })

      expect(response.status).toBe(200)
      const data = await response.json()
      expect(data).toEqual({})
    })

    it('should handle response with additional metadata', async () => {
      const mockResponse = {
        message: 'Email verified',
        user: { id: 1, email: 'test@example.com' },
        metadata: {
          verified_at: '2025-01-01T00:00:00Z',
          ip_address: '127.0.0.1',
        },
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockResponse,
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email-enhanced/token123',
        {
          method: 'POST',
        }
      )

      const response = await POST(request, {
        params: Promise.resolve({ token: 'token123' }),
      })

      const data = await response.json()
      expect(data.metadata).toBeDefined()
      expect(data.metadata.verified_at).toBe('2025-01-01T00:00:00Z')
    })
  })
})
