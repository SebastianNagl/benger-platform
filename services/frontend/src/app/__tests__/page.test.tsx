/**
 * @jest-environment jsdom
 */

import { useAuth } from '@/contexts/AuthContext'
import { authRedirect } from '@/utils/authRedirect'
import { render, screen, waitFor } from '@testing-library/react'
import { useRouter } from 'next/navigation'
import LandingPage from '../page'

// Mock dependencies
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}))

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))

jest.mock('@/utils/authRedirect', () => ({
  authRedirect: {
    toDashboard: jest.fn(),
  },
}))

jest.mock('@/components/landing/HeroSection', () => ({
  HeroSection: () => <div data-testid="hero-section">Hero Section</div>,
}))

jest.mock('@/components/landing/LandingLayout', () => ({
  LandingLayout: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="landing-layout">{children}</div>
  ),
}))

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

describe('LandingPage', () => {
  const mockRouter = {
    push: jest.fn(),
    replace: jest.fn(),
    prefetch: jest.fn(),
  }

  const mockUseRouter = useRouter as jest.Mock
  const mockUseAuth = useAuth as jest.Mock
  const mockAuthRedirect = authRedirect.toDashboard as jest.Mock

  beforeEach(() => {
    jest.clearAllMocks()
    mockUseRouter.mockReturnValue(mockRouter)
  })

  describe('Loading State', () => {
    it('shows loading spinner when auth is loading', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
      })

      render(<LandingPage />)

      expect(screen.getByText('Loading...')).toBeInTheDocument()
      expect(screen.queryByTestId('hero-section')).not.toBeInTheDocument()
      expect(screen.queryByTestId('landing-layout')).not.toBeInTheDocument()
    })

    it('applies correct loading styles', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
      })

      const { container } = render(<LandingPage />)

      const loadingContainer = container.querySelector(
        '.flex.min-h-screen.items-center.justify-center'
      )
      expect(loadingContainer).toBeInTheDocument()
      expect(loadingContainer).toHaveClass('bg-white', 'dark:bg-zinc-900')
    })

    it('shows spinner with correct styling', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
      })

      const { container } = render(<LandingPage />)

      const spinner = container.querySelector('.animate-spin')
      expect(spinner).toBeInTheDocument()
      expect(spinner).toHaveClass(
        'h-8',
        'w-8',
        'rounded-full',
        'border-b-2',
        'border-emerald-500'
      )
    })
  })

  describe('Authenticated User Redirect', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'user@example.com', name: 'Test User' },
        isLoading: false,
      })
    })

    it('redirects authenticated users to dashboard', async () => {
      render(<LandingPage />)

      await waitFor(() => {
        expect(mockAuthRedirect).toHaveBeenCalledWith(mockRouter)
      })
    })

    it('shows redirect loading state for authenticated users', () => {
      render(<LandingPage />)

      expect(
        screen.getByText('Redirecting to dashboard...')
      ).toBeInTheDocument()
      expect(screen.queryByTestId('hero-section')).not.toBeInTheDocument()
    })

    it('shows spinner during redirect for authenticated users', () => {
      const { container } = render(<LandingPage />)

      const spinner = container.querySelector('.animate-spin')
      expect(spinner).toBeInTheDocument()
      expect(spinner).toHaveClass('border-emerald-500')
    })

    it('applies correct redirect loading styles', () => {
      const { container } = render(<LandingPage />)

      const redirectContainer = container.querySelector(
        '.flex.min-h-screen.items-center.justify-center'
      )
      expect(redirectContainer).toBeInTheDocument()
      expect(redirectContainer).toHaveClass('bg-white', 'dark:bg-zinc-900')
    })

    it('does not render landing layout during redirect', () => {
      render(<LandingPage />)

      expect(screen.queryByTestId('landing-layout')).not.toBeInTheDocument()
    })

    it('redirects only after loading is complete', async () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'user@example.com' },
        isLoading: true,
      })

      const { rerender } = render(<LandingPage />)

      expect(mockAuthRedirect).not.toHaveBeenCalled()

      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'user@example.com' },
        isLoading: false,
      })

      rerender(<LandingPage />)

      await waitFor(() => {
        expect(mockAuthRedirect).toHaveBeenCalledWith(mockRouter)
      })
    })
  })

  describe('Unauthenticated User', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
      })
    })

    it('renders landing layout for unauthenticated users', () => {
      render(<LandingPage />)

      expect(screen.getByTestId('landing-layout')).toBeInTheDocument()
    })

    it('renders hero section for unauthenticated users', () => {
      render(<LandingPage />)

      expect(screen.getByTestId('hero-section')).toBeInTheDocument()
    })

    it('does not redirect unauthenticated users', () => {
      render(<LandingPage />)

      expect(mockAuthRedirect).not.toHaveBeenCalled()
    })

    it('does not show loading state for unauthenticated users', () => {
      render(<LandingPage />)

      expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
      expect(
        screen.queryByText('Redirecting to dashboard...')
      ).not.toBeInTheDocument()
    })

    it('shows full landing page content', () => {
      render(<LandingPage />)

      expect(screen.getByTestId('landing-layout')).toBeInTheDocument()
      expect(screen.getByTestId('hero-section')).toBeInTheDocument()
    })
  })

  describe('Auth State Transitions', () => {
    it('transitions from loading to unauthenticated', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
      })

      const { rerender } = render(<LandingPage />)

      expect(screen.getByText('Loading...')).toBeInTheDocument()

      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
      })

      rerender(<LandingPage />)

      expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
      expect(screen.getByTestId('landing-layout')).toBeInTheDocument()
      expect(screen.getByTestId('hero-section')).toBeInTheDocument()
    })

    it('transitions from loading to authenticated', async () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
      })

      const { rerender } = render(<LandingPage />)

      expect(screen.getByText('Loading...')).toBeInTheDocument()

      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'user@example.com' },
        isLoading: false,
      })

      rerender(<LandingPage />)

      expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
      expect(
        screen.getByText('Redirecting to dashboard...')
      ).toBeInTheDocument()

      await waitFor(() => {
        expect(mockAuthRedirect).toHaveBeenCalledWith(mockRouter)
      })
    })

    it('transitions from unauthenticated to authenticated', async () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
      })

      const { rerender } = render(<LandingPage />)

      expect(screen.getByTestId('landing-layout')).toBeInTheDocument()

      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'user@example.com' },
        isLoading: false,
      })

      rerender(<LandingPage />)

      expect(screen.queryByTestId('landing-layout')).not.toBeInTheDocument()
      expect(
        screen.getByText('Redirecting to dashboard...')
      ).toBeInTheDocument()

      await waitFor(() => {
        expect(mockAuthRedirect).toHaveBeenCalledWith(mockRouter)
      })
    })

    it('handles rapid state changes correctly', async () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
      })

      const { rerender } = render(<LandingPage />)

      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'user@example.com' },
        isLoading: false,
      })

      rerender(<LandingPage />)

      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
      })

      rerender(<LandingPage />)

      expect(screen.getByTestId('landing-layout')).toBeInTheDocument()
      expect(screen.getByTestId('hero-section')).toBeInTheDocument()
    })
  })

  describe('Edge Cases', () => {
    it('handles undefined user gracefully', () => {
      mockUseAuth.mockReturnValue({
        user: undefined,
        isLoading: false,
      })

      render(<LandingPage />)

      expect(screen.getByTestId('landing-layout')).toBeInTheDocument()
      expect(screen.getByTestId('hero-section')).toBeInTheDocument()
    })

    it('handles null user gracefully', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
      })

      render(<LandingPage />)

      expect(screen.getByTestId('landing-layout')).toBeInTheDocument()
      expect(screen.getByTestId('hero-section')).toBeInTheDocument()
    })

    it('handles missing router gracefully', () => {
      mockUseRouter.mockReturnValue(null)
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'user@example.com' },
        isLoading: false,
      })

      // Should not throw error
      render(<LandingPage />)

      expect(
        screen.getByText('Redirecting to dashboard...')
      ).toBeInTheDocument()
    })

    it('prevents flash of content during redirect', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'user@example.com' },
        isLoading: false,
      })

      render(<LandingPage />)

      expect(screen.queryByTestId('landing-layout')).not.toBeInTheDocument()
      expect(screen.queryByTestId('hero-section')).not.toBeInTheDocument()
      expect(
        screen.getByText('Redirecting to dashboard...')
      ).toBeInTheDocument()
    })

    it('handles loading state without user', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
      })

      render(<LandingPage />)

      expect(screen.getByText('Loading...')).toBeInTheDocument()
      expect(screen.queryByTestId('hero-section')).not.toBeInTheDocument()
    })

    it('handles user with minimal properties', async () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1' },
        isLoading: false,
      })

      render(<LandingPage />)

      await waitFor(() => {
        expect(mockAuthRedirect).toHaveBeenCalledWith(mockRouter)
      })
    })

    it('handles user with complete properties', async () => {
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          email: 'user@example.com',
          name: 'Test User',
          role: 'user',
        },
        isLoading: false,
      })

      render(<LandingPage />)

      await waitFor(() => {
        expect(mockAuthRedirect).toHaveBeenCalledWith(mockRouter)
      })
    })
  })

  describe('useEffect Dependencies', () => {
    it('calls redirect when user changes from null to defined', async () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
      })

      const { rerender } = render(<LandingPage />)

      expect(mockAuthRedirect).not.toHaveBeenCalled()

      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'user@example.com' },
        isLoading: false,
      })

      rerender(<LandingPage />)

      await waitFor(() => {
        expect(mockAuthRedirect).toHaveBeenCalledTimes(1)
        expect(mockAuthRedirect).toHaveBeenCalledWith(mockRouter)
      })
    })

    it('does not call redirect when loading changes but user remains null', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
      })

      const { rerender } = render(<LandingPage />)

      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
      })

      rerender(<LandingPage />)

      expect(mockAuthRedirect).not.toHaveBeenCalled()
    })

    it('respects isLoading flag to prevent premature redirects', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'user@example.com' },
        isLoading: true,
      })

      render(<LandingPage />)

      expect(mockAuthRedirect).not.toHaveBeenCalled()
      expect(screen.getByText('Loading...')).toBeInTheDocument()
    })
  })

  describe('Component Structure', () => {
    it('renders loading container with correct structure', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
      })

      const { container } = render(<LandingPage />)

      const loadingDiv = container.querySelector('.flex.min-h-screen')
      expect(loadingDiv).toBeInTheDocument()

      const textCenter = loadingDiv?.querySelector('.text-center')
      expect(textCenter).toBeInTheDocument()
    })

    it('renders redirect container with correct structure', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'user@example.com' },
        isLoading: false,
      })

      const { container } = render(<LandingPage />)

      const redirectDiv = container.querySelector('.flex.min-h-screen')
      expect(redirectDiv).toBeInTheDocument()

      const textCenter = redirectDiv?.querySelector('.text-center')
      expect(textCenter).toBeInTheDocument()
    })

    it('nests hero section within landing layout', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
      })

      render(<LandingPage />)

      const landingLayout = screen.getByTestId('landing-layout')
      const heroSection = screen.getByTestId('hero-section')

      expect(landingLayout).toContainElement(heroSection)
    })
  })

  describe('Text Content', () => {
    it('shows loading text', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
      })

      render(<LandingPage />)

      expect(screen.getByText('Loading...')).toBeInTheDocument()
    })

    it('shows redirect text', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'user@example.com' },
        isLoading: false,
      })

      render(<LandingPage />)

      expect(
        screen.getByText('Redirecting to dashboard...')
      ).toBeInTheDocument()
    })

    it('applies correct text styling', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
      })

      const { container } = render(<LandingPage />)

      const text = screen.getByText('Loading...')
      expect(text).toHaveClass('text-zinc-600', 'dark:text-zinc-400')
    })
  })

  describe('Dark Mode Support', () => {
    it('includes dark mode classes in loading state', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
      })

      const { container } = render(<LandingPage />)

      const loadingContainer = container.querySelector('.flex.min-h-screen')
      expect(loadingContainer).toHaveClass('dark:bg-zinc-900')

      const text = screen.getByText('Loading...')
      expect(text).toHaveClass('dark:text-zinc-400')
    })

    it('includes dark mode classes in redirect state', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'user@example.com' },
        isLoading: false,
      })

      const { container } = render(<LandingPage />)

      const redirectContainer = container.querySelector('.flex.min-h-screen')
      expect(redirectContainer).toHaveClass('dark:bg-zinc-900')

      const text = screen.getByText('Redirecting to dashboard...')
      expect(text).toHaveClass('dark:text-zinc-400')
    })
  })
})
