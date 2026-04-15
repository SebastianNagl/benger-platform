import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { api } from '@/lib/api'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useRouter } from 'next/navigation'
import CompleteProfilePage from '../page'

jest.mock('@/contexts/AuthContext')
jest.mock('@/contexts/I18nContext')
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}))
jest.mock('@/lib/api')

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, ...props }: any) => (
    <button {...props}>{children}</button>
  ),
}))

// Translation map for tests
const translations: Record<string, string> = {
  'completeProfile.loading': 'Loading profile...',
  'completeProfile.title': 'Complete Your Profile',
  'completeProfile.welcome': 'Welcome to BenGER!',
  'completeProfile.description': 'Please set up your username and password to continue.',
  'completeProfile.username': 'Username',
  'completeProfile.usernamePlaceholder': 'Enter username',
  'completeProfile.displayName': 'Display Name (Optional)',
  'completeProfile.displayNamePlaceholder': 'Enter your name',
  'completeProfile.password': 'Password',
  'completeProfile.passwordPlaceholder': 'Enter password',
  'completeProfile.confirmPassword': 'Confirm Password',
  'completeProfile.confirmPasswordPlaceholder': 'Confirm your password',
  'completeProfile.submit': 'Complete Profile Setup',
  'completeProfile.submitting': 'Setting up profile...',
  'completeProfile.passwordMismatch': 'Passwords do not match',
  'completeProfile.passwordTooShort': 'Password must be at least 8 characters',
  'completeProfile.failedToCheck': 'Failed to check profile status',
  'completeProfile.failedToComplete': 'Failed to complete profile setup',
  'completeProfile.alreadyCompleted': 'Profile already completed.',
  'completeProfile.notice': 'Completing your profile will gain full access to your organization\'s projects and collaboration features.',
  'completeProfile.organizationAccess': 'You will have access to your organization after completing your profile.',
}

describe('CompleteProfilePage', () => {
  const mockRouterPush = jest.fn()
  const mockRefreshAuth = jest.fn()
  const mockT = jest.fn((key: string) => translations[key] || key)
  const mockApiGet = jest.fn()
  const mockApiPost = jest.fn()

  const mockUser = {
    id: '1',
    username: 'inviteduser',
    email: 'invited@example.com',
    name: 'Invited User',
    is_superadmin: false,
    is_active: true,
  }

  beforeEach(() => {
    jest.clearAllMocks()
    ;(useAuth as jest.Mock).mockReturnValue({
      user: mockUser,
      refreshAuth: mockRefreshAuth,
      isLoading: false,
    })
    ;(useI18n as jest.Mock).mockReturnValue({
      t: mockT,
      currentLanguage: 'en',
    })
    ;(useRouter as jest.Mock).mockReturnValue({
      push: mockRouterPush,
      replace: jest.fn(),
    })
    ;(api as any).get = mockApiGet
    ;(api as any).post = mockApiPost
  })

  describe('Rendering', () => {
    it('should show loading state initially', () => {
      mockApiGet.mockReturnValue(new Promise(() => {}))

      render(<CompleteProfilePage />)

      expect(screen.getByText('Loading profile...')).toBeInTheDocument()
    })

    it('should render form after loading', async () => {
      mockApiGet.mockResolvedValue({
        data: {
          profile_completed: false,
          created_via_invitation: true,
        },
      })

      render(<CompleteProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Complete Your Profile')).toBeInTheDocument()
        expect(screen.getByLabelText('Username')).toBeInTheDocument()
        expect(
          screen.getByLabelText('Display Name (Optional)')
        ).toBeInTheDocument()
        expect(screen.getByLabelText('Password')).toBeInTheDocument()
        expect(screen.getByLabelText('Confirm Password')).toBeInTheDocument()
      })
    })

    it('should pre-fill username and name from user data', async () => {
      mockApiGet.mockResolvedValue({
        data: {
          profile_completed: false,
          created_via_invitation: true,
        },
      })

      render(<CompleteProfilePage />)

      await waitFor(() => {
        const usernameInput = screen.getByLabelText(
          'Username'
        ) as HTMLInputElement
        const nameInput = screen.getByLabelText(
          'Display Name (Optional)'
        ) as HTMLInputElement

        expect(usernameInput.value).toBe('inviteduser')
        expect(nameInput.value).toBe('Invited User')
      })
    })

    it('should render welcome message', async () => {
      mockApiGet.mockResolvedValue({
        data: {
          profile_completed: false,
          created_via_invitation: true,
        },
      })

      render(<CompleteProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Welcome to BenGER!')).toBeInTheDocument()
        expect(
          screen.getByText(/Please set up your username and password/i)
        ).toBeInTheDocument()
      })
    })
  })

  describe('Profile Status Check', () => {
    it('should redirect to login if user not authenticated', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        refreshAuth: mockRefreshAuth,
        isLoading: false,
      })

      render(<CompleteProfilePage />)

      await waitFor(() => {
        expect(mockRouterPush).toHaveBeenCalledWith('/login')
      })
    })

    it('should redirect to dashboard if profile already completed', async () => {
      mockApiGet.mockResolvedValue({
        data: {
          profile_completed: true,
          created_via_invitation: true,
        },
      })

      render(<CompleteProfilePage />)

      await waitFor(() => {
        expect(mockRouterPush).toHaveBeenCalledWith('/dashboard')
      })
    })

    it('should redirect to dashboard if not invited user', async () => {
      mockApiGet.mockResolvedValue({
        data: {
          profile_completed: false,
          created_via_invitation: false,
        },
      })

      render(<CompleteProfilePage />)

      await waitFor(() => {
        expect(mockRouterPush).toHaveBeenCalledWith('/dashboard')
      })
    })

    it('should show error message on status check failure', async () => {
      const consoleErrorSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})

      mockApiGet.mockRejectedValue(new Error('Failed to check status'))

      render(<CompleteProfilePage />)

      await waitFor(() => {
        expect(
          screen.getByText('Failed to check profile status')
        ).toBeInTheDocument()
      })

      consoleErrorSpy.mockRestore()
    })

    it('should show profile completed message when already complete', async () => {
      mockApiGet.mockResolvedValue({
        data: {
          profile_completed: true,
          created_via_invitation: true,
        },
      })

      render(<CompleteProfilePage />)

      await waitFor(() => {
        expect(
          screen.getByText(/Profile already completed/i)
        ).toBeInTheDocument()
      })
    })
  })

  describe('Form Validation', () => {
    beforeEach(async () => {
      mockApiGet.mockResolvedValue({
        data: {
          profile_completed: false,
          created_via_invitation: true,
        },
      })

      render(<CompleteProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Complete Your Profile')).toBeInTheDocument()
      })
    })

    it('should validate password mismatch', async () => {
      const user = userEvent.setup()

      await user.type(screen.getByLabelText('Password'), 'password123')
      await user.type(screen.getByLabelText('Confirm Password'), 'different')
      await user.click(screen.getByText('Complete Profile Setup'))

      await waitFor(() => {
        expect(screen.getByText('Passwords do not match')).toBeInTheDocument()
      })

      expect(mockApiPost).not.toHaveBeenCalled()
    })

    it('should validate password length', async () => {
      const user = userEvent.setup()

      await user.type(screen.getByLabelText('Password'), '1234567')
      await user.type(screen.getByLabelText('Confirm Password'), '1234567')
      await user.click(screen.getByText('Complete Profile Setup'))

      await waitFor(() => {
        expect(
          screen.getByText('Password must be at least 8 characters')
        ).toBeInTheDocument()
      })

      expect(mockApiPost).not.toHaveBeenCalled()
    })

    it('should have required fields', () => {
      expect(screen.getByLabelText('Username')).toHaveAttribute('required')
      expect(screen.getByLabelText('Password')).toHaveAttribute('required')
      expect(screen.getByLabelText('Confirm Password')).toHaveAttribute(
        'required'
      )
    })

    it('should allow typing in all fields', async () => {
      const user = userEvent.setup()

      const usernameInput = screen.getByLabelText(
        'Username'
      ) as HTMLInputElement
      const nameInput = screen.getByLabelText(
        'Display Name (Optional)'
      ) as HTMLInputElement
      const passwordInput = screen.getByLabelText(
        'Password'
      ) as HTMLInputElement
      const confirmPasswordInput = screen.getByLabelText(
        'Confirm Password'
      ) as HTMLInputElement

      await user.clear(usernameInput)
      await user.clear(nameInput)

      await user.type(usernameInput, 'newusername')
      await user.type(nameInput, 'New Name')
      await user.type(passwordInput, 'password123')
      await user.type(confirmPasswordInput, 'password123')

      expect(usernameInput.value).toBe('newusername')
      expect(nameInput.value).toBe('New Name')
      expect(passwordInput.value).toBe('password123')
      expect(confirmPasswordInput.value).toBe('password123')
    })
  })

  describe('Form Submission', () => {
    beforeEach(async () => {
      mockApiGet.mockResolvedValue({
        data: {
          profile_completed: false,
          created_via_invitation: true,
        },
      })

      render(<CompleteProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Complete Your Profile')).toBeInTheDocument()
      })
    })

    it('should call API with correct data', async () => {
      const user = userEvent.setup()

      mockApiPost.mockResolvedValue({
        data: {
          success: true,
          redirect_url: '/dashboard',
        },
      })

      await user.type(screen.getByLabelText('Password'), 'newpassword123')
      await user.type(
        screen.getByLabelText('Confirm Password'),
        'newpassword123'
      )
      await user.click(screen.getByText('Complete Profile Setup'))

      await waitFor(() => {
        expect(mockApiPost).toHaveBeenCalledWith('/auth/complete-profile', {
          username: 'inviteduser',
          password: 'newpassword123',
          name: 'Invited User',
        })
      })
    })

    it('should handle undefined name field', async () => {
      const user = userEvent.setup()

      mockApiPost.mockResolvedValue({
        data: {
          success: true,
          redirect_url: '/dashboard',
        },
      })

      const nameInput = screen.getByLabelText(
        'Display Name (Optional)'
      ) as HTMLInputElement
      await user.clear(nameInput)

      await user.type(screen.getByLabelText('Password'), 'newpassword123')
      await user.type(
        screen.getByLabelText('Confirm Password'),
        'newpassword123'
      )
      await user.click(screen.getByText('Complete Profile Setup'))

      await waitFor(() => {
        expect(mockApiPost).toHaveBeenCalledWith('/auth/complete-profile', {
          username: 'inviteduser',
          password: 'newpassword123',
          name: undefined,
        })
      })
    })

    it('should show loading state during submission', async () => {
      const user = userEvent.setup()

      let resolvePost: any
      mockApiPost.mockReturnValue(
        new Promise((resolve) => {
          resolvePost = resolve
        })
      )

      await user.type(screen.getByLabelText('Password'), 'newpassword123')
      await user.type(
        screen.getByLabelText('Confirm Password'),
        'newpassword123'
      )

      const submitButton = screen.getByText('Complete Profile Setup')
      await user.click(submitButton)

      await waitFor(() => {
        expect(screen.getByText(/Setting up profile/i)).toBeInTheDocument()
      })

      resolvePost({
        data: { success: true },
      })
    })

    it('should refresh auth after successful submission', async () => {
      const user = userEvent.setup()

      mockApiPost.mockResolvedValue({
        data: {
          success: true,
          redirect_url: '/dashboard',
        },
      })

      await user.type(screen.getByLabelText('Password'), 'newpassword123')
      await user.type(
        screen.getByLabelText('Confirm Password'),
        'newpassword123'
      )
      await user.click(screen.getByText('Complete Profile Setup'))

      await waitFor(() => {
        expect(mockRefreshAuth).toHaveBeenCalled()
      })
    })

    it('should redirect to provided redirect URL', async () => {
      const user = userEvent.setup()

      mockApiPost.mockResolvedValue({
        data: {
          success: true,
          redirect_url: '/projects/123',
        },
      })

      await user.type(screen.getByLabelText('Password'), 'newpassword123')
      await user.type(
        screen.getByLabelText('Confirm Password'),
        'newpassword123'
      )
      await user.click(screen.getByText('Complete Profile Setup'))

      await waitFor(() => {
        expect(mockRouterPush).toHaveBeenCalledWith('/projects/123')
      })
    })

    it('should redirect to dashboard if no redirect URL provided', async () => {
      const user = userEvent.setup()

      mockApiPost.mockResolvedValue({
        data: {
          success: true,
        },
      })

      await user.type(screen.getByLabelText('Password'), 'newpassword123')
      await user.type(
        screen.getByLabelText('Confirm Password'),
        'newpassword123'
      )
      await user.click(screen.getByText('Complete Profile Setup'))

      await waitFor(() => {
        expect(mockRouterPush).toHaveBeenCalledWith('/dashboard')
      })
    })
  })

  describe('Error Handling', () => {
    beforeEach(async () => {
      mockApiGet.mockResolvedValue({
        data: {
          profile_completed: false,
          created_via_invitation: true,
        },
      })

      render(<CompleteProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Complete Your Profile')).toBeInTheDocument()
      })
    })

    it('should display error message on submission failure', async () => {
      const user = userEvent.setup()
      const consoleErrorSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})

      mockApiPost.mockRejectedValue({
        response: {
          data: {
            detail: 'Username already exists',
          },
        },
      })

      await user.type(screen.getByLabelText('Password'), 'newpassword123')
      await user.type(
        screen.getByLabelText('Confirm Password'),
        'newpassword123'
      )
      await user.click(screen.getByText('Complete Profile Setup'))

      await waitFor(() => {
        expect(screen.getByText('Username already exists')).toBeInTheDocument()
      })

      consoleErrorSpy.mockRestore()
    })

    it('should use fallback error message', async () => {
      const user = userEvent.setup()
      const consoleErrorSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})

      mockApiPost.mockRejectedValue(new Error('Network error'))

      await user.type(screen.getByLabelText('Password'), 'newpassword123')
      await user.type(
        screen.getByLabelText('Confirm Password'),
        'newpassword123'
      )
      await user.click(screen.getByText('Complete Profile Setup'))

      await waitFor(() => {
        expect(
          screen.getByText('Failed to complete profile setup')
        ).toBeInTheDocument()
      })

      consoleErrorSpy.mockRestore()
    })

    it('should re-enable submit button after error', async () => {
      const user = userEvent.setup()
      const consoleErrorSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})

      mockApiPost.mockRejectedValue({
        response: {
          data: {
            detail: 'Error',
          },
        },
      })

      await user.type(screen.getByLabelText('Password'), 'newpassword123')
      await user.type(
        screen.getByLabelText('Confirm Password'),
        'newpassword123'
      )
      await user.click(screen.getByText('Complete Profile Setup'))

      await waitFor(() => {
        expect(screen.getByText('Error')).toBeInTheDocument()
        expect(screen.getByText('Complete Profile Setup')).not.toBeDisabled()
      })

      consoleErrorSpy.mockRestore()
    })

    it('should clear error on new submission', async () => {
      const user = userEvent.setup()
      const consoleErrorSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})

      mockApiPost
        .mockRejectedValueOnce({
          response: {
            data: {
              detail: 'First error',
            },
          },
        })
        .mockResolvedValueOnce({
          data: {
            success: true,
          },
        })

      await user.type(screen.getByLabelText('Password'), 'password123')
      await user.type(screen.getByLabelText('Confirm Password'), 'password123')
      await user.click(screen.getByText('Complete Profile Setup'))

      await waitFor(() => {
        expect(screen.getByText('First error')).toBeInTheDocument()
      })

      // Retry
      const passwordInput = screen.getByLabelText(
        'Password'
      ) as HTMLInputElement
      const confirmPasswordInput = screen.getByLabelText(
        'Confirm Password'
      ) as HTMLInputElement

      await user.clear(passwordInput)
      await user.clear(confirmPasswordInput)
      await user.type(passwordInput, 'newpassword123')
      await user.type(confirmPasswordInput, 'newpassword123')
      await user.click(screen.getByText('Complete Profile Setup'))

      await waitFor(() => {
        expect(screen.queryByText('First error')).not.toBeInTheDocument()
      })

      consoleErrorSpy.mockRestore()
    })
  })

  describe('Accessibility', () => {
    beforeEach(async () => {
      mockApiGet.mockResolvedValue({
        data: {
          profile_completed: false,
          created_via_invitation: true,
        },
      })

      render(<CompleteProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Complete Your Profile')).toBeInTheDocument()
      })
    })

    it('should have proper form labels', () => {
      expect(screen.getByLabelText('Username')).toBeInTheDocument()
      expect(
        screen.getByLabelText('Display Name (Optional)')
      ).toBeInTheDocument()
      expect(screen.getByLabelText('Password')).toBeInTheDocument()
      expect(screen.getByLabelText('Confirm Password')).toBeInTheDocument()
    })

    it('should have proper autocomplete attributes', () => {
      expect(screen.getByLabelText('Username')).toHaveAttribute(
        'autocomplete',
        'username'
      )
      expect(screen.getByLabelText('Display Name (Optional)')).toHaveAttribute(
        'autocomplete',
        'name'
      )
      expect(screen.getByLabelText('Password')).toHaveAttribute(
        'autocomplete',
        'new-password'
      )
      expect(screen.getByLabelText('Confirm Password')).toHaveAttribute(
        'autocomplete',
        'new-password'
      )
    })

    it('should have proper field IDs', () => {
      expect(screen.getByLabelText('Username')).toHaveAttribute(
        'id',
        'username'
      )
      expect(screen.getByLabelText('Display Name (Optional)')).toHaveAttribute(
        'id',
        'name'
      )
      expect(screen.getByLabelText('Password')).toHaveAttribute(
        'id',
        'password'
      )
      expect(screen.getByLabelText('Confirm Password')).toHaveAttribute(
        'id',
        'confirmPassword'
      )
    })
  })

  describe('UI Elements', () => {
    beforeEach(async () => {
      mockApiGet.mockResolvedValue({
        data: {
          profile_completed: false,
          created_via_invitation: true,
        },
      })

      render(<CompleteProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Complete Your Profile')).toBeInTheDocument()
      })
    })

    it('should show organization access message', () => {
      expect(
        screen.getByText(/gain full access to your organization's projects/i)
      ).toBeInTheDocument()
    })

    it('should show header icon', () => {
      expect(screen.getByText('Complete Your Profile')).toBeInTheDocument()
    })

    it('should have password field type', () => {
      expect(screen.getByLabelText('Password')).toHaveAttribute(
        'type',
        'password'
      )
      expect(screen.getByLabelText('Confirm Password')).toHaveAttribute(
        'type',
        'password'
      )
    })
  })

  describe('Loading States', () => {
    it('should show loading spinner', () => {
      mockApiGet.mockReturnValue(new Promise(() => {}))

      render(<CompleteProfilePage />)

      expect(screen.getByText('Loading profile...')).toBeInTheDocument()
    })

    it('should not show form during loading', () => {
      mockApiGet.mockReturnValue(new Promise(() => {}))

      render(<CompleteProfilePage />)

      expect(
        screen.queryByText('Complete Your Profile')
      ).not.toBeInTheDocument()
    })
  })
})
