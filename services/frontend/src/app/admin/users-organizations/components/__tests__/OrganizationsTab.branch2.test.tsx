/**
 * @jest-environment jsdom
 *
 * Branch coverage tests for OrganizationsTab.
 * Focuses on rendering branches that don't require async member loading.
 * Targets: no-selected-org state, org switcher, modals, permissions.
 */

import '@testing-library/jest-dom'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { OrganizationsTab } from '../OrganizationsTab'

const mockGetOrganizationMembers = jest.fn().mockResolvedValue([
  { user_id: 'user-1', user_name: 'Admin', user_email: 'admin@test.com', role: 'ORG_ADMIN' },
  { user_id: 'u2', user_name: 'John', user_email: 'john@test.com', role: 'ANNOTATOR' },
])

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
  useSearchParams: () => ({ get: jest.fn().mockReturnValue(null) }),
}))

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'user-1', name: 'Admin', is_superadmin: true },
    organizations: [
      { id: 'org-1', name: 'Org One', description: 'First org', role: 'ORG_ADMIN', user_role: 'ORG_ADMIN' },
      { id: 'org-2', name: 'Org Two', description: '', role: 'ANNOTATOR' },
    ],
    refreshOrganizations: jest.fn().mockResolvedValue(undefined),
    apiClient: {
      createOrganization: jest.fn().mockResolvedValue({ id: 'new-org', name: 'New' }),
      updateOrganization: jest.fn().mockResolvedValue({}),
      deleteOrganization: jest.fn().mockResolvedValue({}),
      getOrganizationMembers: mockGetOrganizationMembers,
      cancelInvitation: jest.fn().mockResolvedValue({}),
    },
  }),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: any) => {
      if (params) {
        let r = key
        for (const [k, v] of Object.entries(params)) r = r.replace(`{${k}}`, String(v))
        return r
      }
      return key
    },
    locale: 'en',
  }),
}))

jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: jest.fn() }),
}))

jest.mock('@/hooks/useDialogs', () => ({
  useErrorAlert: () => jest.fn(),
  useDeleteConfirm: () => jest.fn().mockResolvedValue(true),
}))

jest.mock('@/lib/api/organizations', () => ({
  organizationsAPI: {
    sendInvitation: jest.fn().mockResolvedValue({}),
    removeMember: jest.fn().mockResolvedValue({}),
    updateMemberRole: jest.fn().mockResolvedValue({}),
    getAllUsers: jest.fn().mockResolvedValue([]),
    addUserToOrganization: jest.fn().mockResolvedValue({}),
    getOrganizationInvitations: jest.fn().mockResolvedValue([]),
  },
}))

jest.mock('@/components/shared/Badge', () => ({
  Badge: ({ children }: any) => <span data-testid="badge">{children}</span>,
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, disabled, type, ...rest }: any) => (
    <button onClick={onClick} disabled={disabled} type={type || 'button'} {...rest}>{children}</button>
  ),
}))

jest.mock('@/components/shared/Card', () => ({
  Card: ({ children }: any) => <div data-testid="card">{children}</div>,
}))

jest.mock('@/components/organization/OrgApiKeys', () => ({
  OrgApiKeys: ({ open }: any) => open ? <div data-testid="api-keys-modal">API Keys</div> : null,
}))

jest.mock('@heroicons/react/24/outline', () => ({
  BuildingOfficeIcon: () => <span data-testid="building-icon" />,
  ChevronDownIcon: () => <span />,
  EnvelopeIcon: () => <span />,
  KeyIcon: () => <span />,
  PencilIcon: () => <span data-testid="pencil-icon" />,
  PlusIcon: () => <span />,
  TrashIcon: () => <span data-testid="trash-icon" />,
  UserGroupIcon: () => <span />,
  UserPlusIcon: () => <span />,
  XMarkIcon: () => <span data-testid="x-mark-icon" />,
}))

jest.mock('@/lib/permissions/userOrganizationPermissions', () => ({
  UserOrganizationPermissions: {
    canCreateOrganization: jest.fn().mockReturnValue(true),
    canManageOrganization: jest.fn().mockReturnValue(true),
    canEditOrganization: jest.fn().mockReturnValue(true),
    canDeleteOrganization: jest.fn().mockReturnValue(true),
    canInviteToOrganization: jest.fn().mockReturnValue(true),
    canRemoveMember: jest.fn().mockReturnValue(true),
    canChangeUserRole: jest.fn().mockReturnValue(true),
    canManageGlobalUsers: jest.fn().mockReturnValue(true),
  },
}))

describe('OrganizationsTab - branch2 coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetOrganizationMembers.mockResolvedValue([
      { user_id: 'user-1', user_name: 'Admin', user_email: 'admin@test.com', role: 'ORG_ADMIN' },
      { user_id: 'u2', user_name: 'John', user_email: 'john@test.com', role: 'ANNOTATOR' },
    ])
    window.history.replaceState = jest.fn()
  })

  async function renderAndWaitForMembers() {
    const result = render(<OrganizationsTab />)
    // Wait for loading to complete - check for the description text
    // (which is present both during and after loading)
    await waitFor(() => {
      expect(screen.getByText('First org')).toBeInTheDocument()
    })
    return result
  }

  it('calls getOrganizationMembers on mount', async () => {
    render(<OrganizationsTab />)

    // The org auto-selects and triggers the member load
    await waitFor(() => {
      expect(mockGetOrganizationMembers).toHaveBeenCalledWith('org-1')
    })
  })

  it('shows role badge for selected org', async () => {
    await renderAndWaitForMembers()

    const badges = screen.getAllByTestId('badge')
    const roleBadge = badges.find(b => b.textContent?.includes('admin.organizations.yourRole'))
    expect(roleBadge).toBeTruthy()
  })

  it('opens create org modal', async () => {
    const user = userEvent.setup()
    await renderAndWaitForMembers()

    const createBtn = screen.getAllByRole('button').find(
      b => b.textContent?.includes('admin.organizations.createOrganization')
    )!
    await user.click(createBtn)

    expect(screen.getByText('admin.organizations.createNewOrganization')).toBeInTheDocument()
  })

  it('opens API keys modal', async () => {
    const user = userEvent.setup()
    await renderAndWaitForMembers()

    const btn = screen.getAllByRole('button').find(
      b => b.textContent?.includes('admin.organizations.apiKeys')
    )!
    await user.click(btn)

    expect(screen.getByTestId('api-keys-modal')).toBeInTheDocument()
  })

  it('shows edit form when pencil clicked', async () => {
    const user = userEvent.setup()
    await renderAndWaitForMembers()

    const pencils = screen.getAllByTestId('pencil-icon')
    const editBtn = pencils[0].closest('button')!
    await user.click(editBtn)

    expect(screen.getByText('admin.organizations.save')).toBeInTheDocument()
    expect(screen.getByText('admin.organizations.cancel')).toBeInTheDocument()
  })
})
