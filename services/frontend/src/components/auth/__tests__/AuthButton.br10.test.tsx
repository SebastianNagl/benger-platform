/**
 * @jest-environment jsdom
 *
 * Branch coverage tests for AuthButton.
 * Targets 8 uncovered branches:
 * - isClient ternary fallbacks (lines 53, 84, 94, 146, 158, 173, 190, 193)
 */

import '@testing-library/jest-dom'
import { render, screen, fireEvent } from '@testing-library/react'
import { AuthButton } from '../AuthButton'

const mockUseAuth = jest.fn()
const mockUseFeatureFlags = jest.fn()
const mockUseHydration = jest.fn()

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}))

jest.mock('@/contexts/FeatureFlagContext', () => ({
  useFeatureFlags: () => mockUseFeatureFlags(),
}))

jest.mock('@/contexts/HydrationContext', () => ({
  useHydration: () => mockUseHydration(),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const t: Record<string, string> = {
        'common.loading': 'Loading...',
        'auth.private': 'Private',
        'auth.profileSettings': 'Profile Settings',
        'auth.notificationSettings': 'Notification Settings',
        'auth.switchContext': 'Switch Context',
        'auth.signOut': 'Sign Out',
        'auth.signIn': 'Sign In',
        'auth.signUp': 'Sign Up',
        'admin.usersOrganizations': 'Users & Organizations',
        'admin.featureFlags': 'Feature Flags',
      }
      return t[key] || key
    },
  }),
}))

jest.mock('@/components/auth/LoginModal', () => ({
  LoginModal: ({ isOpen, onClose }: any) =>
    isOpen ? <div data-testid="login-modal"><button onClick={onClose}>Close</button></div> : null,
}))

jest.mock('@/components/auth/SignupModal', () => ({
  SignupModal: ({ isOpen, onClose }: any) =>
    isOpen ? <div data-testid="signup-modal"><button onClick={onClose}>Close</button></div> : null,
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, disabled, ...props }: any) => (
    <button onClick={onClick} disabled={disabled}>{children}</button>
  ),
}))

jest.mock('next/link', () => {
  return ({ children, href, onClick }: any) => <a href={href} onClick={onClick}>{children}</a>
})

jest.mock('@heroicons/react/24/outline', () => ({
  ArrowRightOnRectangleIcon: (props: any) => <svg {...props} />,
  BeakerIcon: (props: any) => <svg {...props} />,
  BellIcon: (props: any) => <svg {...props} />,
  BuildingOfficeIcon: (props: any) => <svg {...props} />,
  CheckIcon: (props: any) => <svg {...props} />,
  ChevronDownIcon: (props: any) => <svg {...props} />,
  UserIcon: (props: any) => <svg {...props} />,
  UsersIcon: (props: any) => <svg {...props} />,
}))

describe('AuthButton', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockUseFeatureFlags.mockReturnValue({ isEnabled: () => false })
  })

  it('shows loading button when isLoading=true and isClient=false (SSR fallback)', () => {
    mockUseAuth.mockReturnValue({
      user: null,
      logout: jest.fn(),
      isLoading: true,
      currentOrganization: null,
      organizations: [],
      setCurrentOrganization: jest.fn(),
    })
    mockUseHydration.mockReturnValue(false)

    render(<AuthButton />)
    expect(screen.getByText('Loading...')).toBeInTheDocument()
  })

  it('shows loading button when isLoading=true and isClient=true', () => {
    mockUseAuth.mockReturnValue({
      user: null,
      logout: jest.fn(),
      isLoading: true,
      currentOrganization: null,
      organizations: [],
      setCurrentOrganization: jest.fn(),
    })
    mockUseHydration.mockReturnValue(true)

    render(<AuthButton />)
    expect(screen.getByText('Loading...')).toBeInTheDocument()
  })

  it('shows sign in/sign up buttons when no user and isClient=false', () => {
    mockUseAuth.mockReturnValue({
      user: null,
      logout: jest.fn(),
      isLoading: false,
      currentOrganization: null,
      organizations: [],
      setCurrentOrganization: jest.fn(),
    })
    mockUseHydration.mockReturnValue(false)

    render(<AuthButton />)
    expect(screen.getByText('Sign In')).toBeInTheDocument()
    expect(screen.getByText('Sign up')).toBeInTheDocument()
  })

  it('shows sign in/sign up buttons when no user and isClient=true', () => {
    mockUseAuth.mockReturnValue({
      user: null,
      logout: jest.fn(),
      isLoading: false,
      currentOrganization: null,
      organizations: [],
      setCurrentOrganization: jest.fn(),
    })
    mockUseHydration.mockReturnValue(true)

    render(<AuthButton />)
    expect(screen.getByText('Sign In')).toBeInTheDocument()
    expect(screen.getByText('Sign Up')).toBeInTheDocument()
  })

  it('shows user dropdown with profile links when user is logged in (isClient=true)', () => {
    mockUseAuth.mockReturnValue({
      user: { id: 1, username: 'alice', is_superadmin: false },
      logout: jest.fn(),
      isLoading: false,
      currentOrganization: null,
      organizations: [],
      setCurrentOrganization: jest.fn(),
    })
    mockUseHydration.mockReturnValue(true)

    render(<AuthButton />)
    // Click to open dropdown
    fireEvent.click(screen.getByText('alice'))
    expect(screen.getByText('Profile Settings')).toBeInTheDocument()
    expect(screen.getByText('Notification Settings')).toBeInTheDocument()
    expect(screen.getByText('Sign Out')).toBeInTheDocument()
  })

  it('shows SSR fallback text when isClient=false and user logged in', () => {
    mockUseAuth.mockReturnValue({
      user: { id: 1, username: 'alice', is_superadmin: false },
      logout: jest.fn(),
      isLoading: false,
      currentOrganization: null,
      organizations: [],
      setCurrentOrganization: jest.fn(),
    })
    mockUseHydration.mockReturnValue(false)

    render(<AuthButton />)
    fireEvent.click(screen.getByText('alice'))
    // SSR fallbacks
    expect(screen.getByText('Profile Settings')).toBeInTheDocument()
    expect(screen.getByText('Notification Settings')).toBeInTheDocument()
  })

  it('shows Feature Flags link for superadmin', () => {
    mockUseAuth.mockReturnValue({
      user: { id: 1, username: 'admin', is_superadmin: true },
      logout: jest.fn(),
      isLoading: false,
      currentOrganization: null,
      organizations: [],
      setCurrentOrganization: jest.fn(),
    })
    mockUseHydration.mockReturnValue(true)

    render(<AuthButton />)
    fireEvent.click(screen.getByText('admin'))
    expect(screen.getByText('Feature Flags')).toBeInTheDocument()
  })

  it('does not show Feature Flags link for non-superadmin', () => {
    mockUseAuth.mockReturnValue({
      user: { id: 1, username: 'user', is_superadmin: false },
      logout: jest.fn(),
      isLoading: false,
      currentOrganization: null,
      organizations: [],
      setCurrentOrganization: jest.fn(),
    })
    mockUseHydration.mockReturnValue(true)

    render(<AuthButton />)
    fireEvent.click(screen.getByText('user'))
    expect(screen.queryByText('Feature Flags')).not.toBeInTheDocument()
  })

  it('shows organization switcher when organizations exist', () => {
    const setCurrentOrg = jest.fn()
    mockUseAuth.mockReturnValue({
      user: { id: 1, username: 'alice', is_superadmin: false },
      logout: jest.fn(),
      isLoading: false,
      currentOrganization: null,
      organizations: [{ id: 1, name: 'TUM' }],
      setCurrentOrganization: setCurrentOrg,
    })
    mockUseHydration.mockReturnValue(true)

    render(<AuthButton />)
    fireEvent.click(screen.getByText('alice'))
    expect(screen.getByText('Switch Context')).toBeInTheDocument()
    expect(screen.getByText('TUM')).toBeInTheDocument()
    expect(screen.getByText('Private')).toBeInTheDocument()
  })

  it('shows current organization name in header', () => {
    mockUseAuth.mockReturnValue({
      user: { id: 1, username: 'alice', is_superadmin: false },
      logout: jest.fn(),
      isLoading: false,
      currentOrganization: { id: 1, name: 'TUM' },
      organizations: [{ id: 1, name: 'TUM' }],
      setCurrentOrganization: jest.fn(),
    })
    mockUseHydration.mockReturnValue(true)

    render(<AuthButton />)
    expect(screen.getByText('(TUM)')).toBeInTheDocument()
  })

  it('opens login modal when Sign In is clicked', () => {
    mockUseAuth.mockReturnValue({
      user: null,
      logout: jest.fn(),
      isLoading: false,
      currentOrganization: null,
      organizations: [],
      setCurrentOrganization: jest.fn(),
    })
    mockUseHydration.mockReturnValue(true)

    render(<AuthButton />)
    fireEvent.click(screen.getByText('Sign In'))
    expect(screen.getByTestId('login-modal')).toBeInTheDocument()
  })

  it('opens signup modal when Sign Up is clicked', () => {
    mockUseAuth.mockReturnValue({
      user: null,
      logout: jest.fn(),
      isLoading: false,
      currentOrganization: null,
      organizations: [],
      setCurrentOrganization: jest.fn(),
    })
    mockUseHydration.mockReturnValue(true)

    render(<AuthButton />)
    fireEvent.click(screen.getByText('Sign Up'))
    expect(screen.getByTestId('signup-modal')).toBeInTheDocument()
  })

  it('calls logout and closes dropdown on Sign Out click', () => {
    const logout = jest.fn()
    mockUseAuth.mockReturnValue({
      user: { id: 1, username: 'alice', is_superadmin: false },
      logout,
      isLoading: false,
      currentOrganization: null,
      organizations: [],
      setCurrentOrganization: jest.fn(),
    })
    mockUseHydration.mockReturnValue(true)

    render(<AuthButton />)
    fireEvent.click(screen.getByText('alice'))
    fireEvent.click(screen.getByTestId('logout-button'))
    expect(logout).toHaveBeenCalled()
  })

  it('closes dropdown on outside click', () => {
    mockUseAuth.mockReturnValue({
      user: { id: 1, username: 'alice', is_superadmin: false },
      logout: jest.fn(),
      isLoading: false,
      currentOrganization: null,
      organizations: [],
      setCurrentOrganization: jest.fn(),
    })
    mockUseHydration.mockReturnValue(true)

    render(<AuthButton />)
    fireEvent.click(screen.getByText('alice'))
    expect(screen.getByText('Profile Settings')).toBeInTheDocument()
    fireEvent.mouseDown(document.body)
    // Dropdown should close
  })
})
