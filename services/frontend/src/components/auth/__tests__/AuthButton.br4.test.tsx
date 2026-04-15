/**
 * @jest-environment jsdom
 *
 * Branch coverage: AuthButton.tsx
 * Targets: L108-109 (setCurrentOrganization null), L123-124 (org check icon),
 *          L155 (superadmin feature flags link), L199-204 (signup modal)
 */

import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const mockLogout = jest.fn()
const mockSetCurrentOrganization = jest.fn()

let mockUser: any = null
let mockOrganizations: any[] = []
let mockCurrentOrganization: any = null

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: mockUser,
    logout: mockLogout,
    isLoading: false,
    currentOrganization: mockCurrentOrganization,
    organizations: mockOrganizations,
    setCurrentOrganization: mockSetCurrentOrganization,
  }),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'auth.signIn': 'Sign In',
        'auth.signUp': 'Sign Up',
        'auth.signOut': 'Sign Out',
        'auth.profileSettings': 'Profile Settings',
        'auth.notificationSettings': 'Notification Settings',
        'auth.switchContext': 'Switch Context',
        'auth.private': 'Private',
        'admin.usersOrganizations': 'Users & Organizations',
        'admin.featureFlags': 'Feature Flags',
        'common.loading': 'Loading...',
      }
      return translations[key] || key
    },
  }),
}))

jest.mock('@/contexts/FeatureFlagContext', () => ({
  useFeatureFlags: () => ({ isEnabled: jest.fn(() => false) }),
}))

jest.mock('@/contexts/HydrationContext', () => ({
  useHydration: () => true,
}))

jest.mock('@/components/auth/LoginModal', () => ({
  LoginModal: ({ isOpen, onClose }: any) =>
    isOpen ? <div data-testid="login-modal"><button onClick={onClose}>Close Login</button></div> : null,
}))

jest.mock('@/components/auth/SignupModal', () => ({
  SignupModal: ({ isOpen, onClose }: any) =>
    isOpen ? <div data-testid="signup-modal"><button onClick={onClose}>Close Signup</button></div> : null,
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, disabled, ...props }: any) => (
    <button onClick={onClick} disabled={disabled} {...props}>{children}</button>
  ),
}))

import { AuthButton } from '../AuthButton'

describe('AuthButton br4 - uncovered branches', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockUser = null
    mockOrganizations = []
    mockCurrentOrganization = null
  })

  it('shows sign in and sign up buttons when no user', () => {
    render(<AuthButton />)
    expect(screen.getByText('Sign In')).toBeInTheDocument()
    expect(screen.getByText('Sign Up')).toBeInTheDocument()
  })

  it('opens signup modal on click (line 192, 199-204)', async () => {
    const user = userEvent.setup()
    render(<AuthButton />)

    await user.click(screen.getByText('Sign Up'))
    expect(screen.getByTestId('signup-modal')).toBeInTheDocument()
  })

  it('opens login modal on click', async () => {
    const user = userEvent.setup()
    render(<AuthButton />)

    await user.click(screen.getByText('Sign In'))
    expect(screen.getByTestId('login-modal')).toBeInTheDocument()
  })

  it('shows dropdown with org switcher when user has orgs', async () => {
    mockUser = { id: 1, username: 'testuser', is_superadmin: false }
    mockOrganizations = [
      { id: 'org-1', name: 'TUM' },
      { id: 'org-2', name: 'LMU' },
    ]
    mockCurrentOrganization = { id: 'org-1', name: 'TUM' }

    const user = userEvent.setup()
    render(<AuthButton />)

    // Open dropdown
    await user.click(screen.getByText('testuser'))

    expect(screen.getByText('Switch Context')).toBeInTheDocument()
    expect(screen.getByText('Private')).toBeInTheDocument()
    expect(screen.getByText('TUM')).toBeInTheDocument()
    expect(screen.getByText('LMU')).toBeInTheDocument()
  })

  it('switches to private context (setCurrentOrganization(null), line 108-109)', async () => {
    mockUser = { id: 1, username: 'testuser', is_superadmin: false }
    mockOrganizations = [{ id: 'org-1', name: 'TUM' }]
    mockCurrentOrganization = { id: 'org-1', name: 'TUM' }

    const user = userEvent.setup()
    render(<AuthButton />)

    await user.click(screen.getByText('testuser'))
    await user.click(screen.getByText('Private'))

    expect(mockSetCurrentOrganization).toHaveBeenCalledWith(null)
  })

  it('switches to specific org (line 123-124)', async () => {
    mockUser = { id: 1, username: 'testuser', is_superadmin: false }
    mockOrganizations = [
      { id: 'org-1', name: 'TUM' },
      { id: 'org-2', name: 'LMU' },
    ]
    mockCurrentOrganization = null

    const user = userEvent.setup()
    render(<AuthButton />)

    await user.click(screen.getByText('testuser'))
    await user.click(screen.getByText('TUM'))

    expect(mockSetCurrentOrganization).toHaveBeenCalledWith({
      id: 'org-1',
      name: 'TUM',
    })
  })

  it('shows feature flags link for superadmin (line 155)', async () => {
    mockUser = { id: 1, username: 'admin', is_superadmin: true }
    mockOrganizations = []

    const user = userEvent.setup()
    render(<AuthButton />)

    await user.click(screen.getByText('admin'))
    expect(screen.getByText('Feature Flags')).toBeInTheDocument()
  })

  it('hides feature flags link for non-superadmin (line 151 false)', async () => {
    mockUser = { id: 1, username: 'regular', is_superadmin: false }
    mockOrganizations = []

    const user = userEvent.setup()
    render(<AuthButton />)

    await user.click(screen.getByText('regular'))
    expect(screen.queryByText('Feature Flags')).not.toBeInTheDocument()
  })

  it('calls logout on sign out click', async () => {
    mockUser = { id: 1, username: 'testuser', is_superadmin: false }
    mockOrganizations = []

    const user = userEvent.setup()
    render(<AuthButton />)

    await user.click(screen.getByText('testuser'))
    await user.click(screen.getByText('Sign Out'))

    expect(mockLogout).toHaveBeenCalled()
  })

  it('closes dropdown on outside click', async () => {
    mockUser = { id: 1, username: 'testuser', is_superadmin: false }
    mockOrganizations = []

    const user = userEvent.setup()
    render(
      <div>
        <div data-testid="outside">Outside</div>
        <AuthButton />
      </div>
    )

    await user.click(screen.getByText('testuser'))
    expect(screen.getByText('Profile Settings')).toBeInTheDocument()

    await user.click(screen.getByTestId('outside'))
    expect(screen.queryByText('Profile Settings')).not.toBeInTheDocument()
  })
})
