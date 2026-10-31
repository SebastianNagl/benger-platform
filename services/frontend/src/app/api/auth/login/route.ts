import {
  copyRetryAfter,
  forwardedForHeaders,
  getExternalHost,
  getInternalApiUrl,
} from '@/lib/utils/apiUrl'
import { readJsonBody } from '@/lib/utils/jsonBody'
import { logger } from '@/lib/utils/logger'
import { scopeUpstreamSetCookies } from '@/lib/utils/upstreamCookies'
import { NextRequest, NextResponse } from 'next/server'

export async function POST(request: NextRequest) {
  try {
    const parsed = await readJsonBody(request)
    if (!parsed.ok) return parsed.response
    const body = parsed.body
    const apiBaseUrl = getInternalApiUrl(request)

    logger.debug('🔐 Login request to:', `${apiBaseUrl}/api/auth/login`)

    // Forward the login request to the backend. Pass the original external
    // host as x-forwarded-host so the backend's after_user_login hook can
    // detect a student-locked origin (vertretbar.net) server-side — this
    // proxy otherwise strips the browser host, and a body field would be
    // client-spoofable (same rationale as the signup route).
    const backendResponse = await fetch(`${apiBaseUrl}/api/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-forwarded-host': getExternalHost(request),
        ...forwardedForHeaders(request),
      },
      body: JSON.stringify(body),
    })

    // Get the response data
    const data = await backendResponse.json()

    // Create Next.js response. Status and body pass through unchanged, so a
    // 429 keeps its {"detail": {"code": "rate_limited", "retry_after"}} body.
    const response = NextResponse.json(data, { status: backendResponse.status })
    copyRetryAfter(backendResponse, response)

    if (backendResponse.ok) {
      // Forward Set-Cookie headers from backend to frontend
      const setCookieHeaders = backendResponse.headers.getSetCookie()
      logger.debug('🍪 Backend sent', setCookieHeaders.length, 'cookies')

      // Host-only: Domain is stripped (legacy-domain clears excepted).
      const host = getExternalHost(request)
      scopeUpstreamSetCookies(setCookieHeaders, host).forEach((cookie) => {
        let modifiedCookie = cookie

        // Ensure path is set to root
        if (!modifiedCookie.includes('Path=')) {
          modifiedCookie += '; Path=/'
        }

        // Ensure SameSite is set appropriately for development
        if (!modifiedCookie.includes('SameSite')) {
          modifiedCookie += '; SameSite=Lax'
        }

        // Outside production the stack runs on plain HTTP, so a Secure
        // cookie would never reach the browser. In production the backend's
        // Secure flag must survive the proxy.
        if (process.env.NODE_ENV !== 'production') {
          modifiedCookie = modifiedCookie.replace(/;\s*Secure/gi, '')
        }

        logger.debug(
          '🍪 Setting cookie:',
          modifiedCookie.substring(0, 100) + '...',
        )
        response.headers.append('Set-Cookie', modifiedCookie)
      })

      // Also set a test cookie that's NOT HttpOnly to verify cookies work at all
      response.headers.append(
        'Set-Cookie',
        'test_cookie=working; Path=/; SameSite=Lax',
      )
    }

    return response
  } catch (error) {
    console.error('❌ Login proxy error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 },
    )
  }
}
