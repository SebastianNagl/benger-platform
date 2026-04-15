/**
 * @jest-environment node
 *
 * Coverage extension tests for the API proxy route.
 * Covers: API_BASE_URL env, benger-test.localhost, localhost:3001,
 * Set-Cookie forwarding on non-204 responses.
 */
import { NextRequest } from 'next/server'
import { GET, PATCH } from '../route'

describe('API Proxy Route - coverage extensions', () => {
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
    delete process.env.API_BASE_URL
  })

  function createMockHeaders(cookies: string[] = []): Headers {
    const headers = new Headers()
    headers.set('content-type', 'application/json')
    cookies.forEach((cookie) => {
      headers.append('Set-Cookie', cookie)
    })
    return headers
  }

  it('should use API_BASE_URL env var when set', async () => {
    process.env.API_BASE_URL = 'http://custom-api:9000'

    mockFetch.mockResolvedValueOnce({
      status: 200,
      statusText: 'OK',
      headers: createMockHeaders(),
      text: async () => '{"ok":true}',
    })

    const request = new NextRequest('http://localhost:3000/api/tasks', {
      headers: { host: 'localhost:3000' },
    })

    await GET(request, { params: Promise.resolve({ path: ['tasks'] }) })

    expect(mockFetch).toHaveBeenCalledWith(
      'http://custom-api:9000/api/tasks',
      expect.anything()
    )
  })

  it('should route benger-test.localhost to test-api:8000', async () => {
    mockFetch.mockResolvedValueOnce({
      status: 200,
      statusText: 'OK',
      headers: createMockHeaders(),
      text: async () => '{"ok":true}',
    })

    const request = new NextRequest('http://benger-test.localhost/api/tasks', {
      headers: { host: 'benger-test.localhost' },
    })

    await GET(request, { params: Promise.resolve({ path: ['tasks'] }) })

    expect(mockFetch).toHaveBeenCalledWith(
      'http://test-api:8000/api/tasks',
      expect.anything()
    )
  })

  it('should handle localhost:3001', async () => {
    mockFetch.mockResolvedValueOnce({
      status: 200,
      statusText: 'OK',
      headers: createMockHeaders(),
      text: async () => '{"ok":true}',
    })

    const request = new NextRequest('http://localhost:3001/api/tasks', {
      headers: { host: 'localhost:3001' },
    })

    await GET(request, { params: Promise.resolve({ path: ['tasks'] }) })

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/tasks'),
      expect.anything()
    )
  })

  it('should forward Set-Cookie headers from non-204 responses with domain rewrite', async () => {
    mockFetch.mockResolvedValueOnce({
      status: 200,
      statusText: 'OK',
      headers: createMockHeaders([
        'session=abc123; Path=/; Domain=old.domain; HttpOnly',
      ]),
      text: async () => '{"ok":true}',
    })

    const request = new NextRequest('http://benger.localhost/api/projects', {
      headers: { host: 'benger.localhost' },
    })

    const response = await GET(request, {
      params: Promise.resolve({ path: ['projects'] }),
    })

    const cookies = response.headers.getSetCookie()
    expect(cookies.length).toBe(1)
    expect(cookies[0]).toContain('session=abc123')
    expect(cookies[0]).toContain('Domain=.benger.localhost')
    expect(cookies[0]).not.toContain('Domain=old.domain')
    expect(cookies[0]).toContain('SameSite=Lax')
  })

  it('should handle PATCH requests with body', async () => {
    mockFetch.mockResolvedValueOnce({
      status: 200,
      statusText: 'OK',
      headers: createMockHeaders(),
      text: async () => '{"updated":true}',
    })

    const request = new NextRequest('http://benger.localhost/api/tasks/1', {
      method: 'PATCH',
      headers: {
        host: 'benger.localhost',
        'content-type': 'application/json',
      },
      body: JSON.stringify({ title: 'Updated' }),
    })

    const response = await PATCH(request, {
      params: Promise.resolve({ path: ['tasks', '1'] }),
    })

    expect(response.status).toBe(200)
  })

  it('should return 500 on fetch failure', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Connection refused'))

    const request = new NextRequest('http://benger.localhost/api/tasks', {
      headers: { host: 'benger.localhost' },
    })

    const response = await GET(request, {
      params: Promise.resolve({ path: ['tasks'] }),
    })

    expect(response.status).toBe(500)
  })
})
