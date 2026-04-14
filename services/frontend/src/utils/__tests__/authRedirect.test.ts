/**
 * Comprehensive tests for authRedirect utility
 * Tests public routes, protected routes, redirect functions, and authentication state handling
 */

import { AppRouterInstance } from 'next/dist/shared/lib/app-router-context.shared-runtime'
import { authRedirect, publicRoutes } from '../authRedirect'

// Mock Next.js router
const mockRouter: jest.Mocked<AppRouterInstance> = {
  replace: jest.fn(),
  push: jest.fn(),
  refresh: jest.fn(),
  back: jest.fn(),
  forward: jest.fn(),
  prefetch: jest.fn(),
} as any

describe('authRedirect', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('publicRoutes array', () => {
    it('should include all expected public routes', () => {
      const expectedRoutes = [
        '/',
        '/login',
        '/register',
        '/reset-password',
        '/verify-email',
        '/accept-invitation',
        '/about/imprint',
        '/about/data-protection',
      ]

      expect(publicRoutes).toEqual(expectedRoutes)
      expect(publicRoutes).toHaveLength(8)
    })

    it('should contain unique routes only', () => {
      const uniqueRoutes = [...new Set(publicRoutes)]
      expect(uniqueRoutes).toEqual(publicRoutes)
    })

    it('should have all routes starting with forward slash', () => {
      publicRoutes.forEach((route) => {
        expect(route).toMatch(/^\//)
      })
    })
  })

  describe('toLogin', () => {
    it('should redirect to login page using router.replace', () => {
      authRedirect.toLogin(mockRouter)

      expect(mockRouter.replace).toHaveBeenCalledWith('/login')
      expect(mockRouter.replace).toHaveBeenCalledTimes(1)
    })

    it('should not call other router methods', () => {
      authRedirect.toLogin(mockRouter)

      expect(mockRouter.push).not.toHaveBeenCalled()
      expect(mockRouter.refresh).not.toHaveBeenCalled()
      expect(mockRouter.back).not.toHaveBeenCalled()
      expect(mockRouter.forward).not.toHaveBeenCalled()
    })
  })

  describe('toDashboard', () => {
    it('should redirect to dashboard using router.replace', () => {
      authRedirect.toDashboard(mockRouter)

      expect(mockRouter.replace).toHaveBeenCalledWith('/dashboard')
      expect(mockRouter.replace).toHaveBeenCalledTimes(1)
    })

    it('should not call other router methods', () => {
      authRedirect.toDashboard(mockRouter)

      expect(mockRouter.push).not.toHaveBeenCalled()
      expect(mockRouter.refresh).not.toHaveBeenCalled()
      expect(mockRouter.back).not.toHaveBeenCalled()
      expect(mockRouter.forward).not.toHaveBeenCalled()
    })
  })

  describe('isProtectedRoute', () => {
    it('should return false for public routes from the publicRoutes array', () => {
      publicRoutes.forEach((route) => {
        expect(authRedirect.isProtectedRoute(route)).toBe(false)
      })
    })

    it('should return false for /about paths', () => {
      const aboutPaths = [
        '/about',
        '/about/',
        '/about/terms',
        '/about/privacy',
        '/about/contact',
        '/about/something-else',
      ]

      aboutPaths.forEach((path) => {
        expect(authRedirect.isProtectedRoute(path)).toBe(false)
      })
    })

    it('should return true for protected routes', () => {
      const protectedRoutes = [
        '/dashboard',
        '/projects',
        '/projects/123',
        '/tasks',
        '/tasks/456',
        '/settings',
        '/profile',
        '/admin',
        '/api',
        '/analytics',
      ]

      protectedRoutes.forEach((route) => {
        expect(authRedirect.isProtectedRoute(route)).toBe(true)
      })
    })

    it('should handle edge cases correctly', () => {
      // Empty string
      expect(authRedirect.isProtectedRoute('')).toBe(true)

      // Paths that start with /about are considered public
      expect(authRedirect.isProtectedRoute('/aboutme')).toBe(false) // starts with '/about'
      expect(authRedirect.isProtectedRoute('/user/about')).toBe(true) // doesn't start with '/about'

      // Case sensitivity - startsWith is case sensitive
      expect(authRedirect.isProtectedRoute('/LOGIN')).toBe(true)
      expect(authRedirect.isProtectedRoute('/ABOUT')).toBe(true) // case sensitive, so not matching '/about'
    })

    it('should handle paths with query parameters and fragments', () => {
      expect(authRedirect.isProtectedRoute('/dashboard?tab=analytics')).toBe(
        true
      )
      expect(authRedirect.isProtectedRoute('/login?redirect=/dashboard')).toBe(
        false
      ) // login page is public, even with query params
      expect(authRedirect.isProtectedRoute('/about/imprint#section1')).toBe(
        false
      ) // starts with '/about'
    })
  })

  describe('isPublicRoute', () => {
    it('should return true for public routes from the publicRoutes array', () => {
      publicRoutes.forEach((route) => {
        expect(authRedirect.isPublicRoute(route)).toBe(true)
      })
    })

    it('should return true for /about paths', () => {
      const aboutPaths = [
        '/about',
        '/about/',
        '/about/terms',
        '/about/privacy',
        '/about/contact',
        '/about/something-else',
      ]

      aboutPaths.forEach((path) => {
        expect(authRedirect.isPublicRoute(path)).toBe(true)
      })
    })

    it('should return false for protected routes', () => {
      const protectedRoutes = [
        '/dashboard',
        '/projects',
        '/projects/123',
        '/tasks',
        '/tasks/456',
        '/settings',
        '/profile',
        '/admin',
        '/api',
        '/analytics',
      ]

      protectedRoutes.forEach((route) => {
        expect(authRedirect.isPublicRoute(route)).toBe(false)
      })
    })

    it('should be the logical inverse of isProtectedRoute', () => {
      const testPaths = [
        '/',
        '/login',
        '/register',
        '/about/terms',
        '/dashboard',
        '/projects',
        '/tasks/123',
        '/aboutme',
        '/user/about',
        '',
      ]

      testPaths.forEach((path) => {
        expect(authRedirect.isPublicRoute(path)).toBe(
          !authRedirect.isProtectedRoute(path)
        )
      })
    })
  })

  describe('getRedirectForAuthState', () => {
    describe('authenticated user scenarios', () => {
      it('should redirect authenticated user from landing page to dashboard', () => {
        authRedirect.getRedirectForAuthState(true, '/', mockRouter)

        expect(mockRouter.replace).toHaveBeenCalledWith('/dashboard')
        expect(mockRouter.replace).toHaveBeenCalledTimes(1)
      })

      it('should not redirect authenticated user on other public routes', () => {
        const publicPaths = [
          '/login',
          '/register',
          '/accept-invitation/some-token',
          '/about/imprint',
          '/about/terms',
        ]

        publicPaths.forEach((path) => {
          jest.clearAllMocks()
          authRedirect.getRedirectForAuthState(true, path, mockRouter)
          expect(mockRouter.replace).not.toHaveBeenCalled()
        })
      })

      it('should not redirect authenticated user on protected routes', () => {
        const protectedPaths = [
          '/dashboard',
          '/projects',
          '/tasks/123',
          '/settings',
        ]

        protectedPaths.forEach((path) => {
          jest.clearAllMocks()
          authRedirect.getRedirectForAuthState(true, path, mockRouter)
          expect(mockRouter.replace).not.toHaveBeenCalled()
        })
      })
    })

    describe('unauthenticated user scenarios', () => {
      it('should redirect unauthenticated user from protected routes to login page', () => {
        const protectedPaths = [
          '/dashboard',
          '/projects',
          '/tasks/123',
          '/settings',
          '/admin',
        ]

        protectedPaths.forEach((path) => {
          jest.clearAllMocks()
          authRedirect.getRedirectForAuthState(false, path, mockRouter)

          expect(mockRouter.replace).toHaveBeenCalledWith('/login')
          expect(mockRouter.replace).toHaveBeenCalledTimes(1)
        })
      })

      it('should not redirect unauthenticated user on public routes', () => {
        const publicPaths = [
          '/',
          '/login',
          '/register',
          '/about/imprint',
          '/about/terms',
        ]

        publicPaths.forEach((path) => {
          jest.clearAllMocks()
          authRedirect.getRedirectForAuthState(false, path, mockRouter)
          expect(mockRouter.replace).not.toHaveBeenCalled()
        })
      })
    })

    describe('edge cases and comprehensive scenarios', () => {
      it('should handle empty path correctly', () => {
        // Empty path is considered protected
        authRedirect.getRedirectForAuthState(false, '', mockRouter)
        expect(mockRouter.replace).toHaveBeenCalledWith('/login')

        jest.clearAllMocks()
        authRedirect.getRedirectForAuthState(true, '', mockRouter)
        expect(mockRouter.replace).not.toHaveBeenCalled()
      })

      it('should handle paths with query parameters', () => {
        // Login page with query params is still public, no redirect needed
        authRedirect.getRedirectForAuthState(
          false,
          '/login?redirect=/dashboard',
          mockRouter
        )
        expect(mockRouter.replace).not.toHaveBeenCalled()

        jest.clearAllMocks()
        // Protected route with query params
        authRedirect.getRedirectForAuthState(
          false,
          '/dashboard?tab=analytics',
          mockRouter
        )
        expect(mockRouter.replace).toHaveBeenCalledWith('/login')
      })

      it('should handle complex about paths', () => {
        const aboutPaths = [
          '/about/privacy/policy',
          '/about/terms/service',
          '/about/team/members',
        ]

        aboutPaths.forEach((path) => {
          jest.clearAllMocks()
          // Unauthenticated user on about paths should not redirect
          authRedirect.getRedirectForAuthState(false, path, mockRouter)
          expect(mockRouter.replace).not.toHaveBeenCalled()

          // Authenticated user on about paths should not redirect
          authRedirect.getRedirectForAuthState(true, path, mockRouter)
          expect(mockRouter.replace).not.toHaveBeenCalled()
        })
      })

      it('should handle nested protected routes', () => {
        const nestedRoutes = [
          '/projects/123/tasks',
          '/projects/123/tasks/456/annotations',
          '/admin/users/management',
          '/settings/profile/security',
        ]

        nestedRoutes.forEach((route) => {
          jest.clearAllMocks()
          authRedirect.getRedirectForAuthState(false, route, mockRouter)
          expect(mockRouter.replace).toHaveBeenCalledWith('/login')
        })
      })
    })

    describe('consistency with route checking functions', () => {
      it('should use isPublicRoute internally for consistency', () => {
        const testPaths = [
          '/',
          '/login',
          '/register',
          '/about/terms',
          '/dashboard',
          '/projects',
          '/tasks/123',
        ]

        testPaths.forEach((path) => {
          const isPublic = authRedirect.isPublicRoute(path)

          jest.clearAllMocks()

          // Test authenticated user
          authRedirect.getRedirectForAuthState(true, path, mockRouter)
          const shouldRedirectAuth = path === '/' && isPublic

          if (shouldRedirectAuth) {
            expect(mockRouter.replace).toHaveBeenCalledWith('/dashboard')
          } else {
            expect(mockRouter.replace).not.toHaveBeenCalled()
          }

          jest.clearAllMocks()

          // Test unauthenticated user
          authRedirect.getRedirectForAuthState(false, path, mockRouter)
          const shouldRedirectUnauth = !isPublic

          if (shouldRedirectUnauth) {
            expect(mockRouter.replace).toHaveBeenCalledWith('/login')
          } else {
            expect(mockRouter.replace).not.toHaveBeenCalled()
          }
        })
      })
    })
  })

  describe('integration scenarios', () => {
    it('should handle typical user authentication flow', () => {
      // 1. Unauthenticated user visits dashboard - should redirect to landing
      authRedirect.getRedirectForAuthState(false, '/dashboard', mockRouter)
      expect(mockRouter.replace).toHaveBeenCalledWith('/login')

      jest.clearAllMocks()

      // 2. User goes to login page - should not redirect
      authRedirect.getRedirectForAuthState(false, '/login', mockRouter)
      expect(mockRouter.replace).not.toHaveBeenCalled()

      // 3. After login, user goes to login page - should redirect to dashboard
      authRedirect.getRedirectForAuthState(true, '/', mockRouter)
      expect(mockRouter.replace).toHaveBeenCalledWith('/dashboard')

      jest.clearAllMocks()

      // 4. Authenticated user accesses dashboard - should not redirect
      authRedirect.getRedirectForAuthState(true, '/dashboard', mockRouter)
      expect(mockRouter.replace).not.toHaveBeenCalled()
    })

    it('should handle admin access patterns', () => {
      // Admin route should be protected
      expect(authRedirect.isProtectedRoute('/admin')).toBe(true)
      expect(authRedirect.isProtectedRoute('/admin/users')).toBe(true)
      expect(authRedirect.isProtectedRoute('/admin/settings')).toBe(true)

      // Unauthenticated access to admin should redirect
      authRedirect.getRedirectForAuthState(false, '/admin', mockRouter)
      expect(mockRouter.replace).toHaveBeenCalledWith('/login')

      jest.clearAllMocks()

      // Authenticated access to admin should not redirect
      authRedirect.getRedirectForAuthState(true, '/admin', mockRouter)
      expect(mockRouter.replace).not.toHaveBeenCalled()
    })

    it('should handle user registration and verification flow', () => {
      const registrationPaths = [
        '/register',
        '/verify-email',
        '/reset-password',
      ]

      registrationPaths.forEach((path) => {
        // These paths should be public
        expect(authRedirect.isPublicRoute(path)).toBe(true)
        expect(authRedirect.isProtectedRoute(path)).toBe(false)

        // No redirects should happen on these paths
        jest.clearAllMocks()
        authRedirect.getRedirectForAuthState(false, path, mockRouter)
        expect(mockRouter.replace).not.toHaveBeenCalled()

        authRedirect.getRedirectForAuthState(true, path, mockRouter)
        expect(mockRouter.replace).not.toHaveBeenCalled()
      })
    })
  })

  describe('performance and edge case robustness', () => {
    it('should handle rapid successive calls without interference', () => {
      // Simulate rapid navigation
      authRedirect.getRedirectForAuthState(false, '/dashboard', mockRouter)
      authRedirect.getRedirectForAuthState(false, '/projects', mockRouter)
      authRedirect.getRedirectForAuthState(false, '/tasks', mockRouter)

      // Should have 3 redirects to login page
      expect(mockRouter.replace).toHaveBeenCalledTimes(3)
      expect(mockRouter.replace).toHaveBeenNthCalledWith(1, '/login')
      expect(mockRouter.replace).toHaveBeenNthCalledWith(2, '/login')
      expect(mockRouter.replace).toHaveBeenNthCalledWith(3, '/login')
    })

    it('should handle malformed or unusual paths gracefully', () => {
      const unusualPaths = [
        '//double/slash',
        '/path/with/./dot',
        '/path/with/../parent',
        '/path with spaces',
        '/path/with/émojis/🚀',
        '/CAPS/path',
        '/path?query=value&other=value',
        '/path#fragment',
        '/path?query=value#fragment',
      ]

      unusualPaths.forEach((path) => {
        // Should not throw errors
        expect(() => authRedirect.isPublicRoute(path)).not.toThrow()
        expect(() => authRedirect.isProtectedRoute(path)).not.toThrow()
        expect(() =>
          authRedirect.getRedirectForAuthState(false, path, mockRouter)
        ).not.toThrow()
        expect(() =>
          authRedirect.getRedirectForAuthState(true, path, mockRouter)
        ).not.toThrow()
      })
    })

    it('should maintain logical consistency across all functions', () => {
      const testPaths = [
        '/',
        '/login',
        '/register',
        '/about',
        '/about/terms',
        '/dashboard',
        '/projects',
        '/admin',
        '',
        '/unusual/path',
      ]

      testPaths.forEach((path) => {
        const isPublic = authRedirect.isPublicRoute(path)
        const isProtected = authRedirect.isProtectedRoute(path)

        // Should be logical inverses
        expect(isPublic).toBe(!isProtected)

        // getRedirectForAuthState should be consistent with route checking
        jest.clearAllMocks()
        authRedirect.getRedirectForAuthState(false, path, mockRouter)

        if (isProtected) {
          expect(mockRouter.replace).toHaveBeenCalledWith('/login')
        } else {
          expect(mockRouter.replace).not.toHaveBeenCalled()
        }
      })
    })
  })
})
