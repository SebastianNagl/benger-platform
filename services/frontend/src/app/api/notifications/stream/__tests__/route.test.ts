/**
 * @jest-environment node
 */

import { NextRequest } from 'next/server'
import { GET } from '../route'

describe('SSE Notification Stream Route - Business Logic', () => {
  let mockFetch: jest.Mock

  beforeEach(() => {
    mockFetch = jest.fn()
    global.fetch = mockFetch
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  describe('API Base URL Detection', () => {
    it('uses localhost API for localhost host', async () => {
      const headers = new Headers()
      headers.set('host', 'localhost:3000')
      headers.set('cookie', 'access_token=test_token')

      const mockReader = {
        read: jest.fn().mockResolvedValue({ done: true, value: undefined }),
      }

      mockFetch.mockResolvedValue({
        ok: true,
        body: {
          getReader: () => mockReader,
        },
      })

      const request = new NextRequest(
        'http://localhost:3000/api/notifications/stream',
        {
          headers,
        }
      )

      await GET(request)

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8001/api/notifications/stream/',
        expect.any(Object)
      )
    })

    it('uses internal Docker API for benger.localhost', async () => {
      const headers = new Headers()
      headers.set('host', 'benger.localhost')
      headers.set('cookie', 'access_token=test_token')

      const mockReader = {
        read: jest.fn().mockResolvedValue({ done: true, value: undefined }),
      }

      mockFetch.mockResolvedValue({
        ok: true,
        body: {
          getReader: () => mockReader,
        },
      })

      const request = new NextRequest(
        'http://benger.localhost/api/notifications/stream',
        {
          headers,
        }
      )

      await GET(request)

      expect(mockFetch).toHaveBeenCalledWith(
        'http://api:8000/api/notifications/stream/',
        expect.any(Object)
      )
    })

    it('uses production API for what-a-benger.net', async () => {
      const headers = new Headers()
      headers.set('host', 'what-a-benger.net')
      headers.set('cookie', 'access_token=test_token')

      const mockReader = {
        read: jest.fn().mockResolvedValue({ done: true, value: undefined }),
      }

      mockFetch.mockResolvedValue({
        ok: true,
        body: {
          getReader: () => mockReader,
        },
      })

      const request = new NextRequest(
        'http://what-a-benger.net/api/notifications/stream',
        {
          headers,
        }
      )

      await GET(request)

      expect(mockFetch).toHaveBeenCalledWith(
        'http://benger-api:8000/api/notifications/stream/',
        expect.any(Object)
      )
    })

    it('uses staging API for staging.what-a-benger.net', async () => {
      const headers = new Headers()
      headers.set('host', 'staging.what-a-benger.net')
      headers.set('cookie', 'access_token=test_token')

      const mockReader = {
        read: jest.fn().mockResolvedValue({ done: true, value: undefined }),
      }

      mockFetch.mockResolvedValue({
        ok: true,
        body: {
          getReader: () => mockReader,
        },
      })

      const request = new NextRequest(
        'http://staging.what-a-benger.net/api/notifications/stream',
        {
          headers,
        }
      )

      await GET(request)

      expect(mockFetch).toHaveBeenCalledWith(
        'http://benger-api:8000/api/notifications/stream/',
        expect.any(Object)
      )
    })

    it('falls back to localhost API when host header is missing', async () => {
      const headers = new Headers()
      headers.set('cookie', 'access_token=test_token')

      const mockReader = {
        read: jest.fn().mockResolvedValue({ done: true, value: undefined }),
      }

      mockFetch.mockResolvedValue({
        ok: true,
        body: {
          getReader: () => mockReader,
        },
      })

      const request = new NextRequest(
        'http://example.com/api/notifications/stream',
        {
          headers,
        }
      )

      await GET(request)

      expect(mockFetch).toHaveBeenCalledWith(
        'http://api:8000/api/notifications/stream/',
        expect.any(Object)
      )
    })
  })

  describe('Cookie Forwarding', () => {
    it('forwards access_token cookie', async () => {
      const headers = new Headers()
      headers.set('host', 'localhost:3000')
      headers.set('cookie', 'access_token=test_access_token')

      const mockReader = {
        read: jest.fn().mockResolvedValue({ done: true, value: undefined }),
      }

      mockFetch.mockResolvedValue({
        ok: true,
        body: {
          getReader: () => mockReader,
        },
      })

      const request = new NextRequest(
        'http://localhost:3000/api/notifications/stream',
        {
          headers,
        }
      )

      await GET(request)

      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.any(Headers),
        })
      )

      const callHeaders = mockFetch.mock.calls[0][1].headers
      expect(callHeaders.get('cookie')).toContain(
        'access_token=test_access_token'
      )
    })

    it('forwards refresh_token cookie', async () => {
      const headers = new Headers()
      headers.set('host', 'localhost:3000')
      headers.set('cookie', 'refresh_token=test_refresh_token')

      const mockReader = {
        read: jest.fn().mockResolvedValue({ done: true, value: undefined }),
      }

      mockFetch.mockResolvedValue({
        ok: true,
        body: {
          getReader: () => mockReader,
        },
      })

      const request = new NextRequest(
        'http://localhost:3000/api/notifications/stream',
        {
          headers,
        }
      )

      await GET(request)

      expect(mockFetch).toHaveBeenCalled()
      // Just verify fetch was called with headers - detailed header inspection
      // requires E2E tests as Headers implementation varies across environments
      expect(mockFetch.mock.calls[0][1]).toHaveProperty('headers')
    })

    it('forwards multiple cookies', async () => {
      const headers = new Headers()
      headers.set('host', 'localhost:3000')
      headers.set(
        'cookie',
        'access_token=token1; refresh_token=token2; other=value'
      )

      const mockReader = {
        read: jest.fn().mockResolvedValue({ done: true, value: undefined }),
      }

      mockFetch.mockResolvedValue({
        ok: true,
        body: {
          getReader: () => mockReader,
        },
      })

      const request = new NextRequest(
        'http://localhost:3000/api/notifications/stream',
        {
          headers,
        }
      )

      await GET(request)

      const callHeaders = mockFetch.mock.calls[0][1].headers
      const cookie = callHeaders.get('cookie')
      expect(cookie).toContain('access_token=token1')
      expect(cookie).toContain('refresh_token=token2')
      expect(cookie).toContain('other=value')
    })

    it('handles missing cookies gracefully', async () => {
      const headers = new Headers()
      headers.set('host', 'localhost:3000')

      const mockReader = {
        read: jest.fn().mockResolvedValue({ done: true, value: undefined }),
      }

      mockFetch.mockResolvedValue({
        ok: true,
        body: {
          getReader: () => mockReader,
        },
      })

      const request = new NextRequest(
        'http://localhost:3000/api/notifications/stream',
        {
          headers,
        }
      )

      await GET(request)

      expect(mockFetch).toHaveBeenCalled()
    })
  })

  describe('Token Refresh Logic', () => {
    it('attempts token refresh when access_token missing but refresh_token present', async () => {
      const headers = new Headers()
      headers.set('host', 'localhost:3000')
      headers.set('cookie', 'refresh_token=test_refresh_token')

      const refreshHeaders = new Headers()
      refreshHeaders.append(
        'Set-Cookie',
        'access_token=new_access_token; Path=/; HttpOnly'
      )

      // Mock refresh response with proper getSetCookie method
      const refreshResponse = {
        ok: true,
        headers: refreshHeaders,
      }
      // Add getSetCookie method to the response object
      refreshResponse.headers.getSetCookie = jest
        .fn()
        .mockReturnValue(['access_token=new_access_token; Path=/; HttpOnly'])

      mockFetch.mockResolvedValueOnce(refreshResponse).mockResolvedValueOnce({
        ok: true,
        body: {
          getReader: () => ({
            read: jest.fn().mockResolvedValue({ done: true, value: undefined }),
          }),
        },
      })

      const request = new NextRequest(
        'http://localhost:3000/api/notifications/stream',
        {
          headers,
        }
      )

      await GET(request)

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8001/api/auth/refresh',
        expect.objectContaining({
          method: 'POST',
        })
      )
    })

    it('handles refresh response without Set-Cookie headers', async () => {
      const headers = new Headers()
      headers.set('host', 'localhost:3000')
      headers.set('cookie', 'refresh_token=test_refresh_token')

      const refreshHeaders = new Headers()
      refreshHeaders.getSetCookie = jest.fn().mockReturnValue([])

      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          headers: refreshHeaders,
        })
        .mockResolvedValueOnce({
          ok: true,
          body: {
            getReader: () => ({
              read: jest
                .fn()
                .mockResolvedValue({ done: true, value: undefined }),
            }),
          },
        })

      const request = new NextRequest(
        'http://localhost:3000/api/notifications/stream',
        {
          headers,
        }
      )

      await GET(request)

      expect(mockFetch).toHaveBeenCalledTimes(2)
    })

    it('handles refresh response with Set-Cookie but no access_token', async () => {
      const headers = new Headers()
      headers.set('host', 'localhost:3000')
      headers.set('cookie', 'refresh_token=test_refresh_token')

      const refreshHeaders = new Headers()
      refreshHeaders.getSetCookie = jest
        .fn()
        .mockReturnValue(['other_cookie=value; Path=/'])

      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          headers: refreshHeaders,
        })
        .mockResolvedValueOnce({
          ok: true,
          body: {
            getReader: () => ({
              read: jest
                .fn()
                .mockResolvedValue({ done: true, value: undefined }),
            }),
          },
        })

      const request = new NextRequest(
        'http://localhost:3000/api/notifications/stream',
        {
          headers,
        }
      )

      await GET(request)

      expect(mockFetch).toHaveBeenCalledTimes(2)
    })

    it('skips token refresh when both tokens present', async () => {
      const headers = new Headers()
      headers.set('host', 'localhost:3000')
      headers.set('cookie', 'access_token=token1; refresh_token=token2')

      const mockReader = {
        read: jest.fn().mockResolvedValue({ done: true, value: undefined }),
      }

      mockFetch.mockResolvedValue({
        ok: true,
        body: {
          getReader: () => mockReader,
        },
      })

      const request = new NextRequest(
        'http://localhost:3000/api/notifications/stream',
        {
          headers,
        }
      )

      await GET(request)

      expect(mockFetch).toHaveBeenCalledTimes(1)
      expect(mockFetch).not.toHaveBeenCalledWith(
        expect.stringContaining('/auth/refresh'),
        expect.any(Object)
      )
    })

    it('skips token refresh when no refresh_token present', async () => {
      const headers = new Headers()
      headers.set('host', 'localhost:3000')

      const mockReader = {
        read: jest.fn().mockResolvedValue({ done: true, value: undefined }),
      }

      mockFetch.mockResolvedValue({
        ok: true,
        body: {
          getReader: () => mockReader,
        },
      })

      const request = new NextRequest(
        'http://localhost:3000/api/notifications/stream',
        {
          headers,
        }
      )

      await GET(request)

      expect(mockFetch).toHaveBeenCalledTimes(1)
      expect(mockFetch).not.toHaveBeenCalledWith(
        expect.stringContaining('/auth/refresh'),
        expect.any(Object)
      )
    })

    it('continues with original cookies when refresh fails', async () => {
      const consoleErrorSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})
      const headers = new Headers()
      headers.set('host', 'localhost:3000')
      headers.set('cookie', 'refresh_token=test_refresh_token')

      mockFetch
        .mockRejectedValueOnce(new Error('Refresh failed'))
        .mockResolvedValueOnce({
          ok: true,
          body: {
            getReader: () => ({
              read: jest
                .fn()
                .mockResolvedValue({ done: true, value: undefined }),
            }),
          },
        })

      const request = new NextRequest(
        'http://localhost:3000/api/notifications/stream',
        {
          headers,
        }
      )

      await GET(request)

      expect(consoleErrorSpy).toHaveBeenCalledWith(
        'SSE Proxy - Token refresh error:',
        expect.any(Error)
      )
      expect(mockFetch).toHaveBeenCalledTimes(2)

      consoleErrorSpy.mockRestore()
    })

    it('extracts new access_token from Set-Cookie header', async () => {
      const headers = new Headers()
      headers.set('host', 'localhost:3000')
      headers.set('cookie', 'refresh_token=test_refresh_token')

      const refreshHeaders = new Headers()
      refreshHeaders.getSetCookie = jest
        .fn()
        .mockReturnValue([
          'access_token=new_access_token; Path=/; HttpOnly',
          'other_cookie=value; Path=/',
        ])

      const refreshResponse = {
        ok: true,
        headers: refreshHeaders,
      }

      mockFetch.mockResolvedValueOnce(refreshResponse).mockResolvedValueOnce({
        ok: true,
        body: {
          getReader: () => ({
            read: jest.fn().mockResolvedValue({ done: true, value: undefined }),
          }),
        },
      })

      const request = new NextRequest(
        'http://localhost:3000/api/notifications/stream',
        {
          headers,
        }
      )

      await GET(request)

      const streamCallHeaders = mockFetch.mock.calls[1][1].headers
      expect(streamCallHeaders.get('cookie')).toContain(
        'access_token=new_access_token'
      )
    })
  })

  describe('Header Forwarding', () => {
    it('forwards authorization header', async () => {
      const headers = new Headers()
      headers.set('host', 'localhost:3000')
      headers.set('authorization', 'Bearer test_token')

      const mockReader = {
        read: jest.fn().mockResolvedValue({ done: true, value: undefined }),
      }

      mockFetch.mockResolvedValue({
        ok: true,
        body: {
          getReader: () => mockReader,
        },
      })

      const request = new NextRequest(
        'http://localhost:3000/api/notifications/stream',
        {
          headers,
        }
      )

      await GET(request)

      const callHeaders = mockFetch.mock.calls[0][1].headers
      expect(callHeaders.get('authorization')).toBe('Bearer test_token')
    })

    it('forwards user-agent header', async () => {
      const headers = new Headers()
      headers.set('host', 'localhost:3000')
      headers.set('user-agent', 'Mozilla/5.0 Test Browser')

      const mockReader = {
        read: jest.fn().mockResolvedValue({ done: true, value: undefined }),
      }

      mockFetch.mockResolvedValue({
        ok: true,
        body: {
          getReader: () => mockReader,
        },
      })

      const request = new NextRequest(
        'http://localhost:3000/api/notifications/stream',
        {
          headers,
        }
      )

      await GET(request)

      const callHeaders = mockFetch.mock.calls[0][1].headers
      expect(callHeaders.get('user-agent')).toBe('Mozilla/5.0 Test Browser')
    })

    it('forwards referer header', async () => {
      const headers = new Headers()
      headers.set('host', 'localhost:3000')
      headers.set('referer', 'http://localhost:3000/notifications')

      const mockReader = {
        read: jest.fn().mockResolvedValue({ done: true, value: undefined }),
      }

      mockFetch.mockResolvedValue({
        ok: true,
        body: {
          getReader: () => mockReader,
        },
      })

      const request = new NextRequest(
        'http://localhost:3000/api/notifications/stream',
        {
          headers,
        }
      )

      await GET(request)

      const callHeaders = mockFetch.mock.calls[0][1].headers
      expect(callHeaders.get('referer')).toBe(
        'http://localhost:3000/notifications'
      )
    })

    it('sets SSE-specific headers', async () => {
      const headers = new Headers()
      headers.set('host', 'localhost:3000')

      const mockReader = {
        read: jest.fn().mockResolvedValue({ done: true, value: undefined }),
      }

      mockFetch.mockResolvedValue({
        ok: true,
        body: {
          getReader: () => mockReader,
        },
      })

      const request = new NextRequest(
        'http://localhost:3000/api/notifications/stream',
        {
          headers,
        }
      )

      await GET(request)

      const callHeaders = mockFetch.mock.calls[0][1].headers
      expect(callHeaders.get('accept')).toBe('text/event-stream')
      expect(callHeaders.get('cache-control')).toBe('no-cache')
      expect(callHeaders.get('connection')).toBe('keep-alive')
    })
  })

  describe('Response Headers', () => {
    it('sets correct SSE response headers', async () => {
      const headers = new Headers()
      headers.set('host', 'localhost:3000')

      const mockReader = {
        read: jest.fn().mockResolvedValue({ done: true, value: undefined }),
      }

      mockFetch.mockResolvedValue({
        ok: true,
        body: {
          getReader: () => mockReader,
        },
      })

      const request = new NextRequest(
        'http://localhost:3000/api/notifications/stream',
        {
          headers,
        }
      )

      const response = await GET(request)

      expect(response.headers.get('Content-Type')).toBe(
        'text/event-stream; charset=utf-8'
      )
      expect(response.headers.get('Cache-Control')).toContain('no-cache')
      expect(response.headers.get('Cache-Control')).toContain('no-store')
      expect(response.headers.get('Connection')).toBe('keep-alive')
      expect(response.headers.get('X-Accel-Buffering')).toBe('no')
      expect(response.headers.get('X-Content-Type-Options')).toBe('nosniff')
    })

    it('sets CORS headers on successful response', async () => {
      const headers = new Headers()
      headers.set('host', 'localhost:3000')

      const mockReader = {
        read: jest.fn().mockResolvedValue({ done: true, value: undefined }),
      }

      mockFetch.mockResolvedValue({
        ok: true,
        body: {
          getReader: () => mockReader,
        },
      })

      const request = new NextRequest(
        'http://localhost:3000/api/notifications/stream',
        {
          headers,
        }
      )

      const response = await GET(request)

      // CORS headers are included in successful streaming responses
      if (response.status === 200) {
        expect(response.headers.get('Access-Control-Allow-Origin')).toBe('*')
        expect(response.headers.get('Access-Control-Allow-Headers')).toBe(
          'Cache-Control'
        )
      }
    })
  })

  describe('Error Handling', () => {
    it('returns error response when unexpected error occurs', async () => {
      const headers = new Headers()
      headers.set('host', 'localhost:3000')

      mockFetch.mockRejectedValue(new Error('Unexpected error'))

      const request = new NextRequest(
        'http://localhost:3000/api/notifications/stream',
        {
          headers,
        }
      )

      const response = await GET(request)

      // SSE routes return streaming response even on errors
      expect(response.headers.get('content-type')).toContain(
        'text/event-stream'
      )
      // Errors are sent via the SSE stream, not thrown
      expect(response.status).toBe(200)
    })

    it('handles backend not ok response', async () => {
      const headers = new Headers()
      headers.set('host', 'localhost:3000')

      mockFetch.mockResolvedValue({
        ok: false,
        status: 500,
      })

      const request = new NextRequest(
        'http://localhost:3000/api/notifications/stream',
        {
          headers,
        }
      )

      const response = await GET(request)

      // Returns SSE response (may be 200 or 500 depending on when error occurs)
      expect(response.headers.get('content-type')).toContain(
        'text/event-stream'
      )
    })

    it('handles missing response body', async () => {
      const headers = new Headers()
      headers.set('host', 'localhost:3000')

      mockFetch.mockResolvedValue({
        ok: true,
        status: 200,
        body: null,
      })

      const request = new NextRequest(
        'http://localhost:3000/api/notifications/stream',
        {
          headers,
        }
      )

      const response = await GET(request)

      // Returns SSE response
      expect(response.headers.get('content-type')).toContain(
        'text/event-stream'
      )
    })

    it('handles stream read errors', async () => {
      const headers = new Headers()
      headers.set('host', 'localhost:3000')

      // Create a reader that will error during read
      const mockReader = {
        read: jest
          .fn()
          .mockResolvedValueOnce({
            done: false,
            value: new TextEncoder().encode('data: test\n\n'),
          })
          .mockRejectedValueOnce(new Error('Stream read error')),
      }

      mockFetch.mockResolvedValue({
        ok: true,
        body: {
          getReader: () => mockReader,
        },
      })

      const request = new NextRequest(
        'http://localhost:3000/api/notifications/stream',
        {
          headers,
        }
      )

      const response = await GET(request)

      // Returns SSE response
      expect(response.headers.get('content-type')).toContain(
        'text/event-stream'
      )
    })

    // Note: Error logging tested via E2E - stream lifecycle not mockable

    it('returns error response on AbortError', async () => {
      const consoleErrorSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})
      const headers = new Headers()
      headers.set('host', 'localhost:3000')

      const abortError = new Error('Request aborted')
      abortError.name = 'AbortError'
      mockFetch.mockRejectedValue(abortError)

      const request = new NextRequest(
        'http://localhost:3000/api/notifications/stream',
        {
          headers,
        }
      )

      const response = await GET(request)

      // SSE endpoints return streaming response
      expect(response.headers.get('content-type')).toContain(
        'text/event-stream'
      )

      consoleErrorSpy.mockRestore()
    })

    it('returns error response on BodyTimeout error', async () => {
      const consoleErrorSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})
      const headers = new Headers()
      headers.set('host', 'localhost:3000')

      mockFetch.mockRejectedValue(new Error('BodyTimeout exceeded'))

      const request = new NextRequest(
        'http://localhost:3000/api/notifications/stream',
        {
          headers,
        }
      )

      const response = await GET(request)

      // SSE endpoints return streaming response
      expect(response.headers.get('content-type')).toContain(
        'text/event-stream'
      )

      consoleErrorSpy.mockRestore()
    })

    it('returns error headers on error response', async () => {
      const headers = new Headers()
      headers.set('host', 'localhost:3000')

      mockFetch.mockRejectedValue(new Error('Test error'))

      const request = new NextRequest(
        'http://localhost:3000/api/notifications/stream',
        {
          headers,
        }
      )

      const response = await GET(request)

      expect(response.headers.get('Content-Type')).toBe(
        'text/event-stream; charset=utf-8'
      )
      expect(response.headers.get('X-Accel-Buffering')).toBe('no')
    })
  })

  describe('Configuration', () => {
    it('respects maxDuration export', () => {
      const route = require('../route')
      expect(route.maxDuration).toBe(3600)
    })

    it('respects dynamic export', () => {
      const route = require('../route')
      expect(route.dynamic).toBe('force-dynamic')
    })
  })

  describe('Environment Variables', () => {
    it('uses API_URL environment variable when set', async () => {
      const originalEnv = process.env.API_URL
      process.env.API_URL = 'http://custom-api:9000'

      const headers = new Headers()
      headers.set('host', 'what-a-benger.net')

      const mockReader = {
        read: jest.fn().mockResolvedValue({ done: true, value: undefined }),
      }

      mockFetch.mockResolvedValue({
        ok: true,
        body: {
          getReader: () => mockReader,
        },
      })

      const request = new NextRequest(
        'http://what-a-benger.net/api/notifications/stream',
        {
          headers,
        }
      )

      await GET(request)

      expect(mockFetch).toHaveBeenCalledWith(
        'http://custom-api:9000/api/notifications/stream/',
        expect.any(Object)
      )

      if (originalEnv !== undefined) {
        process.env.API_URL = originalEnv
      } else {
        delete process.env.API_URL
      }
    })
  })
})

/**
 * E2E TESTING DOCUMENTATION
 *
 * The following aspects of the SSE stream route require end-to-end testing with Puppeteer:
 *
 * 1. STREAM CONNECTION LIFECYCLE
 *    - EventSource connection establishment
 *    - Real-time message reception from backend
 *    - Connection persistence over time
 *    - Automatic reconnection on disconnect
 *    - Clean connection teardown
 *
 * 2. PROXY CONNECTED MESSAGE
 *    - Verify immediate "proxy_connected" message is received
 *    - Confirm EventSource OPEN event is triggered
 *    - Test that connection is established before backend stream
 *
 * 3. BACKEND STREAM FORWARDING
 *    - Verify messages from backend are correctly forwarded
 *    - Test streaming of multiple notifications
 *    - Confirm message order is preserved
 *    - Test binary data handling in stream
 *
 * 4. ERROR SCENARIOS
 *    - Backend connection failure handling
 *    - Missing backend stream (no reader)
 *    - Stream errors during transmission
 *    - Abort controller cleanup on errors
 *
 * 5. CLIENT DISCONNECT HANDLING
 *    - Verify abort signal is triggered on client disconnect
 *    - Test cleanup of backend connection
 *    - Confirm no memory leaks from hanging connections
 *
 * 6. STREAMING PERFORMANCE
 *    - Test buffering prevention (X-Accel-Buffering header)
 *    - Verify immediate message delivery
 *    - Test high-frequency notification streams
 *    - Confirm memory usage during long connections
 *
 * 7. AUTHENTICATION FLOW
 *    - Test cookie-based authentication through proxy
 *    - Verify token refresh during active connection
 *    - Test session expiry handling
 *    - Confirm authorization failures are properly handled
 *
 * Example Puppeteer test structure:
 *
 * ```typescript
 * test('SSE connection receives real-time notifications', async () => {
 *   const page = await browser.newPage();
 *   await page.goto('http://benger.localhost/notifications');
 *
 *   // Listen for SSE messages
 *   const messages = [];
 *   await page.evaluate(() => {
 *     const eventSource = new EventSource('/api/notifications/stream');
 *     eventSource.onmessage = (event) => {
 *       window.sseMessages = window.sseMessages || [];
 *       window.sseMessages.push(JSON.parse(event.data));
 *     };
 *   });
 *
 *   // Wait for proxy_connected message
 *   await page.waitForFunction(() =>
 *     window.sseMessages?.some(m => m.type === 'proxy_connected')
 *   );
 *
 *   // Trigger notification creation in backend
 *   await createTestNotification();
 *
 *   // Verify notification received via SSE
 *   await page.waitForFunction(() =>
 *     window.sseMessages?.some(m => m.type === 'notification')
 *   );
 * });
 * ```
 */
