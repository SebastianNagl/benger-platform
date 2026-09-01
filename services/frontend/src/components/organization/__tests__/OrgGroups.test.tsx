/**
 * @jest-environment jsdom
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type * as React from 'react'
import { OrgGroups } from '../OrgGroups'

// Mock HeadlessUI Dialog (mirrors OrgApiKeys.test.tsx)
jest.mock('@headlessui/react', () => {
  const Dialog = ({ children, open, onClose, className }: any) => {
    if (!open) return null
    return (
      <div className={className} data-testid="dialog">
        {children}
      </div>
    )
  }
  // eslint-disable-next-line react/display-name
  Dialog.Panel = ({ children, className }: any) => (
    <div className={className}>{children}</div>
  )
  // eslint-disable-next-line react/display-name
  Dialog.Title = ({ children, className }: any) => (
    <h2 className={className}>{children}</h2>
  )
  return { Dialog }
})

// Mock heroicons
jest.mock('@heroicons/react/24/outline', () => ({
  PencilIcon: (props: any) => <svg {...props} data-testid="pencil-icon" />,
  TrashIcon: (props: any) => <svg {...props} data-testid="trash-icon" />,
  UserGroupIcon: (props: any) => (
    <svg {...props} data-testid="user-group-icon" />
  ),
  XMarkIcon: (props: any) => <svg {...props} data-testid="x-mark-icon" />,
}))

// Mock I18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, vars?: Record<string, any>) => {
      const translations: Record<string, string> = {
        'admin.organizations.groups.dialogTitle': 'Groups',
        'admin.organizations.groups.dialogDescription':
          'Organize members into groups.',
        'admin.organizations.groups.loading': 'Loading…',
        'admin.organizations.groups.noGroups':
          'This organization has no groups yet.',
        'admin.organizations.groups.createTitle': 'New group',
        'admin.organizations.groups.namePlaceholder': 'Group name',
        'admin.organizations.groups.descriptionPlaceholder':
          'Description (optional)',
        'admin.organizations.groups.create': 'Create group',
        'admin.organizations.groups.creating': 'Creating…',
        'admin.organizations.groups.created': 'Group created',
        'admin.organizations.groups.createFailed': 'Failed to create group',
        'admin.organizations.groups.updated': 'Group updated',
        'admin.organizations.groups.updateFailed': 'Failed to update group',
        'admin.organizations.groups.deleted': 'Group deleted',
        'admin.organizations.groups.deleteFailed': 'Failed to delete group',
        'admin.organizations.groups.edit': 'Edit',
        'admin.organizations.groups.delete': 'Delete',
        'admin.organizations.groups.save': 'Save',
        'admin.organizations.groups.saving': 'Saving…',
        'admin.organizations.groups.cancel': 'Cancel',
        'admin.organizations.groups.inactiveBadge': 'Inactive',
        'admin.organizations.groups.activeLabel': 'Group is active',
        'admin.organizations.groups.memberCount': '{count} members',
        'admin.organizations.groups.groupAdminBadge': 'Group admin',
        'admin.organizations.groups.members': 'Members',
        'admin.organizations.groups.membersTitle': 'Members: {name}',
        'admin.organizations.groups.back': 'Back to overview',
        'admin.organizations.groups.loadMembersFailed':
          'Failed to load group members',
        'admin.organizations.groups.noMembers':
          'This group has no members yet.',
        'admin.organizations.groups.addMemberLabel': 'Add member',
        'admin.organizations.groups.addMemberPlaceholder': 'Select a member…',
        'admin.organizations.groups.noAvailableMembers':
          'All organization members already belong to this group.',
        'admin.organizations.groups.addAsGroupAdmin': 'As group admin',
        'admin.organizations.groups.add': 'Add',
        'admin.organizations.groups.adding': 'Adding…',
        'admin.organizations.groups.memberAdded': 'Member added',
        'admin.organizations.groups.addMemberFailed': 'Failed to add member',
        'admin.organizations.groups.memberRemoved': 'Member removed',
        'admin.organizations.groups.removeMemberFailed':
          'Failed to remove member',
        'admin.organizations.groups.memberUpdated': 'Member updated',
        'admin.organizations.groups.updateMemberFailed':
          'Failed to update member',
        'admin.organizations.groups.groupAdminToggle': 'Group admin',
        'admin.organizations.groups.remove': 'Remove',
        'common.done': 'Done',
      }
      let result = translations[key] || key
      if (vars) {
        Object.entries(vars).forEach(([k, v]) => {
          result = result.replace(`{${k}}`, String(v))
        })
      }
      return result
    },
    locale: 'en',
  }),
}))

// Mock shared Button
jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, disabled, variant, ...props }: any) => (
    <button
      onClick={onClick}
      disabled={disabled}
      data-variant={variant}
      {...props}
    >
      {children}
    </button>
  ),
}))

const mockGetGroups = jest.fn()
const mockCreateGroup = jest.fn()
const mockUpdateGroup = jest.fn()
const mockDeleteGroup = jest.fn()
const mockGetGroupMembers = jest.fn()
const mockAddGroupMember = jest.fn()
const mockUpdateGroupMember = jest.fn()
const mockRemoveGroupMember = jest.fn()
const mockGetOrganizationMembers = jest.fn()

jest.mock('@/lib/api/organizations', () => ({
  organizationsAPI: {
    getGroups: (...args: any[]) => mockGetGroups(...args),
    createGroup: (...args: any[]) => mockCreateGroup(...args),
    updateGroup: (...args: any[]) => mockUpdateGroup(...args),
    deleteGroup: (...args: any[]) => mockDeleteGroup(...args),
    getGroupMembers: (...args: any[]) => mockGetGroupMembers(...args),
    addGroupMember: (...args: any[]) => mockAddGroupMember(...args),
    updateGroupMember: (...args: any[]) => mockUpdateGroupMember(...args),
    removeGroupMember: (...args: any[]) => mockRemoveGroupMember(...args),
    getOrganizationMembers: (...args: any[]) =>
      mockGetOrganizationMembers(...args),
  },
}))

const groupFixture = (overrides: Record<string, any> = {}) => ({
  id: 'grp-1',
  organization_id: 'org-1',
  name: 'Chair of Civil Law',
  description: 'The Zivilrecht chair',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: null,
  member_count: 3,
  is_member: true,
  is_group_admin: false,
  ...overrides,
})

const memberFixture = (overrides: Record<string, any> = {}) => ({
  id: 'gm-1',
  group_id: 'grp-1',
  user_id: 'user-2',
  is_group_admin: false,
  created_at: '2026-01-02T00:00:00Z',
  user_name: 'Grete Gruppe',
  user_email: 'grete@example.com',
  org_role: 'CONTRIBUTOR',
  ...overrides,
})

function renderOrgGroups(
  props: Partial<React.ComponentProps<typeof OrgGroups>> = {}
) {
  return render(
    <OrgGroups
      organizationId="org-1"
      isAdmin={true}
      open={true}
      onOpenChange={jest.fn()}
      {...props}
    />
  )
}

describe('OrgGroups', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetGroups.mockResolvedValue([])
    mockGetGroupMembers.mockResolvedValue([])
    mockGetOrganizationMembers.mockResolvedValue([])
  })

  describe('group list', () => {
    it('renders groups with description, member count and inactive badge', async () => {
      mockGetGroups.mockResolvedValue([
        groupFixture(),
        groupFixture({
          id: 'grp-2',
          name: 'Old Chair',
          description: null,
          is_active: false,
          member_count: 0,
          is_member: false,
        }),
      ])

      renderOrgGroups()

      await waitFor(() => {
        expect(screen.getByText('Chair of Civil Law')).toBeInTheDocument()
      })
      expect(mockGetGroups).toHaveBeenCalledWith('org-1')
      expect(screen.getByText('The Zivilrecht chair')).toBeInTheDocument()
      expect(screen.getByText('3 members')).toBeInTheDocument()
      expect(screen.getByText('Old Chair')).toBeInTheDocument()
      expect(screen.getByText('Inactive')).toBeInTheDocument()
    })

    it('shows the empty state when the org has no groups', async () => {
      renderOrgGroups()

      await waitFor(() => {
        expect(
          screen.getByText('This organization has no groups yet.')
        ).toBeInTheDocument()
      })
    })

    it('hides member count when it is null (annotator caller shape)', async () => {
      mockGetGroups.mockResolvedValue([groupFixture({ member_count: null })])

      renderOrgGroups()

      await waitFor(() => {
        expect(screen.getByText('Chair of Civil Law')).toBeInTheDocument()
      })
      expect(screen.queryByText(/members$/)).not.toBeInTheDocument()
    })
  })

  describe('create group (org admin)', () => {
    it('creates a group and refreshes the list', async () => {
      mockCreateGroup.mockResolvedValue(groupFixture({ id: 'grp-new' }))

      renderOrgGroups()

      await waitFor(() => {
        expect(screen.getByTestId('group-create-name')).toBeInTheDocument()
      })

      fireEvent.change(screen.getByTestId('group-create-name'), {
        target: { value: 'New Chair' },
      })
      fireEvent.change(screen.getByTestId('group-create-description'), {
        target: { value: 'A brand new chair' },
      })
      fireEvent.click(screen.getByTestId('group-create-submit'))

      await waitFor(() => {
        expect(mockCreateGroup).toHaveBeenCalledWith('org-1', {
          name: 'New Chair',
          description: 'A brand new chair',
        })
      })
      expect(screen.getByText('Group created')).toBeInTheDocument()
      // Initial load + refresh after create
      expect(mockGetGroups).toHaveBeenCalledTimes(2)
    })

    it('surfaces the API detail on a duplicate-name conflict', async () => {
      mockCreateGroup.mockRejectedValue({
        response: { data: { detail: 'Group name already exists' } },
      })

      renderOrgGroups()

      await waitFor(() => {
        expect(screen.getByTestId('group-create-name')).toBeInTheDocument()
      })
      fireEvent.change(screen.getByTestId('group-create-name'), {
        target: { value: 'Chair of Civil Law' },
      })
      fireEvent.click(screen.getByTestId('group-create-submit'))

      await waitFor(() => {
        expect(
          screen.getByText('Group name already exists')
        ).toBeInTheDocument()
      })
    })

    it('does not offer the create form to group admins', async () => {
      mockGetGroups.mockResolvedValue([groupFixture({ is_group_admin: true })])

      renderOrgGroups({ isAdmin: false, canManageGroups: true })

      await waitFor(() => {
        expect(screen.getByText('Chair of Civil Law')).toBeInTheDocument()
      })
      expect(screen.queryByTestId('group-create-name')).not.toBeInTheDocument()
      expect(
        screen.queryByTestId('group-delete-grp-1')
      ).not.toBeInTheDocument()
      expect(screen.queryByTestId('group-edit-grp-1')).not.toBeInTheDocument()
      // But member management of their own group stays available.
      expect(screen.getByTestId('group-members-grp-1')).toBeInTheDocument()
    })
  })

  describe('delete group', () => {
    it('shows the 409 detail text when the group still has attachments', async () => {
      mockGetGroups.mockResolvedValue([groupFixture()])
      mockDeleteGroup.mockRejectedValue({
        response: {
          data: {
            detail:
              'Group still has 2 project attachments and 1 API key; detach them first.',
          },
        },
      })

      renderOrgGroups()

      await waitFor(() => {
        expect(screen.getByTestId('group-delete-grp-1')).toBeInTheDocument()
      })
      fireEvent.click(screen.getByTestId('group-delete-grp-1'))

      await waitFor(() => {
        expect(
          screen.getByText(
            'Group still has 2 project attachments and 1 API key; detach them first.'
          )
        ).toBeInTheDocument()
      })
      expect(mockDeleteGroup).toHaveBeenCalledWith('org-1', 'grp-1')
    })

    it('deletes and refreshes on success', async () => {
      mockGetGroups.mockResolvedValue([groupFixture()])
      mockDeleteGroup.mockResolvedValue({ message: 'ok' })

      renderOrgGroups()

      await waitFor(() => {
        expect(screen.getByTestId('group-delete-grp-1')).toBeInTheDocument()
      })
      fireEvent.click(screen.getByTestId('group-delete-grp-1'))

      await waitFor(() => {
        expect(screen.getByText('Group deleted')).toBeInTheDocument()
      })
      expect(mockGetGroups).toHaveBeenCalledTimes(2)
    })
  })

  describe('member management', () => {
    beforeEach(() => {
      mockGetGroups.mockResolvedValue([groupFixture()])
      mockGetGroupMembers.mockResolvedValue([memberFixture()])
      mockGetOrganizationMembers.mockResolvedValue([
        {
          id: 'om-1',
          user_id: 'user-2',
          organization_id: 'org-1',
          role: 'CONTRIBUTOR',
          is_active: true,
          joined_at: '2026-01-01T00:00:00Z',
          user_name: 'Grete Gruppe',
          user_email: 'grete@example.com',
        },
        {
          id: 'om-2',
          user_id: 'user-3',
          organization_id: 'org-1',
          role: 'ANNOTATOR',
          is_active: true,
          joined_at: '2026-01-01T00:00:00Z',
          user_name: 'Anna Annotator',
          user_email: 'anna@example.com',
        },
      ])
    })

    async function openMembers() {
      renderOrgGroups()
      await waitFor(() => {
        expect(screen.getByTestId('group-members-grp-1')).toBeInTheDocument()
      })
      fireEvent.click(screen.getByTestId('group-members-grp-1'))
      await waitFor(() => {
        expect(screen.getByTestId('group-member-user-2')).toBeInTheDocument()
      })
    }

    it('lists group members with email and org role', async () => {
      await openMembers()

      expect(mockGetGroupMembers).toHaveBeenCalledWith('org-1', 'grp-1')
      expect(mockGetOrganizationMembers).toHaveBeenCalledWith('org-1')
      expect(
        screen.getByText('grete@example.com · CONTRIBUTOR')
      ).toBeInTheDocument()
    })

    it('excludes existing group members from the add picker', async () => {
      await openMembers()

      const select = screen.getByTestId(
        'group-add-member-select'
      ) as HTMLSelectElement
      const optionValues = Array.from(select.options).map((o) => o.value)
      expect(optionValues).toContain('user-3')
      expect(optionValues).not.toContain('user-2')
    })

    it('adds a member (optionally as group admin)', async () => {
      mockAddGroupMember.mockResolvedValue(
        memberFixture({ user_id: 'user-3', id: 'gm-2' })
      )
      await openMembers()

      fireEvent.change(screen.getByTestId('group-add-member-select'), {
        target: { value: 'user-3' },
      })
      fireEvent.click(screen.getByTestId('group-add-member-admin-checkbox'))
      fireEvent.click(screen.getByTestId('group-add-member-submit'))

      await waitFor(() => {
        expect(mockAddGroupMember).toHaveBeenCalledWith('org-1', 'grp-1', {
          user_id: 'user-3',
          is_group_admin: true,
        })
      })
      expect(screen.getByText('Member added')).toBeInTheDocument()
    })

    it('removes a member', async () => {
      mockRemoveGroupMember.mockResolvedValue({ message: 'ok' })
      await openMembers()

      fireEvent.click(screen.getByTestId('group-member-remove-user-2'))

      await waitFor(() => {
        expect(mockRemoveGroupMember).toHaveBeenCalledWith(
          'org-1',
          'grp-1',
          'user-2'
        )
      })
      expect(screen.getByText('Member removed')).toBeInTheDocument()
    })

    it('toggles the group-admin flag', async () => {
      mockUpdateGroupMember.mockResolvedValue(
        memberFixture({ is_group_admin: true })
      )
      await openMembers()

      fireEvent.click(screen.getByTestId('group-member-admin-toggle-user-2'))

      await waitFor(() => {
        expect(mockUpdateGroupMember).toHaveBeenCalledWith(
          'org-1',
          'grp-1',
          'user-2',
          { is_group_admin: true }
        )
      })
    })

    it('hides member controls on groups the group admin does not administrate', async () => {
      mockGetGroups.mockResolvedValue([
        groupFixture({ is_group_admin: false, is_member: true }),
      ])

      renderOrgGroups({ isAdmin: false, canManageGroups: true })

      await waitFor(() => {
        expect(screen.getByText('Chair of Civil Law')).toBeInTheDocument()
      })
      expect(
        screen.queryByTestId('group-members-grp-1')
      ).not.toBeInTheDocument()
    })

    it('surfaces an error banner when the member list fails to load', async () => {
      mockGetGroups.mockResolvedValue([groupFixture()])
      mockGetGroupMembers.mockRejectedValue({
        response: { data: { detail: 'boom' } },
      })

      renderOrgGroups()
      await waitFor(() => {
        expect(screen.getByTestId('group-members-grp-1')).toBeInTheDocument()
      })
      fireEvent.click(screen.getByTestId('group-members-grp-1'))

      await waitFor(() => {
        expect(screen.getByTestId('org-groups-message')).toHaveTextContent(
          'boom'
        )
      })
    })

    it('surfaces API details when add/toggle/remove fail', async () => {
      mockGetGroups.mockResolvedValue([groupFixture()])
      mockGetGroupMembers.mockResolvedValue([memberFixture()])
      mockGetOrganizationMembers.mockResolvedValue([
        {
          user_id: 'user-9',
          user_name: 'Neu Nutzer',
          user_email: 'neu@example.com',
        },
      ])
      mockAddGroupMember.mockRejectedValue({
        response: { data: { detail: 'not an org member' } },
      })
      mockUpdateGroupMember.mockRejectedValue(new Error('nope'))
      mockRemoveGroupMember.mockRejectedValue(new Error('nope'))

      renderOrgGroups()
      await waitFor(() => {
        expect(screen.getByTestId('group-members-grp-1')).toBeInTheDocument()
      })
      fireEvent.click(screen.getByTestId('group-members-grp-1'))
      await waitFor(() => {
        expect(screen.getByTestId('group-add-member-select')).toBeInTheDocument()
      })

      fireEvent.change(screen.getByTestId('group-add-member-select'), {
        target: { value: 'user-9' },
      })
      fireEvent.click(screen.getByTestId('group-add-member-submit'))
      await waitFor(() => {
        expect(screen.getByTestId('org-groups-message')).toHaveTextContent(
          'not an org member'
        )
      })

      fireEvent.click(screen.getByTestId('group-member-admin-toggle-user-2'))
      await waitFor(() => {
        expect(screen.getByTestId('org-groups-message')).toHaveTextContent(
          'Failed to update member'
        )
      })

      fireEvent.click(screen.getByTestId('group-member-remove-user-2'))
      await waitFor(() => {
        expect(screen.getByTestId('org-groups-message')).toHaveTextContent(
          'Failed to remove member'
        )
      })
    })
  })

  describe('edit group (org admin)', () => {
    it('renames, describes and deactivates a group via the inline form', async () => {
      mockGetGroups.mockResolvedValue([groupFixture()])
      mockUpdateGroup.mockResolvedValue(groupFixture({ name: 'Neu' }))

      renderOrgGroups()
      await waitFor(() => {
        expect(screen.getByTestId('group-edit-grp-1')).toBeInTheDocument()
      })
      fireEvent.click(screen.getByTestId('group-edit-grp-1'))

      fireEvent.change(screen.getByTestId('group-edit-name-grp-1'), {
        target: { value: 'Lehrstuhl Neu' },
      })
      fireEvent.change(screen.getByTestId('group-edit-description-grp-1'), {
        target: { value: 'Umbenannt' },
      })
      fireEvent.click(screen.getByTestId('group-edit-active-grp-1'))
      fireEvent.click(screen.getByTestId('group-edit-save-grp-1'))

      await waitFor(() => {
        expect(mockUpdateGroup).toHaveBeenCalledWith('org-1', 'grp-1', {
          name: 'Lehrstuhl Neu',
          description: 'Umbenannt',
          is_active: false,
        })
      })
      // List refreshed after the save.
      expect(mockGetGroups).toHaveBeenCalledTimes(2)
    })

    it('keeps the form open and shows the API detail on a failed save', async () => {
      mockGetGroups.mockResolvedValue([groupFixture()])
      mockUpdateGroup.mockRejectedValue({
        response: { data: { detail: 'name already taken' } },
      })

      renderOrgGroups()
      await waitFor(() => {
        expect(screen.getByTestId('group-edit-grp-1')).toBeInTheDocument()
      })
      fireEvent.click(screen.getByTestId('group-edit-grp-1'))
      fireEvent.click(screen.getByTestId('group-edit-save-grp-1'))

      await waitFor(() => {
        expect(screen.getByTestId('org-groups-message')).toHaveTextContent(
          'name already taken'
        )
      })
      expect(screen.getByTestId('group-edit-name-grp-1')).toBeInTheDocument()
    })

    it('cancel closes the form without saving', async () => {
      mockGetGroups.mockResolvedValue([groupFixture()])

      renderOrgGroups()
      await waitFor(() => {
        expect(screen.getByTestId('group-edit-grp-1')).toBeInTheDocument()
      })
      fireEvent.click(screen.getByTestId('group-edit-grp-1'))
      fireEvent.click(screen.getByText('Cancel'))

      await waitFor(() => {
        expect(
          screen.queryByTestId('group-edit-name-grp-1')
        ).not.toBeInTheDocument()
      })
      expect(mockUpdateGroup).not.toHaveBeenCalled()
    })

    it('does not offer edit or delete to non-admins', async () => {
      mockGetGroups.mockResolvedValue([
        groupFixture({ is_group_admin: true }),
      ])

      renderOrgGroups({ isAdmin: false, canManageGroups: true })
      await waitFor(() => {
        expect(screen.getByText('Chair of Civil Law')).toBeInTheDocument()
      })
      expect(screen.queryByTestId('group-edit-grp-1')).not.toBeInTheDocument()
      expect(
        screen.queryByTestId('group-delete-grp-1')
      ).not.toBeInTheDocument()
    })
  })
})
