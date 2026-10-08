/**
 * @jest-environment node
 */

import { NextRequest } from 'next/server'
import { PUT } from '../route'

const mockFetch = jest.fn()
global.fetch = mockFetch

const BODY = { tours: { student: 1 } }

function makeRequest(
  body: unknown = BODY,
  headers: Record<string, string> = {},
) {
  return new NextRequest('http://benger.localhost/api/auth/me/onboarding', {
    method: 'PUT',
    headers: {
      host: 'benger.localhost',
      'content-type': 'application/json',
      ...headers,
    },
    body: typeof body === 'string' ? body : JSON.stringify(body),
  })
}

describe('PUT /api/auth/me/onboarding', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('proxies the request with auth headers and the JSON body', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ id: 'u1', onboarding_state: BODY }),
    })

    const response = await PUT(
      makeRequest(BODY, { cookie: 'session=abc', authorization: 'Bearer t' }),
    )

    expect((await response.json()).onboarding_state).toEqual(BODY)
    expect(mockFetch).toHaveBeenCalledWith(
      'http://api:8000/api/auth/me/onboarding',
      expect.objectContaining({
        method: 'PUT',
        headers: expect.objectContaining({
          Cookie: 'session=abc',
          Authorization: 'Bearer t',
        }),
        body: JSON.stringify(BODY),
      }),
    )
  })

  it('passes backend errors through with their status', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 422,
      text: () => Promise.resolve('validation error'),
    })

    const response = await PUT(makeRequest({ tours: { student: 'x' } }))

    expect(response.status).toBe(422)
    expect((await response.json()).error).toBe('validation error')
  })

  it('returns 500 on fetch error', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'))

    const response = await PUT(makeRequest())
    expect(response.status).toBe(500)
  })

  it('answers 422 for a body that is not valid JSON, without calling the backend', async () => {
    const response = await PUT(makeRequest('not json'))

    expect(response.status).toBe(422)
    expect(mockFetch).not.toHaveBeenCalled()
  })
})
