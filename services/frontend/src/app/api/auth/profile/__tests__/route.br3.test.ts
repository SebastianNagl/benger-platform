/**
 * @jest-environment node
 *
 * Branch coverage: auth/profile/route.ts
 * Targets: getApiBaseUrl branches, GET ok/error, PUT ok/error
 */

import { NextRequest } from 'next/server'

function makeGetRequest(host: string) {
  return new NextRequest(new URL('http://localhost/api/auth/profile'), {
    method: 'GET',
    headers: { host, cookie: 'token=abc', authorization: 'Bearer xyz' },
  })
}

function makePutRequest(host: string, body: any) {
  return new NextRequest(new URL('http://localhost/api/auth/profile'), {
    method: 'PUT',
    headers: {
      host,
      cookie: 'token=abc',
      authorization: 'Bearer xyz',
      'content-type': 'application/json',
    },
    body: JSON.stringify(body),
  })
}

describe('auth/profile route', () => {
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

  it('GET uses API_BASE_URL', async () => {
    process.env.API_BASE_URL = 'http://custom:9000'
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ name: 'test' }), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeGetRequest('anything'))
    expect(fetchSpy).toHaveBeenCalledWith(
      'http://custom:9000/api/auth/profile',
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('GET routes benger-test to test-api', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({}), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeGetRequest('benger-test.localhost'))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('test-api'),
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('GET routes localhost:3000 to localhost:8001', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({}), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeGetRequest('localhost:3000'))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('localhost:8001'),
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('GET routes what-a-benger.net with DOCKER_INTERNAL_API_URL', async () => {
    process.env.DOCKER_INTERNAL_API_URL = 'http://docker:9000'
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({}), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeGetRequest('what-a-benger.net'))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('docker:9000'),
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('GET routes what-a-benger.net with API_URL', async () => {
    process.env.API_URL = 'http://api-url:9000'
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({}), { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeGetRequest('what-a-benger.net'))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('api-url:9000'),
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('GET handles non-ok with empty error text', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('', { status: 403 })
    )
    const { GET } = require('../route')
    const res = await GET(makeGetRequest('benger.localhost'))
    expect(res.status).toBe(403)
    const json = await res.json()
    expect(json.error).toBe('Request failed')
    fetchSpy.mockRestore()
  })

  it('GET handles fetch error', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockRejectedValue(new Error('fail'))
    const { GET } = require('../route')
    const res = await GET(makeGetRequest('benger.localhost'))
    expect(res.status).toBe(500)
    fetchSpy.mockRestore()
  })

  it('PUT success path', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ updated: true }), { status: 200 })
    )
    const { PUT } = require('../route')
    const res = await PUT(makePutRequest('benger.localhost', { name: 'new' }))
    expect(res.status).toBe(200)
    fetchSpy.mockRestore()
  })

  it('PUT handles non-ok with empty error text', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('', { status: 400 })
    )
    const { PUT } = require('../route')
    const res = await PUT(makePutRequest('benger.localhost', { name: 'new' }))
    expect(res.status).toBe(400)
    const json = await res.json()
    expect(json.error).toBe('Request failed')
    fetchSpy.mockRestore()
  })

  it('PUT handles fetch error', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockRejectedValue(new Error('fail'))
    const { PUT } = require('../route')
    const res = await PUT(makePutRequest('benger.localhost', { name: 'new' }))
    expect(res.status).toBe(500)
    fetchSpy.mockRestore()
  })
})
