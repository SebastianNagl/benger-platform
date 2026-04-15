/**
 * @jest-environment jsdom
 */

import { useAuth } from '@/contexts/AuthContext'
import { authRedirect } from '@/utils/authRedirect'
import { render, screen, waitFor } from '@testing-library/react'
import { usePathname, useRouter } from 'next/navigation'
import { ProtectedRoute } from '../ProtectedRoute'

// Mock Next.js navigation
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
  usePathname: jest.fn(),
}))

// Mock AuthContext
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))

// Mock i18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'common.redirecting': 'Redirecting...',
        'common.loading': 'Loading...',
      }
      return translations[key] || key
    },
    locale: 'en',
  }),
}))

// Mock authRedirect utility
jest.mock('@/utils/authRedirect', () => ({
  authRedirect: {
    isPublicRoute: jest.fn(),
    toLogin: jest.fn(),
  },
}))

describe('ProtectedRoute Component', () => {
  const mockPush = jest.fn()
  const mockRouter = { push: mockPush }
  const mockUseRouter = useRouter as jest.Mock
  const mockUsePathname = usePathname as jest.Mock
  const mockUseAuth = useAuth as jest.Mock
  const mockIsPublicRoute = authRedirect.isPublicRoute as jest.Mock
  const mockToLogin = authRedirect.toLogin as jest.Mock

  const TestComponent = () => (
    <div data-testid="protected-content">
      <h1>Protected Content</h1>
      <p>This content requires authentication</p>
    </div>
  )

  beforeEach(() => {
    jest.clearAllMocks()
    mockUseRouter.mockReturnValue(mockRouter)
    mockUsePathname.mockReturnValue('/dashboard')
    mockIsPublicRoute.mockReturnValue(false)
  })

  describe('Public Routes', () => {
    beforeEach(() => {
      mockIsPublicRoute.mockReturnValue(true)
      mockUsePathname.mockReturnValue('/')
    })

    it('renders children immediately on public routes without auth check', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
      })

      render(
        <ProtectedRoute>
          <TestComponent />
        </ProtectedRoute>
      )

      expect(screen.getByTestId('protected-content')).toBeInTheDocument()
      expect(mockToLogin).not.toHaveBeenCalled()
    })

    it('renders children on public routes when not authenticated', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
      })

      render(
        <ProtectedRoute>
          <TestComponent />
        </ProtectedRoute>
      )

      expect(screen.getByTestId('protected-content')).toBeInTheDocument()
      expect(screen.getByText('Protected Content')).toBeInTheDocument()
      expect(mockToLogin).not.toHaveBeenCalled()
    })

    it('renders children on public routes when authenticated', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'user@example.com' },
        isLoading: false,
      })

      render(
        <ProtectedRoute>
          <TestComponent />
        </ProtectedRoute>
      )

      expect(screen.getByTestId('protected-content')).toBeInTheDocument()
    })

    it('does not redirect on public routes', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
      })

      render(
        <ProtectedRoute>
          <TestComponent />
        </ProtectedRoute>
      )

      expect(mockToLogin).not.toHaveBeenCalled()
    })
  })

  describe('Protected Routes - Authenticated User', () => {
    beforeEach(() => {
      mockIsPublicRoute.mockReturnValue(false)
    })

    it('renders children when user is authenticated', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'user@example.com', name: 'Test User' },
        isLoading: false,
      })

      render(
        <ProtectedRoute>
          <TestComponent />
        </ProtectedRoute>
      )

      expect(screen.getByTestId('protected-content')).toBeInTheDocument()
      expect(screen.getByText('Protected Content')).toBeInTheDocument()
      expect(mockToLogin).not.toHaveBeenCalled()
    })

    it('does not redirect when user is authenticated', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'user@example.com' },
        isLoading: false,
      })

      render(
        <ProtectedRoute>
          <TestComponent />
        </ProtectedRoute>
      )

      expect(mockToLogin).not.toHaveBeenCalled()
    })
  })

  describe('Protected Routes - Loading State', () => {
    beforeEach(() => {
      mockIsPublicRoute.mockReturnValue(false)
    })

    it('returns null when auth is loading', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
      })

      const { container } = render(
        <ProtectedRoute>
          <TestComponent />
        </ProtectedRoute>
      )

      expect(container.firstChild).toBeNull()
      expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument()
      expect(mockToLogin).not.toHaveBeenCalled()
    })

    it('does not render loading spinner (handled by ConditionalLayout)', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
      })

      render(
        <ProtectedRoute>
          <TestComponent />
        </ProtectedRoute>
      )

      expect(screen.queryByText('Redirecting...')).not.toBeInTheDocument()
    })

    it('does not redirect during loading state', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
      })

      render(
        <ProtectedRoute>
          <TestComponent />
        </ProtectedRoute>
      )

      expect(mockToLogin).not.toHaveBeenCalled()
    })
  })

  describe('Protected Routes - Unauthenticated User', () => {
    beforeEach(() => {
      mockIsPublicRoute.mockReturnValue(false)
    })

    it('shows loading state when not authenticated', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
      })

      render(
        <ProtectedRoute>
          <TestComponent />
        </ProtectedRoute>
      )

      expect(screen.getByText('Redirecting...')).toBeInTheDocument()
      expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument()
    })

    it('shows loading spinner with correct styling when not authenticated', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
      })

      const { container } = render(
        <ProtectedRoute>
          <TestComponent />
        </ProtectedRoute>
      )

      const loadingContainer = container.querySelector('.min-h-screen')
      expect(loadingContainer).toHaveClass(
        'min-h-screen',
        'flex',
        'items-center',
        'justify-center'
      )

      const spinner = container.querySelector('.animate-spin')
      expect(spinner).toHaveClass(
        'animate-spin',
        'rounded-full',
        'border-b-2',
        'border-emerald-500'
      )
    })

    it('redirects to login when not authenticated', async () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
      })

      render(
        <ProtectedRoute>
          <TestComponent />
        </ProtectedRoute>
      )

      await waitFor(() => {
        expect(mockToLogin).toHaveBeenCalledWith(mockRouter)
      })
    })

    it('redirects only once when not authenticated', async () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
      })

      const { rerender } = render(
        <ProtectedRoute>
          <TestComponent />
        </ProtectedRoute>
      )

      await waitFor(() => {
        expect(mockToLogin).toHaveBeenCalledTimes(1)
      })

      rerender(
        <ProtectedRoute>
          <TestComponent />
        </ProtectedRoute>
      )

      expect(mockToLogin).toHaveBeenCalledTimes(1)
    })
  })

  describe('Route Transitions', () => {
    it('handles transition from public to protected route', () => {
      mockIsPublicRoute.mockReturnValue(true)
      mockUsePathname.mockReturnValue('/')

      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'user@example.com' },
        isLoading: false,
      })

      const { rerender } = render(
        <ProtectedRoute>
          <TestComponent />
        </ProtectedRoute>
      )

      expect(screen.getByTestId('protected-content')).toBeInTheDocument()

      // Navigate to protected route
      mockIsPublicRoute.mockReturnValue(false)
      mockUsePathname.mockReturnValue('/dashboard')

      rerender(
        <ProtectedRoute>
          <TestComponent />
        </ProtectedRoute>
      )

      expect(screen.getByTestId('protected-content')).toBeInTheDocument()
      expect(mockToLogin).not.toHaveBeenCalled()
    })

    it('handles transition from loading to authenticated', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
      })

      const { container, rerender } = render(
        <ProtectedRoute>
          <TestComponent />
        </ProtectedRoute>
      )

      expect(container.firstChild).toBeNull()

      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'user@example.com' },
        isLoading: false,
      })

      rerender(
        <ProtectedRoute>
          <TestComponent />
        </ProtectedRoute>
      )

      expect(screen.getByTestId('protected-content')).toBeInTheDocument()
    })

    it('handles transition from authenticated to unauthenticated', async () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'user@example.com' },
        isLoading: false,
      })

      const { rerender } = render(
        <ProtectedRoute>
          <TestComponent />
        </ProtectedRoute>
      )

      expect(screen.getByTestId('protected-content')).toBeInTheDocument()

      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
      })

      rerender(
        <ProtectedRoute>
          <TestComponent />
        </ProtectedRoute>
      )

      expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument()
      expect(screen.getByText('Redirecting...')).toBeInTheDocument()

      await waitFor(() => {
        expect(mockToLogin).toHaveBeenCalled()
      })
    })
  })

  describe('Edge Cases', () => {
    it('handles undefined user gracefully', async () => {
      mockIsPublicRoute.mockReturnValue(false)

      mockUseAuth.mockReturnValue({
        user: undefined,
        isLoading: false,
      })

      render(
        <ProtectedRoute>
          <TestComponent />
        </ProtectedRoute>
      )

      await waitFor(() => {
        expect(mockToLogin).toHaveBeenCalled()
      })
    })

    it('handles null pathname gracefully', () => {
      mockUsePathname.mockReturnValue(null)
      mockIsPublicRoute.mockReturnValue(false)

      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'user@example.com' },
        isLoading: false,
      })

      render(
        <ProtectedRoute>
          <TestComponent />
        </ProtectedRoute>
      )

      expect(screen.getByTestId('protected-content')).toBeInTheDocument()
      expect(authRedirect.isPublicRoute).toHaveBeenCalledWith('/')
    })

    it('handles empty children gracefully', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'user@example.com' },
        isLoading: false,
      })

      render(<ProtectedRoute>{null}</ProtectedRoute>)

      expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument()
    })

    it('handles multiple children correctly', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'user@example.com' },
        isLoading: false,
      })

      render(
        <ProtectedRoute>
          <div data-testid="child-1">Child 1</div>
          <div data-testid="child-2">Child 2</div>
        </ProtectedRoute>
      )

      expect(screen.getByTestId('child-1')).toBeInTheDocument()
      expect(screen.getByTestId('child-2')).toBeInTheDocument()
    })
  })

  describe('Dark Mode Support', () => {
    it('applies dark mode classes to loading state', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
      })

      const { container } = render(
        <ProtectedRoute>
          <TestComponent />
        </ProtectedRoute>
      )

      const loadingContainer = container.querySelector('.bg-white')
      expect(loadingContainer).toHaveClass('dark:bg-zinc-900')

      const loadingText = screen.getByText('Redirecting...')
      expect(loadingText).toHaveClass('text-zinc-600', 'dark:text-zinc-400')
    })
  })
})
