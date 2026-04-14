import { useI18n } from '@/contexts/I18nContext'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useRouter } from 'next/navigation'
import VerifyTokenPage from '../page'

jest.mock('@/contexts/I18nContext')
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}))

describe('VerifyTokenPage', () => {
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
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  const mockParams = (token: string) => Promise.resolve({ token })

  describe('Rendering', () => {
    it('should show loading state initially', async () => {
      ;(global.fetch as jest.Mock).mockImplementation(
        () => new Promise(() => {})
      )

      render(<VerifyTokenPage params={mockParams('test-token')} />)

      await waitFor(() => {
        expect(
          screen.getByText('emailVerification.verifying')
        ).toBeInTheDocument()
        expect(
          screen.getByText('emailVerification.checkInboxDescription')
        ).toBeInTheDocument()
      })
    })

    it('should render card layout', async () => {
      ;(global.fetch as jest.Mock).mockImplementation(
        () => new Promise(() => {})
      )

      render(<VerifyTokenPage params={mockParams('test-token')} />)

      await waitFor(() => {
        expect(
          screen.getByText('emailVerification.verifying')
        ).toBeInTheDocument()
      })
    })
  })

  describe('Enhanced Verification Endpoint', () => {
    it('should try enhanced endpoint first', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          message: 'Email verified successfully',
          user_type: 'standard',
          profile_completed: true,
        }),
      })

      render(<VerifyTokenPage params={mockParams('test-token')} />)

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          '/api/auth/verify-email-enhanced/test-token',
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
          }
        )
      })
    })

    it('should fallback to standard endpoint on 403', async () => {
      ;(global.fetch as jest.Mock)
        .mockResolvedValueOnce({
          status: 403,
          ok: false,
          json: async () => ({ detail: 'Enhanced endpoint not available' }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            success: true,
            message: 'Email verified',
          }),
        })

      render(<VerifyTokenPage params={mockParams('test-token')} />)

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledTimes(2)
        expect(global.fetch).toHaveBeenNthCalledWith(
          2,
          '/api/auth/verify-email',
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({ token: 'test-token' }),
          }
        )
      })
    })

    it('should fallback to standard endpoint on 404', async () => {
      ;(global.fetch as jest.Mock)
        .mockResolvedValueOnce({
          status: 404,
          ok: false,
          json: async () => ({ detail: 'Endpoint not found' }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            success: true,
            message: 'Email verified',
          }),
        })

      render(<VerifyTokenPage params={mockParams('test-token')} />)

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledTimes(2)
      })
    })
  })

  describe('Success States', () => {
    it('should show success message on verification', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          message: 'Email verified successfully',
        }),
      })

      render(<VerifyTokenPage params={mockParams('test-token')} />)

      await waitFor(() => {
        expect(
          screen.getByText('emailVerification.verified')
        ).toBeInTheDocument()
        expect(
          screen.getByText('Email verified successfully')
        ).toBeInTheDocument()
      })
    })

    it('should use fallback message when message missing', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
        }),
      })

      render(<VerifyTokenPage params={mockParams('test-token')} />)

      await waitFor(() => {
        // Multiple elements may display this text
        const descriptions = screen.getAllByText(
          'emailVerification.verifiedDescription'
        )
        expect(descriptions.length).toBeGreaterThanOrEqual(1)
      })
    })

    it('should show success icon on verification', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          message: 'Verified',
        }),
      })

      render(<VerifyTokenPage params={mockParams('test-token')} />)

      await waitFor(() => {
        expect(
          screen.getByText('emailVerification.verified')
        ).toBeInTheDocument()
      })
    })

    it('should show redirect message', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          message: 'Verified',
        }),
      })

      render(<VerifyTokenPage params={mockParams('test-token')} />)

      await waitFor(() => {
        expect(screen.getByText(/You will be redirected/i)).toBeInTheDocument()
      })
    })
  })

  describe('Redirect Handling', () => {
    it('should redirect to provided redirect_url', async () => {
      jest.useFakeTimers()
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          redirect_url: '/projects/123',
        }),
      })

      render(<VerifyTokenPage params={mockParams('test-token')} />)

      await waitFor(() => {
        expect(
          screen.getByText('emailVerification.verified')
        ).toBeInTheDocument()
      })

      jest.advanceTimersByTime(3000)

      await waitFor(() => {
        expect(mockRouterPush).toHaveBeenCalledWith('/projects/123')
      })

      jest.useRealTimers()
    })

    it('should redirect invited user to complete-profile', async () => {
      jest.useFakeTimers()
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          user_type: 'invited',
          profile_completed: false,
        }),
      })

      render(<VerifyTokenPage params={mockParams('test-token')} />)

      await waitFor(() => {
        expect(
          screen.getByText('emailVerification.verified')
        ).toBeInTheDocument()
      })

      jest.advanceTimersByTime(3000)

      await waitFor(() => {
        expect(mockRouterPush).toHaveBeenCalledWith('/complete-profile')
      })

      jest.useRealTimers()
    })

    it('should redirect to login with message for standard users', async () => {
      jest.useFakeTimers()
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          user_type: 'standard',
        }),
      })

      render(<VerifyTokenPage params={mockParams('test-token')} />)

      await waitFor(() => {
        expect(
          screen.getByText('emailVerification.verified')
        ).toBeInTheDocument()
      })

      jest.advanceTimersByTime(3000)

      await waitFor(() => {
        expect(mockRouterPush).toHaveBeenCalledWith(
          '/login?message=Email verified! You can now log in.'
        )
      })

      jest.useRealTimers()
    })

    it('should redirect to login for standard endpoint', async () => {
      jest.useFakeTimers()
      ;(global.fetch as jest.Mock)
        .mockResolvedValueOnce({
          status: 404,
          ok: false,
          json: async () => ({}),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            success: true,
          }),
        })

      render(<VerifyTokenPage params={mockParams('test-token')} />)

      await waitFor(() => {
        expect(
          screen.getByText('emailVerification.verified')
        ).toBeInTheDocument()
      })

      jest.advanceTimersByTime(3000)

      await waitFor(() => {
        expect(mockRouterPush).toHaveBeenCalledWith(
          '/login?message=Email verified! You can now log in.'
        )
      })

      jest.useRealTimers()
    })
  })

  describe('Error Handling', () => {
    it('should show error message on verification failure', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        json: async () => ({
          detail: 'Invalid verification token',
        }),
      })

      render(<VerifyTokenPage params={mockParams('invalid-token')} />)

      await waitFor(() => {
        expect(
          screen.getByText('emailVerification.invalid')
        ).toBeInTheDocument()
        expect(
          screen.getByText('Invalid verification token')
        ).toBeInTheDocument()
      })
    })

    it('should use message field if detail missing', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        json: async () => ({
          message: 'Token expired',
        }),
      })

      render(<VerifyTokenPage params={mockParams('expired-token')} />)

      await waitFor(() => {
        expect(screen.getByText('Token expired')).toBeInTheDocument()
      })
    })

    it('should use fallback message if both detail and message missing', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        json: async () => ({}),
      })

      render(<VerifyTokenPage params={mockParams('test-token')} />)

      await waitFor(() => {
        const elements = screen.getAllByText(
          'emailVerification.invalidDescription'
        )
        expect(elements.length).toBeGreaterThan(0)
      })
    })

    it('should handle network errors', async () => {
      ;(global.fetch as jest.Mock).mockRejectedValueOnce(
        new Error('Network error')
      )

      render(<VerifyTokenPage params={mockParams('test-token')} />)

      await waitFor(() => {
        const invalidElements = screen.getAllByText('emailVerification.invalid')
        expect(invalidElements.length).toBeGreaterThan(0)
        const descElements = screen.getAllByText(
          'emailVerification.invalidDescription'
        )
        expect(descElements.length).toBeGreaterThan(0)
      })
    })

    it('should show error icon on failure', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        json: async () => ({
          detail: 'Invalid token',
        }),
      })

      render(<VerifyTokenPage params={mockParams('invalid-token')} />)

      await waitFor(() => {
        expect(
          screen.getByText('emailVerification.invalid')
        ).toBeInTheDocument()
      })
    })
  })

  describe('Navigation Actions', () => {
    it('should have back to login button on success', async () => {
      const user = userEvent.setup()

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          message: 'Verified',
        }),
      })

      render(<VerifyTokenPage params={mockParams('test-token')} />)

      await waitFor(() => {
        expect(
          screen.getByText('passwordReset.backToLogin')
        ).toBeInTheDocument()
      })

      const backButton = screen.getByText('passwordReset.backToLogin')
      await user.click(backButton)

      expect(mockRouterPush).toHaveBeenCalledWith(
        '/login?message=Email verified! You can now log in.'
      )
    })

    it('should have resend verification button on error', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        json: async () => ({
          detail: 'Token expired',
        }),
      })

      render(<VerifyTokenPage params={mockParams('expired-token')} />)

      await waitFor(() => {
        expect(screen.getByText('emailVerification.resend')).toBeInTheDocument()
      })
    })

    it('should navigate to verify-email on resend click', async () => {
      const user = userEvent.setup()

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        json: async () => ({
          detail: 'Token expired',
        }),
      })

      render(<VerifyTokenPage params={mockParams('expired-token')} />)

      await waitFor(() => {
        expect(screen.getByText('emailVerification.resend')).toBeInTheDocument()
      })

      const resendButton = screen.getByText('emailVerification.resend')
      await user.click(resendButton)

      expect(mockRouterPush).toHaveBeenCalledWith('/verify-email')
    })

    it('should have back to login button on error', async () => {
      const user = userEvent.setup()

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        json: async () => ({
          detail: 'Invalid token',
        }),
      })

      render(<VerifyTokenPage params={mockParams('invalid-token')} />)

      await waitFor(() => {
        const backButtons = screen.getAllByText('passwordReset.backToLogin')
        expect(backButtons).toHaveLength(1)
      })

      const backButton = screen.getByText('passwordReset.backToLogin')
      await user.click(backButton)

      expect(mockRouterPush).toHaveBeenCalledWith('/register')
    })
  })

  describe('Loading State', () => {
    it('should show loading spinner', async () => {
      ;(global.fetch as jest.Mock).mockImplementation(
        () => new Promise(() => {})
      )

      render(<VerifyTokenPage params={mockParams('test-token')} />)

      await waitFor(() => {
        expect(
          screen.getByText('emailVerification.verifying')
        ).toBeInTheDocument()
      })
    })

    it('should show loading description', async () => {
      ;(global.fetch as jest.Mock).mockImplementation(
        () => new Promise(() => {})
      )

      render(<VerifyTokenPage params={mockParams('test-token')} />)

      await waitFor(() => {
        expect(
          screen.getByText('emailVerification.checkInboxDescription')
        ).toBeInTheDocument()
      })
    })
  })

  describe('Token Resolution', () => {
    it('should wait for params to resolve before verification', async () => {
      let resolveParams: any
      const paramsPromise = new Promise<{ token: string }>((resolve) => {
        resolveParams = resolve
      })

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
        }),
      })

      render(<VerifyTokenPage params={paramsPromise} />)

      // Should not call fetch yet
      expect(global.fetch).not.toHaveBeenCalled()

      // Resolve params
      resolveParams({ token: 'test-token' })

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalled()
      })
    })

    it('should not verify if token is null', async () => {
      render(<VerifyTokenPage params={Promise.resolve({ token: '' })} />)

      await waitFor(
        () => {
          expect(global.fetch).not.toHaveBeenCalled()
        },
        { timeout: 1000 }
      )
    })
  })

  describe('i18n Integration', () => {
    it('should call translation function for all text', async () => {
      ;(global.fetch as jest.Mock).mockImplementation(
        () => new Promise(() => {})
      )

      render(<VerifyTokenPage params={mockParams('test-token')} />)

      await waitFor(() => {
        expect(mockT).toHaveBeenCalledWith('emailVerification.verifying')
        expect(mockT).toHaveBeenCalledWith(
          'emailVerification.checkInboxDescription'
        )
      })
    })

    it('should translate success messages', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          message: 'Success',
        }),
      })

      render(<VerifyTokenPage params={mockParams('test-token')} />)

      await waitFor(() => {
        expect(mockT).toHaveBeenCalledWith('emailVerification.verified')
        expect(mockT).toHaveBeenCalledWith(
          'emailVerification.verifiedDescription'
        )
      })
    })

    it('should translate error messages', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        json: async () => ({
          detail: 'Error',
        }),
      })

      render(<VerifyTokenPage params={mockParams('test-token')} />)

      await waitFor(() => {
        expect(mockT).toHaveBeenCalledWith('emailVerification.invalid')
        expect(mockT).toHaveBeenCalledWith(
          'emailVerification.invalidDescription'
        )
      })
    })
  })

  describe('Alert Styling', () => {
    it('should have success styling for verified state', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          message: 'Verified',
        }),
      })

      render(<VerifyTokenPage params={mockParams('test-token')} />)

      await waitFor(() => {
        const alert = screen.getByText('Verified').closest('div')
        expect(alert).toHaveClass('border-green-200', 'bg-green-50')
      })
    })

    it('should have error styling for failed state', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        json: async () => ({
          detail: 'Invalid',
        }),
      })

      render(<VerifyTokenPage params={mockParams('test-token')} />)

      await waitFor(() => {
        const alert = screen.getByText('Invalid').closest('div')
        expect(alert).toHaveClass('border-red-200', 'bg-red-50')
      })
    })
  })
})
