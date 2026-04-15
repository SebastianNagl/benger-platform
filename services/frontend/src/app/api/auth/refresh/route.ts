import { NextRequest, NextResponse } from 'next/server'
import { logger } from '@/lib/utils/logger'
import { getInternalApiUrl, getExternalHost } from '@/lib/utils/apiUrl'
import { getCookieDomainFromHost } from '@/lib/utils/subdomain'

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

        // Ensure SameSite is set
        if (!modifiedCookie.includes('SameSite')) {
          modifiedCookie += '; SameSite=Lax'
        }

        // Remove Secure for development
        modifiedCookie = modifiedCookie.replace(/;\s*Secure/gi, '')

        response.headers.append('Set-Cookie', modifiedCookie)
      })
    }

    return response
  } catch (error) {
    console.error('❌ Refresh proxy error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}
