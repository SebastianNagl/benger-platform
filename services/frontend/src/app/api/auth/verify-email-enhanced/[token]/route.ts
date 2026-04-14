import { NextRequest, NextResponse } from 'next/server'
import { logger } from '@/lib/utils/logger'
import { getInternalApiUrl, getExternalHost } from '@/lib/utils/apiUrl'
import { getCookieDomainFromHost } from '@/lib/utils/subdomain'

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ token: string }> }
) {
  try {
    const resolvedParams = await params
    const apiBaseUrl = getInternalApiUrl(request)
    const url = `${apiBaseUrl}/api/auth/verify-email-enhanced/${resolvedParams.token}`

    logger.debug('🔐 Verify email enhanced request:', {
      host: request.headers.get('host'),
      token: resolvedParams.token.substring(0, 20) + '...',
      apiBaseUrl,
      targetUrl: url,
    })

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    })

    const data = await response.json()

    // Create response with the API data
    const nextResponse = NextResponse.json(data, {
      status: response.status,
    })

    // Handle Set-Cookie headers if present
    const setCookieHeaders = response.headers.getSetCookie()
    if (setCookieHeaders && setCookieHeaders.length > 0) {
      setCookieHeaders.forEach((cookieString) => {
        // Remove any existing domain restriction
        let modifiedCookie = cookieString.replace(/Domain=[^;]+;?/gi, '')

        // Set cookie domain for cross-subdomain sharing
        const host = getExternalHost(request)
        const cookieDomain = getCookieDomainFromHost(host)
        if (cookieDomain) {
          modifiedCookie += `; Domain=${cookieDomain}`
        }

        // Ensure SameSite is set appropriately
        if (!modifiedCookie.includes('SameSite')) {
          modifiedCookie += '; SameSite=Lax'
        }

        logger.debug('🍪 Setting cookie from verify-email-enhanced:', {
          original: cookieString.substring(0, 100),
          modified: modifiedCookie.substring(0, 100),
        })

        nextResponse.headers.append('Set-Cookie', modifiedCookie)
      })
    }

    return nextResponse
  } catch (error) {
    console.error('❌ Verify email enhanced error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}
