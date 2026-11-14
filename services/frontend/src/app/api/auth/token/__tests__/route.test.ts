/**
 * @jest-environment node
 *
 * POST /api/auth/token on the app host: the script login the API documents.
 * The catch-all proxy refuses auth/* paths without a dedicated handler, so
 * this route is what makes the endpoint reachable on the public host.
 */

import { NextRequest } from 'next/server'
import { POST as catchAll } from '../../../[...path]/route'
import { POST } from '../route'

const tokenBody = {
  access_token: 'jwt-access',
  token_type: 'bearer',
  expires_in: 3600,
  user: { id: 'u1', username: 'script' },
}

function request(body: string, headers: Record<string, string> = {}) {
  return new NextRequest('http://what-a-benger.net/api/auth/token', {
    method: 'POST',
    headers: {
      host: 'what-a-benger.net',
      'Content-Type': 'application/json',
      ...headers,
    },
    body,
  })
}

describe('/api/auth/token', () => {
  let mockFetch: jest.Mock

  beforeEach(() => {
    mockFetch = jest.fn()
    global.fetch = mockFetch
    jest.spyOn(console, 'error').mockImplementation()
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  it('relays the access token in the body and sets no cookie', async () => {
    mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify(tokenBody), {
        status: 200,
        // Even if an API version set one, a script login never starts a
        // browser session on this host.
        headers: { 'Set-Cookie': 'access_token=jwt-access; HttpOnly; Path=/' },
      }),
    )

    const response = await POST(
      request(JSON.stringify({ username: 'script', password: 'pw' }), {
        'x-forwarded-for': '203.0.113.7',
      }),
    )

    expect(response.status).toBe(200)
    expect(await response.json()).toEqual(tokenBody)
    expect(response.headers.getSetCookie()).toEqual([])
    expect(response.headers.get('Cache-Control')).toBe('no-store')

    const [url, init] = mockFetch.mock.calls[0]
    expect(url).toMatch(/\/api\/auth\/token$/)
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({
      username: 'script',
      password: 'pw',
    })
    // The API limits failed logins per client address.
    expect(init.headers['x-forwarded-for']).toBe('203.0.113.7')
    expect(init.headers['x-forwarded-host']).toBe('what-a-benger.net')
  })

  it('passes a refusal through with its status and Retry-After', async () => {
    mockFetch.mockResolvedValueOnce(
      new Response(
        JSON.stringify({ detail: { code: 'rate_limited', retry_after: 30 } }),
        { status: 429, headers: { 'Retry-After': '30' } },
      ),
    )

    const response = await POST(
      request(JSON.stringify({ username: 'script', password: 'wrong' })),
    )

    expect(response.status).toBe(429)
    expect(response.headers.get('Retry-After')).toBe('30')
    expect(await response.json()).toEqual({
      detail: { code: 'rate_limited', retry_after: 30 },
    })
  })

  it('passes wrong credentials through as 401', async () => {
    mockFetch.mockResolvedValueOnce(
      new Response(
        JSON.stringify({ detail: 'Incorrect username or password' }),
        {
          status: 401,
        },
      ),
    )

    const response = await POST(
      request(JSON.stringify({ username: 'script', password: 'wrong' })),
    )

    expect(response.status).toBe(401)
  })

  it('answers a body that is not JSON with 422 without calling the API', async () => {
    const response = await POST(request('not json'))

    expect(response.status).toBe(422)
    expect(mockFetch).not.toHaveBeenCalled()
  })

  it('answers 500 when the API cannot be reached', async () => {
    mockFetch.mockRejectedValueOnce(new Error('ECONNREFUSED'))

    const response = await POST(
      request(JSON.stringify({ username: 'script', password: 'pw' })),
    )

    expect(response.status).toBe(500)
  })

  it('leaves the catch-all guard for other auth paths in place', async () => {
    const response = await catchAll(
      new NextRequest('http://what-a-benger.net/api/auth/tokens', {
        method: 'POST',
        headers: { host: 'what-a-benger.net' },
        body: '{}',
      }),
      { params: Promise.resolve({ path: ['auth', 'tokens'] }) },
    )

    expect(response.status).toBe(400)
    expect(mockFetch).not.toHaveBeenCalled()
  })
})
