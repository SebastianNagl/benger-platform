/**
 * @jest-environment node
 *
 * Branch coverage: verify-email-enhanced/[token]/route.ts
 * Targets: getApiBaseUrl branches, cookie handling, SameSite branch
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
  return new NextRequest(new URL(`http://localhost/api/auth/verify-email-enhanced/test-token-abc`), {
    method: 'POST',
    headers: { host, 'content-type': 'application/json' },
  })
}

describe('verify-email-enhanced route', () => {
  const origEnv = { ...process.env }

  beforeEach(() => {
    jest.resetModules()
    process.env = { ...origEnv }
    delete process.env.API_BASE_URL
  })

  afterEach(() => {
    process.env = origEnv
  })

  it('routes localhost:3000 to localhost:8001', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ success: true }), {
        status: 200,
        headers: {},
      })
    )
    const { POST } = require('../route')
    await POST(makeRequest('localhost:3000'), { params: Promise.resolve({ token: 'abc' }) })
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('http://localhost:8001'),
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('routes benger-test.localhost to test-api', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ success: true }), { status: 200 })
    )
    const { POST } = require('../route')
    await POST(makeRequest('benger-test.localhost'), { params: Promise.resolve({ token: 'abc' }) })
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('http://test-api:8000'),
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('routes staging.what-a-benger.net', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ success: true }), { status: 200 })
    )
    const { POST } = require('../route')
    await POST(makeRequest('staging.what-a-benger.net'), { params: Promise.resolve({ token: 'abc' }) })
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('benger-api'),
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('routes what-a-benger.net with API_BASE_URL', async () => {
    process.env.API_BASE_URL = 'http://custom:9000'
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ success: true }), { status: 200 })
    )
    const { POST } = require('../route')
    await POST(makeRequest('what-a-benger.net'), { params: Promise.resolve({ token: 'abc' }) })
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('http://custom:9000'),
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('handles Set-Cookie with domain and SameSite', async () => {
    const headers = new Headers()
    headers.append('Set-Cookie', 'access_token=xyz; Path=/; Domain=old.test')
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ success: true }), { status: 200, headers })
    )
    const { POST } = require('../route')
    const res = await POST(makeRequest('benger.localhost'), { params: Promise.resolve({ token: 'abc' }) })
    expect(res.status).toBe(200)
    // Should have Set-Cookie header with modified domain
    const setCookies = res.headers.getSetCookie()
    expect(setCookies.length).toBeGreaterThan(0)
    fetchSpy.mockRestore()
  })

  it('handles Set-Cookie that already has SameSite', async () => {
    const headers = new Headers()
    headers.append('Set-Cookie', 'token=xyz; SameSite=Strict; Path=/')
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ success: true }), { status: 200, headers })
    )
    const { POST } = require('../route')
    const res = await POST(makeRequest('benger.localhost'), { params: Promise.resolve({ token: 'abc' }) })
    expect(res.status).toBe(200)
    fetchSpy.mockRestore()
  })

  it('handles no Set-Cookie headers', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ success: true }), { status: 200 })
    )
    const { POST } = require('../route')
    const res = await POST(makeRequest('benger.localhost'), { params: Promise.resolve({ token: 'abc' }) })
    expect(res.status).toBe(200)
    fetchSpy.mockRestore()
  })

  it('handles cookie domain for localhost (empty domain)', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ success: true }), { status: 200 })
    )
    const { POST } = require('../route')
    const req = new NextRequest(new URL('http://localhost/api/auth/verify-email-enhanced/tok'), {
      method: 'POST',
      headers: { host: 'localhost:3000' },
    })
    const res = await POST(req, { params: Promise.resolve({ token: 'tok' }) })
    expect(res.status).toBe(200)
    fetchSpy.mockRestore()
  })

  it('handles fetch error', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockRejectedValue(new Error('fail'))
    const { POST } = require('../route')
    const res = await POST(makeRequest('benger.localhost'), { params: Promise.resolve({ token: 'abc' }) })
    expect(res.status).toBe(500)
    fetchSpy.mockRestore()
  })
})
