import { NextRequest, NextResponse } from 'next/server'
import { logger } from '@/lib/utils/logger'
import { getCookieDomainFromHost } from '@/lib/utils/subdomain'
import { getInternalApiUrl, getExternalHost } from '@/lib/utils/apiUrl'

// Development debugging
const isDevelopment = process.env.NODE_ENV === 'development'

// Node's default fetch dispatcher imposes a 5-minute `bodyTimeout`: if no body
// bytes are read from the upstream socket for 300s it aborts with
// UND_ERR_BODY_TIMEOUT. For a multi-GB project export (the ZJS dataset is
// ~4.5 GB) the browser pulls the streamed body slowly, backpressure stalls the
// upstream read past 5 minutes, and the download is severed mid-stream — saved
// as a silently-truncated file before the export-completeness fix, now surfaced
// as a TruncatedExportError. A reverse proxy must not cap how long a legitimate
// download streams, so export/download paths fetch through an undici dispatcher
// with the body timeout disabled. `headersTimeout` is left at its default so a
// dead upstream still fails fast. Scoped to export paths only — the 99% CRUD
// path keeps the unchanged global fetch.
//
// undici must be passed to its OWN `fetch`, not Node's global fetch: the global
// fetch's bundled undici rejects a dispatcher built by the npm `undici` package
// ("invalid onError method" — divergent handler interfaces). It is loaded
// lazily because undici's modules reference `ReadableStream` at import time,
// which is absent in the jsdom test environment; deferring the import keeps
// this route module loadable there and only pulls undici in when an export is
// actually proxied (always the Node runtime, where ReadableStream exists).
type UndiciModule = typeof import('undici')
let exportFetcher: Promise<{
  fetch: UndiciModule['fetch']
  dispatcher: InstanceType<UndiciModule['Agent']>
}> | null = null

function getExportFetcher() {
  if (!exportFetcher) {
    exportFetcher = import('undici').then(({ Agent, fetch }) => ({
      fetch,
      dispatcher: new Agent({ bodyTimeout: 0 }),
    }))
  }
  return exportFetcher
}

function isLongLivedDownloadPath(path: string): boolean {
  return path.includes('export')
}

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

// Forward all upstream response headers (skipping ones the runtime owns) and
// rewrite Set-Cookie Domain= so cookies work across multi-org subdomains. Runs
// identically for buffered and streamed bodies — body-independent.
function forwardHeadersAndCookies(
  upstream: Response,
  downstream: NextResponse,
  request: NextRequest
) {
  upstream.headers.forEach((value, key) => {
    if (
      !['content-length', 'transfer-encoding', 'set-cookie'].includes(
        key.toLowerCase()
      )
    ) {
      downstream.headers.set(key, value)
    }
  })

  const setCookieHeaders = upstream.headers.getSetCookie()
  if (setCookieHeaders && setCookieHeaders.length > 0) {
    const host = getExternalHost(request)
    const cookieDomain = getCookieDomainFromHost(host)
    setCookieHeaders.forEach((cookieString) => {
      let modifiedCookie = cookieString.replace(/Domain=[^;]+;?/gi, '')
      if (cookieDomain) {
        modifiedCookie += `; Domain=${cookieDomain}`
      }
      if (!modifiedCookie.includes('SameSite')) {
        modifiedCookie += '; SameSite=Lax'
      }

      logger.debug('Setting cookie:', {
        original: cookieString.substring(0, 100),
        modified: modifiedCookie.substring(0, 100),
      })

      downstream.headers.append('Set-Cookie', modifiedCookie)
    })
  }
}

async function proxyRequest(
  request: NextRequest,
  pathSegments: string[],
  method: string,
  retryCount: number = 0
) {
  try {
    const path = pathSegments.join('/')

    // Auth endpoints that manage session cookies have dedicated handlers
    // under src/app/api/auth/. Public auth endpoints (verify-email,
    // request-password-reset, reset-password) don't touch cookies, so they
    // are allowed through the catch-all here. Adding one to PUBLIC_AUTH_PATHS
    // without a dedicated handler is intentional.
    const PUBLIC_AUTH_PATHS = [
      'verify-email',
      'request-password-reset',
      'reset-password',
    ]
    if (
      path.startsWith('auth/') &&
      !PUBLIC_AUTH_PATHS.some((p) => path.includes(p))
    ) {
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

    // Hybrid body forwarding:
    //   - small requests (the 99% case: JSON CRUD, auth) are buffered once
    //     as ArrayBuffer and handed to fetch. Single copy, no UTF-8 round
    //     trip, fetch sets Content-Length itself, undici is happy.
    //   - large requests (legal-corpus imports in the 10–100 MB range) are
    //     streamed via `request.body` + `duplex: 'half'` to avoid OOM-ing
    //     the frontend pod (the original motivation for streaming).
    //
    // Streaming-only broke small POSTs in prod: undici returned
    // `TypeError: fetch failed` for the wizard's create-project payload
    // (a few KB JSON), surfacing to users as an opaque 500. The 100 MB
    // ASGI guard in services/api/main.py is the backstop for both paths.
    const STREAM_THRESHOLD_BYTES = 5 * 1024 * 1024

    const declaredLength = request.headers.get('content-length')
    const declaredBytes = declaredLength ? parseInt(declaredLength, 10) : NaN
    const shouldStream =
      !Number.isFinite(declaredBytes) || declaredBytes > STREAM_THRESHOLD_BYTES

    let body: BodyInit | undefined
    if (method !== 'GET' && method !== 'HEAD') {
      body = shouldStream
        ? (request.body ?? undefined)
        : await request.arrayBuffer()
    }

    // Forward headers (excluding host and other problematic headers).
    // `content-length` is dropped: when streaming we emit chunked transfer
    // encoding; when buffering, fetch recomputes it from the ArrayBuffer.
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

    // `duplex: 'half'` is required by undici (Node ≥ 18) whenever the body
    // is a ReadableStream. Buffered ArrayBuffer bodies must NOT pass it.
    const fetchInit = {
      method,
      headers,
      body,
      ...(shouldStream && body ? { duplex: 'half' } : {}),
    } as RequestInit & { duplex?: 'half' }

    // Export paths go through undici's own fetch + no-body-timeout dispatcher
    // (see getExportFetcher); the 99% CRUD path keeps Node's global fetch. Both
    // return spec Responses, so downstream handling is identical. undici's
    // `RequestInit` and the DOM lib's diverge on the `body` ReadableStream type,
    // so the init is cast to the type undici's fetch expects.
    let response: Response
    if (isLongLivedDownloadPath(path)) {
      const { fetch: undiciFetch, dispatcher } = await getExportFetcher()
      response = (await undiciFetch(url, {
        ...fetchInit,
        dispatcher,
      } as unknown as Parameters<UndiciModule['fetch']>[1])) as unknown as Response
    } else {
      response = await fetch(url, fetchInit)
    }

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
      forwardHeadersAndCookies(response, nextResponse, request)
      return nextResponse
    }

    // Stream attachment / binary responses through without buffering. Triggered
    // by Content-Disposition: attachment (file downloads — bulk-export sets
    // this even when Content-Type is application/json) or by binary/CSV-style
    // Content-Type. Buffering these via `await response.text()` was OOMing the
    // frontend pod on multi-MB exports (GH #68). Drops `content-length` /
    // `transfer-encoding` (already excluded by the helper) so Node emits
    // chunked transfer encoding correctly.
    const contentDisposition = response.headers.get('content-disposition') ?? ''
    const contentType = (response.headers.get('content-type') ?? '').toLowerCase()
    const isAttachment = /^\s*attachment\b/i.test(contentDisposition)
    const STREAMABLE_TYPES = [
      'application/zip',
      'application/octet-stream',
      'application/pdf',
      'text/csv',
      'text/tab-separated-values',
    ]
    const isStreamableType =
      STREAMABLE_TYPES.some((t) => contentType.startsWith(t)) ||
      contentType.startsWith('image/') ||
      contentType.startsWith('video/') ||
      contentType.startsWith('audio/')

    if (response.body !== null && (isAttachment || isStreamableType)) {
      const streamed = new NextResponse(response.body, {
        status: response.status,
        statusText: response.statusText,
      })
      forwardHeadersAndCookies(response, streamed, request)
      return streamed
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
    forwardHeadersAndCookies(response, nextResponse, request)
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
