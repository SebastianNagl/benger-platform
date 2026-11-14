import { useI18n } from '@/contexts/I18nContext'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useRouter, useSearchParams } from 'next/navigation'
import VerifyEmailPage from '../page'

jest.mock('@/contexts/I18nContext')
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
  useSearchParams: jest.fn(),
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

describe('VerifyEmailPage', () => {
  const mockRouterPush = jest.fn()
  const mockT = jest.fn((key: string) => key)
  let mockSearchParams: URLSearchParams

  beforeEach(() => {
    jest.clearAllMocks()
    global.fetch = jest.fn()

    mockSearchParams = new URLSearchParams()
    ;(useI18n as jest.Mock).mockReturnValue({
      t: mockT,
      currentLanguage: 'en',
    })
    ;(useRouter as jest.Mock).mockReturnValue({
      push: mockRouterPush,
      replace: jest.fn(),
    })
    ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  describe('Rendering', () => {
    it('should render navigation elements', () => {
      render(<VerifyEmailPage />)

      expect(screen.getAllByText('BenGER').length).toBeGreaterThan(0)
      expect(screen.getByTestId('language-switcher')).toBeInTheDocument()
      expect(screen.getByTestId('theme-toggle')).toBeInTheDocument()
    })

    it('should show loading state initially when token present', () => {
      mockSearchParams.set('token', 'test-token')
      ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)

      render(<VerifyEmailPage />)

      expect(
        screen.getByText('emailVerification.verifying'),
      ).toBeInTheDocument()
    })

    it('should show info message when messageKey param present', () => {
      mockSearchParams.set('messageKey', 'registrationSuccess')
      ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)

      render(<VerifyEmailPage />)

      waitFor(() => {
        expect(
          screen.getByText('emailVerification.checkInbox'),
        ).toBeInTheDocument()
        // Component calls t(`emailVerification.${messageKey}`)
        expect(
          screen.getByText('emailVerification.registrationSuccess'),
        ).toBeInTheDocument()
      })
    })

    it('should show error when no token or messageKey provided', () => {
      render(<VerifyEmailPage />)

      waitFor(() => {
        expect(
          screen.getByText('emailVerification.invalid'),
        ).toBeInTheDocument()
        // Component calls t('emailVerification.noToken')
        expect(
          screen.getByText('emailVerification.noToken'),
        ).toBeInTheDocument()
      })
    })
  })

  describe('Email Verification with Token', () => {
    it('should call API to verify email with token', async () => {
      mockSearchParams.set('token', 'valid-token')
      ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ email: 'test@example.com' }),
      })

      render(<VerifyEmailPage />)

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith('/api/auth/verify-email', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            token: 'valid-token',
          }),
        })
      })
    })

    it('should show success message on successful verification', async () => {
      mockSearchParams.set('token', 'valid-token')
      ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ email: 'test@example.com' }),
      })

      render(<VerifyEmailPage />)

      await waitFor(() => {
        expect(
          screen.getByText('emailVerification.verified'),
        ).toBeInTheDocument()
        expect(
          screen.getByText('emailVerification.verifiedDescription'),
        ).toBeInTheDocument()
      })
    })

    it('should display user email on successful verification', async () => {
      mockSearchParams.set('token', 'valid-token')
      ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ email: 'verified@example.com' }),
      })

      render(<VerifyEmailPage />)

      await waitFor(() => {
        // Component renders: {t('emailVerification.emailLabel')} {email}
        // Mock t() returns the key, so we expect: 'emailVerification.emailLabel verified@example.com'
        expect(
          screen.getByText(
            /emailVerification\.emailLabel.*verified@example\.com/i,
          ),
        ).toBeInTheDocument()
      })
    })

    it('should redirect to login after successful verification', async () => {
      jest.useFakeTimers()
      mockSearchParams.set('token', 'valid-token')
      ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ email: 'test@example.com' }),
      })

      render(<VerifyEmailPage />)

      await waitFor(() => {
        expect(
          screen.getByText('emailVerification.verified'),
        ).toBeInTheDocument()
      })

      jest.advanceTimersByTime(3000)

      await waitFor(() => {
        expect(mockRouterPush).toHaveBeenCalledWith('/login')
      })

      jest.useRealTimers()
    })

    it('should show error message on verification failure', async () => {
      mockSearchParams.set('token', 'invalid-token')
      ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        json: async () => ({ detail: 'Invalid verification token' }),
      })

      render(<VerifyEmailPage />)

      await waitFor(() => {
        expect(
          screen.getByText('emailVerification.invalid'),
        ).toBeInTheDocument()
        expect(
          screen.getByText('Invalid verification token'),
        ).toBeInTheDocument()
      })
    })

    it('should handle network errors gracefully', async () => {
      mockSearchParams.set('token', 'test-token')
      ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)
      ;(global.fetch as jest.Mock).mockRejectedValueOnce(
        new Error('Network error'),
      )

      render(<VerifyEmailPage />)

      await waitFor(() => {
        expect(
          screen.getByText('emailVerification.invalid'),
        ).toBeInTheDocument()
        expect(
          screen.getByText('emailVerification.invalidDescription'),
        ).toBeInTheDocument()
      })
    })
  })

  describe('Resend Verification', () => {
    // Regression: after a login refused for an unverified address the page
    // used to show no resend control at all, so an account whose address
    // never got a mail stayed locked out.
    beforeEach(() => {
      ;(useI18n as jest.Mock).mockReturnValue({ t: mockT, locale: 'de' })
    })

    it('offers a prefilled resend after the login 403 and sends it', async () => {
      const user = userEvent.setup()
      mockSearchParams.set('messageKey', 'verifyEmailRequired')
      mockSearchParams.set('email', 'stuck@example.org')
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({}),
      })

      render(<VerifyEmailPage />)

      const input = await screen.findByTestId('verify-email-resend-input')
      expect(input).toHaveValue('stuck@example.org')
      expect(
        screen.getByText('emailVerification.verifyEmailRequired'),
      ).toBeInTheDocument()

      await user.click(screen.getByTestId('verify-email-resend-button'))

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          '/api/auth/resend-verification',
          expect.objectContaining({
            method: 'POST',
            body: JSON.stringify({
              email: 'stuck@example.org',
              language: 'de',
            }),
          }),
        )
      })
      expect(
        await screen.findByTestId('verify-email-resend-message'),
      ).toHaveTextContent('emailVerification.resent')
    })

    it('offers the resend on an invalid or expired link too', async () => {
      const user = userEvent.setup()
      mockSearchParams.set('token', 'expired-token')
      ;(global.fetch as jest.Mock)
        .mockResolvedValueOnce({
          ok: false,
          json: async () => ({ detail: 'Token expired' }),
        })
        .mockResolvedValueOnce({ ok: true, json: async () => ({}) })

      render(<VerifyEmailPage />)

      await waitFor(() => {
        expect(
          screen.getByText('emailVerification.invalid'),
        ).toBeInTheDocument()
      })
      const button = screen.getByTestId('verify-email-resend-button')
      expect(button).toBeDisabled()

      await user.type(
        screen.getByTestId('verify-email-resend-input'),
        'typed@example.org',
      )
      await user.click(button)

      await waitFor(() => {
        expect(global.fetch).toHaveBeenLastCalledWith(
          '/api/auth/resend-verification',
          expect.objectContaining({
            body: JSON.stringify({
              email: 'typed@example.org',
              language: 'de',
            }),
          }),
        )
      })
    })

    it('offers the resend when sent here to request a new link', () => {
      mockSearchParams.set('messageKey', 'requestNewLink')

      render(<VerifyEmailPage />)

      expect(
        screen.getByText('emailVerification.requestNewLink'),
      ).toBeInTheDocument()
      expect(screen.getByTestId('verify-email-resend-form')).toBeInTheDocument()
    })

    it('reports a rate limit instead of claiming success', async () => {
      const user = userEvent.setup()
      mockSearchParams.set('messageKey', 'verifyEmailRequired')
      mockSearchParams.set('email', 'stuck@example.org')
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 429,
        json: async () => ({
          detail: { code: 'rate_limited', retry_after: 600 },
        }),
      })

      render(<VerifyEmailPage />)
      await user.click(await screen.findByTestId('verify-email-resend-button'))

      const message = await screen.findByTestId('verify-email-resend-message')
      expect(message).not.toHaveTextContent('emailVerification.resent')
      expect(message.textContent).not.toBe('')
    })

    it('reports a failed request', async () => {
      const user = userEvent.setup()
      mockSearchParams.set('messageKey', 'verifyEmailRequired')
      mockSearchParams.set('email', 'stuck@example.org')
      ;(global.fetch as jest.Mock).mockRejectedValueOnce(new Error('offline'))
      jest.spyOn(console, 'error').mockImplementation(() => {})

      render(<VerifyEmailPage />)
      await user.click(await screen.findByTestId('verify-email-resend-button'))

      expect(
        await screen.findByTestId('verify-email-resend-message'),
      ).toHaveTextContent('emailVerification.resendFailed')
    })
  })

  describe('Navigation', () => {
    it('should have back to login link', async () => {
      mockSearchParams.set('messageKey', 'registrationSuccess')
      ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)

      render(<VerifyEmailPage />)

      await waitFor(() => {
        // The link contains "← passwordReset.backToLogin" with the arrow character
        const loginLinks = screen.getAllByText(/passwordReset\.backToLogin/)
        expect(loginLinks[0].closest('a')).toHaveAttribute('href', '/login')
      })
    })

    it('should navigate to login on success', async () => {
      jest.useFakeTimers()
      mockSearchParams.set('token', 'valid-token')
      ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ email: 'test@example.com' }),
      })

      render(<VerifyEmailPage />)

      await waitFor(() => {
        expect(
          screen.getByText('emailVerification.verified'),
        ).toBeInTheDocument()
      })

      jest.advanceTimersByTime(3000)

      await waitFor(() => {
        expect(mockRouterPush).toHaveBeenCalledWith('/login')
      })

      jest.useRealTimers()
    })
  })

  describe('Status States', () => {
    it('should show loading spinner while verifying', () => {
      mockSearchParams.set('token', 'test-token')
      ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)
      ;(global.fetch as jest.Mock).mockImplementation(
        () => new Promise(() => {}), // Never resolves
      )

      render(<VerifyEmailPage />)

      expect(
        screen.getByText('emailVerification.verifying'),
      ).toBeInTheDocument()
      expect(
        screen.getByText('emailVerification.checkInboxDescription'),
      ).toBeInTheDocument()
    })

    it('should show success icon on successful verification', async () => {
      mockSearchParams.set('token', 'valid-token')
      ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ email: 'test@example.com' }),
      })

      render(<VerifyEmailPage />)

      await waitFor(() => {
        const successIcon = screen.getByText('emailVerification.verified')
        expect(successIcon).toBeInTheDocument()
      })
    })

    it('should show error icon on verification failure', async () => {
      mockSearchParams.set('token', 'invalid-token')
      ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        json: async () => ({ detail: 'Invalid token' }),
      })

      render(<VerifyEmailPage />)

      await waitFor(() => {
        expect(
          screen.getByText('emailVerification.invalid'),
        ).toBeInTheDocument()
      })
    })

    it('should show info icon for messageKey state', () => {
      mockSearchParams.set('messageKey', 'registrationSuccess')
      ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)

      render(<VerifyEmailPage />)

      waitFor(() => {
        expect(
          screen.getByText('emailVerification.checkInbox'),
        ).toBeInTheDocument()
      })
    })
  })

  describe('i18n Integration', () => {
    it('should call translation function for all text', () => {
      mockSearchParams.set('token', 'test-token')
      ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)
      ;(global.fetch as jest.Mock).mockImplementation(
        () => new Promise(() => {}),
      )

      render(<VerifyEmailPage />)

      expect(mockT).toHaveBeenCalledWith('emailVerification.verifying')
      expect(mockT).toHaveBeenCalledWith(
        'emailVerification.checkInboxDescription',
      )
    })
  })

  describe('Accessibility', () => {
    it('should have proper navigation aria-label', () => {
      render(<VerifyEmailPage />)

      const nav = screen.getByRole('navigation')
      expect(nav).toHaveAttribute('aria-label', 'layout.minimal.globalNav')
    })

    it('should have descriptive loading message', () => {
      mockSearchParams.set('token', 'test-token')
      ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)
      ;(global.fetch as jest.Mock).mockImplementation(
        () => new Promise(() => {}),
      )

      render(<VerifyEmailPage />)

      expect(
        screen.getByText('emailVerification.checkInboxDescription'),
      ).toBeInTheDocument()
    })
  })

  describe('Error Fallback Handling', () => {
    it('should use fallback message when detail missing', async () => {
      mockSearchParams.set('token', 'invalid-token')
      ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        json: async () => ({}),
      })

      render(<VerifyEmailPage />)

      await waitFor(() => {
        expect(
          screen.getByText('emailVerification.invalidDescription'),
        ).toBeInTheDocument()
      })
    })

    it('should handle console errors gracefully', async () => {
      const consoleErrorSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})

      mockSearchParams.set('token', 'test-token')
      ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)
      ;(global.fetch as jest.Mock).mockRejectedValueOnce(
        new Error('Network error'),
      )

      render(<VerifyEmailPage />)

      await waitFor(() => {
        expect(
          screen.getByText('emailVerification.invalid'),
        ).toBeInTheDocument()
      })

      expect(consoleErrorSpy).toHaveBeenCalledWith(
        'Error verifying email:',
        expect.any(Error),
      )

      consoleErrorSpy.mockRestore()
    })
  })

  describe('Redirect Message Display', () => {
    it('should show redirecting message on success', async () => {
      mockSearchParams.set('token', 'valid-token')
      ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ email: 'test@example.com' }),
      })

      render(<VerifyEmailPage />)

      await waitFor(() => {
        expect(screen.getByText('login.redirecting')).toBeInTheDocument()
      })
    })
  })
})
