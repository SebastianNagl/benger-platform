/**
 * @jest-environment node
 *
 * Branch coverage: logout/route.ts
 * Targets uncovered branches:
 *   - L10: API_BASE_URL env var
 *   - L14-25: host routing branches (benger-test, staging, what-a-benger)
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
  return new NextRequest(new URL('http://localhost/api/auth/logout'), {
    method: 'POST',
    headers: { host, cookie: 'access_token=abc; refresh_token=xyz' },
  })
}

describe('logout route br8', () => {
  const origEnv = { ...process.env }

  beforeEach(() => {
    jest.resetModules()
    process.env = { ...origEnv }
    delete process.env.API_BASE_URL
    delete process.env.DOCKER_INTERNAL_API_URL
    delete process.env.API_URL
  })

  afterEach(() => {
    process.env = origEnv
    jest.restoreAllMocks()
  })

  it('uses API_BASE_URL when set (L10)', async () => {
    process.env.API_BASE_URL = 'http://custom:8888'
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(null, { status: 204 })
    )
    const { POST } = require('../route')
    await POST(makeRequest('anything'))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('custom:8888'),
      expect.anything()
    )
  })

  it('routes benger-test.localhost (L14-15)', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(null, { status: 204 })
    )
    const { POST } = require('../route')
    await POST(makeRequest('benger-test.localhost'))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('test-api:8000'),
      expect.anything()
    )
  })

  it('routes staging.what-a-benger.net to staging API (L20-22)', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(null, { status: 204 })
    )
    const { POST } = require('../route')
    await POST(makeRequest('staging.what-a-benger.net'))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('benger-api:8000'),
      expect.anything()
    )
  })

  it('clears cookies with domain attribute (L49-60)', async () => {
    jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(null, { status: 204 })
    )
    const { POST } = require('../route')
    const res = await POST(makeRequest('benger.localhost'))
    expect(res.status).toBe(204)
    const cookies = res.headers.getSetCookie()
    expect(cookies.length).toBe(2)
    expect(cookies[0]).toContain('access_token=')
    expect(cookies[0]).toContain('Max-Age=0')
    expect(cookies[0]).toContain('.benger.localhost')
    expect(cookies[1]).toContain('refresh_token=')
    expect(cookies[1]).toContain('Max-Age=0')
  })

  it('clears cookies without domain for localhost (L52 empty domain)', async () => {
    jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(null, { status: 204 })
    )
    const { POST } = require('../route')
    const res = await POST(makeRequest('localhost:3000'))
    const cookies = res.headers.getSetCookie()
    expect(cookies[0]).not.toContain('Domain=')
  })

  it('handles fetch exception (L65-70)', async () => {
    jest.spyOn(global, 'fetch').mockRejectedValue(new Error('fail'))
    jest.spyOn(console, 'error').mockImplementation()
    const { POST } = require('../route')
    const res = await POST(makeRequest('benger.localhost'))
    expect(res.status).toBe(500)
  })
})
