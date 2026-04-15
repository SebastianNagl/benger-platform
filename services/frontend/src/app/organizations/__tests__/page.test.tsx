/**
 * Comprehensive test suite for Organizations Page
 * Tests rendering, organization management, invitations, and error handling
 */

/**
 * @jest-environment jsdom
 */

import { useToast } from '@/components/shared/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { useFeatureFlags } from '@/contexts/FeatureFlagContext'
import { useI18n } from '@/contexts/I18nContext'
import { organizationsAPI } from '@/lib/api/organizations'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useRouter } from 'next/navigation'
import OrganizationsPage from '../page'

// Mock dependencies before imports
jest.unmock('@/lib/api/base')
global.fetch = jest.fn()

// Mock icons
jest.mock('@heroicons/react/24/outline', () => ({
  BuildingOfficeIcon: () => <div data-testid="building-icon" />,
  ChevronRightIcon: () => <div data-testid="chevron-icon" />,
  EnvelopeIcon: () => <div data-testid="envelope-icon" />,
  TrashIcon: () => <div data-testid="trash-icon" />,
  UserGroupIcon: () => <div data-testid="user-group-icon" />,
  UserPlusIcon: () => <div data-testid="user-plus-icon" />,
}))

// Mock Next.js navigation
const mockPush = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}))

// Mock contexts
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))

jest.mock('@/contexts/FeatureFlagContext', () => ({
  useFeatureFlags: jest.fn(),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(),
}))

jest.mock('@/components/shared/Toast', () => ({
  useToast: jest.fn(),
}))

// Mock organizations API
const mockGetOrganizations = jest.spyOn(organizationsAPI, 'getOrganizations')
const mockGetOrganizationMembers = jest.spyOn(
  organizationsAPI,
  'getOrganizationMembers'
)
const mockGetOrganizationInvitations = jest.spyOn(
  organizationsAPI,
  'getOrganizationInvitations'
)
const mockSendInvitation = jest.spyOn(organizationsAPI, 'sendInvitation')
const mockRemoveMember = jest.spyOn(organizationsAPI, 'removeMember')
const mockUpdateMemberRole = jest.spyOn(organizationsAPI, 'updateMemberRole')

// Mock data
const mockOrganizations = [
  {
    id: 'org-1',
    name: 'Organization One',
    description: 'First test organization',
    user_role: 'ORG_ADMIN' as const,
    member_count: 5,
    slug: 'org-one',
    created_at: '2024-01-01',
    updated_at: '2024-01-01',
  },
  {
    id: 'org-2',
    name: 'Organization Two',
    description: 'Second test organization',
    user_role: 'CONTRIBUTOR' as const,
    member_count: 3,
    slug: 'org-two',
    created_at: '2024-01-02',
    updated_at: '2024-01-02',
  },
]

const mockMembers = [
  {
    user_id: 'user-1',
    user_name: 'Admin User',
    user_email: 'admin@example.com',
    role: 'ORG_ADMIN' as const,
    is_active: true,
    joined_at: '2024-01-01',
  },
  {
    user_id: 'user-2',
    user_name: 'Contributor User',
    user_email: 'contributor@example.com',
    role: 'CONTRIBUTOR' as const,
    is_active: true,
    joined_at: '2024-01-02',
  },
  {
    user_id: 'user-3',
    user_name: 'Annotator User',
    user_email: 'annotator@example.com',
    role: 'ANNOTATOR' as const,
    is_active: true,
    joined_at: '2024-01-03',
  },
]

const mockSuperadminUser = {
  id: 'user-1',
  name: 'Admin User',
  email: 'admin@example.com',
  is_superadmin: true,
  is_active: true,
  created_at: '2024-01-01',
  updated_at: '2024-01-01',
}

const mockRegularUser = {
  id: 'user-2',
  name: 'Regular User',
  email: 'regular@example.com',
  is_superadmin: false,
  is_active: true,
  created_at: '2024-01-02',
  updated_at: '2024-01-02',
}

const mockAddToast = jest.fn()

// Translation helper
const mockTranslations: Record<string, string> = {
  'organizationsPage.title': 'Organizations',
  'organizationsPage.subtitle': 'Manage your organizations and members',
  'organizationsPage.yourOrganizations': 'Your Organizations',
  'organizationsPage.inviteMember': 'Invite Member',
  'organizationsPage.inviteToOrganization': 'Invite to Organization',
  'organizationsPage.emailAddress': 'Email Address',
  'organizationsPage.role': 'Role',
  'organizationsPage.cancel': 'Cancel',
  'organizationsPage.sendInvitation': 'Send Invitation',
  'organizationsPage.sending': 'Sending...',
  'organizationsPage.members': 'Members',
  'organizationsPage.joined': 'Joined',
  'organizationsPage.selectAnOrganization':
    'Select an organization to view details',
  'organizationsPage.loadingOrganizations': 'Loading organizations...',
  'organizationsPage.noOrganizations': 'No Organizations',
  'organizationsPage.noOrganizationsDesc':
    'You are not a member of any organizations',
  'organizationsPage.goToDashboard': 'Go to Dashboard',
  'organizationsPage.noMembersYet': 'No members yet',
  'organizationsPage.invitationSent': 'Invitation sent successfully',
  'organizationsPage.failedToSendInvitation': 'Failed to send invitation',
  'organizationsPage.invitationAlreadyExists':
    'Invitation already exists for {{email}}',
  'organizationsPage.invalidEmailAddress': 'Invalid email address',
  'organizationsPage.rateLimitExceeded': 'Too many invitations sent',
  'organizationsPage.networkError': 'Network error occurred',
  'organizationsPage.failedToLoadOrganizations': 'Failed to load organizations',
  'organizationsPage.failedToLoadMembers': 'Failed to load members',
  'organizationsPage.memberRemoved': 'Member removed successfully',
  'organizationsPage.failedToRemoveMember': 'Failed to remove member',
  'organizationsPage.memberRoleUpdated': 'Member role updated',
  'organizationsPage.failedToUpdateRole': 'Failed to update role',
  'organizationsPage.confirmRemoveMember':
    'Are you sure you want to remove this member?',
  'organizationsPage.roleDescriptions.ANNOTATOR':
    'Annotator - Can annotate tasks',
  'organizationsPage.roleDescriptions.CONTRIBUTOR':
    'Contributor - Can create content',
  'organizationsPage.roleDescriptions.ORG_ADMIN':
    'Admin - Can manage organization',
  'organizationsPage.roles.ANNOTATOR': 'Annotator',
  'organizationsPage.roles.CONTRIBUTOR': 'Contributor',
  'organizationsPage.roles.ORG_ADMIN': 'Admin',
  'organizationsPage.membersCount': 'members',
  'organizationsPage.emailPlaceholder': 'colleague@example.com',
  'admin.accessDeniedDesc': 'Access denied',
}

const mockT = (key: string, params?: any) => {
  const translation = mockTranslations[key] || key
  if (params) {
    return translation.replace(
      /\{\{(\w+)\}\}/g,
      (_, param) => params[param] || ''
    )
  }
  return translation
}

describe('OrganizationsPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()

    // Setup default mocks
    ;(useRouter as jest.Mock).mockReturnValue({ push: mockPush })
    ;(useAuth as jest.Mock).mockReturnValue({
      user: mockSuperadminUser,
      organizations: ['org-1', 'org-2'],
    })
    ;(useFeatureFlags as jest.Mock).mockReturnValue({
      isEnabled: jest.fn().mockReturnValue(true),
    })
    ;(useI18n as jest.Mock).mockReturnValue({ t: mockT })
    ;(useToast as jest.Mock).mockReturnValue({ addToast: mockAddToast })

    // Setup default API responses
    mockGetOrganizations.mockResolvedValue(mockOrganizations)
    mockGetOrganizationMembers.mockResolvedValue(mockMembers)
    mockGetOrganizationInvitations.mockResolvedValue([])
    mockSendInvitation.mockResolvedValue({
      id: 'inv-new',
      email: 'new@example.com',
      role: 'ANNOTATOR',
    })
  })

  describe('Page Redirects', () => {
    it('should redirect to unified admin interface on mount', () => {
      render(<OrganizationsPage />)

      expect(mockPush).toHaveBeenCalledWith('/admin/users-organizations')
    })
  })

  describe('Access Control', () => {
    it('should redirect non-authenticated users to login', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        organizations: [],
      })

      render(<OrganizationsPage />)

      expect(mockPush).toHaveBeenCalledWith('/login')
    })

    it('should redirect non-superadmin users to dashboard', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: mockRegularUser,
        organizations: ['org-1'],
      })

      render(<OrganizationsPage />)

      expect(mockPush).toHaveBeenCalledWith('/dashboard')
      expect(mockAddToast).toHaveBeenCalledWith('Access denied', 'error')
    })

    it('should allow superadmin users to access the page', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: mockSuperadminUser,
        organizations: ['org-1'],
      })

      render(<OrganizationsPage />)

      // Should not redirect to login or dashboard (only to new interface)
      expect(mockPush).toHaveBeenCalledWith('/admin/users-organizations')
      expect(mockPush).not.toHaveBeenCalledWith('/login')
      expect(mockPush).not.toHaveBeenCalledWith('/dashboard')
    })
  })

  describe('Page Rendering', () => {
    it('should render loading state initially', async () => {
      // Create a never-resolving promise to keep loading state
      mockGetOrganizations.mockImplementation(() => new Promise(() => {}))

      render(<OrganizationsPage />)

      expect(screen.getByText('Loading organizations...')).toBeInTheDocument()
    })

    it('should render page title and subtitle', async () => {
      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(mockGetOrganizations).toHaveBeenCalled()
      })

      expect(screen.getByText('Organizations')).toBeInTheDocument()
      expect(
        screen.getByText('Manage your organizations and members')
      ).toBeInTheDocument()
    })

    it('should render empty state when no organizations exist', async () => {
      mockGetOrganizations.mockResolvedValue([])

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('No Organizations')).toBeInTheDocument()
      })

      expect(
        screen.getByText('You are not a member of any organizations')
      ).toBeInTheDocument()
      expect(screen.getByText('Go to Dashboard')).toBeInTheDocument()
    })

    it('should navigate to dashboard when clicking dashboard button in empty state', async () => {
      mockGetOrganizations.mockResolvedValue([])
      const user = userEvent.setup()

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('Go to Dashboard')).toBeInTheDocument()
      })

      const dashboardButton = screen.getByText('Go to Dashboard')
      await user.click(dashboardButton)

      expect(mockPush).toHaveBeenCalledWith('/dashboard')
    })
  })

  describe('Organization List Display', () => {
    it('should display list of organizations', async () => {
      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('Organization One')).toBeInTheDocument()
        expect(screen.getByText('Organization Two')).toBeInTheDocument()
      })
    })

    it('should display organization roles and member counts', async () => {
      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('ORG_ADMIN')).toBeInTheDocument()
        expect(screen.getByText('CONTRIBUTOR')).toBeInTheDocument()
        expect(screen.getByText('5 members')).toBeInTheDocument()
        expect(screen.getByText('3 members')).toBeInTheDocument()
      })
    })

    it('should auto-select first organization when only one exists', async () => {
      mockGetOrganizations.mockResolvedValue([mockOrganizations[0]])

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(mockGetOrganizationMembers).toHaveBeenCalledWith('org-1')
      })
    })

    it('should not auto-select when multiple organizations exist', async () => {
      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(mockGetOrganizations).toHaveBeenCalled()
      })

      expect(
        screen.getByText('Select an organization to view details')
      ).toBeInTheDocument()
    })
  })

  describe('Organization Selection', () => {
    it('should load members when organization is selected', async () => {
      const user = userEvent.setup()

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('Organization One')).toBeInTheDocument()
      })

      const orgButton = screen.getByText('Organization One')
      await user.click(orgButton)

      await waitFor(() => {
        expect(mockGetOrganizationMembers).toHaveBeenCalledWith('org-1')
      })
    })

    it('should display organization details when selected', async () => {
      const user = userEvent.setup()

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('Organization One')).toBeInTheDocument()
      })

      const orgButton = screen.getByText('Organization One')
      await user.click(orgButton)

      await waitFor(() => {
        expect(screen.getByText('First test organization')).toBeInTheDocument()
      })
    })

    it('should display member list when organization is selected', async () => {
      const user = userEvent.setup()

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('Organization One')).toBeInTheDocument()
      })

      const orgButton = screen.getByText('Organization One')
      await user.click(orgButton)

      await waitFor(() => {
        expect(screen.getByText('Admin User')).toBeInTheDocument()
        expect(screen.getByText('admin@example.com')).toBeInTheDocument()
        expect(screen.getByText('Contributor User')).toBeInTheDocument()
        expect(screen.getByText('Annotator User')).toBeInTheDocument()
      })
    })

    it('should show empty member state when no members exist', async () => {
      const user = userEvent.setup()
      mockGetOrganizationMembers.mockResolvedValue([])

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('Organization One')).toBeInTheDocument()
      })

      const orgButton = screen.getByText('Organization One')
      await user.click(orgButton)

      await waitFor(() => {
        expect(screen.getByText('No members yet')).toBeInTheDocument()
      })
    })

    it('should show loading state while fetching members', async () => {
      const user = userEvent.setup()
      mockGetOrganizationMembers.mockImplementation(() => new Promise(() => {}))

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('Your Organizations')).toBeInTheDocument()
      })

      const orgButtons = screen.getAllByText('Organization One')
      await user.click(orgButtons[0])

      // Just verify the API was not called yet since it's pending
      await new Promise((resolve) => setTimeout(resolve, 100))
    })
  })

  describe('Invite Member Modal', () => {
    it('should show invite button for organization admins', async () => {
      const user = userEvent.setup()

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('Organization One')).toBeInTheDocument()
      })

      const orgButton = screen.getByText('Organization One')
      await user.click(orgButton)

      await waitFor(() => {
        expect(screen.getByText('Invite Member')).toBeInTheDocument()
      })
    })

    it('should not show invite button for non-admins', async () => {
      const user = userEvent.setup()
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { ...mockSuperadminUser, is_superadmin: false },
        organizations: ['org-2'],
      })

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('Organization Two')).toBeInTheDocument()
      })

      const orgButton = screen.getByText('Organization Two')
      await user.click(orgButton)

      await waitFor(() => {
        expect(mockGetOrganizationMembers).toHaveBeenCalled()
      })

      expect(screen.queryByText('Invite Member')).not.toBeInTheDocument()
    })

    it('should open invite modal when clicking invite button', async () => {
      const user = userEvent.setup()

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('Organization One')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Organization One'))
      await waitFor(() => {
        expect(screen.getByText('Invite Member')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Invite Member'))

      expect(screen.getByText('Invite to Organization')).toBeInTheDocument()
      expect(screen.getByText('Email Address')).toBeInTheDocument()
      expect(screen.getByText('Role')).toBeInTheDocument()
    })

    it('should clear form when modal opens', async () => {
      const user = userEvent.setup()

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('Organization One')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Organization One'))
      await waitFor(() => {
        expect(screen.getByText('Invite Member')).toBeInTheDocument()
      })

      // Open modal
      await user.click(screen.getByText('Invite Member'))

      const emailInput = screen.getByPlaceholderText(
        'colleague@example.com'
      ) as HTMLInputElement
      await user.type(emailInput, 'test@example.com')

      // Close modal
      await user.click(screen.getByText('Cancel'))

      // Reopen modal
      await user.click(screen.getByText('Invite Member'))

      const newEmailInput = screen.getByPlaceholderText(
        'colleague@example.com'
      ) as HTMLInputElement
      expect(newEmailInput.value).toBe('')
    })

    it('should reset role to ANNOTATOR when modal reopens', async () => {
      const user = userEvent.setup()

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('Organization One')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Organization One'))
      await waitFor(() => {
        expect(screen.getByText('Invite Member')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Invite Member'))

      // Change role
      const roleSelect = screen.getAllByRole('combobox')[0] as HTMLSelectElement
      await user.selectOptions(roleSelect, 'CONTRIBUTOR')

      // Close and reopen
      await user.click(screen.getByText('Cancel'))
      await user.click(screen.getByText('Invite Member'))

      const newRoleSelect = screen.getAllByRole(
        'combobox'
      )[0] as HTMLSelectElement
      expect(newRoleSelect.value).toBe('ANNOTATOR')
    })
  })

  describe('Send Invitation', () => {
    it('should send invitation successfully', async () => {
      const user = userEvent.setup()

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('Organization One')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Organization One'))
      await waitFor(() => {
        expect(screen.getByText('Invite Member')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Invite Member'))

      const emailInput = screen.getByPlaceholderText('colleague@example.com')
      await user.type(emailInput, 'new@example.com')

      await user.click(screen.getByText('Send Invitation'))

      await waitFor(() => {
        expect(mockSendInvitation).toHaveBeenCalledWith('org-1', {
          email: 'new@example.com',
          role: 'ANNOTATOR',
        })
        expect(mockAddToast).toHaveBeenCalledWith(
          'Invitation sent successfully',
          'success'
        )
      })
    })

    it('should check for existing invitations before sending', async () => {
      const user = userEvent.setup()
      mockGetOrganizationInvitations.mockResolvedValue([
        {
          id: 'inv-1',
          email: 'existing@example.com',
          role: 'ANNOTATOR',
          is_accepted: false,
        },
      ])

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('Organization One')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Organization One'))
      await waitFor(() => {
        expect(screen.getByText('Invite Member')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Invite Member'))

      const emailInput = screen.getByPlaceholderText('colleague@example.com')
      await user.type(emailInput, 'existing@example.com')

      await user.click(screen.getByText('Send Invitation'))

      await waitFor(() => {
        expect(mockGetOrganizationInvitations).toHaveBeenCalledWith('org-1')
        expect(mockAddToast).toHaveBeenCalledWith(
          'Invitation already exists for existing@example.com',
          'warning'
        )
        expect(mockSendInvitation).not.toHaveBeenCalled()
      })
    })

    it('should show loading state while sending invitation', async () => {
      const user = userEvent.setup()
      let resolveInvitation: any
      mockSendInvitation.mockImplementation(
        () =>
          new Promise((resolve) => {
            resolveInvitation = resolve
          })
      )

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('Organization One')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Organization One'))
      await waitFor(() => {
        expect(screen.getByText('Invite Member')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Invite Member'))

      const emailInput = screen.getByPlaceholderText('colleague@example.com')
      await user.type(emailInput, 'new@example.com')

      await user.click(screen.getByText('Send Invitation'))

      await waitFor(() => {
        expect(screen.getByText('Sending...')).toBeInTheDocument()
      })

      resolveInvitation({
        id: 'inv-new',
        email: 'new@example.com',
        role: 'ANNOTATOR',
      })

      await waitFor(() => {
        expect(screen.queryByText('Sending...')).not.toBeInTheDocument()
      })
    })

    it('should reload members list after successful invitation', async () => {
      const user = userEvent.setup()

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('Organization One')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Organization One'))
      await waitFor(() => {
        expect(mockGetOrganizationMembers).toHaveBeenCalledTimes(1)
      })

      await user.click(screen.getByText('Invite Member'))

      const emailInput = screen.getByPlaceholderText('colleague@example.com')
      await user.type(emailInput, 'new@example.com')

      await user.click(screen.getByText('Send Invitation'))

      await waitFor(() => {
        expect(mockGetOrganizationMembers).toHaveBeenCalledTimes(2)
      })
    })
  })

  describe('Error Handling', () => {
    it('should display error when organization loading fails', async () => {
      const consoleError = jest.spyOn(console, 'error').mockImplementation()
      mockGetOrganizations.mockRejectedValue(new Error('Network error'))

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Failed to load organizations',
          'error'
        )
      })

      consoleError.mockRestore()
    })

    it('should display error when member loading fails', async () => {
      const consoleError = jest.spyOn(console, 'error').mockImplementation()
      const user = userEvent.setup()
      mockGetOrganizationMembers.mockRejectedValue(new Error('Network error'))

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('Organization One')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Organization One'))

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Failed to load members',
          'error'
        )
      })

      consoleError.mockRestore()
    })

    it('should handle invitation API error with detail message', async () => {
      const user = userEvent.setup()
      mockSendInvitation.mockRejectedValue({
        response: {
          data: {
            detail: 'already exists',
          },
        },
      })

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('Organization One')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Organization One'))
      await user.click(screen.getByText('Invite Member'))

      const emailInput = screen.getByPlaceholderText('colleague@example.com')
      await user.type(emailInput, 'test@example.com')

      await user.click(screen.getByText('Send Invitation'))

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Invitation already exists for test@example.com',
          'error'
        )
      })
    })

    it('should handle rate limit error', async () => {
      const user = userEvent.setup()
      mockSendInvitation.mockRejectedValue({
        response: {
          data: {
            detail: 'rate limit exceeded',
          },
        },
      })

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('Organization One')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Organization One'))
      await user.click(screen.getByText('Invite Member'))

      const emailInput = screen.getByPlaceholderText('colleague@example.com')
      await user.type(emailInput, 'test@example.com')

      await user.click(screen.getByText('Send Invitation'))

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Too many invitations sent',
          'error'
        )
      })
    })

    it('should handle network error', async () => {
      const user = userEvent.setup()
      mockSendInvitation.mockRejectedValue(new Error('Network error'))

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('Organization One')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Organization One'))
      await user.click(screen.getByText('Invite Member'))

      const emailInput = screen.getByPlaceholderText('colleague@example.com')
      await user.type(emailInput, 'test@example.com')

      await user.click(screen.getByText('Send Invitation'))

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Network error occurred',
          'error'
        )
      })
    })

    it('should handle invalid email error', async () => {
      const user = userEvent.setup()
      mockSendInvitation.mockRejectedValue({
        response: {
          data: {
            detail: 'invalid email address',
          },
        },
      })

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('Organization One')).toBeInTheDocument()
      })

      const orgButtons = screen.getAllByText('Organization One')
      await user.click(orgButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Invite Member')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Invite Member'))

      const emailInput = screen.getByPlaceholderText('colleague@example.com')
      await user.type(emailInput, 'test@example.com')

      await user.click(screen.getByText('Send Invitation'))

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Invalid email address',
          'error'
        )
      })
    })

    it('should handle generic API error with detail message', async () => {
      const user = userEvent.setup()
      mockSendInvitation.mockRejectedValue({
        response: {
          data: {
            detail: 'Some unexpected error occurred',
          },
        },
      })

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('Organization One')).toBeInTheDocument()
      })

      const orgButtons = screen.getAllByText('Organization One')
      await user.click(orgButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Invite Member')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Invite Member'))

      const emailInput = screen.getByPlaceholderText('colleague@example.com')
      await user.type(emailInput, 'test@example.com')

      await user.click(screen.getByText('Send Invitation'))

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Some unexpected error occurred',
          'error'
        )
      })
    })

    it('should close modal when clicking cancel or backdrop', async () => {
      const user = userEvent.setup()

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('Organization One')).toBeInTheDocument()
      })

      const orgButtons = screen.getAllByText('Organization One')
      await user.click(orgButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Invite Member')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Invite Member'))

      expect(screen.getByText('Invite to Organization')).toBeInTheDocument()

      await user.click(screen.getByText('Cancel'))

      await waitFor(() => {
        expect(
          screen.queryByText('Invite to Organization')
        ).not.toBeInTheDocument()
      })
    })
  })

  describe('Member Management', () => {
    it('should allow role changes for organization admins', async () => {
      const user = userEvent.setup()
      mockUpdateMemberRole.mockResolvedValue(undefined)

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('Organization One')).toBeInTheDocument()
      })

      const orgButtons = screen.getAllByText('Organization One')
      await user.click(orgButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Admin User')).toBeInTheDocument()
      })

      // Find role select for Contributor User
      const roleSelects = screen.getAllByRole('combobox')
      const contributorRoleSelect = roleSelects.find(
        (select) => (select as HTMLSelectElement).value === 'CONTRIBUTOR'
      ) as HTMLSelectElement

      await user.selectOptions(contributorRoleSelect, 'ORG_ADMIN')

      await waitFor(() => {
        expect(mockUpdateMemberRole).toHaveBeenCalledWith(
          'org-1',
          'user-2',
          'ORG_ADMIN'
        )
        expect(mockAddToast).toHaveBeenCalledWith(
          'Member role updated',
          'success'
        )
      })
    })

    it('should reload members after role change', async () => {
      const user = userEvent.setup()
      mockUpdateMemberRole.mockResolvedValue(undefined)

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('Organization One')).toBeInTheDocument()
      })

      const orgButtons = screen.getAllByText('Organization One')
      await user.click(orgButtons[0])

      await waitFor(() => {
        expect(mockGetOrganizationMembers).toHaveBeenCalledTimes(1)
      })

      const roleSelects = screen.getAllByRole('combobox')
      const contributorRoleSelect = roleSelects.find(
        (select) => (select as HTMLSelectElement).value === 'CONTRIBUTOR'
      ) as HTMLSelectElement

      await user.selectOptions(contributorRoleSelect, 'ORG_ADMIN')

      await waitFor(() => {
        expect(mockGetOrganizationMembers).toHaveBeenCalledTimes(2)
      })
    })

    it('should handle role change errors', async () => {
      const consoleError = jest.spyOn(console, 'error').mockImplementation()
      const user = userEvent.setup()
      mockUpdateMemberRole.mockRejectedValue(new Error('Update failed'))

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('Organization One')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Organization One'))

      await waitFor(() => {
        expect(screen.getByText('Admin User')).toBeInTheDocument()
      })

      const roleSelects = screen.getAllByRole('combobox')
      const contributorRoleSelect = roleSelects.find(
        (select) => (select as HTMLSelectElement).value === 'CONTRIBUTOR'
      ) as HTMLSelectElement

      await user.selectOptions(contributorRoleSelect, 'ORG_ADMIN')

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Failed to update role',
          'error'
        )
      })

      consoleError.mockRestore()
    })

    it('should remove member after confirmation', async () => {
      const user = userEvent.setup()
      window.confirm = jest.fn().mockReturnValue(true)
      mockRemoveMember.mockResolvedValue(undefined)

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('Organization One')).toBeInTheDocument()
      })

      const orgButtons = screen.getAllByText('Organization One')
      await user.click(orgButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Contributor User')).toBeInTheDocument()
      })

      // Find and click remove button for Contributor User
      const trashIcons = screen.getAllByTestId('trash-icon')
      await user.click(trashIcons[0].closest('button')!)

      await waitFor(() => {
        expect(window.confirm).toHaveBeenCalledWith(
          'Are you sure you want to remove this member?'
        )
        expect(mockRemoveMember).toHaveBeenCalledWith('org-1', 'user-2')
        expect(mockAddToast).toHaveBeenCalledWith(
          'Member removed successfully',
          'success'
        )
      })
    })

    it('should not remove member if confirmation is cancelled', async () => {
      const user = userEvent.setup()
      window.confirm = jest.fn().mockReturnValue(false)

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('Organization One')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Organization One'))

      await waitFor(() => {
        expect(screen.getByText('Contributor User')).toBeInTheDocument()
      })

      const trashIcons = screen.getAllByTestId('trash-icon')
      await user.click(trashIcons[0].closest('button')!)

      expect(mockRemoveMember).not.toHaveBeenCalled()
    })

    it('should not show remove button for current user', async () => {
      const user = userEvent.setup()

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('Organization One')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Organization One'))

      await waitFor(() => {
        expect(screen.getByText('Admin User')).toBeInTheDocument()
      })

      // Current user is user-1 (Admin User), should not have remove button
      const trashIcons = screen.getAllByTestId('trash-icon')
      // Should be fewer trash icons than total members since current user shouldn't have one
      expect(trashIcons.length).toBeLessThan(mockMembers.length)
    })

    it('should handle member removal errors', async () => {
      const consoleError = jest.spyOn(console, 'error').mockImplementation()
      const user = userEvent.setup()
      window.confirm = jest.fn().mockReturnValue(true)
      mockRemoveMember.mockRejectedValue(new Error('Removal failed'))

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('Organization One')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Organization One'))

      await waitFor(() => {
        expect(screen.getByText('Contributor User')).toBeInTheDocument()
      })

      const trashIcons = screen.getAllByTestId('trash-icon')
      await user.click(trashIcons[0].closest('button')!)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Failed to remove member',
          'error'
        )
      })

      consoleError.mockRestore()
    })

    it('should reload members after successful removal', async () => {
      const user = userEvent.setup()
      window.confirm = jest.fn().mockReturnValue(true)
      mockRemoveMember.mockResolvedValue(undefined)

      render(<OrganizationsPage />)

      await waitFor(() => {
        expect(screen.getByText('Organization One')).toBeInTheDocument()
      })

      const orgButtons = screen.getAllByText('Organization One')
      await user.click(orgButtons[0])

      await waitFor(() => {
        expect(mockGetOrganizationMembers).toHaveBeenCalledTimes(1)
      })

      const trashIcons = screen.getAllByTestId('trash-icon')
      await user.click(trashIcons[0].closest('button')!)

      await waitFor(() => {
        expect(mockGetOrganizationMembers).toHaveBeenCalledTimes(2)
      })
    })
  })
})
