import type { NextRequest } from 'next/server'
import { NextResponse } from 'next/server'
import { BASE_DOMAINS } from '@/lib/utils/subdomain'

export function middleware(request: NextRequest) {
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
  const hostname = request.headers.get('x-forwarded-host') || request.headers.get('host') || ''
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
