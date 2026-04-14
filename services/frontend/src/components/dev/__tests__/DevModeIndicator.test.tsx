/**
 * @jest-environment jsdom
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DevModeIndicator } from '../DevModeIndicator'

// Mock AuthContext
const mockUseAuth = jest.fn()
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}))

describe('DevModeIndicator', () => {
  let originalNodeEnv: string | undefined
  let originalDisableAutoLogin: string | undefined

  beforeEach(() => {
    jest.clearAllMocks()
    originalNodeEnv = process.env.NODE_ENV
    originalDisableAutoLogin = process.env.NEXT_PUBLIC_DISABLE_AUTO_LOGIN

    // Setup default mocks
    mockUseAuth.mockReturnValue({
      user: {
        id: '1',
        username: 'testuser',
        email: 'test@example.com',
        is_superadmin: false,
      },
    })

    // Mock window.location
    delete (window as any).location
    ;(window as any).location = { hostname: 'localhost' }
  })

  afterEach(() => {
    process.env.NODE_ENV = originalNodeEnv
    if (originalDisableAutoLogin === undefined) {
      delete process.env.NEXT_PUBLIC_DISABLE_AUTO_LOGIN
    } else {
      process.env.NEXT_PUBLIC_DISABLE_AUTO_LOGIN = originalDisableAutoLogin
    }
  })

  describe('visibility conditions', () => {
    it('shows indicator when dev auth enabled, localhost, and user exists', async () => {
      process.env.NODE_ENV = 'development'
      delete process.env.NEXT_PUBLIC_DISABLE_AUTO_LOGIN
      ;(window as any).location = { hostname: 'localhost' }

      render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.getByText('DEV MODE')).toBeInTheDocument()
      })
    })

    it('hides indicator when dev auth disabled', async () => {
      process.env.NODE_ENV = 'test'
      ;(window as any).location = { hostname: 'localhost' }

      render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.queryByText('DEV MODE')).not.toBeInTheDocument()
      })
    })

    it('hides indicator when user is null', async () => {
      process.env.NODE_ENV = 'development'
      delete process.env.NEXT_PUBLIC_DISABLE_AUTO_LOGIN
      ;(window as any).location = { hostname: 'localhost' }
      mockUseAuth.mockReturnValue({ user: null })

      render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.queryByText('DEV MODE')).not.toBeInTheDocument()
      })
    })

    it('hides indicator when user is undefined', async () => {
      process.env.NODE_ENV = 'development'
      delete process.env.NEXT_PUBLIC_DISABLE_AUTO_LOGIN
      ;(window as any).location = { hostname: 'localhost' }
      mockUseAuth.mockReturnValue({ user: undefined })

      render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.queryByText('DEV MODE')).not.toBeInTheDocument()
      })
    })
  })

  describe('badge rendering', () => {
    beforeEach(() => {
      process.env.NODE_ENV = 'development'
      delete process.env.NEXT_PUBLIC_DISABLE_AUTO_LOGIN
      ;(window as any).location = { hostname: 'localhost' }
    })

    it('renders badge with correct text', async () => {
      render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.getByText('DEV MODE')).toBeInTheDocument()
      })
    })

    it('renders badge as button', async () => {
      render(<DevModeIndicator />)

      await waitFor(() => {
        const badge = screen.getByRole('button')
        expect(badge).toBeInTheDocument()
        expect(badge).toHaveTextContent('DEV MODE')
      })
    })

    it('has correct title attribute', async () => {
      render(<DevModeIndicator />)

      await waitFor(() => {
        const badge = screen.getByRole('button')
        expect(badge).toHaveAttribute(
          'title',
          'Development mode with auto-authentication enabled'
        )
      })
    })

    it('includes animated pulse indicator', async () => {
      const { container } = render(<DevModeIndicator />)

      await waitFor(() => {
        const pulseElement = container.querySelector('.animate-pulse')
        expect(pulseElement).toBeInTheDocument()
      })
    })

    it('applies correct styling classes', async () => {
      render(<DevModeIndicator />)

      await waitFor(() => {
        const badge = screen.getByRole('button')
        expect(badge).toHaveClass(
          'flex',
          'items-center',
          'gap-2',
          'rounded-full',
          'border',
          'border-amber-300',
          'bg-amber-100'
        )
      })
    })

    it('applies dark mode classes', async () => {
      render(<DevModeIndicator />)

      await waitFor(() => {
        const badge = screen.getByRole('button')
        expect(badge).toHaveClass(
          'dark:border-amber-700',
          'dark:bg-amber-900/80',
          'dark:text-amber-200'
        )
      })
    })

    it('positions badge in bottom-right corner', async () => {
      const { container } = render(<DevModeIndicator />)

      await waitFor(() => {
        const wrapper = container.querySelector('.fixed.bottom-4.right-4')
        expect(wrapper).toBeInTheDocument()
      })
    })

    it('sets correct z-index for overlay', async () => {
      const { container } = render(<DevModeIndicator />)

      await waitFor(() => {
        const wrapper = container.querySelector('.z-50')
        expect(wrapper).toBeInTheDocument()
      })
    })
  })

  describe('details popup interaction', () => {
    beforeEach(() => {
      process.env.NODE_ENV = 'development'
      delete process.env.NEXT_PUBLIC_DISABLE_AUTO_LOGIN
      ;(window as any).location = { hostname: 'localhost' }
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          username: 'admin',
          email: 'admin@example.com',
          is_superadmin: true,
        },
      })
    })

    it('does not show details popup initially', async () => {
      render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.getByText('DEV MODE')).toBeInTheDocument()
      })

      expect(
        screen.queryByText('Development Mode Active')
      ).not.toBeInTheDocument()
    })

    it('shows details popup when badge clicked', async () => {
      const user = userEvent.setup()
      render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.getByText('DEV MODE')).toBeInTheDocument()
      })

      const badge = screen.getByRole('button')
      await user.click(badge)

      expect(screen.getByText('Development Mode Active')).toBeInTheDocument()
    })

    it('hides details popup when badge clicked again', async () => {
      const user = userEvent.setup()
      render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.getByText('DEV MODE')).toBeInTheDocument()
      })

      const badge = screen.getByRole('button')
      await user.click(badge)
      expect(screen.getByText('Development Mode Active')).toBeInTheDocument()

      await user.click(badge)
      expect(
        screen.queryByText('Development Mode Active')
      ).not.toBeInTheDocument()
    })

    it('displays username in details', async () => {
      const user = userEvent.setup()
      render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.getByText('DEV MODE')).toBeInTheDocument()
      })

      const badge = screen.getByRole('button')
      await user.click(badge)

      expect(screen.getByText('admin')).toBeInTheDocument()
    })

    it('displays email in details', async () => {
      const user = userEvent.setup()
      render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.getByText('DEV MODE')).toBeInTheDocument()
      })

      const badge = screen.getByRole('button')
      await user.click(badge)

      expect(screen.getByText(/admin@example.com/)).toBeInTheDocument()
    })

    it('displays hostname in details', async () => {
      const user = userEvent.setup()
      render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.getByText('DEV MODE')).toBeInTheDocument()
      })

      const badge = screen.getByRole('button')
      await user.click(badge)

      expect(screen.getByText(/localhost/)).toBeInTheDocument()
    })

    it('displays superadmin status as Yes', async () => {
      const user = userEvent.setup()
      render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.getByText('DEV MODE')).toBeInTheDocument()
      })

      const badge = screen.getByRole('button')
      await user.click(badge)

      expect(screen.getByText(/Superadmin:.*Yes/)).toBeInTheDocument()
    })

    it('displays superadmin status as No for non-superadmin', async () => {
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          username: 'user',
          email: 'user@example.com',
          is_superadmin: false,
        },
      })

      const user = userEvent.setup()
      render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.getByText('DEV MODE')).toBeInTheDocument()
      })

      const badge = screen.getByRole('button')
      await user.click(badge)

      expect(screen.getByText(/Superadmin:.*No/)).toBeInTheDocument()
    })

    it('includes close button in details popup', async () => {
      const user = userEvent.setup()
      render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.getByText('DEV MODE')).toBeInTheDocument()
      })

      const badge = screen.getByRole('button')
      await user.click(badge)

      const closeButton = screen.getByRole('button', { name: /close/i })
      expect(closeButton).toBeInTheDocument()
    })

    it('closes details popup when close button clicked', async () => {
      const user = userEvent.setup()
      render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.getByText('DEV MODE')).toBeInTheDocument()
      })

      const badge = screen.getByRole('button')
      await user.click(badge)
      expect(screen.getByText('Development Mode Active')).toBeInTheDocument()

      const closeButton = screen.getByRole('button', { name: /close/i })
      await user.click(closeButton)

      expect(
        screen.queryByText('Development Mode Active')
      ).not.toBeInTheDocument()
    })

    it('positions details popup above badge', async () => {
      const user = userEvent.setup()
      const { container } = render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.getByText('DEV MODE')).toBeInTheDocument()
      })

      const badge = screen.getByRole('button')
      await user.click(badge)

      const popup = container.querySelector('.fixed.bottom-16.right-4')
      expect(popup).toBeInTheDocument()
    })

    it('applies transition classes to details popup', async () => {
      const user = userEvent.setup()
      const { container } = render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.getByText('DEV MODE')).toBeInTheDocument()
      })

      const badge = screen.getByRole('button')
      await user.click(badge)

      const popup = container.querySelector('.transition-opacity')
      expect(popup).toBeInTheDocument()
    })
  })

  describe('user data display', () => {
    beforeEach(() => {
      process.env.NODE_ENV = 'development'
      delete process.env.NEXT_PUBLIC_DISABLE_AUTO_LOGIN
      ;(window as any).location = { hostname: 'localhost' }
    })

    it('handles user with special characters in username', async () => {
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          username: 'user@name-123',
          email: 'test@example.com',
          is_superadmin: false,
        },
      })

      const user = userEvent.setup()
      render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.getByText('DEV MODE')).toBeInTheDocument()
      })

      const badge = screen.getByRole('button')
      await user.click(badge)

      expect(screen.getByText('user@name-123')).toBeInTheDocument()
    })

    it('handles long email addresses', async () => {
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          username: 'user',
          email: 'very.long.email.address@subdomain.example.com',
          is_superadmin: false,
        },
      })

      const user = userEvent.setup()
      render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.getByText('DEV MODE')).toBeInTheDocument()
      })

      const badge = screen.getByRole('button')
      await user.click(badge)

      expect(
        screen.getByText(/very.long.email.address@subdomain.example.com/)
      ).toBeInTheDocument()
    })

    it('handles user with empty email', async () => {
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          username: 'user',
          email: '',
          is_superadmin: false,
        },
      })

      const user = userEvent.setup()
      render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.getByText('DEV MODE')).toBeInTheDocument()
      })

      const badge = screen.getByRole('button')
      await user.click(badge)

      expect(screen.getByText('Development Mode Active')).toBeInTheDocument()
    })

    it('handles undefined is_superadmin', async () => {
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          username: 'user',
          email: 'test@example.com',
          is_superadmin: undefined,
        },
      })

      const user = userEvent.setup()
      render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.getByText('DEV MODE')).toBeInTheDocument()
      })

      const badge = screen.getByRole('button')
      await user.click(badge)

      expect(screen.getByText(/Superadmin:.*No/)).toBeInTheDocument()
    })
  })

  describe('re-render behavior', () => {
    beforeEach(() => {
      process.env.NODE_ENV = 'development'
      delete process.env.NEXT_PUBLIC_DISABLE_AUTO_LOGIN
      ;(window as any).location = { hostname: 'localhost' }
    })

    it('shows indicator when user logs in', async () => {
      mockUseAuth.mockReturnValue({ user: null })
      const { rerender } = render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.queryByText('DEV MODE')).not.toBeInTheDocument()
      })

      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          username: 'testuser',
          email: 'test@example.com',
          is_superadmin: false,
        },
      })

      rerender(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.getByText('DEV MODE')).toBeInTheDocument()
      })
    })

    it('hides indicator when user logs out', async () => {
      const { rerender } = render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.getByText('DEV MODE')).toBeInTheDocument()
      })

      mockUseAuth.mockReturnValue({ user: null })
      rerender(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.queryByText('DEV MODE')).not.toBeInTheDocument()
      })
    })

    it('updates user info when user changes', async () => {
      const { rerender } = render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.getByText('DEV MODE')).toBeInTheDocument()
      })

      mockUseAuth.mockReturnValue({
        user: {
          id: '2',
          username: 'newuser',
          email: 'new@example.com',
          is_superadmin: false,
        },
      })

      rerender(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.getByText('DEV MODE')).toBeInTheDocument()
      })
    })
  })

  describe('accessibility', () => {
    beforeEach(() => {
      process.env.NODE_ENV = 'development'
      delete process.env.NEXT_PUBLIC_DISABLE_AUTO_LOGIN
      ;(window as any).location = { hostname: 'localhost' }
    })

    it('badge is keyboard accessible', async () => {
      const user = userEvent.setup()
      render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.getByText('DEV MODE')).toBeInTheDocument()
      })

      const badge = screen.getByRole('button')
      badge.focus()
      expect(badge).toHaveFocus()

      await user.keyboard('{Enter}')
      expect(screen.getByText('Development Mode Active')).toBeInTheDocument()
    })

    it('close button is keyboard accessible', async () => {
      const user = userEvent.setup()
      render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.getByText('DEV MODE')).toBeInTheDocument()
      })

      const badge = screen.getByRole('button')
      await user.click(badge)

      const closeButton = screen.getByRole('button', { name: /close/i })
      closeButton.focus()
      expect(closeButton).toHaveFocus()
    })

    it('has proper aria-label for close button', async () => {
      const user = userEvent.setup()
      render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.getByText('DEV MODE')).toBeInTheDocument()
      })

      const badge = screen.getByRole('button')
      await user.click(badge)

      const closeButton = screen.getByRole('button', { name: /close/i })
      expect(closeButton).toHaveAttribute('aria-label', 'Close')
    })

    it('provides descriptive title for badge', async () => {
      render(<DevModeIndicator />)

      await waitFor(() => {
        const badge = screen.getByRole('button')
        expect(badge).toHaveAttribute(
          'title',
          'Development mode with auto-authentication enabled'
        )
      })
    })
  })

  describe('edge cases', () => {
    it('handles rapid toggle clicks', async () => {
      process.env.NODE_ENV = 'development'
      delete process.env.NEXT_PUBLIC_DISABLE_AUTO_LOGIN
      ;(window as any).location = { hostname: 'localhost' }

      const user = userEvent.setup()
      render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.getByText('DEV MODE')).toBeInTheDocument()
      })

      const badge = screen.getByRole('button')

      // Click odd number of times to end with closed state
      await user.click(badge)
      expect(screen.getByText('Development Mode Active')).toBeInTheDocument()
      await user.click(badge)
      await user.click(badge)

      expect(screen.getByText('Development Mode Active')).toBeInTheDocument()
    })

    it('handles missing user properties gracefully', async () => {
      process.env.NODE_ENV = 'development'
      delete process.env.NEXT_PUBLIC_DISABLE_AUTO_LOGIN
      ;(window as any).location = { hostname: 'localhost' }
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
        } as any,
      })

      const user = userEvent.setup()
      render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.getByText('DEV MODE')).toBeInTheDocument()
      })

      const badge = screen.getByRole('button')
      await user.click(badge)

      expect(screen.getByText('Development Mode Active')).toBeInTheDocument()
    })

    it('returns null when not visible', () => {
      process.env.NODE_ENV = 'test'
      const { container } = render(<DevModeIndicator />)
      expect(container.firstChild).toBeNull()
    })

    it('handles hostname with port number', async () => {
      process.env.NODE_ENV = 'development'
      delete process.env.NEXT_PUBLIC_DISABLE_AUTO_LOGIN
      ;(window as any).location = { hostname: 'localhost' }

      const user = userEvent.setup()
      render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.getByText('DEV MODE')).toBeInTheDocument()
      })

      const badge = screen.getByRole('button')
      await user.click(badge)

      expect(screen.getByText(/localhost/)).toBeInTheDocument()
    })
  })

  describe('styling and visual elements', () => {
    beforeEach(() => {
      process.env.NODE_ENV = 'development'
      delete process.env.NEXT_PUBLIC_DISABLE_AUTO_LOGIN
      ;(window as any).location = { hostname: 'localhost' }
    })

    it('includes shadow on badge', async () => {
      render(<DevModeIndicator />)

      await waitFor(() => {
        const badge = screen.getByRole('button')
        expect(badge).toHaveClass('shadow-sm')
      })
    })

    it('includes shadow on details popup', async () => {
      const user = userEvent.setup()
      const { container } = render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.getByText('DEV MODE')).toBeInTheDocument()
      })

      const badge = screen.getByRole('button')
      await user.click(badge)

      const popup = container.querySelector('.shadow-lg')
      expect(popup).toBeInTheDocument()
    })

    it('applies rounded corners to badge', async () => {
      render(<DevModeIndicator />)

      await waitFor(() => {
        const badge = screen.getByRole('button')
        expect(badge).toHaveClass('rounded-full')
      })
    })

    it('applies rounded corners to details popup', async () => {
      const user = userEvent.setup()
      const { container } = render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.getByText('DEV MODE')).toBeInTheDocument()
      })

      const badge = screen.getByRole('button')
      await user.click(badge)

      const popup = container.querySelector('.rounded-lg')
      expect(popup).toBeInTheDocument()
    })

    it('uses max-width for details popup', async () => {
      const user = userEvent.setup()
      const { container } = render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.getByText('DEV MODE')).toBeInTheDocument()
      })

      const badge = screen.getByRole('button')
      await user.click(badge)

      const popup = container.querySelector('.max-w-sm')
      expect(popup).toBeInTheDocument()
    })

    it('uses proper spacing in details', async () => {
      const user = userEvent.setup()
      const { container } = render(<DevModeIndicator />)

      await waitFor(() => {
        expect(screen.getByText('DEV MODE')).toBeInTheDocument()
      })

      const badge = screen.getByRole('button')
      await user.click(badge)

      const contentWrapper = container.querySelector('.space-y-1')
      expect(contentWrapper).toBeInTheDocument()
    })
  })
})
