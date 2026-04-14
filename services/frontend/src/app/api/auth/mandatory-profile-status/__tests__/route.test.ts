/**
 * @jest-environment node
 */

import { NextRequest } from 'next/server'
import { GET } from '../route'

const mockFetch = jest.fn()
global.fetch = mockFetch

describe('GET /api/auth/mandatory-profile-status', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('should proxy GET request and return data on success', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ profile_complete: true }),
    })

    const request = new NextRequest(
      'http://benger.localhost/api/auth/mandatory-profile-status',
      { headers: { host: 'benger.localhost', cookie: 'session=abc' } }
    )

    const response = await GET(request)
    const data = await response.json()

    expect(data).toEqual({ profile_complete: true })
  })

  it('should return error on backend failure', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 401,
      text: () => Promise.resolve('Unauthorized'),
    })

    const request = new NextRequest(
      'http://benger.localhost/api/auth/mandatory-profile-status',
      { headers: { host: 'benger.localhost' } }
    )

    const response = await GET(request)
    expect(response.status).toBe(401)
  })

  it('should return 500 on fetch error', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'))

    const request = new NextRequest(
      'http://benger.localhost/api/auth/mandatory-profile-status',
      { headers: { host: 'benger.localhost' } }
    )

    const response = await GET(request)
    expect(response.status).toBe(500)
  })
})
