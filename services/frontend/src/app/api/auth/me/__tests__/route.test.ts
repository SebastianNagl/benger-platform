/**
 * Unit tests for /api/auth/me route
 * Tests authentication proxy for current user endpoint
 */

global.fetch = jest.fn()

import { NextRequest } from 'next/server'
import { GET } from '../route'

describe('/api/auth/me route', () => {
  let mockFetch: jest.MockedFunction<typeof fetch>

  beforeEach(() => {
    mockFetch = global.fetch as jest.MockedFunction<typeof fetch>
    mockFetch.mockClear()
  })

  describe('GET /api/auth/me', () => {
    it('should get current user with valid token', async () => {
      const mockUser = {
        id: 1,
        username: 'testuser',
        email: 'test@example.com',
        role: 'user',
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockUser),
      } as Response)

      const request = new NextRequest('http://localhost:3000/api/auth/me', {
        headers: {
          cookie: 'access_token=valid-token',
        },
      })

      const response = await GET(request)

      expect(response.status).toBe(200)
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/auth/me'),
        expect.objectContaining({
          method: 'GET',
          headers: {
            Cookie: 'access_token=valid-token',
          },
        })
      )

      const data = await response.json()
      expect(data).toEqual(mockUser)
    })

    it('should return 401 when no token provided', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: () => Promise.resolve({ detail: 'Unauthorized' }),
      } as Response)

      const request = new NextRequest('http://localhost:3000/api/auth/me')

      const response = await GET(request)

      expect(response.status).toBe(401)
      const data = await response.json()
      expect(data).toEqual({ error: 'Unauthorized' })
    })

    it('should return 401 when token is invalid', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: () => Promise.resolve({ detail: 'Invalid token' }),
      } as Response)

      const request = new NextRequest('http://localhost:3000/api/auth/me', {
        headers: {
          cookie: 'access_token=invalid-token',
        },
      })

      const response = await GET(request)

      expect(response.status).toBe(401)
      const data = await response.json()
      expect(data).toEqual({ error: 'Unauthorized' })
    })

    it('should return 403 when token is expired', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 403,
        json: () => Promise.resolve({ detail: 'Token expired' }),
      } as Response)

      const request = new NextRequest('http://localhost:3000/api/auth/me', {
        headers: {
          cookie: 'access_token=expired-token',
        },
      })

      const response = await GET(request)

      expect(response.status).toBe(403)
      const data = await response.json()
      expect(data).toEqual({ error: 'Unauthorized' })
    })

    it('should handle backend errors', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Backend connection failed'))

      const request = new NextRequest('http://localhost:3000/api/auth/me', {
        headers: {
          cookie: 'access_token=valid-token',
        },
      })

      const response = await GET(request)

      expect(response.status).toBe(500)
      const data = await response.json()
      expect(data).toEqual({ error: 'Internal server error' })
    })

    it('should forward cookies correctly', async () => {
      const mockUser = {
        id: 1,
        username: 'testuser',
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockUser),
      } as Response)

      const request = new NextRequest('http://localhost:3000/api/auth/me', {
        headers: {
          cookie: 'access_token=token123; refresh_token=refresh123',
        },
      })

      await GET(request)

      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: {
            Cookie: 'access_token=token123; refresh_token=refresh123',
          },
        })
      )
    })

    it('should use correct API URL for benger.localhost', async () => {
      const mockUser = { id: 1, username: 'testuser' }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockUser),
      } as Response)

      const request = new NextRequest('http://benger.localhost/api/auth/me', {
        headers: {
          host: 'benger.localhost',
          cookie: 'access_token=valid-token',
        },
      })

      await GET(request)

      expect(mockFetch).toHaveBeenCalledWith(
        'http://api:8000/api/auth/me',
        expect.any(Object)
      )
    })

    it('should use correct API URL for localhost:3000', async () => {
      const mockUser = { id: 1, username: 'testuser' }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockUser),
      } as Response)

      const request = new NextRequest('http://localhost:3000/api/auth/me', {
        headers: {
          host: 'localhost:3000',
          cookie: 'access_token=valid-token',
        },
      })

      await GET(request)

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8001/api/auth/me',
        expect.any(Object)
      )
    })
  })
})
