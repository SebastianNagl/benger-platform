/**
 * @jest-environment node
 *
 * Branch coverage: [...path]/route.ts
 * Targets: auth endpoint check, 502/503 retry, annotations longer delay,
 *          204 No Content, Set-Cookie handling, staging detection,
 *          localhost:3001, body parsing error, response text error
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

function makeRequest(host: string, path: string, method = 'GET') {
  return new NextRequest(new URL(`http://localhost/api/${path}`), {
    method,
    headers: { host, cookie: 'access_token=abc' },
  })
}

describe('[...path] route branch coverage', () => {
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

  it('rejects auth endpoints (not verify-email)', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('{}', { status: 200 })
    )
    const { GET } = require('../route')
    const res = await GET(
      makeRequest('benger.localhost', 'auth/login'),
      { params: Promise.resolve({ path: ['auth', 'login'] }) }
    )
    expect(res.status).toBe(400)
    fetchSpy.mockRestore()
  })

  it('allows auth/verify-email endpoints', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('{}', { status: 200 })
    )
    const { GET } = require('../route')
    const res = await GET(
      makeRequest('benger.localhost', 'auth/verify-email/token123'),
      { params: Promise.resolve({ path: ['auth', 'verify-email', 'token123'] }) }
    )
    expect(res.status).toBe(200)
    fetchSpy.mockRestore()
  })

  it('handles 204 No Content response', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(null, { status: 204 })
    )
    const { DELETE } = require('../route')
    const res = await DELETE(
      makeRequest('benger.localhost', 'projects/1'),
      { params: Promise.resolve({ path: ['projects', '1'] }) }
    )
    expect(res.status).toBe(204)
    fetchSpy.mockRestore()
  })

  it('forwards Set-Cookie with domain rewriting', async () => {
    const headers = new Headers()
    headers.append('Set-Cookie', 'token=xyz; Domain=old.test; Path=/')
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('{"ok":true}', { status: 200, headers })
    )
    const { GET } = require('../route')
    const res = await GET(
      makeRequest('benger.localhost', 'projects'),
      { params: Promise.resolve({ path: ['projects'] }) }
    )
    const setCookies = res.headers.getSetCookie()
    expect(setCookies.length).toBeGreaterThan(0)
    expect(setCookies[0]).toContain('.benger.localhost')
    fetchSpy.mockRestore()
  })

  it('adds SameSite=Lax when not present', async () => {
    const headers = new Headers()
    headers.append('Set-Cookie', 'token=xyz; Path=/')
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('{"ok":true}', { status: 200, headers })
    )
    const { GET } = require('../route')
    const res = await GET(
      makeRequest('benger.localhost', 'projects'),
      { params: Promise.resolve({ path: ['projects'] }) }
    )
    const setCookies = res.headers.getSetCookie()
    expect(setCookies[0]).toContain('SameSite=Lax')
    fetchSpy.mockRestore()
  })

  it('routes staging.what-a-benger.net', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('{}', { status: 200 })
    )
    const { GET } = require('../route')
    await GET(
      makeRequest('staging.what-a-benger.net', 'projects'),
      { params: Promise.resolve({ path: ['projects'] }) }
    )
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('benger-api'),
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('routes localhost:3001', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('{}', { status: 200 })
    )
    const { GET } = require('../route')
    await GET(
      makeRequest('localhost:3001', 'projects'),
      { params: Promise.resolve({ path: ['projects'] }) }
    )
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('localhost:8001'),
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('POST forwards body', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('{"created":true}', { status: 201 })
    )
    const { POST } = require('../route')
    const req = new NextRequest(new URL('http://localhost/api/projects'), {
      method: 'POST',
      headers: {
        host: 'benger.localhost',
        'content-type': 'application/json',
        cookie: 'token=abc',
      },
      body: JSON.stringify({ name: 'test' }),
    })
    const res = await POST(req, { params: Promise.resolve({ path: ['projects'] }) })
    expect(res.status).toBe(201)
    fetchSpy.mockRestore()
  })

  it('handles fetch error with 500', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockRejectedValue(new Error('Network'))
    const { GET } = require('../route')
    const res = await GET(
      makeRequest('benger.localhost', 'projects'),
      { params: Promise.resolve({ path: ['projects'] }) }
    )
    expect(res.status).toBe(500)
    fetchSpy.mockRestore()
  })

  it('uses production URL with DOCKER_INTERNAL_API_URL', async () => {
    process.env.DOCKER_INTERNAL_API_URL = 'http://docker-api:9000'
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('{}', { status: 200 })
    )
    const { GET } = require('../route')
    await GET(
      makeRequest('what-a-benger.net', 'projects'),
      { params: Promise.resolve({ path: ['projects'] }) }
    )
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('docker-api:9000'),
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('includes query params in forwarded URL', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('{}', { status: 200 })
    )
    const { GET } = require('../route')
    const req = new NextRequest(
      new URL('http://localhost/api/projects?page=1&limit=10'),
      { headers: { host: 'benger.localhost' } }
    )
    await GET(req, { params: Promise.resolve({ path: ['projects'] }) })
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('page=1&limit=10'),
      expect.anything()
    )
    fetchSpy.mockRestore()
  })
})
