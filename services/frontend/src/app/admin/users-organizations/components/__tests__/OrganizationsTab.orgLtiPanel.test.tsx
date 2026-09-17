/**
 * @jest-environment jsdom
 *
 * Tests for the 'OrgLtiPanel' extension-slot host in OrganizationsTab:
 * the slot renders for superadmins, org admins and group admins of the
 * selected organization (never for other members), only when the extended
 * package has registered it, and receives the caller's scope as props —
 * mirroring the useSlot + useAuth mock pattern of src/app/admin/lti.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import React from 'react'

// Mock Next.js navigation
const mockSearchParams = {
  get: jest.fn(),
  toString: jest.fn(() => ''),
}

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: jest.fn(),
    replace: jest.fn(),
    back: jest.fn(),
    forward: jest.fn(),
    refresh: jest.fn(),
    prefetch: jest.fn(),
  }),
  useSearchParams: () => mockSearchParams,
}))

// Mock the slot registry (extension point)
const mockUseSlot = jest.fn()
jest.mock('@/lib/extensions/slots', () => ({
  useSlot: (name: string) => mockUseSlot(name),
}))

// Mock contexts
const mockUseAuth = jest.fn()
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => key,
    changeLanguage: jest.fn(),
    currentLanguage: 'en',
    languages: ['en', 'de'],
  }),
}))

jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: jest.fn() }),
}))

jest.mock('@/hooks/useDialogs', () => ({
  useErrorAlert: () => jest.fn(),
  useDeleteConfirm: () => jest.fn(),
}))

jest.mock('@/lib/api/organizations', () => ({
  organizationsAPI: {
    sendInvitation: jest.fn(),
    bulkInvite: jest.fn(),
    removeMember: jest.fn(),
    updateMemberRole: jest.fn(),
    getAllUsers: jest.fn(),
    addUserToOrganization: jest.fn(),
    getOrganizationInvitations: jest.fn(),
  },
}))

import { OrganizationsTab } from '../OrganizationsTab'

const mockApiClient = {
  createOrganization: jest.fn(),
  updateOrganization: jest.fn(),
  deleteOrganization: jest.fn(),
  getOrganizationMembers: jest.fn(),
}

const superadminUser = {
  id: 'user-1',
  username: 'admin',
  email: 'admin@example.com',
  name: 'Admin User',
  is_superadmin: true,
  is_active: true,
}

const regularUser = {
  ...superadminUser,
  id: 'user-2',
  username: 'orgadmin',
  email: 'orgadmin@example.com',
  is_superadmin: false,
}

const orgAdminOrganizations = [
  {
    id: 'org-1',
    name: 'Test Organization',
    slug: 'test-org',
    description: 'Test description',
    role: 'ORG_ADMIN',
  },
]

const groupAdminOrganizations = [
  {
    ...orgAdminOrganizations[0],
    role: 'CONTRIBUTOR',
    groups: [
      {
        id: 'grp-admin',
        name: 'Chair A',
        is_active: true,
        is_group_admin: true,
      },
      {
        id: 'grp-member',
        name: 'Chair B',
        is_active: true,
        is_group_admin: false,
      },
      {
        id: 'grp-old',
        name: 'Chair Old',
        is_active: false,
        is_group_admin: true,
      },
    ],
  },
]

const memberOrganizations = (role: string) => [
  {
    ...orgAdminOrganizations[0],
    role,
    groups: [
      {
        id: 'grp-member',
        name: 'Chair B',
        is_active: true,
        is_group_admin: false,
      },
    ],
  },
]

const OrgLtiPanelStub = ({
  organizationId,
  organizationName,
  open,
  hideTrigger,
  isAdmin,
  canManageGroups,
  isSuperadmin,
  adminGroupIds,
  orgRole,
}: {
  organizationId: string
  organizationName: string
  open?: boolean
  hideTrigger?: boolean
  isAdmin?: boolean
  canManageGroups?: boolean
  isSuperadmin?: boolean
  adminGroupIds?: string[]
  orgRole?: string | null
}) => (
  <div
    data-testid="org-lti-panel"
    data-open={String(Boolean(open))}
    data-hide-trigger={String(Boolean(hideTrigger))}
    data-scope={JSON.stringify({
      isAdmin,
      canManageGroups,
      isSuperadmin,
      adminGroupIds,
      orgRole,
    })}
  >
    {organizationId}:{organizationName}
  </div>
)

const panelScope = (panel: HTMLElement) =>
  JSON.parse(panel.getAttribute('data-scope') || '{}')

const setupMocks = ({
  user = superadminUser,
  slotRegistered = true,
  organizations = orgAdminOrganizations as Array<Record<string, unknown>>,
} = {}) => {
  const { organizationsAPI } = require('@/lib/api/organizations')

  mockUseAuth.mockReturnValue({
    user,
    organizations,
    refreshOrganizations: jest.fn(),
    apiClient: mockApiClient,
  })
  mockUseSlot.mockImplementation((name: string) =>
    slotRegistered && name === 'OrgLtiPanel' ? OrgLtiPanelStub : null,
  )
  mockSearchParams.get.mockReturnValue(null)
  mockApiClient.getOrganizationMembers.mockResolvedValue([])
  organizationsAPI.getOrganizationInvitations.mockResolvedValue([])
}

beforeEach(() => {
  jest.clearAllMocks()
})

const waitForOrg = () =>
  waitFor(() =>
    expect(screen.getAllByText('Test Organization').length).toBeGreaterThan(0),
  )

describe('OrganizationsTab OrgLtiPanel slot host', () => {
  it('renders the registered slot with the selected org for superadmins', async () => {
    setupMocks()
    render(<OrganizationsTab />)

    const panel = await screen.findByTestId('org-lti-panel')
    expect(panel).toHaveTextContent('org-1:Test Organization')
    expect(mockUseSlot).toHaveBeenCalledWith('OrgLtiPanel')
    expect(panelScope(panel)).toEqual({
      isAdmin: true,
      canManageGroups: false,
      isSuperadmin: true,
      adminGroupIds: [],
      orgRole: 'ORG_ADMIN',
    })
  })

  it('renders the slot for org admins who are not superadmins', async () => {
    setupMocks({ user: regularUser })
    render(<OrganizationsTab />)

    const panel = await screen.findByTestId('org-lti-panel')
    expect(panelScope(panel)).toEqual({
      isAdmin: true,
      canManageGroups: false,
      isSuperadmin: false,
      adminGroupIds: [],
      orgRole: 'ORG_ADMIN',
    })

    fireEvent.click(screen.getByTestId('org-more-button'))
    await screen.findByTestId('org-storage-button')
    fireEvent.click(await screen.findByTestId('org-lti-button'))
    await waitFor(() =>
      expect(screen.getByTestId('org-lti-panel')).toHaveAttribute(
        'data-open',
        'true',
      ),
    )
  })

  it('renders the slot for group admins with their active admin groups', async () => {
    setupMocks({
      user: regularUser,
      organizations: groupAdminOrganizations,
    })
    render(<OrganizationsTab />)

    const panel = await screen.findByTestId('org-lti-panel')
    // orgRole lets the panel cap the teacher role the group admin grants.
    expect(panelScope(panel)).toEqual({
      isAdmin: false,
      canManageGroups: true,
      isSuperadmin: false,
      adminGroupIds: ['grp-admin'],
      orgRole: 'CONTRIBUTOR',
    })

    // The "Mehr" menu offers the LMS item, but not the org-admin-only
    // storage connections.
    fireEvent.click(screen.getByTestId('org-more-button'))
    await screen.findByTestId('org-lti-button')
    expect(screen.queryByTestId('org-storage-button')).not.toBeInTheDocument()
  })

  it.each(['ANNOTATOR', 'CONTRIBUTOR'])(
    'offers nothing to a %s without group admin rights',
    async (role) => {
      setupMocks({
        user: regularUser,
        organizations: memberOrganizations(role),
      })
      render(<OrganizationsTab />)

      await waitForOrg()
      expect(screen.queryByTestId('org-lti-panel')).not.toBeInTheDocument()
      expect(screen.queryByTestId('org-more-button')).not.toBeInTheDocument()
      expect(screen.queryByTestId('org-lti-button')).not.toBeInTheDocument()
    },
  )

  it('offers nothing to the admin of an inactive group only', async () => {
    setupMocks({
      user: regularUser,
      organizations: [
        {
          ...orgAdminOrganizations[0],
          role: 'ANNOTATOR',
          groups: [
            {
              id: 'grp-old',
              name: 'Chair Old',
              is_active: false,
              is_group_admin: true,
            },
          ],
        },
      ],
    })
    render(<OrganizationsTab />)

    await waitForOrg()
    // The API would answer 403 for this scope: no LMS panel, no menu.
    expect(screen.queryByTestId('org-lti-panel')).not.toBeInTheDocument()
    expect(screen.queryByTestId('org-more-button')).not.toBeInTheDocument()
  })

  it('does not render anything when no slot is registered (community edition)', async () => {
    setupMocks({ slotRegistered: false })
    render(<OrganizationsTab />)

    await waitForOrg()
    expect(mockUseSlot).toHaveBeenCalledWith('OrgLtiPanel')
    expect(screen.queryByTestId('org-lti-panel')).not.toBeInTheDocument()

    // Org admins still get the storage item, just no LMS item.
    fireEvent.click(screen.getByTestId('org-more-button'))
    await screen.findByTestId('org-storage-button')
    expect(screen.queryByTestId('org-lti-button')).not.toBeInTheDocument()
  })

  it('offers group admins no "Mehr" menu without the slot', async () => {
    setupMocks({
      user: regularUser,
      organizations: groupAdminOrganizations,
      slotRegistered: false,
    })
    render(<OrganizationsTab />)

    await waitForOrg()
    expect(screen.queryByTestId('org-more-button')).not.toBeInTheDocument()
  })

  it('mounts the slot trigger-less and opens it from the "Mehr" menu', async () => {
    setupMocks()
    render(<OrganizationsTab />)

    const panel = await screen.findByTestId('org-lti-panel')
    expect(panel).toHaveAttribute('data-hide-trigger', 'true')
    expect(panel).toHaveAttribute('data-open', 'false')

    fireEvent.click(screen.getByTestId('org-more-button'))
    fireEvent.click(await screen.findByTestId('org-lti-button'))

    await waitFor(() =>
      expect(screen.getByTestId('org-lti-panel')).toHaveAttribute(
        'data-open',
        'true',
      ),
    )
  })
})
