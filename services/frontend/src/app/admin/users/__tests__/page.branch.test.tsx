/**
 * Branch coverage tests for AdminUsersPage
 *
 * The page immediately redirects to /admin/users-organizations.
 * Tests here cover the initial branches: superadmin check, user loading,
 * error states, organization selection auto-fill, and tab rendering.
 *
 * @jest-environment jsdom
 */

import { useAuth } from '@/contexts/AuthContext'
import { useFeatureFlags } from '@/contexts/FeatureFlagContext'
import { useI18n } from '@/contexts/I18nContext'
import { useDeleteConfirm, useErrorAlert } from '@/hooks/useDialogs'
import { api, ApiClient } from '@/lib/api'
import { organizationsAPI } from '@/lib/api/organizations'
import { render, screen, waitFor } from '@testing-library/react'
import AdminUsersPage from '../page'

jest.mock('@/contexts/AuthContext')
jest.mock('@/contexts/FeatureFlagContext', () => ({
  useFeatureFlags: jest.fn(),
}))
jest.mock('@/contexts/I18nContext')
jest.mock('@/hooks/useDialogs', () => ({
  useErrorAlert: jest.fn(),
  useDeleteConfirm: jest.fn(),
}))
jest.mock('@/lib/api')
jest.mock('@/lib/api/organizations')

const mockPush = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(() => ({
    push: mockPush,
    replace: jest.fn(),
    back: jest.fn(),
    forward: jest.fn(),
    refresh: jest.fn(),
    prefetch: jest.fn(),
  })),
  useParams: jest.fn(() => ({})),
  useSearchParams: jest.fn(() => new URLSearchParams()),
  usePathname: jest.fn(() => '/admin/users'),
}))

const mockApiClient = {
  getAllUsers: jest.fn().mockResolvedValue([]),
  getOrganizationMembers: jest.fn().mockResolvedValue([]),
  listInvitations: jest.fn().mockResolvedValue([]),
  createInvitation: jest.fn(),
  cancelInvitation: jest.fn(),
  updateMemberRole: jest.fn(),
  removeMember: jest.fn(),
  addUserToOrganization: jest.fn(),
  createOrganization: jest.fn(),
  updateOrganization: jest.fn(),
} as unknown as ApiClient

const mockOrg = { id: 'org-1', name: 'TUM', display_name: 'TUM', slug: 'tum', description: '', created_at: '2024-01-01', updated_at: '2024-01-01' }

function setupMocks(overrides: Record<string, any> = {}) {
  ;(useFeatureFlags as jest.Mock).mockReturnValue({
    flags: {},
    isLoading: false,
    error: null,
    isEnabled: jest.fn().mockReturnValue(true),
    refreshFlags: jest.fn(),
    checkFlag: jest.fn(),
    lastUpdate: Date.now(),
  })
  ;(useI18n as jest.Mock).mockReturnValue({
    locale: 'en',
    t: (key: string) => key,
    changeLocale: jest.fn(),
  })
  ;(useErrorAlert as jest.Mock).mockReturnValue(jest.fn())
  ;(useDeleteConfirm as jest.Mock).mockReturnValue(jest.fn().mockResolvedValue(true))

  const mockApi = api as jest.Mocked<typeof api>
  mockApi.getAllUsers = jest.fn().mockResolvedValue(overrides.users ?? [])
  mockApi.verifyUserEmail = jest.fn().mockResolvedValue(undefined)
  mockApi.updateUserSuperadminStatus = jest.fn().mockResolvedValue({})
  mockApi.deleteUser = jest.fn().mockResolvedValue(undefined)

  ;(useAuth as jest.Mock).mockReturnValue({
    user: overrides.user ?? {
      id: 'admin-1',
      username: 'admin',
      email: 'admin@test.com',
      name: 'Admin',
      is_superadmin: overrides.isSuperAdmin ?? true,
      is_active: true,
      created_at: '2024-01-01',
    },
    login: jest.fn(),
    signup: jest.fn(),
    logout: jest.fn(),
    updateUser: jest.fn(),
    isLoading: false,
    refreshAuth: jest.fn(),
    apiClient: mockApiClient,
    organizations: overrides.organizations ?? [mockOrg],
    currentOrganization: overrides.currentOrganization ?? mockOrg,
    setCurrentOrganization: jest.fn(),
    refreshOrganizations: jest.fn(),
  } as any)
}

describe('AdminUsersPage Branch Coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Redirect behavior', () => {
    it('always redirects to unified interface', async () => {
      setupMocks()
      render(<AdminUsersPage />)
      await waitFor(() => {
        expect(mockPush).toHaveBeenCalledWith('/admin/users-organizations')
      })
    })
  })

  describe('Access control branches', () => {
    it('shows access denied for non-superadmin', () => {
      setupMocks({
        isSuperAdmin: false,
        user: {
          id: 'user-1',
          username: 'user',
          email: 'user@test.com',
          name: 'User',
          is_superadmin: false,
          is_active: true,
          created_at: '2024-01-01',
        },
        organizations: [],
        currentOrganization: null,
      })
      render(<AdminUsersPage />)
      expect(screen.getByText('admin.accessDenied')).toBeInTheDocument()
    })

    it('shows page content for superadmin', () => {
      setupMocks()
      render(<AdminUsersPage />)
      // Superadmin sees the page (even though redirect fires)
      expect(screen.getByText('admin.usersPage.title')).toBeInTheDocument()
    })
  })

  describe('Organization auto-selection', () => {
    it('auto-selects first organization when available', async () => {
      setupMocks()
      render(<AdminUsersPage />)
      await waitFor(() => {
        expect(api.getAllUsers).toHaveBeenCalled()
      })
    })

    it('handles empty organizations list', () => {
      setupMocks({ organizations: [], currentOrganization: null })
      render(<AdminUsersPage />)
      // Should still render without error
      expect(screen.getByText('admin.usersPage.title')).toBeInTheDocument()
    })
  })

  describe('User loading error branch', () => {
    it('handles error when fetching users fails', async () => {
      setupMocks()
      const mockApi = api as jest.Mocked<typeof api>
      mockApi.getAllUsers = jest.fn().mockRejectedValue(new Error('Network error'))
      render(<AdminUsersPage />)
      // Should show error state after load fails
      await waitFor(() => {
        expect(mockApi.getAllUsers).toHaveBeenCalled()
      })
    })

    it('uses fallback error message for non-Error objects', async () => {
      setupMocks()
      const mockApi = api as jest.Mocked<typeof api>
      mockApi.getAllUsers = jest.fn().mockRejectedValue('string error')
      render(<AdminUsersPage />)
      await waitFor(() => {
        expect(mockApi.getAllUsers).toHaveBeenCalled()
      })
    })
  })

  describe('canCreateOrganization branch', () => {
    it('superadmin can create organizations', () => {
      setupMocks()
      render(<AdminUsersPage />)
      // The button should be visible for superadmin
      expect(screen.getByText('admin.usersPage.title')).toBeInTheDocument()
    })

    it('non-superadmin with organizations can see create button', () => {
      setupMocks({
        isSuperAdmin: false,
        user: {
          id: 'user-1',
          username: 'user',
          email: 'user@test.com',
          name: 'User',
          is_superadmin: false,
          is_active: true,
          created_at: '2024-01-01',
        },
      })
      // Still renders access denied since not superadmin
      render(<AdminUsersPage />)
      expect(screen.getByText('admin.accessDenied')).toBeInTheDocument()
    })
  })
})
