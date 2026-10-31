/**
 * @jest-environment node
 *
 * Branch coverage: login/route.ts
 * Targets uncovered branches:
 *   - L7: host empty fallback
 *   - upstream Domain stripped, legacy-domain clears relayed
 *   - L67: missing Path in cookie
 */

import { NextRequest } from 'next/server'

jest.mock('@/lib/utils/logger', () => ({
  logger: { debug: jest.fn() },
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

  it('handles OK response with Set-Cookie, stripping the upstream Domain (L52-96)', async () => {
    const headers = new Headers()
    headers.append(
      'Set-Cookie',
      'access_token=tok; Domain=old; Secure; HttpOnly',
    )

    jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ user: { id: 1 } }), {
        status: 200,
        headers,
      }),
    )
    const { POST } = require('../route')
    const res = await POST(makeRequest('benger.localhost'))
    const cookies = res.headers.getSetCookie()
    // Should have the modified cookie + test cookie
    expect(cookies.length).toBeGreaterThanOrEqual(2)
    // First cookie is host-only: the upstream Domain is gone
    expect(cookies[0]).not.toContain('Domain=')
    // Secure should be removed
    expect(cookies[0]).not.toMatch(/;\s*Secure/)
  })

  it('relays the legacy-domain clears ahead of the new host-only cookie', async () => {
    const headers = new Headers()
    headers.append(
      'Set-Cookie',
      'access_token=""; Domain=.benger.localhost; expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0; Path=/; SameSite=lax',
    )
    headers.append(
      'Set-Cookie',
      'access_token=""; Domain=.vertretbar.localhost; expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0; Path=/; SameSite=lax',
    )
    headers.append(
      'Set-Cookie',
      'access_token=new; HttpOnly; Max-Age=1800; Path=/; SameSite=lax',
    )

    jest
      .spyOn(global, 'fetch')
      .mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), { status: 200, headers }),
      )
    const { POST } = require('../route')
    const res = await POST(makeRequest('benger.localhost'))
    const cookies = res.headers
      .getSetCookie()
      .filter((c: string) => c.startsWith('access_token='))
    // The clear for this host's legacy domain keeps its Domain and comes
    // first; the one for a foreign domain is dropped; the session is host-only.
    expect(cookies).toHaveLength(2)
    expect(cookies[0]).toContain('Domain=.benger.localhost')
    expect(cookies[0]).toContain('Max-Age=0')
    expect(cookies[1]).toMatch(/^access_token=new;/)
    expect(cookies[1]).not.toContain('Domain=')
  })

  it('handles OK response with cookie missing Path and SameSite (L72-78)', async () => {
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
    const mainCookie = cookies[0]
    expect(mainCookie).toContain('Path=/')
    expect(mainCookie).toContain('SameSite=Lax')
  })

  it('adds no Domain for plain localhost', async () => {
    const headers = new Headers()
    headers.append('Set-Cookie', 'token=val')

    jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers,
      }),
    )
    const { POST } = require('../route')
    const res = await POST(makeRequest('localhost:3000'))
    const cookies = res.headers.getSetCookie()
    // No Domain attribute is ever added
    expect(cookies[0]).not.toContain('Domain=')
  })

  it('handles non-ok response (login failure)', async () => {
    jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Invalid credentials' }), {
        status: 401,
      }),
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
