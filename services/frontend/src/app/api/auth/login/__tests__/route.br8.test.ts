/**
 * @jest-environment node
 *
 * Branch coverage: login/route.ts
 * Targets uncovered branches:
 *   - L7: host empty fallback
 *   - L65: cookieDomain truthy for domain append
 *   - L67: missing Path in cookie
 */

import { NextRequest } from 'next/server'

jest.mock('@/lib/utils/logger', () => ({
  logger: { debug: jest.fn() },
}))

jest.mock('@/lib/utils/subdomain', () => ({
  getCookieDomainFromHost: (host: string) => {
    if (host.includes('benger.localhost')) return '.benger.localhost'
    return ''
  },
}))

function makeRequest(host: string) {
  return new NextRequest(new URL('http://localhost/api/auth/login'), {
    method: 'POST',
    headers: { host, 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'admin', password: 'admin' }),
  })
}

describe('login route br8', () => {
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

  it('handles OK response with Set-Cookie having domain rewrite (L52-96)', async () => {
    const headers = new Headers()
    headers.append('Set-Cookie', 'access_token=tok; Domain=old; Secure; HttpOnly')

    jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ user: { id: 1 } }), {
        status: 200,
        headers,
      })
    )
    const { POST } = require('../route')
    const res = await POST(makeRequest('benger.localhost'))
    const cookies = res.headers.getSetCookie()
    // Should have the modified cookie + test cookie
    expect(cookies.length).toBeGreaterThanOrEqual(2)
    // First cookie should have domain rewritten
    expect(cookies[0]).toContain('.benger.localhost')
    // Secure should be removed
    expect(cookies[0]).not.toMatch(/;\s*Secure/)
  })

  it('handles OK response with cookie missing Path and SameSite (L72-78)', async () => {
    const headers = new Headers()
    headers.append('Set-Cookie', 'token=val; HttpOnly')

    jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers,
      })
    )
    const { POST } = require('../route')
    const res = await POST(makeRequest('benger.localhost'))
    const cookies = res.headers.getSetCookie()
    const mainCookie = cookies[0]
    expect(mainCookie).toContain('Path=/')
    expect(mainCookie).toContain('SameSite=Lax')
  })

  it('handles OK response with empty cookieDomain (localhost, L67 falsy)', async () => {
    const headers = new Headers()
    headers.append('Set-Cookie', 'token=val')

    jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers,
      })
    )
    const { POST } = require('../route')
    const res = await POST(makeRequest('localhost:3000'))
    const cookies = res.headers.getSetCookie()
    // No Domain attribute should be added for empty cookieDomain
    expect(cookies[0]).not.toContain('Domain=')
  })

  it('handles non-ok response (login failure)', async () => {
    jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Invalid credentials' }), { status: 401 })
    )
    const { POST } = require('../route')
    const res = await POST(makeRequest('benger.localhost'))
    expect(res.status).toBe(401)
  })

  it('handles fetch exception (L99-104)', async () => {
    jest.spyOn(global, 'fetch').mockRejectedValue(new Error('fail'))
    jest.spyOn(console, 'error').mockImplementation()
    const { POST } = require('../route')
    const res = await POST(makeRequest('benger.localhost'))
    expect(res.status).toBe(500)
  })
})
