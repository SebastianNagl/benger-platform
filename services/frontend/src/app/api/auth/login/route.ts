import { NextRequest, NextResponse } from 'next/server'
import { logger } from '@/lib/utils/logger'
import { getInternalApiUrl, getExternalHost } from '@/lib/utils/apiUrl'
import { getCookieDomainFromHost } from '@/lib/utils/subdomain'

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const apiBaseUrl = getInternalApiUrl(request)

    logger.debug('🔐 Login request to:', `${apiBaseUrl}/api/auth/login`)

    // Forward the login request to the backend
    const backendResponse = await fetch(`${apiBaseUrl}/api/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    })

    // Get the response data
    const data = await backendResponse.json()

    // Create Next.js response
    const response = NextResponse.json(data, { status: backendResponse.status })

    if (backendResponse.ok) {
      // Forward Set-Cookie headers from backend to frontend
      const setCookieHeaders = backendResponse.headers.getSetCookie()
      logger.debug('🍪 Backend sent', setCookieHeaders.length, 'cookies')

      setCookieHeaders.forEach((cookie) => {
        // Parse and modify cookie for proper domain/path
        let modifiedCookie = cookie

        // Remove any existing domain restriction
        modifiedCookie = modifiedCookie.replace(/Domain=[^;]+;?/gi, '')

        // Set cookie domain for cross-subdomain sharing
        const host = getExternalHost(request)
        const cookieDomain = getCookieDomainFromHost(host)
        if (cookieDomain) {
          modifiedCookie += `; Domain=${cookieDomain}`
        }

        // Ensure path is set to root
        if (!modifiedCookie.includes('Path=')) {
          modifiedCookie += '; Path=/'
        }

        // Ensure SameSite is set appropriately for development
        if (!modifiedCookie.includes('SameSite')) {
          modifiedCookie += '; SameSite=Lax'
        }

        // For development, ensure Secure is NOT set (since we're using HTTP)
        modifiedCookie = modifiedCookie.replace(/;\s*Secure/gi, '')

        logger.debug(
          '🍪 Setting cookie:',
          modifiedCookie.substring(0, 100) + '...'
        )
        response.headers.append('Set-Cookie', modifiedCookie)
      })

      // Also set a test cookie that's NOT HttpOnly to verify cookies work at all
      response.headers.append(
        'Set-Cookie',
        'test_cookie=working; Path=/; SameSite=Lax'
      )
    }

    return response
  } catch (error) {
    console.error('❌ Login proxy error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}
