/**
 * Comprehensive tests for login API route
 * Tests authentication flow, error handling, and cookie management
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

describe('/api/auth/login', () => {
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

  describe('Invalid Credentials', () => {
    it('should return 401 for invalid credentials', async () => {
      const mockError = {
        detail: 'Invalid credentials',
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => mockError,
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest('http://localhost:3000/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({
          email: 'wrong@example.com',
          password: 'wrongpassword',
        }),
      })

      const response = await POST(request)

      expect(response.status).toBe(401)
      const data = await response.json()
      expect(data).toEqual(mockError)
    })

    it('should handle 403 forbidden response', async () => {
      const mockError = {
        detail: 'Account is disabled',
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 403,
        json: async () => mockError,
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest('http://localhost:3000/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({
          email: 'disabled@example.com',
          password: 'password123',
        }),
      })

      const response = await POST(request)

      expect(response.status).toBe(403)
      const data = await response.json()
      expect(data.detail).toBe('Account is disabled')
    })
  })

  describe('Request Validation', () => {
    it('should handle missing email', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 422,
        json: async () => ({
          detail: 'Email is required',
        }),
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest('http://localhost:3000/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({
          password: 'password123',
        }),
      })

      const response = await POST(request)

      expect(response.status).toBe(422)
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/auth/login'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ password: 'password123' }),
        })
      )
    })

    it('should handle missing password', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 422,
        json: async () => ({
          detail: 'Password is required',
        }),
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest('http://localhost:3000/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({
          email: 'test@example.com',
        }),
      })

      const response = await POST(request)

      expect(response.status).toBe(422)
    })

    it('should handle empty request body', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 422,
        json: async () => ({
          detail: 'Request body is required',
        }),
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest('http://localhost:3000/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({}),
      })

      const response = await POST(request)

      expect(response.status).toBe(422)
    })

    it('should handle malformed JSON', async () => {
      const request = createRequest('http://localhost:3000/api/auth/login', {
        method: 'POST',
        body: 'invalid json',
      })

      const response = await POST(request)

      expect(response.status).toBe(500)
      const data = await response.json()
      expect(data.error).toBe('Internal server error')
    })
  })

  describe('Backend API Errors', () => {
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

      const request = createRequest('http://localhost:3000/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({
          email: 'test@example.com',
          password: 'password123',
        }),
      })

      const response = await POST(request)

      expect(response.status).toBe(502)
      const data = await response.json()
      expect(data).toEqual(mockError)
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

      const request = createRequest('http://localhost:3000/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({
          email: 'test@example.com',
          password: 'password123',
        }),
      })

      const response = await POST(request)

      expect(response.status).toBe(503)
    })

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

      const request = createRequest('http://localhost:3000/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({
          email: 'test@example.com',
          password: 'password123',
        }),
      })

      const response = await POST(request)

      expect(response.status).toBe(500)
    })
  })

  describe('Network Errors', () => {
    it('should handle network timeout', async () => {
      ;(global.fetch as jest.Mock).mockRejectedValueOnce(
        new Error('Network timeout')
      )

      const request = createRequest('http://localhost:3000/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({
          email: 'test@example.com',
          password: 'password123',
        }),
      })

      const response = await POST(request)

      expect(response.status).toBe(500)
      const data = await response.json()
      expect(data.error).toBe('Internal server error')
    })

    it('should handle connection refused', async () => {
      ;(global.fetch as jest.Mock).mockRejectedValueOnce(
        new Error('ECONNREFUSED')
      )

      const request = createRequest('http://localhost:3000/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({
          email: 'test@example.com',
          password: 'password123',
        }),
      })

      const response = await POST(request)

      expect(response.status).toBe(500)
      const data = await response.json()
      expect(data.error).toBe('Internal server error')
      expect(console.error).toHaveBeenCalledWith(
        '❌ Login proxy error:',
        expect.any(Error)
      )
    })

    it('should handle DNS resolution failure', async () => {
      ;(global.fetch as jest.Mock).mockRejectedValueOnce(
        new Error('getaddrinfo ENOTFOUND')
      )

      const request = createRequest('http://localhost:3000/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({
          email: 'test@example.com',
          password: 'password123',
        }),
      })

      const response = await POST(request)

      expect(response.status).toBe(500)
    })
  })

  describe('API Base URL Detection', () => {
    it('should use Docker API URL for benger.localhost', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ access_token: 'token', refresh_token: 'refresh' }),
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest('http://benger.localhost/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({
          email: 'test@example.com',
          password: 'password123',
        }),
      })

      await POST(request)

      expect(global.fetch).toHaveBeenCalledWith(
        'http://api:8000/api/auth/login',
        expect.any(Object)
      )
    })

    it('should use localhost:8001 for localhost:3000', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ access_token: 'token', refresh_token: 'refresh' }),
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest('http://localhost:3000/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({
          email: 'test@example.com',
          password: 'password123',
        }),
      })

      await POST(request)

      expect(global.fetch).toHaveBeenCalledWith(
        'http://localhost:8001/api/auth/login',
        expect.any(Object)
      )
    })

    it('should use production API for what-a-benger.net without env var', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ access_token: 'token', refresh_token: 'refresh' }),
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest(
        'https://what-a-benger.net/api/auth/login',
        {
          method: 'POST',
          body: JSON.stringify({
            email: 'test@example.com',
            password: 'password123',
          }),
        }
      )

      await POST(request)

      expect(global.fetch).toHaveBeenCalledWith(
        'http://benger-api:8000/api/auth/login',
        expect.any(Object)
      )
    })

    it('should use default API for staging.what-a-benger.net without env var', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ access_token: 'token', refresh_token: 'refresh' }),
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest(
        'https://staging.what-a-benger.net/api/auth/login',
        {
          method: 'POST',
          body: JSON.stringify({
            email: 'test@example.com',
            password: 'password123',
          }),
        }
      )

      await POST(request)

      // Without DOCKER_INTERNAL_API_URL set, falls back to benger-api:8000
      // In real K8s, DOCKER_INTERNAL_API_URL is always set to the correct service
      expect(global.fetch).toHaveBeenCalledWith(
        'http://benger-api:8000/api/auth/login',
        expect.any(Object)
      )
    })

    it('should use environment variable for staging API when set', async () => {
      const originalApiUrl = process.env.API_URL
      process.env.API_URL = 'http://custom-api:9000'
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ access_token: 'token', refresh_token: 'refresh' }),
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest(
        'https://what-a-benger.net/api/auth/login',
        {
          method: 'POST',
          body: JSON.stringify({
            email: 'test@example.com',
            password: 'password123',
          }),
        }
      )

      await POST(request)

      expect(global.fetch).toHaveBeenCalledWith(
        'http://custom-api:9000/api/auth/login',
        expect.any(Object)
      )

      // Restore original
      if (originalApiUrl) {
        process.env.API_URL = originalApiUrl
      } else {
        delete process.env.API_URL
      }
    })

    it('should default to Docker API URL for unknown hosts', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ access_token: 'token', refresh_token: 'refresh' }),
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest('http://unknown.domain/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({
          email: 'test@example.com',
          password: 'password123',
        }),
      })

      await POST(request)

      expect(global.fetch).toHaveBeenCalledWith(
        'http://api:8000/api/auth/login',
        expect.any(Object)
      )
    })
  })

  describe('Request Forwarding', () => {
    it('should forward request body correctly', async () => {
      const credentials = {
        email: 'user@test.com',
        password: 'securepass123',
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ access_token: 'token', refresh_token: 'refresh' }),
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest('http://localhost:3000/api/auth/login', {
        method: 'POST',
        body: JSON.stringify(credentials),
      })

      await POST(request)

      expect(global.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(credentials),
        })
      )
    })

    it('should set correct Content-Type header', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ access_token: 'token', refresh_token: 'refresh' }),
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest('http://localhost:3000/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({
          email: 'test@example.com',
          password: 'password123',
        }),
      })

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

  describe('Cookie Handling', () => {
    it('should forward Set-Cookie headers on successful login', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          access_token: 'token-abc',
          refresh_token: 'refresh-xyz',
          token_type: 'bearer',
        }),
        headers: {
          getSetCookie: () => [
            'access_token=token-abc; Path=/; HttpOnly; SameSite=Strict; Domain=api:8000',
            'refresh_token=refresh-xyz; Path=/; HttpOnly; Secure',
          ],
        },
      })

      const request = createRequest('http://benger.localhost/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({
          email: 'test@example.com',
          password: 'password123',
        }),
      })

      const response = await POST(request)

      expect(response.status).toBe(200)
      // Response should have Set-Cookie headers appended
      const setCookieHeaders = response.headers.getSetCookie()
      // Should have the two forwarded cookies plus the test cookie
      expect(setCookieHeaders.length).toBeGreaterThanOrEqual(2)
    })

    it('should set SameSite=Lax when not present in cookie', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ access_token: 'tok' }),
        headers: {
          getSetCookie: () => [
            'access_token=tok; Path=/; HttpOnly',
          ],
        },
      })

      const request = createRequest('http://benger.localhost/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email: 'test@ex.com', password: 'pw' }),
      })

      const response = await POST(request)
      const cookies = response.headers.getSetCookie()
      // At least one cookie should have SameSite=Lax
      expect(cookies.some((c: string) => c.includes('SameSite=Lax'))).toBe(true)
    })

    it('should remove Secure flag for development', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ access_token: 'tok' }),
        headers: {
          getSetCookie: () => [
            'access_token=tok; Path=/; HttpOnly; Secure',
          ],
        },
      })

      const request = createRequest('http://benger.localhost/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email: 'test@ex.com', password: 'pw' }),
      })

      const response = await POST(request)
      const cookies = response.headers.getSetCookie()
      // The access_token cookie should NOT have Secure flag
      const accessCookie = cookies.find((c: string) => c.startsWith('access_token='))
      if (accessCookie) {
        expect(accessCookie).not.toMatch(/;\s*Secure/i)
      }
    })

    it('should add Path=/ when not present in cookie', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ access_token: 'tok' }),
        headers: {
          getSetCookie: () => [
            'access_token=tok; HttpOnly',
          ],
        },
      })

      const request = createRequest('http://benger.localhost/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email: 'test@ex.com', password: 'pw' }),
      })

      const response = await POST(request)
      const cookies = response.headers.getSetCookie()
      const accessCookie = cookies.find((c: string) => c.startsWith('access_token='))
      if (accessCookie) {
        expect(accessCookie).toContain('Path=/')
      }
    })

    it('should always add test_cookie on successful login', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ access_token: 'tok' }),
        headers: {
          getSetCookie: () => [],
        },
      })

      const request = createRequest('http://benger.localhost/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email: 'test@ex.com', password: 'pw' }),
      })

      const response = await POST(request)
      const cookies = response.headers.getSetCookie()
      const testCookie = cookies.find((c: string) => c.startsWith('test_cookie='))
      expect(testCookie).toBeDefined()
      expect(testCookie).toContain('working')
    })

    it('should use API_BASE_URL env var when set', async () => {
      const orig = process.env.API_BASE_URL
      process.env.API_BASE_URL = 'http://custom-api:9999'

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ access_token: 'tok' }),
        headers: { getSetCookie: () => [] },
      })

      const request = createRequest('http://benger.localhost/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email: 'test@ex.com', password: 'pw' }),
      })

      await POST(request)

      expect(global.fetch).toHaveBeenCalledWith(
        'http://custom-api:9999/api/auth/login',
        expect.any(Object)
      )

      if (orig) process.env.API_BASE_URL = orig
      else delete process.env.API_BASE_URL
    })

    it('should use test-api for benger-test.localhost', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ access_token: 'tok' }),
        headers: { getSetCookie: () => [] },
      })

      const request = createRequest('http://benger-test.localhost/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email: 'test@ex.com', password: 'pw' }),
      })

      await POST(request)

      expect(global.fetch).toHaveBeenCalledWith(
        'http://test-api:8000/api/auth/login',
        expect.any(Object)
      )
    })
  })

  describe('Error Logging', () => {
    it('should log errors', async () => {
      ;(global.fetch as jest.Mock).mockRejectedValueOnce(
        new Error('Connection failed')
      )

      const request = createRequest('http://localhost:3000/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({
          email: 'test@example.com',
          password: 'password123',
        }),
      })

      await POST(request)

      expect(console.error).toHaveBeenCalledWith(
        '❌ Login proxy error:',
        expect.any(Error)
      )
    })
  })
})
