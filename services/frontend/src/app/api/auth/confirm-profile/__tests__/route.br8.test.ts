/**
 * @jest-environment node
 *
 * Branch coverage: confirm-profile/route.ts
 * Targets uncovered branches:
 *   - L4: getApiBaseUrl host empty string fallback
 *   - L6: API_BASE_URL env var
 *   - L14-22: benger-test, benger.localhost, localhost, what-a-benger branches
 *   - L48: error text empty fallback to 'Request failed'
 */

import { NextRequest } from 'next/server'

function makeRequest(host: string) {
  return new NextRequest(new URL('http://localhost/api/auth/confirm-profile'), {
    method: 'POST',
    headers: { host, cookie: 'access_token=abc', authorization: 'Bearer tok' },
  })
}

describe('confirm-profile route br8', () => {
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

  it('uses API_BASE_URL when set (L6)', async () => {
    process.env.API_BASE_URL = 'http://custom:9000'
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 })
    )
    const { POST } = require('../route')
    await POST(makeRequest('anything.com'))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('custom:9000'),
      expect.anything()
    )
  })

  it('routes benger-test.localhost to test-api (L10-11)', async () => {
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

  it('routes benger.localhost to api:8000 (L12-13)', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 })
    )
    const { POST } = require('../route')
    await POST(makeRequest('benger.localhost'))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('api:8000'),
      expect.anything()
    )
  })

  it('routes what-a-benger.net to production API (L16-21)', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 })
    )
    const { POST } = require('../route')
    await POST(makeRequest('what-a-benger.net'))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('benger-api:8000'),
      expect.anything()
    )
  })

  it('handles non-ok response with empty error text (L48 fallback)', async () => {
    jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('', { status: 400 })
    )
    const { POST } = require('../route')
    const res = await POST(makeRequest('benger.localhost'))
    const body = await res.json()
    expect(res.status).toBe(400)
    expect(body.error).toBe('Request failed')
  })

  it('handles non-ok response with error text', async () => {
    jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('Custom error', { status: 422 })
    )
    const { POST } = require('../route')
    const res = await POST(makeRequest('benger.localhost'))
    const body = await res.json()
    expect(res.status).toBe(422)
    expect(body.error).toBe('Custom error')
  })

  it('handles fetch exception (L55-60)', async () => {
    jest.spyOn(global, 'fetch').mockRejectedValue(new Error('network down'))
    jest.spyOn(console, 'error').mockImplementation()
    const { POST } = require('../route')
    const res = await POST(makeRequest('benger.localhost'))
    expect(res.status).toBe(500)
  })
})
