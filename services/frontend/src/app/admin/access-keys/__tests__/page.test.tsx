/**
 * @jest-environment jsdom
 *
 * Superadmin overview of every access key: guard, filters, paging, revoke
 * and the usage CSV link.
 */

import { makeKey, mockTranslate } from '@/test-utils/accessKeyFixtures'
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'

const mockUser: { current: { is_superadmin: boolean } | null } = {
  current: null,
}
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: mockUser.current }),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: mockTranslate, locale: 'de' }),
}))

jest.mock('@/lib/api/accessKeys', () => ({
  accessKeysAPI: {
    adminListKeys: jest.fn(),
    adminRevokeKey: jest.fn(),
    adminUsageExportUrl: jest.fn((params?: { organization_id?: string }) =>
      params?.organization_id
        ? `/api/admin/access-keys/usage/export.csv?organization_id=${params.organization_id}`
        : '/api/admin/access-keys/usage/export.csv',
    ),
  },
}))

jest.mock('@/lib/api/organizations', () => ({
  organizationsAPI: { getOrganizations: jest.fn() },
}))

import { accessKeysAPI } from '@/lib/api/accessKeys'
import { organizationsAPI } from '@/lib/api/organizations'
import AdminAccessKeysPage from '../page'

const api = accessKeysAPI as jest.Mocked<typeof accessKeysAPI>
const orgs = organizationsAPI as jest.Mocked<typeof organizationsAPI>

const ORG_KEY = makeKey({
  id: 'k1',
  name: 'Org runner',
  last_used_at: '2026-10-01T08:00:00Z',
})
const USER_KEY = makeKey({
  id: 'k2',
  name: 'Personal script',
  owner_type: 'user',
  organization_id: null,
  user_id: 'user-7',
  expires_at: null,
})
const REVOKED_KEY = makeKey({
  id: 'k3',
  name: 'Old',
  status: 'revoked',
  organization_id: 'org-x',
})

beforeEach(() => {
  jest.clearAllMocks()
  mockUser.current = { is_superadmin: true }
  orgs.getOrganizations.mockResolvedValue([
    { id: 'org-1', name: 'Uni Test' },
    { id: 'org-2', name: 'Kanzlei' },
  ] as never)
  api.adminListKeys.mockResolvedValue({
    items: [ORG_KEY, USER_KEY, REVOKED_KEY],
    next_cursor: null,
  })
})

describe('Admin access keys page', () => {
  it.each([
    ['a non-superadmin', { is_superadmin: false }],
    ['a signed-out visitor', null],
  ])('denies access to %s', (_label, user) => {
    mockUser.current = user
    render(<AdminAccessKeysPage />)
    expect(screen.getByTestId('admin-access-keys-denied')).toBeInTheDocument()
    expect(api.adminListKeys).not.toHaveBeenCalled()
    expect(orgs.getOrganizations).not.toHaveBeenCalled()
  })

  it('lists every key with owner, scopes, dates and status', async () => {
    render(<AdminAccessKeysPage />)

    const row1 = await screen.findByTestId('admin-access-key-k1')
    await waitFor(() =>
      expect(row1).toHaveTextContent('accessKeys.ownerOrg: Uni Test'),
    )
    expect(row1).toHaveTextContent('bgr_live_abcd1234')
    expect(row1).toHaveTextContent('org:read')
    expect(row1).toHaveTextContent('1.10.2026')
    expect(
      within(row1).getByTestId('access-key-status-active'),
    ).toBeInTheDocument()

    const row2 = screen.getByTestId('admin-access-key-k2')
    expect(row2).toHaveTextContent('accessKeys.ownerUser: user-7')
    expect(row2).toHaveTextContent('accessKeys.noExpiry')
    expect(row2).toHaveTextContent('accessKeys.never')

    const row3 = screen.getByTestId('admin-access-key-k3')
    expect(row3).toHaveTextContent('accessKeys.ownerOrg: org-x')
    expect(
      within(row3).queryByTestId('admin-access-key-revoke-k3'),
    ).not.toBeInTheDocument()

    expect(screen.getByTestId('admin-access-keys-export')).toHaveAttribute(
      'href',
      '/api/admin/access-keys/usage/export.csv',
    )
  })

  it('filters by organization, owner type and status', async () => {
    render(<AdminAccessKeysPage />)
    await screen.findByTestId('admin-access-key-k1')
    await waitFor(() =>
      expect(
        within(screen.getByTestId('admin-access-keys-org')).getAllByRole(
          'option',
        ),
      ).toHaveLength(3),
    )

    fireEvent.change(screen.getByTestId('admin-access-keys-org'), {
      target: { value: 'org-2' },
    })
    fireEvent.change(screen.getByTestId('admin-access-keys-owner'), {
      target: { value: 'org' },
    })
    fireEvent.change(screen.getByTestId('admin-access-keys-status'), {
      target: { value: 'revoked' },
    })

    await waitFor(() =>
      expect(api.adminListKeys).toHaveBeenLastCalledWith({
        organization_id: 'org-2',
        owner_type: 'org',
        status: 'revoked',
        cursor: undefined,
      }),
    )
    expect(api.adminListKeys.mock.calls[0][0]).toEqual({
      organization_id: undefined,
      owner_type: undefined,
      status: undefined,
      cursor: undefined,
    })
    expect(screen.getByTestId('admin-access-keys-export')).toHaveAttribute(
      'href',
      '/api/admin/access-keys/usage/export.csv?organization_id=org-2',
    )
  })

  it('loads more pages with the cursor', async () => {
    api.adminListKeys
      .mockResolvedValueOnce({ items: [ORG_KEY], next_cursor: 'c1' })
      .mockResolvedValueOnce({ items: [USER_KEY], next_cursor: null })
    render(<AdminAccessKeysPage />)

    fireEvent.click(await screen.findByTestId('admin-access-keys-more'))
    expect(await screen.findByTestId('admin-access-key-k2')).toBeInTheDocument()
    expect(screen.getByTestId('admin-access-key-k1')).toBeInTheDocument()
    expect(api.adminListKeys).toHaveBeenLastCalledWith(
      expect.objectContaining({ cursor: 'c1' }),
    )
    expect(
      screen.queryByTestId('admin-access-keys-more'),
    ).not.toBeInTheDocument()
  })

  it('revokes a key with a reason and reloads', async () => {
    api.adminRevokeKey.mockResolvedValue(REVOKED_KEY)
    render(<AdminAccessKeysPage />)

    fireEvent.click(await screen.findByTestId('admin-access-key-revoke-k1'))
    fireEvent.change(screen.getByTestId('access-key-revoke-reason'), {
      target: { value: 'abuse' },
    })
    fireEvent.click(screen.getByTestId('access-key-revoke-confirm'))

    await waitFor(() =>
      expect(api.adminRevokeKey).toHaveBeenCalledWith('k1', 'abuse'),
    )
    expect(
      await screen.findByTestId('admin-access-keys-notice'),
    ).toHaveTextContent('accessKeys.revoke.success')
    expect(api.adminListKeys).toHaveBeenCalledTimes(2)
  })

  it('cancels a revocation', async () => {
    render(<AdminAccessKeysPage />)
    fireEvent.click(await screen.findByTestId('admin-access-key-revoke-k1'))
    fireEvent.click(screen.getByText('accessKeys.cancel'))
    expect(
      await screen.findByTestId('admin-access-keys-table'),
    ).toBeInTheDocument()
    expect(api.adminRevokeKey).not.toHaveBeenCalled()
  })

  it('shows the empty state and load errors', async () => {
    api.adminListKeys.mockResolvedValueOnce({ items: [], next_cursor: null })
    orgs.getOrganizations.mockRejectedValue(new Error('down'))
    const { unmount } = render(<AdminAccessKeysPage />)
    expect(
      await screen.findByTestId('admin-access-keys-empty'),
    ).toBeInTheDocument()
    unmount()

    api.adminListKeys.mockRejectedValueOnce(new Error('down'))
    render(<AdminAccessKeysPage />)
    expect(await screen.findByText('accessKeys.loadFailed')).toBeInTheDocument()
  })
})
