/**
 * @jest-environment jsdom
 */

import { useAuth } from '@/contexts/AuthContext'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SignupModal } from '../SignupModal'

// Mock AuthContext
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))

// Mock I18nContext
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(() => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'signupModal.title': 'Create your BenGER account',
        'signupModal.subtitle': 'Join as an annotator and help improve AI models',
        'signupModal.fullName': 'Full Name',
        'signupModal.fullNamePlaceholder': 'Enter your full name',
        'signupModal.emailAddress': 'Email Address',
        'signupModal.emailPlaceholder': 'Enter your email address',
        'signupModal.username': 'Username',
        'signupModal.usernamePlaceholder': 'Choose a username',
        'signupModal.password': 'Password',
        'signupModal.passwordPlaceholder': 'Enter a secure password',
        'signupModal.confirmPassword': 'Confirm Password',
        'signupModal.confirmPasswordPlaceholder': 'Confirm your password',
        'signupModal.cancel': 'Cancel',
        'signupModal.creating': 'Creating account...',
        'signupModal.createAccount': 'Create account',
        'signupModal.defaultRole': 'New users are created with annotator role by default',
        'signupModal.passwordMismatch': 'Passwords do not match',
        'signupModal.passwordLength': 'Password must be at least 6 characters long',
        'signupModal.signupFailed': 'Signup failed',
      }
      return translations[key] || key
    },
    locale: 'en',
    changeLocale: jest.fn(),
    isReady: true,
  })),
}))

// Mock Headless UI components
jest.mock('@headlessui/react', () => ({
  Dialog: ({ open, onClose, children, className }: any) =>
    open ? (
      <div className={className} data-testid="signup-dialog" role="dialog">
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

describe('SignupModal Component', () => {
  const mockSignup = jest.fn()
  const mockOnClose = jest.fn()
  const mockUseAuth = useAuth as jest.Mock

  beforeEach(() => {
    jest.clearAllMocks()
    jest.useRealTimers()
    mockUseAuth.mockReturnValue({
      signup: mockSignup,
    })
  })

  describe('Modal Visibility', () => {
    it('renders when isOpen is true', () => {
      render(<SignupModal isOpen={true} onClose={mockOnClose} />)

      expect(screen.getByTestId('signup-dialog')).toBeInTheDocument()
      expect(screen.getByText('Create your BenGER account')).toBeInTheDocument()
    })

    it('does not render when isOpen is false', () => {
      render(<SignupModal isOpen={false} onClose={mockOnClose} />)

      expect(screen.queryByTestId('signup-dialog')).not.toBeInTheDocument()
    })

    it('shows dialog role for accessibility', () => {
      render(<SignupModal isOpen={true} onClose={mockOnClose} />)

      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })
  })

  describe('Form Elements', () => {
    beforeEach(() => {
      render(<SignupModal isOpen={true} onClose={mockOnClose} />)
    })

    it('renders all form fields', () => {
      expect(screen.getByLabelText('Full Name')).toBeInTheDocument()
      expect(screen.getByLabelText('Email Address')).toBeInTheDocument()
      expect(screen.getByLabelText('Username')).toBeInTheDocument()
      expect(screen.getByLabelText('Password')).toBeInTheDocument()
      expect(screen.getByLabelText('Confirm Password')).toBeInTheDocument()
    })

    it('has correct input types', () => {
      expect(screen.getByLabelText('Email Address')).toHaveAttribute(
        'type',
        'email'
      )
      expect(screen.getByLabelText('Password')).toHaveAttribute(
        'type',
        'password'
      )
      expect(screen.getByLabelText('Confirm Password')).toHaveAttribute(
        'type',
        'password'
      )
    })

    it('has all fields marked as required', () => {
      expect(screen.getByLabelText('Full Name')).toBeRequired()
      expect(screen.getByLabelText('Email Address')).toBeRequired()
      expect(screen.getByLabelText('Username')).toBeRequired()
      expect(screen.getByLabelText('Password')).toBeRequired()
      expect(screen.getByLabelText('Confirm Password')).toBeRequired()
    })

    it('has correct autocomplete attributes', () => {
      expect(screen.getByLabelText('Full Name')).toHaveAttribute(
        'autocomplete',
        'name'
      )
      expect(screen.getByLabelText('Email Address')).toHaveAttribute(
        'autocomplete',
        'email'
      )
      expect(screen.getByLabelText('Username')).toHaveAttribute(
        'autocomplete',
        'username'
      )
      expect(screen.getByLabelText('Password')).toHaveAttribute(
        'autocomplete',
        'new-password'
      )
    })

    it('renders Cancel and Create account buttons', () => {
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: 'Create account' })
      ).toBeInTheDocument()
    })

    it('shows helper text about annotator role', () => {
      expect(
        screen.getByText('New users are created with annotator role by default')
      ).toBeInTheDocument()
    })
  })

  describe('Form Submission', () => {
    it('submits form with valid data', async () => {
      const user = userEvent.setup()
      mockSignup.mockResolvedValue(undefined)

      render(<SignupModal isOpen={true} onClose={mockOnClose} />)

      await user.type(screen.getByLabelText('Full Name'), 'Test User')
      await user.type(
        screen.getByLabelText('Email Address'),
        'test@example.com'
      )
      await user.type(screen.getByLabelText('Username'), 'testuser')
      await user.type(screen.getByLabelText('Password'), 'password123')
      await user.type(screen.getByLabelText('Confirm Password'), 'password123')

      await user.click(screen.getByRole('button', { name: 'Create account' }))

      await waitFor(() => {
        expect(mockSignup).toHaveBeenCalledWith(
          'testuser',
          'test@example.com',
          'Test User',
          'password123'
        )
      })
    })

    it('calls onClose after successful signup', async () => {
      const user = userEvent.setup()
      mockSignup.mockResolvedValue(undefined)

      render(<SignupModal isOpen={true} onClose={mockOnClose} />)

      await user.type(screen.getByLabelText('Full Name'), 'Test User')
      await user.type(
        screen.getByLabelText('Email Address'),
        'test@example.com'
      )
      await user.type(screen.getByLabelText('Username'), 'testuser')
      await user.type(screen.getByLabelText('Password'), 'password123')
      await user.type(screen.getByLabelText('Confirm Password'), 'password123')

      await user.click(screen.getByRole('button', { name: 'Create account' }))

      await waitFor(() => {
        expect(mockOnClose).toHaveBeenCalled()
      })
    })

    it('clears form after successful signup', async () => {
      const user = userEvent.setup()
      mockSignup.mockResolvedValue(undefined)

      render(<SignupModal isOpen={true} onClose={mockOnClose} />)

      const nameInput = screen.getByLabelText('Full Name')
      const emailInput = screen.getByLabelText('Email Address')
      const usernameInput = screen.getByLabelText('Username')
      const passwordInput = screen.getByLabelText('Password')
      const confirmPasswordInput = screen.getByLabelText('Confirm Password')

      await user.type(nameInput, 'Test User')
      await user.type(emailInput, 'test@example.com')
      await user.type(usernameInput, 'testuser')
      await user.type(passwordInput, 'password123')
      await user.type(confirmPasswordInput, 'password123')

      await user.click(screen.getByRole('button', { name: 'Create account' }))

      await waitFor(() => {
        expect(mockOnClose).toHaveBeenCalled()
      })
    })

    it('shows loading state during submission', async () => {
      const user = userEvent.setup()
      mockSignup.mockImplementation(
        () => new Promise((resolve) => setTimeout(resolve, 1000))
      )

      render(<SignupModal isOpen={true} onClose={mockOnClose} />)

      await user.type(screen.getByLabelText('Full Name'), 'Test User')
      await user.type(
        screen.getByLabelText('Email Address'),
        'test@example.com'
      )
      await user.type(screen.getByLabelText('Username'), 'testuser')
      await user.type(screen.getByLabelText('Password'), 'password123')
      await user.type(screen.getByLabelText('Confirm Password'), 'password123')

      await user.click(screen.getByRole('button', { name: 'Create account' }))

      expect(
        screen.getByRole('button', { name: 'Creating account...' })
      ).toBeInTheDocument()
    })

    it('disables form inputs during submission', async () => {
      const user = userEvent.setup()
      mockSignup.mockImplementation(
        () => new Promise((resolve) => setTimeout(resolve, 1000))
      )

      render(<SignupModal isOpen={true} onClose={mockOnClose} />)

      await user.type(screen.getByLabelText('Full Name'), 'Test User')
      await user.type(
        screen.getByLabelText('Email Address'),
        'test@example.com'
      )
      await user.type(screen.getByLabelText('Username'), 'testuser')
      await user.type(screen.getByLabelText('Password'), 'password123')
      await user.type(screen.getByLabelText('Confirm Password'), 'password123')

      await user.click(screen.getByRole('button', { name: 'Create account' }))

      expect(screen.getByLabelText('Full Name')).toBeDisabled()
      expect(screen.getByLabelText('Email Address')).toBeDisabled()
      expect(screen.getByLabelText('Username')).toBeDisabled()
      expect(screen.getByLabelText('Password')).toBeDisabled()
      expect(screen.getByLabelText('Confirm Password')).toBeDisabled()
    })
  })

  describe('Validation', () => {
    it('shows error when passwords do not match', async () => {
      const user = userEvent.setup()
      render(<SignupModal isOpen={true} onClose={mockOnClose} />)

      await user.type(screen.getByLabelText('Full Name'), 'Test User')
      await user.type(
        screen.getByLabelText('Email Address'),
        'test@example.com'
      )
      await user.type(screen.getByLabelText('Username'), 'testuser')
      await user.type(screen.getByLabelText('Password'), 'password123')
      await user.type(
        screen.getByLabelText('Confirm Password'),
        'differentpassword'
      )

      await user.click(screen.getByRole('button', { name: 'Create account' }))

      expect(screen.getByText('Passwords do not match')).toBeInTheDocument()
      expect(mockSignup).not.toHaveBeenCalled()
    })

    it('shows error when password is too short', async () => {
      const user = userEvent.setup()
      render(<SignupModal isOpen={true} onClose={mockOnClose} />)

      await user.type(screen.getByLabelText('Full Name'), 'Test User')
      await user.type(
        screen.getByLabelText('Email Address'),
        'test@example.com'
      )
      await user.type(screen.getByLabelText('Username'), 'testuser')
      await user.type(screen.getByLabelText('Password'), '12345')
      await user.type(screen.getByLabelText('Confirm Password'), '12345')

      await user.click(screen.getByRole('button', { name: 'Create account' }))

      expect(
        screen.getByText('Password must be at least 6 characters long')
      ).toBeInTheDocument()
      expect(mockSignup).not.toHaveBeenCalled()
    })

    it('clears error when form is corrected', async () => {
      const user = userEvent.setup()
      render(<SignupModal isOpen={true} onClose={mockOnClose} />)

      await user.type(screen.getByLabelText('Full Name'), 'Test User')
      await user.type(
        screen.getByLabelText('Email Address'),
        'test@example.com'
      )
      await user.type(screen.getByLabelText('Username'), 'testuser')
      await user.type(screen.getByLabelText('Password'), '12345')
      await user.type(screen.getByLabelText('Confirm Password'), '12345')

      await user.click(screen.getByRole('button', { name: 'Create account' }))

      expect(screen.getByText(/Password must be at least/)).toBeInTheDocument()

      // Correct the password
      await user.clear(screen.getByLabelText('Password'))
      await user.clear(screen.getByLabelText('Confirm Password'))
      await user.type(screen.getByLabelText('Password'), 'password123')
      await user.type(screen.getByLabelText('Confirm Password'), 'password123')

      await user.click(screen.getByRole('button', { name: 'Create account' }))

      expect(
        screen.queryByText(/Password must be at least/)
      ).not.toBeInTheDocument()
    })

    it('disables submit button when fields are empty', () => {
      render(<SignupModal isOpen={true} onClose={mockOnClose} />)

      const submitButton = screen.getByRole('button', {
        name: 'Create account',
      })
      expect(submitButton).toBeDisabled()
    })

    it('enables submit button when all fields are filled', async () => {
      const user = userEvent.setup()
      render(<SignupModal isOpen={true} onClose={mockOnClose} />)

      await user.type(screen.getByLabelText('Full Name'), 'Test User')
      await user.type(
        screen.getByLabelText('Email Address'),
        'test@example.com'
      )
      await user.type(screen.getByLabelText('Username'), 'testuser')
      await user.type(screen.getByLabelText('Password'), 'password123')
      await user.type(screen.getByLabelText('Confirm Password'), 'password123')

      const submitButton = screen.getByRole('button', {
        name: 'Create account',
      })
      expect(submitButton).not.toBeDisabled()
    })
  })

  describe('Error Handling', () => {
    it('shows error message when signup fails', async () => {
      const user = userEvent.setup()
      mockSignup.mockRejectedValue(new Error('Username already exists'))

      render(<SignupModal isOpen={true} onClose={mockOnClose} />)

      await user.type(screen.getByLabelText('Full Name'), 'Test User')
      await user.type(
        screen.getByLabelText('Email Address'),
        'test@example.com'
      )
      await user.type(screen.getByLabelText('Username'), 'testuser')
      await user.type(screen.getByLabelText('Password'), 'password123')
      await user.type(screen.getByLabelText('Confirm Password'), 'password123')

      await user.click(screen.getByRole('button', { name: 'Create account' }))

      await waitFor(() => {
        expect(screen.getByText('Username already exists')).toBeInTheDocument()
      })
    })

    it('shows generic error for non-Error rejections', async () => {
      const user = userEvent.setup()
      mockSignup.mockRejectedValue('Unknown error')

      render(<SignupModal isOpen={true} onClose={mockOnClose} />)

      await user.type(screen.getByLabelText('Full Name'), 'Test User')
      await user.type(
        screen.getByLabelText('Email Address'),
        'test@example.com'
      )
      await user.type(screen.getByLabelText('Username'), 'testuser')
      await user.type(screen.getByLabelText('Password'), 'password123')
      await user.type(screen.getByLabelText('Confirm Password'), 'password123')

      await user.click(screen.getByRole('button', { name: 'Create account' }))

      await waitFor(() => {
        expect(screen.getByText('Signup failed')).toBeInTheDocument()
      })
    })

    it('does not close modal on error', async () => {
      const user = userEvent.setup()
      const localOnClose = jest.fn()
      mockSignup.mockRejectedValue(new Error('Network error'))

      render(<SignupModal isOpen={true} onClose={localOnClose} />)

      await user.type(screen.getByLabelText('Full Name'), 'Test User')
      await user.type(
        screen.getByLabelText('Email Address'),
        'test@example.com'
      )
      await user.type(screen.getByLabelText('Username'), 'testuser')
      await user.type(screen.getByLabelText('Password'), 'password123')
      await user.type(screen.getByLabelText('Confirm Password'), 'password123')

      await user.click(screen.getByRole('button', { name: 'Create account' }))

      await waitFor(() => {
        expect(screen.getByText('Network error')).toBeInTheDocument()
      })

      expect(localOnClose).not.toHaveBeenCalled()
    })

    it('re-enables form after error', async () => {
      const user = userEvent.setup()
      mockSignup.mockRejectedValue(new Error('Network error'))

      render(<SignupModal isOpen={true} onClose={mockOnClose} />)

      await user.type(screen.getByLabelText('Full Name'), 'Test User')
      await user.type(
        screen.getByLabelText('Email Address'),
        'test@example.com'
      )
      await user.type(screen.getByLabelText('Username'), 'testuser')
      await user.type(screen.getByLabelText('Password'), 'password123')
      await user.type(screen.getByLabelText('Confirm Password'), 'password123')

      await user.click(screen.getByRole('button', { name: 'Create account' }))

      await waitFor(() => {
        expect(screen.getByText('Network error')).toBeInTheDocument()
      })

      expect(screen.getByLabelText('Full Name')).not.toBeDisabled()
      expect(
        screen.getByRole('button', { name: 'Create account' })
      ).not.toBeDisabled()
    })
  })

  describe('Cancel Button', () => {
    it('calls onClose when Cancel button is clicked', async () => {
      const user = userEvent.setup()
      render(<SignupModal isOpen={true} onClose={mockOnClose} />)

      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      expect(mockOnClose).toHaveBeenCalled()
    })

    it('clears form when Cancel button is clicked', async () => {
      const user = userEvent.setup()
      render(<SignupModal isOpen={true} onClose={mockOnClose} />)

      await user.type(screen.getByLabelText('Full Name'), 'Test User')
      await user.type(screen.getByLabelText('Username'), 'testuser')

      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      expect(mockOnClose).toHaveBeenCalled()
    })

    it('clears error when Cancel button is clicked', async () => {
      const user = userEvent.setup()
      render(<SignupModal isOpen={true} onClose={mockOnClose} />)

      await user.type(screen.getByLabelText('Full Name'), 'Test User')
      await user.type(
        screen.getByLabelText('Email Address'),
        'test@example.com'
      )
      await user.type(screen.getByLabelText('Username'), 'testuser')
      await user.type(screen.getByLabelText('Password'), '12345')
      await user.type(screen.getByLabelText('Confirm Password'), '12345')

      await user.click(screen.getByRole('button', { name: 'Create account' }))

      expect(screen.getByText(/Password must be at least/)).toBeInTheDocument()

      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      expect(mockOnClose).toHaveBeenCalled()
    })

    it('does not close modal during submission', async () => {
      const user = userEvent.setup()
      const localOnClose = jest.fn()
      mockSignup.mockImplementation(
        () => new Promise((resolve) => setTimeout(resolve, 1000))
      )

      render(<SignupModal isOpen={true} onClose={localOnClose} />)

      await user.type(screen.getByLabelText('Full Name'), 'Test User')
      await user.type(
        screen.getByLabelText('Email Address'),
        'test@example.com'
      )
      await user.type(screen.getByLabelText('Username'), 'testuser')
      await user.type(screen.getByLabelText('Password'), 'password123')
      await user.type(screen.getByLabelText('Confirm Password'), 'password123')

      await user.click(screen.getByRole('button', { name: 'Create account' }))

      const cancelButton = screen.getByRole('button', { name: 'Cancel' })
      await user.click(cancelButton)

      expect(localOnClose).not.toHaveBeenCalled()
    })
  })

  describe('Dark Mode Support', () => {
    it('applies dark mode classes to dialog', () => {
      const { container } = render(
        <SignupModal isOpen={true} onClose={mockOnClose} />
      )

      const dialogPanel = screen.getByTestId('dialog-panel')
      expect(dialogPanel).toHaveClass('dark:bg-zinc-900')
    })

    it('applies dark mode classes to inputs', () => {
      render(<SignupModal isOpen={true} onClose={mockOnClose} />)

      const nameInput = screen.getByLabelText('Full Name')
      expect(nameInput).toHaveClass('dark:bg-zinc-800', 'dark:text-white')
    })

    it('applies dark mode classes to error message', async () => {
      const user = userEvent.setup()
      render(<SignupModal isOpen={true} onClose={mockOnClose} />)

      await user.type(screen.getByLabelText('Full Name'), 'Test User')
      await user.type(
        screen.getByLabelText('Email Address'),
        'test@example.com'
      )
      await user.type(screen.getByLabelText('Username'), 'testuser')
      await user.type(screen.getByLabelText('Password'), '123')
      await user.type(screen.getByLabelText('Confirm Password'), '123')

      await user.click(screen.getByRole('button', { name: 'Create account' }))

      const errorContainer = screen
        .getByText(/Password must be at least/)
        .closest('div')
      expect(errorContainer).toHaveClass(
        'dark:border-red-800',
        'dark:bg-red-950/50'
      )
    })
  })
})
