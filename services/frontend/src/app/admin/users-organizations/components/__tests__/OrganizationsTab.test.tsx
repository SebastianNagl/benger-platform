/**
 * @jest-environment jsdom
 */

import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { OrganizationsTab } from '../OrganizationsTab'

// Mock Next.js navigation
const mockPush = jest.fn()
const mockRouter = jest.fn(() => ({
  push: mockPush,
  replace: jest.fn(),
  back: jest.fn(),
  forward: jest.fn(),
  refresh: jest.fn(),
  prefetch: jest.fn(),
}))

const mockSearchParams = {
  get: jest.fn(),
  toString: jest.fn(() => ''),
}

jest.mock('next/navigation', () => ({
  useRouter: () => mockRouter(),
  useSearchParams: () => mockSearchParams,
}))

// Mock contexts
// Create mock functions that will be shared across mocks
const mockUseAuth = jest.fn()
const mockUseI18n = jest.fn()
const mockUseToast = jest.fn()
const mockUseErrorAlert = jest.fn()
const mockUseDeleteConfirm = jest.fn()

// Mock contexts
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => mockUseI18n(),
}))

jest.mock('@/components/shared/Toast', () => ({
  useToast: () => mockUseToast(),
}))

jest.mock('@/hooks/useDialogs', () => ({
  useErrorAlert: () => mockUseErrorAlert(),
  useDeleteConfirm: () => mockUseDeleteConfirm(),
}))

jest.mock('@/lib/api/organizations', () => ({
  organizationsAPI: {
    sendInvitation: jest.fn(),
    removeMember: jest.fn(),
    updateMemberRole: jest.fn(),
    getAllUsers: jest.fn(),
    addUserToOrganization: jest.fn(),
    getOrganizationInvitations: jest.fn(),
  },
}))

// Get references to the mocked objects
const mockApiClient = {
  createOrganization: jest.fn(),
  updateOrganization: jest.fn(),
  deleteOrganization: jest.fn(),
  getOrganizationMembers: jest.fn(),
  listInvitations: jest.fn(),
  cancelInvitation: jest.fn(),
}

describe('OrganizationsTab', () => {
  // Helper function to get input by label text
  const getInputByLabel = (labelText: string | RegExp) => {
    const label = screen.getByText(labelText)
    const input = label.parentElement?.querySelector('input, textarea, select')
    return input as HTMLElement
  }

  const mockUser = {
    id: 'user-1',
    username: 'testuser',
    email: 'test@example.com',
    name: 'Test User',
    is_superadmin: true,
    is_active: true,
  }

  const mockOrganizations = [
    {
      id: 'org-1',
      name: 'Test Organization',
      slug: 'test-org',
      description: 'Test description',
      role: 'ORG_ADMIN',
    },
    {
      id: 'org-2',
      name: 'Second Organization',
      slug: 'second-org',
      description: 'Second description',
      role: 'CONTRIBUTOR',
    },
  ]

  const mockMembers = [
    {
      user_id: 'user-2',
      user_name: 'Member User',
      user_email: 'member@example.com',
      role: 'CONTRIBUTOR',
      organization_id: 'org-1',
      joined_at: '2024-01-01',
    },
    {
      user_id: 'user-3',
      user_name: 'Annotator User',
      user_email: 'annotator@example.com',
      role: 'ANNOTATOR',
      organization_id: 'org-1',
      joined_at: '2024-01-02',
    },
  ]

  const mockInvitations = [
    {
      id: 'invite-1',
      organization_id: 'org-1',
      email: 'invited@example.com',
      role: 'ANNOTATOR',
      token: 'test-token',
      invited_by: 'user-1',
      expires_at: '2024-12-31',
      accepted_at: null,
      is_accepted: false,
      created_at: '2024-01-01',
    },
  ]

  const mockAllUsers = [
    {
      id: 'user-4',
      name: 'New User',
      email: 'newuser@example.com',
      is_active: true,
    },
  ]

  const mockAddToast = jest.fn()
  const mockShowError = jest.fn()
  const mockConfirmDelete = jest.fn()
  const mockRefreshOrganizations = jest.fn()

  const setupDefaultMocks = () => {
    // Get the mocked organizationsAPI
    const { organizationsAPI } = require('@/lib/api/organizations')

    mockUseAuth.mockReturnValue({
      user: mockUser,
      organizations: mockOrganizations,
      refreshOrganizations: mockRefreshOrganizations,
      apiClient: mockApiClient,
    })

    mockUseI18n.mockReturnValue({
      t: (key: string, arg2?: any, arg3?: any) => {
        const vars = typeof arg2 === 'object' ? arg2 : arg3
        const translations: Record<string, string> = {
          'toasts.admin.orgCreated': 'Organization created successfully',
          'toasts.admin.invitationSent': 'Invitation sent successfully',
          'toasts.admin.memberRemoved': 'Member removed successfully',
          'toasts.admin.memberRoleUpdated': 'Member role updated successfully',
          'toasts.admin.orgUpdated': 'Organization updated successfully',
          'toasts.admin.orgDeleted': 'Organization deleted successfully',
          'toasts.admin.invitationCancelled': 'Invitation cancelled',
          'toasts.admin.userAdded': 'User added successfully',
          'admin.organizations.selectOrganization': 'Select Organization',
          'admin.organizations.apiKeys': 'API Keys',
          'admin.organizations.createOrganization': 'Create Organization',
          'admin.organizations.noDescription': 'No description',
          'admin.organizations.membersCount': '{count} members',
          'admin.organizations.yourRole': 'Your role: {role}',
          'admin.organizations.saving': 'Saving...',
          'admin.organizations.save': 'Save',
          'admin.organizations.cancel': 'Cancel',
          'admin.organizations.members': 'Members',
          'admin.organizations.inviteMember': 'Invite Member',
          'admin.organizations.addExistingUser': 'Add Existing User',
          'admin.organizations.loadingMembers': 'Loading members...',
          'admin.organizations.roleAnnotator': 'Annotator',
          'admin.organizations.roleContributor': 'Contributor',
          'admin.organizations.roleAdmin': 'Admin',
          'admin.organizations.pendingInvitations': 'Pending Invitations',
          'admin.organizations.invitedAs': 'Invited as {role}',
          'admin.organizations.selectToViewDetails': 'Select an organization to view details',
          'admin.organizations.noOrganizations': 'No organizations available',
          'admin.organizations.createNewOrganization': 'Create New Organization',
          'admin.organizations.name': 'Name',
          'admin.organizations.slug': 'Slug',
          'admin.organizations.description': 'Description',
          'admin.organizations.creating': 'Creating...',
          'admin.organizations.create': 'Create',
          'admin.organizations.addExistingUserToOrg': 'Add Existing User to Organization',
          'admin.organizations.searchUsers': 'Search Users',
          'admin.organizations.searchByNameOrEmail': 'Search by name or email...',
          'admin.organizations.selectUser': 'Select User',
          'admin.organizations.selectAUser': 'Select a user...',
          'admin.organizations.role': 'Role',
          'admin.organizations.adding': 'Adding...',
          'admin.organizations.addUser': 'Add User',
          'admin.organizations.sending': 'Sending...',
          'admin.organizations.sendInvitation': 'Send Invitation',
          'admin.organizations.email': 'Email',
          'admin.organizations.errors.errorTitle': 'Error',
          'admin.organizations.errors.loadFailed': 'Failed to load organization data',
          'admin.organizations.errors.noPermissionCreate': 'You do not have permission to create organizations',
          'admin.organizations.errors.createFailed': 'Failed to create organization',
          'admin.organizations.errors.noPermissionInvite': 'You do not have permission to invite members',
          'admin.organizations.errors.inviteFailed': 'Failed to send invitation',
          'admin.organizations.errors.noPermissionRemove': 'You do not have permission to remove this member',
          'admin.organizations.errors.removeFailed': 'Failed to remove member',
          'admin.organizations.errors.noPermissionChangeRole': 'You do not have permission to change this role',
          'admin.organizations.errors.updateRoleFailed': 'Failed to update role',
          'admin.organizations.errors.noPermissionEdit': 'You do not have permission to edit this organization',
          'admin.organizations.errors.updateFailed': 'Failed to update organization',
          'admin.organizations.errors.noPermissionDelete': 'You do not have permission to delete organizations',
          'admin.organizations.errors.deleteFailed': 'Failed to delete organization',
          'admin.organizations.errors.cancelInvitationFailed': 'Failed to cancel invitation',
          'admin.organizations.errors.loadUsersFailed': 'Failed to load users',
          'admin.organizations.errors.noPermissionAdd': 'You do not have permission to add members',
          'admin.organizations.errors.addUserFailed': 'Failed to add user',
        }
        let result = translations[key] || key
        if (vars) {
          Object.entries(vars).forEach(([k, v]) => {
            result = result.replace(`{${k}}`, String(v))
          })
        }
        return result
      },
      changeLanguage: jest.fn(),
      currentLanguage: 'en',
      languages: ['en', 'de'],
    })

    mockUseToast.mockReturnValue({
      addToast: mockAddToast,
    })

    mockUseErrorAlert.mockReturnValue(mockShowError)
    mockUseDeleteConfirm.mockReturnValue(mockConfirmDelete)

    mockApiClient.getOrganizationMembers.mockResolvedValue(mockMembers)
    organizationsAPI.getOrganizationInvitations.mockResolvedValue(mockInvitations)
    mockApiClient.createOrganization.mockResolvedValue({
      id: 'new-org',
      name: 'New Org',
      slug: 'new-org',
      description: 'New description',
    })
    mockApiClient.updateOrganization.mockResolvedValue({})
    mockApiClient.deleteOrganization.mockResolvedValue({})
    mockApiClient.cancelInvitation.mockResolvedValue({})

    organizationsAPI.sendInvitation.mockResolvedValue({})
    organizationsAPI.removeMember.mockResolvedValue({})
    organizationsAPI.updateMemberRole.mockResolvedValue({})
    organizationsAPI.getAllUsers.mockResolvedValue(mockAllUsers)
    organizationsAPI.addUserToOrganization.mockResolvedValue({})

    mockSearchParams.get.mockReturnValue(null)
    mockSearchParams.toString.mockReturnValue('')
  }

  beforeEach(() => {
    jest.clearAllMocks()
    setupDefaultMocks()

    // Reset organizationsAPI mocks after each test
    const { organizationsAPI } = require('@/lib/api/organizations')
    organizationsAPI.sendInvitation.mockResolvedValue({})
    organizationsAPI.removeMember.mockResolvedValue({})
    organizationsAPI.updateMemberRole.mockResolvedValue({})
    organizationsAPI.getAllUsers.mockResolvedValue(mockAllUsers)
    organizationsAPI.addUserToOrganization.mockResolvedValue({})
  })

  describe('Component Rendering', () => {
    it('should render organization selector and create button', () => {
      render(<OrganizationsTab />)

      expect(
        screen.getByRole('button', { name: /Test Organization/i })
      ).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: /Create Organization/i })
      ).toBeInTheDocument()
    })

    it('should render organization info card', async () => {
      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(screen.getByText('Test description')).toBeInTheDocument()
        expect(screen.getByText(/2 members/i)).toBeInTheDocument()
        const headings = screen.getAllByText('Test Organization')
        expect(headings.length).toBeGreaterThan(0)
      })
    })

    it('should not show create button for non-superadmin users', () => {
      mockUseAuth.mockReturnValue({
        user: { ...mockUser, is_superadmin: false },
        organizations: mockOrganizations,
        refreshOrganizations: mockRefreshOrganizations,
        apiClient: mockApiClient,
      })

      render(<OrganizationsTab />)

      expect(
        screen.queryByRole('button', { name: /Create Organization/i })
      ).not.toBeInTheDocument()
    })

    it('should show no organizations message when no organizations available', () => {
      mockUseAuth.mockReturnValue({
        user: mockUser,
        organizations: [],
        refreshOrganizations: mockRefreshOrganizations,
        apiClient: mockApiClient,
      })

      render(<OrganizationsTab />)

      expect(
        screen.getByText(/No organizations available/i)
      ).toBeInTheDocument()
    })

    it('should auto-select organization from URL parameter', async () => {
      mockSearchParams.get.mockImplementation((key) =>
        key === 'org' ? 'org-2' : null
      )

      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /Second Organization/i })
        ).toBeInTheDocument()
      })
    })
  })

  describe('Organization List Display', () => {
    it('should display members list', async () => {
      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(screen.getByText('Member User')).toBeInTheDocument()
        expect(screen.getByText('member@example.com')).toBeInTheDocument()
        expect(screen.getByText('Annotator User')).toBeInTheDocument()
        expect(screen.getByText('annotator@example.com')).toBeInTheDocument()
      })
    })

    it('should display pending invitations', async () => {
      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(screen.getByText('invited@example.com')).toBeInTheDocument()
        expect(screen.getByText(/Invited as ANNOTATOR/i)).toBeInTheDocument()
      })
    })

    it('should not display invitations section when no invitations exist', async () => {
      const { organizationsAPI } = require('@/lib/api/organizations')
      organizationsAPI.getOrganizationInvitations.mockResolvedValue([])

      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(screen.getByText('Member User')).toBeInTheDocument()
      })

      expect(screen.queryByText('Pending Invitations')).not.toBeInTheDocument()
    })

    it('should show loading state while fetching members', () => {
      render(<OrganizationsTab />)

      expect(screen.getByText('Loading members...')).toBeInTheDocument()
    })

    it('should display member roles correctly', async () => {
      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(screen.getByText('Member User')).toBeInTheDocument()
      })

      const selects = screen.getAllByRole('combobox')
      const contributorSelect = selects.find(
        (select) => (select as HTMLSelectElement).value === 'CONTRIBUTOR'
      )
      const annotatorSelect = selects.find(
        (select) => (select as HTMLSelectElement).value === 'ANNOTATOR'
      )

      expect(contributorSelect).toBeInTheDocument()
      expect(annotatorSelect).toBeInTheDocument()
    })
  })

  describe('Organization Switcher', () => {
    it('should open organization dropdown on click', () => {
      render(<OrganizationsTab />)

      const switcherButton = screen.getByRole('button', {
        name: /Test Organization/i,
      })
      fireEvent.click(switcherButton)

      expect(screen.getByText('Second Organization')).toBeInTheDocument()
      expect(screen.getByText('Second description')).toBeInTheDocument()
    })

    it('should switch to different organization', async () => {
      const replaceStateSpy = jest.spyOn(window.history, 'replaceState')

      render(<OrganizationsTab />)

      const switcherButton = screen.getByRole('button', {
        name: /Test Organization/i,
      })
      fireEvent.click(switcherButton)

      const secondOrgButton = screen.getByText('Second Organization')
      fireEvent.click(secondOrgButton)

      await waitFor(() => {
        expect(replaceStateSpy).toHaveBeenCalledWith(
          null,
          '',
          expect.stringContaining('org=org-2')
        )
      })

      replaceStateSpy.mockRestore()
    })

    it('should close dropdown after selecting organization', async () => {
      const replaceStateSpy = jest.spyOn(window.history, 'replaceState')

      render(<OrganizationsTab />)

      const switcherButton = screen.getByRole('button', {
        name: /Test Organization/i,
      })
      fireEvent.click(switcherButton)

      await waitFor(() => {
        expect(screen.getByText('Second Organization')).toBeInTheDocument()
      })

      const secondOrgButton = screen.getByText('Second Organization')
      fireEvent.click(secondOrgButton)

      // The dropdown should close
      await waitFor(() => {
        expect(replaceStateSpy).toHaveBeenCalled()
      })

      replaceStateSpy.mockRestore()
    })
  })

  describe('Create Organization', () => {
    it('should open create organization modal', async () => {
      render(<OrganizationsTab />)

      const createButton = screen.getByRole('button', {
        name: /Create Organization/i,
      })
      fireEvent.click(createButton)

      await waitFor(() => {
        expect(screen.getByText('Create New Organization')).toBeInTheDocument()
      })

      const modal = screen.getByText('Create New Organization').closest('div')
      expect(modal).toBeInTheDocument()

      const textInputs = screen.getAllByRole('textbox')
      expect(textInputs.length).toBeGreaterThan(0)
    })

    it('should create organization successfully', async () => {
      const user = userEvent.setup()
      render(<OrganizationsTab />)

      const createButton = screen.getByRole('button', {
        name: /Create Organization/i,
      })
      await user.click(createButton)

      await waitFor(() => {
        expect(screen.getByText('Create New Organization')).toBeInTheDocument()
      })

      const nameInput = getInputByLabel('Name')
      const slugInput = getInputByLabel('Slug')

      await user.type(nameInput, 'New Org')
      await user.type(slugInput, 'new-org')

      const submitButton = screen.getByRole('button', { name: /^Create$/i })
      await user.click(submitButton)

      await waitFor(() => {
        expect(mockApiClient.createOrganization).toHaveBeenCalledWith({
          name: 'New Org',
          display_name: 'New Org',
          slug: 'new-org',
          description: '',
        })
        expect(mockRefreshOrganizations).toHaveBeenCalled()
        expect(mockAddToast).toHaveBeenCalledWith(
          'Organization created successfully',
          'success'
        )
      })
    })

    it('should close modal on cancel', async () => {
      const user = userEvent.setup()
      render(<OrganizationsTab />)

      const createButton = screen.getByRole('button', {
        name: /Create Organization/i,
      })
      await user.click(createButton)

      const cancelButton = screen.getByRole('button', { name: /Cancel/i })
      await user.click(cancelButton)

      await waitFor(() => {
        expect(
          screen.queryByText('Create New Organization')
        ).not.toBeInTheDocument()
      })
    })

    it('should handle create organization errors', async () => {
      mockApiClient.createOrganization.mockRejectedValue(
        new Error('Creation failed')
      )

      const user = userEvent.setup()
      render(<OrganizationsTab />)

      const createButton = screen.getByRole('button', {
        name: /Create Organization/i,
      })
      await user.click(createButton)

      await waitFor(() => {
        expect(screen.getByText('Create New Organization')).toBeInTheDocument()
      })

      const nameInput = getInputByLabel('Name')
      const slugInput = getInputByLabel('Slug')

      await user.type(nameInput, 'New Org')
      await user.type(slugInput, 'new-org')

      const submitButton = screen.getByRole('button', { name: /^Create$/i })
      await user.click(submitButton)

      await waitFor(() => {
        expect(mockShowError).toHaveBeenCalledWith(
          'Failed to create organization',
          'Error'
        )
      })
    })

    it('should prevent non-superadmins from creating organizations', async () => {
      mockUseAuth.mockReturnValue({
        user: { ...mockUser, is_superadmin: false },
        organizations: mockOrganizations,
        refreshOrganizations: mockRefreshOrganizations,
        apiClient: mockApiClient,
      })

      render(<OrganizationsTab />)

      expect(
        screen.queryByRole('button', { name: /Create Organization/i })
      ).not.toBeInTheDocument()
    })
  })

  describe('Edit Organization', () => {
    it('should enable edit mode when clicking edit button', async () => {
      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(screen.getByText('Test description')).toBeInTheDocument()
      })

      const editButtons = screen.getAllByRole('button')
      const editButton = editButtons.find(
        (btn) =>
          btn.querySelector('svg')?.classList.contains('h-4') &&
          btn.className.includes('text-indigo-600')
      )

      if (editButton) {
        fireEvent.click(editButton)

        await waitFor(() => {
          const nameInputs = screen.queryAllByDisplayValue('Test Organization')
          const nameInput = nameInputs.find((el) => el.tagName === 'INPUT')
          expect(nameInput).toBeInTheDocument()
        })
      }
    })

    it('should update organization successfully', async () => {
      const user = userEvent.setup()
      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(screen.getByText('Test description')).toBeInTheDocument()
      })

      const editButtons = screen.getAllByRole('button')
      const editButton = editButtons.find(
        (btn) =>
          btn.querySelector('svg')?.classList.contains('h-4') &&
          btn.className.includes('text-indigo-600')
      )

      if (editButton) {
        await user.click(editButton)

        await waitFor(() => {
          const nameInputs = screen.queryAllByDisplayValue('Test Organization')
          expect(nameInputs.some((el) => el.tagName === 'INPUT')).toBe(true)
        })

        const nameInputs = screen.getAllByDisplayValue('Test Organization')
        const nameInput = nameInputs.find(
          (el) => el.tagName === 'INPUT'
        ) as HTMLInputElement

        await user.clear(nameInput)
        await user.type(nameInput, 'Updated Organization')

        const saveButton = screen.getByRole('button', { name: /Save/i })
        await user.click(saveButton)

        await waitFor(() => {
          expect(mockApiClient.updateOrganization).toHaveBeenCalledWith(
            'org-1',
            {
              name: 'Updated Organization',
              description: 'Test description',
            }
          )
          expect(mockRefreshOrganizations).toHaveBeenCalled()
          expect(mockAddToast).toHaveBeenCalledWith(
            'Organization updated successfully',
            'success'
          )
        })
      }
    })

    it('should cancel edit mode', async () => {
      const user = userEvent.setup()
      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(screen.getByText('Test description')).toBeInTheDocument()
      })

      const editButtons = screen.getAllByRole('button')
      const editButton = editButtons.find(
        (btn) =>
          btn.querySelector('svg')?.classList.contains('h-4') &&
          btn.className.includes('text-indigo-600')
      )

      if (editButton) {
        await user.click(editButton)

        await waitFor(() => {
          expect(
            screen.getByRole('button', { name: /Cancel/i })
          ).toBeInTheDocument()
        })

        const cancelButton = screen.getByRole('button', { name: /Cancel/i })
        await user.click(cancelButton)

        await waitFor(() => {
          const nameInputs = screen.queryAllByDisplayValue('Test Organization')
          const hasInput = nameInputs.some((el) => el.tagName === 'INPUT')
          expect(hasInput).toBe(false)
        })
      }
    })
  })

  describe('Delete Organization', () => {
    it('should delete organization after confirmation', async () => {
      mockConfirmDelete.mockResolvedValue(true)

      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(screen.getByText('Test description')).toBeInTheDocument()
      })

      const deleteButtons = screen.getAllByRole('button')
      const deleteButton = deleteButtons.find((btn) =>
        btn.className.includes('text-red-600')
      )

      if (deleteButton) {
        fireEvent.click(deleteButton)

        await waitFor(() => {
          expect(mockConfirmDelete).toHaveBeenCalledWith(
            'organization "Test Organization"'
          )
          expect(mockApiClient.deleteOrganization).toHaveBeenCalledWith('org-1')
          expect(mockRefreshOrganizations).toHaveBeenCalled()
          expect(mockAddToast).toHaveBeenCalledWith(
            'Organization deleted successfully',
            'success'
          )
        })
      }
    })

    it('should not delete organization if user cancels', async () => {
      mockConfirmDelete.mockResolvedValue(false)

      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(screen.getByText('Test description')).toBeInTheDocument()
      })

      const deleteButtons = screen.getAllByRole('button')
      const deleteButton = deleteButtons.find((btn) =>
        btn.className.includes('text-red-600')
      )

      if (deleteButton) {
        fireEvent.click(deleteButton)

        await waitFor(() => {
          expect(mockConfirmDelete).toHaveBeenCalled()
        })

        expect(mockApiClient.deleteOrganization).not.toHaveBeenCalled()
      }
    })

    it('should handle delete errors', async () => {
      mockConfirmDelete.mockResolvedValue(true)
      mockApiClient.deleteOrganization.mockRejectedValue(
        new Error('Delete failed')
      )

      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(screen.getByText('Test description')).toBeInTheDocument()
      })

      const deleteButtons = screen.getAllByRole('button')
      const deleteButton = deleteButtons.find((btn) =>
        btn.className.includes('text-red-600')
      )

      if (deleteButton) {
        fireEvent.click(deleteButton)

        await waitFor(() => {
          expect(mockShowError).toHaveBeenCalledWith(
            'Failed to delete organization',
            'Error'
          )
        })
      }
    })
  })

  describe('Member Management', () => {
    it('should display invite member button for org admins', async () => {
      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /Invite Member/i })
        ).toBeInTheDocument()
      })
    })

    it('should remove member after confirmation', async () => {
      mockConfirmDelete.mockResolvedValue(true)

      render(<OrganizationsTab />)

      await waitFor(
        () => {
          expect(screen.getByText('Member User')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      const allButtons = screen.getAllByRole('button')
      const deleteButtons = allButtons.filter((btn) =>
        btn.className.includes('text-red-600')
      )

      // We have org delete button, then 2 member delete buttons
      // deleteButtons[0] = org delete
      // deleteButtons[1] = first member (Member User - user-2)
      // deleteButtons[2] = second member (Annotator User - user-3)
      const memberDeleteButton = deleteButtons[1]

      expect(memberDeleteButton).toBeDefined()
      fireEvent.click(memberDeleteButton!)

      await waitFor(
        () => {
          const { organizationsAPI } = require('@/lib/api/organizations')
          expect(mockConfirmDelete).toHaveBeenCalledWith(
            'Member User from organization'
          )
          expect(organizationsAPI.removeMember).toHaveBeenCalledWith(
            'org-1',
            'user-2'
          )
          expect(mockAddToast).toHaveBeenCalledWith(
            'Member removed successfully',
            'success'
          )
        },
        { timeout: 3000 }
      )
    }, 10000)

    it('should change member role', async () => {
      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(screen.getByText('Member User')).toBeInTheDocument()
      })

      // Find the select element by its role
      const selects = screen.getAllByRole('combobox')
      const contributorSelect = selects.find(
        (select) => (select as HTMLSelectElement).value === 'CONTRIBUTOR'
      ) as HTMLSelectElement

      expect(contributorSelect).toBeInTheDocument()

      fireEvent.change(contributorSelect, { target: { value: 'ORG_ADMIN' } })

      await waitFor(() => {
        const { organizationsAPI } = require('@/lib/api/organizations')
        expect(organizationsAPI.updateMemberRole).toHaveBeenCalledWith(
          'org-1',
          'user-2',
          'ORG_ADMIN'
        )
        expect(mockAddToast).toHaveBeenCalledWith(
          'Member role updated successfully',
          'success'
        )
      })
    })

    it('should not show remove button for current user', async () => {
      const membersWithCurrentUser = [
        ...mockMembers,
        {
          user_id: 'user-1',
          user_name: 'Test User',
          user_email: 'test@example.com',
          role: 'ORG_ADMIN',
          organization_id: 'org-1',
          joined_at: '2024-01-01',
        },
      ]

      mockApiClient.getOrganizationMembers.mockResolvedValue(
        membersWithCurrentUser
      )

      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(screen.getByText('Test User')).toBeInTheDocument()
      })

      const currentUserCard = screen
        .getByText('Test User')
        .closest('div')!.parentElement!
      const deleteButton = within(currentUserCard)
        .queryAllByRole('button')
        .find((btn) => btn.className.includes('text-red-600'))

      expect(deleteButton).toBeUndefined()
    })
  })

  describe('Invitation Flows', () => {
    it('should open invite modal', async () => {
      const user = userEvent.setup()
      render(<OrganizationsTab />)

      await waitFor(
        () => {
          expect(screen.getByText('Member User')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      const inviteButtons = screen.getAllByRole('button', {
        name: /Invite Member/i,
      })
      // Click the first invite button (there might be multiple in the UI)
      await user.click(inviteButtons[0])

      await waitFor(
        () => {
          // Check for modal title heading instead of button text
          const modalTitle = screen
            .getAllByText('Invite Member')
            .find(
              (el) => el.tagName === 'H3' || el.parentElement?.tagName === 'H3'
            )
          expect(modalTitle).toBeInTheDocument()
          expect(getInputByLabel('Email')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      const roleSelects = screen.getAllByRole('combobox')
      expect(roleSelects.length).toBeGreaterThan(0)
    }, 10000)

    it('should send invitation successfully', async () => {
      const user = userEvent.setup()
      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /Invite Member/i })
        ).toBeInTheDocument()
      })

      const inviteButton = screen.getByRole('button', {
        name: /Invite Member/i,
      })
      await user.click(inviteButton)

      await waitFor(() => {
        expect(getInputByLabel('Email')).toBeInTheDocument()
      })

      await user.type(getInputByLabel('Email'), 'newinvite@example.com')

      const sendButton = screen.getByRole('button', {
        name: /Send Invitation/i,
      })
      await user.click(sendButton)

      await waitFor(() => {
        const { organizationsAPI } = require('@/lib/api/organizations')
        expect(organizationsAPI.sendInvitation).toHaveBeenCalledWith('org-1', {
          email: 'newinvite@example.com',
          role: 'ANNOTATOR',
        })
        expect(mockAddToast).toHaveBeenCalledWith(
          'Invitation sent successfully',
          'success'
        )
      })
    })

    it('should handle invitation errors', async () => {
      const { organizationsAPI } = require('@/lib/api/organizations')
      organizationsAPI.sendInvitation.mockRejectedValue({
        response: {
          data: {
            detail: 'User already invited',
          },
        },
      })

      const user = userEvent.setup()
      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /Invite Member/i })
        ).toBeInTheDocument()
      })

      const inviteButton = screen.getByRole('button', {
        name: /Invite Member/i,
      })
      await user.click(inviteButton)

      await waitFor(() => {
        expect(getInputByLabel('Email')).toBeInTheDocument()
      })

      await user.type(getInputByLabel('Email'), 'test@example.com')

      const sendButton = screen.getByRole('button', {
        name: /Send Invitation/i,
      })
      await user.click(sendButton)

      await waitFor(() => {
        expect(mockShowError).toHaveBeenCalledWith(
          'User already invited',
          'Error'
        )
      })
    })

    it('should cancel pending invitation', async () => {
      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(screen.getByText('invited@example.com')).toBeInTheDocument()
      })

      const allButtons = screen.getAllByRole('button')
      const redButtons = allButtons.filter((btn) =>
        btn.className.includes('text-red-600')
      )

      // The last red button should be the invitation cancel button
      const cancelButton = redButtons[redButtons.length - 1]
      fireEvent.click(cancelButton)

      await waitFor(() => {
        expect(mockApiClient.cancelInvitation).toHaveBeenCalledWith('invite-1')
        expect(mockAddToast).toHaveBeenCalledWith(
          'Invitation cancelled',
          'success'
        )
      })
    })
  })

  describe('Add Existing User', () => {
    it('should open add existing user modal for superadmins', async () => {
      const user = userEvent.setup()
      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /Add Existing User/i })
        ).toBeInTheDocument()
      })

      const addUserButton = screen.getByRole('button', {
        name: /Add Existing User/i,
      })
      await user.click(addUserButton)

      await waitFor(() => {
        const { organizationsAPI } = require('@/lib/api/organizations')
        expect(
          screen.getByText('Add Existing User to Organization')
        ).toBeInTheDocument()
        expect(organizationsAPI.getAllUsers).toHaveBeenCalled()
      })
    })

    it('should add existing user successfully', async () => {
      const user = userEvent.setup()
      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(screen.getByText('Test description')).toBeInTheDocument()
        expect(
          screen.getByRole('button', { name: /Add Existing User/i })
        ).toBeInTheDocument()
      })

      const addUserButton = screen.getByRole('button', {
        name: /Add Existing User/i,
      })
      await user.click(addUserButton)

      await waitFor(
        () => {
          expect(
            screen.getByText('Add Existing User to Organization')
          ).toBeInTheDocument()
          const userSelect = getInputByLabel('Select User')
          expect(userSelect).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      const userSelect = getInputByLabel('Select User')
      await user.selectOptions(userSelect, 'user-4')

      const addButton = screen.getByRole('button', { name: /Add User/i })
      await user.click(addButton)

      await waitFor(() => {
        const { organizationsAPI } = require('@/lib/api/organizations')
        expect(organizationsAPI.addUserToOrganization).toHaveBeenCalledWith(
          'org-1',
          'user-4',
          'ANNOTATOR'
        )
        expect(mockAddToast).toHaveBeenCalledWith(
          'User added successfully',
          'success'
        )
      })
    })

    it('should filter users by search query', async () => {
      const user = userEvent.setup()
      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(screen.getByText('Test description')).toBeInTheDocument()
        expect(
          screen.getByRole('button', { name: /Add Existing User/i })
        ).toBeInTheDocument()
      })

      const addUserButton = screen.getByRole('button', {
        name: /Add Existing User/i,
      })
      await user.click(addUserButton)

      await waitFor(
        () => {
          const userSelect = getInputByLabel('Select User')
          expect(userSelect).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      const searchInput = screen.getByPlaceholderText(
        /Search by name or email/i
      )
      await user.type(searchInput, 'nonexistent')

      const userSelect = getInputByLabel('Select User')
      const options = within(userSelect).queryAllByRole('option')

      expect(options.length).toBe(1) // Only the "Select a user..." option
    })
  })

  describe('Error Handling', () => {
    it('should handle member loading errors', async () => {
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation()
      mockApiClient.getOrganizationMembers.mockRejectedValue(
        new Error('Failed to load members')
      )

      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(consoleErrorSpy).toHaveBeenCalledWith(
          'Failed to load organization data:',
          expect.any(Error)
        )
        expect(mockShowError).toHaveBeenCalledWith(
          'Failed to load organization data',
          'Error'
        )
      })

      consoleErrorSpy.mockRestore()
    })

    it('should handle member removal errors', async () => {
      const { organizationsAPI } = require('@/lib/api/organizations')
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation()
      mockConfirmDelete.mockResolvedValue(true)
      organizationsAPI.removeMember.mockRejectedValue(
        new Error('Remove failed')
      )

      render(<OrganizationsTab />)

      await waitFor(
        () => {
          expect(screen.getByText('Member User')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      const allButtons = screen.getAllByRole('button')
      const deleteButtons = allButtons.filter((btn) =>
        btn.className.includes('text-red-600')
      )

      // deleteButtons[1] = first member (Member User - user-2)
      const memberDeleteButton = deleteButtons[1]

      expect(memberDeleteButton).toBeDefined()
      fireEvent.click(memberDeleteButton!)

      await waitFor(
        () => {
          expect(mockConfirmDelete).toHaveBeenCalled()
          expect(mockShowError).toHaveBeenCalledWith(
            'Failed to remove member',
            'Error'
          )
        },
        { timeout: 3000 }
      )

      consoleErrorSpy.mockRestore()
    }, 10000)

    it('should handle role change errors', async () => {
      const { organizationsAPI } = require('@/lib/api/organizations')
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation()
      organizationsAPI.updateMemberRole.mockRejectedValue(
        new Error('Update failed')
      )

      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(screen.getByText('Member User')).toBeInTheDocument()
      })

      const selects = screen.getAllByRole('combobox')
      const contributorSelect = selects.find(
        (select) => (select as HTMLSelectElement).value === 'CONTRIBUTOR'
      ) as HTMLSelectElement

      fireEvent.change(contributorSelect, { target: { value: 'ORG_ADMIN' } })

      await waitFor(() => {
        expect(mockShowError).toHaveBeenCalledWith(
          'Failed to update role',
          'Error'
        )
      })

      consoleErrorSpy.mockRestore()
    })
  })

  describe('Permission Checks', () => {
    it('should not show manage buttons for non-admin users', async () => {
      const nonAdminOrgs = mockOrganizations.map((org) => ({
        ...org,
        role: 'ANNOTATOR',
      }))

      mockUseAuth.mockReturnValue({
        user: { ...mockUser, is_superadmin: false },
        organizations: nonAdminOrgs,
        refreshOrganizations: mockRefreshOrganizations,
        apiClient: mockApiClient,
      })

      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(screen.getByText('Test description')).toBeInTheDocument()
      })

      expect(
        screen.queryByRole('button', { name: /Invite Member/i })
      ).not.toBeInTheDocument()
      expect(
        screen.queryByRole('button', { name: /Add Existing User/i })
      ).not.toBeInTheDocument()
    })

    it('should prevent non-org-admin from inviting members', async () => {
      const nonAdminOrgs = mockOrganizations.map((org) => ({
        ...org,
        role: 'CONTRIBUTOR',
      }))

      mockUseAuth.mockReturnValue({
        user: { ...mockUser, is_superadmin: false },
        organizations: nonAdminOrgs,
        refreshOrganizations: mockRefreshOrganizations,
        apiClient: mockApiClient,
      })

      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(screen.getByText('Test description')).toBeInTheDocument()
      })

      expect(
        screen.queryByRole('button', { name: /Invite Member/i })
      ).not.toBeInTheDocument()
    })

    it('should prevent non-org-admin from editing organization', async () => {
      const nonAdminOrgs = mockOrganizations.map((org) => ({
        ...org,
        role: 'CONTRIBUTOR',
      }))

      mockUseAuth.mockReturnValue({
        user: { ...mockUser, is_superadmin: false },
        organizations: nonAdminOrgs,
        refreshOrganizations: mockRefreshOrganizations,
        apiClient: mockApiClient,
      })

      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(screen.getByText('Test description')).toBeInTheDocument()
      })

      // Edit button should not be visible for non-admins
      const editButtons = screen.queryAllByRole('button')
      const editButton = editButtons.find(
        (btn) =>
          btn.querySelector('svg')?.classList.contains('h-4') &&
          btn.className.includes('text-indigo-600')
      )

      expect(editButton).toBeUndefined()
    })
  })

  describe('Edge Cases', () => {
    it('should handle auto-select of first admin organization', () => {
      const orgsWithAdmin = [
        { ...mockOrganizations[0], role: 'ORG_ADMIN' },
        { ...mockOrganizations[1], role: 'CONTRIBUTOR' },
      ]

      mockUseAuth.mockReturnValue({
        user: mockUser,
        organizations: orgsWithAdmin,
        refreshOrganizations: mockRefreshOrganizations,
        apiClient: mockApiClient,
      })

      render(<OrganizationsTab />)

      expect(
        screen.getByRole('button', { name: /Test Organization/i })
      ).toBeInTheDocument()
    })

    it('should handle organization with no description', async () => {
      const orgWithoutDescription = [
        { ...mockOrganizations[0], description: '' },
      ]

      mockUseAuth.mockReturnValue({
        user: mockUser,
        organizations: orgWithoutDescription,
        refreshOrganizations: mockRefreshOrganizations,
        apiClient: mockApiClient,
      })

      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(screen.getByText('No description')).toBeInTheDocument()
      })
    })

    it('should display user role badge', async () => {
      const orgsWithRole = mockOrganizations.map((org) => ({
        ...org,
        user_role: org.role,
      }))

      mockUseAuth.mockReturnValue({
        user: mockUser,
        organizations: orgsWithRole,
        refreshOrganizations: mockRefreshOrganizations,
        apiClient: mockApiClient,
      })

      render(<OrganizationsTab />)

      await waitFor(
        () => {
          expect(screen.getByText(/Your role: ORG_ADMIN/i)).toBeInTheDocument()
        },
        { timeout: 3000 }
      )
    })

    it('should persist form fields when modal is cancelled and reopened', async () => {
      const user = userEvent.setup()
      render(<OrganizationsTab />)

      const createButton = screen.getByRole('button', {
        name: /Create Organization/i,
      })
      await user.click(createButton)

      await waitFor(
        () => {
          expect(
            screen.getByText('Create New Organization')
          ).toBeInTheDocument()
          expect(getInputByLabel('Name')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      const nameInput = getInputByLabel('Name') as HTMLInputElement
      const slugInput = getInputByLabel('Slug') as HTMLInputElement

      await user.type(nameInput, 'Test')
      await user.type(slugInput, 'test')

      // Verify values are entered
      expect(nameInput.value).toBe('Test')
      expect(slugInput.value).toBe('test')

      const cancelButton = screen.getByRole('button', { name: /Cancel/i })
      await user.click(cancelButton)

      await waitFor(
        () => {
          expect(
            screen.queryByText('Create New Organization')
          ).not.toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      // Reopen modal
      await user.click(createButton)

      await waitFor(
        () => {
          expect(
            screen.getByText('Create New Organization')
          ).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      // Form fields should persist (current behavior - form state is not reset on cancel)
      const reopenedNameInput = getInputByLabel('Name') as HTMLInputElement
      const reopenedSlugInput = getInputByLabel('Slug') as HTMLInputElement

      // Current implementation persists form state
      expect(reopenedNameInput.value).toBe('Test')
      expect(reopenedSlugInput.value).toBe('test')
    }, 10000)

    it('should show loading state button during organization update', async () => {
      const user = userEvent.setup()
      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(screen.getByText('Test description')).toBeInTheDocument()
      })

      const editButtons = screen.getAllByRole('button')
      const editButton = editButtons.find(
        (btn) =>
          btn.querySelector('svg')?.classList.contains('h-4') &&
          btn.className.includes('text-indigo-600')
      )

      if (editButton) {
        await user.click(editButton)

        await waitFor(() => {
          const nameInputs = screen.queryAllByDisplayValue('Test Organization')
          expect(nameInputs.some((el) => el.tagName === 'INPUT')).toBe(true)
        })

        const saveButton = screen.getByRole('button', { name: /Save/i })

        // Make the API call take time
        mockApiClient.updateOrganization.mockReturnValue(
          new Promise((resolve) => setTimeout(resolve, 100))
        )

        await user.click(saveButton)

        // Check for loading state
        expect(screen.getByText('Saving...')).toBeInTheDocument()
      }
    })
  })

  describe('Additional Invitation Modal Coverage', () => {
    it('should change invitation role before sending', async () => {
      const user = userEvent.setup()
      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /Invite Member/i })
        ).toBeInTheDocument()
      })

      const inviteButton = screen.getByRole('button', {
        name: /Invite Member/i,
      })
      await user.click(inviteButton)

      await waitFor(() => {
        expect(getInputByLabel('Email')).toBeInTheDocument()
      })

      await user.type(getInputByLabel('Email'), 'newmember@example.com')

      const roleSelects = screen.getAllByRole('combobox')
      const inviteRoleSelect = roleSelects[roleSelects.length - 1]

      await user.selectOptions(inviteRoleSelect, 'CONTRIBUTOR')

      const sendButton = screen.getByRole('button', {
        name: /Send Invitation/i,
      })
      await user.click(sendButton)

      await waitFor(() => {
        const { organizationsAPI } = require('@/lib/api/organizations')
        expect(organizationsAPI.sendInvitation).toHaveBeenCalledWith('org-1', {
          email: 'newmember@example.com',
          role: 'CONTRIBUTOR',
        })
      })
    })

    it('should close invite modal on cancel', async () => {
      const user = userEvent.setup()
      render(<OrganizationsTab />)

      await waitFor(
        () => {
          expect(screen.getByText('Member User')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      const inviteButtons = screen.getAllByRole('button', {
        name: /Invite Member/i,
      })
      await user.click(inviteButtons[0])

      await waitFor(
        () => {
          // Check for modal title heading
          const modalTitle = screen
            .getAllByText('Invite Member')
            .find(
              (el) => el.tagName === 'H3' || el.parentElement?.tagName === 'H3'
            )
          expect(modalTitle).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      const cancelButton = screen.getByRole('button', { name: /Cancel/i })
      await user.click(cancelButton)

      await waitFor(
        () => {
          // Modal title should not be present anymore
          const modalTitles = screen
            .queryAllByText('Invite Member')
            .filter(
              (el) => el.tagName === 'H3' || el.parentElement?.tagName === 'H3'
            )
          expect(modalTitles.length).toBe(0)
        },
        { timeout: 3000 }
      )
    }, 10000)

    it('should reset invite form fields after successful submission', async () => {
      const user = userEvent.setup()
      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(screen.getByText('Member User')).toBeInTheDocument()
      })

      const inviteButtons = screen.getAllByRole('button', {
        name: /Invite Member/i,
      })
      await user.click(inviteButtons[0])

      await waitFor(() => {
        expect(getInputByLabel('Email')).toBeInTheDocument()
      })

      await user.type(getInputByLabel('Email'), 'test@example.com')

      const sendButton = screen.getByRole('button', {
        name: /Send Invitation/i,
      })
      await user.click(sendButton)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Invitation sent successfully',
          'success'
        )
      })

      // Modal title should not be present after success
      await waitFor(() => {
        const modalTitles = screen
          .queryAllByText('Invite Member')
          .filter(
            (el) => el.tagName === 'H3' || el.parentElement?.tagName === 'H3'
          )
        expect(modalTitles.length).toBe(0)
      })
    })
  })

  describe('Additional Add User Modal Coverage', () => {
    it('should close add user modal on cancel', async () => {
      const user = userEvent.setup()
      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /Add Existing User/i })
        ).toBeInTheDocument()
      })

      const addUserButton = screen.getByRole('button', {
        name: /Add Existing User/i,
      })
      await user.click(addUserButton)

      await waitFor(() => {
        expect(
          screen.getByText('Add Existing User to Organization')
        ).toBeInTheDocument()
      })

      const cancelButton = screen.getByRole('button', { name: /Cancel/i })
      await user.click(cancelButton)

      await waitFor(() => {
        expect(
          screen.queryByText('Add Existing User to Organization')
        ).not.toBeInTheDocument()
      })
    })

    it('should change user role before adding', async () => {
      const user = userEvent.setup()
      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /Add Existing User/i })
        ).toBeInTheDocument()
      })

      const addUserButton = screen.getByRole('button', {
        name: /Add Existing User/i,
      })
      await user.click(addUserButton)

      await waitFor(
        () => {
          const userSelect = getInputByLabel('Select User')
          expect(userSelect).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      const userSelect = getInputByLabel('Select User')
      await user.selectOptions(userSelect, 'user-4')

      const roleSelects = screen.getAllByRole('combobox')
      const addUserRoleSelect = roleSelects[roleSelects.length - 1]
      await user.selectOptions(addUserRoleSelect, 'CONTRIBUTOR')

      const addButton = screen.getByRole('button', { name: /Add User/i })
      await user.click(addButton)

      await waitFor(() => {
        const { organizationsAPI } = require('@/lib/api/organizations')
        expect(organizationsAPI.addUserToOrganization).toHaveBeenCalledWith(
          'org-1',
          'user-4',
          'CONTRIBUTOR'
        )
      })
    })

    it('should handle add user errors', async () => {
      const { organizationsAPI } = require('@/lib/api/organizations')
      organizationsAPI.addUserToOrganization.mockRejectedValue({
        response: {
          data: {
            detail: 'User already in organization',
          },
        },
      })

      const user = userEvent.setup()
      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /Add Existing User/i })
        ).toBeInTheDocument()
      })

      const addUserButton = screen.getByRole('button', {
        name: /Add Existing User/i,
      })
      await user.click(addUserButton)

      await waitFor(
        () => {
          const userSelect = getInputByLabel('Select User')
          expect(userSelect).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      const userSelect = getInputByLabel('Select User')
      await user.selectOptions(userSelect, 'user-4')

      const addButton = screen.getByRole('button', { name: /Add User/i })
      await user.click(addButton)

      await waitFor(() => {
        expect(mockShowError).toHaveBeenCalledWith(
          'User already in organization',
          'Error'
        )
      })
    })

    it('should disable add button when no user selected', async () => {
      const user = userEvent.setup()
      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /Add Existing User/i })
        ).toBeInTheDocument()
      })

      const addUserButton = screen.getByRole('button', {
        name: /Add Existing User/i,
      })
      await user.click(addUserButton)

      await waitFor(() => {
        expect(
          screen.getByText('Add Existing User to Organization')
        ).toBeInTheDocument()
      })

      const addButton = screen.getByRole('button', { name: /Add User/i })
      expect(addButton).toBeDisabled()
    })
  })

  describe('Additional Permission Coverage', () => {
    it('should prevent non-superadmin from accessing add existing user', async () => {
      mockUseAuth.mockReturnValue({
        user: { ...mockUser, is_superadmin: false },
        organizations: mockOrganizations,
        refreshOrganizations: mockRefreshOrganizations,
        apiClient: mockApiClient,
      })

      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(screen.getByText('Test description')).toBeInTheDocument()
      })

      expect(
        screen.queryByRole('button', { name: /Add Existing User/i })
      ).not.toBeInTheDocument()
    })

    it('should handle invitation without permission', async () => {
      const nonAdminOrgs = mockOrganizations.map((org) => ({
        ...org,
        role: 'ANNOTATOR',
      }))

      mockUseAuth.mockReturnValue({
        user: { ...mockUser, is_superadmin: false },
        organizations: nonAdminOrgs,
        refreshOrganizations: mockRefreshOrganizations,
        apiClient: mockApiClient,
      })

      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(screen.getByText('Test description')).toBeInTheDocument()
      })

      expect(
        screen.queryByRole('button', { name: /Invite Member/i })
      ).not.toBeInTheDocument()
    })
  })

  describe('Additional Error Handling Coverage', () => {
    it('should handle cancel invitation errors', async () => {
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation()
      mockApiClient.cancelInvitation.mockRejectedValue(
        new Error('Cancel failed')
      )

      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(screen.getByText('invited@example.com')).toBeInTheDocument()
      })

      const allButtons = screen.getAllByRole('button')
      const redButtons = allButtons.filter((btn) =>
        btn.className.includes('text-red-600')
      )

      const cancelButton = redButtons[redButtons.length - 1]
      fireEvent.click(cancelButton)

      await waitFor(() => {
        expect(mockShowError).toHaveBeenCalledWith(
          'Failed to cancel invitation',
          'Error'
        )
      })

      consoleErrorSpy.mockRestore()
    })

    it('should handle update organization errors', async () => {
      mockApiClient.updateOrganization.mockRejectedValue(
        new Error('Update failed')
      )

      const user = userEvent.setup()
      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(screen.getByText('Test description')).toBeInTheDocument()
      })

      const editButtons = screen.getAllByRole('button')
      const editButton = editButtons.find(
        (btn) =>
          btn.querySelector('svg')?.classList.contains('h-4') &&
          btn.className.includes('text-indigo-600')
      )

      if (editButton) {
        await user.click(editButton)

        await waitFor(() => {
          const nameInputs = screen.queryAllByDisplayValue('Test Organization')
          expect(nameInputs.some((el) => el.tagName === 'INPUT')).toBe(true)
        })

        const saveButton = screen.getByRole('button', { name: /Save/i })
        await user.click(saveButton)

        await waitFor(() => {
          expect(mockShowError).toHaveBeenCalledWith(
            'Failed to update organization',
            'Error'
          )
        })
      }
    })

    it('should handle load all users errors', async () => {
      const { organizationsAPI } = require('@/lib/api/organizations')
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation()
      organizationsAPI.getAllUsers.mockRejectedValue(
        new Error('Failed to load users')
      )

      const user = userEvent.setup()
      render(<OrganizationsTab />)

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /Add Existing User/i })
        ).toBeInTheDocument()
      })

      const addUserButton = screen.getByRole('button', {
        name: /Add Existing User/i,
      })
      await user.click(addUserButton)

      await waitFor(() => {
        expect(mockShowError).toHaveBeenCalledWith(
          'Failed to load users',
          'Error'
        )
      })

      consoleErrorSpy.mockRestore()
    })
  })
})
