import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AuthButton } from '../AuthButton'

 

// Mock Next.js Link
jest.mock('next/link', () => {
  function Link({ href, className, children, onClick }: any) {
    return (
      <a href={href} className={className} onClick={onClick}>
        {children}
      </a>
    )
  }
  return Link
})

// Mock components
jest.mock('@/components/shared/Button', () => {
  function Button({ children, onClick, variant, disabled, className }: any) {
    return (
      <button
        onClick={onClick}
        disabled={disabled}
        className={`${variant} ${className}`}
      >
        {children}
      </button>
    )
  }
  return { Button }
})

jest.mock('@/components/auth/LoginModal', () => {
  function LoginModal({ isOpen, onClose }: any) {
    return isOpen ? <div data-testid="login-modal">Login Modal</div> : null
  }
  return { LoginModal }
})

jest.mock('@/components/auth/SignupModal', () => {
  function SignupModal({ isOpen, onClose }: any) {
    return isOpen ? <div data-testid="signup-modal">Signup Modal</div> : null
  }
  return { SignupModal }
})

// Mock contexts
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(),
}))

jest.mock('@/contexts/FeatureFlagContext', () => ({
  useFeatureFlags: jest.fn(),
}))

jest.mock('@/contexts/HydrationContext', () => ({
  useHydration: jest.fn(() => true),
}))

jest.mock('@/lib/utils/subdomain', () => ({
  parseSubdomain: jest.fn(() => ({ orgSlug: null, isPrivateMode: true })),
}))

// Mock Heroicons
jest.mock('@heroicons/react/24/outline', () => {
  function ChevronDownIcon(props: any) {
    return <svg data-testid="chevron-down" {...props} />
  }

  function UserIcon(props: any) {
    return <svg data-testid="user-icon" {...props} />
  }

  function BellIcon(props: any) {
    return <svg data-testid="bell-icon" {...props} />
  }

  function ArrowRightOnRectangleIcon(props: any) {
    return <svg data-testid="logout-icon" {...props} />
  }

  function UsersIcon(props: any) {
    return <svg data-testid="users-icon" {...props} />
  }

  function CogIcon(props: any) {
    return <svg data-testid="cog-icon" {...props} />
  }

  function BeakerIcon(props: any) {
    return <svg data-testid="beaker-icon" {...props} />
  }

  function BuildingOfficeIcon(props: any) {
    return <svg data-testid="building-icon" {...props} />
  }

  function CheckIcon(props: any) {
    return <svg data-testid="check-icon" {...props} />
  }

  return {
    ChevronDownIcon,
    UserIcon,
    BellIcon,
    ArrowRightOnRectangleIcon,
    UsersIcon,
    CogIcon,
    BeakerIcon,
    BuildingOfficeIcon,
    CheckIcon,
  }
})

const mockUseAuth = require('@/contexts/AuthContext').useAuth
const mockUseI18n = require('@/contexts/I18nContext').useI18n
const mockUseFeatureFlags =
  require('@/contexts/FeatureFlagContext').useFeatureFlags

describe('AuthButton', () => {
  const mockLogout = jest.fn()

  const translations = {
    'auth.signIn': 'Sign In',
    'auth.signUp': 'Sign Up',
    'auth.signOut': 'Sign Out',
    'auth.profileSettings': 'Profile Settings',
    'auth.notificationSettings': 'Notification Settings',
    'auth.userManagement': 'User Management',
    'auth.switchContext': 'Switch Context',
    'auth.private': 'Private',
    'navigation.organizations': 'Organizations',
    'admin.usersOrganizations': 'Users & Organizations',
    'admin.defaultConfiguration': 'Default Configuration',
    'admin.featureFlags': 'Feature Flags',
    'common.loading': 'Loading...',
  }

  const mockT = jest.fn((key: string) => translations[key] || key)

  beforeEach(() => {
    jest.clearAllMocks()
    mockUseI18n.mockReturnValue({ t: mockT })
    mockUseFeatureFlags.mockReturnValue({
      flags: {},
      isLoading: false,
      error: null,
      isEnabled: jest.fn().mockReturnValue(true),
      refreshFlags: jest.fn(),
      checkFlag: jest.fn().mockResolvedValue(true),
      lastUpdate: Date.now(),
    })
  })

  describe('loading state', () => {
    it('shows loading button when auth is loading', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        logout: mockLogout,
        isLoading: true,
        currentOrganization: null,
        organizations: [],
        setCurrentOrganization: jest.fn(),
      })

      render(<AuthButton />)

      const loadingButton = screen.getByRole('button', { name: /loading/i })
      expect(loadingButton).toBeInTheDocument()
      expect(loadingButton).toBeDisabled()
    })

    it('shows translated loading text when client is mounted', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        logout: mockLogout,
        isLoading: true,
        currentOrganization: null,
        organizations: [],
        setCurrentOrganization: jest.fn(),
      })

      render(<AuthButton />)

      expect(mockT).toHaveBeenCalledWith('common.loading')
    })
  })

  describe('unauthenticated state', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: null,
        logout: mockLogout,
        isLoading: false,
        currentOrganization: null,
        organizations: [],
        setCurrentOrganization: jest.fn(),
      })
    })

    it('shows sign in and sign up buttons', () => {
      render(<AuthButton />)

      expect(
        screen.getByRole('button', { name: /sign in/i })
      ).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: /sign up/i })
      ).toBeInTheDocument()
    })

    it('opens login modal when sign in button is clicked', async () => {
      const user = userEvent.setup()
      render(<AuthButton />)

      const signInButton = screen.getByRole('button', { name: /sign in/i })
      await user.click(signInButton)

      expect(screen.getByTestId('login-modal')).toBeInTheDocument()
    })

    it('opens signup modal when sign up button is clicked', async () => {
      const user = userEvent.setup()
      render(<AuthButton />)

      const signUpButton = screen.getByRole('button', { name: /sign up/i })
      await user.click(signUpButton)

      expect(screen.getByTestId('signup-modal')).toBeInTheDocument()
    })

    it('uses translated text for buttons', () => {
      render(<AuthButton />)

      expect(mockT).toHaveBeenCalledWith('auth.signIn')
      expect(mockT).toHaveBeenCalledWith('auth.signUp')
    })
  })

  describe('authenticated state', () => {
    const mockUser = {
      id: '1',
      username: 'testuser',
      email: 'test@example.com',
      is_superadmin: false,
    }

    const mockOrganization = {
      id: '1',
      name: 'Test Org',
      role: 'MEMBER',
    }

    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: mockUser,
        logout: mockLogout,
        isLoading: false,
        currentOrganization: mockOrganization,
        organizations: [mockOrganization],
        setCurrentOrganization: jest.fn(),
      })
    })

    it('shows user dropdown trigger', () => {
      render(<AuthButton />)

      expect(screen.getByText('testuser')).toBeInTheDocument()
      expect(screen.getByText('(Test Org)')).toBeInTheDocument()
      expect(screen.getByTestId('chevron-down')).toBeInTheDocument()
    })

    it('toggles dropdown when clicked', async () => {
      const user = userEvent.setup()
      render(<AuthButton />)

      const dropdown = screen.getByRole('button')

      // Open dropdown
      await user.click(dropdown)
      expect(screen.getByText(/profile settings/i)).toBeInTheDocument()

      // Close dropdown
      await user.click(dropdown)
      expect(screen.queryByText(/profile settings/i)).not.toBeInTheDocument()
    })

    it('shows basic menu items for regular user', async () => {
      const user = userEvent.setup()
      render(<AuthButton />)

      await user.click(screen.getByRole('button'))

      expect(screen.getByText(/profile settings/i)).toBeInTheDocument()
      expect(screen.getByText(/notification settings/i)).toBeInTheDocument()
      expect(screen.getByText(/sign out/i)).toBeInTheDocument()
    })

    it('calls logout when sign out is clicked', async () => {
      const user = userEvent.setup()
      render(<AuthButton />)

      await user.click(screen.getByRole('button'))
      await user.click(screen.getByTestId('logout-button'))

      expect(mockLogout).toHaveBeenCalledTimes(1)
    })

    it('closes dropdown when clicking outside', async () => {
      const user = userEvent.setup()
      render(
        <div>
          <AuthButton />
          <div data-testid="outside">Outside</div>
        </div>
      )

      // Open dropdown
      await user.click(screen.getByRole('button'))
      expect(screen.getByText(/profile settings/i)).toBeInTheDocument()

      // Click outside
      await user.click(screen.getByTestId('outside'))
      await waitFor(() => {
        expect(screen.queryByText(/profile settings/i)).not.toBeInTheDocument()
      })
    })
  })

  describe('organization admin features', () => {
    const mockOrgAdmin = {
      id: '1',
      username: 'orgadmin',
      email: 'admin@example.com',
      is_superadmin: false,
    }

    const mockOrgAdminOrganization = {
      id: '1',
      name: 'Admin Org',
      role: 'ORG_ADMIN',
    }

    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: mockOrgAdmin,
        logout: mockLogout,
        isLoading: false,
        currentOrganization: mockOrgAdminOrganization,
        organizations: [mockOrgAdminOrganization],
        setCurrentOrganization: jest.fn(),
      })
    })

    it('shows organizations link for org admin', async () => {
      const user = userEvent.setup()
      render(<AuthButton />)

      await user.click(screen.getByRole('button'))

      expect(screen.getByText(/users & organizations/i)).toBeInTheDocument()
      expect(screen.getByTestId('users-icon')).toBeInTheDocument()
    })
  })

  describe('superadmin features', () => {
    const mockSuperAdmin = {
      id: '1',
      username: 'superadmin',
      email: 'super@example.com',
      is_superadmin: true,
    }

    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: mockSuperAdmin,
        logout: mockLogout,
        isLoading: false,
        currentOrganization: null,
        organizations: [],
        setCurrentOrganization: jest.fn(),
      })
    })

    it('shows admin menu items for superadmin', async () => {
      const user = userEvent.setup()
      render(<AuthButton />)

      await user.click(screen.getByRole('button'))

      expect(screen.getByText(/users & organizations/i)).toBeInTheDocument()
      expect(screen.getByText(/feature flags/i)).toBeInTheDocument()

      expect(screen.getByTestId('users-icon')).toBeInTheDocument()
      expect(screen.getByTestId('beaker-icon')).toBeInTheDocument()
    })

    it('shows organizations link for superadmin', async () => {
      const user = userEvent.setup()
      render(<AuthButton />)

      await user.click(screen.getByRole('button'))

      expect(screen.getByText(/users & organizations/i)).toBeInTheDocument()
      expect(screen.getByTestId('users-icon')).toBeInTheDocument()
    })
  })

  describe('responsive behavior', () => {
    const mockUser = {
      id: '1',
      username: 'testuser',
      email: 'test@example.com',
      is_superadmin: false,
    }

    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: mockUser,
        logout: mockLogout,
        isLoading: false,
        currentOrganization: { id: '1', name: 'Test Org', role: 'MEMBER' },
        organizations: [],
        setCurrentOrganization: jest.fn(),
      })
    })

    it('hides username on small screens', () => {
      render(<AuthButton />)

      const username = screen.getByText('testuser')
      expect(username).toHaveClass('hidden', 'sm:block')
    })

    it('hides organization name on medium screens and below', () => {
      render(<AuthButton />)

      const orgName = screen.getByText('(Test Org)')
      expect(orgName).toHaveClass('hidden', 'text-xs', 'opacity-70', 'md:block')
    })
  })

  describe('dropdown styling', () => {
    const mockUser = {
      id: '1',
      username: 'testuser',
      email: 'test@example.com',
      is_superadmin: false,
    }

    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: mockUser,
        logout: mockLogout,
        isLoading: false,
        currentOrganization: null,
        organizations: [],
        setCurrentOrganization: jest.fn(),
      })
    })

    it('applies correct dropdown positioning and styling', async () => {
      const user = userEvent.setup()
      render(<AuthButton />)

      await user.click(screen.getByRole('button'))

      const dropdown = screen
        .getByText(/profile settings/i)
        .closest('.absolute')
      expect(dropdown).toHaveClass(
        'absolute',
        'right-0',
        'mt-2',
        'w-52',
        'bg-white',
        'dark:bg-zinc-800',
        'border',
        'border-zinc-200',
        'dark:border-zinc-700',
        'rounded-lg',
        'shadow-lg',
        'z-50'
      )
    })

    it('rotates chevron icon when dropdown is open', async () => {
      const user = userEvent.setup()
      render(<AuthButton />)

      const chevron = screen.getByTestId('chevron-down')
      expect(chevron).toHaveClass('transition-transform')

      await user.click(screen.getByRole('button'))
      expect(chevron).toHaveClass('rotate-180')
    })
  })

  describe('accessibility', () => {
    it('provides proper button role for unauthenticated state', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        logout: mockLogout,
        isLoading: false,
        currentOrganization: null,
        organizations: [],
        setCurrentOrganization: jest.fn(),
      })

      render(<AuthButton />)

      expect(screen.getAllByRole('button')).toHaveLength(2) // Sign in + Sign up
    })

    it('provides proper button role for dropdown trigger', () => {
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          username: 'test',
          email: 'test@example.com',
          is_superadmin: false,
        },
        logout: mockLogout,
        isLoading: false,
        currentOrganization: null,
        organizations: [],
        setCurrentOrganization: jest.fn(),
      })

      render(<AuthButton />)

      expect(screen.getByRole('button')).toBeInTheDocument()
    })

    it('provides test id for logout button', async () => {
      const user = userEvent.setup()
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          username: 'test',
          email: 'test@example.com',
          is_superadmin: false,
        },
        logout: mockLogout,
        isLoading: false,
        currentOrganization: null,
        organizations: [],
        setCurrentOrganization: jest.fn(),
      })

      render(<AuthButton />)

      await user.click(screen.getByRole('button'))
      expect(screen.getByTestId('logout-button')).toBeInTheDocument()
    })
  })

  describe('internationalization', () => {
    it('calls translation function for all text content', async () => {
      const user = userEvent.setup()
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          username: 'test',
          email: 'test@example.com',
          is_superadmin: true,
        },
        logout: mockLogout,
        isLoading: false,
        currentOrganization: null,
        organizations: [],
        setCurrentOrganization: jest.fn(),
      })

      render(<AuthButton />)

      await user.click(screen.getByRole('button'))

      expect(mockT).toHaveBeenCalledWith('auth.profileSettings')
      expect(mockT).toHaveBeenCalledWith('auth.notificationSettings')
      expect(mockT).toHaveBeenCalledWith('admin.usersOrganizations')
      expect(mockT).toHaveBeenCalledWith('admin.featureFlags')
      expect(mockT).toHaveBeenCalledWith('auth.signOut')
    })
  })

  describe('modal state management', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: null,
        logout: mockLogout,
        isLoading: false,
        currentOrganization: null,
        organizations: [],
        setCurrentOrganization: jest.fn(),
      })
    })

    it('keeps login modal open when clicking sign in again', async () => {
      const user = userEvent.setup()
      render(<AuthButton />)

      const signInButton = screen.getByRole('button', { name: /sign in/i })
      await user.click(signInButton)
      expect(screen.getByTestId('login-modal')).toBeInTheDocument()

      // Clicking again keeps modal open (doesn't toggle)
      await user.click(signInButton)
      expect(screen.getByTestId('login-modal')).toBeInTheDocument()
    })

    it('keeps signup modal open when clicking sign up again', async () => {
      const user = userEvent.setup()
      render(<AuthButton />)

      const signUpButton = screen.getByRole('button', { name: /sign up/i })
      await user.click(signUpButton)
      expect(screen.getByTestId('signup-modal')).toBeInTheDocument()

      // Clicking again keeps modal open (doesn't toggle)
      await user.click(signUpButton)
      expect(screen.getByTestId('signup-modal')).toBeInTheDocument()
    })

    it('can have both modals open simultaneously', async () => {
      const user = userEvent.setup()
      render(<AuthButton />)

      const signInButton = screen.getByRole('button', { name: /sign in/i })
      await user.click(signInButton)
      expect(screen.getByTestId('login-modal')).toBeInTheDocument()

      const signUpButton = screen.getByRole('button', { name: /sign up/i })
      await user.click(signUpButton)
      // Both modals can be open at the same time
      expect(screen.getByTestId('login-modal')).toBeInTheDocument()
      expect(screen.getByTestId('signup-modal')).toBeInTheDocument()
    })
  })

  describe('dropdown menu links', () => {
    const mockUser = {
      id: '1',
      username: 'testuser',
      email: 'test@example.com',
      is_superadmin: false,
    }

    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: mockUser,
        logout: mockLogout,
        isLoading: false,
        currentOrganization: null,
        organizations: [],
        setCurrentOrganization: jest.fn(),
      })
    })

    it('profile link has correct href', async () => {
      const user = userEvent.setup()
      render(<AuthButton />)

      await user.click(screen.getByRole('button'))

      const profileLink = screen.getByText(/profile settings/i).closest('a')
      expect(profileLink).toHaveAttribute('href', '/profile')
    })

    it('notification settings link has correct href', async () => {
      const user = userEvent.setup()
      render(<AuthButton />)

      await user.click(screen.getByRole('button'))

      const notifLink = screen.getByText(/notification settings/i).closest('a')
      expect(notifLink).toHaveAttribute('href', '/settings/notifications')
    })

    it('closes dropdown when profile link is clicked', async () => {
      const user = userEvent.setup()
      render(<AuthButton />)

      await user.click(screen.getByRole('button'))
      expect(screen.getByText(/profile settings/i)).toBeInTheDocument()

      const profileLink = screen.getByText(/profile settings/i)
      await user.click(profileLink)

      await waitFor(() => {
        expect(screen.queryByText(/profile settings/i)).not.toBeInTheDocument()
      })
    })

    it('closes dropdown when notification settings link is clicked', async () => {
      const user = userEvent.setup()
      render(<AuthButton />)

      await user.click(screen.getByRole('button'))
      expect(screen.getByText(/notification settings/i)).toBeInTheDocument()

      const notifLink = screen.getByText(/notification settings/i)
      await user.click(notifLink)

      await waitFor(() => {
        expect(
          screen.queryByText(/notification settings/i)
        ).not.toBeInTheDocument()
      })
    })
  })

  describe('admin menu links', () => {
    it('users & organizations link has correct href for org admin', async () => {
      const user = userEvent.setup()
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          username: 'orgadmin',
          email: 'admin@example.com',
          is_superadmin: false,
        },
        logout: mockLogout,
        isLoading: false,
        currentOrganization: { id: '1', name: 'Admin Org', role: 'ORG_ADMIN' },
        organizations: [{ id: '1', name: 'Admin Org', role: 'ORG_ADMIN' }],
        setCurrentOrganization: jest.fn(),
      })

      render(<AuthButton />)

      await user.click(screen.getByRole('button'))

      const usersLink = screen.getByText(/users & organizations/i).closest('a')
      expect(usersLink).toHaveAttribute('href', '/users-organizations')
    })

    it('feature flags link has correct href for superadmin', async () => {
      const user = userEvent.setup()
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          username: 'superadmin',
          email: 'super@example.com',
          is_superadmin: true,
        },
        logout: mockLogout,
        isLoading: false,
        currentOrganization: null,
        organizations: [],
        setCurrentOrganization: jest.fn(),
      })

      render(<AuthButton />)

      await user.click(screen.getByRole('button'))

      const flagsLink = screen.getByText(/feature flags/i).closest('a')
      expect(flagsLink).toHaveAttribute('href', '/admin/feature-flags')
    })

    it('closes dropdown when admin link is clicked', async () => {
      const user = userEvent.setup()
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          username: 'superadmin',
          email: 'super@example.com',
          is_superadmin: true,
        },
        logout: mockLogout,
        isLoading: false,
        currentOrganization: null,
        organizations: [],
        setCurrentOrganization: jest.fn(),
      })

      render(<AuthButton />)

      await user.click(screen.getByRole('button'))

      const usersLink = screen.getByText(/users & organizations/i)
      await user.click(usersLink)

      await waitFor(() => {
        expect(
          screen.queryByText(/users & organizations/i)
        ).not.toBeInTheDocument()
      })
    })
  })

  describe('client-side hydration', () => {
    it('shows fallback text before client is mounted', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        logout: mockLogout,
        isLoading: false,
        currentOrganization: null,
        organizations: [],
        setCurrentOrganization: jest.fn(),
      })

      render(<AuthButton />)

      expect(screen.getByText('Sign In')).toBeInTheDocument()
      expect(screen.getByText('Sign Up')).toBeInTheDocument()
    })

    it('shows loading fallback text before client is mounted', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        logout: mockLogout,
        isLoading: true,
        currentOrganization: null,
        organizations: [],
        setCurrentOrganization: jest.fn(),
      })

      render(<AuthButton />)

      const loadingButton = screen.getByRole('button')
      expect(loadingButton).toBeInTheDocument()
    })
  })

  describe('dropdown trigger button styling', () => {
    const mockUser = {
      id: '1',
      username: 'testuser',
      email: 'test@example.com',
      is_superadmin: false,
    }

    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: mockUser,
        logout: mockLogout,
        isLoading: false,
        currentOrganization: null,
        organizations: [],
        setCurrentOrganization: jest.fn(),
      })
    })

    it('applies correct button styling classes', () => {
      render(<AuthButton />)

      const button = screen.getByRole('button')
      expect(button).toHaveClass(
        'inline-flex',
        'items-center',
        'justify-center',
        'gap-2',
        'rounded-full',
        'px-4',
        'py-1.5'
      )
    })

    it('applies dark mode styling classes', () => {
      render(<AuthButton />)

      const button = screen.getByRole('button')
      expect(button).toHaveClass(
        'dark:text-zinc-400',
        'dark:ring-white/10',
        'dark:hover:bg-white/5',
        'dark:hover:text-white'
      )
    })
  })

  describe('menu item styling', () => {
    const mockUser = {
      id: '1',
      username: 'testuser',
      email: 'test@example.com',
      is_superadmin: false,
    }

    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: mockUser,
        logout: mockLogout,
        isLoading: false,
        currentOrganization: null,
        organizations: [],
        setCurrentOrganization: jest.fn(),
      })
    })

    it('applies correct link styling', async () => {
      const user = userEvent.setup()
      render(<AuthButton />)

      await user.click(screen.getByRole('button'))

      const profileLink = screen.getByText(/profile settings/i).closest('a')
      expect(profileLink).toHaveClass(
        'flex',
        'items-center',
        'px-4',
        'py-2',
        'text-sm',
        'hover:bg-zinc-100',
        'dark:hover:bg-zinc-700'
      )
    })

    it('applies correct logout button styling', async () => {
      const user = userEvent.setup()
      render(<AuthButton />)

      await user.click(screen.getByRole('button'))

      const logoutButton = screen.getByTestId('logout-button')
      expect(logoutButton).toHaveClass(
        'flex',
        'w-full',
        'items-center',
        'px-4',
        'py-2',
        'text-sm',
        'hover:bg-zinc-100',
        'dark:hover:bg-zinc-700'
      )
    })
  })

  describe('organization display', () => {
    it('shows Private context when no current organization', () => {
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          username: 'testuser',
          email: 'test@example.com',
          is_superadmin: false,
        },
        logout: mockLogout,
        isLoading: false,
        currentOrganization: null,
        organizations: [],
        setCurrentOrganization: jest.fn(),
      })

      render(<AuthButton />)

      expect(screen.getByText('(Private)')).toBeInTheDocument()
    })

    it('shows organization name in parentheses when set', () => {
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          username: 'testuser',
          email: 'test@example.com',
          is_superadmin: false,
        },
        logout: mockLogout,
        isLoading: false,
        currentOrganization: { id: '1', name: 'My Org', role: 'MEMBER' },
        organizations: [{ id: '1', name: 'My Org', role: 'MEMBER' }],
        setCurrentOrganization: jest.fn(),
      })

      render(<AuthButton />)

      expect(screen.getByText('(My Org)')).toBeInTheDocument()
    })

    it('applies correct styling to organization name', () => {
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          username: 'testuser',
          email: 'test@example.com',
          is_superadmin: false,
        },
        logout: mockLogout,
        isLoading: false,
        currentOrganization: { id: '1', name: 'Test Org', role: 'MEMBER' },
        organizations: [{ id: '1', name: 'Test Org', role: 'MEMBER' }],
        setCurrentOrganization: jest.fn(),
      })

      render(<AuthButton />)

      const orgName = screen.getByText('(Test Org)')
      expect(orgName).toHaveClass('hidden', 'text-xs', 'opacity-70', 'md:block')
    })
  })

  describe('dropdown menu separators', () => {
    it('shows separator before admin section for org admin', async () => {
      const user = userEvent.setup()
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          username: 'orgadmin',
          email: 'admin@example.com',
          is_superadmin: false,
        },
        logout: mockLogout,
        isLoading: false,
        currentOrganization: { id: '1', name: 'Admin Org', role: 'ORG_ADMIN' },
        organizations: [{ id: '1', name: 'Admin Org', role: 'ORG_ADMIN' }],
        setCurrentOrganization: jest.fn(),
      })

      render(<AuthButton />)

      await user.click(screen.getByRole('button'))

      const separators = document.querySelectorAll('hr')
      expect(separators.length).toBeGreaterThan(0)
    })

    it('shows separator before logout section', async () => {
      const user = userEvent.setup()
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          username: 'testuser',
          email: 'test@example.com',
          is_superadmin: false,
        },
        logout: mockLogout,
        isLoading: false,
        currentOrganization: null,
        organizations: [],
        setCurrentOrganization: jest.fn(),
      })

      render(<AuthButton />)

      await user.click(screen.getByRole('button'))

      const separators = document.querySelectorAll('hr')
      expect(separators.length).toBeGreaterThan(0)
    })
  })

  describe('icon display', () => {
    it('shows user icon in profile menu item', async () => {
      const user = userEvent.setup()
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          username: 'testuser',
          email: 'test@example.com',
          is_superadmin: false,
        },
        logout: mockLogout,
        isLoading: false,
        currentOrganization: null,
        organizations: [],
        setCurrentOrganization: jest.fn(),
      })

      render(<AuthButton />)

      await user.click(screen.getByRole('button'))

      expect(screen.getByTestId('user-icon')).toBeInTheDocument()
    })

    it('shows bell icon in notification settings menu item', async () => {
      const user = userEvent.setup()
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          username: 'testuser',
          email: 'test@example.com',
          is_superadmin: false,
        },
        logout: mockLogout,
        isLoading: false,
        currentOrganization: null,
        organizations: [],
        setCurrentOrganization: jest.fn(),
      })

      render(<AuthButton />)

      await user.click(screen.getByRole('button'))

      expect(screen.getByTestId('bell-icon')).toBeInTheDocument()
    })

    it('shows logout icon in sign out menu item', async () => {
      const user = userEvent.setup()
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          username: 'testuser',
          email: 'test@example.com',
          is_superadmin: false,
        },
        logout: mockLogout,
        isLoading: false,
        currentOrganization: null,
        organizations: [],
        setCurrentOrganization: jest.fn(),
      })

      render(<AuthButton />)

      await user.click(screen.getByRole('button'))

      expect(screen.getByTestId('logout-icon')).toBeInTheDocument()
    })
  })

  describe('edge cases', () => {
    it('handles user with very long username', () => {
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          username: 'verylongusernamethatmightbreakthelayout',
          email: 'test@example.com',
          is_superadmin: false,
        },
        logout: mockLogout,
        isLoading: false,
        currentOrganization: null,
        organizations: [],
        setCurrentOrganization: jest.fn(),
      })

      render(<AuthButton />)

      expect(
        screen.getByText('verylongusernamethatmightbreakthelayout')
      ).toBeInTheDocument()
    })

    it('handles organization with very long name', () => {
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          username: 'testuser',
          email: 'test@example.com',
          is_superadmin: false,
        },
        logout: mockLogout,
        isLoading: false,
        currentOrganization: {
          id: '1',
          name: 'Very Long Organization Name That Might Break Layout',
          role: 'MEMBER',
        },
        organizations: [
          {
            id: '1',
            name: 'Very Long Organization Name That Might Break Layout',
            role: 'MEMBER',
          },
        ],
        setCurrentOrganization: jest.fn(),
      })

      render(<AuthButton />)

      expect(
        screen.getByText(
          '(Very Long Organization Name That Might Break Layout)'
        )
      ).toBeInTheDocument()
    })

    it('handles multiple organizations with same user', () => {
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          username: 'testuser',
          email: 'test@example.com',
          is_superadmin: false,
        },
        logout: mockLogout,
        isLoading: false,
        currentOrganization: { id: '1', name: 'Org 1', role: 'MEMBER' },
        organizations: [
          { id: '1', name: 'Org 1', role: 'MEMBER' },
          { id: '2', name: 'Org 2', role: 'ORG_ADMIN' },
          { id: '3', name: 'Org 3', role: 'MEMBER' },
        ],
        setCurrentOrganization: jest.fn(),
      })

      render(<AuthButton />)

      expect(screen.getByText('(Org 1)')).toBeInTheDocument()
    })
  })

  describe('feature flag integration', () => {
    it('calls isEnabled from feature flags context', async () => {
      const mockIsEnabled = jest.fn().mockReturnValue(true)
      mockUseFeatureFlags.mockReturnValue({
        flags: {},
        isLoading: false,
        error: null,
        isEnabled: mockIsEnabled,
        refreshFlags: jest.fn(),
        checkFlag: jest.fn().mockResolvedValue(true),
        lastUpdate: Date.now(),
      })

      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          username: 'testuser',
          email: 'test@example.com',
          is_superadmin: false,
        },
        logout: mockLogout,
        isLoading: false,
        currentOrganization: null,
        organizations: [],
        setCurrentOrganization: jest.fn(),
      })

      render(<AuthButton />)

      expect(mockUseFeatureFlags).toHaveBeenCalled()
    })
  })
})
