/**
 * Response-header forwarding tests for the API proxy.
 *
 * The critical contract: `content-encoding` must NEVER be copied from the
 * upstream response. undici transparently decompresses the body (buffered and
 * streamed alike) while leaving the stale header on `response.headers` —
 * copying it labels plaintext as gzip and breaks strict clients downstream
 * (2026-07-31 finding from the vertretbar status-endpoint smoke).
 */

import { NextRequest } from 'next/server'
import { GET } from '../route'

global.fetch = jest.fn()

function upstreamHeaders(entries: Record<string, string>): Headers {
  const headers = new Headers()
  Object.entries(entries).forEach(([k, v]) => headers.set(k, v))
  return headers
}

describe('API proxy response-header forwarding', () => {
  let mockFetch: jest.MockedFunction<typeof fetch>

  beforeEach(() => {
    mockFetch = global.fetch as jest.MockedFunction<typeof fetch>
    mockFetch.mockClear()
    jest.spyOn(console, 'log').mockImplementation()
    jest.spyOn(console, 'error').mockImplementation()
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  it('drops content-encoding but keeps other upstream headers', async () => {
    mockFetch.mockResolvedValueOnce({
      status: 200,
      statusText: 'OK',
      headers: upstreamHeaders({
        'content-type': 'application/json',
        // What undici leaves behind after transparently gunzipping the body.
        'content-encoding': 'gzip',
        'x-catalog-version': 'abc123',
      }),
      text: async () => '{"ok": true}',
    } as any)

    const request = new NextRequest('http://localhost:3000/api/tasks', {
      headers: { host: 'localhost:3000' },
    })
    const response = await GET(request, {
      params: Promise.resolve({ path: ['tasks'] }),
    })

    expect(response.headers.get('content-encoding')).toBeNull()
    expect(response.headers.get('content-type')).toContain('application/json')
    expect(response.headers.get('x-catalog-version')).toBe('abc123')
  })

  describe('client address forwarding (per-IP auth limits)', () => {
    const okUpstream = () =>
      mockFetch.mockResolvedValueOnce({
        status: 200,
        statusText: 'OK',
        headers: upstreamHeaders({ 'content-type': 'application/json' }),
        text: async () => '{}',
      } as any)

    it('forwards x-forwarded-for unchanged', async () => {
      okUpstream()
      const request = new NextRequest(
        'http://localhost:3000/api/auth/reset-password',
        {
          headers: {
            host: 'localhost:3000',
            'x-forwarded-for': '198.51.100.7, 203.0.113.9',
          },
        },
      )
      await GET(request, {
        params: Promise.resolve({ path: ['auth', 'reset-password'] }),
      })
      const init = mockFetch.mock.calls[0][1] as RequestInit
      expect(new Headers(init.headers).get('x-forwarded-for')).toBe(
        '198.51.100.7, 203.0.113.9',
      )
    })

    it('adds x-forwarded-for from x-real-ip when missing', async () => {
      okUpstream()
      const request = new NextRequest('http://localhost:3000/api/tasks', {
        headers: { host: 'localhost:3000', 'x-real-ip': '198.51.100.8' },
      })
      await GET(request, { params: Promise.resolve({ path: ['tasks'] }) })
      const init = mockFetch.mock.calls[0][1] as RequestInit
      expect(new Headers(init.headers).get('x-forwarded-for')).toBe(
        '198.51.100.8',
      )
    })
  })
})
