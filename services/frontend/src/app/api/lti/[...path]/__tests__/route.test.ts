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
  cookies: string[] = [],
): Headers {
  const headers = new Headers(entries)
  cookies.forEach((cookie) => headers.append('Set-Cookie', cookie))
  return headers
}

/** Minimal upstream fetch-response double covering what the route touches. */
function upstreamResponse(
  status: number,
  opts: { headers?: Headers; body?: string } = {},
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
  } = {},
): NextRequest {
  const request = new NextRequest(url, {
    method: init.method ?? 'GET',
    headers: init.headers ?? {},
    ...(init.body !== undefined ? { body: init.body } : {}),
  } as ConstructorParameters<typeof NextRequest>[1])
  ;(
    request as unknown as { arrayBuffer: () => Promise<ArrayBuffer> }
  ).arrayBuffer = async () =>
    new TextEncoder().encode(init.body ?? '').buffer as ArrayBuffer
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
        }),
      )

      const response = await POST(
        ltiRequest('http://benger.localhost/api/lti/launch', {
          method: 'POST',
          headers: { host: 'benger.localhost' },
          body: 'id_token=abc&state=xyz',
        }),
      )

      expect(mockFetch).toHaveBeenCalledTimes(1)
      expect(mockFetch).toHaveBeenCalledWith(
        'http://api:8000/api/lti/launch',
        expect.objectContaining({ redirect: 'manual', method: 'POST' }),
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
        headers: upstreamHeaders({
          location: 'http://benger.localhost/lti/consent',
        }),
        arrayBuffer: async () => {
          throw new Error('3xx body must not be consumed by the proxy')
        },
      } as unknown as Response)

      const response = await GET(
        ltiRequest('http://benger.localhost/api/lti/launch', {
          headers: { host: 'benger.localhost' },
        }),
      )

      expect(response.status).toBe(303)
    })

    it('proxies the OIDC login init with its query string and passes the 302 through', async () => {
      const moodleAuth =
        'https://moodle.example/mod/lti/auth.php?scope=openid&state=s1'
      mockFetch.mockResolvedValueOnce(
        upstreamResponse(302, {
          headers: upstreamHeaders({ location: moodleAuth }),
        }),
      )

      const response = await GET(
        ltiRequest(
          'http://benger.localhost/api/lti/login?iss=https%3A%2F%2Fmoodle.example&login_hint=42',
          { headers: { host: 'benger.localhost' } },
        ),
      )

      expect(mockFetch).toHaveBeenCalledWith(
        'http://api:8000/api/lti/login?iss=https%3A%2F%2Fmoodle.example&login_hint=42',
        expect.objectContaining({ redirect: 'manual' }),
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
            ],
          ),
        }),
      )

      const response = await POST(
        ltiRequest('http://benger.localhost/api/lti/launch', {
          method: 'POST',
          headers: { host: 'benger.localhost' },
          body: 'id_token=abc',
        }),
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
        }),
      )

      const response = await GET(
        ltiRequest('http://localhost:3000/api/lti/session', {
          headers: { host: 'localhost:3000' },
        }),
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
            [
              'access_token=x; Domain=api.internal; Path=/; HttpOnly; SameSite=Lax; Secure',
            ],
          ),
        }),
      )

      const response = await POST(
        ltiRequest('https://what-a-benger.net/api/lti/launch', {
          method: 'POST',
          headers: { host: 'what-a-benger.net' },
          body: 'id_token=abc',
        }),
      )

      const cookie = response.headers.getSetCookie()[0]
      expect(cookie).toContain('Secure')
      expect(cookie).toContain('Domain=.what-a-benger.net')
    })
  })

  describe('parked LMS launch cookie (lti_pending, Path=/api/lti)', () => {
    // The launch parks the verified launch server-side and sets an httponly
    // session cookie scoped to /api/lti that carries the park's secret (the
    // URL only carries the public handle `p`); the consent and identity
    // calls send it back through this proxy. Both directions are pinned here.
    const PENDING_COOKIE =
      'lti_pending=secret-1; Domain=api.internal; HttpOnly; Path=/api/lti; SameSite=lax'

    it('keeps Path=/api/lti on the launch redirect and does not add Path=/', async () => {
      mockFetch.mockResolvedValueOnce(
        upstreamResponse(303, {
          headers: upstreamHeaders(
            {
              location:
                'http://benger.localhost/lti/consent?rl=rl-1&p=handle-1',
            },
            [
              PENDING_COOKIE,
              // The consent launch also logs out whoever was signed in.
              'access_token=""; Domain=api.internal; expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0; Path=/; SameSite=lax',
              'refresh_token=""; Domain=api.internal; expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0; Path=/; SameSite=lax',
            ],
          ),
        }),
      )

      const response = await POST(
        ltiRequest('http://benger.localhost/api/lti/launch', {
          method: 'POST',
          headers: { host: 'benger.localhost' },
          body: 'id_token=abc&state=xyz',
        }),
      )

      expect(response.status).toBe(303)
      expect(response.headers.get('location')).toBe(
        'http://benger.localhost/lti/consent?rl=rl-1&p=handle-1',
      )
      const cookies = response.headers.getSetCookie()
      expect(cookies).toHaveLength(3)

      const pending = cookies.find((c) => c.startsWith('lti_pending='))!
      expect(pending).toContain('lti_pending=secret-1')
      expect(pending.match(/Path=/gi)).toHaveLength(1)
      expect(pending).toContain('Path=/api/lti')
      expect(pending).toContain('HttpOnly')
      // Still a session cookie: the proxy adds no lifetime.
      expect(pending).not.toMatch(/Max-Age|expires/i)
      expect(pending.match(/SameSite=/gi)).toHaveLength(1)
      expect(pending).not.toContain('api.internal')
      expect(pending).toContain('Domain=.benger.localhost')

      // The session cookies are deleted, not dropped: expiry survives.
      const access = cookies.find((c) => c.startsWith('access_token='))!
      expect(access).toContain('Max-Age=0')
      expect(access).toContain('expires=Thu, 01 Jan 1970 00:00:00 GMT')
      expect(access.match(/Path=/gi)).toHaveLength(1)
      expect(access).toContain('Path=/')
      expect(cookies.some((c) => c.startsWith('refresh_token='))).toBe(true)
    })

    it('forwards the cookie and the handle to GET /api/lti/pending', async () => {
      const status =
        '{"stage":"consent","audience":"student","reconsent":false}'
      mockFetch.mockResolvedValueOnce(
        upstreamResponse(200, {
          headers: upstreamHeaders({ 'content-type': 'application/json' }),
          body: status,
        }),
      )

      const response = await GET(
        ltiRequest('http://benger.localhost/api/lti/pending?h=handle-1', {
          headers: {
            host: 'benger.localhost',
            cookie: 'lti_pending=secret-1; other=1',
          },
        }),
      )

      expect(mockFetch).toHaveBeenCalledWith(
        'http://api:8000/api/lti/pending?h=handle-1',
        expect.objectContaining({ method: 'GET', redirect: 'manual' }),
      )
      const headers = mockFetch.mock.calls[0][1]!.headers as Headers
      expect(headers.get('cookie')).toBe('lti_pending=secret-1; other=1')
      expect(response.status).toBe(200)
      expect(responseBody(response)).toBe(status)
    })

    it('forwards the consent POST with cookie and JSON body, and passes the session and the cookie deletion back', async () => {
      mockFetch.mockResolvedValueOnce(
        upstreamResponse(200, {
          headers: upstreamHeaders({ 'content-type': 'application/json' }, [
            'access_token=new; Domain=api.internal; HttpOnly; Path=/; SameSite=lax',
            'lti_pending=""; Domain=api.internal; expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0; Path=/api/lti; SameSite=lax',
          ]),
          body: '{"redirect":"/student/exams/p1?lti_u=u1"}',
        }),
      )

      const payload = '{"h":"handle-1","processing":true,"research":true}'
      const response = await POST(
        ltiRequest('http://vertretbar.localhost/api/lti/pending/consent', {
          method: 'POST',
          headers: {
            host: 'vertretbar.localhost',
            'content-type': 'application/json',
            cookie: 'lti_pending=secret-1',
          },
          body: payload,
        }),
      )

      expect(mockFetch).toHaveBeenCalledWith(
        'http://api:8000/api/lti/pending/consent',
        expect.objectContaining({ method: 'POST', redirect: 'manual' }),
      )
      const init = mockFetch.mock.calls[0][1]!
      const headers = init.headers as Headers
      expect(headers.get('cookie')).toBe('lti_pending=secret-1')
      expect(headers.get('content-type')).toBe('application/json')
      expect(headers.get('x-forwarded-host')).toBe('vertretbar.localhost')
      expect(Buffer.from(init.body as ArrayBuffer).toString('utf8')).toBe(
        payload,
      )

      expect(response.status).toBe(200)
      expect(responseBody(response)).toBe(
        '{"redirect":"/student/exams/p1?lti_u=u1"}',
      )
      const cookies = response.headers.getSetCookie()
      expect(cookies).toHaveLength(2)
      const cleared = cookies.find((c) => c.startsWith('lti_pending='))!
      expect(cleared).toContain('Max-Age=0')
      expect(cleared).toContain('Path=/api/lti')
      expect(cleared.match(/Path=/gi)).toHaveLength(1)
      expect(cleared).toContain('Domain=.vertretbar.localhost')
      const session = cookies.find((c) => c.startsWith('access_token='))!
      expect(session).toContain('Domain=.vertretbar.localhost')
      expect(session).toContain('Path=/')
    })

    it('passes a 4xx error body of the pending endpoints through unchanged', async () => {
      const detail =
        '{"detail":{"code":"launch_expired","message":"Start the activity again."}}'
      mockFetch.mockResolvedValueOnce(
        upstreamResponse(404, {
          headers: upstreamHeaders({ 'content-type': 'application/json' }),
          body: detail,
        }),
      )

      const response = await GET(
        ltiRequest('http://benger.localhost/api/lti/pending?h=gone', {
          headers: { host: 'benger.localhost' },
        }),
      )

      expect(response.status).toBe(404)
      expect(response.headers.get('content-type')).toBe('application/json')
      expect(responseBody(response)).toBe(detail)
    })
  })

  describe('request forwarding', () => {
    it('forwards POST form bodies and headers, sets x-forwarded-host, strips hop-by-hop headers', async () => {
      mockFetch.mockResolvedValueOnce(
        upstreamResponse(302, {
          headers: upstreamHeaders({ location: 'https://moodle.example/auth' }),
        }),
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
        }),
      )

      // The external host (x-forwarded-host) drives internal API resolution.
      expect(mockFetch).toHaveBeenCalledWith(
        'http://api:8000/api/lti/login',
        expect.objectContaining({ method: 'POST', redirect: 'manual' }),
      )

      const init = mockFetch.mock.calls[0][1]!
      const headers = init.headers as Headers
      // Hop-by-hop request headers are stripped...
      expect(headers.has('host')).toBe(false)
      expect(headers.has('connection')).toBe(false)
      expect(headers.has('content-length')).toBe(false)
      // ...while the payload headers survive.
      expect(headers.get('content-type')).toBe(
        'application/x-www-form-urlencoded',
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
        }),
      )

      await GET(
        ltiRequest('http://benger.localhost/api/lti/jwks', {
          headers: { host: 'benger.localhost' },
        }),
      )

      const init = mockFetch.mock.calls[0][1]!
      expect(init.body == null).toBe(true)
    })
  })

  describe('upstream failure', () => {
    it.each([
      ['POST', 'http://benger.localhost/api/lti/launch', 'id_token=abc'],
      ['POST', 'http://benger.localhost/api/lti/login', 'iss=x'],
      ['GET', 'http://benger.localhost/api/lti/login?iss=x', undefined],
      [
        'GET',
        'http://benger.localhost/api/lti/register/init?openid_configuration=x',
        undefined,
      ],
    ])(
      'sends the browser to the error page when %s %s cannot reach the API',
      async (method, url, body) => {
        mockFetch.mockRejectedValueOnce(new Error('ECONNREFUSED'))
        const handler = method === 'POST' ? POST : GET

        const response = await handler(
          ltiRequest(url, {
            method,
            headers: { host: 'benger.localhost' },
            ...(body !== undefined ? { body } : {}),
          }),
        )

        expect(response.status).toBe(303)
        expect(response.headers.get('location')).toBe(
          '/lti/error?code=internal',
        )
        expect(responseBody(response)).toBe('')
      },
    )

    it('returns 502 JSON when a page call cannot reach the API', async () => {
      mockFetch.mockRejectedValueOnce(new Error('ECONNREFUSED'))

      const response = await POST(
        ltiRequest('http://benger.localhost/api/lti/pending/consent', {
          method: 'POST',
          headers: { host: 'benger.localhost' },
          body: '{}',
        }),
      )

      expect(response.status).toBe(502)
      const data = await response.json()
      expect(data).toEqual({ error: 'LTI upstream unreachable' })
    })

    it('keeps JSON for the key set and other non-browser endpoints', async () => {
      mockFetch.mockRejectedValueOnce(new Error('ECONNREFUSED'))

      const response = await GET(
        ltiRequest('http://benger.localhost/api/lti/jwks', {
          headers: { host: 'benger.localhost' },
        }),
      )

      expect(response.status).toBe(502)
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
        }),
      )

      const response = await GET(
        ltiRequest('http://benger.localhost/api/lti/jwks', {
          headers: { host: 'benger.localhost' },
        }),
      )

      expect(mockFetch).toHaveBeenCalledWith(
        'http://api:8000/api/lti/jwks',
        expect.objectContaining({ method: 'GET', redirect: 'manual' }),
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
