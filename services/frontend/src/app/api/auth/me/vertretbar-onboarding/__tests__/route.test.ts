/**
 * @jest-environment node
 */

import { NextRequest } from 'next/server'
import { POST } from '../route'

// Mock fetch
const mockFetch = jest.fn()
global.fetch = mockFetch

describe('POST /api/auth/me/vertretbar-onboarding', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('should proxy request to backend and return JSON on success', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          id: 'u1',
          vertretbar_onboarding_completed_at: '2026-07-15T00:00:00Z',
        }),
    })

    const request = new NextRequest(
      'http://vertretbar.localhost/api/auth/me/vertretbar-onboarding',
      {
        method: 'POST',
        headers: {
          host: 'vertretbar.localhost',
          cookie: 'session=abc',
          authorization: 'Bearer token123',
        },
      }
    )

    const response = await POST(request)
    const data = await response.json()

    expect(data.vertretbar_onboarding_completed_at).toBe('2026-07-15T00:00:00Z')
    expect(mockFetch).toHaveBeenCalledWith(
      'http://api:8000/api/auth/me/vertretbar-onboarding',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          Cookie: 'session=abc',
          Authorization: 'Bearer token123',
        }),
      })
    )
  })

  it('should return error on backend failure', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 401,
      text: () => Promise.resolve('Unauthorized'),
    })

    const request = new NextRequest(
      'http://vertretbar.localhost/api/auth/me/vertretbar-onboarding',
      { method: 'POST', headers: { host: 'vertretbar.localhost' } }
    )

    const response = await POST(request)
    const data = await response.json()

    expect(response.status).toBe(401)
    expect(data.error).toBe('Unauthorized')
  })

  it('should return 500 on fetch error', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'))

    const request = new NextRequest(
      'http://vertretbar.localhost/api/auth/me/vertretbar-onboarding',
      { method: 'POST', headers: { host: 'vertretbar.localhost' } }
    )

    const response = await POST(request)
    expect(response.status).toBe(500)
  })

  it('should use correct API URL for test environment', async () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({}) })

    const request = new NextRequest(
      'http://benger-test.localhost/api/auth/me/vertretbar-onboarding',
      { method: 'POST', headers: { host: 'benger-test.localhost' } }
    )

    await POST(request)

    expect(mockFetch).toHaveBeenCalledWith(
      'http://test-api:8000/api/auth/me/vertretbar-onboarding',
      expect.anything()
    )
  })
})
