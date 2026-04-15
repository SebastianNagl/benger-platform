/**
 * @jest-environment node
 *
 * Branch coverage: change-password/route.ts
 * Targets uncovered branches:
 *   - L5: host empty fallback
 *   - L8: API_BASE_URL env var
 *   - L12-25: various host routing branches (benger-test, what-a-benger)
 */

import { NextRequest } from 'next/server'

function makeRequest(host: string) {
  return new NextRequest(new URL('http://localhost/api/auth/change-password'), {
    method: 'POST',
    headers: { host, 'Content-Type': 'application/json', cookie: 'access_token=abc', authorization: 'Bearer tok' },
    body: JSON.stringify({ old_password: 'old', new_password: 'new' }),
  })
}

describe('change-password route br8', () => {
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

  it('uses API_BASE_URL when set (L8)', async () => {
    process.env.API_BASE_URL = 'http://custom:7777'
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 })
    )
    const { POST } = require('../route')
    await POST(makeRequest('anything'))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('custom:7777'),
      expect.anything()
    )
  })

  it('routes benger-test.localhost (L12)', async () => {
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

  it('routes what-a-benger.net to production (L18-24)', async () => {
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

  it('handles non-ok response with error text (L52-57)', async () => {
    jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('Bad password', { status: 400 })
    )
    const { POST } = require('../route')
    const res = await POST(makeRequest('benger.localhost'))
    expect(res.status).toBe(400)
    const body = await res.json()
    expect(body.error).toBe('Bad password')
  })

  it('handles non-ok response with empty error text (L55 fallback)', async () => {
    jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('', { status: 401 })
    )
    const { POST } = require('../route')
    const res = await POST(makeRequest('benger.localhost'))
    const body = await res.json()
    expect(body.error).toBe('Password change failed')
  })

  it('handles fetch exception (L62-68)', async () => {
    jest.spyOn(global, 'fetch').mockRejectedValue(new Error('fail'))
    jest.spyOn(console, 'error').mockImplementation()
    const { POST } = require('../route')
    const res = await POST(makeRequest('benger.localhost'))
    expect(res.status).toBe(500)
  })
})
