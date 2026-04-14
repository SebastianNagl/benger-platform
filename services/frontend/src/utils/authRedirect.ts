import { AppRouterInstance } from 'next/dist/shared/lib/app-router-context.shared-runtime'

// Public routes that don't require authentication
export const publicRoutes = [
  '/', // Landing page
  '/login', // Login page
  '/register', // Registration page
  '/reset-password', // Password reset
  '/verify-email', // Email verification
  '/accept-invitation', // Organization invitation acceptance
  '/about/imprint', // Imprint page
  '/about/data-protection', // Data protection page
]

/**
 * Centralized authentication redirect utilities
 * Helps prevent infinite redirect loops by providing consistent redirect logic
 */
export const authRedirect = {
  /**
   * Redirect to login page (for unauthenticated users)
   */
  toLogin: (router: AppRouterInstance) => {
    router.replace('/login')
  },

  /**
   * Redirect to dashboard (for authenticated users)
   */
  toDashboard: (router: AppRouterInstance) => {
    router.replace('/dashboard')
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
      // Unauthenticated user on protected route should go to landing
      authRedirect.toLogin(router)
    }
    // No redirect needed for other cases
  },
}
