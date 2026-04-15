import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useRouter } from 'next/navigation'
import LoginPage from '../page'

jest.mock('@/contexts/AuthContext')
jest.mock('@/contexts/I18nContext')
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}))

jest.mock('@/components/layout', () => ({
  LanguageSwitcher: () => (
    <div data-testid="language-switcher">LanguageSwitcher</div>
  ),
  ThemeToggle: () => <div data-testid="theme-toggle">ThemeToggle</div>,
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, ...props }: any) => (
    <button {...props}>{children}</button>
  ),
}))

describe('LoginPage', () => {
  const mockLogin = jest.fn()
  const mockRouterPush = jest.fn()
  const mockRouterReplace = jest.fn()
  const mockT = jest.fn((key: string) => key)

  beforeEach(() => {
    jest.clearAllMocks()

    // Clear sessionStorage
    if (typeof window !== 'undefined') {
      sessionStorage.clear()
    }

    ;(useAuth as jest.Mock).mockReturnValue({
      user: null,
      login: mockLogin,
      isLoading: false,
    })
    ;(useI18n as jest.Mock).mockReturnValue({
      t: mockT,
      currentLanguage: 'en',
    })
    ;(useRouter as jest.Mock).mockReturnValue({
      push: mockRouterPush,
      replace: mockRouterReplace,
    })
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  describe('Rendering', () => {
    it('should render login form', () => {
      render(<LoginPage />)

      expect(screen.getByTestId('auth-login-form')).toBeInTheDocument()
      expect(screen.getByTestId('auth-login-email-input')).toBeInTheDocument()
      expect(
        screen.getByTestId('auth-login-password-input')
      ).toBeInTheDocument()
      expect(screen.getByTestId('auth-login-submit-button')).toBeInTheDocument()
    })

    it('should render navigation elements', () => {
      render(<LoginPage />)

      expect(screen.getAllByText('BenGER').length).toBeGreaterThan(0)
      expect(screen.getByTestId('language-switcher')).toBeInTheDocument()
      expect(screen.getByTestId('theme-toggle')).toBeInTheDocument()
    })

    it('should render register link', () => {
      render(<LoginPage />)

      const registerLink = screen.getByTestId('auth-login-register-link')
      expect(registerLink).toBeInTheDocument()
      expect(registerLink).toHaveAttribute('href', '/register')
    })

    it('should render forgot password link', () => {
      render(<LoginPage />)

      const forgotPasswordLink = screen.getByTestId(
        'auth-login-forgot-password-link'
      )
      expect(forgotPasswordLink).toBeInTheDocument()
      expect(forgotPasswordLink).toHaveAttribute('href', '/reset-password')
    })

    it('should render back to landing link', () => {
      render(<LoginPage />)

      const backLink = screen.getByText('login.backToLanding')
      expect(backLink).toBeInTheDocument()
      expect(backLink.closest('a')).toHaveAttribute('href', '/')
    })
  })

  describe('Form Validation', () => {
    it('should have required fields', () => {
      render(<LoginPage />)

      const usernameInput = screen.getByTestId('auth-login-email-input')
      const passwordInput = screen.getByTestId('auth-login-password-input')

      expect(usernameInput).toHaveAttribute('required')
      expect(passwordInput).toHaveAttribute('required')
    })

    it('should allow typing in username field', async () => {
      const user = userEvent.setup()
      render(<LoginPage />)

      const usernameInput = screen.getByTestId(
        'auth-login-email-input'
      ) as HTMLInputElement
      await user.type(usernameInput, 'testuser')

      expect(usernameInput.value).toBe('testuser')
    })

    it('should allow typing in password field', async () => {
      const user = userEvent.setup()
      render(<LoginPage />)

      const passwordInput = screen.getByTestId(
        'auth-login-password-input'
      ) as HTMLInputElement
      await user.type(passwordInput, 'password123')

      expect(passwordInput.value).toBe('password123')
    })

    it('should have password field type as password', () => {
      render(<LoginPage />)

      const passwordInput = screen.getByTestId('auth-login-password-input')
      expect(passwordInput).toHaveAttribute('type', 'password')
    })
  })

  describe('Form Submission', () => {
    it('should call login function on form submit', async () => {
      const user = userEvent.setup()
      mockLogin.mockResolvedValue(undefined)

      render(<LoginPage />)

      const usernameInput = screen.getByTestId('auth-login-email-input')
      const passwordInput = screen.getByTestId('auth-login-password-input')
      const submitButton = screen.getByTestId('auth-login-submit-button')

      await user.type(usernameInput, 'testuser')
      await user.type(passwordInput, 'password123')
      await user.click(submitButton)

      await waitFor(() => {
        expect(mockLogin).toHaveBeenCalledWith('testuser', 'password123')
      })
    })

    it('should display loading state during submission', async () => {
      const user = userEvent.setup()
      let resolveLogin: any
      mockLogin.mockReturnValue(
        new Promise((resolve) => {
          resolveLogin = resolve
        })
      )

      render(<LoginPage />)

      const usernameInput = screen.getByTestId('auth-login-email-input')
      const passwordInput = screen.getByTestId('auth-login-password-input')
      const submitButton = screen.getByTestId('auth-login-submit-button')

      await user.type(usernameInput, 'testuser')
      await user.type(passwordInput, 'password123')
      await user.click(submitButton)

      await waitFor(() => {
        expect(submitButton).toBeDisabled()
        expect(screen.getByText('login.loading')).toBeInTheDocument()
      })

      resolveLogin()
    })

    it('should prevent multiple submissions while loading', async () => {
      const user = userEvent.setup()
      mockLogin.mockReturnValue(new Promise(() => {})) // Never resolves

      render(<LoginPage />)

      const usernameInput = screen.getByTestId('auth-login-email-input')
      const passwordInput = screen.getByTestId('auth-login-password-input')
      const submitButton = screen.getByTestId('auth-login-submit-button')

      await user.type(usernameInput, 'testuser')
      await user.type(passwordInput, 'password123')
      await user.click(submitButton)
      await user.click(submitButton)
      await user.click(submitButton)

      await waitFor(() => {
        expect(mockLogin).toHaveBeenCalledTimes(1)
      })
    })
  })

  describe('Error Handling', () => {
    it('should display error message on login failure', async () => {
      const user = userEvent.setup()
      mockLogin.mockRejectedValue(new Error('Invalid credentials'))

      render(<LoginPage />)

      const usernameInput = screen.getByTestId('auth-login-email-input')
      const passwordInput = screen.getByTestId('auth-login-password-input')
      const submitButton = screen.getByTestId('auth-login-submit-button')

      await user.type(usernameInput, 'wronguser')
      await user.type(passwordInput, 'wrongpassword')
      await user.click(submitButton)

      await waitFor(() => {
        const errorMessage = screen.getByTestId('auth-login-error-message')
        expect(errorMessage).toBeInTheDocument()
        expect(errorMessage).toHaveTextContent('Invalid credentials')
      })
    })

    it('should display generic error for non-Error objects', async () => {
      const user = userEvent.setup()
      mockLogin.mockRejectedValue('String error')

      render(<LoginPage />)

      const usernameInput = screen.getByTestId('auth-login-email-input')
      const passwordInput = screen.getByTestId('auth-login-password-input')
      const submitButton = screen.getByTestId('auth-login-submit-button')

      await user.type(usernameInput, 'testuser')
      await user.type(passwordInput, 'password123')
      await user.click(submitButton)

      await waitFor(() => {
        const errorMessage = screen.getByTestId('auth-login-error-message')
        expect(errorMessage).toHaveTextContent('login.failed')
      })
    })

    it('should clear error message when starting new submission', async () => {
      const user = userEvent.setup()
      mockLogin
        .mockRejectedValueOnce(new Error('First error'))
        .mockResolvedValueOnce(undefined)

      render(<LoginPage />)

      const usernameInput = screen.getByTestId('auth-login-email-input')
      const passwordInput = screen.getByTestId('auth-login-password-input')
      const submitButton = screen.getByTestId('auth-login-submit-button')

      // First submission with error
      await user.type(usernameInput, 'wronguser')
      await user.type(passwordInput, 'wrongpassword')
      await user.click(submitButton)

      await waitFor(() => {
        expect(
          screen.getByTestId('auth-login-error-message')
        ).toBeInTheDocument()
      })

      // Clear inputs
      await user.clear(usernameInput)
      await user.clear(passwordInput)

      // Second submission
      await user.type(usernameInput, 'correctuser')
      await user.type(passwordInput, 'correctpassword')
      await user.click(submitButton)

      await waitFor(() => {
        expect(
          screen.queryByTestId('auth-login-error-message')
        ).not.toBeInTheDocument()
      })
    })

    it('should re-enable submit button after error', async () => {
      const user = userEvent.setup()
      mockLogin.mockRejectedValue(new Error('Login failed'))

      render(<LoginPage />)

      const usernameInput = screen.getByTestId('auth-login-email-input')
      const passwordInput = screen.getByTestId('auth-login-password-input')
      const submitButton = screen.getByTestId('auth-login-submit-button')

      await user.type(usernameInput, 'testuser')
      await user.type(passwordInput, 'password123')
      await user.click(submitButton)

      await waitFor(() => {
        expect(
          screen.getByTestId('auth-login-error-message')
        ).toBeInTheDocument()
        expect(submitButton).not.toBeDisabled()
      })
    })
  })

  describe('Authentication Redirect', () => {
    it('should redirect authenticated users to dashboard', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', username: 'testuser' },
        login: mockLogin,
        isLoading: false,
      })

      render(<LoginPage />)

      expect(mockRouterReplace).toHaveBeenCalledWith('/dashboard')
    })

    it('should show loading state for authenticated users', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', username: 'testuser' },
        login: mockLogin,
        isLoading: false,
      })

      render(<LoginPage />)

      expect(screen.getByText('login.redirecting')).toBeInTheDocument()
      expect(screen.queryByTestId('auth-login-form')).not.toBeInTheDocument()
    })

    it('should not render form when user is authenticated', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', username: 'testuser' },
        login: mockLogin,
        isLoading: false,
      })

      render(<LoginPage />)

      expect(screen.queryByTestId('auth-login-form')).not.toBeInTheDocument()
    })
  })

  // Auto-login tests removed - auto-login moved to layout.tsx inline script

  describe('Accessibility', () => {
    it('should have proper form labels', () => {
      render(<LoginPage />)

      expect(screen.getByLabelText('login.username')).toBeInTheDocument()
      expect(screen.getByLabelText('login.password')).toBeInTheDocument()
    })

    it('should have proper autocomplete attributes', () => {
      render(<LoginPage />)

      const usernameInput = screen.getByTestId('auth-login-email-input')
      const passwordInput = screen.getByTestId('auth-login-password-input')

      expect(usernameInput).toHaveAttribute('autocomplete', 'username')
      expect(passwordInput).toHaveAttribute('autocomplete', 'current-password')
    })

    it('should have proper navigation aria-label', () => {
      render(<LoginPage />)

      const nav = screen.getByRole('navigation')
      expect(nav).toHaveAttribute('aria-label', 'Global')
    })
  })

  describe('i18n Integration', () => {
    it('should call translation function for all text', () => {
      render(<LoginPage />)

      expect(mockT).toHaveBeenCalledWith('login.title')
      expect(mockT).toHaveBeenCalledWith('login.subtitle')
      expect(mockT).toHaveBeenCalledWith('login.username')
      expect(mockT).toHaveBeenCalledWith('login.password')
      expect(mockT).toHaveBeenCalledWith('login.button')
      expect(mockT).toHaveBeenCalledWith('login.register')
      expect(mockT).toHaveBeenCalledWith('login.forgotPassword')
    })
  })

  describe('Form Interaction', () => {
    it('should handle Enter key submission', async () => {
      const user = userEvent.setup()
      mockLogin.mockResolvedValue(undefined)

      render(<LoginPage />)

      const usernameInput = screen.getByTestId('auth-login-email-input')
      const passwordInput = screen.getByTestId('auth-login-password-input')

      await user.type(usernameInput, 'testuser')
      await user.type(passwordInput, 'password123')
      await user.keyboard('{Enter}')

      await waitFor(() => {
        expect(mockLogin).toHaveBeenCalledWith('testuser', 'password123')
      })
    })

    it('should not submit form with empty fields', async () => {
      const user = userEvent.setup()
      render(<LoginPage />)

      const submitButton = screen.getByTestId('auth-login-submit-button')
      await user.click(submitButton)

      // Form validation should prevent submission
      expect(mockLogin).not.toHaveBeenCalled()
    })
  })

  describe('Button States', () => {
    it('should show login.button text when not loading', () => {
      render(<LoginPage />)

      expect(screen.getByText('login.button')).toBeInTheDocument()
    })

    it('should not show loading text initially', () => {
      render(<LoginPage />)

      expect(screen.queryByText('login.loading')).not.toBeInTheDocument()
    })
  })
})
