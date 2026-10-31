/**
 * @jest-environment node
 *
 * Branch coverage: refresh/route.ts
 * Targets uncovered branches:
 *   - upstream Domain stripped, legacy-domain clears relayed
 *   - L67: missing Path in cookie
 *   - L77: missing SameSite in cookie
 */

import { NextRequest } from 'next/server'

jest.mock('@/lib/utils/logger', () => ({
  logger: { debug: jest.fn() },
}))

function makeRequest(host: string) {
  return new NextRequest(new URL('http://localhost/api/auth/refresh'), {
    method: 'POST',
    headers: { host, cookie: 'refresh_token=oldtok' },
  })
}

describe('refresh route br8', () => {
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

  it('handles OK response with Set-Cookie, stripping the upstream Domain (L52-85)', async () => {
    const headers = new Headers()
    headers.append(
      'Set-Cookie',
      'access_token=newtok; Domain=old; Secure; HttpOnly',
    )

    jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ refreshed: true }), {
        status: 200,
        headers,
      }),
    )
    const { POST } = require('../route')
    const res = await POST(makeRequest('benger.localhost'))
    const cookies = res.headers.getSetCookie()
    expect(cookies.length).toBeGreaterThan(0)
    expect(cookies[0]).not.toContain('Domain=')
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

  it('handles OK response with cookie missing Path and SameSite (L72, L77)', async () => {
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
    expect(cookies[0]).toContain('Path=/')
    expect(cookies[0]).toContain('SameSite=Lax')
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
    expect(cookies[0]).not.toContain('Domain=')
  })

  it('handles non-ok response', async () => {
    jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Token expired' }), {
        status: 401,
      }),
    )
    const { POST } = require('../route')
    const res = await POST(makeRequest('benger.localhost'))
    expect(res.status).toBe(401)
  })

  it('handles fetch exception (L89-94)', async () => {
    jest.spyOn(global, 'fetch').mockRejectedValue(new Error('fail'))
    jest.spyOn(console, 'error').mockImplementation()
    const { POST } = require('../route')
    const res = await POST(makeRequest('benger.localhost'))
    expect(res.status).toBe(500)
  })
})
