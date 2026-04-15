/**
 * @jest-environment node
 *
 * Branch coverage: auth/me/route.ts
 * Targets: API_BASE_URL env, benger-test, localhost:3000 isInDocker,
 *          staging.what-a-benger.net, what-a-benger.net, error paths
 */

import { NextRequest } from 'next/server'

function makeRequest(host: string) {
  return new NextRequest(new URL('http://localhost/api/auth/me'), {
    headers: { host, cookie: 'access_token=abc' },
  })
}

describe('auth/me route', () => {
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
  })

  it('uses API_BASE_URL', async () => {
    process.env.API_BASE_URL = 'http://custom:9000'
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ id: 1 }), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('anything'))
    expect(fetchSpy).toHaveBeenCalledWith(
      'http://custom:9000/api/auth/me',
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('routes benger-test.localhost to test-api', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ id: 1 }), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('benger-test.localhost'))
    expect(fetchSpy).toHaveBeenCalledWith(
      'http://test-api:8000/api/auth/me',
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('routes localhost:3000 to api:8000 when HOSTNAME starts with frontend', async () => {
    process.env.DOCKER_INTERNAL_API_URL = 'http://api:8000'
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ id: 1 }), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('localhost:3000'))
    expect(fetchSpy).toHaveBeenCalledWith(
      'http://api:8000/api/auth/me',
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('routes localhost:3000 to localhost:8001 when not in Docker', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ id: 1 }), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('localhost:3000'))
    expect(fetchSpy).toHaveBeenCalledWith(
      'http://localhost:8001/api/auth/me',
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('routes staging.what-a-benger.net to staging API', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ id: 1 }), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('staging.what-a-benger.net'))
    expect(fetchSpy).toHaveBeenCalledWith(
      'http://benger-api:8000/api/auth/me',
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('routes what-a-benger.net with env vars', async () => {
    process.env.DOCKER_INTERNAL_API_URL = 'http://docker:9000'
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ id: 1 }), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('what-a-benger.net'))
    expect(fetchSpy).toHaveBeenCalledWith(
      'http://docker:9000/api/auth/me',
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('routes what-a-benger.net with API_URL fallback', async () => {
    process.env.API_URL = 'http://api-url:9000'
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ id: 1 }), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('what-a-benger.net'))
    expect(fetchSpy).toHaveBeenCalledWith(
      'http://api-url:9000/api/auth/me',
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('handles non-ok response', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('Unauthorized', { status: 401 })
    )
    const { GET } = require('../route')
    const res = await GET(makeRequest('benger.localhost'))
    expect(res.status).toBe(401)
    fetchSpy.mockRestore()
  })

  it('handles fetch error', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockRejectedValue(new Error('fail'))
    const { GET } = require('../route')
    const res = await GET(makeRequest('benger.localhost'))
    expect(res.status).toBe(500)
    fetchSpy.mockRestore()
  })
})
