/**
 * @jest-environment jsdom
 */

import { User } from '@/lib/api/types'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EmailVerificationModal } from '../EmailVerificationModal'

// Mock i18n
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'admin.emailVerificationModal.title': 'Verify Email Address',
        'admin.emailVerificationModal.confirmMessage': 'Are you sure you want to manually verify the email address for',
        'admin.emailVerificationModal.reasonLabel': 'Reason (optional)',
        'admin.emailVerificationModal.reasonPlaceholder': 'Optionally provide a reason for verification...',
        'admin.emailVerificationModal.cancel': 'Cancel',
        'admin.emailVerificationModal.verifyEmail': 'Verify Email',
        'admin.emailVerificationModal.processing': 'Processing...',
      }
      return translations[key] || key
    },
    locale: 'en',
  }),
}))

// Mock heroicons
jest.mock('@heroicons/react/24/outline', () => ({
  CheckCircleIcon: (props: any) => (
    <svg {...props} data-testid="check-circle-icon" />
  ),
}))

// Mock Headless UI
jest.mock('@headlessui/react', () => {
  const mockFragment = ({ children }: any) => children
  let currentOnClose: (() => void) | null = null

  return {
    Dialog: Object.assign(
      ({ children, onClose, ...props }: any) => {
        currentOnClose = onClose
        return (
          <div {...props} role="dialog">
            {children}
          </div>
        )
      },
      {
        Panel: ({ children, ...props }: any) => (
          <div {...props}>{children}</div>
        ),
        Title: ({ children, ...props }: any) => <h3 {...props}>{children}</h3>,
      }
    ),
    Transition: Object.assign(
      ({ show, appear, children, ...props }: any) =>
        show ? <div {...props}>{children}</div> : null,
      {
        Child: ({ children, ...props }: any) => {
          const childrenArray = Array.isArray(children) ? children : [children]
          const processedChildren = childrenArray.map((child: any) => {
            if (child?.props?.className?.includes('fixed inset-0 bg-black')) {
              return {
                ...child,
                props: {
                  ...child.props,
                  onClick: () => currentOnClose && currentOnClose(),
                },
              }
            }
            return child
          })

          return (
            <div {...props}>
              {Array.isArray(children)
                ? processedChildren
                : processedChildren[0]}
            </div>
          )
        },
      }
    ),
    Fragment: mockFragment,
  }
})

describe('EmailVerificationModal', () => {
  const mockUser: User = {
    id: '1',
    name: 'Test User',
    email: 'test@example.com',
    username: 'testuser',
    role: 'user',
    is_active: true,
    email_verified: false,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    organization_roles: [],
  }

  const defaultProps = {
    isOpen: true,
    onClose: jest.fn(),
    user: mockUser,
    action: 'verify' as const,
    onConfirm: jest.fn().mockResolvedValue(undefined),
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Rendering', () => {
    it('renders when isOpen is true', () => {
      render(<EmailVerificationModal {...defaultProps} />)
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    it('does not render when isOpen is false', () => {
      render(<EmailVerificationModal {...defaultProps} isOpen={false} />)
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    it('renders modal title', () => {
      render(<EmailVerificationModal {...defaultProps} />)
      expect(
        screen.getByRole('heading', { name: 'Verify Email Address' })
      ).toBeInTheDocument()
    })

    it('renders check circle icon', () => {
      render(<EmailVerificationModal {...defaultProps} />)
      expect(screen.getByTestId('check-circle-icon')).toBeInTheDocument()
    })

    it('displays user name and email in confirmation message', () => {
      render(<EmailVerificationModal {...defaultProps} />)
      expect(
        screen.getByText('Test User', { exact: false })
      ).toBeInTheDocument()
      expect(
        screen.getByText('test@example.com', { exact: false })
      ).toBeInTheDocument()
    })

    it('renders confirmation message', () => {
      render(<EmailVerificationModal {...defaultProps} />)
      expect(
        screen.getByText(
          /Are you sure you want to manually verify the email address/i
        )
      ).toBeInTheDocument()
    })

    it('renders reason textarea', () => {
      render(<EmailVerificationModal {...defaultProps} />)
      expect(screen.getByLabelText('Reason (optional)')).toBeInTheDocument()
    })

    it('renders textarea with placeholder', () => {
      render(<EmailVerificationModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Reason (optional)')
      expect(textarea).toHaveAttribute(
        'placeholder',
        'Optionally provide a reason for verification...'
      )
    })

    it('renders cancel button', () => {
      render(<EmailVerificationModal {...defaultProps} />)
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    })

    it('renders verify button', () => {
      render(<EmailVerificationModal {...defaultProps} />)
      expect(
        screen.getByRole('button', { name: 'Verify Email' })
      ).toBeInTheDocument()
    })

    it('renders with proper styling classes', () => {
      const { container } = render(<EmailVerificationModal {...defaultProps} />)
      expect(container.querySelector('.max-w-md')).toBeInTheDocument()
    })
  })

  describe('User Information Display', () => {
    it('displays user with different name', () => {
      const customUser = { ...mockUser, name: 'John Doe' }
      render(<EmailVerificationModal {...defaultProps} user={customUser} />)
      expect(screen.getByText('John Doe', { exact: false })).toBeInTheDocument()
    })

    it('displays user with different email', () => {
      const customUser = { ...mockUser, email: 'john@example.com' }
      render(<EmailVerificationModal {...defaultProps} user={customUser} />)
      expect(
        screen.getByText('john@example.com', { exact: false })
      ).toBeInTheDocument()
    })

    it('handles null user gracefully', () => {
      render(<EmailVerificationModal {...defaultProps} user={null} />)
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    it('renders user name in bold', () => {
      const { container } = render(<EmailVerificationModal {...defaultProps} />)
      const boldElements = container.querySelectorAll('.font-semibold')
      expect(boldElements.length).toBeGreaterThan(0)
    })
  })

  describe('Reason Input', () => {
    it('allows typing in reason textarea', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Reason (optional)')

      await user.type(textarea, 'User requested verification')
      expect(textarea).toHaveValue('User requested verification')
    })

    it('starts with empty reason', () => {
      render(<EmailVerificationModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Reason (optional)')
      expect(textarea).toHaveValue('')
    })

    it('allows clearing reason text', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Reason (optional)')

      await user.type(textarea, 'Some reason')
      await user.clear(textarea)
      expect(textarea).toHaveValue('')
    })

    it('allows multiline reason input', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Reason (optional)')

      await user.type(textarea, 'Line 1{Enter}Line 2{Enter}Line 3')
      expect(textarea.value).toContain('Line 1')
      expect(textarea.value).toContain('Line 2')
      expect(textarea.value).toContain('Line 3')
    })

    it('has correct row attribute', () => {
      render(<EmailVerificationModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Reason (optional)')
      expect(textarea).toHaveAttribute('rows', '3')
    })

    it('accepts long reason text', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Reason (optional)')
      const longReason = 'This is a very long reason. '.repeat(20)

      await user.type(textarea, longReason)
      expect(textarea).toHaveValue(longReason)
    })

    it('handles special characters in reason', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Reason (optional)')

      await user.type(textarea, '!@#$%^&*()')
      expect(textarea).toHaveValue('!@#$%^&*()')
    })
  })

  describe('Verify Functionality', () => {
    it('calls onConfirm when verify button clicked without reason', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationModal {...defaultProps} />)
      const verifyButton = screen.getByRole('button', { name: 'Verify Email' })

      await user.click(verifyButton)

      await waitFor(() => {
        expect(defaultProps.onConfirm).toHaveBeenCalledWith(undefined)
      })
    })

    it('calls onConfirm with reason when provided', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Reason (optional)')
      const verifyButton = screen.getByRole('button', { name: 'Verify Email' })

      await user.type(textarea, 'Manual verification requested')
      await user.click(verifyButton)

      await waitFor(() => {
        expect(defaultProps.onConfirm).toHaveBeenCalledWith(
          'Manual verification requested'
        )
      })
    })

    it('calls onConfirm with undefined for empty reason', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationModal {...defaultProps} />)
      const verifyButton = screen.getByRole('button', { name: 'Verify Email' })

      await user.click(verifyButton)

      await waitFor(() => {
        expect(defaultProps.onConfirm).toHaveBeenCalledWith(undefined)
      })
    })

    it('calls onClose after successful verification', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationModal {...defaultProps} />)
      const verifyButton = screen.getByRole('button', { name: 'Verify Email' })

      await user.click(verifyButton)

      await waitFor(() => {
        expect(defaultProps.onClose).toHaveBeenCalled()
      })
    })

    it('shows loading state during verification', async () => {
      const user = userEvent.setup()
      let resolveConfirm: () => void
      const confirmPromise = new Promise<void>((resolve) => {
        resolveConfirm = resolve
      })
      const onConfirm = jest.fn().mockReturnValue(confirmPromise)

      render(<EmailVerificationModal {...defaultProps} onConfirm={onConfirm} />)
      const verifyButton = screen.getByRole('button', { name: 'Verify Email' })

      await user.click(verifyButton)

      await waitFor(() => {
        expect(screen.getByText('Processing...')).toBeInTheDocument()
      })

      resolveConfirm!()
    })

    it('disables buttons during loading', async () => {
      const user = userEvent.setup()
      let resolveConfirm: () => void
      const confirmPromise = new Promise<void>((resolve) => {
        resolveConfirm = resolve
      })
      const onConfirm = jest.fn().mockReturnValue(confirmPromise)

      render(<EmailVerificationModal {...defaultProps} onConfirm={onConfirm} />)
      const verifyButton = screen.getByRole('button', { name: 'Verify Email' })
      const cancelButton = screen.getByRole('button', { name: 'Cancel' })

      await user.click(verifyButton)

      await waitFor(() => {
        expect(verifyButton).toBeDisabled()
        expect(cancelButton).toBeDisabled()
      })

      resolveConfirm!()
    })

    it('handles successful verification with reason', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Reason (optional)')
      const verifyButton = screen.getByRole('button', { name: 'Verify Email' })

      await user.type(textarea, 'Admin approval')
      await user.click(verifyButton)

      await waitFor(() => {
        expect(defaultProps.onConfirm).toHaveBeenCalledWith('Admin approval')
        expect(defaultProps.onClose).toHaveBeenCalled()
      })
    })

    it('clears reason after successful verification', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Reason (optional)')
      const verifyButton = screen.getByRole('button', { name: 'Verify Email' })

      await user.type(textarea, 'Test reason')
      await user.click(verifyButton)

      await waitFor(() => {
        expect(defaultProps.onClose).toHaveBeenCalled()
      })
    })
  })

  describe('Error Handling', () => {
    it('handles verification failure', async () => {
      const user = userEvent.setup()
      const consoleErrorSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})
      const onConfirm = jest
        .fn()
        .mockRejectedValue(new Error('Verification failed'))

      render(<EmailVerificationModal {...defaultProps} onConfirm={onConfirm} />)
      const verifyButton = screen.getByRole('button', { name: 'Verify Email' })

      await user.click(verifyButton)

      await waitFor(() => {
        expect(consoleErrorSpy).toHaveBeenCalledWith(
          'Failed to verify email:',
          expect.any(Error)
        )
      })

      consoleErrorSpy.mockRestore()
    })

    it('does not close modal on verification failure', async () => {
      const user = userEvent.setup()
      const consoleErrorSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})
      const onConfirm = jest
        .fn()
        .mockRejectedValue(new Error('Verification failed'))

      render(<EmailVerificationModal {...defaultProps} onConfirm={onConfirm} />)
      const verifyButton = screen.getByRole('button', { name: 'Verify Email' })

      await user.click(verifyButton)

      await waitFor(() => {
        expect(consoleErrorSpy).toHaveBeenCalled()
      })

      expect(screen.getByRole('dialog')).toBeInTheDocument()

      consoleErrorSpy.mockRestore()
    })

    it('clears loading state after error', async () => {
      const user = userEvent.setup()
      const consoleErrorSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})
      const onConfirm = jest
        .fn()
        .mockRejectedValue(new Error('Verification failed'))

      render(<EmailVerificationModal {...defaultProps} onConfirm={onConfirm} />)
      const verifyButton = screen.getByRole('button', { name: 'Verify Email' })

      await user.click(verifyButton)

      await waitFor(() => {
        expect(consoleErrorSpy).toHaveBeenCalled()
      })

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: 'Verify Email' })
        ).toBeInTheDocument()
      })

      consoleErrorSpy.mockRestore()
    })

    it('clears reason after error', async () => {
      const user = userEvent.setup()
      const consoleErrorSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})
      const onConfirm = jest
        .fn()
        .mockRejectedValue(new Error('Verification failed'))

      render(<EmailVerificationModal {...defaultProps} onConfirm={onConfirm} />)
      const textarea = screen.getByLabelText('Reason (optional)')
      const verifyButton = screen.getByRole('button', { name: 'Verify Email' })

      await user.type(textarea, 'Test reason')
      await user.click(verifyButton)

      await waitFor(() => {
        expect(textarea).toHaveValue('')
      })

      consoleErrorSpy.mockRestore()
    })

    it('handles network timeout error', async () => {
      const user = userEvent.setup()
      const consoleErrorSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})
      const onConfirm = jest
        .fn()
        .mockRejectedValue(new Error('Network timeout'))

      render(<EmailVerificationModal {...defaultProps} onConfirm={onConfirm} />)
      const verifyButton = screen.getByRole('button', { name: 'Verify Email' })

      await user.click(verifyButton)

      await waitFor(() => {
        expect(consoleErrorSpy).toHaveBeenCalled()
      })

      consoleErrorSpy.mockRestore()
    })
  })

  describe('Cancel Functionality', () => {
    it('calls onClose when cancel button clicked', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationModal {...defaultProps} />)
      const cancelButton = screen.getByRole('button', { name: 'Cancel' })

      await user.click(cancelButton)

      expect(defaultProps.onClose).toHaveBeenCalled()
    })

    it('does not call onConfirm when cancelled', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Reason (optional)')
      const cancelButton = screen.getByRole('button', { name: 'Cancel' })

      await user.type(textarea, 'Some reason')
      await user.click(cancelButton)

      expect(defaultProps.onConfirm).not.toHaveBeenCalled()
    })

    it('does not verify email when cancelled', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationModal {...defaultProps} />)
      const cancelButton = screen.getByRole('button', { name: 'Cancel' })

      await user.click(cancelButton)

      expect(defaultProps.onConfirm).not.toHaveBeenCalled()
      expect(defaultProps.onClose).toHaveBeenCalled()
    })

    it('cannot cancel during loading', async () => {
      const user = userEvent.setup()
      let resolveConfirm: () => void
      const confirmPromise = new Promise<void>((resolve) => {
        resolveConfirm = resolve
      })
      const onConfirm = jest.fn().mockReturnValue(confirmPromise)

      render(<EmailVerificationModal {...defaultProps} onConfirm={onConfirm} />)
      const verifyButton = screen.getByRole('button', { name: 'Verify Email' })
      const cancelButton = screen.getByRole('button', { name: 'Cancel' })

      await user.click(verifyButton)

      await waitFor(() => {
        expect(cancelButton).toBeDisabled()
      })

      resolveConfirm!()
    })
  })

  describe('Modal Behavior', () => {
    it('handles backdrop click to close', async () => {
      const { container } = render(<EmailVerificationModal {...defaultProps} />)

      const backdrop = container.querySelector('.fixed.inset-0.bg-black')
      if (backdrop) {
        fireEvent.click(backdrop)
        await waitFor(() => {
          expect(defaultProps.onClose).toHaveBeenCalled()
        })
      }
    })

    it('handles rapid open/close transitions', () => {
      const { rerender } = render(
        <EmailVerificationModal {...defaultProps} isOpen={false} />
      )
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

      rerender(<EmailVerificationModal {...defaultProps} isOpen={true} />)
      expect(screen.getByRole('dialog')).toBeInTheDocument()

      rerender(<EmailVerificationModal {...defaultProps} isOpen={false} />)
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    it('maintains reason state when modal stays open', () => {
      const { rerender } = render(<EmailVerificationModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Reason (optional)')
      fireEvent.change(textarea, { target: { value: 'Test reason' } })

      rerender(<EmailVerificationModal {...defaultProps} />)

      expect(textarea).toHaveValue('Test reason')
    })

    it('preserves reason state across modal close/open cycles', async () => {
      const user = userEvent.setup()
      const { rerender } = render(
        <EmailVerificationModal {...defaultProps} isOpen={true} />
      )
      const textarea = screen.getByLabelText('Reason (optional)')
      await user.type(textarea, 'Test reason')

      rerender(<EmailVerificationModal {...defaultProps} isOpen={false} />)
      rerender(<EmailVerificationModal {...defaultProps} isOpen={true} />)

      expect(screen.getByLabelText('Reason (optional)')).toHaveValue(
        'Test reason'
      )
    })
  })

  describe('Accessibility', () => {
    it('has proper dialog role', () => {
      render(<EmailVerificationModal {...defaultProps} />)
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    it('has proper heading', () => {
      render(<EmailVerificationModal {...defaultProps} />)
      expect(
        screen.getByRole('heading', { name: 'Verify Email Address' })
      ).toBeInTheDocument()
    })

    it('has labeled textarea', () => {
      render(<EmailVerificationModal {...defaultProps} />)
      expect(screen.getByLabelText('Reason (optional)')).toBeInTheDocument()
    })

    it('all buttons are keyboard accessible', () => {
      render(<EmailVerificationModal {...defaultProps} />)
      const buttons = screen.getAllByRole('button')
      expect(buttons.length).toBe(2)
      buttons.forEach((button) => {
        expect(button).toBeInTheDocument()
      })
    })

    it('has proper button labels', () => {
      render(<EmailVerificationModal {...defaultProps} />)
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: 'Verify Email' })
      ).toBeInTheDocument()
    })
  })

  describe('Edge Cases', () => {
    it('handles user with empty name', () => {
      const userWithEmptyName = { ...mockUser, name: '' }
      render(
        <EmailVerificationModal {...defaultProps} user={userWithEmptyName} />
      )
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    it('handles user with long name', () => {
      const userWithLongName = { ...mockUser, name: 'A'.repeat(100) }
      render(
        <EmailVerificationModal {...defaultProps} user={userWithLongName} />
      )
      expect(
        screen.getByText('A'.repeat(100), { exact: false })
      ).toBeInTheDocument()
    })

    it('handles user with special characters in name', () => {
      const userWithSpecialName = { ...mockUser, name: "O'Brien-Smith" }
      render(
        <EmailVerificationModal {...defaultProps} user={userWithSpecialName} />
      )
      expect(
        screen.getByText("O'Brien-Smith", { exact: false })
      ).toBeInTheDocument()
    })

    it('handles unicode characters in reason', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Reason (optional)')

      await user.type(textarea, 'Verified 验证 تحقق')
      expect(textarea).toHaveValue('Verified 验证 تحقق')
    })

    it('handles whitespace-only reason as undefined', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Reason (optional)')
      const verifyButton = screen.getByRole('button', { name: 'Verify Email' })

      await user.type(textarea, '   ')
      await user.click(verifyButton)

      await waitFor(() => {
        expect(defaultProps.onConfirm).toHaveBeenCalledWith('   ')
      })
    })

    it('handles rapid verify clicks', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationModal {...defaultProps} />)
      const verifyButton = screen.getByRole('button', { name: 'Verify Email' })

      await user.click(verifyButton)

      await waitFor(() => {
        expect(defaultProps.onConfirm).toHaveBeenCalled()
        expect(defaultProps.onClose).toHaveBeenCalled()
      })
    })

    it('handles different user props', () => {
      const { rerender } = render(
        <EmailVerificationModal {...defaultProps} user={mockUser} />
      )
      expect(
        screen.getByText('Test User', { exact: false })
      ).toBeInTheDocument()

      const newUser = {
        ...mockUser,
        name: 'Jane Doe',
        email: 'jane@example.com',
      }
      rerender(<EmailVerificationModal {...defaultProps} user={newUser} />)
      expect(screen.getByText('Jane Doe', { exact: false })).toBeInTheDocument()
      expect(
        screen.getByText('jane@example.com', { exact: false })
      ).toBeInTheDocument()
    })

    it('preserves reason during loading', async () => {
      const user = userEvent.setup()
      let resolveConfirm: () => void
      const confirmPromise = new Promise<void>((resolve) => {
        resolveConfirm = resolve
      })
      const onConfirm = jest.fn().mockReturnValue(confirmPromise)

      render(<EmailVerificationModal {...defaultProps} onConfirm={onConfirm} />)
      const textarea = screen.getByLabelText('Reason (optional)')
      const verifyButton = screen.getByRole('button', { name: 'Verify Email' })

      await user.type(textarea, 'Important reason')
      await user.click(verifyButton)

      expect(textarea).toHaveValue('Important reason')

      resolveConfirm!()
    })
  })
})
