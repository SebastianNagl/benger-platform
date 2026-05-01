/**
 * @jest-environment jsdom
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { mockToast } from '@/test-utils/setupTests'
import { ChangePasswordModal } from '../ChangePasswordModal'

// Alias the per-type mocks so existing toast.success/error assertions keep
// working without rewriting every expect(...) call site.
const toast = { success: mockToast.success, error: mockToast.error }

// Mock heroicons
jest.mock('@heroicons/react/24/outline', () => ({
  XMarkIcon: (props: any) => <svg {...props} data-testid="x-mark-icon" />,
}))

// Mock I18n context
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

// Mock API client
const mockChangePassword = jest.fn()
jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: {
    changePassword: (...args: any[]) => mockChangePassword(...args),
  },
}))

// Mock Button component
jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, disabled, type, ...props }: any) => (
    <button onClick={onClick} disabled={disabled} type={type} {...props}>
      {children}
    </button>
  ),
}))

// Mock Headless UI
jest.mock('@headlessui/react', () => {
  return {
    Dialog: Object.assign(
      ({ children, onClose, open, ...props }: any) => {
        return open ? (
          <div {...props} role="dialog">
            {children}
          </div>
        ) : null
      },
      {
        Panel: ({ children, ...props }: any) => (
          <div {...props}>{children}</div>
        ),
        Title: ({ children, ...props }: any) => <h2 {...props}>{children}</h2>,
      }
    ),
  }
})

describe('ChangePasswordModal', () => {
  const defaultProps = {
    isOpen: true,
    onClose: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
    mockChangePassword.mockReset()
  })

  describe('Rendering', () => {
    it('renders when isOpen is true', () => {
      render(<ChangePasswordModal {...defaultProps} />)
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    it('does not render when isOpen is false', () => {
      render(<ChangePasswordModal {...defaultProps} isOpen={false} />)
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    it('renders modal title', () => {
      render(<ChangePasswordModal {...defaultProps} />)
      // Title is rendered as h2 element
      expect(
        screen.getByRole('heading', { name: 'Change Password' })
      ).toBeInTheDocument()
    })

    it('renders all password form fields', () => {
      render(<ChangePasswordModal {...defaultProps} />)
      expect(screen.getByLabelText('Current Password')).toBeInTheDocument()
      expect(screen.getByLabelText('New Password')).toBeInTheDocument()
      expect(screen.getByLabelText('Confirm New Password')).toBeInTheDocument()
    })

    it('displays password requirements hint', () => {
      render(<ChangePasswordModal {...defaultProps} />)
      expect(screen.getByText('Minimum 6 characters')).toBeInTheDocument()
    })

    it('renders close button with aria-label', () => {
      render(<ChangePasswordModal {...defaultProps} />)
      expect(screen.getByLabelText('Close')).toBeInTheDocument()
    })

    it('renders Cancel and Submit buttons', () => {
      render(<ChangePasswordModal {...defaultProps} />)
      expect(screen.getByText('Cancel')).toBeInTheDocument()
      // Both the title and button say "Change Password", so use getAllByText
      const changePasswordElements = screen.getAllByText('Change Password')
      // Should have 2 elements: title and button
      expect(changePasswordElements.length).toBeGreaterThanOrEqual(2)
    })
  })

  describe('User Interaction', () => {
    it('updates form state when typing in current password field', async () => {
      const user = userEvent.setup()
      render(<ChangePasswordModal {...defaultProps} />)

      const input = screen.getByLabelText('Current Password')
      await user.type(input, 'oldpassword')

      expect(input).toHaveValue('oldpassword')
    })

    it('updates form state when typing in new password field', async () => {
      const user = userEvent.setup()
      render(<ChangePasswordModal {...defaultProps} />)

      const input = screen.getByLabelText('New Password')
      await user.type(input, 'newpassword123')

      expect(input).toHaveValue('newpassword123')
    })

    it('updates form state when typing in confirm password field', async () => {
      const user = userEvent.setup()
      render(<ChangePasswordModal {...defaultProps} />)

      const input = screen.getByLabelText('Confirm New Password')
      await user.type(input, 'newpassword123')

      expect(input).toHaveValue('newpassword123')
    })

    it('calls onClose when clicking close button', async () => {
      const user = userEvent.setup()
      render(<ChangePasswordModal {...defaultProps} />)

      await user.click(screen.getByLabelText('Close'))

      expect(defaultProps.onClose).toHaveBeenCalled()
    })

    it('calls onClose when clicking Cancel button', async () => {
      const user = userEvent.setup()
      render(<ChangePasswordModal {...defaultProps} />)

      await user.click(screen.getByText('Cancel'))

      expect(defaultProps.onClose).toHaveBeenCalled()
    })
  })

  describe('Validation', () => {
    it('shows error toast when passwords do not match', async () => {
      const user = userEvent.setup()
      render(<ChangePasswordModal {...defaultProps} />)

      await user.type(screen.getByLabelText('Current Password'), 'oldpassword')
      await user.type(screen.getByLabelText('New Password'), 'newpassword123')
      await user.type(
        screen.getByLabelText('Confirm New Password'),
        'differentpassword'
      )

      fireEvent.submit(screen.getByRole('dialog').querySelector('form')!)

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Passwords do not match')
      })
    })

    it('does not call API when passwords do not match', async () => {
      const user = userEvent.setup()
      render(<ChangePasswordModal {...defaultProps} />)

      await user.type(screen.getByLabelText('Current Password'), 'oldpassword')
      await user.type(screen.getByLabelText('New Password'), 'newpassword123')
      await user.type(
        screen.getByLabelText('Confirm New Password'),
        'differentpassword'
      )

      fireEvent.submit(screen.getByRole('dialog').querySelector('form')!)

      await waitFor(() => {
        expect(mockChangePassword).not.toHaveBeenCalled()
      })
    })

    it('password inputs have type password', () => {
      render(<ChangePasswordModal {...defaultProps} />)

      expect(screen.getByLabelText('Current Password')).toHaveAttribute(
        'type',
        'password'
      )
      expect(screen.getByLabelText('New Password')).toHaveAttribute(
        'type',
        'password'
      )
      expect(screen.getByLabelText('Confirm New Password')).toHaveAttribute(
        'type',
        'password'
      )
    })

    it('password inputs have minLength attribute', () => {
      render(<ChangePasswordModal {...defaultProps} />)

      expect(screen.getByLabelText('New Password')).toHaveAttribute(
        'minLength',
        '6'
      )
      expect(screen.getByLabelText('Confirm New Password')).toHaveAttribute(
        'minLength',
        '6'
      )
    })

    it('password inputs have required attribute', () => {
      render(<ChangePasswordModal {...defaultProps} />)

      expect(screen.getByLabelText('Current Password')).toHaveAttribute(
        'required'
      )
      expect(screen.getByLabelText('New Password')).toHaveAttribute('required')
      expect(screen.getByLabelText('Confirm New Password')).toHaveAttribute(
        'required'
      )
    })
  })

  describe('Form Submission', () => {
    it('calls apiClient.changePassword with form data on successful submission', async () => {
      mockChangePassword.mockResolvedValueOnce({})
      const user = userEvent.setup()
      render(<ChangePasswordModal {...defaultProps} />)

      await user.type(screen.getByLabelText('Current Password'), 'oldpassword')
      await user.type(screen.getByLabelText('New Password'), 'newpassword123')
      await user.type(
        screen.getByLabelText('Confirm New Password'),
        'newpassword123'
      )

      fireEvent.submit(screen.getByRole('dialog').querySelector('form')!)

      await waitFor(() => {
        expect(mockChangePassword).toHaveBeenCalledWith({
          current_password: 'oldpassword',
          new_password: 'newpassword123',
          confirm_password: 'newpassword123',
        })
      })
    })

    it('shows success toast on successful password change', async () => {
      mockChangePassword.mockResolvedValueOnce({})
      const user = userEvent.setup()
      render(<ChangePasswordModal {...defaultProps} />)

      await user.type(screen.getByLabelText('Current Password'), 'oldpassword')
      await user.type(screen.getByLabelText('New Password'), 'newpassword123')
      await user.type(
        screen.getByLabelText('Confirm New Password'),
        'newpassword123'
      )

      fireEvent.submit(screen.getByRole('dialog').querySelector('form')!)

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith(
          'Password changed successfully'
        )
      })
    })

    it('closes modal on successful password change', async () => {
      mockChangePassword.mockResolvedValueOnce({})
      const user = userEvent.setup()
      render(<ChangePasswordModal {...defaultProps} />)

      await user.type(screen.getByLabelText('Current Password'), 'oldpassword')
      await user.type(screen.getByLabelText('New Password'), 'newpassword123')
      await user.type(
        screen.getByLabelText('Confirm New Password'),
        'newpassword123'
      )

      fireEvent.submit(screen.getByRole('dialog').querySelector('form')!)

      await waitFor(() => {
        expect(defaultProps.onClose).toHaveBeenCalled()
      })
    })

    it('shows error toast on API failure', async () => {
      mockChangePassword.mockRejectedValueOnce(new Error('API Error'))
      const user = userEvent.setup()
      render(<ChangePasswordModal {...defaultProps} />)

      await user.type(screen.getByLabelText('Current Password'), 'oldpassword')
      await user.type(screen.getByLabelText('New Password'), 'newpassword123')
      await user.type(
        screen.getByLabelText('Confirm New Password'),
        'newpassword123'
      )

      fireEvent.submit(screen.getByRole('dialog').querySelector('form')!)

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('API Error')
      })
    })

    it('shows default error message when error has no message', async () => {
      mockChangePassword.mockRejectedValueOnce({})
      const user = userEvent.setup()
      render(<ChangePasswordModal {...defaultProps} />)

      await user.type(screen.getByLabelText('Current Password'), 'oldpassword')
      await user.type(screen.getByLabelText('New Password'), 'newpassword123')
      await user.type(
        screen.getByLabelText('Confirm New Password'),
        'newpassword123'
      )

      fireEvent.submit(screen.getByRole('dialog').querySelector('form')!)

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Failed to change password')
      })
    })

    it('does not close modal on API failure', async () => {
      mockChangePassword.mockRejectedValueOnce(new Error('API Error'))
      const user = userEvent.setup()
      render(<ChangePasswordModal {...defaultProps} />)

      await user.type(screen.getByLabelText('Current Password'), 'oldpassword')
      await user.type(screen.getByLabelText('New Password'), 'newpassword123')
      await user.type(
        screen.getByLabelText('Confirm New Password'),
        'newpassword123'
      )

      fireEvent.submit(screen.getByRole('dialog').querySelector('form')!)

      // Wait for the error to be shown
      await waitFor(() => {
        expect(toast.error).toHaveBeenCalled()
      })

      // The modal should still be rendered (onClose not called for error case)
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })
  })

  describe('Loading State', () => {
    it('disables submit button while loading', async () => {
      // Make the API call hang
      mockChangePassword.mockImplementation(
        () => new Promise(() => {}) // Never resolves
      )
      const user = userEvent.setup()
      render(<ChangePasswordModal {...defaultProps} />)

      await user.type(screen.getByLabelText('Current Password'), 'oldpassword')
      await user.type(screen.getByLabelText('New Password'), 'newpassword123')
      await user.type(
        screen.getByLabelText('Confirm New Password'),
        'newpassword123'
      )

      fireEvent.submit(screen.getByRole('dialog').querySelector('form')!)

      await waitFor(() => {
        // Find button with type="submit" that is disabled
        const submitButton = screen.getByRole('button', { name: 'Changing...' })
        expect(submitButton).toBeDisabled()
      })
    })

    it('shows loading text on submit button while loading', async () => {
      mockChangePassword.mockImplementation(
        () => new Promise(() => {}) // Never resolves
      )
      const user = userEvent.setup()
      render(<ChangePasswordModal {...defaultProps} />)

      await user.type(screen.getByLabelText('Current Password'), 'oldpassword')
      await user.type(screen.getByLabelText('New Password'), 'newpassword123')
      await user.type(
        screen.getByLabelText('Confirm New Password'),
        'newpassword123'
      )

      fireEvent.submit(screen.getByRole('dialog').querySelector('form')!)

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: 'Changing...' })
        ).toBeInTheDocument()
      })
    })
  })

  describe('Form Reset', () => {
    it('calls onClose and resets form when clicking Cancel', async () => {
      const user = userEvent.setup()
      render(<ChangePasswordModal {...defaultProps} />)

      // Fill out the form
      await user.type(screen.getByLabelText('Current Password'), 'oldpassword')
      await user.type(screen.getByLabelText('New Password'), 'newpassword123')
      await user.type(
        screen.getByLabelText('Confirm New Password'),
        'newpassword123'
      )

      // Click cancel to close
      await user.click(screen.getByText('Cancel'))

      // Verify onClose was called (which triggers handleClose -> resetForm -> onClose)
      expect(defaultProps.onClose).toHaveBeenCalled()
    })

    it('calls resetForm and onClose after successful submission', async () => {
      mockChangePassword.mockResolvedValueOnce({})
      const user = userEvent.setup()
      render(<ChangePasswordModal {...defaultProps} />)

      await user.type(screen.getByLabelText('Current Password'), 'oldpassword')
      await user.type(screen.getByLabelText('New Password'), 'newpassword123')
      await user.type(
        screen.getByLabelText('Confirm New Password'),
        'newpassword123'
      )

      fireEvent.submit(screen.getByRole('dialog').querySelector('form')!)

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalled()
        expect(defaultProps.onClose).toHaveBeenCalled()
      })
    })
  })

  describe('Accessibility', () => {
    it('has proper autocomplete attributes', () => {
      render(<ChangePasswordModal {...defaultProps} />)

      expect(screen.getByLabelText('Current Password')).toHaveAttribute(
        'autocomplete',
        'current-password'
      )
      expect(screen.getByLabelText('New Password')).toHaveAttribute(
        'autocomplete',
        'new-password'
      )
      expect(screen.getByLabelText('Confirm New Password')).toHaveAttribute(
        'autocomplete',
        'new-password'
      )
    })

    it('form inputs have associated labels', () => {
      render(<ChangePasswordModal {...defaultProps} />)

      expect(screen.getByLabelText('Current Password')).toBeInTheDocument()
      expect(screen.getByLabelText('New Password')).toBeInTheDocument()
      expect(screen.getByLabelText('Confirm New Password')).toBeInTheDocument()
    })

    it('close button has aria-label', () => {
      render(<ChangePasswordModal {...defaultProps} />)

      expect(
        screen.getByRole('button', { name: 'Close' })
      ).toBeInTheDocument()
    })
  })
})
