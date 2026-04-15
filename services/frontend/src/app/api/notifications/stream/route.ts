import { NextRequest } from 'next/server'
import { getInternalApiUrl } from '@/lib/utils/apiUrl'

// Configure Next.js route segment config for SSE
export const dynamic = 'force-dynamic'
export const maxDuration = 3600 // 1 hour max duration for SSE connections

// SSE proxy endpoint to handle authentication for cross-origin EventSource
export async function GET(request: NextRequest) {
  const apiBaseUrl = getInternalApiUrl(request)

  const cookies = request.headers.get('cookie') || ''
  let hasAccessToken = cookies.includes('access_token')
  const hasRefreshToken = cookies.includes('refresh_token')

  // Attempt token refresh if needed
  let finalCookies = cookies
  let newAccessToken = ''

  if (!hasAccessToken && hasRefreshToken) {
    try {
      const refreshResponse = await fetch(`${apiBaseUrl}/api/auth/refresh`, {
        method: 'POST',
        headers: {
          Cookie: cookies,
          'Content-Type': 'application/json',
        },
      })

      if (refreshResponse.ok) {
        // Get the new cookies from the refresh response
        const setCookieHeaders = refreshResponse.headers.getSetCookie()
        if (setCookieHeaders.length > 0) {
          // Extract new access_token from Set-Cookie headers
          for (const setCookie of setCookieHeaders) {
            if (setCookie.includes('access_token=')) {
              const match = setCookie.match(/access_token=([^;]+)/)
              if (match) {
                newAccessToken = match[1]
                break
              }
            }
          }

          if (newAccessToken) {
            // Update cookies for the backend request
            finalCookies = cookies + `; access_token=${newAccessToken}`
          }
        }
      } else {
      }
    } catch (refreshError) {
      console.error('SSE Proxy - Token refresh error:', refreshError)
    }
  }

  // Forward the request to the backend API with all necessary headers
  const headers = new Headers()

  // Forward ALL cookies (including access_token and refresh_token)
  if (finalCookies) {
    headers.set('cookie', finalCookies)
  } else {
  }

  // Forward authorization header if present
  const authHeader = request.headers.get('authorization')
  if (authHeader) {
    headers.set('authorization', authHeader)
  }

  // Forward other important headers
  const userAgent = request.headers.get('user-agent')
  if (userAgent) {
    headers.set('user-agent', userAgent)
  }

  const referer = request.headers.get('referer')
  if (referer) {
    headers.set('referer', referer)
  }

  // Set proper headers for SSE
  headers.set('accept', 'text/event-stream')
  headers.set('cache-control', 'no-cache')
  headers.set('connection', 'keep-alive')

  // Create an AbortController for cleanup
  const abortController = new AbortController()

  try {
    const encoder = new TextEncoder()

    // Create a ReadableStream that sends immediate data and then backend stream
    const stream = new ReadableStream({
      async start(controller) {
        // Send immediate connection confirmation to trigger EventSource OPEN
        controller.enqueue(
          encoder.encode(`data: {"type": "proxy_connected"}\n\n`)
        )

        // Start backend connection
        try {
          const backendUrl = `${apiBaseUrl}/api/notifications/stream/`
          const response = await fetch(backendUrl, {
            headers,
            signal: abortController.signal,
          })

          if (!response.ok) {
            controller.enqueue(
              encoder.encode(
                `data: {"type": "error", "message": "Backend connection failed"}\n\n`
              )
            )
            controller.close()
            return
          }

          const reader = response.body?.getReader()
          if (!reader) {
            controller.enqueue(
              encoder.encode(
                `data: {"type": "error", "message": "No backend stream"}\n\n`
              )
            )
            controller.close()
            return
          }

          // Forward backend stream
          try {
            while (true) {
              const { done, value } = await reader.read()
              if (done) break
              controller.enqueue(value)
            }
          } catch (error: any) {
            if (!abortController.signal.aborted) {
              console.error('SSE stream error:', error)
            }
          } finally {
            controller.close()
          }
        } catch (error: any) {
          if (!abortController.signal.aborted) {
            controller.enqueue(
              encoder.encode(
                `data: {"type": "error", "message": "Backend error"}\n\n`
              )
            )
          }
          controller.close()
        }
      },
      cancel() {
        abortController.abort()
      },
    })

    // Handle request abortion (client disconnect)
    if (request.signal) {
      request.signal.addEventListener('abort', () => {
        abortController.abort()
      })
    }

    // Return the streaming response with comprehensive anti-buffering headers
    return new Response(stream, {
      headers: {
        'Content-Type': 'text/event-stream; charset=utf-8',
        'Cache-Control': 'no-cache, no-store, must-revalidate, no-transform',
        Pragma: 'no-cache',
        Expires: '0',
        Connection: 'keep-alive',
        'X-Accel-Buffering': 'no', // nginx
        'X-Content-Type-Options': 'nosniff',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Cache-Control',
        // Additional headers to prevent buffering
        'Transfer-Encoding': 'chunked',
      },
    })
  } catch (error: any) {
    // Only log unexpected errors
    if (
      error.name !== 'AbortError' &&
      !error.message?.includes('BodyTimeout')
    ) {
      console.error('SSE proxy error:', error)
    }
    return new Response(
      'data: {"type": "error", "message": "SSE proxy error"}\n\n',
      {
        status: 500,
        headers: {
          'Content-Type': 'text/event-stream; charset=utf-8',
          'Cache-Control': 'no-cache, no-store, must-revalidate, no-transform',
          Pragma: 'no-cache',
          Expires: '0',
          Connection: 'keep-alive',
          'X-Accel-Buffering': 'no',
          'X-Content-Type-Options': 'nosniff',
        },
      }
    )
  }
}
