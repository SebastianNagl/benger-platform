/**
 * @jest-environment node
 *
 * Branch coverage: verify-email/route.ts
 * Targets uncovered branches:
 *   - L7: host empty fallback
 *   - L20: benger-test.localhost branch
 *   - L78: cookieDomain truthy check
 *   - L80: Set-Cookie domain append
 *   - L85: SameSite missing check
 */

import { NextRequest } from 'next/server'

jest.mock('@/lib/utils/logger', () => ({
  logger: { debug: jest.fn() },
}))

jest.mock('@/lib/utils/subdomain', () => ({
  getCookieDomainFromHost: (host: string) => {
    if (host.includes('benger.localhost')) return '.benger.localhost'
    if (host.includes('what-a-benger.net')) return '.what-a-benger.net'
    return ''
  },
}))

function makeRequest(host: string) {
  return new NextRequest(new URL('http://localhost/api/auth/verify-email'), {
    method: 'POST',
    headers: { host, 'Content-Type': 'application/json' },
    body: JSON.stringify({ token: 'abc123' }),
  })
}

describe('verify-email route br8', () => {
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

  it('routes benger-test.localhost to test-api (L20-22)', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 })
    )
    const { POST } = require('../route')
    await POST(makeRequest('benger-test.localhost'))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('test-api:8000'),
      expect.anything()
    )
  })

  it('handles response with Set-Cookie, domain rewrite and SameSite (L72-95)', async () => {
    const headers = new Headers()
    headers.append('Set-Cookie', 'access_token=xyz; Domain=old.domain; HttpOnly')

    jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ verified: true }), {
        status: 200,
        headers,
      })
    )
    const { POST } = require('../route')
    const res = await POST(makeRequest('benger.localhost'))
    const cookies = res.headers.getSetCookie()
    expect(cookies.length).toBeGreaterThan(0)
    expect(cookies[0]).toContain('.benger.localhost')
    expect(cookies[0]).toContain('SameSite=Lax')
  })

  it('handles response with Set-Cookie that already has SameSite (L85 skip)', async () => {
    const headers = new Headers()
    headers.append('Set-Cookie', 'token=val; SameSite=Strict; HttpOnly')

    jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers,
      })
    )
    const { POST } = require('../route')
    const res = await POST(makeRequest('benger.localhost'))
    const cookies = res.headers.getSetCookie()
    // Should not add a second SameSite
    const sameSiteCount = (cookies[0].match(/SameSite/g) || []).length
    expect(sameSiteCount).toBe(1)
  })

  it('handles response without Set-Cookie headers (L72 empty)', async () => {
    jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 })
    )
    const { POST } = require('../route')
    const res = await POST(makeRequest('benger.localhost'))
    expect(res.status).toBe(200)
  })

  it('handles empty cookieDomain (L80 falsy, no domain added)', async () => {
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
    // No domain should be appended for plain localhost
    expect(cookies[0]).not.toContain('Domain=')
  })

  it('handles staging what-a-benger.net (L30-31)', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 })
    )
    const { POST } = require('../route')
    await POST(makeRequest('staging.what-a-benger.net'))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('benger-api:8000'),
      expect.anything()
    )
  })

  it('handles fetch exception (L99-104)', async () => {
    jest.spyOn(global, 'fetch').mockRejectedValue(new Error('fail'))
    jest.spyOn(console, 'error').mockImplementation()
    const { POST } = require('../route')
    const res = await POST(makeRequest('benger.localhost'))
    expect(res.status).toBe(500)
  })
})
