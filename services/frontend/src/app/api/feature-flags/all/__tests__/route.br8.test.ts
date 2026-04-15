/**
 * @jest-environment node
 *
 * Branch coverage: feature-flags/all/route.ts
 * Targets uncovered branches:
 *   - L6: host empty fallback
 *   - L30: searchParams empty ternary
 *   - L39: production NODE_ENV without what-a-benger host
 *   - L40-41: DOCKER_INTERNAL_API_URL || API_URL fallback chain
 */

import { NextRequest } from 'next/server'

jest.mock('@/lib/utils/logger', () => ({
  logger: { debug: jest.fn() },
}))

function makeRequest(host: string, queryString = '') {
  const url = new URL(`http://localhost/api/feature-flags/all${queryString ? `?${queryString}` : ''}`)
  return new NextRequest(url, {
    method: 'GET',
    headers: { host, cookie: 'access_token=abc' },
  })
}

describe('feature-flags/all route br8', () => {
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

  it('includes query params in URL when present (L54 truthy ternary)', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ flags: {} }), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('benger.localhost', 'active=true'))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('?active=true'),
      expect.anything()
    )
  })

  it('omits query string when empty (L54 falsy ternary)', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ flags: {} }), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('benger.localhost'))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.not.stringContaining('?'),
      expect.anything()
    )
  })

  it('routes benger-test.localhost to test-api (L19-20)', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({}), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('benger-test.localhost'))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('test-api:8000'),
      expect.anything()
    )
  })

  it('routes localhost:3000 to localhost:8001 (L30)', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({}), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('localhost:3000'))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('localhost:8001'),
      expect.anything()
    )
  })

  it('routes staging.what-a-benger.net to staging API (L34-35)', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({}), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('staging.what-a-benger.net'))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('benger-api:8000'),
      expect.anything()
    )
  })

  it('uses DOCKER_INTERNAL_API_URL for production (L39-43)', async () => {
    process.env.NODE_ENV = 'production'
    process.env.DOCKER_INTERNAL_API_URL = 'http://my-api:9000'
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({}), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('other-host.com'))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('my-api:9000'),
      expect.anything()
    )
  })

  it('uses API_URL when DOCKER_INTERNAL_API_URL not set (L43 middle fallback)', async () => {
    process.env.NODE_ENV = 'production'
    process.env.API_URL = 'http://alt-api:8080'
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({}), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('what-a-benger.net'))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('alt-api:8080'),
      expect.anything()
    )
  })

  it('handles fetch exception (L68-73)', async () => {
    jest.spyOn(global, 'fetch').mockRejectedValue(new Error('network'))
    jest.spyOn(console, 'error').mockImplementation()
    const { GET } = require('../route')
    const res = await GET(makeRequest('benger.localhost'))
    expect(res.status).toBe(500)
  })
})
