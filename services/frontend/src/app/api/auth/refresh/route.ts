import { getExternalHost, getInternalApiUrl } from '@/lib/utils/apiUrl'
import { logger } from '@/lib/utils/logger'
import { scopeUpstreamSetCookies } from '@/lib/utils/upstreamCookies'
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

    // Get the response data
    const data = await backendResponse.json()

    // Create Next.js response
    const response = NextResponse.json(data, { status: backendResponse.status })

    if (backendResponse.ok) {
      // Forward Set-Cookie headers from backend to frontend
      const setCookieHeaders = backendResponse.headers.getSetCookie()
      logger.debug('🍪 Refresh sent', setCookieHeaders.length, 'new cookies')

      // Host-only: Domain is stripped (legacy-domain clears excepted).
      const host = getExternalHost(request)
      scopeUpstreamSetCookies(setCookieHeaders, host).forEach((cookie) => {
        let modifiedCookie = cookie

        // Ensure path is set to root
        if (!modifiedCookie.includes('Path=')) {
          modifiedCookie += '; Path=/'
        }

        // Ensure SameSite is set
        if (!modifiedCookie.includes('SameSite')) {
          modifiedCookie += '; SameSite=Lax'
        }

        // Outside production the stack runs on plain HTTP, so a Secure
        // cookie would never reach the browser. In production the backend's
        // Secure flag must survive the proxy.
        if (process.env.NODE_ENV !== 'production') {
          modifiedCookie = modifiedCookie.replace(/;\s*Secure/gi, '')
        }

        response.headers.append('Set-Cookie', modifiedCookie)
      })
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
