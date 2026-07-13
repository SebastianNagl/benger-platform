import { NextRequest, NextResponse } from 'next/server'
import { logger } from '@/lib/utils/logger'
import { getInternalApiUrl, getExternalHost } from '@/lib/utils/apiUrl'
import { getCookieDomainFromHost } from '@/lib/utils/subdomain'

/**
 * Dedicated proxy for the LTI tool endpoints (/api/lti/*).
 *
 * The generic catch-all proxy cannot carry these: it follows redirects
 * server-side (fetch default), so the launch endpoint's `303 + Set-Cookie`
 * would be consumed inside the proxy and the browser would never navigate.
 * LTI flows are redirect-driven (OIDC login init 302s to the platform, the
 * launch 303s into the app), so this handler uses `redirect: 'manual'` and
 * passes 3xx responses through verbatim.
 *
 * A more specific route segment wins over the dynamic catch-all in the App
 * Router, so every /api/lti/* request lands here and nowhere else.
 *
 * Cookie handling mirrors the dedicated auth handlers: strip the upstream
 * Domain, re-scope to the requesting host (multi-host: vertretbar.* and
 * *.what-a-benger.net families), preserve an explicit SameSite, and drop
 * Secure outside production so plain-HTTP dev setups keep working.
 */

const HOP_BY_HOP_REQUEST_HEADERS = ['host', 'connection', 'content-length']

async function proxyLti(request: NextRequest): Promise<NextResponse> {
  const path = request.nextUrl.pathname.replace(/^\/api\/lti\//, '')
  const search = request.nextUrl.search
  const apiBaseUrl = getInternalApiUrl(request)
  const targetUrl = `${apiBaseUrl}/api/lti/${path}${search}`

  const headers = new Headers()
  request.headers.forEach((value, key) => {
    if (!HOP_BY_HOP_REQUEST_HEADERS.includes(key.toLowerCase())) {
      headers.set(key, value)
    }
  })
  // The API builds browser-facing URLs (OIDC redirect_uri) from the
  // original host — same convention as the catch-all proxy.
  headers.set('x-forwarded-host', getExternalHost(request))
  if (!headers.has('x-forwarded-proto')) {
    headers.set('x-forwarded-proto', request.nextUrl.protocol.replace(':', ''))
  }

  const init: RequestInit = {
    method: request.method,
    headers,
    redirect: 'manual', // pass 3xx through to the browser — the whole point
  }
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    const body = await request.arrayBuffer()
    if (body.byteLength > 0) {
      init.body = body
      // duplex is required by undici when streaming a body; a buffered
      // ArrayBuffer does not need it.
    }
  }

  let backendResponse: Response
  try {
    backendResponse = await fetch(targetUrl, init)
  } catch (error) {
    logger.error('LTI proxy error:', error)
    return NextResponse.json({ error: 'LTI upstream unreachable' }, { status: 502 })
  }

  const responseHeaders = new Headers()
  backendResponse.headers.forEach((value, key) => {
    const k = key.toLowerCase()
    if (k === 'set-cookie' || k === 'content-length' || k === 'content-encoding' || k === 'transfer-encoding') {
      return
    }
    responseHeaders.set(key, value)
  })

  // Re-scope cookies to the host the browser is actually on.
  const host = getExternalHost(request)
  const cookieDomain = getCookieDomainFromHost(host)
  const isProduction = process.env.NODE_ENV === 'production'
  for (const cookie of backendResponse.headers.getSetCookie()) {
    let modified = cookie.replace(/Domain=[^;]+;?\s*/gi, '')
    if (cookieDomain) {
      modified += `; Domain=${cookieDomain}`
    }
    if (!/Path=/i.test(modified)) {
      modified += '; Path=/'
    }
    if (!/SameSite=/i.test(modified)) {
      modified += '; SameSite=Lax'
    }
    if (!isProduction) {
      modified = modified.replace(/;\s*Secure/gi, '')
    }
    responseHeaders.append('Set-Cookie', modified)
  }

  const status = backendResponse.status
  // 3xx and 204/304 responses must not carry a body.
  if ((status >= 300 && status < 400) || status === 204 || status === 304) {
    return new NextResponse(null, { status, headers: responseHeaders })
  }
  const body = await backendResponse.arrayBuffer()
  return new NextResponse(body, { status, headers: responseHeaders })
}

export async function GET(request: NextRequest) {
  return proxyLti(request)
}

export async function POST(request: NextRequest) {
  return proxyLti(request)
}
