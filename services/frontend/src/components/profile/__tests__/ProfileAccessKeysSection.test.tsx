/**
 * @jest-environment jsdom
 *
 * Personal access keys on the profile page: same list, create form,
 * show-once panel, test, renewal and revocation as the organization
 * dialog, without role, group and project allowlist.
 */

import {
  SCOPE_CATALOG,
  makeKey,
  mockTranslate,
} from '@/test-utils/accessKeyFixtures'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: mockTranslate, locale: 'en' }),
}))

jest.mock('@/lib/api/accessKeys', () => ({
  accessKeysAPI: {
    scopes: jest.fn(),
    listMyKeys: jest.fn(),
    createMyKey: jest.fn(),
    revokeMyKey: jest.fn(),
    myKeyUsage: jest.fn(),
    listOrgKeys: jest.fn(),
    testConnection: jest.fn(),
  },
}))

jest.mock('@/lib/api/organizations', () => ({
  organizationsAPI: { getGroups: jest.fn() },
}))

jest.mock('@/lib/api/projects', () => ({
  projectsAPI: { list: jest.fn() },
}))

import { accessKeysAPI } from '@/lib/api/accessKeys'
import { organizationsAPI } from '@/lib/api/organizations'
import { projectsAPI } from '@/lib/api/projects'
import { ProfileAccessKeysSection } from '../ProfileAccessKeysSection'

const api = accessKeysAPI as jest.Mocked<typeof accessKeysAPI>

const personalKey = (overrides = {}) =>
  makeKey({
    id: 'pk',
    name: 'My script',
    owner_type: 'user',
    organization_id: null,
    org_role: null,
    user_id: 'user-1',
    ...overrides,
  })

beforeEach(() => {
  jest.clearAllMocks()
  api.scopes.mockResolvedValue(SCOPE_CATALOG)
  api.listMyKeys.mockResolvedValue([])
})

describe('ProfileAccessKeysSection', () => {
  it('lists personal keys without org columns', async () => {
    api.listMyKeys.mockResolvedValue([personalKey()])
    render(<ProfileAccessKeysSection />)

    expect(screen.getByText('profile.accessKeys')).toBeInTheDocument()
    expect(
      screen.getByText('accessKeys.personalDescription'),
    ).toBeInTheDocument()
    expect(await screen.findByText('My script')).toBeInTheDocument()
    expect(
      screen.queryByText('accessKeys.columns.role:'),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByText(/accessKeys\.columns\.group/),
    ).not.toBeInTheDocument()
    expect(api.listOrgKeys).not.toHaveBeenCalled()
    expect(organizationsAPI.getGroups).not.toHaveBeenCalled()
  })

  it('creates a personal key without role, group or projects', async () => {
    api.createMyKey.mockResolvedValue({
      key: personalKey({ id: 'new' }),
      secret: 'bgr_live_personal_SECRET',
    })
    api.testConnection.mockResolvedValue({
      ok: true,
      me: {
        principal: { kind: 'api_key', scopes: ['projects:read'] },
        user: { id: 'user-1', name: 'Erika Muster' },
      },
    })
    render(<ProfileAccessKeysSection />)
    await waitFor(() => expect(api.listMyKeys).toHaveBeenCalled())

    fireEvent.click(screen.getByTestId('access-key-new'))
    await screen.findByTestId('access-key-create-form')
    expect(projectsAPI.list).not.toHaveBeenCalled()
    expect(screen.queryByTestId('access-key-role')).not.toBeInTheDocument()
    expect(screen.queryByTestId('access-key-group')).not.toBeInTheDocument()
    expect(screen.queryByTestId('access-key-projects')).not.toBeInTheDocument()

    // Personal keys may manage their owner's keys, never org-admin scopes;
    // reference solutions follow the owner's own role.
    fireEvent.click(screen.getByTestId('access-key-advanced-toggle'))
    expect(
      screen.getByText("Manage the owner's own access keys"),
    ).toBeInTheDocument()
    expect(
      screen.queryByTestId('access-key-scope-compliance:admin'),
    ).not.toBeInTheDocument()
    expect(
      screen.getByTestId('access-key-scope-tasks:read_reference'),
    ).toBeEnabled()

    fireEvent.click(screen.getByTestId('access-key-preset-org_full'))
    expect(
      screen.queryByTestId('access-key-role-notice'),
    ).not.toBeInTheDocument()
    fireEvent.change(screen.getByTestId('access-key-name'), {
      target: { value: 'My script' },
    })
    fireEvent.click(screen.getByTestId('access-key-create-submit'))

    await screen.findByTestId('access-key-secret-panel')
    const body = api.createMyKey.mock.calls[0][0]
    expect(body.scopes).toContain('tasks:read_reference')
    expect(body).not.toHaveProperty('org_role')
    expect(body).not.toHaveProperty('group_id')
    expect(body.project_ids).toBeNull()

    fireEvent.click(screen.getByTestId('access-key-test'))
    expect(
      await screen.findByTestId('access-key-test-success'),
    ).toHaveTextContent('accessKeys.test.actsAs {"name":"Erika Muster"}')
  })

  it('renews and revokes through the personal routes', async () => {
    api.listMyKeys.mockResolvedValue([personalKey()])
    api.createMyKey.mockResolvedValue({
      key: personalKey({ id: 'new', key_prefix: 'bgr_live_new' }),
      secret: 'bgr_live_new_SECRET',
    })
    api.revokeMyKey.mockResolvedValue(personalKey({ status: 'revoked' }))
    render(<ProfileAccessKeysSection />)

    fireEvent.click(await screen.findByTestId('access-key-renew-pk'))
    fireEvent.click(screen.getByTestId('access-key-renew-confirm'))
    await screen.findByTestId('access-key-secret-panel')
    const body = api.createMyKey.mock.calls[0][0]
    expect(body.name).toBe('My script')
    expect(body).not.toHaveProperty('org_role')

    fireEvent.click(screen.getByTestId('access-key-revoke-old'))
    await waitFor(() =>
      expect(api.revokeMyKey).toHaveBeenCalledWith(
        'pk',
        'accessKeys.renew.reason {"prefix":"bgr_live_new"}',
      ),
    )

    fireEvent.click(await screen.findByTestId('access-key-revoke-pk'))
    fireEvent.click(screen.getByTestId('access-key-revoke-confirm'))
    await waitFor(() => expect(api.revokeMyKey).toHaveBeenCalledWith('pk', ''))
  })

  it('shows usage without a CSV link', async () => {
    api.listMyKeys.mockResolvedValue([personalKey()])
    api.myKeyUsage.mockResolvedValue({
      key_id: 'pk',
      from: '',
      to: '',
      granularity: 'day',
      total_requests: 3,
      total_errors: 0,
      items: [],
    })
    render(<ProfileAccessKeysSection />)

    fireEvent.click(await screen.findByTestId('access-key-usage-pk'))
    expect(
      await screen.findByText(
        'accessKeys.usage.total {"requests":3,"errors":0}',
      ),
    ).toBeInTheDocument()
    expect(api.myKeyUsage).toHaveBeenCalledWith('pk', { granularity: 'day' })
    expect(api.myKeyUsage).toHaveBeenCalledWith('pk', { granularity: 'route' })
    expect(
      screen.queryByTestId('access-key-usage-export'),
    ).not.toBeInTheDocument()
  })
})
