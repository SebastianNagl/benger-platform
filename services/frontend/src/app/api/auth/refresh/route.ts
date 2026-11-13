import { getExternalHost, getInternalApiUrl } from '@/lib/utils/apiUrl'
import { logger } from '@/lib/utils/logger'
import { withoutSessionTokens } from '@/lib/utils/sessionBody'
import { relayedAuthCookies } from '@/lib/utils/upstreamCookies'
import { NextRequest, NextResponse } from 'next/server'

export async function POST(request: NextRequest) {
  try {
    const apiBaseUrl = getInternalApiUrl(request)
    const cookies = request.headers.get('cookie') || ''

    logger.debug('🔄 Token refresh request')

    // Forward the refresh request to the backend with cookies
    const backendResponse = await fetch(`${apiBaseUrl}/api/auth/refresh`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Cookie: cookies, // Forward existing cookies
      },
    })

    // Session tokens never reach page script: only the cookies carry them.
    const data = withoutSessionTokens(await backendResponse.json())
    const response = NextResponse.json(data, { status: backendResponse.status })

    if (backendResponse.ok) {
      // Forward the new (rotated) cookies, host-only.
      const setCookieHeaders = backendResponse.headers.getSetCookie()
      logger.debug('🍪 Refresh sent', setCookieHeaders.length, 'new cookies')
      relayedAuthCookies(setCookieHeaders, getExternalHost(request)).forEach(
        (cookie) => response.headers.append('Set-Cookie', cookie),
      )
    }

    return response
  } catch (error) {
    console.error('❌ Refresh proxy error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 },
    )
  }
}
