/**
 * Comprehensive tests for signup API route
 * Tests signup functionality including validation, error handling, and cookie management
 *
 * NOTE: Cookie-related tests are skipped due to Cookie API limitations in Jest
 * See: /services/frontend/docs/testing/auth-api-routes-e2e.md for E2E test requirements
 */

import '@testing-library/jest-dom'
import { NextRequest } from 'next/server'
import { POST } from '../route'

describe('/api/auth/signup', () => {
  let originalFetch: typeof global.fetch

  beforeEach(() => {
    // Store original fetch
    originalFetch = global.fetch

    // Mock fetch
    global.fetch = jest.fn()

    // Clear console.log and console.error to reduce test output noise
    jest.spyOn(console, 'log').mockImplementation(() => {})
    jest.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    // Restore original fetch
    global.fetch = originalFetch

    // Restore console methods
    jest.restoreAllMocks()
  })

  describe('Successful signup', () => {
    it('should signup successfully with valid data and return 201', async () => {
      const mockUser = {
        id: 1,
        email: 'newuser@example.com',
        username: 'newuser',
        access_token: 'mock_token_123',
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 201,
        headers: {
          getSetCookie: () => [],
        },
        json: async () => mockUser,
      })

      const request = new NextRequest('http://localhost:3000/api/auth/signup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          host: 'localhost:3000',
        },
        body: JSON.stringify({
          email: 'newuser@example.com',
          password: 'SecurePass123!',
          username: 'newuser',
        }),
      })

      const response = await POST(request)

      expect(response.status).toBe(201)
      const data = await response.json()
      expect(data).toEqual(mockUser)
      expect(global.fetch).toHaveBeenCalledWith(
        'http://localhost:8001/api/auth/signup',
        expect.objectContaining({
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            email: 'newuser@example.com',
            password: 'SecurePass123!',
            username: 'newuser',
          }),
        })
      )
    })

    // E2E TEST REQUIRED: Cookie forwarding from backend
    // See: /services/frontend/docs/testing/auth-api-routes-e2e.md

    it('should use correct API base URL for benger.localhost', async () => {
      const mockUser = {
        id: 1,
        email: 'newuser@example.com',
        access_token: 'mock_token_123',
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 201,
        headers: {
          getSetCookie: () => [],
        },
        json: async () => mockUser,
      })

      const request = new NextRequest(
        'http://benger.localhost/api/auth/signup',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            host: 'benger.localhost',
          },
          body: JSON.stringify({
            email: 'newuser@example.com',
            password: 'SecurePass123!',
            username: 'newuser',
          }),
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(201)
      expect(global.fetch).toHaveBeenCalledWith(
        'http://api:8000/api/auth/signup',
        expect.any(Object)
      )
    })
  })

  describe('Email validation errors', () => {
    it('should return 409 when email already exists', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 409,
        headers: {
          getSetCookie: () => [],
        },
        json: async () => ({
          detail: 'Email already registered',
        }),
      })

      const request = new NextRequest('http://localhost:3000/api/auth/signup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          host: 'localhost:3000',
        },
        body: JSON.stringify({
          email: 'existing@example.com',
          password: 'SecurePass123!',
          username: 'existinguser',
        }),
      })

      const response = await POST(request)

      expect(response.status).toBe(409)
      const data = await response.json()
      expect(data.detail).toBe('Email already registered')
    })

    it('should return 400 for invalid email format', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 400,
        headers: {
          getSetCookie: () => [],
        },
        json: async () => ({
          detail: 'Invalid email format',
        }),
      })

      const request = new NextRequest('http://localhost:3000/api/auth/signup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          host: 'localhost:3000',
        },
        body: JSON.stringify({
          email: 'invalid-email',
          password: 'SecurePass123!',
          username: 'newuser',
        }),
      })

      const response = await POST(request)

      expect(response.status).toBe(400)
      const data = await response.json()
      expect(data.detail).toBe('Invalid email format')
    })
  })

  describe('Password validation errors', () => {
    it('should return 400 for weak password', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 400,
        headers: {
          getSetCookie: () => [],
        },
        json: async () => ({
          detail: 'Password must be at least 8 characters long',
        }),
      })

      const request = new NextRequest('http://localhost:3000/api/auth/signup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          host: 'localhost:3000',
        },
        body: JSON.stringify({
          email: 'newuser@example.com',
          password: 'weak',
          username: 'newuser',
        }),
      })

      const response = await POST(request)

      expect(response.status).toBe(400)
      const data = await response.json()
      expect(data.detail).toBe('Password must be at least 8 characters long')
    })

    it('should return 400 for password without special characters', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 400,
        headers: {
          getSetCookie: () => [],
        },
        json: async () => ({
          detail: 'Password must contain special characters',
        }),
      })

      const request = new NextRequest('http://localhost:3000/api/auth/signup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          host: 'localhost:3000',
        },
        body: JSON.stringify({
          email: 'newuser@example.com',
          password: 'SimplePassword123',
          username: 'newuser',
        }),
      })

      const response = await POST(request)

      expect(response.status).toBe(400)
      const data = await response.json()
      expect(data.detail).toBe('Password must contain special characters')
    })
  })

  describe('Missing field validation', () => {
    it('should return 400 when email is missing', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 400,
        headers: {
          getSetCookie: () => [],
        },
        json: async () => ({
          detail: 'Email is required',
        }),
      })

      const request = new NextRequest('http://localhost:3000/api/auth/signup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          host: 'localhost:3000',
        },
        body: JSON.stringify({
          password: 'SecurePass123!',
          username: 'newuser',
        }),
      })

      const response = await POST(request)

      expect(response.status).toBe(400)
      const data = await response.json()
      expect(data.detail).toBe('Email is required')
    })

    it('should return 400 when password is missing', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 400,
        headers: {
          getSetCookie: () => [],
        },
        json: async () => ({
          detail: 'Password is required',
        }),
      })

      const request = new NextRequest('http://localhost:3000/api/auth/signup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          host: 'localhost:3000',
        },
        body: JSON.stringify({
          email: 'newuser@example.com',
          username: 'newuser',
        }),
      })

      const response = await POST(request)

      expect(response.status).toBe(400)
      const data = await response.json()
      expect(data.detail).toBe('Password is required')
    })

    it('should return 400 when username is missing', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 400,
        headers: {
          getSetCookie: () => [],
        },
        json: async () => ({
          detail: 'Username is required',
        }),
      })

      const request = new NextRequest('http://localhost:3000/api/auth/signup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          host: 'localhost:3000',
        },
        body: JSON.stringify({
          email: 'newuser@example.com',
          password: 'SecurePass123!',
        }),
      })

      const response = await POST(request)

      expect(response.status).toBe(400)
      const data = await response.json()
      expect(data.detail).toBe('Username is required')
    })
  })

  describe('Backend error handling', () => {
    it('should return 502 for bad gateway errors', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 502,
        headers: {
          getSetCookie: () => [],
        },
        json: async () => ({
          detail: 'Bad gateway',
        }),
      })

      const request = new NextRequest('http://localhost:3000/api/auth/signup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          host: 'localhost:3000',
        },
        body: JSON.stringify({
          email: 'newuser@example.com',
          password: 'SecurePass123!',
          username: 'newuser',
        }),
      })

      const response = await POST(request)

      expect(response.status).toBe(502)
      const data = await response.json()
      expect(data.detail).toBe('Bad gateway')
    })

    it('should return 503 for service unavailable errors', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 503,
        headers: {
          getSetCookie: () => [],
        },
        json: async () => ({
          detail: 'Service temporarily unavailable',
        }),
      })

      const request = new NextRequest('http://localhost:3000/api/auth/signup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          host: 'localhost:3000',
        },
        body: JSON.stringify({
          email: 'newuser@example.com',
          password: 'SecurePass123!',
          username: 'newuser',
        }),
      })

      const response = await POST(request)

      expect(response.status).toBe(503)
      const data = await response.json()
      expect(data.detail).toBe('Service temporarily unavailable')
    })

    it('should return 500 for internal server errors from backend', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 500,
        headers: {
          getSetCookie: () => [],
        },
        json: async () => ({
          detail: 'Internal server error',
        }),
      })

      const request = new NextRequest('http://localhost:3000/api/auth/signup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          host: 'localhost:3000',
        },
        body: JSON.stringify({
          email: 'newuser@example.com',
          password: 'SecurePass123!',
          username: 'newuser',
        }),
      })

      const response = await POST(request)

      expect(response.status).toBe(500)
      const data = await response.json()
      expect(data.detail).toBe('Internal server error')
    })

    it('should handle network errors gracefully', async () => {
      ;(global.fetch as jest.Mock).mockRejectedValueOnce(
        new Error('Network error')
      )

      const request = new NextRequest('http://localhost:3000/api/auth/signup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          host: 'localhost:3000',
        },
        body: JSON.stringify({
          email: 'newuser@example.com',
          password: 'SecurePass123!',
          username: 'newuser',
        }),
      })

      const response = await POST(request)

      expect(response.status).toBe(500)
      const data = await response.json()
      expect(data.error).toBe('Internal server error')
    })

    it('should handle JSON parse errors from backend', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 201,
        headers: {
          getSetCookie: () => [],
        },
        json: async () => {
          throw new Error('Invalid JSON')
        },
      })

      const request = new NextRequest('http://localhost:3000/api/auth/signup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          host: 'localhost:3000',
        },
        body: JSON.stringify({
          email: 'newuser@example.com',
          password: 'SecurePass123!',
          username: 'newuser',
        }),
      })

      const response = await POST(request)

      expect(response.status).toBe(500)
      const data = await response.json()
      expect(data.error).toBe('Internal server error')
    })
  })

  describe('Email verification flow', () => {
    it('should return user with email_verified: false on successful signup', async () => {
      const mockUser = {
        id: 1,
        email: 'newuser@example.com',
        username: 'newuser',
        email_verified: false,
        access_token: 'mock_token_123',
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 201,
        headers: {
          getSetCookie: () => [],
        },
        json: async () => mockUser,
      })

      const request = new NextRequest('http://localhost:3000/api/auth/signup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          host: 'localhost:3000',
        },
        body: JSON.stringify({
          email: 'newuser@example.com',
          password: 'SecurePass123!',
          username: 'newuser',
        }),
      })

      const response = await POST(request)

      expect(response.status).toBe(201)
      const data = await response.json()
      expect(data.email_verified).toBe(false)
      expect(data.email).toBe('newuser@example.com')
    })

    it('should handle verification email sending errors', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 500,
        headers: {
          getSetCookie: () => [],
        },
        json: async () => ({
          detail: 'Failed to send verification email',
        }),
      })

      const request = new NextRequest('http://localhost:3000/api/auth/signup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          host: 'localhost:3000',
        },
        body: JSON.stringify({
          email: 'newuser@example.com',
          password: 'SecurePass123!',
          username: 'newuser',
        }),
      })

      const response = await POST(request)

      expect(response.status).toBe(500)
      const data = await response.json()
      expect(data.detail).toBe('Failed to send verification email')
    })
  })

  describe('API base URL detection', () => {
    it('should use http://localhost:8001 for localhost:3000', async () => {
      const mockUser = {
        id: 1,
        email: 'newuser@example.com',
        access_token: 'mock_token_123',
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 201,
        headers: {
          getSetCookie: () => [],
        },
        json: async () => mockUser,
      })

      const request = new NextRequest('http://localhost:3000/api/auth/signup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          host: 'localhost:3000',
        },
        body: JSON.stringify({
          email: 'newuser@example.com',
          password: 'SecurePass123!',
          username: 'newuser',
        }),
      })

      await POST(request)

      expect(global.fetch).toHaveBeenCalledWith(
        'http://localhost:8001/api/auth/signup',
        expect.any(Object)
      )
    })

    it('should use http://api:8000 for benger.localhost', async () => {
      const mockUser = {
        id: 1,
        email: 'newuser@example.com',
        access_token: 'mock_token_123',
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 201,
        headers: {
          getSetCookie: () => [],
        },
        json: async () => mockUser,
      })

      const request = new NextRequest(
        'http://benger.localhost/api/auth/signup',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            host: 'benger.localhost',
          },
          body: JSON.stringify({
            email: 'newuser@example.com',
            password: 'SecurePass123!',
            username: 'newuser',
          }),
        }
      )

      await POST(request)

      expect(global.fetch).toHaveBeenCalledWith(
        'http://api:8000/api/auth/signup',
        expect.any(Object)
      )
    })

    it('should use environment variable API_URL for production', async () => {
      const originalApiUrl = process.env.API_URL
      process.env.API_URL = 'http://custom-api:8000'

      const mockUser = {
        id: 1,
        email: 'newuser@example.com',
        access_token: 'mock_token_123',
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 201,
        headers: {
          getSetCookie: () => [],
        },
        json: async () => mockUser,
      })

      const request = new NextRequest(
        'https://what-a-benger.net/api/auth/signup',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            host: 'what-a-benger.net',
          },
          body: JSON.stringify({
            email: 'newuser@example.com',
            password: 'SecurePass123!',
            username: 'newuser',
          }),
        }
      )

      await POST(request)

      expect(global.fetch).toHaveBeenCalledWith(
        'http://custom-api:8000/api/auth/signup',
        expect.any(Object)
      )

      // Restore environment variable
      if (originalApiUrl) {
        process.env.API_URL = originalApiUrl
      } else {
        delete process.env.API_URL
      }
    })
  })

  describe('Cookie handling edge cases - E2E TESTS REQUIRED', () => {
    // All cookie handling tests require browser Cookie API
    // See: /services/frontend/docs/testing/auth-api-routes-e2e.md

    it('should handle empty cookie array', async () => {
      const mockUser = {
        id: 1,
        email: 'newuser@example.com',
        access_token: 'mock_token_123',
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 201,
        headers: {
          getSetCookie: () => [],
        },
        json: async () => mockUser,
      })

      const request = new NextRequest('http://localhost:3000/api/auth/signup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          host: 'localhost:3000',
        },
        body: JSON.stringify({
          email: 'newuser@example.com',
          password: 'SecurePass123!',
          username: 'newuser',
        }),
      })

      const response = await POST(request)

      expect(response.status).toBe(201)
    })

    // E2E TEST REQUIRED: Cookie Domain stripping
    // See: /services/frontend/docs/testing/auth-api-routes-e2e.md

    // E2E TEST REQUIRED: SameSite attribute addition
    // See: /services/frontend/docs/testing/auth-api-routes-e2e.md
  })

  describe('Request body validation', () => {
    it('should handle empty request body', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 400,
        headers: {
          getSetCookie: () => [],
        },
        json: async () => ({
          detail: 'Request body is required',
        }),
      })

      const request = new NextRequest('http://localhost:3000/api/auth/signup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          host: 'localhost:3000',
        },
        body: JSON.stringify({}),
      })

      const response = await POST(request)

      expect(response.status).toBe(400)
    })

    it('should handle invalid JSON in request body', async () => {
      const request = new NextRequest('http://localhost:3000/api/auth/signup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          host: 'localhost:3000',
        },
        body: 'invalid json',
      })

      const response = await POST(request)

      expect(response.status).toBe(500)
      const data = await response.json()
      expect(data.error).toBe('Internal server error')
    })

    it('should handle null values in required fields', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 400,
        headers: {
          getSetCookie: () => [],
        },
        json: async () => ({
          detail: 'Email is required',
        }),
      })

      const request = new NextRequest('http://localhost:3000/api/auth/signup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          host: 'localhost:3000',
        },
        body: JSON.stringify({
          email: null,
          password: 'SecurePass123!',
          username: 'newuser',
        }),
      })

      const response = await POST(request)

      expect(response.status).toBe(400)
    })

    it('should handle extra fields in request body', async () => {
      const mockUser = {
        id: 1,
        email: 'newuser@example.com',
        username: 'newuser',
        access_token: 'mock_token_123',
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 201,
        headers: {
          getSetCookie: () => [],
        },
        json: async () => mockUser,
      })

      const request = new NextRequest('http://localhost:3000/api/auth/signup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          host: 'localhost:3000',
        },
        body: JSON.stringify({
          email: 'newuser@example.com',
          password: 'SecurePass123!',
          username: 'newuser',
          extraField: 'should be ignored',
          role: 'admin',
        }),
      })

      const response = await POST(request)

      expect(response.status).toBe(201)
      expect(global.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          body: JSON.stringify({
            email: 'newuser@example.com',
            password: 'SecurePass123!',
            username: 'newuser',
            extraField: 'should be ignored',
            role: 'admin',
          }),
        })
      )
    })
  })

  describe('Username validation errors', () => {
    it('should return 409 when username already exists', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 409,
        headers: {
          getSetCookie: () => [],
        },
        json: async () => ({
          detail: 'Username already taken',
        }),
      })

      const request = new NextRequest('http://localhost:3000/api/auth/signup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          host: 'localhost:3000',
        },
        body: JSON.stringify({
          email: 'newuser@example.com',
          password: 'SecurePass123!',
          username: 'existinguser',
        }),
      })

      const response = await POST(request)

      expect(response.status).toBe(409)
      const data = await response.json()
      expect(data.detail).toBe('Username already taken')
    })

    it('should return 400 for username with invalid characters', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 400,
        headers: {
          getSetCookie: () => [],
        },
        json: async () => ({
          detail: 'Username contains invalid characters',
        }),
      })

      const request = new NextRequest('http://localhost:3000/api/auth/signup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          host: 'localhost:3000',
        },
        body: JSON.stringify({
          email: 'newuser@example.com',
          password: 'SecurePass123!',
          username: 'user@name!',
        }),
      })

      const response = await POST(request)

      expect(response.status).toBe(400)
      const data = await response.json()
      expect(data.detail).toBe('Username contains invalid characters')
    })

    it('should return 400 for username that is too short', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 400,
        headers: {
          getSetCookie: () => [],
        },
        json: async () => ({
          detail: 'Username must be at least 3 characters long',
        }),
      })

      const request = new NextRequest('http://localhost:3000/api/auth/signup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          host: 'localhost:3000',
        },
        body: JSON.stringify({
          email: 'newuser@example.com',
          password: 'SecurePass123!',
          username: 'ab',
        }),
      })

      const response = await POST(request)

      expect(response.status).toBe(400)
      const data = await response.json()
      expect(data.detail).toBe('Username must be at least 3 characters long')
    })
  })

  describe('Error Logging', () => {
    it('should log error on failure', async () => {
      ;(global.fetch as jest.Mock).mockRejectedValueOnce(
        new Error('Network error')
      )

      const request = new NextRequest('http://localhost:3000/api/auth/signup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          host: 'localhost:3000',
        },
        body: JSON.stringify({
          email: 'newuser@example.com',
          password: 'SecurePass123!',
          username: 'newuser',
        }),
      })

      await POST(request)

      expect(console.error).toHaveBeenCalledWith(
        '❌ Signup proxy error:',
        expect.any(Error)
      )
    })
  })
})
