/**
 * @jest-environment node
 */

import { NextRequest } from 'next/server'
import { GET } from '../route'

// Mock global fetch
const mockFetch = jest.fn()
global.fetch = mockFetch

describe('GET /api/auth/me/contexts', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    delete process.env.API_BASE_URL
    delete process.env.DOCKER_INTERNAL_API_URL
    delete process.env.API_URL
    delete process.env.HOSTNAME
  })

  it('should proxy request to backend and return data', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          contexts: [{ org_id: 'org-1', role: 'ADMIN' }],
        }),
    })

    const request = new NextRequest('http://benger.localhost/api/auth/me/contexts', {
      headers: {
        host: 'benger.localhost',
        cookie: 'session=abc123',
      },
    })

    const response = await GET(request)
    const data = await response.json()

    expect(mockFetch).toHaveBeenCalledWith(
      'http://api:8000/api/auth/me/contexts',
      expect.objectContaining({
        method: 'GET',
        headers: expect.objectContaining({
          Cookie: 'session=abc123',
        }),
      })
    )
    expect(data.contexts).toHaveLength(1)
  })

  it('should return error when backend returns non-ok response', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
    })

    const request = new NextRequest('http://benger.localhost/api/auth/me/contexts', {
      headers: { host: 'benger.localhost' },
    })

    const response = await GET(request)
    const data = await response.json()

    expect(response.status).toBe(401)
    expect(data.error).toBe('Unauthorized')
  })

  it('should return 500 on fetch error', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Network error'))

    const request = new NextRequest('http://benger.localhost/api/auth/me/contexts', {
      headers: { host: 'benger.localhost' },
    })

    const response = await GET(request)
    const data = await response.json()

    expect(response.status).toBe(500)
    expect(data.error).toBe('Internal server error')
  })

  it('should use API_BASE_URL env var when set', async () => {
    process.env.API_BASE_URL = 'http://custom-api:9000'
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ contexts: [] }),
    })

    const request = new NextRequest('http://benger.localhost/api/auth/me/contexts', {
      headers: { host: 'benger.localhost' },
    })

    await GET(request)

    expect(mockFetch).toHaveBeenCalledWith(
      'http://custom-api:9000/api/auth/me/contexts',
      expect.any(Object)
    )
  })

  it('should use test API URL for benger-test.localhost', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ contexts: [] }),
    })

    const request = new NextRequest(
      'http://benger-test.localhost/api/auth/me/contexts',
      { headers: { host: 'benger-test.localhost' } }
    )

    await GET(request)

    expect(mockFetch).toHaveBeenCalledWith(
      'http://test-api:8000/api/auth/me/contexts',
      expect.any(Object)
    )
  })

  it('should use staging API URL for staging host', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ contexts: [] }),
    })

    const request = new NextRequest(
      'http://staging.what-a-benger.net/api/auth/me/contexts',
      { headers: { host: 'staging.what-a-benger.net' } }
    )

    await GET(request)

    expect(mockFetch).toHaveBeenCalledWith(
      'http://benger-api:8000/api/auth/me/contexts',
      expect.any(Object)
    )
  })

  it('should use production API URL for what-a-benger.net', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ contexts: [] }),
    })

    const request = new NextRequest(
      'http://what-a-benger.net/api/auth/me/contexts',
      { headers: { host: 'what-a-benger.net' } }
    )

    await GET(request)

    expect(mockFetch).toHaveBeenCalledWith(
      'http://benger-api:8000/api/auth/me/contexts',
      expect.any(Object)
    )
  })

  it('should handle localhost:3000 in Docker', async () => {
    process.env.DOCKER_INTERNAL_API_URL = 'http://api:8000'
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ contexts: [] }),
    })

    const request = new NextRequest('http://localhost:3000/api/auth/me/contexts', {
      headers: { host: 'localhost:3000' },
    })

    await GET(request)

    expect(mockFetch).toHaveBeenCalledWith(
      'http://api:8000/api/auth/me/contexts',
      expect.any(Object)
    )
  })

  it('should handle localhost:3000 outside Docker', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ contexts: [] }),
    })

    const request = new NextRequest('http://localhost:3000/api/auth/me/contexts', {
      headers: { host: 'localhost:3000' },
    })

    await GET(request)

    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8001/api/auth/me/contexts',
      expect.any(Object)
    )
  })

  it('should handle missing cookie header', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ contexts: [] }),
    })

    const request = new NextRequest('http://benger.localhost/api/auth/me/contexts', {
      headers: { host: 'benger.localhost' },
    })

    await GET(request)

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
