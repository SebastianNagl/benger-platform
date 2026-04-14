import { NextRequest } from 'next/server'

/**
 * Get the external-facing hostname from the request.
 * Behind reverse proxies (traefik/k8s ingress), the Host header contains the
 * internal service name. The real hostname is in X-Forwarded-Host.
 */
export function getExternalHost(request: NextRequest): string {
  return (
    request.headers.get('x-forwarded-host') ||
    request.headers.get('host') ||
    ''
  )
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
  if (host.includes('benger.localhost')) return 'http://api:8000'
  if (host.includes('localhost:3000') || host.includes('localhost:3001')) {
    return process.env.DOCKER_INTERNAL_API_URL
      ? 'http://api:8000'
      : 'http://localhost:8001'
  }
  if (host.includes('what-a-benger.net')) {
    return (
      process.env.DOCKER_INTERNAL_API_URL ||
      process.env.API_URL ||
      'http://benger-api:8000'
    )
  }

  // Fallback
  return process.env.DOCKER_INTERNAL_API_URL || 'http://api:8000'
}
