import { legacyAnalysisPath } from '@/lib/results/paths'
import { BASE_DOMAINS, isStudentLockedHost } from '@/lib/utils/subdomain'
import type { NextRequest } from 'next/server'
import { NextResponse } from 'next/server'

export function proxy(request: NextRequest) {
  const hostname =
    request.headers.get('x-forwarded-host') || request.headers.get('host') || ''

  // The analysis pages moved under /evaluations: old URLs redirect
  // permanently (308) with their meaning kept.
  const legacy = legacyAnalysisPath(
    request.nextUrl.pathname,
    request.nextUrl.searchParams,
  )
  if (legacy) {
    const url = request.nextUrl.clone()
    const [pathname, query = ''] = legacy.split('?')
    url.pathname = pathname
    url.search = query ? `?${query}` : ''
    return NextResponse.redirect(url, 308)
  }

  // Vertretbar: serve the dedicated student landing at the apex root, decided
  // server-side from the host header so there's no benger-branding flash. The
  // URL stays "/"; the /vertretbar route renders the VertretbarLanding slot.
  if (request.nextUrl.pathname === '/' && isStudentLockedHost(hostname)) {
    const url = request.nextUrl.clone()
    url.pathname = '/vertretbar'
    return NextResponse.rewrite(url)
  }

  const response = NextResponse.next()

  // Set proper MIME types for CSS files
  if (request.nextUrl.pathname.endsWith('.css')) {
    response.headers.set('Content-Type', 'text/css')
  }

  // Set proper MIME types for JavaScript files
  if (request.nextUrl.pathname.endsWith('.js')) {
    response.headers.set('Content-Type', 'application/javascript')
  }

  // Set proper MIME types for SVG files
  if (request.nextUrl.pathname.endsWith('.svg')) {
    response.headers.set('Content-Type', 'image/svg+xml')
  }

  // Extract org slug from subdomain for organization context
  for (const baseDomain of BASE_DOMAINS) {
    if (hostname.endsWith(`.${baseDomain}`) && hostname !== baseDomain) {
      const subdomain = hostname.replace(`.${baseDomain}`, '')
      if (subdomain && !subdomain.includes('.')) {
        response.headers.set('x-org-slug', subdomain)
      }
      break
    }
  }

  return response
}

export const config = {
  // Skip all paths that should not be internationalized
  matcher: ['/((?!api|_next|_vercel|.*\\..*).*)'],
}
