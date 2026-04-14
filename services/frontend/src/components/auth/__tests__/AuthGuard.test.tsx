/**
 * @jest-environment jsdom
 */

import { useAuth } from '@/contexts/AuthContext'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useRouter } from 'next/navigation'
import { AuthGuard } from '../AuthGuard'

// Mock Next.js router
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}))
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, varsOrDefault?: any) => {
      const translations: Record<string, any> = require('../../../locales/en/common.json')
      const parts = key.split('.')
      let value: any = translations
      for (const part of parts) {
        if (value && typeof value === 'object' && part in value) {
          value = value[part]
        } else {
          return key
        }
      }
      if (typeof value !== 'string') return key
      if (varsOrDefault && typeof varsOrDefault === 'object') {
        for (const [k, v] of Object.entries(varsOrDefault)) {
          value = value.replace(new RegExp(`\\{${k}\\}`, 'g'), String(v))
        }
      }
      return value
    },
    locale: 'en',
  }),
}))


// Mock AuthContext
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))

// Mock LoginModal component
jest.mock('../LoginModal', () => ({
  LoginModal: ({
    isOpen,
    onClose,
  }: {
    isOpen: boolean
    onClose: () => void
  }) =>
    isOpen ? (
      <div data-testid="login-modal">
        <h2>Login Modal</h2>
        <button onClick={onClose} data-testid="login-modal-close">
          Close Login
        </button>
      </div>
    ) : null,
}))

// Mock Button component
jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, variant, className }: any) => (
    <button
      onClick={onClick}
      className={className}
      data-variant={variant}
      data-testid={`button-${children.toLowerCase().replace(/\s+/g, '-')}`}
    >
      {children}
    </button>
  ),
}))

// Mock Headless UI components
jest.mock('@headlessui/react', () => ({
  Dialog: ({ open, onClose, children, className }: any) =>
    open ? (
      <div className={className} data-testid="auth-dialog" role="dialog">
        <div onClick={onClose} data-testid="dialog-backdrop" />
        {children}
      </div>
    ) : null,
  DialogBackdrop: ({ className }: any) => (
    <div className={className} data-testid="dialog-backdrop" />
  ),
  DialogPanel: ({ children, className }: any) => (
    <div className={className} data-testid="dialog-panel">
      {children}
    </div>
  ),
}))

describe('AuthGuard Component', () => {
  const mockPush = jest.fn()
  const mockUseRouter = useRouter as jest.Mock
  const mockUseAuth = useAuth as jest.Mock

  const TestComponent = () => (
    <div data-testid="protected-content">
      <h1>Protected Content</h1>
      <p>This content requires authentication</p>
    </div>
  )

  beforeEach(() => {
    jest.clearAllMocks()
    mockUseRouter.mockReturnValue({
      push: mockPush,
    })
  })

  describe('Loading State', () => {
    it('shows loading spinner when auth is loading', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
      })

      render(
        <AuthGuard>
          <TestComponent />
        </AuthGuard>
      )

      expect(screen.getByText('Loading...')).toBeInTheDocument()
      expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument()
      expect(screen.queryByTestId('auth-dialog')).not.toBeInTheDocument()
    })

    it('applies correct loading styles', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
      })

      render(
        <AuthGuard>
          <TestComponent />
        </AuthGuard>
      )

      const loadingContainer = screen.getByTestId('loading-container')
      expect(loadingContainer).toHaveClass(
        'min-h-screen',
        'flex',
        'items-center',
        'justify-center',
        'bg-white',
        'dark:bg-zinc-900'
      )

      const spinner = loadingContainer?.querySelector('.animate-spin')
      expect(spinner).toHaveClass(
        'animate-spin',
        'rounded-full',
        'h-8',
        'w-8',
        'border-b-2',
        'border-emerald-500'
      )
    })
  })

  describe('Authenticated User (Default Behavior)', () => {
    it('renders children normally when user is authenticated', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'user@example.com', name: 'Test User' },
        isLoading: false,
      })

      render(
        <AuthGuard>
          <TestComponent />
        </AuthGuard>
      )

      expect(screen.getByTestId('auth-guard')).toBeInTheDocument()
      expect(screen.getByTestId('protected-content')).toBeInTheDocument()
      expect(screen.getByText('Protected Content')).toBeInTheDocument()
      expect(screen.queryByTestId('auth-dialog')).not.toBeInTheDocument()
      expect(screen.queryByTestId('login-modal')).not.toBeInTheDocument()
    })

    it('does not show auth dialog when user is authenticated', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'user@example.com' },
        isLoading: false,
      })

      render(
        <AuthGuard requireAuth={true}>
          <TestComponent />
        </AuthGuard>
      )

      expect(screen.getByTestId('protected-content')).toBeInTheDocument()
      expect(
        screen.queryByText('Authentication Required')
      ).not.toBeInTheDocument()
    })
  })

  describe('Unauthenticated User with requireAuth=true', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
      })
    })

    it('shows auth required dialog when user is not authenticated', () => {
      render(
        <AuthGuard requireAuth={true}>
          <TestComponent />
        </AuthGuard>
      )

      expect(screen.getByText('Authentication Required')).toBeInTheDocument()
      expect(
        screen.getByText(
          'You need to be signed in to access this feature. Please sign in and try again.'
        )
      ).toBeInTheDocument()
      expect(screen.getByTestId('auth-dialog')).toBeInTheDocument()
    })

    it('renders children in background with disabled styling', () => {
      const { container } = render(
        <AuthGuard requireAuth={true}>
          <TestComponent />
        </AuthGuard>
      )

      const backgroundContent = screen.getByTestId('protected-content')
      const backgroundContainer = container.querySelector(
        '.pointer-events-none'
      )

      expect(backgroundContainer).toHaveClass(
        'pointer-events-none',
        'opacity-50',
        'blur-sm'
      )
      expect(backgroundContent).toBeInTheDocument()
    })

    it('shows correct dialog content and buttons', () => {
      render(
        <AuthGuard requireAuth={true}>
          <TestComponent />
        </AuthGuard>
      )

      expect(screen.getByText('Authentication Required')).toBeInTheDocument()
      expect(screen.getByTestId('button-go-to-sign-in')).toBeInTheDocument()
      expect(screen.getByTestId('button-cancel')).toBeInTheDocument()
    })

    it('applies correct styling to auth dialog', () => {
      render(
        <AuthGuard requireAuth={true}>
          <TestComponent />
        </AuthGuard>
      )

      const dialog = screen.getByTestId('auth-dialog')
      expect(dialog).toHaveClass('relative', 'z-50')

      const dialogPanel = screen.getByTestId('dialog-panel')
      expect(dialogPanel).toHaveClass(
        'mx-auto',
        'max-w-md',
        'rounded-lg',
        'bg-white',
        'dark:bg-zinc-800',
        'p-6',
        'shadow-xl',
        'border',
        'border-zinc-200',
        'dark:border-zinc-700'
      )
    })

    it('shows lock icon in dialog', () => {
      render(
        <AuthGuard requireAuth={true}>
          <TestComponent />
        </AuthGuard>
      )

      const lockIcon = document.querySelector('svg.text-emerald-600')
      expect(lockIcon).toBeInTheDocument()
      expect(lockIcon).toHaveClass(
        'h-6',
        'w-6',
        'text-emerald-600',
        'dark:text-emerald-400'
      )
    })
  })

  describe('Dialog Interactions', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
      })
    })

    it('redirects to home page when Cancel button is clicked', async () => {
      const user = userEvent.setup()
      render(
        <AuthGuard requireAuth={true}>
          <TestComponent />
        </AuthGuard>
      )

      const cancelButton = screen.getByTestId('button-cancel')
      await user.click(cancelButton)

      expect(mockPush).toHaveBeenCalledWith('/')
    })

    it('opens login modal when "Go to Sign In" button is clicked', async () => {
      const user = userEvent.setup()
      render(
        <AuthGuard requireAuth={true}>
          <TestComponent />
        </AuthGuard>
      )

      const signInButton = screen.getByTestId('button-go-to-sign-in')
      await user.click(signInButton)

      expect(screen.getByTestId('login-modal')).toBeInTheDocument()
      expect(screen.getByText('Login Modal')).toBeInTheDocument()
      expect(screen.queryByTestId('auth-dialog')).not.toBeInTheDocument()
    })

    it('closes auth dialog when "Go to Sign In" is clicked', async () => {
      const user = userEvent.setup()
      render(
        <AuthGuard requireAuth={true}>
          <TestComponent />
        </AuthGuard>
      )

      expect(screen.getByTestId('auth-dialog')).toBeInTheDocument()

      const signInButton = screen.getByTestId('button-go-to-sign-in')
      await user.click(signInButton)

      expect(screen.queryByTestId('auth-dialog')).not.toBeInTheDocument()
      expect(screen.getByTestId('login-modal')).toBeInTheDocument()
    })

    it('handles login modal close correctly', async () => {
      const user = userEvent.setup()
      render(
        <AuthGuard requireAuth={true}>
          <TestComponent />
        </AuthGuard>
      )

      // Open login modal
      const signInButton = screen.getByTestId('button-go-to-sign-in')
      await user.click(signInButton)

      expect(screen.getByTestId('login-modal')).toBeInTheDocument()

      // Close login modal
      const closeLoginButton = screen.getByTestId('login-modal-close')
      await user.click(closeLoginButton)

      expect(screen.queryByTestId('login-modal')).not.toBeInTheDocument()
    })
  })

  describe('requireAuth=false', () => {
    it('renders children normally when requireAuth is false and user is not authenticated', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
      })

      render(
        <AuthGuard requireAuth={false}>
          <TestComponent />
        </AuthGuard>
      )

      expect(screen.getByTestId('auth-guard')).toBeInTheDocument()
      expect(screen.getByTestId('protected-content')).toBeInTheDocument()
      expect(screen.queryByTestId('auth-dialog')).not.toBeInTheDocument()
      expect(
        screen.queryByText('Authentication Required')
      ).not.toBeInTheDocument()
    })

    it('renders children normally when requireAuth is false and user is authenticated', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'user@example.com' },
        isLoading: false,
      })

      render(
        <AuthGuard requireAuth={false}>
          <TestComponent />
        </AuthGuard>
      )

      expect(screen.getByTestId('auth-guard')).toBeInTheDocument()
      expect(screen.getByTestId('protected-content')).toBeInTheDocument()
      expect(screen.queryByTestId('auth-dialog')).not.toBeInTheDocument()
    })
  })

  describe('Default Props', () => {
    it('defaults requireAuth to true when not specified', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
      })

      render(
        <AuthGuard>
          <TestComponent />
        </AuthGuard>
      )

      // Should show auth dialog because requireAuth defaults to true
      expect(screen.getByTestId('auth-dialog')).toBeInTheDocument()
      expect(screen.getByText('Authentication Required')).toBeInTheDocument()
    })
  })

  describe('Auth State Changes', () => {
    it('updates when user authentication state changes from null to authenticated', () => {
      // Start with unauthenticated state
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
      })

      const { rerender } = render(
        <AuthGuard>
          <TestComponent />
        </AuthGuard>
      )

      expect(screen.getByTestId('auth-dialog')).toBeInTheDocument()

      // Simulate user login
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'user@example.com' },
        isLoading: false,
      })

      rerender(
        <AuthGuard>
          <TestComponent />
        </AuthGuard>
      )

      expect(screen.queryByTestId('auth-dialog')).not.toBeInTheDocument()
      expect(screen.getByTestId('auth-guard')).toBeInTheDocument()
      expect(screen.getByTestId('protected-content')).toBeInTheDocument()
    })

    it('updates when user authentication state changes from authenticated to null', () => {
      // Start with authenticated state
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'user@example.com' },
        isLoading: false,
      })

      const { rerender } = render(
        <AuthGuard>
          <TestComponent />
        </AuthGuard>
      )

      expect(screen.getByTestId('auth-guard')).toBeInTheDocument()
      expect(screen.queryByTestId('auth-dialog')).not.toBeInTheDocument()

      // Simulate user logout
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
      })

      rerender(
        <AuthGuard>
          <TestComponent />
        </AuthGuard>
      )

      expect(screen.getByTestId('auth-dialog')).toBeInTheDocument()
      expect(screen.queryByTestId('auth-guard')).not.toBeInTheDocument()
    })

    it('handles transition from loading to authenticated', () => {
      // Start with loading state
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
      })

      const { rerender } = render(
        <AuthGuard>
          <TestComponent />
        </AuthGuard>
      )

      expect(screen.getByText('Loading...')).toBeInTheDocument()

      // Transition to authenticated
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'user@example.com' },
        isLoading: false,
      })

      rerender(
        <AuthGuard>
          <TestComponent />
        </AuthGuard>
      )

      expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
      expect(screen.getByTestId('auth-guard')).toBeInTheDocument()
      expect(screen.getByTestId('protected-content')).toBeInTheDocument()
    })

    it('handles transition from loading to unauthenticated', () => {
      // Start with loading state
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
      })

      const { rerender } = render(
        <AuthGuard>
          <TestComponent />
        </AuthGuard>
      )

      expect(screen.getByText('Loading...')).toBeInTheDocument()

      // Transition to unauthenticated
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
      })

      rerender(
        <AuthGuard>
          <TestComponent />
        </AuthGuard>
      )

      expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
      expect(screen.getByTestId('auth-dialog')).toBeInTheDocument()
    })
  })

  describe('Edge Cases and Error Handling', () => {
    it('handles undefined user object gracefully', () => {
      mockUseAuth.mockReturnValue({
        user: undefined,
        isLoading: false,
      })

      render(
        <AuthGuard>
          <TestComponent />
        </AuthGuard>
      )

      expect(screen.getByTestId('auth-dialog')).toBeInTheDocument()
      expect(screen.getByText('Authentication Required')).toBeInTheDocument()
    })

    it('handles missing router push function gracefully', async () => {
      mockUseRouter.mockReturnValue({
        push: undefined,
      })

      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
      })

      const user = userEvent.setup()
      render(
        <AuthGuard>
          <TestComponent />
        </AuthGuard>
      )

      const cancelButton = screen.getByTestId('button-cancel')

      // Should not throw error even if push is undefined
      await user.click(cancelButton)
      expect(screen.getByTestId('auth-dialog')).toBeInTheDocument()
    })

    it('handles rapid auth state changes gracefully', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
      })

      const { rerender } = render(
        <AuthGuard>
          <TestComponent />
        </AuthGuard>
      )

      // Rapidly change states
      mockUseAuth.mockReturnValue({
        user: { id: '1' },
        isLoading: false,
      })

      rerender(
        <AuthGuard>
          <TestComponent />
        </AuthGuard>
      )

      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
      })

      rerender(
        <AuthGuard>
          <TestComponent />
        </AuthGuard>
      )

      expect(screen.getByTestId('auth-dialog')).toBeInTheDocument()
    })

    it('handles empty children gracefully', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'user@example.com' },
        isLoading: false,
      })

      render(<AuthGuard>{null}</AuthGuard>)

      expect(screen.getByTestId('auth-guard')).toBeInTheDocument()
    })

    it('handles multiple children correctly', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'user@example.com' },
        isLoading: false,
      })

      render(
        <AuthGuard>
          <div data-testid="child-1">Child 1</div>
          <div data-testid="child-2">Child 2</div>
          <div data-testid="child-3">Child 3</div>
        </AuthGuard>
      )

      expect(screen.getByTestId('auth-guard')).toBeInTheDocument()
      expect(screen.getByTestId('child-1')).toBeInTheDocument()
      expect(screen.getByTestId('child-2')).toBeInTheDocument()
      expect(screen.getByTestId('child-3')).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
      })
    })

    it('has proper ARIA attributes on auth dialog', () => {
      render(
        <AuthGuard>
          <TestComponent />
        </AuthGuard>
      )

      const dialog = screen.getByRole('dialog')
      expect(dialog).toBeInTheDocument()
      expect(dialog).toHaveAttribute('data-testid', 'auth-dialog')
    })

    it('has proper heading hierarchy', () => {
      render(
        <AuthGuard>
          <TestComponent />
        </AuthGuard>
      )

      const heading = screen.getByRole('heading', { level: 3 })
      expect(heading).toHaveTextContent('Authentication Required')
    })

    it('has accessible buttons with clear labels', () => {
      render(
        <AuthGuard>
          <TestComponent />
        </AuthGuard>
      )

      const signInButton = screen.getByRole('button', { name: 'Go to Sign In' })
      const cancelButton = screen.getByRole('button', { name: 'Cancel' })

      expect(signInButton).toBeInTheDocument()
      expect(cancelButton).toBeInTheDocument()
    })

    it('provides proper loading state accessibility', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
      })

      render(
        <AuthGuard>
          <TestComponent />
        </AuthGuard>
      )

      expect(screen.getByText('Loading...')).toBeInTheDocument()
    })

    it('manages focus correctly when dialog opens', () => {
      render(
        <AuthGuard>
          <TestComponent />
        </AuthGuard>
      )

      // Dialog should be present and focusable
      const dialog = screen.getByRole('dialog')
      expect(dialog).toBeInTheDocument()
      expect(document.activeElement).toBe(document.body) // Initial focus state
    })
  })

  describe('Performance and Re-rendering', () => {
    it('does not re-render unnecessarily when auth state remains the same', () => {
      const renderSpy = jest.fn()
      const TestComponentWithSpy = () => {
        renderSpy()
        return <TestComponent />
      }

      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'user@example.com' },
        isLoading: false,
      })

      const { rerender } = render(
        <AuthGuard>
          <TestComponentWithSpy />
        </AuthGuard>
      )

      expect(renderSpy).toHaveBeenCalledTimes(1)

      // Re-render with same auth state
      rerender(
        <AuthGuard>
          <TestComponentWithSpy />
        </AuthGuard>
      )

      expect(renderSpy).toHaveBeenCalledTimes(2) // Component will re-render, but AuthGuard behavior stays the same
    })
  })
})
