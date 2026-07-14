import { AppRouterInstance } from 'next/dist/shared/lib/app-router-context.shared-runtime'

import { isStudentLockedHost } from '@/lib/utils/subdomain'

// Public routes that don't require authentication
export const publicRoutes = [
  '/', // Landing page
  '/vertretbar', // Vertretbar landing (student-locked hosts; "/" rewrites here)
  '/login', // Login page
  '/register', // Registration page
  '/reset-password', // Password reset
  '/verify-email', // Email verification
  '/accept-invitation', // Organization invitation acceptance
  '/shares', // Exam-share join page — invitees land here before logging in (Issue #35)
  '/lti/error', // LTI launch errors: most failures (invalid token, disabled
  // registration, unavailable state store) abort BEFORE a session is minted,
  // so the explanation page must render unauthenticated (issue #61).
  '/about/imprint', // Imprint page
  '/about/data-protection', // Data protection page
]

/**
 * Centralized authentication redirect utilities
 * Helps prevent infinite redirect loops by providing consistent redirect logic
 */
export const authRedirect = {
  /**
   * Sanitize a return-to path so it can only point at an internal route
   * (guards against open-redirect). Returns null when the path is missing,
   * not root-relative, protocol-relative, or itself the login page.
   */
  sanitizeNext: (path: string | null | undefined): string | null => {
    if (!path) return null
    if (!path.startsWith('/') || path.startsWith('//')) return null
    if (path === '/login' || path.startsWith('/login?')) return null
    return path
  },

  /**
   * Redirect to login page (for unauthenticated users). When `returnTo` is a
   * safe internal path, preserve it as ?next= so the login flow can send the
   * user back to where they were headed after authenticating (Issue #35).
   */
  toLogin: (router: AppRouterInstance, returnTo?: string | null) => {
    const next = authRedirect.sanitizeNext(returnTo)
    router.replace(next ? `/login?next=${encodeURIComponent(next)}` : '/login')
  },

  /**
   * The home path for an authenticated user. On a student-locked host
   * (vertretbar.net) that's the student area — never the benger dashboard.
   */
  defaultAuthedPath: (): string =>
    isStudentLockedHost() ? '/student' : '/dashboard',

  /**
   * Redirect to the authenticated home (dashboard, or /student on a
   * student-locked host).
   */
  toDashboard: (router: AppRouterInstance) => {
    router.replace(authRedirect.defaultAuthedPath())
  },

  /**
   * Check if a route is protected (requires authentication)
   */
  isProtectedRoute: (pathname: string): boolean => {
    // Check if path matches or starts with any public route
    const isPublic = publicRoutes.some((route) => {
      if (route === '/') {
        return pathname === '/'
      }
      return pathname === route || pathname.startsWith(route)
    })
    return !isPublic && !pathname.startsWith('/about')
  },

  /**
   * Check if a route is public (no authentication required)
   */
  isPublicRoute: (pathname: string): boolean => {
    // Check if path matches or starts with any public route
    const matchesPublicRoute = publicRoutes.some((route) => {
      if (route === '/') {
        return pathname === '/'
      }
      return pathname === route || pathname.startsWith(route)
    })
    return matchesPublicRoute || pathname.startsWith('/about')
  },

  /**
   * Get the appropriate redirect for a user's auth state
   */
  getRedirectForAuthState: (
    isAuthenticated: boolean,
    currentPath: string,
    router: AppRouterInstance
  ) => {
    const isPublic = authRedirect.isPublicRoute(currentPath)

    if (isAuthenticated && isPublic && currentPath === '/') {
      // Authenticated user on landing page should go to dashboard
      authRedirect.toDashboard(router)
    } else if (!isAuthenticated && !isPublic) {
      // Unauthenticated user on protected route should go to login
      authRedirect.toLogin(router)
    }
    // No redirect needed for other cases
  },
}
