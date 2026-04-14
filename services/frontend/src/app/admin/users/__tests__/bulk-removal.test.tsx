/**
 * @jest-environment jsdom
 */

import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import AdminUsersPage from '../page'

// Mock modules
jest.mock('@/contexts/AuthContext')
jest.mock('@/contexts/I18nContext')
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

describe('AdminUsersPage - Bulk Operations Removal', () => {
  beforeEach(() => {
    // Clear all mocks before each test
    jest.clearAllMocks()

    const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>
    mockUseAuth.mockReturnValue({
      user: {
        id: '1',
        username: 'admin',
        role: 'superadmin',
        is_superadmin: true,
      } as any,
      login: jest.fn(),
      signup: jest.fn(),
      logout: jest.fn(),
      updateUser: jest.fn(),
      isLoading: false,
      refreshAuth: jest.fn(),
      apiClient: {
        getAllUsers: jest.fn().mockResolvedValue([
          {
            id: 'user-1',
            username: 'testuser1',
            email: 'test1@example.com',
            name: 'Test User 1',
            is_superadmin: false,
            is_active: true,
            created_at: '2024-01-01',
            updated_at: '2024-01-01',
          },
        ]),
        getOrganizationMembers: jest.fn().mockResolvedValue([]),
        listInvitations: jest.fn().mockResolvedValue([]),
        updateUserSuperadminStatus: jest.fn().mockResolvedValue({}),
        deleteUser: jest.fn().mockResolvedValue({}),
      } as any,
      organizations: [],
      currentOrganization: null,
      setCurrentOrganization: jest.fn(),
      refreshOrganizations: jest.fn(),
    })

    const mockUseI18n = useI18n as jest.MockedFunction<typeof useI18n>
    const adminTranslations: Record<string, string> = {
      'admin.usersPage.title': 'User Management',
      'admin.usersPage.subtitle': 'Manage users, roles, and organizations',
      'admin.usersPage.tabs.globalUserRoles': 'Global User Roles',
      'admin.usersPage.tabs.organizationRoles': 'Organization Roles',
      'admin.usersPage.loadingUsers': 'Loading users...',
      'admin.usersPage.noOrgSelected': 'No Organization Selected',
      'admin.usersPage.noOrgSelectedDesc': 'Select an organization to manage',
      'admin.usersPage.selectOrganization': 'Select Organization',
      'admin.usersPage.breadcrumb.dashboard': 'Dashboard',
      'admin.usersPage.breadcrumb.userManagement': 'User Management',
      'admin.usersPage.columnUser': 'User',
      'admin.usersPage.columnEmail': 'Email',
      'admin.usersPage.columnEmailVerification': 'Email Verification',
      'admin.usersPage.columnSuperadminStatus': 'Superadmin Status',
      'admin.usersPage.columnActions': 'Actions',
      'admin.usersPage.verified': 'Verified',
      'admin.usersPage.unverified': 'Unverified',
      'admin.usersPage.superadmin': 'Superadmin',
      'admin.usersPage.regularUser': 'Regular User',
    }
    mockUseI18n.mockReturnValue({
      locale: 'en',
      t: ((key: string, params?: any) => {
        let result = adminTranslations[key] || key
        if (params && typeof params === 'object') {
          Object.entries(params).forEach(([k, v]: [string, any]) => {
            result = result.replace(`{${k}}`, String(v))
          })
        }
        return result
      }) as any,
      changeLocale: jest.fn(),
    } as any)
  })

  it('should not render bulk operations tab', async () => {
    render(<AdminUsersPage />)

    // Check that the page h1 title exists
    const pageTitle = screen.getByRole('heading', { name: 'User Management' })
    expect(pageTitle).toBeInTheDocument()

    // Check that organization roles tab exists
    const organizationRolesTab = screen.getByText('Organization Roles')
    expect(organizationRolesTab).toBeInTheDocument()

    // Check that bulk operations tab doesn't exist
    const bulkOperationsTab = screen.queryByText('Bulk Operations')
    expect(bulkOperationsTab).not.toBeInTheDocument()
  })

  it('should only allow switching between users and organizations tabs', async () => {
    const user = userEvent.setup()
    render(<AdminUsersPage />)

    const organizationRolesTab = screen.getByText('Organization Roles')
    await user.click(organizationRolesTab)

    // Should not show any bulk operations content
    const bulkContent = screen.queryByText(/bulk operations/i)
    expect(bulkContent).not.toBeInTheDocument()
  })

  it('should not import BulkUserManagement component', () => {
    // This test verifies that the component file import has been removed
    // by checking that attempting to use it would fail
    const moduleContent = require('../page').default.toString()
    expect(moduleContent).not.toContain('BulkUserManagement')
  })
})
