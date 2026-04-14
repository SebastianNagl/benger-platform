/**
 * @jest-environment node
 */

import { NextRequest } from 'next/server'
import { GET } from '../route'

const mockFetch = jest.fn()
global.fetch = mockFetch

describe('GET /api/auth/profile-history', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('should proxy GET request and return data on success', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ history: [] }),
    })

    const request = new NextRequest(
      'http://benger.localhost/api/auth/profile-history',
      { headers: { host: 'benger.localhost' } }
    )

    const response = await GET(request)
    const data = await response.json()

    expect(data).toEqual({ history: [] })
  })

  it('should pass query parameters to backend', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ history: [] }),
    })

    const request = new NextRequest(
      'http://benger.localhost/api/auth/profile-history?page=1&limit=10',
      { headers: { host: 'benger.localhost' } }
    )

    await GET(request)

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('page=1'),
      expect.anything()
    )
  })

  it('should return error on backend failure', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 403,
      text: () => Promise.resolve('Forbidden'),
    })

    const request = new NextRequest(
      'http://benger.localhost/api/auth/profile-history',
      { headers: { host: 'benger.localhost' } }
    )

    const response = await GET(request)
    expect(response.status).toBe(403)
  })

  it('should return 500 on fetch error', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'))

    const request = new NextRequest(
      'http://benger.localhost/api/auth/profile-history',
      { headers: { host: 'benger.localhost' } }
    )

    const response = await GET(request)
    expect(response.status).toBe(500)
  })
})
