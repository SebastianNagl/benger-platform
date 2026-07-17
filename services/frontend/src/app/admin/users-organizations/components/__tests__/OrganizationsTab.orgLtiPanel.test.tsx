/**
 * @jest-environment jsdom
 *
 * Tests for the 'OrgLtiPanel' extension-slot host in OrganizationsTab:
 * the slot renders only for superadmins, only when an organization is
 * selected, and only when the extended package has registered it —
 * mirroring the useSlot + useAuth mock pattern of src/app/admin/lti.
 */

import { render, screen, waitFor } from '@testing-library/react'
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

const mockOrganizations = [
  {
    id: 'org-1',
    name: 'Test Organization',
    slug: 'test-org',
    description: 'Test description',
    role: 'ORG_ADMIN',
  },
]

const OrgLtiPanelStub = ({
  organizationId,
  organizationName,
}: {
  organizationId: string
  organizationName: string
}) => (
  <div data-testid="org-lti-panel">
    {organizationId}:{organizationName}
  </div>
)

const setupMocks = ({ user = superadminUser, slotRegistered = true } = {}) => {
  const { organizationsAPI } = require('@/lib/api/organizations')

  mockUseAuth.mockReturnValue({
    user,
    organizations: mockOrganizations,
    refreshOrganizations: jest.fn(),
    apiClient: mockApiClient,
  })
  mockUseSlot.mockImplementation((name: string) =>
    slotRegistered && name === 'OrgLtiPanel' ? OrgLtiPanelStub : null
  )
  mockSearchParams.get.mockReturnValue(null)
  mockApiClient.getOrganizationMembers.mockResolvedValue([])
  organizationsAPI.getOrganizationInvitations.mockResolvedValue([])
}

beforeEach(() => {
  jest.clearAllMocks()
})

describe('OrganizationsTab OrgLtiPanel slot host', () => {
  it('renders the registered slot with the selected org for superadmins', async () => {
    setupMocks()
    render(<OrganizationsTab />)

    const panel = await screen.findByTestId('org-lti-panel')
    expect(panel).toHaveTextContent('org-1:Test Organization')
    expect(mockUseSlot).toHaveBeenCalledWith('OrgLtiPanel')
  })

  it('does not render the slot for non-superadmins', async () => {
    setupMocks({ user: regularUser })
    render(<OrganizationsTab />)

    // Wait until the auto-selected org has rendered, then assert absence.
    await waitFor(() =>
      expect(screen.getAllByText('Test Organization').length).toBeGreaterThan(0)
    )
    expect(screen.queryByTestId('org-lti-panel')).not.toBeInTheDocument()
  })

  it('does not render anything when no slot is registered (community edition)', async () => {
    setupMocks({ slotRegistered: false })
    render(<OrganizationsTab />)

    await waitFor(() =>
      expect(screen.getAllByText('Test Organization').length).toBeGreaterThan(0)
    )
    expect(mockUseSlot).toHaveBeenCalledWith('OrgLtiPanel')
    expect(screen.queryByTestId('org-lti-panel')).not.toBeInTheDocument()
  })
})
