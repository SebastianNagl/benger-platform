/**
 * @jest-environment node
 *
 * Branch coverage: profile-history/route.ts
 * Targets: all getApiBaseUrl branches, queryString branch, error responses
 */

import { NextRequest } from 'next/server'

function makeRequest(host: string, qs = '') {
  const url = `http://localhost/api/auth/profile-history${qs ? '?' + qs : ''}`
  return new NextRequest(new URL(url), {
    headers: { host, cookie: 'token=abc', authorization: 'Bearer xyz' },
  })
}

describe('profile-history route', () => {
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

  it('uses API_BASE_URL when set', async () => {
    process.env.API_BASE_URL = 'http://custom:9000'
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('anything'))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('http://custom:9000'),
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('routes benger-test to test-api', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('benger-test.localhost'))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('http://test-api:8000'),
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('routes benger.localhost to api', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('benger.localhost'))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('http://api:8000'),
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('routes localhost:3000 to localhost:8001', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('localhost:3000'))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('http://localhost:8001'),
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('routes what-a-benger.net with DOCKER_INTERNAL_API_URL', async () => {
    process.env.DOCKER_INTERNAL_API_URL = 'http://docker:9000'
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('what-a-benger.net'))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('http://docker:9000'),
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('routes what-a-benger.net with API_URL', async () => {
    process.env.API_URL = 'http://api-url:9000'
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('what-a-benger.net'))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('http://api-url:9000'),
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('routes what-a-benger.net default fallback', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('what-a-benger.net'))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('http://benger-api:8000'),
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('appends query string when present', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('benger.localhost', 'page=1&limit=10'))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('?page=1&limit=10'),
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('handles non-ok response', async () => {
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

  it('handles fetch error', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockRejectedValue(new Error('fail'))
    const { GET } = require('../route')
    const res = await GET(makeRequest('benger.localhost'))
    expect(res.status).toBe(500)
    fetchSpy.mockRestore()
  })
})
