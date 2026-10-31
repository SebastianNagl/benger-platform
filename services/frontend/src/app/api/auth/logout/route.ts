import { getExternalHost, getInternalApiUrl } from '@/lib/utils/apiUrl'
import { logger } from '@/lib/utils/logger'
import { scopeUpstreamSetCookies } from '@/lib/utils/upstreamCookies'
import { NextRequest, NextResponse } from 'next/server'

export async function POST(request: NextRequest) {
  try {
    const apiBaseUrl = getInternalApiUrl(request)
    const cookies = request.headers.get('cookie') || ''

    logger.debug('🚪 Logout request')

    // Forward the logout request to the backend with cookies
    const backendResponse = await fetch(`${apiBaseUrl}/api/auth/logout`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Cookie: cookies, // Forward existing cookies
      },
    })

    // Create Next.js response (logout might return 204 No Content)
    const response = new NextResponse(null, { status: 204 })

    // Relay the backend's clears for the domain-wide cookies of older
    // releases (LEGACY_COOKIE_DOMAIN); its host-only clears repeat the ones
    // below and are harmless.
    const host = getExternalHost(request)
    for (const cookie of scopeUpstreamSetCookies(
      backendResponse.headers.getSetCookie(),
      host,
    )) {
      response.headers.append('Set-Cookie', cookie)
    }

    // Clear the host-only session cookies even when the backend call failed
    // (an expired access token answers 401).
    response.headers.append(
      'Set-Cookie',
      'access_token=; Path=/; Max-Age=0; HttpOnly',
    )
    response.headers.append(
      'Set-Cookie',
      'refresh_token=; Path=/; Max-Age=0; HttpOnly',
    )
    // The LMS-launch marker (auth_module/session_origin.py) ends with the session.
    response.headers.append(
      'Set-Cookie',
      'benger_session_origin=; Path=/; Max-Age=0',
    )

    logger.debug('🍪 Cookies cleared')

    return response
  } catch (error) {
    console.error('❌ Logout proxy error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 },
    )
  }
}
