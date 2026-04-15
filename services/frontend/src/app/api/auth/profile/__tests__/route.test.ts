/**
 * Unit tests for /api/auth/profile route
 * Tests authentication proxy for user profile endpoint (GET and PUT)
 */

global.fetch = jest.fn()

import { NextRequest } from 'next/server'
import { GET, PUT } from '../route'

describe('/api/auth/profile route', () => {
  let mockFetch: jest.MockedFunction<typeof fetch>

  beforeEach(() => {
    mockFetch = global.fetch as jest.MockedFunction<typeof fetch>
    mockFetch.mockClear()
  })

  describe('GET /api/auth/profile', () => {
    it('should fetch user profile successfully', async () => {
      const mockProfile = {
        id: 1,
        username: 'testuser',
        email: 'test@example.com',
        bio: 'Test bio',
        full_name: 'Test User',
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockProfile),
      } as Response)

      const request = new NextRequest(
        'http://localhost:3000/api/auth/profile',
        {
          headers: {
            cookie: 'access_token=valid-token',
          },
        }
      )

      const response = await GET(request)

      expect(response.status).toBe(200)
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/auth/profile'),
        expect.objectContaining({
          method: 'GET',
          headers: {
            Cookie: 'access_token=valid-token',
            Authorization: '',
          },
        })
      )

      const data = await response.json()
      expect(data).toEqual(mockProfile)
    })

    it('should forward authorization header', async () => {
      const mockProfile = { id: 1, username: 'testuser' }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockProfile),
      } as Response)

      const request = new NextRequest(
        'http://localhost:3000/api/auth/profile',
        {
          headers: {
            authorization: 'Bearer token123',
          },
        }
      )

      await GET(request)

      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            Authorization: 'Bearer token123',
          }),
        })
      )
    })

    it('should return 401 when unauthorized', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        text: () => Promise.resolve('Unauthorized'),
      } as Response)

      const request = new NextRequest('http://localhost:3000/api/auth/profile')

      const response = await GET(request)

      expect(response.status).toBe(401)
      const data = await response.json()
      expect(data).toEqual({ error: 'Unauthorized' })
    })

    it('should handle backend errors', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Connection failed'))

      const request = new NextRequest(
        'http://localhost:3000/api/auth/profile',
        {
          headers: {
            cookie: 'access_token=valid-token',
          },
        }
      )

      const response = await GET(request)

      expect(response.status).toBe(500)
      const data = await response.json()
      expect(data).toEqual({ error: 'Internal server error' })
    })

    it('should use correct API URL for benger.localhost', async () => {
      const mockProfile = { id: 1, username: 'testuser' }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockProfile),
      } as Response)

      const request = new NextRequest(
        'http://benger.localhost/api/auth/profile',
        {
          headers: {
            host: 'benger.localhost',
            cookie: 'access_token=valid-token',
          },
        }
      )

      await GET(request)

      expect(mockFetch).toHaveBeenCalledWith(
        'http://api:8000/api/auth/profile',
        expect.any(Object)
      )
    })
  })

  describe('PUT /api/auth/profile', () => {
    it('should update profile successfully', async () => {
      const updateData = {
        full_name: 'Updated Name',
        bio: 'Updated bio',
      }

      const mockUpdatedProfile = {
        id: 1,
        username: 'testuser',
        email: 'test@example.com',
        ...updateData,
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockUpdatedProfile),
      } as Response)

      const request = new NextRequest(
        'http://localhost:3000/api/auth/profile',
        {
          method: 'PUT',
          headers: {
            'content-type': 'application/json',
            cookie: 'access_token=valid-token',
          },
          body: JSON.stringify(updateData),
        }
      )

      const response = await PUT(request)

      expect(response.status).toBe(200)
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/auth/profile'),
        expect.objectContaining({
          method: 'PUT',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
            Cookie: 'access_token=valid-token',
          }),
          body: JSON.stringify(updateData),
        })
      )

      const data = await response.json()
      expect(data).toEqual(mockUpdatedProfile)
    })

    it('should handle validation errors', async () => {
      const updateData = {
        email: 'invalid-email',
      }

      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 422,
        text: () => Promise.resolve('Validation error: Invalid email format'),
      } as Response)

      const request = new NextRequest(
        'http://localhost:3000/api/auth/profile',
        {
          method: 'PUT',
          headers: {
            'content-type': 'application/json',
            cookie: 'access_token=valid-token',
          },
          body: JSON.stringify(updateData),
        }
      )

      const response = await PUT(request)

      expect(response.status).toBe(422)
      const data = await response.json()
      expect(data).toEqual({ error: 'Validation error: Invalid email format' })
    })

    it('should return 401 when unauthorized', async () => {
      const updateData = { full_name: 'New Name' }

      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        text: () => Promise.resolve('Unauthorized'),
      } as Response)

      const request = new NextRequest(
        'http://localhost:3000/api/auth/profile',
        {
          method: 'PUT',
          headers: {
            'content-type': 'application/json',
          },
          body: JSON.stringify(updateData),
        }
      )

      const response = await PUT(request)

      expect(response.status).toBe(401)
      const data = await response.json()
      expect(data).toEqual({ error: 'Unauthorized' })
    })

    it('should forward authorization header on PUT', async () => {
      const updateData = { full_name: 'New Name' }
      const mockUpdatedProfile = {
        id: 1,
        username: 'testuser',
        full_name: 'New Name',
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockUpdatedProfile),
      } as Response)

      const request = new NextRequest(
        'http://localhost:3000/api/auth/profile',
        {
          method: 'PUT',
          headers: {
            'content-type': 'application/json',
            authorization: 'Bearer token123',
          },
          body: JSON.stringify(updateData),
        }
      )

      await PUT(request)

      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            Authorization: 'Bearer token123',
          }),
        })
      )
    })

    it('should handle backend errors on PUT', async () => {
      const updateData = { full_name: 'New Name' }

      mockFetch.mockRejectedValueOnce(new Error('Connection failed'))

      const request = new NextRequest(
        'http://localhost:3000/api/auth/profile',
        {
          method: 'PUT',
          headers: {
            'content-type': 'application/json',
            cookie: 'access_token=valid-token',
          },
          body: JSON.stringify(updateData),
        }
      )

      const response = await PUT(request)

      expect(response.status).toBe(500)
      const data = await response.json()
      expect(data).toEqual({ error: 'Internal server error' })
    })

    it('should handle empty request body', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        text: () => Promise.resolve('Request body is required'),
      } as Response)

      const request = new NextRequest(
        'http://localhost:3000/api/auth/profile',
        {
          method: 'PUT',
          headers: {
            'content-type': 'application/json',
            cookie: 'access_token=valid-token',
          },
          body: JSON.stringify({}),
        }
      )

      const response = await PUT(request)

      expect(response.status).toBe(400)
      const data = await response.json()
      expect(data).toEqual({ error: 'Request body is required' })
    })
  })
})
