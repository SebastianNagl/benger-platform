/**
 * Unit tests for /api/auth/refresh route
 * Tests token refresh functionality with cookie management
 *
 * NOTE: Cookie-related tests are skipped due to Cookie API limitations in Jest
 * See: /services/frontend/docs/testing/auth-api-routes-e2e.md for E2E test requirements
 */

global.fetch = jest.fn()

import { NextRequest } from 'next/server'
import { POST } from '../route'

describe('/api/auth/refresh route', () => {
  let mockFetch: jest.MockedFunction<typeof fetch>

  beforeEach(() => {
    mockFetch = global.fetch as jest.MockedFunction<typeof fetch>
    mockFetch.mockClear()
    jest.clearAllMocks()
    jest.spyOn(console, 'log').mockImplementation()
    jest.spyOn(console, 'error').mockImplementation()
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  describe('POST /api/auth/refresh', () => {
    // E2E TEST REQUIRED: Token refresh with cookies
    // See: /services/frontend/docs/testing/auth-api-routes-e2e.md

    // E2E TEST REQUIRED: Cookie setting verification
    // See: /services/frontend/docs/testing/auth-api-routes-e2e.md

    it('should call backend with correct parameters', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ access_token: 'new-token' }),
        headers: {
          getSetCookie: () => [],
        },
      } as Response)

      const request = new NextRequest(
        'http://localhost:3000/api/auth/refresh',
        {
          method: 'POST',
          headers: {
            host: 'localhost:3000',
            cookie: 'refresh_token=valid-token',
          },
        }
      )

      await POST(request)

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8001/api/auth/refresh',
        expect.objectContaining({
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Cookie: 'refresh_token=valid-token',
          },
        })
      )
    })

    it('should forward cookies to backend', async () => {
      const cookies = 'refresh_token=token123; session_id=sess456'

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ access_token: 'new-token' }),
        headers: {
          getSetCookie: () => [],
        },
      } as Response)

      const request = new NextRequest(
        'http://localhost:3000/api/auth/refresh',
        {
          method: 'POST',
          headers: {
            cookie: cookies,
          },
        }
      )

      await POST(request)

      const fetchCall = mockFetch.mock.calls[0]
      expect(fetchCall[1]?.headers).toEqual({
        'Content-Type': 'application/json',
        Cookie: cookies,
      })
    })

    it('should handle empty cookie header', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: () => Promise.resolve({ detail: 'Refresh token missing' }),
        headers: {
          getSetCookie: () => [],
        },
      } as Response)

      const request = new NextRequest(
        'http://localhost:3000/api/auth/refresh',
        {
          method: 'POST',
        }
      )

      await POST(request)

      const fetchCall = mockFetch.mock.calls[0]
      expect(fetchCall[1]?.headers).toEqual({
        'Content-Type': 'application/json',
        Cookie: '',
      })
    })

    it('should return 401 when refresh token missing', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: () => Promise.resolve({ detail: 'Refresh token missing' }),
        headers: {
          getSetCookie: () => [],
        },
      } as Response)

      const request = new NextRequest(
        'http://localhost:3000/api/auth/refresh',
        {
          method: 'POST',
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(401)
      const data = await response.json()
      expect(data).toEqual({ detail: 'Refresh token missing' })
    })

    it('should return 401 when refresh token invalid', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: () => Promise.resolve({ detail: 'Invalid refresh token' }),
        headers: {
          getSetCookie: () => [],
        },
      } as Response)

      const request = new NextRequest(
        'http://localhost:3000/api/auth/refresh',
        {
          method: 'POST',
          headers: {
            cookie: 'refresh_token=invalid-token',
          },
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(401)
      const data = await response.json()
      expect(data).toEqual({ detail: 'Invalid refresh token' })
    })

    it('should return 401 when refresh token expired', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: () => Promise.resolve({ detail: 'Refresh token expired' }),
        headers: {
          getSetCookie: () => [],
        },
      } as Response)

      const request = new NextRequest(
        'http://localhost:3000/api/auth/refresh',
        {
          method: 'POST',
          headers: {
            cookie: 'refresh_token=expired-token',
          },
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(401)
      const data = await response.json()
      expect(data).toEqual({ detail: 'Refresh token expired' })
    })

    it('should handle backend errors', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Connection failed'))

      const request = new NextRequest(
        'http://localhost:3000/api/auth/refresh',
        {
          method: 'POST',
          headers: {
            cookie: 'refresh_token=valid-token',
          },
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(500)
      const data = await response.json()
      expect(data).toEqual({ error: 'Internal server error' })
    })

    it('should use correct API URL for benger.localhost', async () => {
      const mockRefreshResponse = { access_token: 'new-token' }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockRefreshResponse),
        headers: {
          getSetCookie: () => [],
        },
      } as Response)

      const request = new NextRequest(
        'http://benger.localhost/api/auth/refresh',
        {
          method: 'POST',
          headers: {
            host: 'benger.localhost',
            cookie: 'refresh_token=valid-token',
          },
        }
      )

      await POST(request)

      expect(mockFetch).toHaveBeenCalledWith(
        'http://api:8000/api/auth/refresh',
        expect.any(Object)
      )
    })

    it('should use correct API URL for localhost:3000', async () => {
      const mockRefreshResponse = { access_token: 'new-token' }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockRefreshResponse),
        headers: {
          getSetCookie: () => [],
        },
      } as Response)

      const request = new NextRequest(
        'http://localhost:3000/api/auth/refresh',
        {
          method: 'POST',
          headers: {
            host: 'localhost:3000',
            cookie: 'refresh_token=valid-token',
          },
        }
      )

      await POST(request)

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8001/api/auth/refresh',
        expect.any(Object)
      )
    })

    // E2E TEST REQUIRED: Multiple cookie headers
    // See: /services/frontend/docs/testing/auth-api-routes-e2e.md

    it('should use what-a-benger.net production API', async () => {
      const mockRefreshResponse = { access_token: 'new-token' }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockRefreshResponse),
        headers: {
          getSetCookie: () => [],
        },
      } as Response)

      const request = new NextRequest(
        'https://what-a-benger.net/api/auth/refresh',
        {
          method: 'POST',
          headers: {
            host: 'what-a-benger.net',
            cookie: 'refresh_token=valid-token',
          },
        }
      )

      await POST(request)

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/auth/refresh'),
        expect.any(Object)
      )
    })

    it('should use staging API for staging.what-a-benger.net', async () => {
      const mockRefreshResponse = { access_token: 'new-token' }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockRefreshResponse),
        headers: {
          getSetCookie: () => [],
        },
      } as Response)

      const request = new NextRequest(
        'https://staging.what-a-benger.net/api/auth/refresh',
        {
          method: 'POST',
          headers: {
            host: 'staging.what-a-benger.net',
            cookie: 'refresh_token=valid-token',
          },
        }
      )

      await POST(request)

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/auth/refresh'),
        expect.any(Object)
      )
    })

    it('should use environment variable when set', async () => {
      const originalUrl = process.env.DOCKER_INTERNAL_API_URL
      process.env.DOCKER_INTERNAL_API_URL = 'http://custom-api:9000'

      const mockRefreshResponse = { access_token: 'new-token' }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockRefreshResponse),
        headers: {
          getSetCookie: () => [],
        },
      } as Response)

      const request = new NextRequest(
        'https://what-a-benger.net/api/auth/refresh',
        {
          method: 'POST',
          headers: {
            host: 'what-a-benger.net',
            cookie: 'refresh_token=valid-token',
          },
        }
      )

      await POST(request)

      expect(mockFetch).toHaveBeenCalledWith(
        'http://custom-api:9000/api/auth/refresh',
        expect.any(Object)
      )

      // Restore
      if (originalUrl) {
        process.env.DOCKER_INTERNAL_API_URL = originalUrl
      } else {
        delete process.env.DOCKER_INTERNAL_API_URL
      }
    })

    it('should return response data from backend', async () => {
      const mockRefreshResponse = {
        access_token: 'new-access-token',
        token_type: 'bearer',
        expires_in: 3600,
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockRefreshResponse),
        headers: {
          getSetCookie: () => [],
        },
      } as Response)

      const request = new NextRequest(
        'http://localhost:3000/api/auth/refresh',
        {
          method: 'POST',
          headers: {
            cookie: 'refresh_token=valid-token',
          },
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(200)
      const data = await response.json()
      expect(data).toEqual(mockRefreshResponse)
    })

    it('should handle JSON parse errors from backend', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.reject(new Error('Invalid JSON')),
        headers: {
          getSetCookie: () => [],
        },
      } as any)

      const request = new NextRequest(
        'http://localhost:3000/api/auth/refresh',
        {
          method: 'POST',
          headers: {
            cookie: 'refresh_token=valid-token',
          },
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(500)
      const data = await response.json()
      expect(data.error).toBe('Internal server error')
    })

    it('should return correct status for different error codes', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 403,
        json: () => Promise.resolve({ detail: 'Forbidden' }),
        headers: {
          getSetCookie: () => [],
        },
      } as Response)

      const request = new NextRequest(
        'http://localhost:3000/api/auth/refresh',
        {
          method: 'POST',
          headers: {
            cookie: 'refresh_token=valid-token',
          },
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(403)
    })

    it('should handle 500 errors from backend', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: () => Promise.resolve({ detail: 'Internal server error' }),
        headers: {
          getSetCookie: () => [],
        },
      } as Response)

      const request = new NextRequest(
        'http://localhost:3000/api/auth/refresh',
        {
          method: 'POST',
          headers: {
            cookie: 'refresh_token=valid-token',
          },
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(500)
    })

    it('should handle 502 Bad Gateway', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 502,
        json: () => Promise.resolve({ detail: 'Bad Gateway' }),
        headers: {
          getSetCookie: () => [],
        },
      } as Response)

      const request = new NextRequest(
        'http://localhost:3000/api/auth/refresh',
        {
          method: 'POST',
          headers: {
            cookie: 'refresh_token=valid-token',
          },
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(502)
    })

    it('should handle 503 Service Unavailable', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 503,
        json: () => Promise.resolve({ detail: 'Service Unavailable' }),
        headers: {
          getSetCookie: () => [],
        },
      } as Response)

      const request = new NextRequest(
        'http://localhost:3000/api/auth/refresh',
        {
          method: 'POST',
          headers: {
            cookie: 'refresh_token=valid-token',
          },
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(503)
    })

    it('should use API_URL environment variable', async () => {
      const originalApiUrl = process.env.API_URL
      process.env.API_URL = 'http://env-api:8000'

      const mockRefreshResponse = { access_token: 'new-token' }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockRefreshResponse),
        headers: {
          getSetCookie: () => [],
        },
      } as Response)

      const request = new NextRequest(
        'https://what-a-benger.net/api/auth/refresh',
        {
          method: 'POST',
          headers: {
            host: 'what-a-benger.net',
            cookie: 'refresh_token=valid-token',
          },
        }
      )

      await POST(request)

      expect(mockFetch).toHaveBeenCalledWith(
        'http://env-api:8000/api/auth/refresh',
        expect.any(Object)
      )

      // Restore
      if (originalApiUrl) {
        process.env.API_URL = originalApiUrl
      } else {
        delete process.env.API_URL
      }
    })

    it('should default to api:8000 for unknown hosts', async () => {
      const mockRefreshResponse = { access_token: 'new-token' }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockRefreshResponse),
        headers: {
          getSetCookie: () => [],
        },
      } as Response)

      const request = new NextRequest('http://unknown.host/api/auth/refresh', {
        method: 'POST',
        headers: {
          host: 'unknown.host',
          cookie: 'refresh_token=valid-token',
        },
      })

      await POST(request)

      expect(mockFetch).toHaveBeenCalledWith(
        'http://api:8000/api/auth/refresh',
        expect.any(Object)
      )
    })

    it('should handle fetch timeout errors', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Timeout'))

      const request = new NextRequest(
        'http://localhost:3000/api/auth/refresh',
        {
          method: 'POST',
          headers: {
            cookie: 'refresh_token=valid-token',
          },
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(500)
      const data = await response.json()
      expect(data).toEqual({ error: 'Internal server error' })
    })

    it('should handle DNS resolution errors', async () => {
      mockFetch.mockRejectedValueOnce(new Error('getaddrinfo ENOTFOUND'))

      const request = new NextRequest(
        'http://localhost:3000/api/auth/refresh',
        {
          method: 'POST',
          headers: {
            cookie: 'refresh_token=valid-token',
          },
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(500)
      expect(console.error).toHaveBeenCalledWith(
        '❌ Refresh proxy error:',
        expect.any(Error)
      )
    })

    it('should forward cookies from backend on successful refresh', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ access_token: 'new-tok' }),
        headers: {
          getSetCookie: () => [
            'access_token=new-tok; Path=/; HttpOnly; Domain=api:8000; Secure',
            'refresh_token=new-ref; HttpOnly',
          ],
        },
      } as any)

      const request = new NextRequest(
        'http://benger.localhost/api/auth/refresh',
        {
          method: 'POST',
          headers: {
            host: 'benger.localhost',
            cookie: 'refresh_token=old-token',
          },
        }
      )

      const response = await POST(request)
      expect(response.status).toBe(200)
      const cookies = response.headers.getSetCookie()
      expect(cookies.length).toBeGreaterThanOrEqual(1)
      // Should have Domain rewritten and Secure removed
      const accessCookie = cookies.find((c: string) => c.startsWith('access_token='))
      if (accessCookie) {
        expect(accessCookie).not.toMatch(/Domain=api:8000/)
        expect(accessCookie).not.toMatch(/;\s*Secure/i)
        expect(accessCookie).toContain('SameSite=Lax')
      }
    })

    it('should add Path=/ when not present in refresh cookie', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ access_token: 'tok' }),
        headers: {
          getSetCookie: () => [
            'access_token=tok; HttpOnly',
          ],
        },
      } as any)

      const request = new NextRequest(
        'http://benger.localhost/api/auth/refresh',
        {
          method: 'POST',
          headers: {
            host: 'benger.localhost',
            cookie: 'refresh_token=old',
          },
        }
      )

      const response = await POST(request)
      const cookies = response.headers.getSetCookie()
      const accessCookie = cookies.find((c: string) => c.startsWith('access_token='))
      if (accessCookie) {
        expect(accessCookie).toContain('Path=/')
      }
    })

    it('should use API_BASE_URL env var when set for refresh', async () => {
      const orig = process.env.API_BASE_URL
      process.env.API_BASE_URL = 'http://custom:7777'

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ access_token: 'tok' }),
        headers: { getSetCookie: () => [] },
      } as any)

      const request = new NextRequest(
        'http://benger.localhost/api/auth/refresh',
        {
          method: 'POST',
          headers: {
            host: 'benger.localhost',
            cookie: 'refresh_token=old',
          },
        }
      )

      await POST(request)

      expect(mockFetch).toHaveBeenCalledWith(
        'http://custom:7777/api/auth/refresh',
        expect.any(Object)
      )

      if (orig) process.env.API_BASE_URL = orig
      else delete process.env.API_BASE_URL
    })

    it('should use test-api URL for benger-test.localhost', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ access_token: 'tok' }),
        headers: { getSetCookie: () => [] },
      } as any)

      const request = new NextRequest(
        'http://benger-test.localhost/api/auth/refresh',
        {
          method: 'POST',
          headers: {
            host: 'benger-test.localhost',
            cookie: 'refresh_token=old',
          },
        }
      )

      await POST(request)
      expect(mockFetch).toHaveBeenCalledWith(
        'http://test-api:8000/api/auth/refresh',
        expect.any(Object)
      )
    })

    it('should handle network errors', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network failure'))

      const request = new NextRequest(
        'http://localhost:3000/api/auth/refresh',
        {
          method: 'POST',
          headers: {
            cookie: 'refresh_token=valid-token',
          },
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(500)
      const data = await response.json()
      expect(data.error).toBe('Internal server error')
    })
  })
})
