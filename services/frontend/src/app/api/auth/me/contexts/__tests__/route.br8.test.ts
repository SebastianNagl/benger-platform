/**
 * @jest-environment node
 *
 * Branch coverage: me/contexts/route.ts
 * Targets uncovered branches:
 *   - L4: host empty fallback
 *   - L22: non-ok response (backendResponse.ok false)
 */

import { NextRequest } from 'next/server'

function makeRequest(host: string) {
  return new NextRequest(new URL('http://localhost/api/auth/me/contexts'), {
    method: 'GET',
    headers: { host, cookie: 'access_token=abc' },
  })
}

describe('me/contexts route br8', () => {
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

  it('handles non-ok response (L41-45, L22 branch)', async () => {
    jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Unauthorized' }), { status: 401 })
    )
    const { GET } = require('../route')
    const res = await GET(makeRequest('benger.localhost'))
    expect(res.status).toBe(401)
    const body = await res.json()
    expect(body.error).toBe('Unauthorized')
  })

  it('handles OK response', async () => {
    jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ contexts: ['org1'] }), { status: 200 })
    )
    const { GET } = require('../route')
    const res = await GET(makeRequest('benger.localhost'))
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.contexts).toEqual(['org1'])
  })

  it('routes localhost:3000 with Docker hostname (L15-18)', async () => {
    process.env.DOCKER_INTERNAL_API_URL = 'http://api:8000'
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({}), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('localhost:3000'))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('api:8000'),
      expect.anything()
    )
  })

  it('routes localhost:3000 without Docker (L18 else)', async () => {
    delete process.env.HOSTNAME
    delete process.env.DOCKER_INTERNAL_API_URL
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

  it('routes staging.what-a-benger.net (L19-21)', async () => {
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

  it('handles fetch exception (L50-56)', async () => {
    jest.spyOn(global, 'fetch').mockRejectedValue(new Error('network'))
    jest.spyOn(console, 'error').mockImplementation()
    const { GET } = require('../route')
    const res = await GET(makeRequest('benger.localhost'))
    expect(res.status).toBe(500)
  })
})
