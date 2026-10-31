import { NextRequest, NextResponse } from 'next/server'

/**
 * Get the external-facing hostname from the request.
 * Behind reverse proxies (traefik/k8s ingress), the Host header contains the
 * internal service name. The real hostname is in X-Forwarded-Host.
 */
export function getExternalHost(request: NextRequest): string {
  return (
    request.headers.get('x-forwarded-host') || request.headers.get('host') || ''
  )
}

/**
 * The `x-forwarded-for` header to send upstream, unchanged.
 *
 * The API keys its per-IP auth limits on the rightmost X-Forwarded-For hop,
 * the one the ingress (Traefik) appended. Calls from this server to the API
 * open a new connection, so without this header the API would see the
 * frontend pod as the client and put every visitor into one bucket. When an
 * ingress sent only X-Real-Ip, that address stands in for the chain.
 */
export function forwardedForHeaders(
  request: NextRequest,
): Record<string, string> {
  const chain =
    request.headers.get('x-forwarded-for') || request.headers.get('x-real-ip')
  return chain ? { 'x-forwarded-for': chain } : {}
}

/**
 * Copy a 429's `Retry-After` from the API response onto the proxy response
 * (the dedicated auth routes rebuild the response and would drop it).
 */
export function copyRetryAfter(
  upstream: Response,
  downstream: NextResponse,
): void {
  if (upstream.status !== 429) return
  const retryAfter = upstream.headers?.get?.('retry-after')
  if (retryAfter) downstream.headers.set('Retry-After', retryAfter)
}

/**
 * Resolve the internal API base URL for server-side proxy routes.
 *
 * Priority:
 * 1. INTERNAL_API_URL env var (canonical)
 * 2. API_BASE_URL env var (backwards compat, docker-compose dev)
 * 3. Host-based detection using x-forwarded-host (handles traefik/k8s)
 * 4. DOCKER_INTERNAL_API_URL fallback
 * 5. Default: http://api:8000
 */
export function getInternalApiUrl(request: NextRequest): string {
  const host = getExternalHost(request)

  // Explicit env var override (highest priority)
  if (process.env.INTERNAL_API_URL) return process.env.INTERNAL_API_URL
  if (process.env.API_BASE_URL) return process.env.API_BASE_URL

  // Host-based detection
  if (host.includes('benger-test.localhost')) return 'http://test-api:8000'
  // Vertretbar shares the same backend as benger (dev: the api service).
  if (
    host.includes('benger.localhost') ||
    host.includes('vertretbar.localhost')
  )
    return 'http://api:8000'
  if (host.includes('localhost:3000') || host.includes('localhost:3001')) {
    return process.env.DOCKER_INTERNAL_API_URL
      ? 'http://api:8000'
      : 'http://localhost:8001'
  }
  if (host.includes('what-a-benger.net') || host.includes('vertretbar.net')) {
    return (
      process.env.DOCKER_INTERNAL_API_URL ||
      process.env.API_URL ||
      'http://benger-api:8000'
    )
  }

  // Fallback
  return process.env.DOCKER_INTERNAL_API_URL || 'http://api:8000'
}
