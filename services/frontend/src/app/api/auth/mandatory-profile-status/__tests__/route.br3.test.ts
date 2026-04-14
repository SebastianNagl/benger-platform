/**
 * @jest-environment node
 *
 * Branch coverage: mandatory-profile-status/route.ts
 * Targets: getApiBaseUrl branches (API_BASE_URL env, benger-test, benger, localhost:3000,
 *          what-a-benger.net with env vars), error/ok response paths, empty host
 */

import { NextRequest } from 'next/server'

function makeRequest(host: string, url = 'http://localhost/api/auth/mandatory-profile-status') {
  return new NextRequest(new URL(url), {
    headers: { host, cookie: 'token=abc', authorization: 'Bearer xyz' },
  })
}

describe('mandatory-profile-status route', () => {
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
  })

  it('uses API_BASE_URL env var when set', async () => {
    process.env.API_BASE_URL = 'http://custom:9000'
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ complete: true }), { status: 200 })
    )
    const { GET } = require('../route')
    const res = await GET(makeRequest('anything'))
    expect(fetchSpy).toHaveBeenCalledWith(
      'http://custom:9000/api/auth/mandatory-profile-status',
      expect.anything()
    )
    expect(res.status).toBe(200)
    fetchSpy.mockRestore()
  })

  it('routes benger-test.localhost to test-api', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({}), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('benger-test.localhost'))
    expect(fetchSpy).toHaveBeenCalledWith(
      'http://test-api:8000/api/auth/mandatory-profile-status',
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('routes benger.localhost to api:8000', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({}), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('benger.localhost'))
    expect(fetchSpy).toHaveBeenCalledWith(
      'http://api:8000/api/auth/mandatory-profile-status',
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('routes localhost:3000 to localhost:8001', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({}), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('localhost:3000'))
    expect(fetchSpy).toHaveBeenCalledWith(
      'http://localhost:8001/api/auth/mandatory-profile-status',
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('routes what-a-benger.net with DOCKER_INTERNAL_API_URL', async () => {
    process.env.DOCKER_INTERNAL_API_URL = 'http://docker-api:9000'
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({}), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('what-a-benger.net'))
    expect(fetchSpy).toHaveBeenCalledWith(
      'http://docker-api:9000/api/auth/mandatory-profile-status',
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('routes what-a-benger.net with API_URL fallback', async () => {
    process.env.API_URL = 'http://api-url:9000'
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({}), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('what-a-benger.net'))
    expect(fetchSpy).toHaveBeenCalledWith(
      'http://api-url:9000/api/auth/mandatory-profile-status',
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('routes what-a-benger.net with default benger-api:8000', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({}), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('what-a-benger.net'))
    expect(fetchSpy).toHaveBeenCalledWith(
      'http://benger-api:8000/api/auth/mandatory-profile-status',
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('handles non-ok response with error text', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('Forbidden', { status: 403 })
    )
    const { GET } = require('../route')
    const res = await GET(makeRequest('benger.localhost'))
    expect(res.status).toBe(403)
    const json = await res.json()
    expect(json.error).toBe('Forbidden')
    fetchSpy.mockRestore()
  })

  it('handles non-ok response with empty text', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('', { status: 401 })
    )
    const { GET } = require('../route')
    const res = await GET(makeRequest('benger.localhost'))
    expect(res.status).toBe(401)
    const json = await res.json()
    expect(json.error).toBe('Request failed')
    fetchSpy.mockRestore()
  })

  it('handles fetch error with 500', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockRejectedValue(new Error('Network'))
    const { GET } = require('../route')
    const res = await GET(makeRequest('benger.localhost'))
    expect(res.status).toBe(500)
    fetchSpy.mockRestore()
  })

  it('handles empty host header', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({}), { status: 200 })
    )
    const { GET } = require('../route')
    const req = new NextRequest(new URL('http://localhost/api/auth/mandatory-profile-status'))
    await GET(req)
    // Should fall through to default api:8000
    expect(fetchSpy).toHaveBeenCalledWith(
      'http://api:8000/api/auth/mandatory-profile-status',
      expect.anything()
    )
    fetchSpy.mockRestore()
  })
})
