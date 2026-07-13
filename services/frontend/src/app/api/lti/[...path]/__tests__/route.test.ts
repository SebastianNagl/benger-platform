/**
 * @jest-environment node
 *
 * Tests for the dedicated LTI proxy route (/api/lti/*).
 *
 * The route exists because the generic catch-all proxy follows redirects
 * server-side; LTI is redirect-driven (OIDC login init 302s to Moodle, the
 * launch 303s into the app with Set-Cookie), so this proxy must use
 * redirect: 'manual' and pass 3xx responses through verbatim. These tests
 * pin that contract with global.fetch mocked.
 */

import { NextRequest } from 'next/server'
import { GET, POST } from '../route'

jest.mock('@/lib/utils/logger', () => ({
  logger: {
    debug: jest.fn(),
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}))

global.fetch = jest.fn()
const mockFetch = global.fetch as jest.MockedFunction<typeof fetch>

/** Build upstream response headers (jest.setup's Headers supports getSetCookie). */
function upstreamHeaders(
  entries: Record<string, string> = {},
  cookies: string[] = []
): Headers {
  const headers = new Headers(entries)
  cookies.forEach((cookie) => headers.append('Set-Cookie', cookie))
  return headers
}

/** Minimal upstream fetch-response double covering what the route touches. */
function upstreamResponse(
  status: number,
  opts: { headers?: Headers; body?: string } = {}
): Response {
  return {
    status,
    statusText: '',
    headers: opts.headers ?? new Headers(),
    arrayBuffer: async () =>
      new TextEncoder().encode(opts.body ?? '').buffer as ArrayBuffer,
  } as unknown as Response
}

/**
 * Build a NextRequest for the route. jest.setup.js replaces the global
 * Request with a minimal mock that lacks Body methods, so arrayBuffer()
 * (which the route uses to buffer non-GET bodies) is patched per instance.
 */
function ltiRequest(
  url: string,
  init: {
    method?: string
    headers?: Record<string, string>
    body?: string
  } = {}
): NextRequest {
  const request = new NextRequest(url, {
    method: init.method ?? 'GET',
    headers: init.headers ?? {},
    ...(init.body !== undefined ? { body: init.body } : {}),
  } as ConstructorParameters<typeof NextRequest>[1])
  ;(request as unknown as { arrayBuffer: () => Promise<ArrayBuffer> }).arrayBuffer =
    async () => new TextEncoder().encode(init.body ?? '').buffer as ArrayBuffer
  return request
}

/** Decode a NextResponse body (the jest.setup Response mock stores it raw). */
function responseBody(response: unknown): string {
  const body = (response as { body?: unknown }).body
  if (body == null) return ''
  if (typeof body === 'string') return body
  return Buffer.from(body as ArrayBuffer).toString('utf8')
}

describe('LTI proxy route (/api/lti/[...path])', () => {
  const origEnv = { ...process.env }

  beforeEach(() => {
    mockFetch.mockReset()
    process.env = { ...origEnv }
    // Make host-based API resolution deterministic (benger.localhost -> api:8000).
    delete process.env.INTERNAL_API_URL
    delete process.env.API_BASE_URL
    delete process.env.DOCKER_INTERNAL_API_URL
  })

  afterEach(() => {
    process.env = origEnv
  })

  describe('redirect passthrough', () => {
    it('passes an upstream 303 through verbatim instead of following it', async () => {
      const location = 'http://benger.localhost/lti/link?launch_id=L1'
      mockFetch.mockResolvedValueOnce(
        upstreamResponse(303, {
          headers: upstreamHeaders({ location }),
        })
      )

      const response = await POST(
        ltiRequest('http://benger.localhost/api/lti/launch', {
          method: 'POST',
          headers: { host: 'benger.localhost' },
          body: 'id_token=abc&state=xyz',
        })
      )

      expect(mockFetch).toHaveBeenCalledTimes(1)
      expect(mockFetch).toHaveBeenCalledWith(
        'http://api:8000/api/lti/launch',
        expect.objectContaining({ redirect: 'manual', method: 'POST' })
      )
      expect(response.status).toBe(303)
      expect(response.headers.get('location')).toBe(location)
      // 3xx responses must not carry a body.
      expect(responseBody(response)).toBe('')
    })

    it('does not read the upstream body of a 3xx response', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 303,
        statusText: '',
        headers: upstreamHeaders({ location: 'http://benger.localhost/lti/consent' }),
        arrayBuffer: async () => {
          throw new Error('3xx body must not be consumed by the proxy')
        },
      } as unknown as Response)

      const response = await GET(
        ltiRequest('http://benger.localhost/api/lti/launch', {
          headers: { host: 'benger.localhost' },
        })
      )

      expect(response.status).toBe(303)
    })

    it('proxies the OIDC login init with its query string and passes the 302 through', async () => {
      const moodleAuth =
        'https://moodle.example/mod/lti/auth.php?scope=openid&state=s1'
      mockFetch.mockResolvedValueOnce(
        upstreamResponse(302, {
          headers: upstreamHeaders({ location: moodleAuth }),
        })
      )

      const response = await GET(
        ltiRequest(
          'http://benger.localhost/api/lti/login?iss=https%3A%2F%2Fmoodle.example&login_hint=42',
          { headers: { host: 'benger.localhost' } }
        )
      )

      expect(mockFetch).toHaveBeenCalledWith(
        'http://api:8000/api/lti/login?iss=https%3A%2F%2Fmoodle.example&login_hint=42',
        expect.objectContaining({ redirect: 'manual' })
      )
      expect(response.status).toBe(302)
      expect(response.headers.get('location')).toBe(moodleAuth)
    })
  })

  describe('Set-Cookie rewriting', () => {
    it('re-scopes Domain to the requesting host, strips Secure outside production, preserves SameSite', async () => {
      mockFetch.mockResolvedValueOnce(
        upstreamResponse(303, {
          headers: upstreamHeaders(
            { location: 'http://benger.localhost/student' },
            [
              'access_token=x; Domain=api.internal; Path=/; HttpOnly; SameSite=Lax; Secure',
            ]
          ),
        })
      )

      const response = await POST(
        ltiRequest('http://benger.localhost/api/lti/launch', {
          method: 'POST',
          headers: { host: 'benger.localhost' },
          body: 'id_token=abc',
        })
      )

      const cookies = response.headers.getSetCookie()
      expect(cookies).toHaveLength(1)
      const cookie = cookies[0]
      expect(cookie).toContain('access_token=x')
      // Upstream Domain replaced with the browser-facing cookie domain.
      expect(cookie).not.toContain('api.internal')
      expect(cookie).toContain('Domain=.benger.localhost')
      // NODE_ENV is 'test' here, so Secure must be stripped for plain-HTTP dev.
      expect(cookie).not.toMatch(/Secure/i)
      // The explicit SameSite is preserved, not duplicated.
      expect(cookie.match(/SameSite=/gi)).toHaveLength(1)
      expect(cookie).toContain('SameSite=Lax')
      // Path was already present and is kept as-is, once.
      expect(cookie.match(/Path=/gi)).toHaveLength(1)
      expect(cookie).toContain('Path=/')
      expect(cookie).toContain('HttpOnly')
    })

    it('appends SameSite=Lax and Path=/ when missing and sets no Domain for plain localhost', async () => {
      mockFetch.mockResolvedValueOnce(
        upstreamResponse(200, {
          headers: upstreamHeaders({ 'content-type': 'application/json' }, [
            'lti_state=abc',
          ]),
          body: '{}',
        })
      )

      const response = await GET(
        ltiRequest('http://localhost:3000/api/lti/session', {
          headers: { host: 'localhost:3000' },
        })
      )

      const cookies = response.headers.getSetCookie()
      expect(cookies).toHaveLength(1)
      const cookie = cookies[0]
      expect(cookie).toContain('lti_state=abc')
      expect(cookie).toContain('SameSite=Lax')
      expect(cookie).toContain('Path=/')
      // getCookieDomainFromHost('localhost:3000') is empty: no Domain attribute.
      expect(cookie).not.toContain('Domain=')
    })

    it('keeps Secure in production', async () => {
      process.env.NODE_ENV = 'production'
      mockFetch.mockResolvedValueOnce(
        upstreamResponse(303, {
          headers: upstreamHeaders(
            { location: 'https://what-a-benger.net/student' },
            ['access_token=x; Domain=api.internal; Path=/; HttpOnly; SameSite=Lax; Secure']
          ),
        })
      )

      const response = await POST(
        ltiRequest('https://what-a-benger.net/api/lti/launch', {
          method: 'POST',
          headers: { host: 'what-a-benger.net' },
          body: 'id_token=abc',
        })
      )

      const cookie = response.headers.getSetCookie()[0]
      expect(cookie).toContain('Secure')
      expect(cookie).toContain('Domain=.what-a-benger.net')
    })
  })

  describe('request forwarding', () => {
    it('forwards POST form bodies and headers, sets x-forwarded-host, strips hop-by-hop headers', async () => {
      mockFetch.mockResolvedValueOnce(
        upstreamResponse(302, {
          headers: upstreamHeaders({ location: 'https://moodle.example/auth' }),
        })
      )

      const form = 'iss=https%3A%2F%2Fmoodle.example&login_hint=42'
      await POST(
        ltiRequest('http://frontend-internal:3000/api/lti/login', {
          method: 'POST',
          headers: {
            host: 'frontend-internal:3000',
            'x-forwarded-host': 'benger.localhost',
            'content-type': 'application/x-www-form-urlencoded',
            connection: 'keep-alive',
            'content-length': '999',
            cookie: 'session=1',
          },
          body: form,
        })
      )

      // The external host (x-forwarded-host) drives internal API resolution.
      expect(mockFetch).toHaveBeenCalledWith(
        'http://api:8000/api/lti/login',
        expect.objectContaining({ method: 'POST', redirect: 'manual' })
      )

      const init = mockFetch.mock.calls[0][1]!
      const headers = init.headers as Headers
      // Hop-by-hop request headers are stripped...
      expect(headers.has('host')).toBe(false)
      expect(headers.has('connection')).toBe(false)
      expect(headers.has('content-length')).toBe(false)
      // ...while the payload headers survive.
      expect(headers.get('content-type')).toBe(
        'application/x-www-form-urlencoded'
      )
      expect(headers.get('cookie')).toBe('session=1')
      // The API builds browser-facing URLs from the external host.
      expect(headers.get('x-forwarded-host')).toBe('benger.localhost')
      expect(headers.get('x-forwarded-proto')).toBe('http')
      // The form body reaches fetch byte-identical.
      expect(Buffer.from(init.body as ArrayBuffer).toString('utf8')).toBe(form)
    })

    it('does not attach a body to GET requests', async () => {
      mockFetch.mockResolvedValueOnce(
        upstreamResponse(200, {
          headers: upstreamHeaders({ 'content-type': 'application/json' }),
          body: '{}',
        })
      )

      await GET(
        ltiRequest('http://benger.localhost/api/lti/jwks', {
          headers: { host: 'benger.localhost' },
        })
      )

      const init = mockFetch.mock.calls[0][1]!
      expect(init.body == null).toBe(true)
    })
  })

  describe('upstream failure', () => {
    it('returns 502 JSON when the upstream fetch rejects', async () => {
      mockFetch.mockRejectedValueOnce(new Error('ECONNREFUSED'))

      const response = await POST(
        ltiRequest('http://benger.localhost/api/lti/launch', {
          method: 'POST',
          headers: { host: 'benger.localhost' },
          body: 'id_token=abc',
        })
      )

      expect(response.status).toBe(502)
      const data = await response.json()
      expect(data).toEqual({ error: 'LTI upstream unreachable' })
    })
  })

  describe('plain 200 passthrough', () => {
    it('passes a JWKS-like JSON body and content-type through', async () => {
      const jwks = '{"keys":[{"kty":"RSA","kid":"benger-lti-1"}]}'
      mockFetch.mockResolvedValueOnce(
        upstreamResponse(200, {
          headers: upstreamHeaders({
            'content-type': 'application/json',
            'content-length': String(jwks.length),
            'transfer-encoding': 'chunked',
          }),
          body: jwks,
        })
      )

      const response = await GET(
        ltiRequest('http://benger.localhost/api/lti/jwks', {
          headers: { host: 'benger.localhost' },
        })
      )

      expect(mockFetch).toHaveBeenCalledWith(
        'http://api:8000/api/lti/jwks',
        expect.objectContaining({ method: 'GET', redirect: 'manual' })
      )
      expect(response.status).toBe(200)
      expect(response.headers.get('content-type')).toBe('application/json')
      // Length/encoding headers are recomputed by the runtime, not forwarded.
      expect(response.headers.has('content-length')).toBe(false)
      expect(response.headers.has('transfer-encoding')).toBe(false)
      expect(responseBody(response)).toBe(jwks)
    })
  })
})
