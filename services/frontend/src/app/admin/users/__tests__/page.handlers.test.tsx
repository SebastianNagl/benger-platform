/**
 * Behavioral handler-coverage tests for AdminUsersPage.
 *
 * These drive the interactive handlers through the rendered DOM (superadmin
 * Select changes, delete confirm modal, bulk verify, per-row email verify,
 * and the full organizations tab: role change, remove member, cancel
 * invitation, edit org, add-user error branches).
 *
 * The page fires a router.push redirect in a useEffect, but that does NOT
 * unmount the component in jsdom, so every handler below is reachable.
 *
 * Mock scaffold is copied from page.branch.test.tsx (setupMocks). The shared
 * Select is auto-mocked globally to a native <select> (role combobox) by
 * jest.config.js moduleNameMapper, so userEvent.selectOptions drives
 * onValueChange. EmailVerificationModal is mocked here to a minimal confirm
 * button so handleVerifyEmail is reachable without HeadlessUI Dialog portal
 * flakiness.
 *
 * @jest-environment jsdom
 */

import { useAuth } from '@/contexts/AuthContext'
import { useFeatureFlags } from '@/contexts/FeatureFlagContext'
import { useI18n } from '@/contexts/I18nContext'
import { useDeleteConfirm, useErrorAlert } from '@/hooks/useDialogs'
import { api, ApiClient } from '@/lib/api'
import { organizationsAPI } from '@/lib/api/organizations'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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

// Mock the EmailVerificationModal to a minimal confirm button so the page's
// onConfirm -> handleVerifyEmail path is reachable deterministically.
jest.mock('@/components/admin/EmailVerificationModal', () => ({
  EmailVerificationModal: ({ isOpen, onConfirm, onClose, user }: any) =>
    isOpen ? (
      <div data-testid="email-verification-modal">
        <span data-testid="evm-user">{user?.email}</span>
        <button
          data-testid="evm-confirm"
          onClick={async () => {
            await onConfirm('admin reason')
            onClose()
          }}
        >
          confirm-verify
        </button>
      </div>
    ) : null,
}))

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

const mockOrg = {
  id: 'org-1',
  name: 'TUM',
  display_name: 'TUM',
  slug: 'tum',
  description: 'TUM org',
  created_at: '2024-01-01',
  updated_at: '2024-01-01',
}

// The current (logged-in) superadmin. Other users are the testable rows.
const currentUserFixture = {
  id: 'admin-1',
  username: 'admin',
  email: 'admin@test.com',
  name: 'Admin',
  is_superadmin: true,
  is_active: true,
  created_at: '2024-01-01',
}

// A non-current regular user (drives the superadmin Select + delete button).
const otherUser = {
  id: 'user-2',
  username: 'jdoe',
  email: 'jdoe@test.com',
  name: 'John Doe',
  is_superadmin: false,
  is_active: true,
  email_verified: false,
  created_at: '2024-01-01',
}

const mockMembers = [
  {
    user_id: 'user-2',
    organization_id: 'org-1',
    role: 'CONTRIBUTOR' as const,
    user_name: 'John Doe',
    user_email: 'jdoe@test.com',
    email_verified: true,
    joined_at: '2024-01-01',
    is_active: true,
  },
]

const mockInvitations = [
  {
    id: 'invite-1',
    organization_id: 'org-1',
    email: 'invited@test.com',
    role: 'ANNOTATOR' as const,
    token: 'tok',
    invited_by: 'admin-1',
    expires_at: '2024-12-31',
    accepted_at: null,
    is_accepted: false,
    created_at: '2024-01-01',
    organization_name: 'TUM',
    inviter_name: 'Admin',
  },
]

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
  ;(useErrorAlert as jest.Mock).mockReturnValue(overrides.showError ?? jest.fn())
  ;(useDeleteConfirm as jest.Mock).mockReturnValue(
    overrides.confirmDelete ?? jest.fn().mockResolvedValue(true)
  )

  const mockApi = api as jest.Mocked<typeof api>
  mockApi.getAllUsers = jest
    .fn()
    .mockResolvedValue(overrides.users ?? [currentUserFixture, otherUser])
  mockApi.verifyUserEmail = jest.fn().mockResolvedValue(undefined)
  mockApi.updateUserSuperadminStatus = jest.fn().mockResolvedValue({})
  mockApi.deleteUser = jest.fn().mockResolvedValue(undefined)

  ;(organizationsAPI as jest.Mocked<typeof organizationsAPI>).bulkVerifyMemberEmails =
    jest.fn().mockResolvedValue({
      summary: { total: 1, success: 1, skipped: 0, errors: 0 },
      results: [{ user_id: 'user-2', status: 'success', message: 'ok' }],
    })

  ;(useAuth as jest.Mock).mockReturnValue({
    user: overrides.user ?? currentUserFixture,
    login: jest.fn(),
    signup: jest.fn(),
    logout: jest.fn(),
    updateUser: jest.fn(),
    isLoading: false,
    refreshAuth: jest.fn(),
    apiClient: overrides.apiClient ?? mockApiClient,
    organizations: overrides.organizations ?? [mockOrg],
    currentOrganization: overrides.currentOrganization ?? mockOrg,
    setCurrentOrganization: jest.fn(),
    refreshOrganizations: overrides.refreshOrganizations ?? jest.fn(),
  } as any)
}

// Wait until the users table rows have rendered (loading=false + users set).
async function waitForUserRow(name: string) {
  return await screen.findByText(name)
}

// Find the <tr> containing the given user display name.
function rowFor(name: string): HTMLElement {
  const cell = screen.getByText(name)
  const row = cell.closest('tr')
  if (!row) throw new Error(`No row for ${name}`)
  return row as HTMLElement
}

describe('AdminUsersPage handler coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('handleSuperadminChange (lines 181-215)', () => {
    it('promotes a user and merges a valid response into local state', async () => {
      setupMocks()
      // Override AFTER setupMocks so this per-test resolution wins.
      ;(api.updateUserSuperadminStatus as jest.Mock).mockResolvedValue({
        id: 'user-2',
        is_superadmin: true,
      })
      render(<AdminUsersPage />)
      await waitForUserRow('John Doe')

      const row = rowFor('John Doe')
      const combobox = within(row).getByRole('combobox')
      await userEvent.selectOptions(combobox, 'superadmin')

      await waitFor(() => {
        expect(api.updateUserSuperadminStatus).toHaveBeenCalledWith(
          'user-2',
          true
        )
      })
    })

    it('refetches users when the response is invalid (no id)', async () => {
      setupMocks()
      // setupMocks already resolves {} (invalid -> triggers fetchUsers()).
      render(<AdminUsersPage />)
      await waitForUserRow('John Doe')

      // First fetchUsers happened on mount; reset to observe the refetch.
      ;(api.getAllUsers as jest.Mock).mockClear()

      const row = rowFor('John Doe')
      await userEvent.selectOptions(
        within(row).getByRole('combobox'),
        'superadmin'
      )

      await waitFor(() => {
        expect(api.updateUserSuperadminStatus).toHaveBeenCalled()
        expect(api.getAllUsers).toHaveBeenCalled()
      })
    })

    it('sets error and refetches on rejection', async () => {
      setupMocks()
      ;(api.updateUserSuperadminStatus as jest.Mock).mockRejectedValue(
        new Error('boom')
      )
      render(<AdminUsersPage />)
      await waitForUserRow('John Doe')

      ;(api.getAllUsers as jest.Mock).mockClear()

      const row = rowFor('John Doe')
      await userEvent.selectOptions(
        within(row).getByRole('combobox'),
        'superadmin'
      )

      // Error message surfaces in the error banner and a refetch fires.
      await waitFor(() => {
        expect(screen.getByText('boom')).toBeInTheDocument()
        expect(api.getAllUsers).toHaveBeenCalled()
      })
    })
  })

  describe('handleDeleteUser (lines 217-230 + delete modal 1113-1140)', () => {
    it('deletes the user and removes the row after confirming', async () => {
      setupMocks()
      render(<AdminUsersPage />)
      await waitForUserRow('John Doe')

      // Row delete button (TrashIcon) sets showDeleteConfirm. The row has a
      // verify button (with a title) and a delete button (no title); pick the
      // one that is not the verify button.
      const row = rowFor('John Doe')
      const deleteBtn = within(row)
        .getAllByRole('button')
        .find((b) => b.getAttribute('title') !== 'admin.usersPage.verifyEmail')!
      await userEvent.click(deleteBtn)

      // Confirm modal appears; click the destructive confirm button.
      const confirmBtn = await screen.findByText('admin.usersPage.delete')
      await userEvent.click(confirmBtn)

      await waitFor(() => {
        expect(api.deleteUser).toHaveBeenCalledWith('user-2')
      })
      // Row gone after state update.
      await waitFor(() => {
        expect(screen.queryByText('John Doe')).not.toBeInTheDocument()
      })
    })

    it('shows an error and keeps the row when delete rejects', async () => {
      setupMocks()
      ;(api.deleteUser as jest.Mock).mockRejectedValue(
        new Error('cannot delete')
      )
      render(<AdminUsersPage />)
      await waitForUserRow('John Doe')

      const row = rowFor('John Doe')
      const deleteBtn = within(row)
        .getAllByRole('button')
        .find((b) => b.getAttribute('title') !== 'admin.usersPage.verifyEmail')!
      await userEvent.click(deleteBtn)
      await userEvent.click(await screen.findByText('admin.usersPage.delete'))

      await waitFor(() => {
        expect(screen.getByText('cannot delete')).toBeInTheDocument()
      })
      // Row still present (no successful filter).
      expect(screen.getByText('John Doe')).toBeInTheDocument()
    })
  })

  describe('handleBulkVerifyEmails (lines 232-298)', () => {
    it('verifies selected users against the active org and shows the summary', async () => {
      const showError = jest.fn()
      // organizations=[mockOrg] auto-selects selectedOrganization on mount, so
      // orgId resolves from selectedOrganization?.id (line 239). (The TUM-find
      // fallback at 243-246 is not reachable here because the auto-select
      // effect always populates selectedOrganization when orgs exist.)
      setupMocks({ showError, currentOrganization: null })
      render(<AdminUsersPage />)
      await waitForUserRow('John Doe')

      // Select-all via the header checkbox (first checkbox in the table head).
      const checkboxes = screen.getAllByRole('checkbox')
      await userEvent.click(checkboxes[0]) // header select-all

      // Bulk bar appears; click bulkVerifyEmails.
      const bulkBtn = await screen.findByText(
        'admin.usersPage.bulkVerifyEmails'
      )
      await userEvent.click(bulkBtn)

      await waitFor(() => {
        expect(organizationsAPI.bulkVerifyMemberEmails).toHaveBeenCalledWith(
          'org-1', // resolved selected org id
          expect.arrayContaining(['admin-1', 'user-2']),
          'admin.usersPage.bulkVerifyReason'
        )
      })
      // Success summary toast.
      await waitFor(() => {
        expect(showError).toHaveBeenCalledWith(
          'admin.usersPage.bulkVerifyResult',
          'admin.usersPage.bulkVerifyComplete'
        )
      })
    })

    it('shows the bulk-verify error toast when the API rejects', async () => {
      const showError = jest.fn()
      setupMocks({ showError, currentOrganization: null })
      ;(organizationsAPI.bulkVerifyMemberEmails as jest.Mock).mockRejectedValue(
        new Error('bulk failed')
      )
      render(<AdminUsersPage />)
      await waitForUserRow('John Doe')

      await userEvent.click(screen.getAllByRole('checkbox')[0])
      await userEvent.click(
        await screen.findByText('admin.usersPage.bulkVerifyEmails')
      )

      await waitFor(() => {
        expect(showError).toHaveBeenCalledWith(
          'admin.usersPage.bulkVerifyFailed',
          'admin.usersPage.bulkVerifyError'
        )
      })
    })

    it('errors with noOrgsAvailable when superadmin has no organizations', async () => {
      const showError = jest.fn()
      setupMocks({ showError, organizations: [], currentOrganization: null })
      render(<AdminUsersPage />)
      await waitForUserRow('John Doe')

      await userEvent.click(screen.getAllByRole('checkbox')[0])
      await userEvent.click(
        await screen.findByText('admin.usersPage.bulkVerifyEmails')
      )

      await waitFor(() => {
        expect(showError).toHaveBeenCalledWith(
          'admin.usersPage.noOrgsAvailable',
          'admin.usersPage.orgRequired'
        )
      })
      expect(organizationsAPI.bulkVerifyMemberEmails).not.toHaveBeenCalled()
    })
  })

  describe('handleVerifyEmail via per-row verify button (lines 152-179)', () => {
    it('verifies an unverified user and shows the success toast (users tab)', async () => {
      const showError = jest.fn()
      setupMocks({ showError })
      render(<AdminUsersPage />)
      await waitForUserRow('John Doe')

      // The verify (CheckIcon) button only renders for unverified users.
      // John Doe is unverified; his row has [checkbox, verify, delete] buttons.
      const row = rowFor('John Doe')
      const verifyBtn = within(row).getByTitle('admin.usersPage.verifyEmail')
      await userEvent.click(verifyBtn)

      // Mocked modal renders; confirm drives handleVerifyEmail.
      const confirm = await screen.findByTestId('evm-confirm')
      await userEvent.click(confirm)

      await waitFor(() => {
        expect(api.verifyUserEmail).toHaveBeenCalledWith('user-2')
        expect(showError).toHaveBeenCalledWith(
          'admin.usersPage.emailVerifiedSuccess',
          'admin.usersPage.successTitle'
        )
      })
    })

    it('shows the failure toast when verify rejects', async () => {
      const showError = jest.fn()
      setupMocks({ showError })
      ;(api.verifyUserEmail as jest.Mock).mockRejectedValue(
        new Error('verify failed')
      )
      render(<AdminUsersPage />)
      await waitForUserRow('John Doe')

      const row = rowFor('John Doe')
      await userEvent.click(
        within(row).getByTitle('admin.usersPage.verifyEmail')
      )
      await userEvent.click(await screen.findByTestId('evm-confirm'))

      await waitFor(() => {
        expect(showError).toHaveBeenCalledWith(
          'admin.usersPage.emailVerifyFailed',
          'admin.usersPage.errorTitle'
        )
      })
    })
  })

  describe('Organizations tab handlers', () => {
    async function renderOrgTab(overrides: Record<string, any> = {}) {
      ;(mockApiClient.getOrganizationMembers as jest.Mock).mockResolvedValue(
        mockMembers
      )
      ;(mockApiClient.listInvitations as jest.Mock).mockResolvedValue(
        mockInvitations
      )
      setupMocks(overrides)
      render(<AdminUsersPage />)
      // Switch to organizations tab.
      const orgTab = await screen.findByTestId('admin-organizations-tab')
      await userEvent.click(orgTab)
      // Member loads.
      await screen.findByText('jdoe@test.com')
    }

    it('handleRemoveMember: early-returns when confirmDelete resolves false', async () => {
      const confirmDelete = jest.fn().mockResolvedValue(false)
      await renderOrgTab({ confirmDelete })

      // The member row's last button is the remove (TrashIcon) button.
      const memberName = screen.getByText('John Doe')
      const memberBlock = memberName.closest('div.border-b') as HTMLElement
      const buttons = within(memberBlock).getAllByRole('button')
      await userEvent.click(buttons[buttons.length - 1])

      await waitFor(() => {
        expect(confirmDelete).toHaveBeenCalledWith('this member')
      })
      expect(mockApiClient.removeMember).not.toHaveBeenCalled()
    })

    it('handleRemoveMember: removes the member when confirmDelete resolves true', async () => {
      const confirmDelete = jest.fn().mockResolvedValue(true)
      await renderOrgTab({ confirmDelete })

      const memberBlock = screen
        .getByText('John Doe')
        .closest('div.border-b') as HTMLElement
      const buttons = within(memberBlock).getAllByRole('button')
      await userEvent.click(buttons[buttons.length - 1])

      await waitFor(() => {
        expect(mockApiClient.removeMember).toHaveBeenCalledWith(
          'org-1',
          'user-2'
        )
      })
    })

    it('handleOrgRoleChange: updates a member role via the role Select', async () => {
      await renderOrgTab()

      const memberBlock = screen
        .getByText('John Doe')
        .closest('div.border-b') as HTMLElement
      const roleSelect = within(memberBlock).getByRole('combobox')
      await userEvent.selectOptions(roleSelect, 'ORG_ADMIN')

      await waitFor(() => {
        expect(mockApiClient.updateMemberRole).toHaveBeenCalledWith(
          'org-1',
          'user-2',
          'ORG_ADMIN'
        )
      })
    })

    it('handleCancelInvitation: cancels a pending invitation', async () => {
      await renderOrgTab()

      const inviteRow = screen
        .getByText('invited@test.com')
        .closest('div.border-b') as HTMLElement
      const cancelBtn = within(inviteRow).getByText('admin.usersPage.cancel')
      await userEvent.click(cancelBtn)

      await waitFor(() => {
        expect(mockApiClient.cancelInvitation).toHaveBeenCalledWith('invite-1')
      })
    })

    it('handleEditOrgStart + handleEditOrgSave: saves edited org name/description', async () => {
      const refreshOrganizations = jest.fn()
      ;(mockApiClient.updateOrganization as jest.Mock).mockResolvedValue({
        ...mockOrg,
        name: 'TUM Renamed',
      })
      await renderOrgTab({ refreshOrganizations })

      // Start editing (Edit button -> handleEditOrgStart).
      await userEvent.click(screen.getByText('admin.usersPage.edit'))

      // Save (handleEditOrgSave).
      const saveBtn = await screen.findByText('admin.usersPage.save')
      await userEvent.click(saveBtn)

      await waitFor(() => {
        expect(mockApiClient.updateOrganization).toHaveBeenCalledWith(
          'org-1',
          expect.objectContaining({ name: expect.any(String) })
        )
        expect(refreshOrganizations).toHaveBeenCalled()
      })
    })

    it('handleEditOrgSave: shows error toast when update rejects', async () => {
      const showError = jest.fn()
      ;(mockApiClient.updateOrganization as jest.Mock).mockRejectedValue(
        new Error('update org failed')
      )
      await renderOrgTab({ showError })

      await userEvent.click(screen.getByText('admin.usersPage.edit'))
      await userEvent.click(await screen.findByText('admin.usersPage.save'))

      await waitFor(() => {
        expect(showError).toHaveBeenCalledWith(
          'admin.users.orgDetails.updateFailed',
          'admin.usersPage.orgUpdateFailed'
        )
      })
    })

    it('handleAddUserToOrganization: maps a 400 "already a member" error', async () => {
      const showError = jest.fn()
      ;(mockApiClient.addUserToOrganization as jest.Mock).mockRejectedValue({
        response: { status: 400, data: { detail: 'User is already a member' } },
      })
      await renderOrgTab({ showError })

      // Open the Add User modal.
      await userEvent.click(screen.getByText('admin.usersPage.addUser'))

      // Submit the add-user form. The submit button inside the modal has the
      // addUser label too; scope to the dialog form by finding the submit button.
      const submitButtons = screen.getAllByText('admin.usersPage.addUser')
      // The modal submit button is the last "Add User" labelled control.
      await userEvent.click(submitButtons[submitButtons.length - 1])

      await waitFor(() => {
        expect(showError).toHaveBeenCalledWith(
          'admin.users.addUser.alreadyMember',
          'admin.usersPage.addUserFailed'
        )
      })
    })

    it('handleAddUserToOrganization: maps a 403 permission error', async () => {
      const showError = jest.fn()
      ;(mockApiClient.addUserToOrganization as jest.Mock).mockRejectedValue({
        response: { status: 403, data: { detail: 'forbidden' } },
      })
      await renderOrgTab({ showError })

      await userEvent.click(screen.getByText('admin.usersPage.addUser'))
      const submitButtons = screen.getAllByText('admin.usersPage.addUser')
      await userEvent.click(submitButtons[submitButtons.length - 1])

      await waitFor(() => {
        expect(showError).toHaveBeenCalledWith(
          'admin.users.addUser.noPermission',
          'admin.usersPage.addUserFailed'
        )
      })
    })

    it('handleAddUserToOrganization: maps a 404 not-found error', async () => {
      const showError = jest.fn()
      ;(mockApiClient.addUserToOrganization as jest.Mock).mockRejectedValue({
        response: { status: 404, data: { detail: 'missing' } },
      })
      await renderOrgTab({ showError })

      await userEvent.click(screen.getByText('admin.usersPage.addUser'))
      const submitButtons = screen.getAllByText('admin.usersPage.addUser')
      await userEvent.click(submitButtons[submitButtons.length - 1])

      await waitFor(() => {
        expect(showError).toHaveBeenCalledWith(
          'admin.users.addUser.notFound',
          'admin.usersPage.addUserFailed'
        )
      })
    })
  })
})
