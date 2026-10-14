/**
 * @jest-environment jsdom
 *
 * The "API-Zugänge" button of OrganizationsTab: shown to superadmins, org
 * admins and admins of an active group of the selected organization, never
 * to plain members, and it opens OrgAccessKeys with the caller's scope.
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

// Public API feature flag: on unless a test switches it off.
const mockPublicApi: { current: boolean | null } = { current: true }
jest.mock('@/hooks/usePublicApiEnabled', () => ({
  usePublicApiEnabled: () => mockPublicApi.current,
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
        role: 'ORG_ADMIN',
      },
      {
        id: 'grp-member',
        name: 'Chair B',
        is_active: true,
        role: 'CONTRIBUTOR',
      },
      {
        id: 'grp-old',
        name: 'Chair Old',
        is_active: false,
        role: 'ORG_ADMIN',
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
        role: 'CONTRIBUTOR',
      },
    ],
  },
]

// The dialog itself is tested in OrgAccessKeys.test.tsx; a stub records
// the props it receives.
jest.mock('@/components/organization/OrgAccessKeys', () => ({
  OrgAccessKeys: (props: {
    organizationId: string
    isAdmin: boolean
    canManageGroups?: boolean
    adminGroupIds?: string[]
    open: boolean
  }) => (
    <div
      data-testid="org-access-keys-stub"
      data-open={String(props.open)}
      data-scope={JSON.stringify({
        organizationId: props.organizationId,
        isAdmin: props.isAdmin,
        canManageGroups: props.canManageGroups,
        adminGroupIds: props.adminGroupIds,
      })}
    />
  ),
}))

import { OrganizationsTab } from '../OrganizationsTab'

const setupMocks = ({
  user = superadminUser,
  organizations = orgAdminOrganizations as Array<Record<string, unknown>>,
} = {}) => {
  const { organizationsAPI } = require('@/lib/api/organizations')

  mockUseAuth.mockReturnValue({
    user,
    organizations,
    refreshOrganizations: jest.fn(),
    apiClient: mockApiClient,
  })
  mockUseSlot.mockReturnValue(null)
  mockSearchParams.get.mockReturnValue(null)
  mockApiClient.getOrganizationMembers.mockResolvedValue([])
  organizationsAPI.getOrganizationInvitations.mockResolvedValue([])
}

beforeEach(() => {
  jest.clearAllMocks()
  mockPublicApi.current = true
})

const waitForOrg = () =>
  waitFor(() =>
    expect(screen.getAllByText('Test Organization').length).toBeGreaterThan(0),
  )

const stubScope = () =>
  JSON.parse(
    screen.getByTestId('org-access-keys-stub').getAttribute('data-scope') ||
      '{}',
  )

describe('OrganizationsTab access keys button', () => {
  it('opens the dialog for superadmins', async () => {
    setupMocks()
    render(<OrganizationsTab />)

    const button = await screen.findByTestId('org-access-keys-button')
    expect(button).toHaveTextContent('admin.organizations.accessKeys')
    expect(screen.getByTestId('org-access-keys-stub')).toHaveAttribute(
      'data-open',
      'false',
    )
    expect(stubScope()).toEqual({
      organizationId: 'org-1',
      isAdmin: true,
      canManageGroups: false,
      adminGroupIds: [],
    })

    fireEvent.click(button)
    await waitFor(() =>
      expect(screen.getByTestId('org-access-keys-stub')).toHaveAttribute(
        'data-open',
        'true',
      ),
    )
  })

  it('shows the button to org admins next to the provider keys', async () => {
    setupMocks({ user: regularUser })
    render(<OrganizationsTab />)

    const button = await screen.findByTestId('org-access-keys-button')
    const providerButton = screen.getByTestId('org-api-keys-button')
    expect(providerButton.nextElementSibling).toBe(button)
    expect(stubScope().isAdmin).toBe(true)
  })

  it('passes group admins their active admin groups', async () => {
    setupMocks({ user: regularUser, organizations: groupAdminOrganizations })
    render(<OrganizationsTab />)

    await screen.findByTestId('org-access-keys-button')
    expect(stubScope()).toEqual({
      organizationId: 'org-1',
      isAdmin: false,
      canManageGroups: true,
      adminGroupIds: ['grp-admin'],
    })
  })

  it.each(['ANNOTATOR', 'CONTRIBUTOR'])(
    'hides the button from a %s without group admin rights',
    async (role) => {
      setupMocks({
        user: regularUser,
        organizations: memberOrganizations(role),
      })
      render(<OrganizationsTab />)

      await waitForOrg()
      expect(
        screen.queryByTestId('org-access-keys-button'),
      ).not.toBeInTheDocument()
      expect(stubScope()).toMatchObject({
        isAdmin: false,
        canManageGroups: false,
      })
    },
  )
  it.each([
    ['off', false],
    ['still loading', null],
  ])(
    'hides the button and the dialog while the public API is %s',
    async (_label, value) => {
      mockPublicApi.current = value
      setupMocks()
      render(<OrganizationsTab />)

      await waitForOrg()
      expect(
        screen.queryByTestId('org-access-keys-button'),
      ).not.toBeInTheDocument()
      expect(
        screen.queryByTestId('org-access-keys-stub'),
      ).not.toBeInTheDocument()
      // The provider keys button is unaffected by the flag.
      expect(screen.getByTestId('org-api-keys-button')).toBeInTheDocument()
    },
  )
})
