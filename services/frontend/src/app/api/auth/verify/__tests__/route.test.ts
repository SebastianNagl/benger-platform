/**
 * Comprehensive tests for verify API route
 * Tests authentication verification, cookie forwarding, and error scenarios
 */

import { NextRequest } from 'next/server'
import { GET } from '../route'

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

// Helper to create mock backend response
const createMockResponse = (data: any, status: number, isText = false) => {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
    text: async () => (isText ? data : JSON.stringify(data)),
  }
}

describe('/api/auth/verify', () => {
  let originalFetch: typeof global.fetch

  beforeEach(() => {
    originalFetch = global.fetch
    global.fetch = jest.fn()
    jest.clearAllMocks()
    jest.spyOn(console, 'error').mockImplementation()
  })

  afterEach(() => {
    global.fetch = originalFetch
    jest.restoreAllMocks()
  })

  describe('Successful Verification', () => {
    it('should forward verify request to backend with cookies', async () => {
      const mockResponse = {
        user: {
          id: 1,
          email: 'test@example.com',
          is_verified: true,
        },
        authenticated: true,
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse(mockResponse, 200)
      )

      const request = createRequest('http://localhost:3000/api/auth/verify', {
        method: 'GET',
        headers: {
          cookie: 'access_token=test_token_123; refresh_token=refresh_456',
        },
      })

      await GET(request)

      expect(global.fetch).toHaveBeenCalledWith(
        'http://localhost:8001/api/auth/verify',
        expect.objectContaining({
          method: 'GET',
          headers: expect.objectContaining({
            Cookie: 'access_token=test_token_123; refresh_token=refresh_456',
          }),
        })
      )
    })

    it('should return 200 with authenticated user data', async () => {
      const mockResponse = {
        user: {
          id: 1,
          email: 'user@test.com',
          is_verified: true,
        },
        authenticated: true,
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse(mockResponse, 200)
      )

      const request = createRequest('http://localhost:3000/api/auth/verify', {
        method: 'GET',
        headers: {
          cookie: 'access_token=valid_token',
        },
      })

      const response = await GET(request)

      expect(response.status).toBe(200)
      const data = await response.json()
      expect(data).toEqual(mockResponse)
      expect(data.authenticated).toBe(true)
    })

    it('should forward authorization header when present', async () => {
      const mockResponse = {
        user: { id: 1, email: 'test@example.com' },
        authenticated: true,
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse(mockResponse, 200)
      )

      const request = createRequest('http://localhost:3000/api/auth/verify', {
        method: 'GET',
        headers: {
          authorization: 'Bearer test_token_123',
        },
      })

      await GET(request)

      expect(global.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            Authorization: 'Bearer test_token_123',
          }),
        })
      )
    })

    it('should handle empty cookies gracefully', async () => {
      const mockResponse = {
        user: { id: 1, email: 'test@example.com' },
        authenticated: true,
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse(mockResponse, 200)
      )

      const request = createRequest('http://localhost:3000/api/auth/verify', {
        method: 'GET',
      })

      await GET(request)

      expect(global.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            Cookie: '',
            Authorization: '',
          }),
        })
      )
    })
  })

  describe('Verification Failures', () => {
    it('should return 401 for unauthenticated request', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse('Unauthorized', 401, true)
      )

      const request = createRequest('http://localhost:3000/api/auth/verify', {
        method: 'GET',
      })

      const response = await GET(request)

      expect(response.status).toBe(401)
      const data = await response.json()
      expect(data.error).toBe('Unauthorized')
    })

    it('should return 401 for invalid token', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse('Invalid token', 401, true)
      )

      const request = createRequest('http://localhost:3000/api/auth/verify', {
        method: 'GET',
        headers: {
          cookie: 'access_token=invalid_token',
        },
      })

      const response = await GET(request)

      expect(response.status).toBe(401)
      const data = await response.json()
      expect(data.error).toBe('Invalid token')
    })

    it('should return 401 for expired token', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse('Token expired', 401, true)
      )

      const request = createRequest('http://localhost:3000/api/auth/verify', {
        method: 'GET',
        headers: {
          cookie: 'access_token=expired_token',
        },
      })

      const response = await GET(request)

      expect(response.status).toBe(401)
      const data = await response.json()
      expect(data.error).toBe('Token expired')
    })

    it('should return 403 for forbidden access', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse('Forbidden', 403, true)
      )

      const request = createRequest('http://localhost:3000/api/auth/verify', {
        method: 'GET',
        headers: {
          cookie: 'access_token=valid_token',
        },
      })

      const response = await GET(request)

      expect(response.status).toBe(403)
    })

    it('should handle empty error response', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse('', 401, true)
      )

      const request = createRequest('http://localhost:3000/api/auth/verify', {
        method: 'GET',
      })

      const response = await GET(request)

      expect(response.status).toBe(401)
      const data = await response.json()
      expect(data.error).toBe('Verification failed')
    })
  })

  describe('Backend API Errors', () => {
    it('should handle 500 Internal Server Error', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse('Internal server error', 500, true)
      )

      const request = createRequest('http://localhost:3000/api/auth/verify', {
        method: 'GET',
        headers: {
          cookie: 'access_token=valid_token',
        },
      })

      const response = await GET(request)

      expect(response.status).toBe(500)
    })

    it('should handle 502 Bad Gateway', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse('Bad Gateway', 502, true)
      )

      const request = createRequest('http://localhost:3000/api/auth/verify', {
        method: 'GET',
        headers: {
          cookie: 'access_token=valid_token',
        },
      })

      const response = await GET(request)

      expect(response.status).toBe(502)
    })

    it('should handle 503 Service Unavailable', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse('Service Unavailable', 503, true)
      )

      const request = createRequest('http://localhost:3000/api/auth/verify', {
        method: 'GET',
        headers: {
          cookie: 'access_token=valid_token',
        },
      })

      const response = await GET(request)

      expect(response.status).toBe(503)
    })
  })

  describe('Network Errors', () => {
    it('should handle network timeout', async () => {
      ;(global.fetch as jest.Mock).mockRejectedValueOnce(
        new Error('Network timeout')
      )

      const request = createRequest('http://localhost:3000/api/auth/verify', {
        method: 'GET',
        headers: {
          cookie: 'access_token=valid_token',
        },
      })

      const response = await GET(request)

      expect(response.status).toBe(500)
      const data = await response.json()
      expect(data.error).toBe('Internal server error')
    })

    it('should handle connection refused', async () => {
      ;(global.fetch as jest.Mock).mockRejectedValueOnce(
        new Error('ECONNREFUSED')
      )

      const request = createRequest('http://localhost:3000/api/auth/verify', {
        method: 'GET',
        headers: {
          cookie: 'access_token=valid_token',
        },
      })

      const response = await GET(request)

      expect(response.status).toBe(500)
      const data = await response.json()
      expect(data.error).toBe('Internal server error')
      expect(console.error).toHaveBeenCalledWith(
        '❌ Auth verify proxy error:',
        expect.any(Error)
      )
    })

    it('should handle DNS resolution failure', async () => {
      ;(global.fetch as jest.Mock).mockRejectedValueOnce(
        new Error('getaddrinfo ENOTFOUND')
      )

      const request = createRequest('http://localhost:3000/api/auth/verify', {
        method: 'GET',
        headers: {
          cookie: 'access_token=valid_token',
        },
      })

      const response = await GET(request)

      expect(response.status).toBe(500)
    })
  })

  describe('API Base URL Detection', () => {
    it('should use Docker API URL for benger.localhost', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse({ authenticated: true }, 200)
      )

      const request = createRequest('http://benger.localhost/api/auth/verify', {
        method: 'GET',
        headers: {
          cookie: 'access_token=valid_token',
        },
      })

      await GET(request)

      expect(global.fetch).toHaveBeenCalledWith(
        'http://api:8000/api/auth/verify',
        expect.any(Object)
      )
    })

    it('should use localhost:8001 for localhost:3000', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse({ authenticated: true }, 200)
      )

      const request = createRequest('http://localhost:3000/api/auth/verify', {
        method: 'GET',
        headers: {
          cookie: 'access_token=valid_token',
        },
      })

      await GET(request)

      expect(global.fetch).toHaveBeenCalledWith(
        'http://localhost:8001/api/auth/verify',
        expect.any(Object)
      )
    })

    it('should use environment variable for production deployment', async () => {
      const originalDockerUrl = process.env.DOCKER_INTERNAL_API_URL
      const originalApiUrl = process.env.API_URL
      process.env.DOCKER_INTERNAL_API_URL = 'http://custom-api:7000'
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse({ authenticated: true }, 200)
      )

      const request = createRequest(
        'https://what-a-benger.net/api/auth/verify',
        {
          method: 'GET',
          headers: {
            cookie: 'access_token=valid_token',
          },
        }
      )

      await GET(request)

      expect(global.fetch).toHaveBeenCalledWith(
        'http://custom-api:7000/api/auth/verify',
        expect.any(Object)
      )

      if (originalDockerUrl) {
        process.env.DOCKER_INTERNAL_API_URL = originalDockerUrl
      } else {
        delete process.env.DOCKER_INTERNAL_API_URL
      }
      if (originalApiUrl) {
        process.env.API_URL = originalApiUrl
      }
    })

    it('should use fallback API URL for production when no env vars set', async () => {
      const originalDockerUrl = process.env.DOCKER_INTERNAL_API_URL
      const originalApiUrl = process.env.API_URL
      delete process.env.DOCKER_INTERNAL_API_URL
      delete process.env.API_URL
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse({ authenticated: true }, 200)
      )

      const request = createRequest(
        'https://what-a-benger.net/api/auth/verify',
        {
          method: 'GET',
          headers: {
            cookie: 'access_token=valid_token',
          },
        }
      )

      await GET(request)

      expect(global.fetch).toHaveBeenCalledWith(
        'http://benger-api:8000/api/auth/verify',
        expect.any(Object)
      )

      if (originalDockerUrl) {
        process.env.DOCKER_INTERNAL_API_URL = originalDockerUrl
      }
      if (originalApiUrl) {
        process.env.API_URL = originalApiUrl
      }
    })

    it('should default to Docker API URL for unknown hosts', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse({ authenticated: true }, 200)
      )

      const request = createRequest('http://unknown.domain/api/auth/verify', {
        method: 'GET',
        headers: {
          cookie: 'access_token=valid_token',
        },
      })

      await GET(request)

      expect(global.fetch).toHaveBeenCalledWith(
        'http://api:8000/api/auth/verify',
        expect.any(Object)
      )
    })
  })

  describe('Request Forwarding', () => {
    it('should forward both cookies and authorization header', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse({ authenticated: true }, 200)
      )

      const request = createRequest('http://localhost:3000/api/auth/verify', {
        method: 'GET',
        headers: {
          cookie: 'access_token=cookie_token',
          authorization: 'Bearer header_token',
        },
      })

      await GET(request)

      expect(global.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          method: 'GET',
          headers: {
            Cookie: 'access_token=cookie_token',
            Authorization: 'Bearer header_token',
          },
        })
      )
    })

    it('should handle only authorization header without cookies', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse({ authenticated: true }, 200)
      )

      const request = createRequest('http://localhost:3000/api/auth/verify', {
        method: 'GET',
        headers: {
          authorization: 'Bearer only_header_token',
        },
      })

      await GET(request)

      expect(global.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            Cookie: '',
            Authorization: 'Bearer only_header_token',
          }),
        })
      )
    })

    it('should handle only cookies without authorization header', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse({ authenticated: true }, 200)
      )

      const request = createRequest('http://localhost:3000/api/auth/verify', {
        method: 'GET',
        headers: {
          cookie: 'access_token=only_cookie_token',
        },
      })

      await GET(request)

      expect(global.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            Cookie: 'access_token=only_cookie_token',
            Authorization: '',
          }),
        })
      )
    })
  })

  describe('Error Logging', () => {
    it('should log errors from network failures', async () => {
      ;(global.fetch as jest.Mock).mockRejectedValueOnce(
        new Error('Connection failed')
      )

      const request = createRequest('http://localhost:3000/api/auth/verify', {
        method: 'GET',
        headers: {
          cookie: 'access_token=valid_token',
        },
      })

      await GET(request)

      expect(console.error).toHaveBeenCalledWith(
        '❌ Auth verify proxy error:',
        expect.any(Error)
      )
    })

    it('should log errors from backend failures', async () => {
      ;(global.fetch as jest.Mock).mockRejectedValueOnce(
        new Error('Backend unreachable')
      )

      const request = createRequest('http://localhost:3000/api/auth/verify', {
        method: 'GET',
        headers: {
          cookie: 'access_token=valid_token',
        },
      })

      await GET(request)

      expect(console.error).toHaveBeenCalledWith(
        '❌ Auth verify proxy error:',
        expect.objectContaining({
          message: 'Backend unreachable',
        })
      )
    })
  })
})

/**
 * Integration Test Requirements
 * ==============================
 *
 * The following scenarios require E2E/integration testing with Puppeteer:
 *
 * 1. Cookie Authentication Flow:
 *    - Login and obtain authentication cookies
 *    - Verify cookies are sent with subsequent requests
 *    - Verify endpoint returns authenticated user data
 *
 * 2. Session Management:
 *    - Verify token refresh handling
 *    - Test session expiration
 *    - Test logout and cookie clearing
 *
 * 3. Cross-Domain Testing:
 *    - Test benger.localhost environment
 *    - Verify production domain behavior
 *
 * These tests should be implemented using Puppeteer as specified in the project guidelines.
 */
