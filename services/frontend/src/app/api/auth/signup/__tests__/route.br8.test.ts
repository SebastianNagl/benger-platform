/**
 * @jest-environment node
 *
 * Branch coverage: signup/route.ts
 * Targets uncovered branches:
 *   - L7: host empty fallback
 *   - L24: staging.what-a-benger.net branch (3rd in chain)
 *   - L67: upstream Domain stripped in Set-Cookie handling
 *   - L69: missing Path= in cookie
 *   - L79: missing SameSite in cookie
 */

import { NextRequest } from 'next/server'

jest.mock('@/lib/utils/logger', () => ({
  logger: { debug: jest.fn() },
}))

function makeRequest(host: string) {
  return new NextRequest(new URL('http://localhost/api/auth/signup'), {
    method: 'POST',
    headers: { host, 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'test', password: 'pass' }),
  })
}

describe('signup route br8', () => {
  const origEnv = { ...process.env }

  beforeEach(() => {
    jest.resetModules()
    process.env = { ...origEnv }
    delete process.env.API_BASE_URL
  })

  afterEach(() => {
    process.env = origEnv
    jest.restoreAllMocks()
  })

  it('routes staging.what-a-benger.net to staging API (L20-22)', async () => {
    const fetchSpy = jest
      .spyOn(global, 'fetch')
      .mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), { status: 200 }),
      )
    const { POST } = require('../route')
    await POST(makeRequest('staging.what-a-benger.net'))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('benger-api:8000'),
      expect.anything(),
    )
  })

  it('handles OK response with Set-Cookie headers, stripping the upstream Domain (L52-92)', async () => {
    const headers = new Headers()
    headers.append(
      'Set-Cookie',
      'access_token=abc; Domain=api.internal; Secure; HttpOnly',
    )

    jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ user: { id: 1 } }), {
        status: 200,
        headers,
      }),
    )
    const { POST } = require('../route')
    const res = await POST(makeRequest('benger.localhost'))
    expect(res.status).toBe(200)
    // Check that Set-Cookie was forwarded host-only
    const cookies = res.headers.getSetCookie()
    expect(cookies.length).toBeGreaterThan(0)
    const cookie = cookies[0]
    expect(cookie).toContain('access_token=abc')
    expect(cookie).not.toContain('Domain=')
    // Secure should be removed
    expect(cookie).not.toMatch(/;\s*Secure/i)
  })

  it('handles OK response with cookie missing Path and SameSite (L74, L79)', async () => {
    const headers = new Headers()
    headers.append('Set-Cookie', 'token=val; HttpOnly')

    jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers,
      }),
    )
    const { POST } = require('../route')
    const res = await POST(makeRequest('benger.localhost'))
    const cookies = res.headers.getSetCookie()
    const cookie = cookies[0]
    expect(cookie).toContain('Path=/')
    expect(cookie).toContain('SameSite=Lax')
  })

  it('handles non-ok response (L48-50)', async () => {
    jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Bad request' }), {
        status: 400,
      }),
    )
    const { POST } = require('../route')
    const res = await POST(makeRequest('benger.localhost'))
    expect(res.status).toBe(400)
  })

  it('handles fetch exception (L96-101)', async () => {
    jest.spyOn(global, 'fetch').mockRejectedValue(new Error('network'))
    jest.spyOn(console, 'error').mockImplementation()
    const { POST } = require('../route')
    const res = await POST(makeRequest('benger.localhost'))
    expect(res.status).toBe(500)
  })

  it('handles a cookie on plain localhost', async () => {
    const headers = new Headers()
    headers.append('Set-Cookie', 'token=val; HttpOnly')

    jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers,
      }),
    )
    const { POST } = require('../route')
    const res = await POST(makeRequest('localhost:3000'))
    expect(res.status).toBe(200)
  })
})
