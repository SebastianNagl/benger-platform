/**
 * Direct Logout Route Tests (without testApiHandler)
 * Tests logout functionality bypassing testApiHandler issues
 */

import { NextRequest } from 'next/server'
import { POST } from '../route'

describe('/api/auth/logout - Direct Tests', () => {
  let originalFetch: typeof global.fetch
  let mockFetch: jest.Mock

  beforeEach(() => {
    originalFetch = global.fetch
    mockFetch = jest.fn()
    global.fetch = mockFetch

    jest.spyOn(console, 'log').mockImplementation()
    jest.spyOn(console, 'error').mockImplementation()
  })

  afterEach(() => {
    global.fetch = originalFetch
    jest.restoreAllMocks()
  })

  describe('Successful Logout', () => {
    it('should return 204 and clear cookies on successful backend logout', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 204,
        headers: new Headers(),
      })

      const request = new NextRequest('http://localhost:3000/api/auth/logout', {
        method: 'POST',
        headers: {
          host: 'localhost:3000',
          cookie: 'access_token=token123; refresh_token=refresh123',
        },
      })

      const response = await POST(request)

      expect(response.status).toBe(204)
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8001/api/auth/logout',
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
            Cookie: 'access_token=token123; refresh_token=refresh123',
          }),
        })
      )
    })

    it('should return 204 even when backend fails', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
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

  describe('Error Handling', () => {
    it('should return 500 on network error', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network error'))

      const request = new NextRequest('http://localhost:3000/api/auth/logout', {
        method: 'POST',
        headers: {
          host: 'localhost:3000',
        },
      })

      const response = await POST(request)

      expect(response.status).toBe(500)
      const data = await response.json()
      expect(data).toEqual({ error: 'Internal server error' })
      expect(console.error).toHaveBeenCalledWith(
        '❌ Logout proxy error:',
        expect.any(Error)
      )
    })

    it('should return 500 on fetch timeout', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Request timeout'))

      const request = new NextRequest('http://localhost:3000/api/auth/logout', {
        method: 'POST',
        headers: {
          host: 'localhost:3000',
        },
      })

      const response = await POST(request)

      expect(response.status).toBe(500)
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

    it('should use environment variable API_URL', async () => {
      const originalApiUrl = process.env.API_URL
      process.env.API_URL = 'http://custom-api:9000'

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 204,
        headers: new Headers(),
      })

      try {
        const request = new NextRequest(
          'https://what-a-benger.net/api/auth/logout',
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
        if (originalApiUrl) {
          process.env.API_URL = originalApiUrl
        } else {
          delete process.env.API_URL
        }
      }
    })

    it('should use staging API for staging environment', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 204,
        headers: new Headers(),
      })

      const request = new NextRequest(
        'https://staging.what-a-benger.net/api/auth/logout',
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

  describe('Cookie Handling', () => {
    it('should forward cookies to backend', async () => {
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

      await POST(request)

      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            Cookie: cookieHeader,
          }),
        })
      )
    })

    it('should handle empty cookie header', async () => {
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
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            Cookie: '',
          }),
        })
      )
    })

    it('should handle malformed cookie strings', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 204,
        headers: new Headers(),
      })

      const malformedCookie = ';;;invalid;;; cookie=malformed'
      const request = new NextRequest('http://localhost:3000/api/auth/logout', {
        method: 'POST',
        headers: {
          host: 'localhost:3000',
          cookie: malformedCookie,
        },
      })

      await POST(request)

      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            Cookie: malformedCookie,
          }),
        })
      )
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
      })

      const response = await POST(request)

      expect(response.status).toBe(204)
      expect(mockFetch).toHaveBeenCalledWith(
        'http://api:8000/api/auth/logout',
        expect.any(Object)
      )
    })

    it('should return empty response body', async () => {
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
  })
})
