/**
 * @jest-environment jsdom
 *
 * Per-group roles in the organization admin page: the invite and bulk invite
 * dialogs (group role select, org role labelled as such, group-admin mode
 * with the org role fixed to Annotator), the per-address result toasts, the
 * add-existing-user group option and the member list group chips.
 */

import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { OrganizationsTab } from '../OrganizationsTab'

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
  useSearchParams: () => ({ get: jest.fn(() => null), toString: () => '' }),
}))

const mockUseAuth = jest.fn()
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}))

// Keys come back verbatim; interpolation values are appended as JSON so the
// assertions can check them.
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, vars?: Record<string, unknown>) =>
      vars ? `${key} ${JSON.stringify(vars)}` : key,
    locale: 'en',
  }),
}))

const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: mockAddToast }),
}))

const mockShowError = jest.fn()
jest.mock('@/hooks/useDialogs', () => ({
  useErrorAlert: () => mockShowError,
  useDeleteConfirm: () => jest.fn().mockResolvedValue(true),
}))

jest.mock('@/lib/extensions/slots', () => ({
  useSlot: () => null,
}))

const mockSendInvitation = jest.fn()
const mockBulkInvite = jest.fn()
const mockGetGroups = jest.fn()
const mockAddUserToOrganization = jest.fn()
const mockAddGroupMember = jest.fn()
const mockGetAllUsers = jest.fn()
jest.mock('@/lib/api/organizations', () => ({
  organizationsAPI: {
    sendInvitation: (...a: any[]) => mockSendInvitation(...a),
    bulkInvite: (...a: any[]) => mockBulkInvite(...a),
    getGroups: (...a: any[]) => mockGetGroups(...a),
    addUserToOrganization: (...a: any[]) => mockAddUserToOrganization(...a),
    addGroupMember: (...a: any[]) => mockAddGroupMember(...a),
    getAllUsers: (...a: any[]) => mockGetAllUsers(...a),
    getOrganizationInvitations: jest.fn().mockResolvedValue([]),
    removeMember: jest.fn(),
    updateMemberRole: jest.fn(),
  },
}))

const mockApiClient = {
  getOrganizationMembers: jest.fn(),
  createOrganization: jest.fn(),
  updateOrganization: jest.fn(),
  deleteOrganization: jest.fn(),
}

const ORG = {
  id: 'org-1',
  name: 'Uni Saarland',
  slug: 'uds',
  description: '',
  is_active: true,
}

const groupRow = (overrides: Record<string, unknown>) => ({
  organization_id: 'org-1',
  description: null,
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: null,
  member_count: 2,
  is_member: true,
  my_role: null,
  ...overrides,
})

function setAuth(kind: 'orgAdmin' | 'groupAdmin' | 'superadmin') {
  const organizations =
    kind === 'groupAdmin'
      ? [
          {
            ...ORG,
            role: 'ANNOTATOR',
            groups: [
              { id: 'grp-a', name: 'LS A', role: 'ANNOTATOR', is_active: true },
              { id: 'grp-b', name: 'LS B', role: 'ORG_ADMIN', is_active: true },
            ],
          },
        ]
      : [{ ...ORG, role: 'ORG_ADMIN', groups: [] }]
  mockUseAuth.mockReturnValue({
    user: {
      id: 'me',
      username: 'me',
      email: 'me@example.com',
      is_superadmin: kind === 'superadmin',
      is_active: true,
    },
    organizations,
    refreshOrganizations: jest.fn(),
    apiClient: mockApiClient,
  })
  mockGetGroups.mockResolvedValue(
    kind === 'groupAdmin'
      ? [
          groupRow({ id: 'grp-a', name: 'LS A', my_role: 'ANNOTATOR' }),
          groupRow({ id: 'grp-b', name: 'LS B', my_role: 'ORG_ADMIN' }),
        ]
      : [
          groupRow({ id: 'grp-a', name: 'LS A', is_member: false }),
          groupRow({ id: 'grp-b', name: 'LS B', is_member: false }),
        ],
  )
}

const comboIn = (testId: string) =>
  within(screen.getByTestId(testId)).getByRole('combobox') as HTMLSelectElement

async function openInvite() {
  fireEvent.click(
    await screen.findByRole('button', {
      name: /admin\.organizations\.inviteMember/,
    }),
  )
  await screen.findByTestId('invite-group-section')
}

async function openBulk() {
  await openInvite()
  fireEvent.click(
    screen.getByRole('button', { name: 'admin.organizations.inviteMultiple' }),
  )
  await screen.findByTestId('bulk-invite-group-section')
}

describe('OrganizationsTab - per-group roles', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockApiClient.getOrganizationMembers.mockResolvedValue([])
    mockSendInvitation.mockResolvedValue({ id: 'inv-1' })
    mockBulkInvite.mockResolvedValue({
      queued: 1,
      skipped: 0,
      total: 1,
      results: [{ email: 'a@example.com', status: 'queued' }],
    })
  })

  describe('invite as org admin', () => {
    beforeEach(() => setAuth('orgAdmin'))

    it('asks only the org role without a group', async () => {
      render(<OrganizationsTab />)
      await openInvite()

      expect(
        screen.queryByTestId('invite-group-role-section'),
      ).not.toBeInTheDocument()
      expect(screen.getByTestId('invite-org-role-section')).toHaveTextContent(
        'admin.organizations.role',
      )
      // (The Select test double may add its own empty placeholder option.)
      expect(
        new Set(
          Array.from(comboIn('invite-group-section').options).map(
            (o) => o.value,
          ),
        ),
      ).toEqual(new Set(['', 'grp-a', 'grp-b']))
      // The old "invite as group admin" checkbox is gone.
      expect(
        screen.queryByTestId('invite-as-group-admin-checkbox'),
      ).not.toBeInTheDocument()

      fireEvent.change(screen.getByRole('textbox'), {
        target: { value: 'new@example.com' },
      })
      fireEvent.click(
        screen.getByRole('button', {
          name: 'admin.organizations.sendInvitation',
        }),
      )
      await waitFor(() =>
        expect(mockSendInvitation).toHaveBeenCalledWith('org-1', {
          email: 'new@example.com',
          role: 'ANNOTATOR',
        }),
      )
      expect(mockAddToast).toHaveBeenCalledWith(
        'toasts.admin.invitationSent',
        'success',
      )
    })

    it('shows the group role (default Annotator) next to the org role once a group is chosen', async () => {
      render(<OrganizationsTab />)
      await openInvite()

      // Raise the org role first: choosing a group resets it to Annotator.
      fireEvent.change(comboIn('invite-org-role-section'), {
        target: { value: 'CONTRIBUTOR' },
      })
      fireEvent.change(comboIn('invite-group-section'), {
        target: { value: 'grp-b' },
      })

      const groupRole = comboIn('invite-group-role-section')
      expect(groupRole.value).toBe('ANNOTATOR')
      expect(Array.from(groupRole.options).map((o) => o.value)).toEqual([
        'ANNOTATOR',
        'CONTRIBUTOR',
        'ORG_ADMIN',
      ])
      expect(screen.getByTestId('invite-group-role-section')).toHaveTextContent(
        'admin.organizations.groups.groupRoleLabel',
      )
      expect(screen.getByTestId('invite-org-role-section')).toHaveTextContent(
        'admin.organizations.groups.orgRoleLabel',
      )
      expect(comboIn('invite-org-role-section').value).toBe('ANNOTATOR')
      expect(screen.getByTestId('invite-role-hint')).toHaveTextContent(
        'admin.organizations.groups.roleScopeHint',
      )

      // Org admins may still raise the org role (incl. Admin).
      fireEvent.change(groupRole, { target: { value: 'ORG_ADMIN' } })
      fireEvent.change(comboIn('invite-org-role-section'), {
        target: { value: 'CONTRIBUTOR' },
      })
      fireEvent.change(screen.getByRole('textbox'), {
        target: { value: 'niklas@example.com' },
      })
      fireEvent.click(
        screen.getByRole('button', {
          name: 'admin.organizations.sendInvitation',
        }),
      )

      await waitFor(() =>
        expect(mockSendInvitation).toHaveBeenCalledWith('org-1', {
          email: 'niklas@example.com',
          role: 'CONTRIBUTOR',
          group_id: 'grp-b',
          group_role: 'ORG_ADMIN',
        }),
      )
    })

    it('says when an existing member was added to the group directly', async () => {
      mockSendInvitation.mockResolvedValue({
        status: 'added_to_group',
        email: 'niklas@example.com',
        group_id: 'grp-b',
      })
      render(<OrganizationsTab />)
      await openInvite()
      fireEvent.change(comboIn('invite-group-section'), {
        target: { value: 'grp-b' },
      })
      fireEvent.change(screen.getByRole('textbox'), {
        target: { value: 'niklas@example.com' },
      })
      fireEvent.click(
        screen.getByRole('button', {
          name: 'admin.organizations.sendInvitation',
        }),
      )

      await waitFor(() =>
        expect(mockAddToast).toHaveBeenCalledWith(
          'admin.organizations.inviteAddedToGroup {"email":"niklas@example.com"}',
          'success',
        ),
      )
      expect(mockAddToast).not.toHaveBeenCalledWith(
        'toasts.admin.invitationSent',
        'success',
      )
    })

    it('says when the person already is in the group', async () => {
      mockSendInvitation.mockResolvedValue({
        status: 'already_in_group',
        email: 'niklas@example.com',
        group_id: 'grp-b',
      })
      render(<OrganizationsTab />)
      await openInvite()
      fireEvent.change(comboIn('invite-group-section'), {
        target: { value: 'grp-b' },
      })
      fireEvent.change(screen.getByRole('textbox'), {
        target: { value: 'niklas@example.com' },
      })
      fireEvent.click(
        screen.getByRole('button', {
          name: 'admin.organizations.sendInvitation',
        }),
      )

      await waitFor(() =>
        expect(mockAddToast).toHaveBeenCalledWith(
          'admin.organizations.inviteAlreadyInGroup {"email":"niklas@example.com"}',
          'info',
        ),
      )
    })

    it('bulk invite sends the group role and lists every address that was not queued', async () => {
      mockBulkInvite.mockResolvedValue({
        queued: 1,
        skipped: 3,
        added_to_group: 1,
        total: 5,
        results: [
          { email: 'a@example.com', status: 'queued' },
          { email: 'b@example.com', status: 'added_to_group' },
          { email: 'c@example.com', status: 'already_in_group' },
          { email: 'd@example.com', status: 'pending' },
          { email: 'bad', status: 'invalid' },
        ],
      })
      render(<OrganizationsTab />)
      await openBulk()

      fireEvent.change(comboIn('bulk-invite-group-section'), {
        target: { value: 'grp-a' },
      })
      fireEvent.change(comboIn('bulk-invite-group-role-section'), {
        target: { value: 'CONTRIBUTOR' },
      })
      fireEvent.change(
        screen.getByPlaceholderText(
          'admin.organizations.bulkEmailsPlaceholder',
        ),
        {
          target: {
            value:
              'a@example.com, b@example.com, c@example.com, d@example.com, bad',
          },
        },
      )
      fireEvent.click(
        screen.getByRole('button', {
          name: 'admin.organizations.bulkInviteSubmit',
        }),
      )

      await waitFor(() =>
        expect(mockBulkInvite).toHaveBeenCalledWith('org-1', {
          emails: [
            'a@example.com',
            'b@example.com',
            'c@example.com',
            'd@example.com',
            'bad',
          ],
          role: 'ANNOTATOR',
          group_id: 'grp-a',
          group_role: 'CONTRIBUTOR',
        }),
      )
      await waitFor(() => expect(mockAddToast).toHaveBeenCalled())
      const [message, type, duration] = mockAddToast.mock.calls[0]
      expect(type).toBe('info')
      expect(duration).toBeGreaterThan(5000)
      expect(message.split('\n')).toEqual([
        'admin.organizations.bulkInviteSummaryWithGroup {"queued":1,"added":1,"skipped":3}',
        'b@example.com: admin.organizations.inviteStatus.added_to_group',
        'c@example.com: admin.organizations.inviteStatus.already_in_group',
        'd@example.com: admin.organizations.inviteStatus.pending',
        'bad: admin.organizations.inviteStatus.invalid',
      ])
    })

    it('bulk invite keeps the short success toast when everything was queued', async () => {
      render(<OrganizationsTab />)
      await openBulk()
      fireEvent.change(
        screen.getByPlaceholderText(
          'admin.organizations.bulkEmailsPlaceholder',
        ),
        { target: { value: 'a@example.com' } },
      )
      fireEvent.click(
        screen.getByRole('button', {
          name: 'admin.organizations.bulkInviteSubmit',
        }),
      )
      await waitFor(() =>
        expect(mockAddToast).toHaveBeenCalledWith(
          'admin.organizations.bulkInviteSummary {"queued":1,"skipped":0}',
          'success',
        ),
      )
    })
  })

  describe('invite as group admin (org role Annotator)', () => {
    beforeEach(() => setAuth('groupAdmin'))

    it('offers only the admin groups, hides the org role and forces Annotator', async () => {
      render(<OrganizationsTab />)
      await openInvite()

      // Pinned to the only admin group, no org-wide option.
      await waitFor(() =>
        expect(comboIn('invite-group-section').value).toBe('grp-b'),
      )
      expect(
        Array.from(comboIn('invite-group-section').options).map((o) => o.value),
      ).toEqual(['grp-b'])
      expect(
        screen.queryByTestId('invite-org-role-section'),
      ).not.toBeInTheDocument()
      expect(screen.getByTestId('invite-role-hint')).toHaveTextContent(
        'admin.organizations.groups.groupOnlyOrgRoleHint',
      )
      // Any group role, up to group Admin.
      const groupRole = comboIn('invite-group-role-section')
      expect(Array.from(groupRole.options).map((o) => o.value)).toContain(
        'ORG_ADMIN',
      )

      fireEvent.change(groupRole, { target: { value: 'CONTRIBUTOR' } })
      fireEvent.change(screen.getByRole('textbox'), {
        target: { value: 'hiwi@example.com' },
      })
      fireEvent.click(
        screen.getByRole('button', {
          name: 'admin.organizations.sendInvitation',
        }),
      )

      await waitFor(() =>
        expect(mockSendInvitation).toHaveBeenCalledWith('org-1', {
          email: 'hiwi@example.com',
          role: 'ANNOTATOR',
          group_id: 'grp-b',
          group_role: 'CONTRIBUTOR',
        }),
      )
    })

    it('bulk invite also sends org role Annotator', async () => {
      render(<OrganizationsTab />)
      await openBulk()
      await waitFor(() =>
        expect(comboIn('bulk-invite-group-section').value).toBe('grp-b'),
      )
      expect(
        screen.queryByTestId('bulk-invite-org-role-section'),
      ).not.toBeInTheDocument()

      fireEvent.change(
        screen.getByPlaceholderText(
          'admin.organizations.bulkEmailsPlaceholder',
        ),
        { target: { value: 'x@example.com' } },
      )
      fireEvent.click(
        screen.getByRole('button', {
          name: 'admin.organizations.bulkInviteSubmit',
        }),
      )
      await waitFor(() =>
        expect(mockBulkInvite).toHaveBeenCalledWith('org-1', {
          emails: ['x@example.com'],
          role: 'ANNOTATOR',
          group_id: 'grp-b',
          group_role: 'ANNOTATOR',
        }),
      )
    })
  })

  describe('add existing user (superadmin)', () => {
    beforeEach(() => {
      setAuth('superadmin')
      mockGetAllUsers.mockResolvedValue([
        { id: 'user-9', name: 'Niklas', email: 'niklas@example.com' },
      ])
      mockAddUserToOrganization.mockResolvedValue({ message: 'ok' })
      mockAddGroupMember.mockResolvedValue({})
    })

    async function openAddUser() {
      fireEvent.click(
        await screen.findByRole('button', {
          name: 'admin.organizations.addExistingUser',
        }),
      )
      await screen.findByTestId('add-user-group-section')
      await waitFor(() =>
        expect(
          screen.getByRole('option', { name: /Niklas/ }),
        ).toBeInTheDocument(),
      )
    }

    const userSelect = () =>
      screen
        .getByRole('option', { name: /Niklas/ })
        .closest('select') as HTMLSelectElement

    it('adds the user to the org and then to the chosen group with its role', async () => {
      render(<OrganizationsTab />)
      await openAddUser()

      fireEvent.change(userSelect(), { target: { value: 'user-9' } })
      fireEvent.change(comboIn('add-user-group-section'), {
        target: { value: 'grp-b' },
      })
      fireEvent.change(comboIn('add-user-group-role-section'), {
        target: { value: 'ORG_ADMIN' },
      })
      fireEvent.click(
        screen.getByRole('button', { name: 'admin.organizations.addUser' }),
      )

      await waitFor(() =>
        expect(mockAddGroupMember).toHaveBeenCalledWith('org-1', 'grp-b', {
          user_id: 'user-9',
          role: 'ORG_ADMIN',
        }),
      )
      expect(mockAddUserToOrganization).toHaveBeenCalledWith(
        'org-1',
        'user-9',
        'ANNOTATOR',
      )
      expect(
        mockAddUserToOrganization.mock.invocationCallOrder[0],
      ).toBeLessThan(mockAddGroupMember.mock.invocationCallOrder[0])
    })

    it('adds only to the org without a group', async () => {
      render(<OrganizationsTab />)
      await openAddUser()

      fireEvent.change(userSelect(), { target: { value: 'user-9' } })
      expect(
        screen.queryByTestId('add-user-group-role-section'),
      ).not.toBeInTheDocument()
      fireEvent.click(
        screen.getByRole('button', { name: 'admin.organizations.addUser' }),
      )

      await waitFor(() =>
        expect(mockAddUserToOrganization).toHaveBeenCalledWith(
          'org-1',
          'user-9',
          'ANNOTATOR',
        ),
      )
      expect(mockAddGroupMember).not.toHaveBeenCalled()
    })
  })

  it('shows each member group with the group role on its chip', async () => {
    setAuth('orgAdmin')
    mockApiClient.getOrganizationMembers.mockResolvedValue([
      {
        id: 'm-1',
        user_id: 'niklas',
        organization_id: 'org-1',
        role: 'ANNOTATOR',
        is_active: true,
        joined_at: '2026-01-01T00:00:00Z',
        user_name: 'Niklas',
        user_email: 'niklas@example.com',
        groups: [
          { id: 'grp-a', name: 'LS A', role: 'ANNOTATOR' },
          { id: 'grp-b', name: 'LS B', role: 'ORG_ADMIN' },
        ],
      },
    ])
    render(<OrganizationsTab />)

    const chipB = await screen.findByTestId('member-group-chip-niklas-grp-b')
    expect(chipB).toHaveTextContent('LS B· admin.organizations.roleAdmin')
    expect(
      screen.getByTestId('member-group-chip-niklas-grp-a'),
    ).toHaveTextContent('LS A· admin.organizations.roleAnnotator')
  })
})
