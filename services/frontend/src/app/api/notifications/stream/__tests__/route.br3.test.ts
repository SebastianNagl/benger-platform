/**
 * @jest-environment node
 *
 * Branch coverage: notifications/stream/route.ts
 * Targets: token refresh path, staging detection, auth header, user-agent, referer,
 *          error handling
 */

import { NextRequest } from 'next/server'

function makeRequest(host: string, opts: { cookie?: string; auth?: string; ua?: string; referer?: string } = {}) {
  const headers: Record<string, string> = { host }
  if (opts.cookie) headers.cookie = opts.cookie
  if (opts.auth) headers.authorization = opts.auth
  if (opts.ua) headers['user-agent'] = opts.ua
  if (opts.referer) headers.referer = opts.referer
  return new NextRequest(new URL('http://localhost/api/notifications/stream'), { headers })
}

describe('notifications/stream route', () => {
  const origEnv = { ...process.env }

  beforeEach(() => {
    jest.resetModules()
    process.env = { ...origEnv }
    delete process.env.API_URL
  })

  afterEach(() => {
    process.env = origEnv
    jest.restoreAllMocks()
  })

  it('uses api:8000 for benger.localhost', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('data: test\n\n', {
        status: 200,
        headers: { 'content-type': 'text/event-stream' },
      })
    )
    const { GET } = require('../route')
    const res = await GET(makeRequest('benger.localhost', {
      cookie: 'access_token=abc',
      auth: 'Bearer token',
      ua: 'TestAgent',
      referer: 'http://test.com',
    }))
    expect(res).toBeTruthy()
    fetchSpy.mockRestore()
  })

  it('routes staging to staging API', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('data: test\n\n', { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('staging.what-a-benger.net', { cookie: 'access_token=abc' }))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('benger-api'),
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('routes what-a-benger.net with API_URL', async () => {
    process.env.API_URL = 'http://custom:9000'
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('data: test\n\n', { status: 200 })
    )
    const { GET } = require('../route')
    await GET(makeRequest('what-a-benger.net', { cookie: 'access_token=abc' }))
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('custom:9000'),
      expect.anything()
    )
    fetchSpy.mockRestore()
  })

  it('attempts token refresh when no access_token but has refresh_token', async () => {
    const refreshResponse = new Response('{}', {
      status: 200,
      headers: new Headers(),
    })
    // First call = refresh, second call = backend stream
    const fetchSpy = jest.spyOn(global, 'fetch')
      .mockResolvedValueOnce(refreshResponse)
      .mockResolvedValueOnce(
        new Response('data: test\n\n', { status: 200 })
      )
    const { GET } = require('../route')
    await GET(makeRequest('benger.localhost', { cookie: 'refresh_token=xyz' }))
    // Should have called refresh endpoint
    expect(fetchSpy).toHaveBeenCalledTimes(2)
    fetchSpy.mockRestore()
  })

  it('handles refresh with new access_token cookie', async () => {
    const refreshHeaders = new Headers()
    refreshHeaders.append('Set-Cookie', 'access_token=new_token; Path=/')
    const refreshResponse = new Response('{}', {
      status: 200,
      headers: refreshHeaders,
    })
    const fetchSpy = jest.spyOn(global, 'fetch')
      .mockResolvedValueOnce(refreshResponse)
      .mockResolvedValueOnce(
        new Response('data: ok\n\n', { status: 200 })
      )
    const { GET } = require('../route')
    await GET(makeRequest('benger.localhost', { cookie: 'refresh_token=xyz' }))
    expect(fetchSpy).toHaveBeenCalledTimes(2)
    fetchSpy.mockRestore()
  })

  it('handles refresh failure', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch')
      .mockResolvedValueOnce(new Response('', { status: 401 })) // refresh fails
      .mockResolvedValueOnce(
        new Response('data: ok\n\n', { status: 200 })
      )
    const { GET } = require('../route')
    const res = await GET(makeRequest('benger.localhost', { cookie: 'refresh_token=xyz' }))
    expect(res).toBeTruthy()
    fetchSpy.mockRestore()
  })

  it('handles fetch error with SSE error response', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockRejectedValue(new Error('Network'))
    const { GET } = require('../route')
    const res = await GET(makeRequest('benger.localhost', { cookie: 'access_token=abc' }))
    // Should return an SSE error response
    expect(res).toBeTruthy()
    fetchSpy.mockRestore()
  })

  it('handles no cookies', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue(
      new Response('data: ok\n\n', { status: 200 })
    )
    const { GET } = require('../route')
    const req = new NextRequest(new URL('http://localhost/api/notifications/stream'), {
      headers: { host: 'benger.localhost' },
    })
    const res = await GET(req)
    expect(res).toBeTruthy()
    fetchSpy.mockRestore()
  })
})

describe('notifications/stream route — reader-loop error classification', () => {
  const origEnv = { ...process.env }

  beforeEach(() => {
    jest.resetModules()
    process.env = { ...origEnv }
  })
  afterEach(() => {
    process.env = origEnv
    jest.restoreAllMocks()
  })

  /** Backend response whose body stream rejects with `err` on first read. */
  function streamingResponseThatFails(err: unknown) {
    return {
      ok: true,
      body: {
        getReader: () => ({
          read: () => Promise.reject(err),
        }),
      },
    } as unknown as Response
  }

  async function drain(res: Response) {
    const reader = res.body!.getReader()
    // eslint-disable-next-line no-constant-condition
    while (true) {
      const { done } = await reader.read()
      if (done) break
    }
  }

  it('does not log an idle-body timeout — EventSource just reconnects', async () => {
    const timeout = Object.assign(new TypeError('terminated'), {
      cause: { code: 'UND_ERR_BODY_TIMEOUT' },
    })
    jest.spyOn(global, 'fetch').mockResolvedValue(streamingResponseThatFails(timeout))
    const errSpy = jest.spyOn(console, 'error').mockImplementation(() => {})

    const { GET } = await import('../route')
    await drain(await GET(makeRequest('benger.localhost')))

    expect(errSpy).not.toHaveBeenCalledWith('SSE stream error:', timeout)
  })

  it('still logs a genuine stream failure', async () => {
    const boom = new Error('backend exploded')
    jest.spyOn(global, 'fetch').mockResolvedValue(streamingResponseThatFails(boom))
    const errSpy = jest.spyOn(console, 'error').mockImplementation(() => {})

    const { GET } = await import('../route')
    await drain(await GET(makeRequest('benger.localhost')))

    expect(errSpy).toHaveBeenCalledWith('SSE stream error:', boom)
  })
})
