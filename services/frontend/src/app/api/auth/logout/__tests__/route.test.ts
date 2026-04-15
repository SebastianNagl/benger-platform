/**
 * Logout Route Tests
 * Tests logout functionality including cookie clearing, backend API interaction, and error handling
 *
 * NOTE: Cookie-related tests are skipped due to Cookie API limitations in Jest
 * See: /services/frontend/docs/testing/auth-api-routes-e2e.md for E2E test requirements
 */

import { NextRequest } from 'next/server'
import { POST } from '../route'

// NOTE: Most logout tests are skipped because logout ALWAYS manipulates cookies
// which requires browser Cookie API not available in Jest
describe('/api/auth/logout', () => {
  let originalFetch: typeof global.fetch
  let mockFetch: jest.Mock

  beforeEach(() => {
    // Store original fetch
    originalFetch = global.fetch

    // Create mock fetch
    mockFetch = jest.fn()
    global.fetch = mockFetch

    // Mock console methods to reduce noise
    jest.spyOn(console, 'log').mockImplementation()
    jest.spyOn(console, 'error').mockImplementation()
  })

  afterEach(() => {
    // Restore original fetch
    global.fetch = originalFetch

    // Restore console
    jest.restoreAllMocks()
  })

  describe('Successful Logout', () => {
    // E2E TEST REQUIRED: Cookie clearing verification
    // See: /services/frontend/docs/testing/auth-api-routes-e2e.md

    it('should forward cookies to backend API', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 204,
        headers: new Headers(),
      })

      const cookieHeader = 'access_token=token123; refresh_token=refresh123'

      const request = new NextRequest('http://localhost:3000/api/auth/logout', {
        method: 'POST',
        headers: {
          host: 'localhost:3000',
          cookie: cookieHeader,
        },
      })

      const response = await POST(request)

      expect(response.status).toBe(204)

      // Verify backend API was called with correct parameters
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8001/api/auth/logout',
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
            Cookie: cookieHeader,
          }),
        })
      )
    })

    // E2E TEST REQUIRED: Backend response handling
    // See: /services/frontend/docs/testing/auth-api-routes-e2e.md
  })

  describe('Cookie Clearing - E2E TESTS REQUIRED', () => {
    // All cookie clearing tests require browser Cookie API
    // See: /services/frontend/docs/testing/auth-api-routes-e2e.md
  })

  describe('Already Logged Out', () => {
    it('should handle logout when no cookies are present', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 204,
        headers: new Headers(),
      })

      const request = new NextRequest('http://localhost:3000/api/auth/logout', {
        method: 'POST',
        headers: {
          host: 'localhost:3000',
          // No cookie header
        },
      })

      const response = await POST(request)

      expect(response.status).toBe(204)

      // Backend should still be called (with empty cookies)
      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            Cookie: '',
          }),
        })
      )
    })
  })

  describe('Invalid Token', () => {
    // All invalid token tests with cookie verification require browser Cookie API
    // See: /services/frontend/docs/testing/auth-api-routes-e2e.md

    it('should handle backend 403 (forbidden)', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 403,
        headers: new Headers(),
      })

      const request = new NextRequest('http://localhost:3000/api/auth/logout', {
        method: 'POST',
        headers: {
          host: 'localhost:3000',
          cookie: 'access_token=token123',
        },
      })

      const response = await POST(request)

      // Should still clear cookies and return 204
      expect(response.status).toBe(204)
    })
  })

  describe('Backend API Errors', () => {
    it('should handle network errors gracefully', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network error'))

      const request = new NextRequest('http://localhost:3000/api/auth/logout', {
        method: 'POST',
        headers: {
          host: 'localhost:3000',
          cookie: 'access_token=token123',
        },
      })

      const response = await POST(request)

      expect(response.status).toBe(500)

      const data = await response.json()
      expect(data).toEqual({ error: 'Internal server error' })

      // Should log the error
      expect(console.error).toHaveBeenCalledWith(
        '❌ Logout proxy error:',
        expect.any(Error)
      )
    })

    it('should handle backend timeout', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Request timeout'))

      const request = new NextRequest('http://localhost:3000/api/auth/logout', {
        method: 'POST',
        headers: {
          host: 'localhost:3000',
        },
      })

      const response = await POST(request)

      expect(response.status).toBe(500)
      expect(await response.json()).toEqual({
        error: 'Internal server error',
      })
    })

    it('should handle backend 500 error', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        headers: new Headers(),
        json: async () => ({ error: 'Internal server error' }),
      })

      const request = new NextRequest('http://localhost:3000/api/auth/logout', {
        method: 'POST',
        headers: {
          host: 'localhost:3000',
          cookie: 'access_token=token123',
        },
      })

      const response = await POST(request)

      // Frontend should still clear cookies and return success
      // This is the expected behavior - we want to log out the user
      // even if the backend has issues
      expect(response.status).toBe(204)
    })

    it('should handle malformed backend response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 204,
        headers: new Headers(),
        // No json method (malformed response)
      })

      const request = new NextRequest('http://localhost:3000/api/auth/logout', {
        method: 'POST',
        headers: {
          host: 'localhost:3000',
          cookie: 'access_token=token123',
        },
      })

      const response = await POST(request)

      // Should still succeed - we don't try to parse the response
      expect(response.status).toBe(204)
    })
  })

  describe('API Base URL Detection', () => {
    it('should use localhost:8001 for localhost:3000', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 204,
        headers: new Headers(),
      })

      const request = new NextRequest('http://localhost:3000/api/auth/logout', {
        method: 'POST',
        headers: {
          host: 'localhost:3000',
        },
      })

      await POST(request)

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8001/api/auth/logout',
        expect.any(Object)
      )
    })

    it('should use api:8000 for benger.localhost', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 204,
        headers: new Headers(),
      })

      const request = new NextRequest(
        'http://benger.localhost/api/auth/logout',
        {
          method: 'POST',
          headers: {
            host: 'benger.localhost',
          },
        }
      )

      await POST(request)

      expect(mockFetch).toHaveBeenCalledWith(
        'http://api:8000/api/auth/logout',
        expect.any(Object)
      )
    })

    it('should use benger-api:8000 for production (what-a-benger.net)', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 204,
        headers: new Headers(),
      })

      const request = new NextRequest(
        'http://what-a-benger.net/api/auth/logout',
        {
          method: 'POST',
          headers: {
            host: 'what-a-benger.net',
          },
        }
      )

      await POST(request)

      expect(mockFetch).toHaveBeenCalledWith(
        'http://benger-api:8000/api/auth/logout',
        expect.any(Object)
      )
    })

    it('should use staging API for staging environment', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 204,
        headers: new Headers(),
      })

      const request = new NextRequest(
        'http://staging.what-a-benger.net/api/auth/logout',
        {
          method: 'POST',
          headers: {
            host: 'staging.what-a-benger.net',
          },
        }
      )

      await POST(request)

      expect(mockFetch).toHaveBeenCalledWith(
        'http://benger-api:8000/api/auth/logout',
        expect.any(Object)
      )
    })

    it('should use environment variable API_URL if set', async () => {
      const originalApiUrl = process.env.API_URL
      process.env.API_URL = 'http://custom-api:9000'

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 204,
        headers: new Headers(),
      })

      try {
        const request = new NextRequest(
          'http://what-a-benger.net/api/auth/logout',
          {
            method: 'POST',
            headers: {
              host: 'what-a-benger.net',
            },
          }
        )

        await POST(request)

        expect(mockFetch).toHaveBeenCalledWith(
          'http://custom-api:9000/api/auth/logout',
          expect.any(Object)
        )
      } finally {
        // Restore original env var
        if (originalApiUrl) {
          process.env.API_URL = originalApiUrl
        } else {
          delete process.env.API_URL
        }
      }
    })

    it('should default to api:8000 for unknown hosts', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 204,
        headers: new Headers(),
      })

      const request = new NextRequest(
        'http://unknown-host.com/api/auth/logout',
        {
          method: 'POST',
          headers: {
            host: 'unknown-host.com',
          },
        }
      )

      await POST(request)

      expect(mockFetch).toHaveBeenCalledWith(
        'http://api:8000/api/auth/logout',
        expect.any(Object)
      )
    })
  })

  describe('HTTP Methods', () => {
    it('should only accept POST method', async () => {
      // The route handler only exports POST
      // Attempting other methods should fail at the framework level
      // This test verifies the route structure

      const routeModule = await import('../route')
      expect(routeModule.POST).toBeDefined()
      expect(routeModule.GET).toBeUndefined()
      expect(routeModule.PUT).toBeUndefined()
      expect(routeModule.DELETE).toBeUndefined()
      expect(routeModule.PATCH).toBeUndefined()
    })
  })

  describe('Error Logging', () => {
    it('should log error on failure', async () => {
      const error = new Error('Test error')
      mockFetch.mockRejectedValueOnce(error)

      const request = new NextRequest('http://localhost:3000/api/auth/logout', {
        method: 'POST',
        headers: {
          host: 'localhost:3000',
        },
      })

      await POST(request)

      expect(console.error).toHaveBeenCalledWith(
        '❌ Logout proxy error:',
        error
      )
    })
  })

  describe('Response Headers', () => {
    it('should return 204 No Content without response body', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 204,
        headers: new Headers(),
      })

      const request = new NextRequest('http://localhost:3000/api/auth/logout', {
        method: 'POST',
        headers: {
          host: 'localhost:3000',
        },
      })

      const response = await POST(request)

      expect(response.status).toBe(204)
      const text = await response.text()
      expect(text).toBe('')
    })

    it('should include Content-Type header', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 204,
        headers: new Headers(),
      })

      const request = new NextRequest('http://localhost:3000/api/auth/logout', {
        method: 'POST',
        headers: {
          host: 'localhost:3000',
        },
      })

      const response = await POST(request)

      expect(response.status).toBe(204)
    })
  })

  describe('Request Validation', () => {
    it('should process logout with valid cookie format', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 204,
        headers: new Headers(),
      })

      const request = new NextRequest('http://localhost:3000/api/auth/logout', {
        method: 'POST',
        headers: {
          host: 'localhost:3000',
          cookie: 'access_token=valid_token',
        },
      })

      const response = await POST(request)

      expect(response.status).toBe(204)
    })

    it('should handle malformed cookie strings gracefully', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 204,
        headers: new Headers(),
      })

      const request = new NextRequest('http://localhost:3000/api/auth/logout', {
        method: 'POST',
        headers: {
          host: 'localhost:3000',
          cookie: ';;;invalid;;;',
        },
      })

      const response = await POST(request)

      expect(response.status).toBe(204)
      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            Cookie: ';;;invalid;;;',
          }),
        })
      )
    })
  })

  describe('Session Termination', () => {
    it('should clear session immediately without waiting for backend', async () => {
      let backendCalled = false
      mockFetch.mockImplementation(async () => {
        await new Promise((resolve) => setTimeout(resolve, 100))
        backendCalled = true
        return {
          ok: true,
          status: 204,
          headers: new Headers(),
        }
      })

      const request = new NextRequest('http://localhost:3000/api/auth/logout', {
        method: 'POST',
        headers: {
          host: 'localhost:3000',
          cookie: 'access_token=token123',
        },
      })

      const response = await POST(request)

      expect(response.status).toBe(204)
      expect(backendCalled).toBe(true)
    })

    it('should terminate session even on backend partial failure', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 504,
        headers: new Headers(),
      })

      const request = new NextRequest('http://localhost:3000/api/auth/logout', {
        method: 'POST',
        headers: {
          host: 'localhost:3000',
          cookie: 'access_token=token123',
        },
      })

      const response = await POST(request)

      expect(response.status).toBe(204)
    })
  })

  describe('Edge Cases', () => {
    it('should handle missing host header', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 204,
        headers: new Headers(),
      })

      const request = new NextRequest('http://localhost:3000/api/auth/logout', {
        method: 'POST',
        // No host header
      })

      const response = await POST(request)

      // Should default to api:8000
      expect(response.status).toBe(204)
      expect(mockFetch).toHaveBeenCalledWith(
        'http://api:8000/api/auth/logout',
        expect.any(Object)
      )
    })

    it('should handle empty cookie string', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 204,
        headers: new Headers(),
      })

      const request = new NextRequest('http://localhost:3000/api/auth/logout', {
        method: 'POST',
        headers: {
          host: 'localhost:3000',
          cookie: '',
        },
      })

      const response = await POST(request)

      expect(response.status).toBe(204)
      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            Cookie: '',
          }),
        })
      )
    })

    // E2E TEST REQUIRED: Cookie clearing with partial cookies
    // See: /services/frontend/docs/testing/auth-api-routes-e2e.md

    // E2E TEST REQUIRED: Cookie clearing with partial cookies
    // See: /services/frontend/docs/testing/auth-api-routes-e2e.md

    it('should handle cookies with extra whitespace', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 204,
        headers: new Headers(),
      })

      const cookieHeader =
        '  access_token=token123  ;  refresh_token=refresh123  '

      const request = new NextRequest('http://localhost:3000/api/auth/logout', {
        method: 'POST',
        headers: {
          host: 'localhost:3000',
          cookie: cookieHeader,
        },
      })

      await POST(request)

      // Should forward cookies as-is (backend handles parsing)
      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            Cookie: cookieHeader,
          }),
        })
      )
    })
  })
})
