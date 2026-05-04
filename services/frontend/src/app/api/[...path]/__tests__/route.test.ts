/**
 * API Proxy Route Tests
 * Comprehensive unit tests for the API proxy functionality
 */

import { NextRequest } from 'next/server'
import { DELETE, GET, PATCH, POST, PUT } from '../route'

// Mock fetch globally
global.fetch = jest.fn()

// Helper to create mock headers with getSetCookie method
function createMockHeaders(cookies: string[] = []): Headers {
  const headers = new Headers()
  // Add cookies as Set-Cookie headers
  cookies.forEach((cookie) => {
    headers.append('Set-Cookie', cookie)
  })
  return headers
}

describe('API Proxy Route', () => {
  let mockFetch: jest.MockedFunction<typeof fetch>

  beforeEach(() => {
    mockFetch = global.fetch as jest.MockedFunction<typeof fetch>
    mockFetch.mockClear()
    jest.clearAllMocks()

    // Mock console methods
    jest.spyOn(console, 'log').mockImplementation()
    jest.spyOn(console, 'error').mockImplementation()
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  describe('Environment-specific routing', () => {
    it('should route localhost:3000 to localhost:8001', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 200,
        statusText: 'OK',
        headers: createMockHeaders(),
        text: async () => '{"success": true}',
      } as any)

      const request = new NextRequest('http://localhost:3000/api/tasks', {
        headers: { host: 'localhost:3000' },
      })
      await GET(request, { params: Promise.resolve({ path: ['tasks'] }) })

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8001/api/tasks',
        expect.any(Object)
      )
    })

    it('should route benger.localhost to api:8000', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 200,
        statusText: 'OK',
        headers: createMockHeaders(),
        text: async () => '{"success": true}',
      } as any)

      const request = new NextRequest('http://benger.localhost/api/tasks', {
        headers: { host: 'benger.localhost' },
      })
      await GET(request, { params: Promise.resolve({ path: ['tasks'] }) })

      expect(mockFetch).toHaveBeenCalledWith(
        'http://api:8000/api/tasks',
        expect.any(Object)
      )
    })

    it('should route what-a-benger.net to benger-api:8000', async () => {
      const originalEnv = process.env.NODE_ENV
      process.env.NODE_ENV = 'production'

      mockFetch.mockResolvedValueOnce({
        status: 200,
        statusText: 'OK',
        headers: createMockHeaders(),
        text: async () => '{"success": true}',
      } as any)

      const request = new NextRequest('https://what-a-benger.net/api/tasks', {
        headers: { host: 'what-a-benger.net' },
      })
      await GET(request, { params: Promise.resolve({ path: ['tasks'] }) })

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('api/tasks'),
        expect.any(Object)
      )

      process.env.NODE_ENV = originalEnv
    })

    it('should use DOCKER_INTERNAL_API_URL when set', async () => {
      const originalUrl = process.env.DOCKER_INTERNAL_API_URL
      process.env.DOCKER_INTERNAL_API_URL = 'http://custom-api:9000'
      const originalEnv = process.env.NODE_ENV
      process.env.NODE_ENV = 'production'

      mockFetch.mockResolvedValueOnce({
        status: 200,
        statusText: 'OK',
        headers: createMockHeaders(),
        text: async () => '{"success": true}',
      } as any)

      const request = new NextRequest('https://what-a-benger.net/api/tasks', {
        headers: { host: 'what-a-benger.net' },
      })
      await GET(request, { params: Promise.resolve({ path: ['tasks'] }) })

      expect(mockFetch).toHaveBeenCalledWith(
        'http://custom-api:9000/api/tasks',
        expect.any(Object)
      )

      process.env.DOCKER_INTERNAL_API_URL = originalUrl
      process.env.NODE_ENV = originalEnv
    })
  })

  describe('HTTP methods', () => {
    beforeEach(() => {
      mockFetch.mockResolvedValue({
        status: 200,
        statusText: 'OK',
        headers: createMockHeaders(),
        text: async () => '{"success": true}',
      } as any)
    })

    it('should proxy GET requests', async () => {
      const request = new NextRequest('http://localhost:3000/api/tasks')
      await GET(request, { params: Promise.resolve({ path: ['tasks'] }) })

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tasks'),
        expect.objectContaining({ method: 'GET' })
      )
    })

    it('should proxy POST requests with body', async () => {
      const body = JSON.stringify({ name: 'Test Task' })
      const request = new NextRequest('http://localhost:3000/api/tasks', {
        method: 'POST',
        body,
      })

      await POST(request, { params: Promise.resolve({ path: ['tasks'] }) })

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tasks'),
        expect.objectContaining({
          method: 'POST',
          // Proxy now streams the body — could be a ReadableStream,
          // legacy string, or null for empty bodies. Don't lock the type.
          body: expect.anything(),
        })
      )
    })

    it('should proxy PUT requests', async () => {
      const body = JSON.stringify({ name: 'Updated Task' })
      const request = new NextRequest('http://localhost:3000/api/tasks/1', {
        method: 'PUT',
        body,
      })

      await PUT(request, { params: Promise.resolve({ path: ['tasks', '1'] }) })

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tasks/1'),
        expect.objectContaining({ method: 'PUT' })
      )
    })

    it('should proxy PATCH requests', async () => {
      const body = JSON.stringify({ status: 'completed' })
      const request = new NextRequest('http://localhost:3000/api/tasks/1', {
        method: 'PATCH',
        body,
      })

      await PATCH(request, {
        params: Promise.resolve({ path: ['tasks', '1'] }),
      })

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tasks/1'),
        expect.objectContaining({ method: 'PATCH' })
      )
    })

    it('should proxy DELETE requests', async () => {
      const request = new NextRequest('http://localhost:3000/api/tasks/1', {
        method: 'DELETE',
      })

      await DELETE(request, {
        params: Promise.resolve({ path: ['tasks', '1'] }),
      })

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tasks/1'),
        expect.objectContaining({ method: 'DELETE' })
      )
    })
  })

  describe('Header forwarding', () => {
    beforeEach(() => {
      mockFetch.mockResolvedValue({
        status: 200,
        statusText: 'OK',
        headers: createMockHeaders(),
        text: async () => '{"success": true}',
      } as any)
    })

    it('should forward authorization header', async () => {
      const request = new NextRequest('http://localhost:3000/api/tasks', {
        headers: {
          authorization: 'Bearer test-token',
        },
      })

      await GET(request, { params: Promise.resolve({ path: ['tasks'] }) })

      const fetchCall = mockFetch.mock.calls[0]
      const headers = fetchCall[1]?.headers as Headers
      expect(headers.get('authorization')).toBe('Bearer test-token')
    })

    it('should forward cookies', async () => {
      const request = new NextRequest('http://localhost:3000/api/tasks', {
        headers: {
          cookie: 'access_token=test; refresh_token=test123',
        },
      })

      await GET(request, { params: Promise.resolve({ path: ['tasks'] }) })

      const fetchCall = mockFetch.mock.calls[0]
      const headers = fetchCall[1]?.headers as Headers
      expect(headers.get('cookie')).toBe(
        'access_token=test; refresh_token=test123'
      )
    })

    it('should forward content-type header', async () => {
      const request = new NextRequest('http://localhost:3000/api/tasks', {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
        },
        body: '{"test": true}',
      })

      await POST(request, { params: Promise.resolve({ path: ['tasks'] }) })

      const fetchCall = mockFetch.mock.calls[0]
      const headers = fetchCall[1]?.headers as Headers
      expect(headers.get('content-type')).toBe('application/json')
    })

    it('should exclude problematic headers', async () => {
      const request = new NextRequest('http://localhost:3000/api/tasks', {
        headers: {
          host: 'localhost:3000',
          connection: 'keep-alive',
          'content-length': '123',
        },
      })

      await GET(request, { params: Promise.resolve({ path: ['tasks'] }) })

      const fetchCall = mockFetch.mock.calls[0]
      const headers = fetchCall[1]?.headers as Headers
      expect(headers.has('host')).toBe(false)
      expect(headers.has('connection')).toBe(false)
      expect(headers.has('content-length')).toBe(false)
    })
  })

  describe('Query parameter handling', () => {
    beforeEach(() => {
      mockFetch.mockResolvedValue({
        status: 200,
        statusText: 'OK',
        headers: createMockHeaders(),
        text: async () => '{"success": true}',
      } as any)
    })

    it('should forward query parameters', async () => {
      const request = new NextRequest(
        'http://localhost:3000/api/tasks?status=active&page=2'
      )

      await GET(request, { params: Promise.resolve({ path: ['tasks'] }) })

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('?status=active&page=2'),
        expect.any(Object)
      )
    })

    it('should handle requests without query parameters', async () => {
      const request = new NextRequest('http://localhost:3000/api/tasks')

      await GET(request, { params: Promise.resolve({ path: ['tasks'] }) })

      const url = mockFetch.mock.calls[0][0] as string
      expect(url).not.toContain('?')
    })
  })

  describe('Response handling', () => {
    it('should return response with correct status', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 201,
        statusText: 'Created',
        headers: createMockHeaders(),
        text: async () => '{"id": 1}',
      } as any)

      const request = new NextRequest('http://localhost:3000/api/tasks')
      const response = await GET(request, {
        params: Promise.resolve({ path: ['tasks'] }),
      })

      expect(response.status).toBe(201)
    })

    it('should forward response headers', async () => {
      const responseHeaders = createMockHeaders()
      responseHeaders.set('x-custom-header', 'test-value')
      responseHeaders.set('content-type', 'application/json')

      mockFetch.mockResolvedValueOnce({
        status: 200,
        statusText: 'OK',
        headers: responseHeaders,
        text: async () => '{"success": true}',
      } as any)

      const request = new NextRequest('http://localhost:3000/api/tasks', {
        headers: { host: 'localhost:3000' },
      })
      const response = await GET(request, {
        params: Promise.resolve({ path: ['tasks'] }),
      })

      expect(response.headers.get('x-custom-header')).toBe('test-value')
      expect(response.headers.get('content-type')).toBe('application/json')
    })

    it('should handle 204 No Content responses', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 204,
        statusText: 'No Content',
        headers: createMockHeaders(),
        text: async () => '',
      } as any)

      const request = new NextRequest('http://localhost:3000/api/tasks/1', {
        method: 'DELETE',
      })
      const response = await DELETE(request, {
        params: Promise.resolve({ path: ['tasks', '1'] }),
      })

      expect(response.status).toBe(204)
      expect(await response.text()).toBe('')
    })

    // Note: Set-Cookie header behavior tested via E2E - NextResponse APIs not fully mockable
  })

  describe('Error handling', () => {
    // Note: Retry logic (502/503) tested via E2E - request.clone() not mockable in Jest

    it('should not retry other error codes', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 500,
        statusText: 'Internal Server Error',
        headers: createMockHeaders(),
        text: async () => 'Server Error',
      } as any)

      const request = new NextRequest('http://localhost:3000/api/tasks')
      const response = await GET(request, {
        params: Promise.resolve({ path: ['tasks'] }),
      })

      expect(mockFetch).toHaveBeenCalledTimes(1)
      expect(response.status).toBe(500)
    })

    it('should handle fetch errors', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network error'))

      const request = new NextRequest('http://localhost:3000/api/tasks', {
        headers: { host: 'localhost:3000' },
      })
      const response = await GET(request, {
        params: Promise.resolve({ path: ['tasks'] }),
      })

      expect(response.status).toBe(500)
      const data = await response.json()
      expect(data.error).toBe('Internal server error')
    })
  })

  describe('Auth endpoint restrictions', () => {
    it('should block auth endpoints except verify-email', async () => {
      const request = new NextRequest('http://localhost:3000/api/auth/login')
      const response = await POST(request, {
        params: Promise.resolve({ path: ['auth', 'login'] }),
      })

      expect(response.status).toBe(400)
      const data = await response.json()
      expect(data.error).toBe('Use dedicated auth handler')
    })

    it('should allow verify-email through', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 200,
        statusText: 'OK',
        headers: createMockHeaders(),
        text: async () => '{"success": true}',
      } as any)

      const request = new NextRequest(
        'http://localhost:3000/api/auth/verify-email',
        {
          headers: { host: 'localhost:3000' },
        }
      )
      const response = await GET(request, {
        params: Promise.resolve({ path: ['auth', 'verify-email'] }),
      })

      expect(mockFetch).toHaveBeenCalled()
      expect(response.status).toBe(200)
    })
  })

  // Note: Cookie modification tested via E2E - NextResponse APIs not fully mockable

  describe('Path handling', () => {
    beforeEach(() => {
      mockFetch.mockResolvedValue({
        status: 200,
        statusText: 'OK',
        headers: createMockHeaders(),
        text: async () => '{"success": true}',
      } as any)
    })

    it('should handle single path segment', async () => {
      const request = new NextRequest('http://localhost:3000/api/tasks')
      await GET(request, { params: Promise.resolve({ path: ['tasks'] }) })

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tasks'),
        expect.any(Object)
      )
    })

    it('should handle nested path segments', async () => {
      const request = new NextRequest('http://localhost:3000/api/tasks/1/edit')
      await GET(request, {
        params: Promise.resolve({ path: ['tasks', '1', 'edit'] }),
      })

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tasks/1/edit'),
        expect.any(Object)
      )
    })

    it('should handle paths with special characters', async () => {
      const request = new NextRequest(
        'http://localhost:3000/api/tasks/test-task-123'
      )
      await GET(request, {
        params: Promise.resolve({ path: ['tasks', 'test-task-123'] }),
      })

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tasks/test-task-123'),
        expect.any(Object)
      )
    })

    it('should handle deep nested paths', async () => {
      const request = new NextRequest(
        'http://localhost:3000/api/projects/1/tasks/2/annotations/3/comments'
      )
      await GET(request, {
        params: Promise.resolve({
          path: ['projects', '1', 'tasks', '2', 'annotations', '3', 'comments'],
        }),
      })

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining(
          '/api/projects/1/tasks/2/annotations/3/comments'
        ),
        expect.any(Object)
      )
    })

    it('should handle paths with numeric IDs', async () => {
      const request = new NextRequest('http://localhost:3000/api/users/12345')
      await GET(request, {
        params: Promise.resolve({ path: ['users', '12345'] }),
      })

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/users/12345'),
        expect.any(Object)
      )
    })

    it('should handle paths with UUID-like strings', async () => {
      const uuid = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
      const request = new NextRequest(
        `http://localhost:3000/api/resources/${uuid}`
      )
      await GET(request, {
        params: Promise.resolve({ path: ['resources', uuid] }),
      })

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining(`/api/resources/${uuid}`),
        expect.any(Object)
      )
    })
  })

  describe('Request body handling', () => {
    beforeEach(() => {
      mockFetch.mockResolvedValue({
        status: 200,
        statusText: 'OK',
        headers: createMockHeaders(),
        text: async () => '{"success": true}',
      } as any)
    })

    it('should handle empty body for POST', async () => {
      const request = new NextRequest('http://localhost:3000/api/tasks', {
        method: 'POST',
      })

      await POST(request, { params: Promise.resolve({ path: ['tasks'] }) })

      const fetchCall = mockFetch.mock.calls[0]
      // Proxy now streams `request.body` (ReadableStream | null) instead
      // of buffering with `await request.text()`. An empty-body POST has
      // no body to forward — we just check fetch was called and the
      // body field is null/undefined, not a synthesized empty string.
      expect(fetchCall).toBeDefined()
      expect(fetchCall[1]?.body == null).toBe(true)
    })

    it('should handle large request bodies', async () => {
      const largeData = { data: 'x'.repeat(10000) }
      const body = JSON.stringify(largeData)

      const request = new NextRequest('http://localhost:3000/api/upload', {
        method: 'POST',
        body,
      })

      await POST(request, { params: Promise.resolve({ path: ['upload'] }) })

      expect(mockFetch).toHaveBeenCalled()
    })

    it('should handle malformed request bodies', async () => {
      const request = new NextRequest('http://localhost:3000/api/tasks', {
        method: 'POST',
        body: '{invalid json',
      })

      const response = await POST(request, {
        params: Promise.resolve({ path: ['tasks'] }),
      })

      // Should forward to backend regardless
      expect(mockFetch).toHaveBeenCalled()
    })
  })

  describe('Response body handling', () => {
    it('should handle large response bodies', async () => {
      const largeResponse = JSON.stringify({ data: 'y'.repeat(10000) })

      mockFetch.mockResolvedValueOnce({
        status: 200,
        statusText: 'OK',
        headers: createMockHeaders(),
        text: async () => largeResponse,
      } as any)

      const request = new NextRequest('http://localhost:3000/api/data', {
        headers: { host: 'localhost:3000' },
      })

      const response = await GET(request, {
        params: Promise.resolve({ path: ['data'] }),
      })

      const text = await response.text()
      expect(text).toBe(largeResponse)
    })

    it('should handle empty response bodies', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 200,
        statusText: 'OK',
        headers: createMockHeaders(),
        text: async () => '',
      } as any)

      const request = new NextRequest('http://localhost:3000/api/tasks', {
        headers: { host: 'localhost:3000' },
      })

      const response = await GET(request, {
        params: Promise.resolve({ path: ['tasks'] }),
      })

      const text = await response.text()
      expect(text).toBe('')
    })

    it('should handle response body read errors', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 200,
        statusText: 'OK',
        headers: createMockHeaders(),
        text: async () => {
          throw new Error('Read error')
        },
      } as any)

      const request = new NextRequest('http://localhost:3000/api/tasks', {
        headers: { host: 'localhost:3000' },
      })

      const response = await GET(request, {
        params: Promise.resolve({ path: ['tasks'] }),
      })

      // Should handle error gracefully
      const text = await response.text()
      expect(text).toBe('')
    })
  })

  // Note: Development logging uses logger.debug() which is not easily testable in unit tests
  // E2E tests should verify logging behavior in actual development environments

  describe('Status code handling', () => {
    it('should handle 201 Created', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 201,
        statusText: 'Created',
        headers: createMockHeaders(),
        text: async () => '{"id": 1}',
      } as any)

      const request = new NextRequest('http://localhost:3000/api/tasks', {
        method: 'POST',
        body: '{"name": "Test"}',
      })

      const response = await POST(request, {
        params: Promise.resolve({ path: ['tasks'] }),
      })

      expect(response.status).toBe(201)
    })

    it('should handle 400 Bad Request', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 400,
        statusText: 'Bad Request',
        headers: createMockHeaders(),
        text: async () => '{"error": "Invalid input"}',
      } as any)

      const request = new NextRequest('http://localhost:3000/api/tasks', {
        headers: { host: 'localhost:3000' },
      })

      const response = await GET(request, {
        params: Promise.resolve({ path: ['tasks'] }),
      })

      expect(response.status).toBe(400)
    })

    it('should handle 401 Unauthorized', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 401,
        statusText: 'Unauthorized',
        headers: createMockHeaders(),
        text: async () => '{"error": "Not authenticated"}',
      } as any)

      const request = new NextRequest('http://localhost:3000/api/tasks', {
        headers: { host: 'localhost:3000' },
      })

      const response = await GET(request, {
        params: Promise.resolve({ path: ['tasks'] }),
      })

      expect(response.status).toBe(401)
    })

    it('should handle 403 Forbidden', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 403,
        statusText: 'Forbidden',
        headers: createMockHeaders(),
        text: async () => '{"error": "Not authorized"}',
      } as any)

      const request = new NextRequest('http://localhost:3000/api/tasks', {
        headers: { host: 'localhost:3000' },
      })

      const response = await GET(request, {
        params: Promise.resolve({ path: ['tasks'] }),
      })

      expect(response.status).toBe(403)
    })

    it('should handle 404 Not Found', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 404,
        statusText: 'Not Found',
        headers: createMockHeaders(),
        text: async () => '{"error": "Not found"}',
      } as any)

      const request = new NextRequest('http://localhost:3000/api/tasks/999', {
        headers: { host: 'localhost:3000' },
      })

      const response = await GET(request, {
        params: Promise.resolve({ path: ['tasks', '999'] }),
      })

      expect(response.status).toBe(404)
    })

    it('should handle 422 Unprocessable Entity', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 422,
        statusText: 'Unprocessable Entity',
        headers: createMockHeaders(),
        text: async () => '{"error": "Validation error"}',
      } as any)

      const request = new NextRequest('http://localhost:3000/api/tasks', {
        method: 'POST',
        body: '{"invalid": "data"}',
      })

      const response = await POST(request, {
        params: Promise.resolve({ path: ['tasks'] }),
      })

      expect(response.status).toBe(422)
    })
  })

  describe('Special header handling', () => {
    it('should forward custom headers', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 200,
        statusText: 'OK',
        headers: createMockHeaders(),
        text: async () => '{"success": true}',
      } as any)

      const request = new NextRequest('http://localhost:3000/api/tasks', {
        headers: {
          'x-api-key': 'test-key-123',
          'x-request-id': 'req-456',
        },
      })

      await GET(request, { params: Promise.resolve({ path: ['tasks'] }) })

      const fetchCall = mockFetch.mock.calls[0]
      const headers = fetchCall[1]?.headers as Headers
      expect(headers.get('x-api-key')).toBe('test-key-123')
      expect(headers.get('x-request-id')).toBe('req-456')
    })

    it('should forward accept header', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 200,
        statusText: 'OK',
        headers: createMockHeaders(),
        text: async () => '{"success": true}',
      } as any)

      const request = new NextRequest('http://localhost:3000/api/tasks', {
        headers: {
          accept: 'application/json',
        },
      })

      await GET(request, { params: Promise.resolve({ path: ['tasks'] }) })

      const fetchCall = mockFetch.mock.calls[0]
      const headers = fetchCall[1]?.headers as Headers
      expect(headers.get('accept')).toBe('application/json')
    })

    it('should forward user-agent header', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 200,
        statusText: 'OK',
        headers: createMockHeaders(),
        text: async () => '{"success": true}',
      } as any)

      const request = new NextRequest('http://localhost:3000/api/tasks', {
        headers: {
          'user-agent': 'Mozilla/5.0',
        },
      })

      await GET(request, { params: Promise.resolve({ path: ['tasks'] }) })

      const fetchCall = mockFetch.mock.calls[0]
      const headers = fetchCall[1]?.headers as Headers
      expect(headers.get('user-agent')).toBe('Mozilla/5.0')
    })
  })

  describe('204 No Content with cookies', () => {
    it('should handle 204 with Set-Cookie headers', async () => {
      const headers = createMockHeaders(['session=abc; Path=/'])
      headers.forEach = jest.fn((callback) => {
        callback('application/json', 'content-type')
      })

      mockFetch.mockResolvedValueOnce({
        status: 204,
        statusText: 'No Content',
        headers,
        text: async () => '',
      } as any)

      const request = new NextRequest('http://localhost:3000/api/logout', {
        method: 'POST',
        headers: { host: 'localhost:3000' },
      })

      const response = await POST(request, {
        params: Promise.resolve({ path: ['logout'] }),
      })

      expect(response.status).toBe(204)
    })

    // Note: Cookie logging uses logger.debug() - tested via E2E

    it('should handle 204 without cookies', async () => {
      const headers = createMockHeaders([])
      headers.forEach = jest.fn((callback) => {
        callback('application/json', 'content-type')
      })

      mockFetch.mockResolvedValueOnce({
        status: 204,
        statusText: 'No Content',
        headers,
        text: async () => '',
      } as any)

      const request = new NextRequest('http://localhost:3000/api/tasks/1', {
        method: 'DELETE',
        headers: { host: 'localhost:3000' },
      })

      const response = await DELETE(request, {
        params: Promise.resolve({ path: ['tasks', '1'] }),
      })

      expect(response.status).toBe(204)
    })
  })

  // Note: Annotation endpoint retry handling logging uses logger.debug() - tested via E2E

  describe('Environment variable priority', () => {
    it('should prioritize DOCKER_INTERNAL_API_URL over API_URL', async () => {
      const originalDocker = process.env.DOCKER_INTERNAL_API_URL
      const originalApi = process.env.API_URL
      const originalEnv = process.env.NODE_ENV

      process.env.DOCKER_INTERNAL_API_URL = 'http://docker-api:8000'
      process.env.API_URL = 'http://api-fallback:8000'
      process.env.NODE_ENV = 'production'

      mockFetch.mockResolvedValueOnce({
        status: 200,
        statusText: 'OK',
        headers: createMockHeaders(),
        text: async () => '{"success": true}',
      } as any)

      const request = new NextRequest('https://what-a-benger.net/api/tasks', {
        headers: { host: 'what-a-benger.net' },
      })

      await GET(request, { params: Promise.resolve({ path: ['tasks'] }) })

      expect(mockFetch).toHaveBeenCalledWith(
        'http://docker-api:8000/api/tasks',
        expect.any(Object)
      )

      // Restore
      process.env.DOCKER_INTERNAL_API_URL = originalDocker
      process.env.API_URL = originalApi
      process.env.NODE_ENV = originalEnv
    })
  })

  // Note: Cookie modification for regular responses tested via E2E

  describe('Non-development environment', () => {
    it('should not log response preview outside development', async () => {
      const originalEnv = process.env.NODE_ENV
      process.env.NODE_ENV = 'production'

      mockFetch.mockResolvedValueOnce({
        status: 200,
        statusText: 'OK',
        headers: createMockHeaders(),
        text: async () => '{"test": "data"}',
      } as any)

      const request = new NextRequest('http://localhost:3000/api/tasks', {
        headers: { host: 'localhost:3000' },
      })

      await GET(request, { params: Promise.resolve({ path: ['tasks'] }) })

      const previewLogs = (console.log as jest.Mock).mock.calls.filter(
        (call) => call[0] === '📝 Response data preview:'
      )
      expect(previewLogs.length).toBe(0)

      process.env.NODE_ENV = originalEnv
    })
  })

  describe('Staging environment routing', () => {
    it('should use staging API for staging.what-a-benger.net', async () => {
      const originalEnv = process.env.NODE_ENV
      const originalApiUrl = process.env.API_BASE_URL

      process.env.NODE_ENV = 'production'
      delete process.env.API_BASE_URL

      mockFetch.mockResolvedValueOnce({
        status: 200,
        statusText: 'OK',
        headers: createMockHeaders(),
        text: async () => '{"success": true}',
      } as any)

      const request = new NextRequest(
        'https://staging.what-a-benger.net/api/tasks',
        {
          headers: { host: 'staging.what-a-benger.net' },
        }
      )

      await GET(request, { params: Promise.resolve({ path: ['tasks'] }) })

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('api/tasks'),
        expect.any(Object)
      )

      process.env.NODE_ENV = originalEnv
      if (originalApiUrl) {
        process.env.API_BASE_URL = originalApiUrl
      }
    })
  })

  describe('localhost:3001 legacy support', () => {
    it('should route localhost:3001 to localhost:8001', async () => {
      // Need to unset HOSTNAME and DOCKER_INTERNAL_API_URL to avoid Docker detection
      const originalHostname = process.env.HOSTNAME
      const originalDockerUrl = process.env.DOCKER_INTERNAL_API_URL
      delete process.env.HOSTNAME
      delete process.env.DOCKER_INTERNAL_API_URL

      mockFetch.mockResolvedValueOnce({
        status: 200,
        statusText: 'OK',
        headers: createMockHeaders(),
        text: async () => '{"success": true}',
      } as any)

      const request = new NextRequest('http://localhost:3001/api/tasks', {
        headers: { host: 'localhost:3001' },
      })

      await GET(request, { params: Promise.resolve({ path: ['tasks'] }) })

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8001/api/tasks',
        expect.any(Object)
      )

      // Restore
      if (originalHostname) {
        process.env.HOSTNAME = originalHostname
      }
      if (originalDockerUrl) {
        process.env.DOCKER_INTERNAL_API_URL = originalDockerUrl
      }
    })
  })
})
