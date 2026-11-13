import {
  copyRetryAfter,
  forwardedForHeaders,
  getExternalHost,
  getInternalApiUrl,
} from '@/lib/utils/apiUrl'
import { readJsonBody } from '@/lib/utils/jsonBody'
import { logger } from '@/lib/utils/logger'
import { withoutSessionTokens } from '@/lib/utils/sessionBody'
import { relayedAuthCookies } from '@/lib/utils/upstreamCookies'
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

    // Status and body pass through, so a 429 keeps its
    // {"detail": {"code": "rate_limited", "retry_after"}} body; session
    // tokens never reach page script (they travel only in HttpOnly cookies).
    const data = withoutSessionTokens(await backendResponse.json())
    const response = NextResponse.json(data, { status: backendResponse.status })
    copyRetryAfter(backendResponse, response)

    if (backendResponse.ok) {
      // Forward the backend's cookies, host-only (Domain is stripped,
      // legacy-domain clears excepted).
      const setCookieHeaders = backendResponse.headers.getSetCookie()
      logger.debug('🍪 Backend sent', setCookieHeaders.length, 'cookies')
      relayedAuthCookies(setCookieHeaders, getExternalHost(request)).forEach(
        (cookie) => response.headers.append('Set-Cookie', cookie),
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
