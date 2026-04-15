import { useI18n } from '@/contexts/I18nContext'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useParams, useRouter } from 'next/navigation'
import ResetPasswordConfirmPage from '../page'

jest.mock('@/contexts/I18nContext')
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
  useParams: jest.fn(),
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

describe('ResetPasswordConfirmPage', () => {
  const mockRouterPush = jest.fn()
  const mockT = jest.fn((key: string) => key)

  beforeEach(() => {
    jest.clearAllMocks()
    global.fetch = jest.fn()
    ;(useI18n as jest.Mock).mockReturnValue({
      t: mockT,
      currentLanguage: 'en',
    })
    ;(useRouter as jest.Mock).mockReturnValue({
      push: mockRouterPush,
      replace: jest.fn(),
    })
    ;(useParams as jest.Mock).mockReturnValue({
      token: 'test-token',
    })
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  describe('Rendering', () => {
    it('should render reset password form', () => {
      render(<ResetPasswordConfirmPage />)

      expect(screen.getByText('passwordReset.title')).toBeInTheDocument()
      expect(
        screen.getByLabelText('passwordReset.newPassword')
      ).toBeInTheDocument()
      expect(
        screen.getByLabelText('passwordReset.confirmPassword')
      ).toBeInTheDocument()
    })

    it('should render navigation elements', () => {
      render(<ResetPasswordConfirmPage />)

      expect(screen.getAllByText('BenGER').length).toBeGreaterThan(0)
      expect(screen.getByTestId('language-switcher')).toBeInTheDocument()
      expect(screen.getByTestId('theme-toggle')).toBeInTheDocument()
    })

    it('should render back to login link', () => {
      render(<ResetPasswordConfirmPage />)

      const backLinks = screen.getAllByText('passwordReset.backToLogin')
      expect(backLinks[0].closest('a')).toHaveAttribute('href', '/login')
    })

    it('should have description text', () => {
      render(<ResetPasswordConfirmPage />)

      expect(screen.getByText('passwordReset.description')).toBeInTheDocument()
    })
  })

  describe('Form Validation', () => {
    it('should have required password fields', () => {
      render(<ResetPasswordConfirmPage />)

      const newPasswordInput = screen.getByLabelText(
        'passwordReset.newPassword'
      )
      const confirmPasswordInput = screen.getByLabelText(
        'passwordReset.confirmPassword'
      )

      expect(newPasswordInput).toHaveAttribute('required')
      expect(confirmPasswordInput).toHaveAttribute('required')
    })

    it('should have password type for both fields', () => {
      render(<ResetPasswordConfirmPage />)

      const newPasswordInput = screen.getByLabelText(
        'passwordReset.newPassword'
      )
      const confirmPasswordInput = screen.getByLabelText(
        'passwordReset.confirmPassword'
      )

      expect(newPasswordInput).toHaveAttribute('type', 'password')
      expect(confirmPasswordInput).toHaveAttribute('type', 'password')
    })

    it('should allow typing in password fields', async () => {
      const user = userEvent.setup()
      render(<ResetPasswordConfirmPage />)

      const newPasswordInput = screen.getByLabelText(
        'passwordReset.newPassword'
      ) as HTMLInputElement
      const confirmPasswordInput = screen.getByLabelText(
        'passwordReset.confirmPassword'
      ) as HTMLInputElement

      await user.type(newPasswordInput, 'newpassword123')
      await user.type(confirmPasswordInput, 'newpassword123')

      expect(newPasswordInput.value).toBe('newpassword123')
      expect(confirmPasswordInput.value).toBe('newpassword123')
    })

    it('should validate password mismatch', async () => {
      const user = userEvent.setup()
      render(<ResetPasswordConfirmPage />)

      await user.type(
        screen.getByLabelText('passwordReset.newPassword'),
        'password123'
      )
      await user.type(
        screen.getByLabelText('passwordReset.confirmPassword'),
        'different123'
      )

      const submitButton = screen.getByText('passwordReset.reset')
      await user.click(submitButton)

      await waitFor(() => {
        expect(screen.getByText('passwordReset.mismatch')).toBeInTheDocument()
      })

      expect(global.fetch).not.toHaveBeenCalled()
    })

    it('should validate password length', async () => {
      const user = userEvent.setup()
      render(<ResetPasswordConfirmPage />)

      await user.type(
        screen.getByLabelText('passwordReset.newPassword'),
        '12345'
      )
      await user.type(
        screen.getByLabelText('passwordReset.confirmPassword'),
        '12345'
      )

      const submitButton = screen.getByText('passwordReset.reset')
      await user.click(submitButton)

      await waitFor(() => {
        expect(screen.getByText('passwordReset.tooShort')).toBeInTheDocument()
      })

      expect(global.fetch).not.toHaveBeenCalled()
    })
  })

  describe('Form Submission', () => {
    it('should call API with correct data', async () => {
      const user = userEvent.setup()
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ message: 'Password reset successfully' }),
      })

      render(<ResetPasswordConfirmPage />)

      await user.type(
        screen.getByLabelText('passwordReset.newPassword'),
        'newpassword123'
      )
      await user.type(
        screen.getByLabelText('passwordReset.confirmPassword'),
        'newpassword123'
      )

      const submitButton = screen.getByText('passwordReset.reset')
      await user.click(submitButton)

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith('/api/auth/reset-password', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            token: 'test-token',
            new_password: 'newpassword123',
            confirm_password: 'newpassword123',
          }),
        })
      })
    })

    it('should display loading state during submission', async () => {
      const user = userEvent.setup()
      let resolveFetch: any
      ;(global.fetch as jest.Mock).mockReturnValue(
        new Promise((resolve) => {
          resolveFetch = resolve
        })
      )

      render(<ResetPasswordConfirmPage />)

      await user.type(
        screen.getByLabelText('passwordReset.newPassword'),
        'newpassword123'
      )
      await user.type(
        screen.getByLabelText('passwordReset.confirmPassword'),
        'newpassword123'
      )

      const submitButton = screen.getByText('passwordReset.reset')
      await user.click(submitButton)

      await waitFor(() => {
        expect(submitButton).toBeDisabled()
        expect(screen.getByText('passwordReset.resetting')).toBeInTheDocument()
      })

      resolveFetch({
        ok: true,
        json: async () => ({}),
      })
    })

    it('should prevent multiple submissions', async () => {
      const user = userEvent.setup()
      ;(global.fetch as jest.Mock).mockReturnValue(new Promise(() => {}))

      render(<ResetPasswordConfirmPage />)

      await user.type(
        screen.getByLabelText('passwordReset.newPassword'),
        'newpassword123'
      )
      await user.type(
        screen.getByLabelText('passwordReset.confirmPassword'),
        'newpassword123'
      )

      const submitButton = screen.getByText('passwordReset.reset')
      await user.click(submitButton)
      await user.click(submitButton)
      await user.click(submitButton)

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledTimes(1)
      })
    })
  })

  describe('Success State', () => {
    it('should show success message on successful reset', async () => {
      const user = userEvent.setup()
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ message: 'Password reset successfully' }),
      })

      render(<ResetPasswordConfirmPage />)

      await user.type(
        screen.getByLabelText('passwordReset.newPassword'),
        'newpassword123'
      )
      await user.type(
        screen.getByLabelText('passwordReset.confirmPassword'),
        'newpassword123'
      )
      await user.click(screen.getByText('passwordReset.reset'))

      await waitFor(() => {
        expect(screen.getByText('passwordReset.success')).toBeInTheDocument()
        expect(
          screen.getByText('passwordReset.successDescription')
        ).toBeInTheDocument()
      })
    })

    it('should hide form after successful reset', async () => {
      const user = userEvent.setup()
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ message: 'Success' }),
      })

      render(<ResetPasswordConfirmPage />)

      await user.type(
        screen.getByLabelText('passwordReset.newPassword'),
        'newpassword123'
      )
      await user.type(
        screen.getByLabelText('passwordReset.confirmPassword'),
        'newpassword123'
      )
      await user.click(screen.getByText('passwordReset.reset'))

      await waitFor(() => {
        expect(
          screen.queryByLabelText('passwordReset.newPassword')
        ).not.toBeInTheDocument()
        expect(screen.getByText('passwordReset.success')).toBeInTheDocument()
      })
    })

    it('should show success icon', async () => {
      const user = userEvent.setup()
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ message: 'Success' }),
      })

      render(<ResetPasswordConfirmPage />)

      await user.type(
        screen.getByLabelText('passwordReset.newPassword'),
        'newpassword123'
      )
      await user.type(
        screen.getByLabelText('passwordReset.confirmPassword'),
        'newpassword123'
      )
      await user.click(screen.getByText('passwordReset.reset'))

      await waitFor(() => {
        expect(screen.getByText('passwordReset.success')).toBeInTheDocument()
      })
    })

    it('should redirect to login after 3 seconds', async () => {
      jest.useFakeTimers()
      const user = userEvent.setup({ delay: null })

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ message: 'Success' }),
      })

      render(<ResetPasswordConfirmPage />)

      await user.type(
        screen.getByLabelText('passwordReset.newPassword'),
        'newpassword123'
      )
      await user.type(
        screen.getByLabelText('passwordReset.confirmPassword'),
        'newpassword123'
      )
      await user.click(screen.getByText('passwordReset.reset'))

      await waitFor(() => {
        expect(screen.getByText('passwordReset.success')).toBeInTheDocument()
      })

      jest.advanceTimersByTime(3000)

      await waitFor(() => {
        expect(mockRouterPush).toHaveBeenCalledWith('/login')
      })

      jest.useRealTimers()
    })
  })

  describe('Error Handling', () => {
    it('should display error message on API failure', async () => {
      const user = userEvent.setup()
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        json: async () => ({ detail: 'Invalid or expired token' }),
      })

      render(<ResetPasswordConfirmPage />)

      await user.type(
        screen.getByLabelText('passwordReset.newPassword'),
        'newpassword123'
      )
      await user.type(
        screen.getByLabelText('passwordReset.confirmPassword'),
        'newpassword123'
      )
      await user.click(screen.getByText('passwordReset.reset'))

      await waitFor(() => {
        expect(screen.getByText('Invalid or expired token')).toBeInTheDocument()
      })
    })

    it('should use fallback error message when detail missing', async () => {
      const user = userEvent.setup()
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        json: async () => ({}),
      })

      render(<ResetPasswordConfirmPage />)

      await user.type(
        screen.getByLabelText('passwordReset.newPassword'),
        'newpassword123'
      )
      await user.type(
        screen.getByLabelText('passwordReset.confirmPassword'),
        'newpassword123'
      )
      await user.click(screen.getByText('passwordReset.reset'))

      await waitFor(() => {
        expect(
          screen.getByText('passwordReset.expiredDescription')
        ).toBeInTheDocument()
      })
    })

    it('should handle network errors', async () => {
      const user = userEvent.setup()
      const consoleErrorSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})
      ;(global.fetch as jest.Mock).mockRejectedValueOnce(
        new Error('Network error')
      )

      render(<ResetPasswordConfirmPage />)

      await user.type(
        screen.getByLabelText('passwordReset.newPassword'),
        'newpassword123'
      )
      await user.type(
        screen.getByLabelText('passwordReset.confirmPassword'),
        'newpassword123'
      )
      await user.click(screen.getByText('passwordReset.reset'))

      await waitFor(() => {
        expect(
          screen.getByText('passwordReset.invalidDescription')
        ).toBeInTheDocument()
      })

      expect(consoleErrorSpy).toHaveBeenCalledWith(
        'Error resetting password:',
        expect.any(Error)
      )
      consoleErrorSpy.mockRestore()
    })

    it('should re-enable submit button after error', async () => {
      const user = userEvent.setup()
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        json: async () => ({ detail: 'Error' }),
      })

      render(<ResetPasswordConfirmPage />)

      await user.type(
        screen.getByLabelText('passwordReset.newPassword'),
        'newpassword123'
      )
      await user.type(
        screen.getByLabelText('passwordReset.confirmPassword'),
        'newpassword123'
      )
      await user.click(screen.getByText('passwordReset.reset'))

      await waitFor(() => {
        expect(screen.getByText('Error')).toBeInTheDocument()
        expect(screen.getByText('passwordReset.reset')).not.toBeDisabled()
      })
    })

    it('should clear error when starting new submission', async () => {
      const user = userEvent.setup()
      ;(global.fetch as jest.Mock)
        .mockResolvedValueOnce({
          ok: false,
          json: async () => ({ detail: 'First error' }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({}),
        })

      render(<ResetPasswordConfirmPage />)

      // First submission with error
      await user.type(
        screen.getByLabelText('passwordReset.newPassword'),
        'password123'
      )
      await user.type(
        screen.getByLabelText('passwordReset.confirmPassword'),
        'password123'
      )
      await user.click(screen.getByText('passwordReset.reset'))

      await waitFor(() => {
        expect(screen.getByText('First error')).toBeInTheDocument()
      })

      // Clear and retry
      const newPasswordInput = screen.getByLabelText(
        'passwordReset.newPassword'
      ) as HTMLInputElement
      const confirmPasswordInput = screen.getByLabelText(
        'passwordReset.confirmPassword'
      ) as HTMLInputElement

      await user.clear(newPasswordInput)
      await user.clear(confirmPasswordInput)
      await user.type(newPasswordInput, 'newpassword123')
      await user.type(confirmPasswordInput, 'newpassword123')
      await user.click(screen.getByText('passwordReset.reset'))

      await waitFor(() => {
        expect(screen.queryByText('First error')).not.toBeInTheDocument()
      })
    })
  })

  describe('Token Handling', () => {
    it('should use token from URL params', async () => {
      const user = userEvent.setup()
      ;(useParams as jest.Mock).mockReturnValue({
        token: 'custom-token-123',
      })
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({}),
      })

      render(<ResetPasswordConfirmPage />)

      await user.type(
        screen.getByLabelText('passwordReset.newPassword'),
        'newpassword123'
      )
      await user.type(
        screen.getByLabelText('passwordReset.confirmPassword'),
        'newpassword123'
      )
      await user.click(screen.getByText('passwordReset.reset'))

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          '/api/auth/reset-password',
          expect.objectContaining({
            body: expect.stringContaining('custom-token-123'),
          })
        )
      })
    })
  })

  describe('Navigation', () => {
    it('should have back to login link in header', () => {
      render(<ResetPasswordConfirmPage />)

      const backLinks = screen.getAllByText('passwordReset.backToLogin')
      const headerLink = backLinks[0]

      expect(headerLink.closest('a')).toHaveAttribute('href', '/login')
    })

    it('should have back to login link in form', () => {
      render(<ResetPasswordConfirmPage />)

      const backLinks = screen.getAllByText('passwordReset.backToLogin')
      const formLink = backLinks[1]

      expect(formLink.closest('a')).toHaveAttribute('href', '/login')
    })

    it('should have back to login link in success state', async () => {
      const user = userEvent.setup()
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({}),
      })

      render(<ResetPasswordConfirmPage />)

      await user.type(
        screen.getByLabelText('passwordReset.newPassword'),
        'newpassword123'
      )
      await user.type(
        screen.getByLabelText('passwordReset.confirmPassword'),
        'newpassword123'
      )
      await user.click(screen.getByText('passwordReset.reset'))

      await waitFor(() => {
        const backLinks = screen.getAllByText('passwordReset.backToLogin')
        expect(backLinks).toHaveLength(1) // One in success message
      })
    })
  })

  describe('Accessibility', () => {
    it('should have proper form labels', () => {
      render(<ResetPasswordConfirmPage />)

      expect(
        screen.getByLabelText('passwordReset.newPassword')
      ).toBeInTheDocument()
      expect(
        screen.getByLabelText('passwordReset.confirmPassword')
      ).toBeInTheDocument()
    })

    it('should have proper autocomplete attributes', () => {
      render(<ResetPasswordConfirmPage />)

      const newPasswordInput = screen.getByLabelText(
        'passwordReset.newPassword'
      )
      const confirmPasswordInput = screen.getByLabelText(
        'passwordReset.confirmPassword'
      )

      expect(newPasswordInput).toHaveAttribute('autocomplete', 'new-password')
      expect(confirmPasswordInput).toHaveAttribute(
        'autocomplete',
        'new-password'
      )
    })

    it('should have proper navigation aria-label', () => {
      render(<ResetPasswordConfirmPage />)

      const nav = screen.getByRole('navigation')
      expect(nav).toHaveAttribute('aria-label', 'Global')
    })

    it('should have proper form id attributes', () => {
      render(<ResetPasswordConfirmPage />)

      expect(
        screen.getByLabelText('passwordReset.newPassword')
      ).toHaveAttribute('id', 'new-password')
      expect(
        screen.getByLabelText('passwordReset.confirmPassword')
      ).toHaveAttribute('id', 'confirm-password')
    })
  })

  describe('i18n Integration', () => {
    it('should call translation function for all text', () => {
      render(<ResetPasswordConfirmPage />)

      expect(mockT).toHaveBeenCalledWith('passwordReset.title')
      expect(mockT).toHaveBeenCalledWith('passwordReset.description')
      expect(mockT).toHaveBeenCalledWith('passwordReset.newPassword')
      expect(mockT).toHaveBeenCalledWith('passwordReset.confirmPassword')
      expect(mockT).toHaveBeenCalledWith('passwordReset.reset')
      expect(mockT).toHaveBeenCalledWith('passwordReset.backToLogin')
    })

    it('should translate error messages', async () => {
      const user = userEvent.setup()
      render(<ResetPasswordConfirmPage />)

      await user.type(
        screen.getByLabelText('passwordReset.newPassword'),
        'password123'
      )
      await user.type(
        screen.getByLabelText('passwordReset.confirmPassword'),
        'different'
      )
      await user.click(screen.getByText('passwordReset.reset'))

      await waitFor(() => {
        expect(mockT).toHaveBeenCalledWith('passwordReset.mismatch')
      })
    })

    it('should translate success messages', async () => {
      const user = userEvent.setup()
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({}),
      })

      render(<ResetPasswordConfirmPage />)

      await user.type(
        screen.getByLabelText('passwordReset.newPassword'),
        'newpassword123'
      )
      await user.type(
        screen.getByLabelText('passwordReset.confirmPassword'),
        'newpassword123'
      )
      await user.click(screen.getByText('passwordReset.reset'))

      await waitFor(() => {
        expect(mockT).toHaveBeenCalledWith('passwordReset.success')
        expect(mockT).toHaveBeenCalledWith('passwordReset.successDescription')
      })
    })
  })

  describe('Form States', () => {
    it('should show form initially', () => {
      render(<ResetPasswordConfirmPage />)

      expect(
        screen.getByLabelText('passwordReset.newPassword')
      ).toBeInTheDocument()
      expect(screen.getByText('passwordReset.reset')).toBeInTheDocument()
    })

    it('should not show success state initially', () => {
      render(<ResetPasswordConfirmPage />)

      expect(
        screen.queryByText('passwordReset.success')
      ).not.toBeInTheDocument()
    })
  })
})
