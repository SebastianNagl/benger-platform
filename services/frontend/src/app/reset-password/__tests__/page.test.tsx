/**
 * @jest-environment jsdom
 *
 * Comprehensive tests for Reset Password page
 * Tests form rendering, submission, validation, success/error states, and navigation
 */

import ResetPasswordPage from '@/app/reset-password/page'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'

// Mock next/link
jest.mock('next/link', () => {
  return function MockLink({ children, href }: { children: React.ReactNode; href: string }) {
    return <a href={href}>{children}</a>
  }
})

// Mock components
jest.mock('@/components/layout', () => ({
  LanguageSwitcher: () => (
    <div data-testid="language-switcher">Language Switcher</div>
  ),
  ThemeToggle: () => <div data-testid="theme-toggle">Theme Toggle</div>,
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, disabled, type, className }: any) => (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={className}
      data-testid="submit-button"
    >
      {children}
    </button>
  ),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'passwordReset.title': 'Reset Your Password',
        'passwordReset.description':
          'Enter your email address and we will send you a link',
        'passwordReset.emailLabel': 'Email Address',
        'passwordReset.emailPlaceholder': 'you@example.com',
        'passwordReset.send': 'Send Reset Link',
        'passwordReset.sending': 'Sending...',
        'passwordReset.sent': 'Check Your Email',
        'passwordReset.sentDescription':
          'We sent a password reset link to your email',
        'passwordReset.backToLogin': 'Back to Login',
        'emailVerification.didntReceive': "Didn't receive the email?",
        'common.loading': 'Loading...',
      }
      return translations[key] || key
    },
    currentLanguage: 'en',
  }),
}))

// Mock fetch
global.fetch = jest.fn()

describe('Reset Password Page', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    ;(global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => ({ success: true }),
    })
  })

  describe('Page Structure', () => {
    it('renders without crashing', () => {
      render(<ResetPasswordPage />)
      expect(screen.getByText('Reset Your Password')).toBeInTheDocument()
    })

    it('renders header with logo', () => {
      render(<ResetPasswordPage />)
      const bengerElements = screen.getAllByText('BenGER')
      expect(bengerElements.length).toBeGreaterThan(0)
      expect(screen.getByText('🤘')).toBeInTheDocument()
    })

    it('renders navigation link to login', () => {
      render(<ResetPasswordPage />)
      const links = screen.getAllByText('Back to Login')
      expect(links.length).toBeGreaterThan(0)
    })

    it('renders language switcher', () => {
      render(<ResetPasswordPage />)
      expect(screen.getByTestId('language-switcher')).toBeInTheDocument()
    })

    it('renders theme toggle', () => {
      render(<ResetPasswordPage />)
      expect(screen.getByTestId('theme-toggle')).toBeInTheDocument()
    })

    it('applies correct main layout classes', () => {
      const { container } = render(<ResetPasswordPage />)
      const main = container.querySelector('main')
      expect(main).toHaveClass('min-h-[calc(100vh-80px)]')
    })
  })

  describe('Form Elements', () => {
    it('renders form with correct title', () => {
      render(<ResetPasswordPage />)
      expect(screen.getByText('Reset Your Password')).toBeInTheDocument()
    })

    it('renders form description', () => {
      render(<ResetPasswordPage />)
      expect(screen.getByText(/Enter your email address/)).toBeInTheDocument()
    })

    it('renders email input field', () => {
      render(<ResetPasswordPage />)
      const input = screen.getByLabelText('Email Address')
      expect(input).toBeInTheDocument()
      expect(input).toHaveAttribute('type', 'email')
    })

    it('renders email input with correct placeholder', () => {
      render(<ResetPasswordPage />)
      const input = screen.getByPlaceholderText('you@example.com')
      expect(input).toBeInTheDocument()
    })

    it('email input is required', () => {
      render(<ResetPasswordPage />)
      const input = screen.getByLabelText('Email Address')
      expect(input).toHaveAttribute('required')
    })

    it('email input has autocomplete attribute', () => {
      render(<ResetPasswordPage />)
      const input = screen.getByLabelText('Email Address')
      expect(input).toHaveAttribute('autocomplete', 'email')
    })

    it('renders submit button', () => {
      render(<ResetPasswordPage />)
      expect(screen.getByTestId('submit-button')).toBeInTheDocument()
    })

    it('submit button displays correct text initially', () => {
      render(<ResetPasswordPage />)
      expect(screen.getByText('Send Reset Link')).toBeInTheDocument()
    })
  })

  describe('Form Interaction', () => {
    it('updates email state when typing', async () => {
      const user = userEvent.setup()
      render(<ResetPasswordPage />)

      const input = screen.getByLabelText('Email Address') as HTMLInputElement
      await user.type(input, 'test@example.com')

      expect(input.value).toBe('test@example.com')
    })

    it('clears email field when cleared', async () => {
      const user = userEvent.setup()
      render(<ResetPasswordPage />)

      const input = screen.getByLabelText('Email Address') as HTMLInputElement
      await user.type(input, 'test@example.com')
      await user.clear(input)

      expect(input.value).toBe('')
    })

    it('handles multiple email changes', async () => {
      const user = userEvent.setup()
      render(<ResetPasswordPage />)

      const input = screen.getByLabelText('Email Address') as HTMLInputElement
      await user.type(input, 'first@example.com')
      expect(input.value).toBe('first@example.com')

      await user.clear(input)
      await user.type(input, 'second@example.com')
      expect(input.value).toBe('second@example.com')
    })
  })

  describe('Form Submission', () => {
    it('calls API with correct parameters on submit', async () => {
      render(<ResetPasswordPage />)

      const input = screen.getByLabelText('Email Address')
      const form = screen
        .getByRole('button', { name: /Send Reset Link/ })
        .closest('form')

      fireEvent.change(input, { target: { value: 'test@example.com' } })
      fireEvent.submit(form!)

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          '/api/auth/request-password-reset',
          expect.objectContaining({
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              email: 'test@example.com',
              language: 'en',
            }),
          })
        )
      })
    })

    it('shows loading state during submission', async () => {
      ;(global.fetch as jest.Mock).mockImplementation(
        () => new Promise((resolve) => setTimeout(resolve, 100))
      )

      render(<ResetPasswordPage />)

      const input = screen.getByLabelText('Email Address')
      const form = screen
        .getByRole('button', { name: /Send Reset Link/ })
        .closest('form')

      fireEvent.change(input, { target: { value: 'test@example.com' } })
      fireEvent.submit(form!)

      await waitFor(() => {
        expect(screen.getByText('Sending...')).toBeInTheDocument()
      })
    })

    it('disables submit button during submission', async () => {
      ;(global.fetch as jest.Mock).mockImplementation(
        () => new Promise((resolve) => setTimeout(resolve, 100))
      )

      render(<ResetPasswordPage />)

      const input = screen.getByLabelText('Email Address')
      const button = screen.getByTestId('submit-button')
      const form = button.closest('form')

      fireEvent.change(input, { target: { value: 'test@example.com' } })
      fireEvent.submit(form!)

      await waitFor(() => {
        expect(button).toBeDisabled()
      })
    })

    it('shows spinner icon during loading', async () => {
      ;(global.fetch as jest.Mock).mockImplementation(
        () => new Promise((resolve) => setTimeout(resolve, 100))
      )

      render(<ResetPasswordPage />)

      const input = screen.getByLabelText('Email Address')
      const form = screen
        .getByRole('button', { name: /Send Reset Link/ })
        .closest('form')

      fireEvent.change(input, { target: { value: 'test@example.com' } })
      fireEvent.submit(form!)

      await waitFor(() => {
        const spinner = document.querySelector('.animate-spin')
        expect(spinner).toBeInTheDocument()
      })
    })
  })

  describe('Success State', () => {
    it('shows success message after submission', async () => {
      render(<ResetPasswordPage />)

      const input = screen.getByLabelText('Email Address')
      const form = screen
        .getByRole('button', { name: /Send Reset Link/ })
        .closest('form')

      fireEvent.change(input, { target: { value: 'test@example.com' } })
      fireEvent.submit(form!)

      await waitFor(() => {
        expect(screen.getByText('Check Your Email')).toBeInTheDocument()
      })
    })

    it('shows success description', async () => {
      render(<ResetPasswordPage />)

      const input = screen.getByLabelText('Email Address')
      const form = screen
        .getByRole('button', { name: /Send Reset Link/ })
        .closest('form')

      fireEvent.change(input, { target: { value: 'test@example.com' } })
      fireEvent.submit(form!)

      await waitFor(() => {
        expect(
          screen.getByText(/We sent a password reset link/)
        ).toBeInTheDocument()
      })
    })

    it('hides form after successful submission', async () => {
      render(<ResetPasswordPage />)

      const input = screen.getByLabelText('Email Address')
      const form = screen
        .getByRole('button', { name: /Send Reset Link/ })
        .closest('form')

      fireEvent.change(input, { target: { value: 'test@example.com' } })
      fireEvent.submit(form!)

      await waitFor(() => {
        expect(screen.queryByLabelText('Email Address')).not.toBeInTheDocument()
      })
    })

    it('shows success icon', async () => {
      render(<ResetPasswordPage />)

      const input = screen.getByLabelText('Email Address')
      const form = screen
        .getByRole('button', { name: /Send Reset Link/ })
        .closest('form')

      fireEvent.change(input, { target: { value: 'test@example.com' } })
      fireEvent.submit(form!)

      await waitFor(() => {
        const icon = document.querySelector('.text-emerald-600')
        expect(icon).toBeInTheDocument()
      })
    })

    it('shows try again link on success page', async () => {
      render(<ResetPasswordPage />)

      const input = screen.getByLabelText('Email Address')
      const form = screen
        .getByRole('button', { name: /Send Reset Link/ })
        .closest('form')

      fireEvent.change(input, { target: { value: 'test@example.com' } })
      fireEvent.submit(form!)

      await waitFor(() => {
        expect(screen.getByText('try again')).toBeInTheDocument()
      })
    })

    it('returns to form when try again is clicked', async () => {
      const user = userEvent.setup()
      render(<ResetPasswordPage />)

      const input = screen.getByLabelText('Email Address')
      const form = screen
        .getByRole('button', { name: /Send Reset Link/ })
        .closest('form')

      fireEvent.change(input, { target: { value: 'test@example.com' } })
      fireEvent.submit(form!)

      await waitFor(() => {
        expect(screen.getByText('try again')).toBeInTheDocument()
      })

      const tryAgainButton = screen.getByText('try again')
      await user.click(tryAgainButton)

      await waitFor(() => {
        expect(screen.getByLabelText('Email Address')).toBeInTheDocument()
      })
    })
  })

  describe('Error Handling', () => {
    it('shows success even on API error (prevent enumeration)', async () => {
      ;(global.fetch as jest.Mock).mockRejectedValue(new Error('Network error'))

      render(<ResetPasswordPage />)

      const input = screen.getByLabelText('Email Address')
      const form = screen
        .getByRole('button', { name: /Send Reset Link/ })
        .closest('form')

      fireEvent.change(input, { target: { value: 'test@example.com' } })
      fireEvent.submit(form!)

      await waitFor(() => {
        expect(screen.getByText('Check Your Email')).toBeInTheDocument()
      })
    })

    it('shows success on 404 response (prevent enumeration)', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValue({
        ok: false,
        status: 404,
        statusText: 'Not Found',
      })

      render(<ResetPasswordPage />)

      const input = screen.getByLabelText('Email Address')
      const form = screen
        .getByRole('button', { name: /Send Reset Link/ })
        .closest('form')

      fireEvent.change(input, { target: { value: 'nonexistent@example.com' } })
      fireEvent.submit(form!)

      await waitFor(() => {
        expect(screen.getByText('Check Your Email')).toBeInTheDocument()
      })
    })

    it('shows success on server error (prevent enumeration)', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValue({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
      })

      render(<ResetPasswordPage />)

      const input = screen.getByLabelText('Email Address')
      const form = screen
        .getByRole('button', { name: /Send Reset Link/ })
        .closest('form')

      fireEvent.change(input, { target: { value: 'test@example.com' } })
      fireEvent.submit(form!)

      await waitFor(() => {
        expect(screen.getByText('Check Your Email')).toBeInTheDocument()
      })
    })

    it('logs error to console on failure', async () => {
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation()
      ;(global.fetch as jest.Mock).mockRejectedValue(new Error('Network error'))

      render(<ResetPasswordPage />)

      const input = screen.getByLabelText('Email Address')
      const form = screen
        .getByRole('button', { name: /Send Reset Link/ })
        .closest('form')

      fireEvent.change(input, { target: { value: 'test@example.com' } })
      fireEvent.submit(form!)

      await waitFor(() => {
        expect(consoleErrorSpy).toHaveBeenCalled()
      })

      consoleErrorSpy.mockRestore()
    })
  })

  describe('Navigation', () => {
    it('renders link to login page in header', () => {
      render(<ResetPasswordPage />)
      const links = screen.getAllByText('Back to Login')
      expect(links[0].closest('a')).toHaveAttribute('href', '/login')
    })

    it('renders link to login page in form', () => {
      render(<ResetPasswordPage />)
      const links = screen.getAllByText('Back to Login')
      expect(links.length).toBe(2)
    })

    it('renders link to home page via logo', () => {
      render(<ResetPasswordPage />)
      const bengerElements = screen.getAllByText('BenGER')
      const logoLink = bengerElements[0].closest('a')
      expect(logoLink).toHaveAttribute('href', '/')
    })
  })

  describe('Styling and Layout', () => {
    it('applies dark mode classes', () => {
      render(<ResetPasswordPage />)
      const title = screen.getByText('Reset Your Password')
      expect(title).toHaveClass('dark:text-white')
    })

    it('applies correct button styling', () => {
      render(<ResetPasswordPage />)
      const button = screen.getByTestId('submit-button')
      expect(button).toHaveClass('bg-emerald-600')
    })

    it('centers main content', () => {
      const { container } = render(<ResetPasswordPage />)
      const main = container.querySelector('main')
      expect(main).toHaveClass('items-center', 'justify-center')
    })

    it('applies correct form width', () => {
      const { container } = render(<ResetPasswordPage />)
      const formContainer = container.querySelector('.max-w-md')
      expect(formContainer).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('has accessible form labels', () => {
      render(<ResetPasswordPage />)
      const input = screen.getByLabelText('Email Address')
      expect(input).toBeInTheDocument()
    })

    it('has semantic header element', () => {
      const { container } = render(<ResetPasswordPage />)
      const header = container.querySelector('header')
      expect(header).toBeInTheDocument()
    })

    it('has semantic main element', () => {
      const { container } = render(<ResetPasswordPage />)
      const main = container.querySelector('main')
      expect(main).toBeInTheDocument()
    })

    it('has semantic nav element', () => {
      const { container } = render(<ResetPasswordPage />)
      const nav = container.querySelector('nav')
      expect(nav).toBeInTheDocument()
    })

    it('nav has aria-label', () => {
      const { container } = render(<ResetPasswordPage />)
      const nav = container.querySelector('nav')
      expect(nav).toHaveAttribute('aria-label', 'Global')
    })

    it('logo has screen reader text', () => {
      render(<ResetPasswordPage />)
      expect(
        screen.getByText('BenGER', { selector: '.sr-only' })
      ).toBeInTheDocument()
    })

    it('success icon has proper SVG structure', async () => {
      render(<ResetPasswordPage />)

      const input = screen.getByLabelText('Email Address')
      const form = screen
        .getByRole('button', { name: /Send Reset Link/ })
        .closest('form')

      fireEvent.change(input, { target: { value: 'test@example.com' } })
      fireEvent.submit(form!)

      await waitFor(() => {
        const svg = document.querySelector('svg')
        expect(svg).toHaveAttribute('viewBox', '0 0 24 24')
      })
    })
  })

  describe('Responsive Design', () => {
    it('applies responsive padding', () => {
      const { container } = render(<ResetPasswordPage />)
      const main = container.querySelector('main')
      expect(main).toHaveClass('px-6', 'lg:px-8')
    })

    it('applies responsive header padding', () => {
      const { container } = render(<ResetPasswordPage />)
      const nav = container.querySelector('nav')
      expect(nav).toHaveClass('lg:px-8')
    })

    it('applies responsive layout', () => {
      const { container } = render(<ResetPasswordPage />)
      const nav = container.querySelector('nav')
      expect(nav).toHaveClass('lg:px-8')
    })
  })
})
