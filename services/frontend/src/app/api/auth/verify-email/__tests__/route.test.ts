/**
 * Comprehensive tests for verify-email API route
 * Tests email verification flow, cookie handling, and error scenarios
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

// Helper to create mock backend response with proper getSetCookie
const createMockResponse = (
  data: any,
  status: number,
  cookies: string[] = []
) => {
  const headers = new Headers()
  headers.set('content-type', 'application/json')

  // Add getSetCookie method to headers
  ;(headers as any).getSetCookie = () => cookies

  // Track if json was called to return data copy each time
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => JSON.parse(JSON.stringify(data)),
    headers,
  }
}

describe('/api/auth/verify-email', () => {
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

  describe('Successful Email Verification', () => {
    it('should forward verify-email request to backend', async () => {
      const mockResponse = {
        message: 'Email verified successfully',
        user: {
          id: 1,
          email: 'test@example.com',
          is_verified: true,
        },
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse(mockResponse, 200, [
          'access_token=test_token_123; HttpOnly; Path=/; SameSite=Lax',
        ])
      )

      const verificationData = {
        token: 'verification_token_abc123',
      }

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(verificationData),
        }
      )

      await POST(request)

      expect(global.fetch).toHaveBeenCalledWith(
        'http://localhost:8001/api/auth/verify-email',
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
          body: JSON.stringify(verificationData),
        })
      )
    })

    it('should return 200 with verified user data', async () => {
      const mockResponse = {
        message: 'Email verified successfully',
        user: {
          id: 1,
          email: 'user@test.com',
          is_verified: true,
        },
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse(mockResponse, 200, [])
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email',
        {
          method: 'POST',
          body: JSON.stringify({ token: 'valid_token' }),
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(200)
      const data = await response.json()
      expect(data).toEqual(mockResponse)
      expect(data.user.is_verified).toBe(true)
    })
  })

  describe('Invalid Verification Token', () => {
    it('should return 400 for invalid token', async () => {
      const mockError = {
        detail: 'Invalid verification token',
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse(mockError, 400, [])
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email',
        {
          method: 'POST',
          body: JSON.stringify({ token: 'invalid_token' }),
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(400)
      const data = await response.json()
      expect(data.detail).toBe('Invalid verification token')
    })

    it('should return 400 for expired token', async () => {
      const mockError = {
        detail: 'Verification token has expired',
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse(mockError, 400, [])
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email',
        {
          method: 'POST',
          body: JSON.stringify({ token: 'expired_token' }),
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(400)
      const data = await response.json()
      expect(data.detail).toBe('Verification token has expired')
    })

    it('should return 404 for user not found', async () => {
      const mockError = {
        detail: 'User not found',
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse(mockError, 404, [])
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email',
        {
          method: 'POST',
          body: JSON.stringify({ token: 'valid_token' }),
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(404)
    })
  })

  describe('Request Validation', () => {
    it('should handle missing token', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse({ detail: 'Token is required' }, 422, [])
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email',
        {
          method: 'POST',
          body: JSON.stringify({}),
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(422)
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/auth/verify-email'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({}),
        })
      )
    })

    it('should handle empty token', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse({ detail: 'Token cannot be empty' }, 422, [])
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email',
        {
          method: 'POST',
          body: JSON.stringify({ token: '' }),
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(422)
    })

    it('should handle malformed JSON', async () => {
      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email',
        {
          method: 'POST',
          body: 'invalid json',
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(500)
      const data = await response.json()
      expect(data.error).toBe('Internal server error')
    })
  })

  describe('Backend API Errors', () => {
    it('should handle 500 Internal Server Error from backend', async () => {
      const mockError = {
        detail: 'Internal server error',
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse(mockError, 500, [])
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email',
        {
          method: 'POST',
          body: JSON.stringify({ token: 'valid_token' }),
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(500)
    })

    it('should handle 502 Bad Gateway', async () => {
      const mockError = {
        detail: 'Bad Gateway',
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse(mockError, 502, [])
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email',
        {
          method: 'POST',
          body: JSON.stringify({ token: 'valid_token' }),
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(502)
    })

    it('should handle 503 Service Unavailable', async () => {
      const mockError = {
        detail: 'Service temporarily unavailable',
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse(mockError, 503, [])
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email',
        {
          method: 'POST',
          body: JSON.stringify({ token: 'valid_token' }),
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(503)
    })
  })

  describe('Network Errors', () => {
    it('should handle network timeout', async () => {
      ;(global.fetch as jest.Mock).mockRejectedValueOnce(
        new Error('Network timeout')
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email',
        {
          method: 'POST',
          body: JSON.stringify({ token: 'valid_token' }),
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(500)
      const data = await response.json()
      expect(data.error).toBe('Internal server error')
    })

    it('should handle connection refused', async () => {
      ;(global.fetch as jest.Mock).mockRejectedValueOnce(
        new Error('ECONNREFUSED')
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email',
        {
          method: 'POST',
          body: JSON.stringify({ token: 'valid_token' }),
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(500)
      const data = await response.json()
      expect(data.error).toBe('Internal server error')
      expect(console.error).toHaveBeenCalledWith(
        '❌ Verify email error:',
        expect.any(Error)
      )
    })

    it('should handle DNS resolution failure', async () => {
      ;(global.fetch as jest.Mock).mockRejectedValueOnce(
        new Error('getaddrinfo ENOTFOUND')
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email',
        {
          method: 'POST',
          body: JSON.stringify({ token: 'valid_token' }),
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(500)
    })
  })

  describe('API Base URL Detection', () => {
    it('should use localhost:8001 for localhost:3000', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse({ message: 'Success' }, 200, [])
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email',
        {
          method: 'POST',
          body: JSON.stringify({ token: 'valid_token' }),
        }
      )

      await POST(request)

      expect(global.fetch).toHaveBeenCalledWith(
        'http://localhost:8001/api/auth/verify-email',
        expect.any(Object)
      )
    })

    it('should use localhost:8001 for localhost:3001', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse({ message: 'Success' }, 200, [])
      )

      const request = createRequest(
        'http://localhost:3001/api/auth/verify-email',
        {
          method: 'POST',
          body: JSON.stringify({ token: 'valid_token' }),
        }
      )

      await POST(request)

      expect(global.fetch).toHaveBeenCalledWith(
        'http://localhost:8001/api/auth/verify-email',
        expect.any(Object)
      )
    })

    it('should use Docker API URL for benger.localhost', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse({ message: 'Success' }, 200, [])
      )

      const request = createRequest(
        'http://benger.localhost/api/auth/verify-email',
        {
          method: 'POST',
          body: JSON.stringify({ token: 'valid_token' }),
        }
      )

      await POST(request)

      expect(global.fetch).toHaveBeenCalledWith(
        'http://api:8000/api/auth/verify-email',
        expect.any(Object)
      )
    })

    it('should use staging API for staging.what-a-benger.net', async () => {
      const originalEnv = process.env.API_BASE_URL
      delete process.env.API_BASE_URL
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse({ message: 'Success' }, 200, [])
      )

      const request = createRequest(
        'https://staging.what-a-benger.net/api/auth/verify-email',
        {
          method: 'POST',
          body: JSON.stringify({ token: 'valid_token' }),
        }
      )

      await POST(request)

      expect(global.fetch).toHaveBeenCalledWith(
        'http://benger-api:8000/api/auth/verify-email',
        expect.any(Object)
      )

      if (originalEnv) {
        process.env.API_BASE_URL = originalEnv
      }
    })

    it('should use production API for what-a-benger.net', async () => {
      const originalEnv = process.env.API_BASE_URL
      delete process.env.API_BASE_URL
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse({ message: 'Success' }, 200, [])
      )

      const request = createRequest(
        'https://what-a-benger.net/api/auth/verify-email',
        {
          method: 'POST',
          body: JSON.stringify({ token: 'valid_token' }),
        }
      )

      await POST(request)

      expect(global.fetch).toHaveBeenCalledWith(
        'http://benger-api:8000/api/auth/verify-email',
        expect.any(Object)
      )

      if (originalEnv) {
        process.env.API_BASE_URL = originalEnv
      }
    })

    it('should use environment variable when API_BASE_URL is set', async () => {
      const originalEnv = process.env.API_BASE_URL
      process.env.API_BASE_URL = 'http://custom-api:9000'
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse({ message: 'Success' }, 200, [])
      )

      const request = createRequest(
        'https://staging.what-a-benger.net/api/auth/verify-email',
        {
          method: 'POST',
          body: JSON.stringify({ token: 'valid_token' }),
        }
      )

      await POST(request)

      expect(global.fetch).toHaveBeenCalledWith(
        'http://custom-api:9000/api/auth/verify-email',
        expect.any(Object)
      )

      if (originalEnv) {
        process.env.API_BASE_URL = originalEnv
      } else {
        delete process.env.API_BASE_URL
      }
    })

    it('should default to api:8000 for unknown hosts', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse({ message: 'Success' }, 200, [])
      )

      const request = createRequest(
        'http://unknown.domain/api/auth/verify-email',
        {
          method: 'POST',
          body: JSON.stringify({ token: 'valid_token' }),
        }
      )

      await POST(request)

      expect(global.fetch).toHaveBeenCalledWith(
        'http://api:8000/api/auth/verify-email',
        expect.any(Object)
      )
    })
  })

  describe('Request Forwarding', () => {
    it('should forward request body correctly', async () => {
      const verificationData = {
        token: 'verification_token_xyz789',
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse({ message: 'Success' }, 200, [])
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email',
        {
          method: 'POST',
          body: JSON.stringify(verificationData),
        }
      )

      await POST(request)

      expect(global.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(verificationData),
        })
      )
    })

    it('should set correct Content-Type header', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse({ message: 'Success' }, 200, [])
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email',
        {
          method: 'POST',
          body: JSON.stringify({ token: 'valid_token' }),
        }
      )

      await POST(request)

      expect(global.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: {
            'Content-Type': 'application/json',
          },
        })
      )
    })
  })

  describe('Error Logging', () => {
    it('should log errors', async () => {
      ;(global.fetch as jest.Mock).mockRejectedValueOnce(
        new Error('Connection failed')
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/verify-email',
        {
          method: 'POST',
          body: JSON.stringify({ token: 'valid_token' }),
        }
      )

      await POST(request)

      expect(console.error).toHaveBeenCalledWith(
        '❌ Verify email error:',
        expect.any(Error)
      )
    })
  })
})

/**
 * Cookie Management Tests - Integration Test Requirements
 * ========================================================
 *
 * Cookie manipulation and Set-Cookie header handling require real HTTP responses
 * and cannot be accurately tested in unit tests due to Next.js Headers API limitations.
 *
 * The following functionality requires E2E/integration tests:
 *
 * 1. Cookie Forwarding:
 *    - Forward Set-Cookie headers from backend to frontend
 *    - Verify cookies are properly set in browser after email verification
 *
 * 2. Cookie Modification:
 *    - Remove Domain restrictions for cross-domain compatibility
 *    - Ensure SameSite is set appropriately (Lax)
 *    - Verify modified cookies are set correctly
 *
 * These tests should be implemented using Puppeteer as specified in the project guidelines.
 */
