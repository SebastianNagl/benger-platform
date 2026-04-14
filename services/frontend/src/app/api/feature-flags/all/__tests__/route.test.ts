/**
 * @jest-environment node
 */

import { NextRequest } from 'next/server'
import { GET } from '../route'

const mockFetch = jest.fn()
global.fetch = mockFetch

jest.mock('@/lib/utils/logger', () => ({
  logger: { debug: jest.fn(), info: jest.fn(), error: jest.fn() },
}))

describe('GET /api/feature-flags/all', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    delete process.env.API_BASE_URL
    delete process.env.DOCKER_INTERNAL_API_URL
    delete process.env.API_URL
    delete process.env.HOSTNAME
  })

  it('should proxy feature flags request', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve([
          { name: 'evaluations', enabled: true },
          { name: 'reports', enabled: false },
        ]),
    })

    const request = new NextRequest(
      'http://benger.localhost/api/feature-flags/all',
      { headers: { host: 'benger.localhost' } }
    )

    const response = await GET(request)
    const data = await response.json()

    expect(mockFetch).toHaveBeenCalledWith(
      'http://api:8000/api/feature-flags/all',
      expect.objectContaining({ method: 'GET' })
    )
    expect(data).toHaveLength(2)
  })

  it('should pass query params to backend', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve([]),
    })

    const request = new NextRequest(
      'http://benger.localhost/api/feature-flags/all?org_id=org-1',
      { headers: { host: 'benger.localhost' } }
    )

    await GET(request)

    expect(mockFetch).toHaveBeenCalledWith(
      'http://api:8000/api/feature-flags/all?org_id=org-1',
      expect.any(Object)
    )
  })

  it('should return 500 on error', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Connection refused'))

    const request = new NextRequest(
      'http://benger.localhost/api/feature-flags/all',
      { headers: { host: 'benger.localhost' } }
    )

    const response = await GET(request)
    const data = await response.json()

    expect(response.status).toBe(500)
    expect(data.error).toBe('Internal server error')
  })

  it('should use test API for test host', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve([]),
    })

    const request = new NextRequest(
      'http://benger-test.localhost/api/feature-flags/all',
      { headers: { host: 'benger-test.localhost' } }
    )

    await GET(request)

    expect(mockFetch).toHaveBeenCalledWith(
      'http://test-api:8000/api/feature-flags/all',
      expect.any(Object)
    )
  })

  it('should use staging API for staging host', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve([]),
    })

    const request = new NextRequest(
      'http://staging.what-a-benger.net/api/feature-flags/all',
      { headers: { host: 'staging.what-a-benger.net' } }
    )

    await GET(request)

    expect(mockFetch).toHaveBeenCalledWith(
      'http://benger-api:8000/api/feature-flags/all',
      expect.any(Object)
    )
  })

  it('should use API_BASE_URL when set', async () => {
    process.env.API_BASE_URL = 'http://custom:9000'
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve([]),
    })

    const request = new NextRequest(
      'http://benger.localhost/api/feature-flags/all',
      { headers: { host: 'benger.localhost' } }
    )

    await GET(request)

    expect(mockFetch).toHaveBeenCalledWith(
      'http://custom:9000/api/feature-flags/all',
      expect.any(Object)
    )
  })

  it('should pass backend status code through', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 403,
      json: () => Promise.resolve({ detail: 'Forbidden' }),
    })

    const request = new NextRequest(
      'http://benger.localhost/api/feature-flags/all',
      { headers: { host: 'benger.localhost' } }
    )

    const response = await GET(request)
    expect(response.status).toBe(403)
  })

  it('should handle production host', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve([]),
    })

    const request = new NextRequest(
      'http://what-a-benger.net/api/feature-flags/all',
      { headers: { host: 'what-a-benger.net' } }
    )

    await GET(request)

    expect(mockFetch).toHaveBeenCalledWith(
      'http://benger-api:8000/api/feature-flags/all',
      expect.any(Object)
    )
  })

  it('should handle localhost outside Docker', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve([]),
    })

    const request = new NextRequest(
      'http://localhost:3000/api/feature-flags/all',
      { headers: { host: 'localhost:3000' } }
    )

    await GET(request)

    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8001/api/feature-flags/all',
      expect.any(Object)
    )
  })
})
