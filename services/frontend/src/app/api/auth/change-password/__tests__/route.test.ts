/**
 * Comprehensive tests for change-password API route
 * Tests password change flow, authentication, and error scenarios
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

// Helper to create mock backend response
const createMockResponse = (data: any, status: number, isText = false) => {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
    text: async () => (isText ? data : JSON.stringify(data)),
  }
}

describe('/api/auth/change-password', () => {
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

  describe('Successful Password Change', () => {
    it('should forward change-password request to backend with authentication', async () => {
      const mockResponse = {
        message: 'Password changed successfully',
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse(mockResponse, 200)
      )

      const passwordData = {
        old_password: 'oldpassword123',
        new_password: 'newpassword456',
      }

      const request = createRequest(
        'http://localhost:3000/api/auth/change-password',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            cookie: 'access_token=valid_token',
          },
          body: JSON.stringify(passwordData),
        }
      )

      await POST(request)

      expect(global.fetch).toHaveBeenCalledWith(
        'http://localhost:8001/api/auth/change-password',
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
            Cookie: 'access_token=valid_token',
          }),
          body: JSON.stringify(passwordData),
        })
      )
    })

    it('should return 200 with success message', async () => {
      const mockResponse = {
        message: 'Password changed successfully',
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse(mockResponse, 200)
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/change-password',
        {
          method: 'POST',
          headers: {
            cookie: 'access_token=valid_token',
          },
          body: JSON.stringify({
            old_password: 'oldpass',
            new_password: 'newpass',
          }),
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(200)
      const data = await response.json()
      expect(data.message).toBe('Password changed successfully')
    })

    it('should forward authorization header when present', async () => {
      const mockResponse = {
        message: 'Password changed successfully',
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse(mockResponse, 200)
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/change-password',
        {
          method: 'POST',
          headers: {
            authorization: 'Bearer test_token_123',
          },
          body: JSON.stringify({
            old_password: 'oldpass',
            new_password: 'newpass',
          }),
        }
      )

      await POST(request)

      expect(global.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            Authorization: 'Bearer test_token_123',
          }),
        })
      )
    })

    it('should forward both cookies and authorization header', async () => {
      const mockResponse = {
        message: 'Password changed successfully',
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse(mockResponse, 200)
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/change-password',
        {
          method: 'POST',
          headers: {
            cookie: 'access_token=cookie_token',
            authorization: 'Bearer header_token',
          },
          body: JSON.stringify({
            old_password: 'oldpass',
            new_password: 'newpass',
          }),
        }
      )

      await POST(request)

      expect(global.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            Cookie: 'access_token=cookie_token',
            Authorization: 'Bearer header_token',
          }),
        })
      )
    })
  })

  describe('Authentication Failures', () => {
    it('should return 401 for unauthenticated request', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse('Unauthorized', 401, true)
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/change-password',
        {
          method: 'POST',
          body: JSON.stringify({
            old_password: 'oldpass',
            new_password: 'newpass',
          }),
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(401)
      const data = await response.json()
      expect(data.error).toBe('Unauthorized')
    })

    it('should return 401 for invalid token', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse('Invalid token', 401, true)
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/change-password',
        {
          method: 'POST',
          headers: {
            cookie: 'access_token=invalid_token',
          },
          body: JSON.stringify({
            old_password: 'oldpass',
            new_password: 'newpass',
          }),
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(401)
    })

    it('should return 403 for forbidden access', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse('Forbidden', 403, true)
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/change-password',
        {
          method: 'POST',
          headers: {
            cookie: 'access_token=valid_token',
          },
          body: JSON.stringify({
            old_password: 'oldpass',
            new_password: 'newpass',
          }),
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(403)
    })
  })

  describe('Password Validation Errors', () => {
    it('should return 400 for incorrect old password', async () => {
      const mockError = {
        detail: 'Current password is incorrect',
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse('Current password is incorrect', 400, true)
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/change-password',
        {
          method: 'POST',
          headers: {
            cookie: 'access_token=valid_token',
          },
          body: JSON.stringify({
            old_password: 'wrongpassword',
            new_password: 'newpass123',
          }),
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(400)
      const data = await response.json()
      expect(data.error).toBe('Current password is incorrect')
    })

    it('should return 422 for weak new password', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse('Password too weak', 422, true)
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/change-password',
        {
          method: 'POST',
          headers: {
            cookie: 'access_token=valid_token',
          },
          body: JSON.stringify({
            old_password: 'oldpass',
            new_password: '123',
          }),
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(422)
    })

    it('should return 422 for missing old password', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse('Old password is required', 422, true)
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/change-password',
        {
          method: 'POST',
          headers: {
            cookie: 'access_token=valid_token',
          },
          body: JSON.stringify({
            new_password: 'newpass123',
          }),
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(422)
    })

    it('should return 422 for missing new password', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse('New password is required', 422, true)
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/change-password',
        {
          method: 'POST',
          headers: {
            cookie: 'access_token=valid_token',
          },
          body: JSON.stringify({
            old_password: 'oldpass123',
          }),
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(422)
    })

    it('should return 422 for empty request body', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse('Request body is required', 422, true)
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/change-password',
        {
          method: 'POST',
          headers: {
            cookie: 'access_token=valid_token',
          },
          body: JSON.stringify({}),
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(422)
    })

    it('should handle malformed JSON', async () => {
      const request = createRequest(
        'http://localhost:3000/api/auth/change-password',
        {
          method: 'POST',
          headers: {
            cookie: 'access_token=valid_token',
          },
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
    it('should handle 500 Internal Server Error', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse('Internal server error', 500, true)
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/change-password',
        {
          method: 'POST',
          headers: {
            cookie: 'access_token=valid_token',
          },
          body: JSON.stringify({
            old_password: 'oldpass',
            new_password: 'newpass',
          }),
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(500)
    })

    it('should handle 502 Bad Gateway', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse('Bad Gateway', 502, true)
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/change-password',
        {
          method: 'POST',
          headers: {
            cookie: 'access_token=valid_token',
          },
          body: JSON.stringify({
            old_password: 'oldpass',
            new_password: 'newpass',
          }),
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(502)
    })

    it('should handle 503 Service Unavailable', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse('Service Unavailable', 503, true)
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/change-password',
        {
          method: 'POST',
          headers: {
            cookie: 'access_token=valid_token',
          },
          body: JSON.stringify({
            old_password: 'oldpass',
            new_password: 'newpass',
          }),
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(503)
    })

    it('should handle empty error response with fallback message', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse('', 400, true)
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/change-password',
        {
          method: 'POST',
          headers: {
            cookie: 'access_token=valid_token',
          },
          body: JSON.stringify({
            old_password: 'oldpass',
            new_password: 'newpass',
          }),
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(400)
      const data = await response.json()
      expect(data.error).toBe('Password change failed')
    })
  })

  describe('Network Errors', () => {
    it('should handle network timeout', async () => {
      ;(global.fetch as jest.Mock).mockRejectedValueOnce(
        new Error('Network timeout')
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/change-password',
        {
          method: 'POST',
          headers: {
            cookie: 'access_token=valid_token',
          },
          body: JSON.stringify({
            old_password: 'oldpass',
            new_password: 'newpass',
          }),
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
        'http://localhost:3000/api/auth/change-password',
        {
          method: 'POST',
          headers: {
            cookie: 'access_token=valid_token',
          },
          body: JSON.stringify({
            old_password: 'oldpass',
            new_password: 'newpass',
          }),
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(500)
      const data = await response.json()
      expect(data.error).toBe('Internal server error')
      expect(console.error).toHaveBeenCalledWith(
        '❌ Change password proxy error:',
        expect.any(Error)
      )
    })

    it('should handle DNS resolution failure', async () => {
      ;(global.fetch as jest.Mock).mockRejectedValueOnce(
        new Error('getaddrinfo ENOTFOUND')
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/change-password',
        {
          method: 'POST',
          headers: {
            cookie: 'access_token=valid_token',
          },
          body: JSON.stringify({
            old_password: 'oldpass',
            new_password: 'newpass',
          }),
        }
      )

      const response = await POST(request)

      expect(response.status).toBe(500)
    })
  })

  describe('API Base URL Detection', () => {
    it('should use Docker API URL for benger.localhost', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse({ message: 'Success' }, 200)
      )

      const request = createRequest(
        'http://benger.localhost/api/auth/change-password',
        {
          method: 'POST',
          headers: {
            cookie: 'access_token=valid_token',
          },
          body: JSON.stringify({
            old_password: 'oldpass',
            new_password: 'newpass',
          }),
        }
      )

      await POST(request)

      expect(global.fetch).toHaveBeenCalledWith(
        'http://api:8000/api/auth/change-password',
        expect.any(Object)
      )
    })

    it('should use localhost:8001 for localhost:3000', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse({ message: 'Success' }, 200)
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/change-password',
        {
          method: 'POST',
          headers: {
            cookie: 'access_token=valid_token',
          },
          body: JSON.stringify({
            old_password: 'oldpass',
            new_password: 'newpass',
          }),
        }
      )

      await POST(request)

      expect(global.fetch).toHaveBeenCalledWith(
        'http://localhost:8001/api/auth/change-password',
        expect.any(Object)
      )
    })

    it('should use environment variable for production deployment', async () => {
      const originalDockerUrl = process.env.DOCKER_INTERNAL_API_URL
      const originalApiUrl = process.env.API_URL
      process.env.DOCKER_INTERNAL_API_URL = 'http://custom-api:7000'
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse({ message: 'Success' }, 200)
      )

      const request = createRequest(
        'https://what-a-benger.net/api/auth/change-password',
        {
          method: 'POST',
          headers: {
            cookie: 'access_token=valid_token',
          },
          body: JSON.stringify({
            old_password: 'oldpass',
            new_password: 'newpass',
          }),
        }
      )

      await POST(request)

      expect(global.fetch).toHaveBeenCalledWith(
        'http://custom-api:7000/api/auth/change-password',
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
        createMockResponse({ message: 'Success' }, 200)
      )

      const request = createRequest(
        'https://what-a-benger.net/api/auth/change-password',
        {
          method: 'POST',
          headers: {
            cookie: 'access_token=valid_token',
          },
          body: JSON.stringify({
            old_password: 'oldpass',
            new_password: 'newpass',
          }),
        }
      )

      await POST(request)

      expect(global.fetch).toHaveBeenCalledWith(
        'http://benger-api:8000/api/auth/change-password',
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
        createMockResponse({ message: 'Success' }, 200)
      )

      const request = createRequest(
        'http://unknown.domain/api/auth/change-password',
        {
          method: 'POST',
          headers: {
            cookie: 'access_token=valid_token',
          },
          body: JSON.stringify({
            old_password: 'oldpass',
            new_password: 'newpass',
          }),
        }
      )

      await POST(request)

      expect(global.fetch).toHaveBeenCalledWith(
        'http://api:8000/api/auth/change-password',
        expect.any(Object)
      )
    })
  })

  describe('Request Forwarding', () => {
    it('should forward request body correctly', async () => {
      const passwordData = {
        old_password: 'oldpassword123',
        new_password: 'newpassword456',
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse({ message: 'Success' }, 200)
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/change-password',
        {
          method: 'POST',
          headers: {
            cookie: 'access_token=valid_token',
          },
          body: JSON.stringify(passwordData),
        }
      )

      await POST(request)

      expect(global.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
          body: JSON.stringify(passwordData),
        })
      )
    })

    it('should set correct Content-Type header', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse({ message: 'Success' }, 200)
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/change-password',
        {
          method: 'POST',
          headers: {
            cookie: 'access_token=valid_token',
          },
          body: JSON.stringify({
            old_password: 'oldpass',
            new_password: 'newpass',
          }),
        }
      )

      await POST(request)

      expect(global.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
        })
      )
    })

    it('should handle empty cookies gracefully', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce(
        createMockResponse({ message: 'Success' }, 200)
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/change-password',
        {
          method: 'POST',
          body: JSON.stringify({
            old_password: 'oldpass',
            new_password: 'newpass',
          }),
        }
      )

      await POST(request)

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

  describe('Error Logging', () => {
    it('should log errors from network failures', async () => {
      ;(global.fetch as jest.Mock).mockRejectedValueOnce(
        new Error('Connection failed')
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/change-password',
        {
          method: 'POST',
          headers: {
            cookie: 'access_token=valid_token',
          },
          body: JSON.stringify({
            old_password: 'oldpass',
            new_password: 'newpass',
          }),
        }
      )

      await POST(request)

      expect(console.error).toHaveBeenCalledWith(
        '❌ Change password proxy error:',
        expect.any(Error)
      )
    })

    it('should log errors from backend failures', async () => {
      ;(global.fetch as jest.Mock).mockRejectedValueOnce(
        new Error('Backend unreachable')
      )

      const request = createRequest(
        'http://localhost:3000/api/auth/change-password',
        {
          method: 'POST',
          headers: {
            cookie: 'access_token=valid_token',
          },
          body: JSON.stringify({
            old_password: 'oldpass',
            new_password: 'newpass',
          }),
        }
      )

      await POST(request)

      expect(console.error).toHaveBeenCalledWith(
        '❌ Change password proxy error:',
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
 * 1. Complete Password Change Flow:
 *    - Login with existing credentials
 *    - Change password via UI
 *    - Logout
 *    - Login with new password
 *
 * 2. Security Validation:
 *    - Test password strength requirements
 *    - Verify old password verification
 *    - Test session invalidation after password change
 *
 * 3. Error Handling:
 *    - Test UI feedback for incorrect old password
 *    - Test UI validation for weak passwords
 *    - Verify authentication required for password change
 *
 * These tests should be implemented using Puppeteer as specified in the project guidelines.
 */
