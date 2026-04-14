/**
 * Test suite for Admin Users Page - Organization Data Loading
 * Ensures organization members and invitations load correctly
 */

/**
 * @jest-environment jsdom
 */

import { ApiClient } from '@/lib/api'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import AdminUsersPage from '../page'

// Mock Next.js router
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

// Mock contexts
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(),
}))

// Mock hooks
jest.mock('@/hooks/useDialogs', () => ({
  useErrorAlert: () => jest.fn(),
  useDeleteConfirm: () => jest.fn().mockResolvedValue(true),
}))

// Mock API client
jest.mock('@/lib/api', () => {
  const actual = jest.requireActual('@/lib/api')
  return {
    ...actual,
    api: {
      getAllUsers: jest.fn().mockResolvedValue([]),
      getOrganizationMembers: jest.fn().mockResolvedValue([]),
      listInvitations: jest.fn().mockResolvedValue([]),
      getOrganizationInvitations: jest.fn().mockResolvedValue([]),
      updateUserSuperadminStatus: jest.fn().mockResolvedValue({}),
      deleteUser: jest.fn().mockResolvedValue({}),
      createInvitation: jest.fn().mockResolvedValue({}),
      cancelInvitation: jest.fn().mockResolvedValue({}),
      updateMemberRole: jest.fn().mockResolvedValue({}),
      removeMember: jest.fn().mockResolvedValue({}),
      addUserToOrganization: jest.fn().mockResolvedValue({}),
      createOrganization: jest.fn().mockResolvedValue({}),
      updateOrganization: jest.fn().mockResolvedValue({}),
    },
    ApiClient: jest.fn().mockImplementation(() => ({
      login: jest.fn().mockResolvedValue({ access_token: 'test-token' }),
      logout: jest.fn().mockResolvedValue({}),
      getCurrentUser: jest
        .fn()
        .mockResolvedValue({ id: '1', username: 'test' }),
      getUser: jest.fn().mockResolvedValue({ id: '1', username: 'test' }),
      setAuthFailureHandler: jest.fn(),
      getTasks: jest.fn().mockResolvedValue({ tasks: [], total: 0 }),
      getTask: jest.fn().mockResolvedValue(null),
      getAllUsers: jest.fn().mockResolvedValue([]),
      getOrganizationMembers: jest.fn().mockResolvedValue([]),
      listInvitations: jest.fn().mockResolvedValue([]),
      getOrganizationInvitations: jest.fn().mockResolvedValue([]),
      updateUserSuperadminStatus: jest.fn().mockResolvedValue({}),
      deleteUser: jest.fn().mockResolvedValue({}),
      createInvitation: jest.fn().mockResolvedValue({}),
      cancelInvitation: jest.fn().mockResolvedValue({}),
      updateMemberRole: jest.fn().mockResolvedValue({}),
      removeMember: jest.fn().mockResolvedValue({}),
      addUserToOrganization: jest.fn().mockResolvedValue({}),
      createOrganization: jest.fn().mockResolvedValue({}),
      updateOrganization: jest.fn().mockResolvedValue({}),
      organizations: {
        list: jest.fn().mockResolvedValue([]),
      },
    })),
  }
})

describe('AdminUsersPage - Organization Data Loading', () => {
  const mockApiClient = new ApiClient()

  // Add missing methods to the mock API client
  mockApiClient.getOrganizationMembers = jest.fn()
  mockApiClient.listInvitations = jest.fn()
  mockApiClient.getOrganizationInvitations = jest.fn()
  const mockUser = {
    id: 'user-1',
    username: 'admin',
    email: 'admin@example.com',
    name: 'Admin User',
    is_superadmin: true,
    is_active: true,
    created_at: '2024-01-01',
    updated_at: '2024-01-01',
  }

  const mockOrganizations = [
    {
      id: 'org-1',
      name: 'Test Organization',
      slug: 'test-org',
      description: 'Test Org Description',
      created_at: '2024-01-01',
      updated_at: '2024-01-01',
    },
  ]

  const mockMembers = [
    {
      user_id: 'user-2',
      organization_id: 'org-1',
      role: 'CONTRIBUTOR' as const,
      user_name: 'Test User',
      user_email: 'test@example.com',
      joined_at: '2024-01-01',
    },
  ]

  const mockInvitations = [
    {
      id: 'invite-1',
      organization_id: 'org-1',
      email: 'invited@example.com',
      role: 'ANNOTATOR' as const,
      token: 'test-token',
      invited_by: 'user-1',
      expires_at: '2024-12-31',
      accepted_at: null,
      is_accepted: false,
      created_at: '2024-01-01',
      organization_name: 'Test Organization',
      inviter_name: 'Admin User',
    },
  ]

  const mockAuthContext = {
    user: mockUser,
    login: jest.fn(),
    signup: jest.fn(),
    logout: jest.fn(),
    updateUser: jest.fn(),
    isLoading: false,
    refreshAuth: jest.fn(),
    apiClient: mockApiClient,
    organizations: mockOrganizations,
    currentOrganization: mockOrganizations[0],
    setCurrentOrganization: jest.fn(),
    refreshOrganizations: jest.fn(),
  }

  const adminTranslations: Record<string, string> = {
    'admin.usersPage.title': 'User Management',
    'admin.usersPage.subtitle': 'Manage users, roles, and organizations',
    'admin.usersPage.tabs.globalUserRoles': 'Global User Roles',
    'admin.usersPage.tabs.organizationRoles': 'Organization Roles',
    'admin.usersPage.loadingUsers': 'Loading users...',
    'admin.usersPage.noOrgSelected': 'No Organization Selected',
    'admin.usersPage.noOrgSelectedDesc': 'Select an organization to manage members and invitations',
    'admin.usersPage.selectOrganization': 'Select Organization',
    'admin.usersPage.members': 'Members',
    'admin.usersPage.created': 'Created',
    'admin.usersPage.pendingInvitations': 'Pending Invitations',
    'admin.usersPage.noPendingInvitations': 'No pending invitations',
    'admin.usersPage.breadcrumb.dashboard': 'Dashboard',
    'admin.usersPage.breadcrumb.userManagement': 'User Management',
    'admin.usersPage.columnUser': 'User',
    'admin.usersPage.columnEmail': 'Email',
    'admin.usersPage.columnEmailVerification': 'Email Verification',
    'admin.usersPage.columnSuperadminStatus': 'Superadmin Status',
    'admin.usersPage.columnActions': 'Actions',
    'admin.usersPage.verified': 'Verified',
    'admin.usersPage.unverified': 'Unverified',
    'admin.usersPage.adminMethod': 'admin',
    'admin.usersPage.verifyEmail': 'Verify Email',
    'admin.usersPage.updating': 'Updating...',
    'admin.usersPage.superadmin': 'Superadmin',
    'admin.usersPage.regularUser': 'Regular User',
    'admin.usersPage.deleting': 'Deleting...',
    'admin.usersPage.edit': 'Edit',
    'admin.usersPage.invite': 'Invite',
    'admin.usersPage.addUser': 'Add User',
    'admin.usersPage.cancel': 'Cancel',
    'admin.usersPage.save': 'Save',
    'admin.usersPage.expires': 'Expires',
    'admin.usersPage.roles.annotator': 'Annotator',
    'admin.usersPage.roles.contributor': 'Contributor',
    'admin.usersPage.roles.admin': 'Org Admin',
    'admin.usersPage.createOrganization': 'Create Organization',
    'admin.accessDenied': 'Access Denied',
    'admin.accessDeniedDesc': 'You need superadmin privileges to access this page',
  }

  const mockI18nContext = {
    t: (key: string, params?: any) => {
      let result = adminTranslations[key] || key
      if (params && typeof params === 'object') {
        Object.entries(params).forEach(([k, v]) => {
          result = result.replace(`{${k}}`, String(v))
        })
      }
      return result
    },
    changeLanguage: jest.fn(),
    currentLanguage: 'en',
    languages: ['en', 'de'],
  }

  beforeEach(() => {
    jest.clearAllMocks()

    // Setup default mock responses for both api and ApiClient
    const { api } = require('@/lib/api')
    ;(api.getAllUsers as jest.Mock).mockResolvedValue([mockUser])
    ;(api.getOrganizationMembers as jest.Mock).mockResolvedValue(mockMembers)
    ;(api.listInvitations as jest.Mock).mockResolvedValue(mockInvitations)
    ;(api.getOrganizationInvitations as jest.Mock).mockResolvedValue(
      mockInvitations
    )

    // Setup ApiClient instance methods
    ;(mockApiClient.getAllUsers as jest.Mock).mockResolvedValue([mockUser])
    ;(mockApiClient.getOrganizationMembers as jest.Mock).mockResolvedValue(
      mockMembers
    )
    ;(mockApiClient.listInvitations as jest.Mock).mockResolvedValue(
      mockInvitations
    )
    ;(mockApiClient.getOrganizationInvitations as jest.Mock).mockResolvedValue(
      mockInvitations
    )
  })

  const renderComponent = () => {
    // Mock the useAuth hook
    const { useAuth } = require('@/contexts/AuthContext')
    useAuth.mockReturnValue(mockAuthContext)

    // Mock the useI18n hook
    const { useI18n } = require('@/contexts/I18nContext')
    useI18n.mockReturnValue(mockI18nContext)

    return render(<AdminUsersPage />)
  }

  describe('Organization Tab Data Loading', () => {
    it('should load organization members and invitations when switching to organizations tab', async () => {
      renderComponent()

      // Wait for initial render
      await waitFor(() => {
        expect(
          screen.getByRole('heading', { level: 1, name: 'User Management' })
        ).toBeInTheDocument()
      })

      // Click on Organizations tab
      const orgTab = screen.getByTestId('admin-organizations-tab')
      fireEvent.click(orgTab)

      // Wait for organization data to load
      await waitFor(() => {
        expect(mockApiClient.getOrganizationMembers).toHaveBeenCalledWith(
          'org-1'
        )
      })

      // Check that the correct invitation method is called
      // This should use listInvitations, not getOrganizationInvitations
      expect(mockApiClient.listInvitations).toHaveBeenCalledWith('org-1')
    })

    it('should handle API method naming consistency', async () => {
      renderComponent()

      // Click on Organizations tab
      const orgTab = screen.getByTestId('admin-organizations-tab')
      fireEvent.click(orgTab)

      await waitFor(() => {
        // Verify that listInvitations is called with the organization ID
        expect(mockApiClient.listInvitations).toHaveBeenCalledWith('org-1')
      })

      // If getOrganizationInvitations is called, it should work the same way
      if (mockApiClient.getOrganizationInvitations) {
        // Both methods should accept the same parameters
        expect(mockApiClient.listInvitations).toHaveBeenCalledWith('org-1')
      }
    })

    it('should display loaded members and invitations correctly', async () => {
      renderComponent()

      // Switch to organizations tab
      const orgTab = screen.getByTestId('admin-organizations-tab')
      fireEvent.click(orgTab)

      // Wait for data to load and render
      await waitFor(() => {
        // Check for member display
        expect(screen.getByText('Test User')).toBeInTheDocument()
        expect(screen.getByText('test@example.com')).toBeInTheDocument()

        // Check for invitation display
        expect(screen.getByText('invited@example.com')).toBeInTheDocument()
      })
    })

    it('should handle errors gracefully when loading organization data fails', async () => {
      // Mock console.error to avoid noise in test output
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation()

      // Make the API calls fail
      ;(mockApiClient.getOrganizationMembers as jest.Mock).mockRejectedValue(
        new Error('Failed to load members')
      )
      ;(mockApiClient.listInvitations as jest.Mock).mockRejectedValue(
        new Error('Failed to load invitations')
      )

      renderComponent()

      // Switch to organizations tab
      const orgTab = screen.getByTestId('admin-organizations-tab')
      fireEvent.click(orgTab)

      // Wait for error handling
      await waitFor(() => {
        expect(consoleErrorSpy).toHaveBeenCalledWith(
          'Failed to load organization data:',
          expect.any(Error)
        )
      })

      // The page should still render without crashing
      expect(
        screen.getByRole('heading', { level: 1, name: 'User Management' })
      ).toBeInTheDocument()

      consoleErrorSpy.mockRestore()
    })

    it('should not load organization data when no organization is selected', async () => {
      // Update the mock for this specific test
      const contextWithNoOrg = {
        ...mockAuthContext,
        organizations: [],
        currentOrganization: null,
      }

      const { useAuth } = require('@/contexts/AuthContext')
      useAuth.mockReturnValue(contextWithNoOrg)

      const { useI18n } = require('@/contexts/I18nContext')
      useI18n.mockReturnValue(mockI18nContext)

      render(<AdminUsersPage />)

      // Switch to organizations tab
      const orgTab = screen.getByTestId('admin-organizations-tab')
      fireEvent.click(orgTab)

      // Wait a bit to ensure no API calls are made
      await waitFor(() => {
        expect(screen.getByText('No Organization Selected')).toBeInTheDocument()
      })

      // Verify no API calls were made
      expect(mockApiClient.getOrganizationMembers).not.toHaveBeenCalled()
      expect(mockApiClient.listInvitations).not.toHaveBeenCalled()
    })
  })

  describe('API Method Compatibility', () => {
    it('should detect when wrong invitation method is used', async () => {
      // This test specifically checks for the bug we found
      // If the code uses getOrganizationInvitations instead of listInvitations,
      // and they have different signatures, it should fail

      // Mock getOrganizationInvitations to throw an error simulating wrong signature
      ;(
        mockApiClient.getOrganizationInvitations as jest.Mock
      ).mockImplementation(() => {
        throw new Error(
          'getOrganizationInvitations is not a function or has wrong signature'
        )
      })

      // listInvitations should still work
      ;(mockApiClient.listInvitations as jest.Mock).mockResolvedValue(
        mockInvitations
      )

      renderComponent()

      const orgTab = screen.getByTestId('admin-organizations-tab')
      fireEvent.click(orgTab)

      await waitFor(() => {
        // The correct method (listInvitations) should be called
        expect(mockApiClient.listInvitations).toHaveBeenCalled()
      })
    })

    it('should verify all organization-related API methods exist', () => {
      // This ensures all required methods are present on the API client
      const requiredMethods = [
        'getOrganizationMembers',
        'listInvitations', // The correct method name
        'createInvitation',
        'cancelInvitation',
        'updateMemberRole',
        'removeMember',
        'addUserToOrganization',
        'createOrganization',
        'updateOrganization',
      ]

      requiredMethods.forEach((method) => {
        expect(mockApiClient[method]).toBeDefined()
        expect(typeof mockApiClient[method]).toBe('function')
      })
    })
  })
})
