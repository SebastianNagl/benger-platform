/**
 * @jest-environment node
 *
 * The browser never sees a session token in a response body.
 *
 * The API keeps the access and refresh tokens in HttpOnly cookies. The proxy
 * routes that relay its login and refresh answers must not hand any token to
 * page script either (an older API, or a future change, could still put one
 * in the body). The SSE proxy refreshes server-side when the access cookie
 * has expired; since every refresh rotates the refresh token, it must pass
 * the new cookies on to the browser, or the browser keeps the replaced token
 * and the next refresh counts as token reuse and ends the session.
 */

import { NextRequest } from 'next/server'
import { GET as stream } from '../../notifications/stream/route'
import { POST as login } from '../login/route'
import { POST as refresh } from '../refresh/route'

const backendBody = {
  access_token: 'jwt-access',
  refresh_token: 'opaque-refresh',
  token_type: 'bearer',
  expires_in: 3600,
  user: { id: 'u1', username: 'user' },
}

const backendSetCookies = [
  'access_token=jwt-access; HttpOnly; Max-Age=3600; Path=/; SameSite=lax',
  'refresh_token=opaque-refresh-2; HttpOnly; Max-Age=604800; Path=/; SameSite=lax',
]

function backendOk() {
  return {
    ok: true,
    status: 200,
    json: async () => ({ ...backendBody }),
    headers: { getSetCookie: () => [...backendSetCookies], get: () => null },
  }
}

function request(path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers)
  headers.set('host', 'localhost:3000')
  return new NextRequest(`http://localhost:3000${path}`, { ...init, headers })
}

describe('session tokens stay in HttpOnly cookies', () => {
  let mockFetch: jest.Mock

  beforeEach(() => {
    mockFetch = jest.fn()
    global.fetch = mockFetch
    jest.spyOn(console, 'error').mockImplementation()
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  it('login relays the user but no token', async () => {
    mockFetch.mockResolvedValueOnce(backendOk())

    const response = await login(
      request('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username: 'user', password: 'pw' }),
      }),
    )

    const body = await response.json()
    expect(body).toEqual({
      token_type: 'bearer',
      expires_in: 3600,
      user: { id: 'u1', username: 'user' },
    })
    const cookies = response.headers.getSetCookie()
    expect(cookies.some((c) => c.startsWith('refresh_token='))).toBe(true)
    expect(cookies.every((c) => /HttpOnly/i.test(c))).toBe(true)
  })

  it('refresh relays no token', async () => {
    mockFetch.mockResolvedValueOnce(backendOk())

    const response = await refresh(
      request('/api/auth/refresh', {
        method: 'POST',
        headers: { cookie: 'refresh_token=opaque-refresh' },
      }),
    )

    const body = await response.json()
    expect(body).not.toHaveProperty('access_token')
    expect(body).not.toHaveProperty('refresh_token')
    expect(body.user).toEqual({ id: 'u1', username: 'user' })
  })

  it('the SSE proxy passes the rotated cookies of its refresh to the browser', async () => {
    mockFetch.mockResolvedValueOnce(backendOk()).mockResolvedValueOnce({
      ok: true,
      body: {
        getReader: () => ({
          read: jest.fn().mockResolvedValue({ done: true, value: undefined }),
        }),
      },
    })

    const response = await stream(
      request('/api/notifications/stream', {
        headers: { cookie: 'refresh_token=opaque-refresh' },
      }),
    )

    const cookies = response.headers.getSetCookie()
    expect(cookies).toEqual(
      expect.arrayContaining([
        expect.stringMatching(/^access_token=jwt-access;.*HttpOnly/i),
        expect.stringMatching(/^refresh_token=opaque-refresh-2;.*HttpOnly/i),
      ]),
    )
    // The backend stream request uses the new access token.
    expect(mockFetch.mock.calls[1][1].headers.get('cookie')).toContain(
      'access_token=jwt-access',
    )
  })
})
