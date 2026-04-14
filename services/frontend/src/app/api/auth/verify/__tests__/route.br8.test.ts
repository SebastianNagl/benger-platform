/**
 * @jest-environment node
 *
 * Branch coverage: verify/route.ts
 * Targets uncovered branches:
 *   - L5: host empty fallback
 *   - L8: API_BASE_URL env var
 *   - L12-25: various host routing branches (benger-test, what-a-benger)
 */

import { NextRequest } from 'next/server'

function makeRequest(host: string) {
  return new NextRequest(new URL('http://localhost/api/auth/verify'), {
    method: 'GET',
    headers: { host, cookie: 'access_token=abc', authorization: 'Bearer tok' },
  })
}

describe('verify route br8', () => {
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

  it('uses API_BASE_URL when set (L8)', async () => {
    process.env.API_BASE_URL = 'http://custom:5555'
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ valid: true }), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('anything'))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('custom:5555'),
      expect.anything()
    )
  })

  it('routes benger-test.localhost (L12)', async () => {
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

  it('routes what-a-benger.net with DOCKER_INTERNAL_API_URL (L18-24)', async () => {
    process.env.DOCKER_INTERNAL_API_URL = 'http://prod-api:9000'
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({}), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('what-a-benger.net'))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('prod-api:9000'),
      expect.anything()
    )
  })

  it('handles non-ok response (L46-51)', async () => {
    jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('Unauthorized', { status: 401 })
    )
    const { GET } = require('../route')
    const res = await GET(makeRequest('benger.localhost'))
    expect(res.status).toBe(401)
    const body = await res.json()
    expect(body.error).toBe('Unauthorized')
  })

  it('handles non-ok response with empty error text (L49 fallback)', async () => {
    jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('', { status: 403 })
    )
    const { GET } = require('../route')
    const res = await GET(makeRequest('benger.localhost'))
    const body = await res.json()
    expect(body.error).toBe('Verification failed')
  })

  it('handles fetch exception (L56-61)', async () => {
    jest.spyOn(global, 'fetch').mockRejectedValue(new Error('fail'))
    jest.spyOn(console, 'error').mockImplementation()
    const { GET } = require('../route')
    const res = await GET(makeRequest('benger.localhost'))
    expect(res.status).toBe(500)
  })
})
