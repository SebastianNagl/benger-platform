/**
 * @jest-environment jsdom
 */

import { EmailVerificationModal } from '@/components/admin/EmailVerificationModal'
import { useAuth } from '@/contexts/AuthContext'
import { useDeleteConfirm, useErrorAlert } from '@/hooks/useDialogs'
import { api, User } from '@/lib/api'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { GlobalUsersTab } from '../GlobalUsersTab'

// Mock modules
jest.mock('@/contexts/AuthContext')
jest.mock('@/hooks/useDialogs', () => ({
  useErrorAlert: jest.fn(),
  useDeleteConfirm: jest.fn(),
}))

// Create stable mock functions outside the mock to prevent recreation on each call
const mockT = (key: string, _defaultVal?: string | Record<string, any>, vars?: Record<string, any>) => {
  const translations: Record<string, string> = {
    'admin.users.loading': 'Loading users...',
    'admin.users.updating': 'Updating...',
    'admin.users.deleting': 'Deleting...',
    'admin.users.updateFailed': 'Failed to update user superadmin status',
    'admin.users.deleteFailed': 'Failed to delete user',
    'admin.users.regularUser': 'Regular User',
    'admin.users.noPermission': 'You do not have permission to manage users.',
    'admin.users.columnUser': 'User',
    'admin.users.columnEmail': 'Email',
    'admin.users.columnEmailVerification': 'Email Verification',
    'admin.users.columnSuperadminStatus': 'Superadmin Status',
    'admin.users.columnActions': 'Actions',
    'admin.users.verified': 'Verified',
    'admin.users.unverified': 'Unverified',
    'admin.users.adminMethod': 'admin',
    'admin.users.verifyEmail': 'Verify Email',
    'admin.users.superadmin': 'Superadmin',
    'admin.users.userSelected': '{count} user selected',
    'admin.users.usersSelected': '{count} users selected',
    'admin.users.bulkVerifyEmails': 'Bulk Verify Emails',
    'admin.users.clearSelection': 'Clear Selection',
    'admin.users.emailVerifiedSuccess': 'Email verified successfully',
    'admin.users.successTitle': 'Success',
    'admin.users.emailVerifyFailed': 'Failed to verify email',
    'admin.users.errorTitle': 'Error',
    'admin.users.infoTitle': 'Info',
    'admin.users.noUnverifiedSelected': 'No unverified users selected',
    'admin.users.bulkVerifySuccess': 'Successfully verified {count} email',
    'admin.users.bulkVerifySuccessPlural': 'Successfully verified {count} emails',
    'admin.users.bulkVerifyFailed': 'Failed to verify some emails',
    'admin.users.deleteSuccess': 'User deleted successfully',
  }
  let result = translations[key] || key
  // Handle vars from second or third argument
  const actualVars = vars || (typeof _defaultVal === 'object' ? _defaultVal : undefined)
  if (actualVars) {
    Object.entries(actualVars).forEach(([k, v]) => {
      result = result.replace(`{${k}}`, String(v))
    })
  }
  return result
}

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: mockT,
    locale: 'en',
    isReady: true,
  }),
}))
jest.mock('@/lib/api', () => ({
  api: {
    getAllUsers: jest.fn(),
    verifyUserEmail: jest.fn(),
    updateUserSuperadminStatus: jest.fn(),
    deleteUser: jest.fn(),
  },
}))
jest.mock('@/components/admin/EmailVerificationModal', () => ({
  EmailVerificationModal: jest.fn(() => null),
}))

// Mock heroicons
jest.mock('@heroicons/react/24/outline', () => ({
  CheckCircleIcon: (props: any) => (
    <svg {...props} data-testid="check-circle-icon" />
  ),
  CheckIcon: (props: any) => <svg {...props} data-testid="check-icon" />,
  TrashIcon: (props: any) => <svg {...props} data-testid="trash-icon" />,
  XCircleIcon: (props: any) => <svg {...props} data-testid="x-circle-icon" />,
}))
jest.mock('@/components/shared/FilterToolbar', () => {
  const FilterToolbar = ({
    searchValue,
    onSearchChange,
    searchPlaceholder,
    searchLabel,
    clearLabel = 'Clear filters',
    onClearFilters,
    hasActiveFilters,
    leftExtras,
    rightExtras,
    children,
  }: any) => (
    <div data-testid="filter-toolbar">
      {leftExtras}
      {onSearchChange && (
        <input
          data-testid="filter-toolbar-search"
          type="search"
          placeholder={searchPlaceholder}
          title={searchPlaceholder || searchLabel}
          value={searchValue ?? ''}
          onChange={(e) => onSearchChange(e.target.value)}
        />
      )}
      <div data-testid="filter-toolbar-fields">{children}</div>
      {onClearFilters && (
        <button
          data-testid="filter-toolbar-clear"
          onClick={onClearFilters}
          disabled={!hasActiveFilters}
          title={clearLabel}
          aria-label={clearLabel}
        />
      )}
      {rightExtras}
    </div>
  )
  FilterToolbar.Field = ({ children }: any) => <div>{children}</div>
  return { FilterToolbar }
})


describe('GlobalUsersTab', () => {
  const mockShowError = jest.fn()
  const mockConfirmDelete = jest.fn()

  const mockUsers: User[] = [
    {
      id: 'user-1',
      username: 'testuser1',
      email: 'test1@example.com',
      name: 'Test User 1',
      is_superadmin: false,
      is_active: true,
      created_at: '2024-01-01',
      email_verified: true,
      email_verification_method: 'self',
    },
    {
      id: 'user-2',
      username: 'testuser2',
      email: 'test2@example.com',
      name: 'Test User 2',
      is_superadmin: false,
      is_active: true,
      created_at: '2024-01-02',
      email_verified: false,
      email_verification_method: null,
    },
    {
      id: 'user-3',
      username: 'admin',
      email: 'admin@example.com',
      name: 'Admin User',
      is_superadmin: true,
      is_active: true,
      created_at: '2024-01-03',
      email_verified: true,
      email_verification_method: 'admin',
    },
  ]

  const mockCurrentUser = mockUsers[2] // Admin user

  beforeEach(() => {
    jest.clearAllMocks()

    // Mock useAuth
    ;(useAuth as jest.Mock).mockReturnValue({
      user: mockCurrentUser,
      organizations: [{ id: 'org-1', role: 'ORG_ADMIN' }],
      isLoading: false,
    })

    // Mock useDialogs hooks
    ;(useErrorAlert as jest.Mock).mockReturnValue(mockShowError)
    ;(useDeleteConfirm as jest.Mock).mockReturnValue(mockConfirmDelete)

    // Mock API calls
    ;(api.getAllUsers as jest.Mock).mockResolvedValue(mockUsers)
    ;(api.verifyUserEmail as jest.Mock).mockResolvedValue({})
    ;(api.updateUserSuperadminStatus as jest.Mock).mockResolvedValue({
      id: 'user-1',
      is_superadmin: true,
    })
    ;(api.deleteUser as jest.Mock).mockResolvedValue({})
  })

  describe('Permissions and Authorization', () => {
    it('renders permission denied message for non-superadmin users', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { ...mockUsers[0], is_superadmin: false },
        organizations: [],
        isLoading: false,
      })

      render(<GlobalUsersTab />)

      expect(
        screen.getByText('You do not have permission to manage users.')
      ).toBeInTheDocument()
    })

    it('loads and displays users for superadmin', async () => {
      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(api.getAllUsers).toHaveBeenCalled()
      })

      expect(screen.getByText('Test User 1')).toBeInTheDocument()
      expect(screen.getByText('Test User 2')).toBeInTheDocument()
      expect(screen.getByText('Admin User')).toBeInTheDocument()
    })
  })

  describe('Loading and Error States', () => {
    it('displays loading state initially', () => {
      render(<GlobalUsersTab />)
      expect(screen.getByText('Loading users...')).toBeInTheDocument()
    })

    it('displays error message when fetch fails', async () => {
      const errorMessage = 'Failed to load users'
      ;(api.getAllUsers as jest.Mock).mockRejectedValue(new Error(errorMessage))

      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(screen.getByText(errorMessage)).toBeInTheDocument()
      })
    })
  })

  describe('User Table Rendering', () => {
    it('renders table with correct headers', async () => {
      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(screen.getByText('User')).toBeInTheDocument()
      })

      expect(screen.getByText('Email')).toBeInTheDocument()
      expect(screen.getByText('Email Verification')).toBeInTheDocument()
      expect(screen.getByText('Superadmin Status')).toBeInTheDocument()
      expect(screen.getByText('Actions')).toBeInTheDocument()
    })

    it('renders user information correctly', async () => {
      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(screen.getByText('Test User 1')).toBeInTheDocument()
      })

      expect(screen.getByText('testuser1')).toBeInTheDocument()
      expect(screen.getByText('test1@example.com')).toBeInTheDocument()
    })

    it('displays user avatar with first letter of name', async () => {
      render(<GlobalUsersTab />)

      await waitFor(() => {
        // Multiple users start with T, so check that at least one exists
        const avatarLetters = screen.getAllByText('T')
        expect(avatarLetters.length).toBeGreaterThan(0)
      })
    })
  })

  describe('Email Verification', () => {
    it('displays verified status correctly', async () => {
      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(screen.getAllByText('Verified')).toHaveLength(2)
      })
    })

    it('displays unverified status correctly', async () => {
      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(screen.getByText('Unverified')).toBeInTheDocument()
      })
    })

    it('shows admin verification method', async () => {
      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(screen.getByText('(admin)')).toBeInTheDocument()
      })
    })

    it('opens email verification modal when verify button is clicked', async () => {
      const user = userEvent.setup()
      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(screen.getByText('Unverified')).toBeInTheDocument()
      })

      const verifyButtons = screen.getAllByTestId('check-icon')
      await user.click(verifyButtons[0])

      expect(EmailVerificationModal).toHaveBeenCalledWith(
        expect.objectContaining({
          isOpen: true,
          user: mockUsers[1],
          action: 'verify',
        }),
        {}
      )
    })

    it('does not show verify button for already verified users', async () => {
      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(screen.getAllByText('Verified')).toHaveLength(2)
      })

      const verifyIcons = screen.queryAllByTestId('check-icon')
      // Only unverified users should have verify buttons
      expect(verifyIcons.length).toBeLessThan(mockUsers.length)
    })

    it('handles email verification successfully', async () => {
      const user = userEvent.setup()
      let modalOnConfirm: any
      ;(EmailVerificationModal as jest.Mock).mockImplementation((props) => {
        modalOnConfirm = props.onConfirm
        return null
      })

      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(api.getAllUsers).toHaveBeenCalled()
      })

      const verifyButtons = screen.getAllByTestId('check-icon')
      await user.click(verifyButtons[0])

      // Simulate modal confirmation
      await modalOnConfirm()

      await waitFor(() => {
        expect(api.verifyUserEmail).toHaveBeenCalledWith('user-2')
        expect(mockShowError).toHaveBeenCalledWith(
          'Email verified successfully',
          'Success'
        )
      })
    })

    it('handles email verification error', async () => {
      const user = userEvent.setup()
      let modalOnConfirm: any
      ;(EmailVerificationModal as jest.Mock).mockImplementation((props) => {
        modalOnConfirm = props.onConfirm
        return null
      })
      ;(api.verifyUserEmail as jest.Mock).mockRejectedValue(
        new Error('Verification failed')
      )

      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(api.getAllUsers).toHaveBeenCalled()
      })

      const verifyButtons = screen.getAllByTestId('check-icon')
      await user.click(verifyButtons[0])

      await modalOnConfirm()

      await waitFor(() => {
        expect(mockShowError).toHaveBeenCalledWith(
          'Failed to verify email',
          'Error'
        )
      })
    })
  })

  describe('Bulk Operations', () => {
    it('shows bulk actions bar when users are selected', async () => {
      const user = userEvent.setup()
      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(screen.getByText('Test User 1')).toBeInTheDocument()
      })

      const checkboxes = screen.getAllByRole('checkbox')
      await user.click(checkboxes[1]) // First user checkbox (not the header)

      expect(screen.getByText('1 user selected')).toBeInTheDocument()
      expect(screen.getByText('Bulk Verify Emails')).toBeInTheDocument()
    })

    it('selects all users when header checkbox is clicked', async () => {
      const user = userEvent.setup()
      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(screen.getByText('Test User 1')).toBeInTheDocument()
      })

      const checkboxes = screen.getAllByRole('checkbox')
      await user.click(checkboxes[0]) // Header checkbox

      expect(screen.getByText('3 users selected')).toBeInTheDocument()
    })

    it('clears selection when clear button is clicked', async () => {
      const user = userEvent.setup()
      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(screen.getByText('Test User 1')).toBeInTheDocument()
      })

      const checkboxes = screen.getAllByRole('checkbox')
      await user.click(checkboxes[1])

      expect(screen.getByText('1 user selected')).toBeInTheDocument()

      const clearButton = screen.getByText('Clear Selection')
      await user.click(clearButton)

      expect(screen.queryByText('1 user selected')).not.toBeInTheDocument()
    })

    it('handles bulk email verification', async () => {
      const user = userEvent.setup()
      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(screen.getByText('Test User 2')).toBeInTheDocument()
      })

      const userRow = screen.getByText('Test User 2').closest('tr')!
      const rowCheckbox = within(userRow).getByRole('checkbox')
      await user.click(rowCheckbox)

      const bulkVerifyButton = screen.getByText('Bulk Verify Emails')
      await user.click(bulkVerifyButton)

      await waitFor(() => {
        expect(api.verifyUserEmail).toHaveBeenCalledWith('user-2')
        expect(mockShowError).toHaveBeenCalledWith(
          'Successfully verified 1 email',
          'Success'
        )
      })
    })

    it('shows info message when no unverified users are selected', async () => {
      const user = userEvent.setup()
      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(screen.getByText('Test User 1')).toBeInTheDocument()
      })

      const checkboxes = screen.getAllByRole('checkbox')
      await user.click(checkboxes[1]) // Select user-1 (already verified)

      const bulkVerifyButton = screen.getByText('Bulk Verify Emails')
      await user.click(bulkVerifyButton)

      expect(mockShowError).toHaveBeenCalledWith(
        'No unverified users selected',
        'Info'
      )
    })

    it('handles bulk verification with multiple users', async () => {
      const user = userEvent.setup()
      const multipleUnverifiedUsers: User[] = [
        ...mockUsers,
        {
          id: 'user-4',
          username: 'testuser4',
          email: 'test4@example.com',
          name: 'Test User 4',
          is_superadmin: false,
          is_active: true,
          created_at: '2024-01-04',
          email_verified: false,
          email_verification_method: null,
        },
      ]
      ;(api.getAllUsers as jest.Mock).mockResolvedValue(multipleUnverifiedUsers)

      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(screen.getByText('Test User 4')).toBeInTheDocument()
      })

      const checkboxes = screen.getAllByRole('checkbox')
      await user.click(checkboxes[0]) // Select all

      const bulkVerifyButton = screen.getByText('Bulk Verify Emails')
      await user.click(bulkVerifyButton)

      await waitFor(() => {
        expect(api.verifyUserEmail).toHaveBeenCalledTimes(2) // user-2 and user-4
        expect(mockShowError).toHaveBeenCalledWith(
          'Successfully verified 2 emails',
          'Success'
        )
      })
    })
  })

  describe('Superadmin Status Management', () => {
    it('displays superadmin status correctly', async () => {
      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(screen.getByText('Test User 1')).toBeInTheDocument()
      })

      const selects = screen.getAllByRole('combobox')
      expect(selects.length).toBeGreaterThan(0)
    })

    it('does not allow changing own superadmin status', async () => {
      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(screen.getByText('Admin User')).toBeInTheDocument()
      })

      // Current user's status should be text, not a select
      const adminTexts = screen.getAllByText('Superadmin')
      expect(adminTexts.length).toBeGreaterThan(0)
    })

    it('updates user superadmin status when changed', async () => {
      const user = userEvent.setup()
      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(screen.getByText('Test User 1')).toBeInTheDocument()
      })

      const userRow = screen.getByText('Test User 1').closest('tr')!
      const select = within(userRow).getByRole('combobox')
      await user.selectOptions(select, 'superadmin')

      await waitFor(() => {
        expect(api.updateUserSuperadminStatus).toHaveBeenCalledWith(
          'user-1',
          true
        )
      })
    })

    it('shows updating state while changing superadmin status', async () => {
      const user = userEvent.setup()
      ;(api.updateUserSuperadminStatus as jest.Mock).mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve({}), 100))
      )

      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(screen.getByText('Test User 1')).toBeInTheDocument()
      })

      const userRow = screen.getByText('Test User 1').closest('tr')!
      const select = within(userRow).getByRole('combobox')
      await user.selectOptions(select, 'superadmin')

      expect(screen.getByText('Updating...')).toBeInTheDocument()
    })

    it('handles superadmin status update error', async () => {
      const user = userEvent.setup()
      ;(api.updateUserSuperadminStatus as jest.Mock).mockRejectedValue(
        new Error('Update failed')
      )

      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(screen.getByText('Test User 1')).toBeInTheDocument()
      })

      const userRow = screen.getByText('Test User 1').closest('tr')!
      const select = within(userRow).getByRole('combobox')
      await user.selectOptions(select, 'superadmin')

      await waitFor(() => {
        expect(mockShowError).toHaveBeenCalledWith('Update failed', 'Error')
      })
    })

    it('refreshes user list when update returns invalid response', async () => {
      const user = userEvent.setup()
      ;(api.updateUserSuperadminStatus as jest.Mock).mockResolvedValue({})

      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(screen.getByText('Test User 1')).toBeInTheDocument()
      })

      const userRow = screen.getByText('Test User 1').closest('tr')!
      const select = within(userRow).getByRole('combobox')
      await user.selectOptions(select, 'superadmin')

      await waitFor(() => {
        // Called at least twice: once on mount, once to refresh after update
        // (React StrictMode or re-renders may cause additional calls)
        expect((api.getAllUsers as jest.Mock).mock.calls.length).toBeGreaterThanOrEqual(2)
      })
    })
  })

  describe('User Deletion', () => {
    it('does not show delete button for current user', async () => {
      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(screen.getByText('Admin User')).toBeInTheDocument()
      })

      const trashIcons = screen.queryAllByTestId('trash-icon')
      // Should be 2 trash icons for the 2 other users
      expect(trashIcons).toHaveLength(2)
    })

    it('shows delete button for other users', async () => {
      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(screen.getByText('Test User 1')).toBeInTheDocument()
      })

      const trashIcons = screen.getAllByTestId('trash-icon')
      expect(trashIcons.length).toBeGreaterThan(0)
    })

    it('opens confirmation dialog when delete is clicked', async () => {
      const user = userEvent.setup()
      mockConfirmDelete.mockResolvedValue(true)

      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(screen.getByText('Test User 1')).toBeInTheDocument()
      })

      const trashIcons = screen.getAllByTestId('trash-icon')
      await user.click(trashIcons[0])

      await waitFor(() => {
        expect(mockConfirmDelete).toHaveBeenCalledWith('user "Test User 1"')
      })
    })

    it('deletes user when confirmed', async () => {
      const user = userEvent.setup()
      mockConfirmDelete.mockResolvedValue(true)

      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(screen.getByText('Test User 1')).toBeInTheDocument()
      })

      const trashIcons = screen.getAllByTestId('trash-icon')
      await user.click(trashIcons[0])

      await waitFor(() => {
        expect(api.deleteUser).toHaveBeenCalledWith('user-1')
        expect(mockShowError).toHaveBeenCalledWith(
          'User deleted successfully',
          'Success'
        )
      })
    })

    it('does not delete user when cancelled', async () => {
      const user = userEvent.setup()
      mockConfirmDelete.mockResolvedValue(false)

      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(screen.getByText('Test User 1')).toBeInTheDocument()
      })

      const trashIcons = screen.getAllByTestId('trash-icon')
      await user.click(trashIcons[0])

      await waitFor(() => {
        expect(mockConfirmDelete).toHaveBeenCalled()
      })

      expect(api.deleteUser).not.toHaveBeenCalled()
    })

    it('handles delete error', async () => {
      const user = userEvent.setup()
      mockConfirmDelete.mockResolvedValue(true)
      ;(api.deleteUser as jest.Mock).mockRejectedValue(
        new Error('Delete failed')
      )

      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(screen.getByText('Test User 1')).toBeInTheDocument()
      })

      const trashIcons = screen.getAllByTestId('trash-icon')
      await user.click(trashIcons[0])

      await waitFor(() => {
        expect(mockShowError).toHaveBeenCalledWith('Delete failed', 'Error')
      })
    })

    it('shows deleting state during deletion', async () => {
      const user = userEvent.setup()
      mockConfirmDelete.mockResolvedValue(true)
      ;(api.deleteUser as jest.Mock).mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve({}), 100))
      )

      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(screen.getByText('Test User 1')).toBeInTheDocument()
      })

      const trashIcons = screen.getAllByTestId('trash-icon')
      await user.click(trashIcons[0])

      await waitFor(() => {
        expect(screen.getByText('Deleting...')).toBeInTheDocument()
      })
    })
  })

  describe('Email Verification Modal Integration', () => {
    it('closes modal when onClose is called', async () => {
      const user = userEvent.setup()
      let modalOnClose: any
      ;(EmailVerificationModal as jest.Mock).mockImplementation((props) => {
        modalOnClose = props.onClose
        return null
      })

      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(screen.getByText('Unverified')).toBeInTheDocument()
      })

      const verifyButtons = screen.getAllByTestId('check-icon')
      await user.click(verifyButtons[0])

      // Wait for modal to be called with isOpen: true
      await waitFor(() => {
        expect(EmailVerificationModal).toHaveBeenCalledWith(
          expect.objectContaining({
            isOpen: true,
          }),
          {}
        )
      })

      // Call onClose
      const callsBefore = (EmailVerificationModal as jest.Mock).mock.calls
        .length
      modalOnClose()

      // Modal should not be rendered anymore (conditional rendering)
      // so the mock call count should remain the same
      await waitFor(() => {
        const callsAfter = (EmailVerificationModal as jest.Mock).mock.calls
          .length
        // No new calls should be made because modal is not rendered when isOpen is false
        expect(callsAfter).toBe(callsBefore)
      })
    })

    it('passes correct user to modal', async () => {
      const user = userEvent.setup()
      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(screen.getByText('Unverified')).toBeInTheDocument()
      })

      const verifyButtons = screen.getAllByTestId('check-icon')
      await user.click(verifyButtons[0])

      // Wait for the modal to be called
      await waitFor(() => {
        expect(EmailVerificationModal).toHaveBeenCalledWith(
          expect.objectContaining({
            user: mockUsers[1],
          }),
          {}
        )
      })
    })
  })

  describe('Individual User Selection', () => {
    it('selects individual user when checkbox is clicked', async () => {
      const user = userEvent.setup()
      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(screen.getByText('Test User 1')).toBeInTheDocument()
      })

      const checkboxes = screen.getAllByRole('checkbox')
      const userCheckbox = checkboxes[1]

      expect(userCheckbox).not.toBeChecked()
      await user.click(userCheckbox)
      expect(userCheckbox).toBeChecked()
    })

    it('deselects individual user when checkbox is clicked again', async () => {
      const user = userEvent.setup()
      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(screen.getByText('Test User 1')).toBeInTheDocument()
      })

      const checkboxes = screen.getAllByRole('checkbox')
      const userCheckbox = checkboxes[1]

      await user.click(userCheckbox)
      expect(userCheckbox).toBeChecked()

      await user.click(userCheckbox)
      expect(userCheckbox).not.toBeChecked()
    })

    it('unchecks header checkbox when individual user is deselected', async () => {
      const user = userEvent.setup()
      render(<GlobalUsersTab />)

      await waitFor(() => {
        expect(screen.getByText('Test User 1')).toBeInTheDocument()
      })

      const checkboxes = screen.getAllByRole('checkbox')
      const headerCheckbox = checkboxes[0]
      const userCheckbox = checkboxes[1]

      // Select all
      await user.click(headerCheckbox)
      expect(headerCheckbox).toBeChecked()

      // Deselect one user
      await user.click(userCheckbox)
      expect(headerCheckbox).not.toBeChecked()
    })
  })
})
