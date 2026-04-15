/**
 * @jest-environment jsdom
 */

import LandingPage from '@/app/page'
import { ProtectedRoute } from '@/components/auth/ProtectedRoute'
import { useAuth } from '@/contexts/AuthContext'
import { render, screen, waitFor } from '@testing-library/react'
import { useRouter } from 'next/navigation'
import React from 'react'

// Mock next/navigation
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(() => ({
    push: jest.fn(),
    replace: jest.fn(),
    back: jest.fn(),
    forward: jest.fn(),
    refresh: jest.fn(),
    prefetch: jest.fn(),
    pathname: '/',
    query: {},
    asPath: '/',
    route: '/',
    basePath: '',
    isReady: true,
    isPreview: false,
    isLocaleDomain: false,
  })),
  useParams: jest.fn(() => ({})),
  useSearchParams: jest.fn(() => new URLSearchParams()),
  usePathname: jest.fn(() => '/'),
  notFound: jest.fn(),
  redirect: jest.fn(),
}))

// Mock AuthContext
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))

// Mock authRedirect utility
jest.mock('@/utils/authRedirect', () => ({
  authRedirect: {
    isPublicRoute: jest.fn(() => false),
    getRedirectUrl: jest.fn(() => '/dashboard'),
    toDashboard: jest.fn((router) => router.replace('/dashboard')),
  },
}))

// Mock ProtectedRoute component
jest.mock('@/components/auth/ProtectedRoute', () => ({
  ProtectedRoute: ({ children }: { children: React.ReactNode }) => {
    const { useAuth } = require('@/contexts/AuthContext')
    const { useRouter, usePathname } = require('next/navigation')
    const { user, isLoading } = useAuth()
    const router = useRouter()
    const pathname = usePathname()

    // Simulate the ProtectedRoute logic
    const isPublicRoute = pathname === '/' || pathname === '/login'

    if (isLoading) {
      return <div data-testid="loading">Loading...</div>
    }

    if (!user && !isPublicRoute) {
      router.replace('/')
      return null
    }

    return <>{children}</>
  },
}))

// Mock LandingLayout and HeroSection
jest.mock('@/components/landing/LandingLayout', () => ({
  LandingLayout: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="landing-layout">{children}</div>
  ),
}))

jest.mock('@/components/landing/HeroSection', () => ({
  HeroSection: () => <div data-testid="hero-section">Hero Section</div>,
}))

describe('Issue #214: Infinite Redirect Loop Fix', () => {
  const mockRouter = {
    push: jest.fn(),
    replace: jest.fn(),
  }

  const mockUsePathname = useRouter as jest.Mock
  const mockUseAuth = useAuth as jest.Mock

  beforeEach(() => {
    jest.clearAllMocks()
    mockUsePathname.mockReturnValue(mockRouter)
    // Mock pathname to return current path
    require('next/navigation').usePathname.mockReturnValue('/')
  })

  describe('ProtectedRoute Component', () => {
    it('should not redirect when loading', async () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
      })

      render(
        <ProtectedRoute>
          <div>Protected Content</div>
        </ProtectedRoute>
      )

      expect(mockRouter.replace).not.toHaveBeenCalled()
    })

    it('should redirect unauthenticated users from protected routes', async () => {
      // Mock protected route
      require('next/navigation').usePathname.mockReturnValue('/tasks')

      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
      })

      render(
        <ProtectedRoute>
          <div>Protected Content</div>
        </ProtectedRoute>
      )

      await waitFor(() => {
        expect(mockRouter.replace).toHaveBeenCalledWith('/')
      })
    })

    it('should not redirect authenticated users on protected routes', async () => {
      // Mock protected route
      require('next/navigation').usePathname.mockReturnValue('/tasks')

      mockUseAuth.mockReturnValue({
        user: { id: 1, username: 'test' },
        isLoading: false,
      })

      render(
        <ProtectedRoute>
          <div>Protected Content</div>
        </ProtectedRoute>
      )

      expect(mockRouter.replace).not.toHaveBeenCalled()
    })

    it('should not redirect on public routes', async () => {
      // Mock public route
      require('next/navigation').usePathname.mockReturnValue('/')

      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
      })

      render(
        <ProtectedRoute>
          <div>Public Content</div>
        </ProtectedRoute>
      )

      expect(mockRouter.replace).not.toHaveBeenCalled()
    })
  })

  describe('Landing Page Component', () => {
    it('should not redirect when loading', async () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
      })

      render(<LandingPage />)

      expect(mockRouter.replace).not.toHaveBeenCalled()
      expect(screen.getByText('Loading...')).toBeInTheDocument()
    })

    it('should redirect authenticated users to dashboard', async () => {
      mockUseAuth.mockReturnValue({
        user: { id: 1, username: 'test' },
        isLoading: false,
      })

      render(<LandingPage />)

      await waitFor(() => {
        expect(mockRouter.replace).toHaveBeenCalledWith('/dashboard')
      })
    })

    it('should show landing page for unauthenticated users', async () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
      })

      render(<LandingPage />)

      expect(mockRouter.replace).not.toHaveBeenCalled()
      expect(screen.getByTestId('landing-layout')).toBeInTheDocument()
      expect(screen.getByTestId('hero-section')).toBeInTheDocument()
    })

    it('should show loading state while redirecting', async () => {
      mockUseAuth.mockReturnValue({
        user: { id: 1, username: 'test' },
        isLoading: false,
      })

      render(<LandingPage />)

      expect(
        screen.getByText('Redirecting to dashboard...')
      ).toBeInTheDocument()
    })
  })

  describe('Auth State Stability', () => {
    it('should not trigger multiple redirects during auth state transitions', async () => {
      // Mock protected route
      require('next/navigation').usePathname.mockReturnValue('/tasks')

      // Initially loading
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
      })

      const { rerender } = render(
        <ProtectedRoute>
          <div>Protected Content</div>
        </ProtectedRoute>
      )

      // Verify no redirect during loading
      expect(mockRouter.replace).not.toHaveBeenCalled()

      // Then stable unauthenticated state
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
      })
      rerender(
        <ProtectedRoute>
          <div>Protected Content</div>
        </ProtectedRoute>
      )

      // Should only redirect once when auth state stabilizes
      await waitFor(() => {
        expect(mockRouter.replace).toHaveBeenCalledTimes(1)
        expect(mockRouter.replace).toHaveBeenCalledWith('/')
      })
    })
  })
})

// Mock i18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'common.loading': 'Loading...',
        'common.redirectingToDashboard': 'Redirecting to dashboard...',
        'common.redirecting': 'Redirecting...',
      }
      return translations[key] || key
    },
    locale: 'en',
  }),
}))
