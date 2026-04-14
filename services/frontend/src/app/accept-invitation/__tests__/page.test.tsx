/**
 * @jest-environment jsdom
 */

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(() => ({
    push: jest.fn(),
    replace: jest.fn(),
    back: jest.fn(),
    forward: jest.fn(),
    refresh: jest.fn(),
    prefetch: jest.fn(),
    pathname: '/',
    query: {},
    asPath: '/',
    route: '/',
    basePath: '',
    isReady: true,
    isPreview: false,
    isLocaleDomain: false,
  })),
  useParams: jest.fn(() => ({})),
  useSearchParams: jest.fn(() => new URLSearchParams()),
  usePathname: jest.fn(() => '/'),
  notFound: jest.fn(),
  redirect: jest.fn(),
}))
jest.mock('@heroicons/react/24/outline', () => ({
  CheckCircleIcon: () => <div data-testid="check-icon" />,
  ExclamationTriangleIcon: () => <div data-testid="warning-icon" />,
  UserPlusIcon: () => <div data-testid="user-plus-icon" />,
  BuildingOfficeIcon: () => <div data-testid="building-icon" />,
  ClockIcon: () => <div data-testid="clock-icon" />,
  ArrowPathIcon: () => <div data-testid="loading-icon" />,
}))

import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { api } from '@/lib/api'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useRouter } from 'next/navigation'
import AcceptInvitationPage from '../[token]/page'

// Mock the API module
jest.mock('@/lib/api', () => ({
  ApiClient: jest.fn().mockImplementation(() => ({
    login: jest.fn(),
    signup: jest.fn(),
    logout: jest.fn(),
    getProfile: jest.fn(),
    getOrganizations: jest.fn(),
    clearCache: jest.fn(),
    getCurrentUser: jest.fn(),
  })),
  api: {
    getInvitationByToken: jest.fn(),
    acceptInvitation: jest.fn(),
  },
}))

/**
 * Tests for the invitation acceptance page
 */
;('use client')

// Mock dependencies

// Mock icons

const mockRouter = {
  push: jest.fn(),
}

const mockAuth = {
  user: null,
  refreshAuth: jest.fn(),
}

// Translation map for tests
const translations: Record<string, string | ((params: any) => string)> = {
  'invitation.loading': 'Loading invitation...',
  'invitation.invalidTitle': 'Invalid Invitation',
  'invitation.invalidDescription': 'This invitation is invalid or has expired.',
  'invitation.returnHome': 'Return to Home',
  'invitation.title': 'Organization Invitation',
  'invitation.youreInvited': "You've been invited to join",
  'invitation.invitedBy': 'Invited by',
  'invitation.role': 'Role',
  'invitation.email': 'Email',
  'invitation.expires': 'Expires:',
  'invitation.expired': 'This invitation has expired.',
  'invitation.emailMismatch': (params: any) =>
    `This invitation is for ${params.invitedEmail}, but you're logged in as ${params.currentEmail}.`,
  'invitation.welcomeTo': (params: any) => `Welcome to ${params.organizationName}!`,
  'invitation.joinedSuccess': (params: any) =>
    `You have successfully joined as ${params.role}.`,
  'invitation.redirectingToOrg': 'Redirecting to organization...',
  'invitation.accept': 'Accept Invitation',
  'invitation.acceptAndCreate': 'Accept Invitation & Create Account',
  'invitation.alreadyHaveAccount': 'Already have an account?',
  'invitation.loginToAccept': 'Log In to Accept',
  'invitation.cancel': 'Cancel',
  'invitation.back': 'Back',
  'invitation.accepting': 'Accepting Invitation...',
  'invitation.creatingAccount': 'Creating Account...',
  'invitation.createAndJoin': 'Create Account & Join Organization',
  'invitation.fullName': 'Full Name',
  'invitation.fullNamePlaceholder': 'Enter your full name',
  'invitation.username': 'Username',
  'invitation.usernamePlaceholder': 'Choose a username',
  'invitation.password': 'Password',
  'invitation.passwordPlaceholder': 'Create a password (min 6 characters)',
  'invitation.confirmPassword': 'Confirm Password',
  'invitation.confirmPasswordPlaceholder': 'Confirm your password',
  'invitation.passwordMismatch': 'Passwords do not match',
  'invitation.passwordTooShort': 'Password must be at least 6 characters',
  'invitation.emailLabel': 'Email',
}

const mockI18n = {
  t: (key: string, params?: any) => {
    const translation = translations[key]
    if (typeof translation === 'function') {
      return translation(params || {})
    }
    return translation || key
  },
}

const mockInvitation = {
  id: 'inv-123',
  organization_id: 'org-123',
  email: 'test@example.com',
  role: 'org_user' as const,
  token: 'test-token-123',
  invited_by: 'user-123',
  expires_at: '2099-12-31T23:59:59Z',
  accepted_at: null,
  is_accepted: false,
  created_at: '2024-01-01T00:00:00Z',
  organization_name: 'Test Organization',
  inviter_name: 'John Doe',
}

describe('AcceptInvitationPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    ;(useRouter as jest.Mock).mockReturnValue(mockRouter)
    ;(useAuth as jest.Mock).mockReturnValue(mockAuth)
    ;(useI18n as jest.Mock).mockReturnValue(mockI18n)
  })

  it('should show loading state initially', async () => {
    const params = Promise.resolve({ token: 'test-token-123' })
    ;(api.getInvitationByToken as jest.Mock).mockImplementation(
      () => new Promise(() => {}) // Never resolves to keep loading
    )

    render(<AcceptInvitationPage params={params} />)

    expect(screen.getByText('Loading invitation...')).toBeInTheDocument()
    expect(screen.getByTestId('loading-icon')).toBeInTheDocument()
  })

  it('should display invitation details when loaded', async () => {
    const params = Promise.resolve({ token: 'test-token-123' })
    ;(api.getInvitationByToken as jest.Mock).mockResolvedValue(mockInvitation)

    render(<AcceptInvitationPage params={params} />)

    await waitFor(() => {
      expect(screen.getByText('Test Organization')).toBeInTheDocument()
      expect(screen.getByText('John Doe')).toBeInTheDocument()
      expect(screen.getByText('test@example.com')).toBeInTheDocument()
    })
  })

  it('should show error for invalid invitation', async () => {
    const params = Promise.resolve({ token: 'invalid-token' })
    ;(api.getInvitationByToken as jest.Mock).mockRejectedValue(
      new Error('Invitation not found')
    )

    render(<AcceptInvitationPage params={params} />)

    await waitFor(() => {
      expect(screen.getByText('Invalid Invitation')).toBeInTheDocument()
      expect(screen.getByTestId('warning-icon')).toBeInTheDocument()
    })
  })

  it('should render invitation page for unauthenticated user', async () => {
    const params = Promise.resolve({ token: 'test-token-123' })

    // Mock user as null (unauthenticated)
    ;(useAuth as jest.Mock).mockReturnValue({
      user: null,
      refreshAuth: jest.fn(),
    })
    ;(api.getInvitationByToken as jest.Mock).mockResolvedValue(mockInvitation)

    render(<AcceptInvitationPage params={params} />)

    // Check that invitation details are displayed
    await waitFor(() => {
      expect(screen.getByText('Test Organization')).toBeInTheDocument()
      expect(screen.getByText('John Doe')).toBeInTheDocument()
      expect(screen.getByText('test@example.com')).toBeInTheDocument()
    })

    // The page should render without error
    expect(screen.getByText('Organization Invitation')).toBeInTheDocument()
  })

  it('should accept invitation for authenticated user', async () => {
    const params = Promise.resolve({ token: 'test-token-123' })
    const authenticatedUser = {
      id: 'user-123',
      email: 'test@example.com',
      name: 'Test User',
    }

    ;(useAuth as jest.Mock).mockReturnValue({
      user: authenticatedUser,
      refreshAuth: jest.fn(),
    })
    ;(api.getInvitationByToken as jest.Mock).mockResolvedValue(mockInvitation)
    ;(api.acceptInvitation as jest.Mock).mockResolvedValue({
      message: 'Success',
      organization_id: 'org-123',
      role: 'org_user',
    })

    render(<AcceptInvitationPage params={params} />)

    await waitFor(() => {
      expect(screen.getByText('Accept Invitation')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Accept Invitation'))

    await waitFor(() => {
      expect(api.acceptInvitation).toHaveBeenCalledWith('test-token-123')
      expect(
        screen.getByText(/Welcome to Test Organization/)
      ).toBeInTheDocument()
    })

    // Should redirect after success
    await waitFor(
      () => {
        expect(mockRouter.push).toHaveBeenCalledWith('/dashboard')
      },
      { timeout: 3000 }
    )
  })

  it('should show warning for email mismatch', async () => {
    const params = Promise.resolve({ token: 'test-token-123' })
    const authenticatedUser = {
      id: 'user-456',
      email: 'different@example.com',
      name: 'Different User',
    }

    ;(useAuth as jest.Mock).mockReturnValue({
      user: authenticatedUser,
      refreshAuth: jest.fn(),
    })
    ;(api.getInvitationByToken as jest.Mock).mockResolvedValue(mockInvitation)

    render(<AcceptInvitationPage params={params} />)

    await waitFor(() => {
      expect(
        screen.getByText(/This invitation is for test@example.com/)
      ).toBeInTheDocument()
      expect(
        screen.getByText(/you're logged in as different@example.com/)
      ).toBeInTheDocument()
    })

    // Accept button should be disabled
    const acceptButton = screen.getByText('Accept Invitation')
    expect(acceptButton.closest('button')).toBeDisabled()
  })

  it('should show expired invitation warning', async () => {
    const params = Promise.resolve({ token: 'test-token-123' })
    const expiredInvitation = {
      ...mockInvitation,
      expires_at: '2020-01-01T00:00:00Z',
    }

    ;(api.getInvitationByToken as jest.Mock).mockResolvedValue(
      expiredInvitation
    )

    render(<AcceptInvitationPage params={params} />)

    await waitFor(() => {
      expect(
        screen.getByText(/This invitation has expired/)
      ).toBeInTheDocument()
    })
  })

  describe('Account Setup Redirect', () => {
    it('should redirect to full registration when clicking accept as guest', async () => {
      const params = Promise.resolve({ token: 'test-token-123' })
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        refreshAuth: jest.fn(),
        signup: jest.fn(),
        isLoading: false,
      })
      ;(api.getInvitationByToken as jest.Mock).mockResolvedValue(mockInvitation)

      render(<AcceptInvitationPage params={params} />)

      await waitFor(() => {
        expect(
          screen.getByText('Accept Invitation & Create Account')
        ).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('Accept Invitation & Create Account'))

      expect(mockRouter.push).toHaveBeenCalledWith(
        '/register?invitation=test-token-123&email=test%40example.com'
      )
    })
  })

  describe('Login Flow', () => {
    it('should show login button for unauthenticated users', async () => {
      const params = Promise.resolve({ token: 'test-token-123' })
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        refreshAuth: jest.fn(),
        isLoading: false,
      })
      ;(api.getInvitationByToken as jest.Mock).mockResolvedValue(mockInvitation)

      render(<AcceptInvitationPage params={params} />)

      await waitFor(() => {
        expect(screen.getByText('Log In to Accept')).toBeInTheDocument()
      })
    })

    it('should navigate to login with redirect', async () => {
      const params = Promise.resolve({ token: 'test-token-123' })
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        refreshAuth: jest.fn(),
        isLoading: false,
      })
      ;(api.getInvitationByToken as jest.Mock).mockResolvedValue(mockInvitation)

      render(<AcceptInvitationPage params={params} />)

      await waitFor(() => {
        expect(screen.getByText('Log In to Accept')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('Log In to Accept'))

      expect(mockRouter.push).toHaveBeenCalledWith(
        '/login?redirect=/accept-invitation/test-token-123'
      )
    })
  })

  describe('Invitation Details Display', () => {
    it('should display organization icon', async () => {
      const params = Promise.resolve({ token: 'test-token-123' })
      ;(api.getInvitationByToken as jest.Mock).mockResolvedValue(mockInvitation)

      render(<AcceptInvitationPage params={params} />)

      await waitFor(() => {
        expect(screen.getByTestId('building-icon')).toBeInTheDocument()
      })
    })

    it('should display invite icon in header', async () => {
      const params = Promise.resolve({ token: 'test-token-123' })
      ;(api.getInvitationByToken as jest.Mock).mockResolvedValue(mockInvitation)

      render(<AcceptInvitationPage params={params} />)

      await waitFor(() => {
        expect(screen.getByTestId('user-plus-icon')).toBeInTheDocument()
      })
    })

    it('should display expiry date with clock icon', async () => {
      const params = Promise.resolve({ token: 'test-token-123' })
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        refreshAuth: jest.fn(),
        isLoading: false,
      })
      ;(api.getInvitationByToken as jest.Mock).mockResolvedValue(mockInvitation)

      render(<AcceptInvitationPage params={params} />)

      await waitFor(() => {
        expect(screen.getByText('Test Organization')).toBeInTheDocument()
      })

      expect(screen.getByTestId('clock-icon')).toBeInTheDocument()
      expect(screen.getByText('Expires:')).toBeInTheDocument()
    })

    it('should capitalize role name', async () => {
      const params = Promise.resolve({ token: 'test-token-123' })
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        refreshAuth: jest.fn(),
        isLoading: false,
      })
      ;(api.getInvitationByToken as jest.Mock).mockResolvedValue(mockInvitation)

      render(<AcceptInvitationPage params={params} />)

      await waitFor(() => {
        expect(screen.getByText('org user')).toBeInTheDocument()
      })
    })
  })

  describe('Cancel Button', () => {
    it('should show cancel button', async () => {
      const params = Promise.resolve({ token: 'test-token-123' })
      ;(api.getInvitationByToken as jest.Mock).mockResolvedValue(mockInvitation)

      render(<AcceptInvitationPage params={params} />)

      await waitFor(() => {
        expect(screen.getByText('Cancel')).toBeInTheDocument()
      })
    })

    it('should navigate to home on cancel', async () => {
      const params = Promise.resolve({ token: 'test-token-123' })
      ;(api.getInvitationByToken as jest.Mock).mockResolvedValue(mockInvitation)

      render(<AcceptInvitationPage params={params} />)

      await waitFor(() => {
        expect(screen.getByText('Cancel')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('Cancel'))

      expect(mockRouter.push).toHaveBeenCalledWith('/')
    })
  })

  describe('Loading States', () => {
    it('should show loading state while auth is loading', () => {
      const params = Promise.resolve({ token: 'test-token-123' })
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        refreshAuth: jest.fn(),
        isLoading: true,
      })
      ;(api.getInvitationByToken as jest.Mock).mockImplementation(
        () => new Promise(() => {})
      )

      render(<AcceptInvitationPage params={params} />)

      expect(screen.getByText('Loading invitation...')).toBeInTheDocument()
    })

    it('should show accepting state during submission', async () => {
      const params = Promise.resolve({ token: 'test-token-123' })
      const mockAccept = jest.fn(() => new Promise(() => {}))
      ;(useAuth as jest.Mock).mockReturnValue({
        user: {
          id: 'user-123',
          email: 'test@example.com',
        },
        refreshAuth: jest.fn(),
        isLoading: false,
      })
      ;(api.getInvitationByToken as jest.Mock).mockResolvedValue(mockInvitation)
      ;(api.acceptInvitation as jest.Mock).mockImplementation(mockAccept)

      render(<AcceptInvitationPage params={params} />)

      await waitFor(() => {
        expect(screen.getByText('Accept Invitation')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('Accept Invitation'))

      await waitFor(() => {
        expect(screen.getByText('Accepting Invitation...')).toBeInTheDocument()
      })
    })

    it('should redirect to register when clicking accept as guest', async () => {
      const params = Promise.resolve({ token: 'test-token-123' })
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        refreshAuth: jest.fn(),
        signup: jest.fn(),
        isLoading: false,
      })
      ;(api.getInvitationByToken as jest.Mock).mockResolvedValue(mockInvitation)

      render(<AcceptInvitationPage params={params} />)

      await waitFor(() => {
        expect(
          screen.getByText('Accept Invitation & Create Account')
        ).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('Accept Invitation & Create Account'))

      expect(mockRouter.push).toHaveBeenCalledWith(
        expect.stringContaining('/register?invitation=')
      )
    })
  })

  describe('Error Return to Home', () => {
    it('should show return to home button on error', async () => {
      const params = Promise.resolve({ token: 'invalid-token' })
      ;(api.getInvitationByToken as jest.Mock).mockRejectedValue(
        new Error('Invitation not found')
      )

      render(<AcceptInvitationPage params={params} />)

      await waitFor(() => {
        expect(screen.getByText('Return to Home')).toBeInTheDocument()
      })
    })

    it('should navigate home when clicking return button', async () => {
      const params = Promise.resolve({ token: 'invalid-token' })
      ;(api.getInvitationByToken as jest.Mock).mockRejectedValue(
        new Error('Invitation not found')
      )

      render(<AcceptInvitationPage params={params} />)

      await waitFor(() => {
        expect(screen.getByText('Return to Home')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('Return to Home'))

      expect(mockRouter.push).toHaveBeenCalledWith('/')
    })
  })

  describe('Disabled States', () => {
    it('should disable accept button when expired', async () => {
      const params = Promise.resolve({ token: 'test-token-123' })
      const expiredInvitation = {
        ...mockInvitation,
        expires_at: '2020-01-01T00:00:00Z',
      }
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        refreshAuth: jest.fn(),
        isLoading: false,
      })
      ;(api.getInvitationByToken as jest.Mock).mockResolvedValue(
        expiredInvitation
      )

      render(<AcceptInvitationPage params={params} />)

      await waitFor(() => {
        const acceptButton = screen.getByText(
          'Accept Invitation & Create Account'
        )
        expect(acceptButton.closest('button')).toBeDisabled()
      })
    })
  })

  describe('Error Handling in Accept Invitation', () => {
    it('should handle API error when accepting invitation', async () => {
      const params = Promise.resolve({ token: 'test-token-123' })
      const authenticatedUser = {
        id: 'user-123',
        email: 'test@example.com',
        name: 'Test User',
      }

      ;(useAuth as jest.Mock).mockReturnValue({
        user: authenticatedUser,
        refreshAuth: jest.fn(),
        isLoading: false,
      })
      ;(api.getInvitationByToken as jest.Mock).mockResolvedValue(mockInvitation)
      ;(api.acceptInvitation as jest.Mock).mockRejectedValue({
        response: {
          data: {
            detail: 'Invitation already accepted',
          },
        },
      })

      render(<AcceptInvitationPage params={params} />)

      await waitFor(() => {
        expect(screen.getByText('Accept Invitation')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('Accept Invitation'))

      await waitFor(() => {
        expect(
          screen.getByText('Invitation already accepted')
        ).toBeInTheDocument()
      })
    })

    it('should handle generic error when accepting invitation', async () => {
      const params = Promise.resolve({ token: 'test-token-123' })
      const authenticatedUser = {
        id: 'user-123',
        email: 'test@example.com',
        name: 'Test User',
      }

      ;(useAuth as jest.Mock).mockReturnValue({
        user: authenticatedUser,
        refreshAuth: jest.fn(),
        isLoading: false,
      })
      ;(api.getInvitationByToken as jest.Mock).mockResolvedValue(mockInvitation)
      ;(api.acceptInvitation as jest.Mock).mockRejectedValue(
        new Error('Network error')
      )

      render(<AcceptInvitationPage params={params} />)

      await waitFor(() => {
        expect(screen.getByText('Accept Invitation')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('Accept Invitation'))

      await waitFor(() => {
        expect(
          screen.getByText('invitation.acceptFailed')
        ).toBeInTheDocument()
      })
    })
  })

})
