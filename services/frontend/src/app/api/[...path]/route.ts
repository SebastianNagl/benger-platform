import { NextRequest, NextResponse } from 'next/server'
import { logger } from '@/lib/utils/logger'
import { getCookieDomainFromHost } from '@/lib/utils/subdomain'
import { getInternalApiUrl, getExternalHost } from '@/lib/utils/apiUrl'

// Development debugging
const isDevelopment = process.env.NODE_ENV === 'development'

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const resolvedParams = await params
  return proxyRequest(request, resolvedParams.path, 'GET')
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const resolvedParams = await params
  return proxyRequest(request, resolvedParams.path, 'POST')
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const resolvedParams = await params
  return proxyRequest(request, resolvedParams.path, 'PUT')
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const resolvedParams = await params
  return proxyRequest(request, resolvedParams.path, 'PATCH')
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const resolvedParams = await params
  return proxyRequest(request, resolvedParams.path, 'DELETE')
}

async function proxyRequest(
  request: NextRequest,
  pathSegments: string[],
  method: string,
  retryCount: number = 0
) {
  try {
    const path = pathSegments.join('/')

    // Allow verify-email endpoints through the catch-all
    // Other auth endpoints have dedicated handlers for cookie management
    if (path.startsWith('auth/') && !path.includes('verify-email')) {
      logger.debug('Auth endpoint should use dedicated handler:', path)
      return NextResponse.json(
        { error: 'Use dedicated auth handler' },
        { status: 400 }
      )
    }

    // Include query parameters from the original request
    const searchParams = request.nextUrl.searchParams.toString()
    const apiBaseUrl = getInternalApiUrl(request)

    // The backend API now has all endpoints under /api/*
    // Including auth which is at /api/auth/*
    // Since our Next.js route is /api/[...path], we just pass through
    let url: string = `${apiBaseUrl}/api/${path}${searchParams ? `?${searchParams}` : ''}`

    // Debug logging
    logger.debug(`🔄 Proxying ${method} request:`, {
      host: request.headers.get('host'),
      originalPath: `/${path}`,
      targetUrl: url,
      apiBaseUrl,
      nodeEnv: process.env.NODE_ENV,
    })

    // Get the request body if it exists
    let body: string | undefined
    if (method !== 'GET') {
      try {
        body = await request.text()
      } catch (e) {
        // No body or invalid body
      }
    }

    // Forward headers (excluding host and other problematic headers)
    const headers = new Headers()
    request.headers.forEach((value, key) => {
      if (
        !['host', 'connection', 'content-length'].includes(key.toLowerCase())
      ) {
        headers.set(key, value)
      }
    })

    // Ensure cookies are forwarded
    const cookies = request.headers.get('cookie')
    if (cookies) {
      headers.set('cookie', cookies)
    }

    // Make the request to the backend API
    const response = await fetch(url, {
      method,
      headers,
      body,
    })

    logger.debug(`✅ API response received:`, {
      status: response.status,
      statusText: response.statusText,
      url,
    })

    // Handle service restart scenarios - retry 502/503 errors
    if ([502, 503].includes(response.status) && retryCount < 3) {
      logger.debug(
        `⚠️ Service temporarily unavailable (${response.status}), retrying in ${(retryCount + 1) * 1000}ms... (attempt ${retryCount + 1}/3)`
      )

      // Special handling for annotation endpoints
      if (path.includes('annotations')) {
        logger.debug('Annotation endpoint detected, using longer retry delay')
        await new Promise((resolve) =>
          setTimeout(resolve, (retryCount + 1) * 2000)
        )
      } else {
        await new Promise((resolve) =>
          setTimeout(resolve, (retryCount + 1) * 1000)
        )
      }

      // Create a new request with fresh body content
      const newRequest = request.clone() as NextRequest
      return proxyRequest(newRequest, pathSegments, method, retryCount + 1)
    }
    // Handle 204 No Content responses
    if (response.status === 204) {
      const nextResponse = new NextResponse(null, {
        status: 204,
        statusText: response.statusText,
      })

      // Forward response headers, with special handling for Set-Cookie headers
      response.headers.forEach((value, key) => {
        if (
          !['content-length', 'transfer-encoding', 'set-cookie'].includes(
            key.toLowerCase()
          )
        ) {
          nextResponse.headers.set(key, value)
        }
      })

      // Handle Set-Cookie headers specially - they need to be appended, not set
      const setCookieHeaders = response.headers.getSetCookie()
      if (setCookieHeaders && setCookieHeaders.length > 0) {
        const host = getExternalHost(request)
        const cookieDomain = getCookieDomainFromHost(host)
        setCookieHeaders.forEach((cookieString) => {
          // Remove any existing domain restriction
          let modifiedCookie = cookieString.replace(/Domain=[^;]+;?/gi, '')

          // Set cookie domain for cross-subdomain sharing
          if (cookieDomain) {
            modifiedCookie += `; Domain=${cookieDomain}`
          }

          // Also ensure SameSite is set to Lax for development
          if (!modifiedCookie.includes('SameSite')) {
            modifiedCookie += '; SameSite=Lax'
          }

          logger.debug('Setting cookie (204):', {
            original: cookieString.substring(0, 100),
            modified: modifiedCookie.substring(0, 100),
          })

          nextResponse.headers.append('Set-Cookie', modifiedCookie)
        })
      }

      return nextResponse
    }

    // Get response data for other status codes
    let responseData: string
    try {
      responseData = await response.text()
    } catch (error) {
      console.error('❌ Failed to read response body:', error)
      responseData = ''
    }

    // Log response details for debugging
    if (isDevelopment) {
      logger.debug(`📝 Response data preview:`, responseData.substring(0, 200))
    }

    // Create response with same status and headers
    const nextResponse = new NextResponse(responseData, {
      status: response.status,
      statusText: response.statusText,
    })

    // Forward response headers, with special handling for Set-Cookie headers
    response.headers.forEach((value, key) => {
      if (
        !['content-length', 'transfer-encoding', 'set-cookie'].includes(
          key.toLowerCase()
        )
      ) {
        nextResponse.headers.set(key, value)
      }
    })

    // Handle Set-Cookie headers specially - they need to be appended, not set
    const setCookieHeaders = response.headers.getSetCookie()
    if (setCookieHeaders && setCookieHeaders.length > 0) {
      const host = getExternalHost(request)
      const cookieDomain = getCookieDomainFromHost(host)
      setCookieHeaders.forEach((cookieString) => {
        // Remove any existing domain restriction
        let modifiedCookie = cookieString.replace(/Domain=[^;]+;?/gi, '')

        // Set cookie domain for cross-subdomain sharing
        if (cookieDomain) {
          modifiedCookie += `; Domain=${cookieDomain}`
        }

        // Also ensure SameSite is set to Lax for development
        if (!modifiedCookie.includes('SameSite')) {
          modifiedCookie += '; SameSite=Lax'
        }

        logger.debug('Setting cookie:', {
          original: cookieString.substring(0, 100),
          modified: modifiedCookie.substring(0, 100),
        })

        nextResponse.headers.append('Set-Cookie', modifiedCookie)
      })
    }

    return nextResponse
  } catch (error) {
    console.error('❌ Proxy error:', {
      error: error instanceof Error ? error.message : String(error),
      stack: error instanceof Error ? error.stack : undefined,
      url: `${getInternalApiUrl(request)}/${pathSegments.join('/')}`,
    })
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}
