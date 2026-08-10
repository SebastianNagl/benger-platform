/**
 * @jest-environment node
 *
 * Regression guard for the once-missing ui-mode proxy: without this dedicated
 * route the catch-all rejects the auth write with 400 and setUiMode() never
 * reaches the backend.
 */

import { NextRequest } from 'next/server'
import { PUT } from '../route'

// Mock fetch
const mockFetch = jest.fn()
global.fetch = mockFetch

function makeRequest(body: unknown = { preferred_ui_mode: 'student' }) {
  return new NextRequest('http://vertretbar.localhost/api/auth/me/ui-mode', {
    method: 'PUT',
    headers: {
      host: 'vertretbar.localhost',
      cookie: 'session=abc',
      authorization: 'Bearer token123',
      'content-type': 'application/json',
    },
    body: JSON.stringify(body),
  })
}

describe('PUT /api/auth/me/ui-mode', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('proxies the request with auth headers AND the JSON body', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ id: 'u1', preferred_ui_mode: 'student' }),
    })

    const response = await PUT(makeRequest())
    const data = await response.json()

    expect(data.preferred_ui_mode).toBe('student')
    expect(mockFetch).toHaveBeenCalledWith(
      'http://api:8000/api/auth/me/ui-mode',
      expect.objectContaining({
        method: 'PUT',
        headers: expect.objectContaining({
          Cookie: 'session=abc',
          Authorization: 'Bearer token123',
        }),
        body: JSON.stringify({ preferred_ui_mode: 'student' }),
      })
    )
  })

  it('passes backend errors through with their status', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 401,
      text: () => Promise.resolve('Unauthorized'),
    })

    const response = await PUT(makeRequest())
    const data = await response.json()

    expect(response.status).toBe(401)
    expect(data.error).toBe('Unauthorized')
  })

  it('forwards empty strings when the request carries no auth headers', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ id: 'u1' }),
    })

    const bare = new NextRequest('http://vertretbar.localhost/api/auth/me/ui-mode', {
      method: 'PUT',
      headers: { host: 'vertretbar.localhost', 'content-type': 'application/json' },
      body: JSON.stringify({ preferred_ui_mode: 'student' }),
    })

    await PUT(bare)

    expect(mockFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({ Cookie: '', Authorization: '' }),
      })
    )
  })

  it('falls back to a generic message when the backend error body is empty', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 502,
      text: () => Promise.resolve(''),
    })

    const response = await PUT(makeRequest())
    const data = await response.json()

    expect(response.status).toBe(502)
    expect(data.error).toBe('Request failed')
  })

  it('returns 500 on fetch error', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'))

    const response = await PUT(makeRequest())
    expect(response.status).toBe(500)
  })
})
