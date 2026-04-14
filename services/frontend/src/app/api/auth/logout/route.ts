import { NextRequest, NextResponse } from 'next/server'
import { logger } from '@/lib/utils/logger'
import { getInternalApiUrl, getExternalHost } from '@/lib/utils/apiUrl'
import { getCookieDomainFromHost } from '@/lib/utils/subdomain'

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

    // Clear cookies by setting them with expired dates
    const host = getExternalHost(request)
    const cookieDomain = getCookieDomainFromHost(host)
    const domainAttr = cookieDomain ? `; Domain=${cookieDomain}` : ''
    response.headers.append(
      'Set-Cookie',
      `access_token=; Path=/; Max-Age=0; HttpOnly${domainAttr}`
    )
    response.headers.append(
      'Set-Cookie',
      `refresh_token=; Path=/; Max-Age=0; HttpOnly${domainAttr}`
    )

    logger.debug('🍪 Cookies cleared')

    return response
  } catch (error) {
    console.error('❌ Logout proxy error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}
