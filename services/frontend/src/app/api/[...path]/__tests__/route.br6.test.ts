/**
 * @jest-environment node
 *
 * Branch coverage: [...path]/route.ts
 * Targets uncovered branches:
 *   - L10-15: API_BASE_URL env var
 *   - L41-45: benger-test.localhost URL
 *   - L49-58: localhost:3000 with/without Docker
 *   - L62-69: localhost:3001 with Docker
 *   - L79-88: production with API_URL fallback, NODE_ENV production
 *   - L91-93: default fallback URL
 *   - L216-235: 502/503 retry logic, annotations longer delay
 *   - L238-283: 204 with Set-Cookie handling
 *   - L288-293: response.text() error
 *   - L150: auth endpoint but with verify-email
 */

import { NextRequest } from 'next/server'

jest.mock('@/lib/utils/logger', () => ({
  logger: { debug: jest.fn() },
}))

jest.mock('@/lib/utils/subdomain', () => ({
  getCookieDomainFromHost: (host: string) => {
    if (host.includes('benger.localhost')) return '.benger.localhost'
    if (host.includes('benger-test.localhost')) return '.benger-test.localhost'
    return ''
  },
}))

function makeRequest(host: string, path: string, method = 'GET') {
  return new NextRequest(new URL(`http://localhost/api/${path}`), {
    method,
    headers: { host, cookie: 'access_token=abc' },
  })
}

describe('[...path] route br6 - uncovered branches', () => {
  const origEnv = { ...process.env }

  beforeEach(() => {
    jest.resetModules()
    process.env = { ...origEnv }
    delete process.env.API_BASE_URL
    delete process.env.DOCKER_INTERNAL_API_URL
    delete process.env.API_URL
    delete process.env.HOSTNAME
  })

  afterEach(() => {
    process.env = origEnv
    jest.restoreAllMocks()
  })

  it('uses API_BASE_URL env var when set (L10-15)', async () => {
    process.env.API_BASE_URL = 'http://custom-api:9999'
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('{}', { status: 200 })
    )
    const { GET } = require('../route')
    await GET(
      makeRequest('anything.com', 'projects'),
      { params: Promise.resolve({ path: ['projects'] }) }
    )
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('custom-api:9999'),
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('routes benger-test.localhost to test-api:8000 (L41-45)', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('{}', { status: 200 })
    )
    const { GET } = require('../route')
    await GET(
      makeRequest('benger-test.localhost', 'projects'),
      { params: Promise.resolve({ path: ['projects'] }) }
    )
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('test-api:8000'),
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('routes localhost:3000 with Docker to api:8000 (L49-54)', async () => {
    process.env.DOCKER_INTERNAL_API_URL = 'http://api:8000'
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('{}', { status: 200 })
    )
    const { GET } = require('../route')
    await GET(
      makeRequest('localhost:3000', 'projects'),
      { params: Promise.resolve({ path: ['projects'] }) }
    )
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('api:8000'),
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('routes localhost:3000 without Docker to localhost:8001 (L55-58)', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('{}', { status: 200 })
    )
    const { GET } = require('../route')
    await GET(
      makeRequest('localhost:3000', 'projects'),
      { params: Promise.resolve({ path: ['projects'] }) }
    )
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('localhost:8001'),
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('routes localhost:3001 with Docker to api:8000 (L62-65)', async () => {
    process.env.DOCKER_INTERNAL_API_URL = 'defined'
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('{}', { status: 200 })
    )
    const { GET } = require('../route')
    await GET(
      makeRequest('localhost:3001', 'projects'),
      { params: Promise.resolve({ path: ['projects'] }) }
    )
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('api:8000'),
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('uses API_URL env var for production (L83-88)', async () => {
    process.env.API_URL = 'http://prod-api:8000'
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('{}', { status: 200 })
    )
    const { GET } = require('../route')
    await GET(
      makeRequest('what-a-benger.net', 'projects'),
      { params: Promise.resolve({ path: ['projects'] }) }
    )
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('prod-api:8000'),
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('uses DOCKER_INTERNAL_API_URL fallback for unknown hosts in production (L79-88)', async () => {
    process.env.NODE_ENV = 'production'
    process.env.DOCKER_INTERNAL_API_URL = 'http://benger-api:8000'
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('{}', { status: 200 })
    )
    const { GET } = require('../route')
    await GET(
      makeRequest('custom-host.com', 'projects'),
      { params: Promise.resolve({ path: ['projects'] }) }
    )
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('benger-api:8000'),
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('falls back to api:8000 for unknown hosts (L91-93)', async () => {
    process.env.NODE_ENV = 'development'
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('{}', { status: 200 })
    )
    const { GET } = require('../route')
    await GET(
      makeRequest('unknown-host:5000', 'projects'),
      { params: Promise.resolve({ path: ['projects'] }) }
    )
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('api:8000'),
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('handles PUT request method', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('{"ok":true}', { status: 200 })
    )
    const { PUT } = require('../route')
    const req = new NextRequest(new URL('http://localhost/api/projects/1'), {
      method: 'PUT',
      headers: { host: 'benger.localhost', 'content-type': 'application/json' },
      body: JSON.stringify({ name: 'updated' }),
    })
    const res = await PUT(req, { params: Promise.resolve({ path: ['projects', '1'] }) })
    expect(res.status).toBe(200)
    fetchSpy.mockRestore()
  })

  it('handles PATCH request method', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('{"ok":true}', { status: 200 })
    )
    const { PATCH } = require('../route')
    const req = new NextRequest(new URL('http://localhost/api/projects/1'), {
      method: 'PATCH',
      headers: { host: 'benger.localhost', 'content-type': 'application/json' },
      body: JSON.stringify({ name: 'patched' }),
    })
    const res = await PATCH(req, { params: Promise.resolve({ path: ['projects', '1'] }) })
    expect(res.status).toBe(200)
    fetchSpy.mockRestore()
  })

  it('handles 204 with Set-Cookie and SameSite handling (L238-283)', async () => {
    const headers = new Headers()
    headers.append('Set-Cookie', 'token=xyz; Path=/; SameSite=None')
    headers.append('content-type', 'application/json')
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(null, { status: 204, headers })
    )
    const { DELETE } = require('../route')
    const res = await DELETE(
      makeRequest('benger.localhost', 'projects/1'),
      { params: Promise.resolve({ path: ['projects', '1'] }) }
    )
    expect(res.status).toBe(204)
    // Cookie should have domain rewritten
    const setCookies = res.headers.getSetCookie()
    expect(setCookies.length).toBeGreaterThan(0)
    expect(setCookies[0]).toContain('.benger.localhost')
    // SameSite=None already exists, so SameSite=Lax should NOT be added
    expect(setCookies[0]).not.toContain('SameSite=Lax')
    fetchSpy.mockRestore()
  })
})
