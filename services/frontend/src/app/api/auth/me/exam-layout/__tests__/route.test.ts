/**
 * @jest-environment node
 */

import { NextRequest } from 'next/server'
import { PUT } from '../route'

// Mock fetch
const mockFetch = jest.fn()
global.fetch = mockFetch

const PREFS_BODY = {
  exam_layout_prefs: {
    mode: 'modern',
    case_position: 'left',
    notes_position: 'right',
    outline_position: 'none',
  },
}

function makeRequest(body: unknown = PREFS_BODY) {
  return new NextRequest('http://vertretbar.localhost/api/auth/me/exam-layout', {
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

describe('PUT /api/auth/me/exam-layout', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('proxies the request with auth headers AND the JSON body', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({ id: 'u1', exam_layout_prefs: PREFS_BODY.exam_layout_prefs }),
    })

    const response = await PUT(makeRequest())
    const data = await response.json()

    expect(data.exam_layout_prefs.mode).toBe('modern')
    expect(mockFetch).toHaveBeenCalledWith(
      'http://api:8000/api/auth/me/exam-layout',
      expect.objectContaining({
        method: 'PUT',
        headers: expect.objectContaining({
          Cookie: 'session=abc',
          Authorization: 'Bearer token123',
        }),
        body: JSON.stringify(PREFS_BODY),
      })
    )
  })

  it('forwards a null-clearing body unchanged', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ id: 'u1', exam_layout_prefs: null }),
    })

    await PUT(makeRequest({ exam_layout_prefs: null }))

    expect(mockFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        body: JSON.stringify({ exam_layout_prefs: null }),
      })
    )
  })

  it('passes backend errors through with their status', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 422,
      text: () => Promise.resolve('validation error'),
    })

    const response = await PUT(makeRequest({ exam_layout_prefs: { mode: 'nope' } }))
    const data = await response.json()

    expect(response.status).toBe(422)
    expect(data.error).toBe('validation error')
  })

  it('forwards empty strings when the request carries no auth headers', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ id: 'u1' }),
    })

    const bare = new NextRequest('http://vertretbar.localhost/api/auth/me/exam-layout', {
      method: 'PUT',
      headers: { host: 'vertretbar.localhost', 'content-type': 'application/json' },
      body: JSON.stringify(PREFS_BODY),
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
