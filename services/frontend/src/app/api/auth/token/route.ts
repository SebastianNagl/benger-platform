import {
  copyRetryAfter,
  forwardedForHeaders,
  getExternalHost,
  getInternalApiUrl,
} from '@/lib/utils/apiUrl'
import { readJsonBody } from '@/lib/utils/jsonBody'
import { logger } from '@/lib/utils/logger'
import { NextRequest, NextResponse } from 'next/server'

/**
 * Script login: `POST /api/auth/token {username, password}` answers with an
 * access token in the body, to send as `Authorization: Bearer <token>`.
 *
 * The catch-all proxy refuses `auth/*` paths without a dedicated handler,
 * so without this route the endpoint the API documents for scripts could
 * only be reached on the api host. Unlike the login route it relays the body
 * unchanged, since the token in the body is what the endpoint is for, and it
 * passes on no cookie: the API sets none here, and a script login must never
 * start a browser session on this host.
 */
export async function POST(request: NextRequest) {
  try {
    const parsed = await readJsonBody(request)
    if (!parsed.ok) return parsed.response
    const apiBaseUrl = getInternalApiUrl(request)

    logger.debug('🔑 Token request to:', `${apiBaseUrl}/api/auth/token`)

    // The client address travels on, because the API limits failed logins
    // per address; the external host for the same reason as on login.
    const backendResponse = await fetch(`${apiBaseUrl}/api/auth/token`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-forwarded-host': getExternalHost(request),
        ...forwardedForHeaders(request),
      },
      body: JSON.stringify(parsed.body),
    })

    const data = await backendResponse.json()
    const response = NextResponse.json(data, {
      status: backendResponse.status,
    })
    copyRetryAfter(backendResponse, response)
    response.headers.set('Cache-Control', 'no-store')
    return response
  } catch (error) {
    console.error('❌ Token proxy error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 },
    )
  }
}
