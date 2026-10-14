/**
 * @jest-environment jsdom
 *
 * OrgAccessKeys: the "API-Zugänge" dialog of an organization. Covers the
 * key list, presets and the Advanced scope list, the show-once panel with
 * copy, snippets and the connection test, renewal, revocation, the usage
 * panel and the group-admin restrictions.
 */

import {
  SCOPE_CATALOG,
  makeKey,
  mockTranslate,
} from '@/test-utils/accessKeyFixtures'
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: mockTranslate, locale: 'de' }),
}))

jest.mock('@/lib/api/accessKeys', () => ({
  accessKeysAPI: {
    scopes: jest.fn(),
    listOrgKeys: jest.fn(),
    createOrgKey: jest.fn(),
    revokeOrgKey: jest.fn(),
    orgKeyUsage: jest.fn(),
    orgUsageExportUrl: jest.fn(
      (orgId: string) =>
        `/api/organizations/${orgId}/access-keys/usage/export.csv`,
    ),
    listMyKeys: jest.fn(),
    createMyKey: jest.fn(),
    revokeMyKey: jest.fn(),
    myKeyUsage: jest.fn(),
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
import { OrgAccessKeys } from '../OrgAccessKeys'

const api = accessKeysAPI as jest.Mocked<typeof accessKeysAPI>
const orgs = organizationsAPI as jest.Mocked<typeof organizationsAPI>
const projects = projectsAPI as jest.Mocked<typeof projectsAPI>

const DAY = 24 * 60 * 60 * 1000

const GROUPS = [
  { id: 'g1', name: 'Lehrstuhl A', is_active: true },
  { id: 'g2', name: 'Lehrstuhl B', is_active: true },
  { id: 'g3', name: 'Alt', is_active: false },
]

const PROJECTS = [
  { id: 'p1', title: 'Org project', organizations: [{ id: 'org-1' }] },
  { id: 'p2', title: 'Public project', is_public: true, organizations: [] },
  { id: 'p3', title: 'Foreign project', organizations: [{ id: 'org-9' }] },
]

const created = (overrides = {}) => ({
  key: makeKey({ id: 'key-new', name: 'Runner', ...overrides }),
  secret: 'bgr_live_newkey12_SECRETVALUE',
})

let clipboardWrite: jest.Mock

beforeEach(() => {
  jest.clearAllMocks()
  api.scopes.mockResolvedValue(SCOPE_CATALOG)
  api.listOrgKeys.mockResolvedValue([])
  orgs.getGroups.mockResolvedValue(GROUPS as never)
  projects.list.mockResolvedValue({ items: PROJECTS } as never)
  clipboardWrite = jest.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText: clipboardWrite },
    configurable: true,
  })
})

const renderDialog = (
  props: Partial<Parameters<typeof OrgAccessKeys>[0]> = {},
) => {
  const onOpenChange = jest.fn()
  const utils = render(
    <OrgAccessKeys
      organizationId="org-1"
      isAdmin
      open
      onOpenChange={onOpenChange}
      {...props}
    />,
  )
  return { ...utils, onOpenChange }
}

const openCreateForm = async () => {
  await waitFor(() => expect(api.listOrgKeys).toHaveBeenCalled())
  fireEvent.click(screen.getByTestId('access-key-new'))
  return screen.findByTestId('access-key-create-form')
}

const fillName = (value = 'Runner') =>
  fireEvent.change(screen.getByTestId('access-key-name'), {
    target: { value },
  })

const submitForm = () =>
  fireEvent.click(screen.getByTestId('access-key-create-submit'))

describe('OrgAccessKeys dialog', () => {
  it('renders nothing for callers without admin rights', () => {
    const { container } = render(
      <OrgAccessKeys
        organizationId="org-1"
        isAdmin={false}
        open
        onOpenChange={jest.fn()}
      />,
    )
    expect(container).toBeEmptyDOMElement()
    expect(api.listOrgKeys).not.toHaveBeenCalled()
  })

  it('does not load while closed and closes from the header', async () => {
    const { rerender, onOpenChange } = renderDialog({ open: false })
    expect(api.listOrgKeys).not.toHaveBeenCalled()
    rerender(
      <OrgAccessKeys
        organizationId="org-1"
        isAdmin
        open
        onOpenChange={onOpenChange}
      />,
    )
    await waitFor(() => expect(api.listOrgKeys).toHaveBeenCalledWith('org-1'))
    fireEvent.click(screen.getByLabelText('accessKeys.close'))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('lists keys with scopes, role, group, projects, expiry and status', async () => {
    api.listOrgKeys.mockResolvedValue([
      makeKey({
        id: 'a',
        name: 'Runner A',
        group_id: 'g1',
        org_role: 'CONTRIBUTOR',
        project_ids: ['p1', 'p2'],
        expires_at: new Date(Date.now() + 5 * DAY).toISOString(),
        last_used_at: '2026-10-10T10:00:00Z',
      }),
      makeKey({
        id: 'b',
        name: 'Old runner',
        status: 'revoked',
        expires_at: null,
      }),
      makeKey({ id: 'c', name: 'Gone', status: 'expired', group_id: 'gx' }),
    ])
    renderDialog()

    const rowA = await screen.findByTestId('access-key-row-a')
    expect(within(rowA).getByText('Runner A')).toBeInTheDocument()
    expect(within(rowA).getByText('bgr_live_abcd1234')).toBeInTheDocument()
    expect(within(rowA).getByText('org:read')).toBeInTheDocument()
    expect(
      within(rowA).getByText('admin.organizations.roleContributor'),
    ).toBeInTheDocument()
    await waitFor(() =>
      expect(within(rowA).getByText('Lehrstuhl A')).toBeInTheDocument(),
    )
    expect(
      within(rowA).getByText('accessKeys.projectsCount {"count":2}'),
    ).toBeInTheDocument()
    expect(
      within(rowA).getByTestId('access-key-expiry-warning'),
    ).toHaveTextContent('accessKeys.expiresSoon {"days":5}')
    expect(within(rowA).getByText('10.10.2026')).toBeInTheDocument()
    expect(
      within(rowA).getByTestId('access-key-status-active'),
    ).toBeInTheDocument()
    expect(within(rowA).getByTestId('access-key-renew-a')).toBeInTheDocument()

    const rowB = screen.getByTestId('access-key-row-b')
    expect(within(rowB).getByText('accessKeys.noExpiry')).toBeInTheDocument()
    expect(within(rowB).getByText('accessKeys.never')).toBeInTheDocument()
    expect(within(rowB).getByText('accessKeys.orgWide')).toBeInTheDocument()
    expect(
      within(rowB).getByText('admin.organizations.roleAnnotator'),
    ).toBeInTheDocument()
    expect(
      within(rowB).getByTestId('access-key-status-revoked'),
    ).toBeInTheDocument()
    expect(
      within(rowB).queryByTestId('access-key-renew-b'),
    ).not.toBeInTheDocument()
    expect(
      within(rowB).queryByTestId('access-key-revoke-b'),
    ).not.toBeInTheDocument()

    const rowC = screen.getByTestId('access-key-row-c')
    expect(within(rowC).getByText('gx')).toBeInTheDocument()
    expect(within(rowC).getByText('accessKeys.allProjects')).toBeInTheDocument()
    expect(
      within(rowC).getByTestId('access-key-status-expired'),
    ).toBeInTheDocument()
    expect(
      within(rowC).queryByTestId('access-key-expiry-warning'),
    ).not.toBeInTheDocument()
  })

  it('shows the empty state and a load error', async () => {
    renderDialog()
    expect(await screen.findByTestId('access-key-empty')).toBeInTheDocument()
  })

  it('shows a load error', async () => {
    api.listOrgKeys.mockRejectedValue(new Error('boom'))
    orgs.getGroups.mockRejectedValue(new Error('boom'))
    renderDialog()
    expect(await screen.findByText('accessKeys.loadFailed')).toBeInTheDocument()
  })

  describe('create form', () => {
    it('starts on the read preset and expands a preset into its scopes', async () => {
      renderDialog()
      await openCreateForm()

      expect(
        screen.getByTestId('access-key-preset-benchmark_read'),
      ).toBeChecked()
      // Presets show in plain language, known ones first.
      const radios = screen
        .getAllByRole('radio')
        .map((r) => (r as HTMLInputElement).value)
      expect(radios).toEqual([
        'benchmark_read',
        'benchmark_submit',
        'org_full',
        'custom',
      ])

      fireEvent.click(screen.getByTestId('access-key-preset-benchmark_submit'))
      fireEvent.click(screen.getByTestId('access-key-advanced-toggle'))
      const list = screen.getByTestId('access-key-scope-list')
      expect(
        screen.getByTestId('access-key-scope-submissions:write'),
      ).toBeChecked()
      expect(screen.getByTestId('access-key-scope-runs:write')).toBeChecked()
      expect(screen.getByTestId('access-key-scope-runs:read')).not.toBeChecked()
      expect(within(list).getByText('Läufe anlegen')).toBeInTheDocument()
      expect(
        within(list).getByText(
          'accessKeys.form.implies {"scopes":"submissions:read"}',
        ),
      ).toBeInTheDocument()
      // Personal-only scopes are never offered on org keys; org-admin ones are.
      expect(
        screen.queryByTestId('access-key-scope-keys:manage'),
      ).not.toBeInTheDocument()
      expect(
        screen.getByTestId('access-key-scope-compliance:admin'),
      ).toBeInTheDocument()
      // Reference solutions need the CONTRIBUTOR role.
      expect(
        screen.getByTestId('access-key-scope-tasks:read_reference'),
      ).toBeDisabled()
      expect(
        within(list).getByText('accessKeys.form.needsContributor'),
      ).toBeInTheDocument()

      // Unchecking one scope turns the selection into a custom one.
      fireEvent.click(screen.getByTestId('access-key-scope-runs:write'))
      expect(screen.getByTestId('access-key-preset-custom')).toBeChecked()
      fireEvent.click(screen.getByTestId('access-key-scope-runs:write'))
      expect(
        screen.getByTestId('access-key-preset-benchmark_submit'),
      ).toBeChecked()

      // Collapsing hides the list again.
      fireEvent.click(screen.getByTestId('access-key-advanced-toggle'))
      expect(
        screen.queryByTestId('access-key-scope-list'),
      ).not.toBeInTheDocument()
      fireEvent.click(screen.getByTestId('access-key-preset-custom'))
      expect(screen.getByTestId('access-key-scope-list')).toBeInTheDocument()
    })

    it('switches to CONTRIBUTOR for full access and drops reference scopes on ANNOTATOR', async () => {
      renderDialog()
      await openCreateForm()

      fireEvent.click(screen.getByTestId('access-key-preset-org_full'))
      expect(screen.getByTestId('access-key-role')).toHaveValue('CONTRIBUTOR')
      expect(screen.getByTestId('access-key-role-notice')).toBeInTheDocument()

      fireEvent.click(screen.getByTestId('access-key-advanced-toggle'))
      expect(
        screen.getByTestId('access-key-scope-tasks:read_reference'),
      ).toBeChecked()

      fireEvent.change(screen.getByTestId('access-key-role'), {
        target: { value: 'ANNOTATOR' },
      })
      expect(
        screen.getByTestId('access-key-scope-tasks:read_reference'),
      ).not.toBeChecked()
      expect(screen.getByTestId('access-key-preset-custom')).toBeChecked()
      expect(
        screen.queryByTestId('access-key-role-notice'),
      ).not.toBeInTheDocument()

      fireEvent.change(screen.getByTestId('access-key-role'), {
        target: { value: 'CONTRIBUTOR' },
      })
      fireEvent.click(
        screen.getByTestId('access-key-scope-tasks:read_reference'),
      )
      expect(
        screen.getByTestId('access-key-scope-tasks:read_reference'),
      ).toBeChecked()
    })

    it('validates the name and the scope selection', async () => {
      renderDialog()
      await openCreateForm()

      submitForm()
      expect(screen.getByTestId('access-key-form-error')).toHaveTextContent(
        'accessKeys.form.nameRequired',
      )

      fillName('  Runner  ')
      fireEvent.click(screen.getByTestId('access-key-advanced-toggle'))
      for (const name of SCOPE_CATALOG.presets.benchmark_read) {
        fireEvent.click(screen.getByTestId(`access-key-scope-${name}`))
      }
      submitForm()
      expect(screen.getByTestId('access-key-form-error')).toHaveTextContent(
        'accessKeys.form.noScopes',
      )
      expect(api.createOrgKey).not.toHaveBeenCalled()
    })

    it('goes back to the list on cancel', async () => {
      renderDialog()
      await openCreateForm()
      fireEvent.click(screen.getByText('accessKeys.cancel'))
      expect(
        await screen.findByTestId('access-key-list-view'),
      ).toBeInTheDocument()
    })

    it('creates a key, shows the secret once with copy and snippets', async () => {
      api.createOrgKey.mockResolvedValue(created())
      renderDialog()
      await openCreateForm()

      fillName('  Runner  ')
      const before = Date.now()
      submitForm()

      await screen.findByTestId('access-key-secret-panel')
      const [orgId, body] = api.createOrgKey.mock.calls[0]
      expect(orgId).toBe('org-1')
      expect(body).toMatchObject({
        name: 'Runner',
        scopes: [...SCOPE_CATALOG.presets.benchmark_read].sort(),
        org_role: 'ANNOTATOR',
        group_id: null,
        project_ids: null,
        rate_limit_per_minute: null,
        rate_limit_per_day: null,
      })
      const expires = Date.parse(body.expires_at as string)
      expect(expires).toBeGreaterThanOrEqual(before + 365 * DAY - 1000)
      expect(expires).toBeLessThanOrEqual(Date.now() + 365 * DAY + 1000)

      expect(screen.getByTestId('access-key-secret')).toHaveTextContent(
        'bgr_live_newkey12_SECRETVALUE',
      )
      expect(screen.getByText('accessKeys.secret.warning')).toBeInTheDocument()
      expect(screen.getByTestId('access-key-curl')).toHaveTextContent(
        'curl -H "Authorization: Bearer bgr_live_newkey12_SECRETVALUE"',
      )
      expect(screen.getByTestId('access-key-curl')).toHaveTextContent(
        'http://localhost/api/v1/me',
      )
      expect(screen.getByTestId('access-key-python')).toHaveTextContent(
        'API_KEY = "bgr_live_newkey12_SECRETVALUE"',
      )
      expect(screen.getByTestId('access-key-python')).toHaveTextContent(
        '"http://localhost/api/v1/me"',
      )

      fireEvent.click(screen.getByTestId('access-key-copy'))
      await waitFor(() =>
        expect(clipboardWrite).toHaveBeenCalledWith(
          'bgr_live_newkey12_SECRETVALUE',
        ),
      )
      expect(
        await screen.findByText('accessKeys.secret.copied'),
      ).toBeInTheDocument()

      // The list reloads behind the panel; "Fertig" drops the secret.
      await waitFor(() => expect(api.listOrgKeys).toHaveBeenCalledTimes(2))
      fireEvent.click(screen.getByTestId('access-key-secret-done'))
      expect(
        await screen.findByTestId('access-key-list-view'),
      ).toBeInTheDocument()
      expect(
        screen.queryByText('bgr_live_newkey12_SECRETVALUE'),
      ).not.toBeInTheDocument()
    })

    it('explains a failed copy', async () => {
      clipboardWrite.mockRejectedValue(new Error('denied'))
      api.createOrgKey.mockResolvedValue(created())
      renderDialog()
      await openCreateForm()
      fillName()
      submitForm()
      await screen.findByTestId('access-key-secret-panel')
      fireEvent.click(screen.getByTestId('access-key-copy'))
      expect(
        await screen.findByText('accessKeys.secret.copyFailed'),
      ).toBeInTheDocument()
    })

    it('sends projects, limits and an unlimited expiry', async () => {
      api.createOrgKey.mockResolvedValue(created())
      renderDialog()
      await openCreateForm()

      // Only projects of this org or public ones are offered.
      const box = screen.getByTestId('access-key-projects')
      expect(within(box).getByText('Org project')).toBeInTheDocument()
      expect(within(box).getByText('Public project')).toBeInTheDocument()
      expect(within(box).queryByText('Foreign project')).not.toBeInTheDocument()
      fireEvent.click(screen.getByTestId('access-key-project-p1'))
      fireEvent.click(screen.getByTestId('access-key-project-p2'))
      fireEvent.click(screen.getByTestId('access-key-project-p2'))

      // Org admins choose org-wide or any active group.
      const group = screen.getByTestId('access-key-group')
      await waitFor(() =>
        expect(within(group).getAllByRole('option')).toHaveLength(3),
      )
      fireEvent.change(group, { target: { value: 'g2' } })

      fireEvent.change(screen.getByTestId('access-key-expiry'), {
        target: { value: 'never' },
      })
      fireEvent.click(screen.getByTestId('access-key-limits-toggle'))
      fireEvent.change(screen.getByTestId('access-key-rpm'), {
        target: { value: '30' },
      })
      fireEvent.change(screen.getByTestId('access-key-rpd'), {
        target: { value: '5000' },
      })
      fireEvent.click(screen.getByTestId('access-key-limits-toggle'))
      fireEvent.click(screen.getByTestId('access-key-limits-toggle'))
      fillName()
      submitForm()

      await screen.findByTestId('access-key-secret-panel')
      expect(api.createOrgKey.mock.calls[0][1]).toMatchObject({
        project_ids: ['p1'],
        group_id: 'g2',
        expires_at: null,
        rate_limit_per_minute: 30,
        rate_limit_per_day: 5000,
      })
    })

    it('shows the limit message on too_many_keys and other errors verbatim', async () => {
      const tooMany = Object.assign(new Error('limit'), {
        response: {
          status: 409,
          data: { detail: { code: 'too_many_keys', message: 'limit' } },
        },
      })
      api.createOrgKey.mockRejectedValueOnce(tooMany)
      api.createOrgKey.mockRejectedValueOnce(new Error('Scope not grantable'))
      renderDialog()
      await openCreateForm()
      fillName()

      submitForm()
      expect(
        await screen.findByText('accessKeys.form.tooManyKeys'),
      ).toBeInTheDocument()

      submitForm()
      expect(
        await screen.findByText(
          'accessKeys.form.createFailed {"message":"Scope not grantable"}',
        ),
      ).toBeInTheDocument()
    })

    it('falls back to an empty catalog and project list when they fail', async () => {
      api.scopes.mockRejectedValue(new Error('down'))
      projects.list.mockRejectedValue(new Error('down'))
      renderDialog()
      await openCreateForm()
      expect(screen.getByTestId('access-key-preset-custom')).toBeChecked()
      expect(screen.getByText('accessKeys.form.noProjects')).toBeInTheDocument()
    })
  })

  describe('connection test', () => {
    const toSecretPanel = async () => {
      api.createOrgKey.mockResolvedValue(created())
      renderDialog()
      await openCreateForm()
      fillName()
      submitForm()
      await screen.findByTestId('access-key-secret-panel')
    }

    it('shows the resolved principal on success', async () => {
      api.testConnection.mockResolvedValue({
        ok: true,
        me: {
          principal: {
            kind: 'api_key',
            scopes: ['org:read', 'projects:read'],
            organization: { id: 'org-1', name: 'Uni Test' },
            group: { id: 'g1', name: 'Lehrstuhl A' },
          },
          user: { id: 'svc', is_service_account: true },
        },
      })
      await toSecretPanel()
      fireEvent.click(screen.getByTestId('access-key-test'))

      const ok = await screen.findByTestId('access-key-test-success')
      expect(api.testConnection).toHaveBeenCalledWith(
        'bgr_live_newkey12_SECRETVALUE',
      )
      expect(ok).toHaveTextContent('accessKeys.test.success')
      expect(ok).toHaveTextContent(
        'accessKeys.test.organization {"name":"Uni Test"}',
      )
      expect(ok).toHaveTextContent(
        'accessKeys.test.group {"name":"Lehrstuhl A"}',
      )
      expect(ok).toHaveTextContent(
        'accessKeys.test.scopes {"scopes":"org:read, projects:read"}',
      )
    })

    it.each([
      [0, 'accessKeys.test.network'],
      [401, 'accessKeys.test.unauthorized'],
      [403, 'accessKeys.test.forbidden'],
      [404, 'accessKeys.test.notAvailable'],
      [429, 'accessKeys.test.rateLimited'],
      [500, 'accessKeys.test.generic {"status":500,"message":"Oops"}'],
    ])('explains a failed test with status %s', async (status, text) => {
      api.testConnection.mockResolvedValue({
        ok: false,
        status,
        code: null,
        message: 'Oops',
      })
      await toSecretPanel()
      fireEvent.click(screen.getByTestId('access-key-test'))
      expect(
        await screen.findByTestId('access-key-test-error'),
      ).toHaveTextContent(text)
    })
  })

  describe('renewal', () => {
    const OLD = makeKey({
      id: 'old',
      name: 'Runner',
      group_id: 'g1',
      org_role: 'CONTRIBUTOR',
      scopes: ['org:read', 'tasks:read_reference'],
      project_ids: ['p1'],
      rate_limit_per_minute: 10,
    })

    it('creates a key with the same settings and revokes the old one on request', async () => {
      api.listOrgKeys.mockResolvedValue([OLD])
      api.createOrgKey.mockResolvedValue(
        created({ key_prefix: 'bgr_live_new' }),
      )
      api.revokeOrgKey.mockResolvedValue(makeKey({ status: 'revoked' }))
      renderDialog()

      fireEvent.click(await screen.findByTestId('access-key-renew-old'))
      expect(screen.getByText('accessKeys.renew.hint')).toBeInTheDocument()
      fireEvent.click(screen.getByTestId('access-key-renew-confirm'))

      await screen.findByTestId('access-key-secret-panel')
      const body = api.createOrgKey.mock.calls[0][1]
      expect(body).toMatchObject({
        name: 'Runner',
        scopes: ['org:read', 'tasks:read_reference'],
        org_role: 'CONTRIBUTOR',
        group_id: 'g1',
        project_ids: ['p1'],
        rate_limit_per_minute: 10,
      })
      expect(Date.parse(body.expires_at as string)).toBeGreaterThan(
        Date.now() + 364 * DAY,
      )
      // The old key stays active until the user decides.
      expect(api.revokeOrgKey).not.toHaveBeenCalled()
      expect(
        screen.queryByTestId('access-key-secret-done'),
      ).not.toBeInTheDocument()
      expect(screen.getByTestId('access-key-renew-choices')).toHaveTextContent(
        'accessKeys.renew.oldStillActive',
      )

      fireEvent.click(screen.getByTestId('access-key-revoke-old'))
      await waitFor(() =>
        expect(api.revokeOrgKey).toHaveBeenCalledWith(
          'org-1',
          'old',
          'accessKeys.renew.reason {"prefix":"bgr_live_new"}',
        ),
      )
      expect(await screen.findByTestId('access-key-notice')).toHaveTextContent(
        'accessKeys.renew.oldRevoked',
      )
    })

    it('can keep the old key and reports a failed revoke', async () => {
      api.listOrgKeys.mockResolvedValue([OLD])
      api.createOrgKey.mockResolvedValue(created())
      api.revokeOrgKey.mockRejectedValue(new Error('nope'))
      renderDialog()

      fireEvent.click(await screen.findByTestId('access-key-renew-old'))
      fireEvent.click(screen.getByTestId('access-key-renew-confirm'))
      await screen.findByTestId('access-key-secret-panel')
      fireEvent.click(screen.getByTestId('access-key-keep-old'))
      expect(
        await screen.findByTestId('access-key-list-view'),
      ).toBeInTheDocument()
      expect(api.revokeOrgKey).not.toHaveBeenCalled()

      fireEvent.click(await screen.findByTestId('access-key-renew-old'))
      fireEvent.click(screen.getByTestId('access-key-renew-confirm'))
      await screen.findByTestId('access-key-secret-panel')
      fireEvent.click(screen.getByTestId('access-key-revoke-old'))
      expect(await screen.findByTestId('access-key-notice')).toHaveTextContent(
        'accessKeys.revoke.failed {"message":"nope"}',
      )
    })

    it('shows renewal errors and can be cancelled', async () => {
      api.listOrgKeys.mockResolvedValue([OLD])
      api.createOrgKey.mockRejectedValueOnce(new Error('broken'))
      api.createOrgKey.mockRejectedValueOnce(
        Object.assign(new Error('x'), {
          response: { data: { detail: { code: 'too_many_keys' } } },
        }),
      )
      renderDialog()

      fireEvent.click(await screen.findByTestId('access-key-renew-old'))
      fireEvent.click(screen.getByTestId('access-key-renew-confirm'))
      expect(
        await screen.findByText('accessKeys.renew.failed {"message":"broken"}'),
      ).toBeInTheDocument()
      fireEvent.click(screen.getByTestId('access-key-renew-confirm'))
      expect(
        await screen.findByText('accessKeys.form.tooManyKeys'),
      ).toBeInTheDocument()
      fireEvent.click(screen.getByText('accessKeys.cancel'))
      expect(
        await screen.findByTestId('access-key-list-view'),
      ).toBeInTheDocument()
    })

    it('keeps an unlimited key unlimited', async () => {
      api.listOrgKeys.mockResolvedValue([
        makeKey({ id: 'old', expires_at: null, group_id: null }),
      ])
      api.createOrgKey.mockResolvedValue(created())
      renderDialog()
      fireEvent.click(await screen.findByTestId('access-key-renew-old'))
      fireEvent.click(screen.getByTestId('access-key-renew-confirm'))
      await screen.findByTestId('access-key-secret-panel')
      expect(api.createOrgKey.mock.calls[0][1]).toMatchObject({
        expires_at: null,
        org_role: 'ANNOTATOR',
        group_id: null,
        project_ids: null,
      })
    })
  })

  describe('revocation', () => {
    it('revokes with a reason and reports success', async () => {
      api.listOrgKeys.mockResolvedValue([makeKey({ id: 'k' })])
      api.revokeOrgKey.mockResolvedValue(makeKey({ status: 'revoked' }))
      renderDialog()

      fireEvent.click(await screen.findByTestId('access-key-revoke-k'))
      const panel = screen.getByTestId('access-key-revoke-panel')
      expect(panel).toHaveTextContent('accessKeys.revoke.description')
      fireEvent.change(screen.getByTestId('access-key-revoke-reason'), {
        target: { value: '  leaked  ' },
      })
      fireEvent.click(screen.getByTestId('access-key-revoke-confirm'))

      await waitFor(() =>
        expect(api.revokeOrgKey).toHaveBeenCalledWith('org-1', 'k', 'leaked'),
      )
      expect(await screen.findByTestId('access-key-notice')).toHaveTextContent(
        'accessKeys.revoke.success',
      )
    })

    it('shows a failed revocation and can be cancelled', async () => {
      api.listOrgKeys.mockResolvedValue([makeKey({ id: 'k' })])
      api.revokeOrgKey.mockRejectedValue(new Error('denied'))
      renderDialog()

      fireEvent.click(await screen.findByTestId('access-key-revoke-k'))
      fireEvent.click(screen.getByTestId('access-key-revoke-confirm'))
      expect(
        await screen.findByText(
          'accessKeys.revoke.failed {"message":"denied"}',
        ),
      ).toBeInTheDocument()
      fireEvent.click(screen.getByText('accessKeys.cancel'))
      expect(
        await screen.findByTestId('access-key-list-view'),
      ).toBeInTheDocument()
    })
  })

  describe('usage', () => {
    const today = new Date().toISOString().slice(0, 10)

    it('shows calls per day, routes with errors and the CSV link', async () => {
      api.listOrgKeys.mockResolvedValue([makeKey({ id: 'k', name: 'Runner' })])
      api.orgKeyUsage.mockImplementation(async (_o, _k, params) =>
        params?.granularity === 'route'
          ? {
              key_id: 'k',
              from: '',
              to: '',
              granularity: 'route',
              total_requests: 12,
              total_errors: 2,
              items: [
                { method: 'GET', route: '/api/v1/me', requests: 10, errors: 0 },
                {
                  method: 'POST',
                  route: '/api/v1/runs',
                  requests: 2,
                  errors: 2,
                },
              ],
            }
          : {
              key_id: 'k',
              from: '',
              to: '',
              granularity: 'day',
              total_requests: 12,
              total_errors: 2,
              items: [{ day: today, requests: 12, errors: 2 }],
            },
      )
      renderDialog()

      fireEvent.click(await screen.findByTestId('access-key-usage-k'))
      const panel = await screen.findByTestId('access-key-usage-panel')
      expect(panel).toHaveTextContent(
        'accessKeys.usage.title {"name":"Runner"}',
      )
      expect(
        await screen.findByText(
          'accessKeys.usage.total {"requests":12,"errors":2}',
        ),
      ).toBeInTheDocument()
      const days = screen.getByTestId('access-key-usage-days')
      expect(within(days).getAllByRole('listitem')).toHaveLength(30)
      expect(within(days).getByText(today)).toBeInTheDocument()
      const routes = screen.getByTestId('access-key-usage-routes')
      expect(routes).toHaveTextContent('GET /api/v1/me')
      expect(routes).toHaveTextContent('accessKeys.usage.errors {"errors":2}')
      expect(screen.getByTestId('access-key-usage-export')).toHaveAttribute(
        'href',
        '/api/organizations/org-1/access-keys/usage/export.csv',
      )
      expect(api.orgKeyUsage).toHaveBeenCalledWith('org-1', 'k', {
        granularity: 'day',
      })

      fireEvent.click(screen.getByText('accessKeys.close'))
      expect(
        await screen.findByTestId('access-key-list-view'),
      ).toBeInTheDocument()
    })

    it('shows an unused key and a load failure', async () => {
      api.listOrgKeys.mockResolvedValue([makeKey({ id: 'k' })])
      api.orgKeyUsage.mockResolvedValueOnce({
        key_id: 'k',
        from: '',
        to: '',
        granularity: 'day',
        total_requests: 0,
        total_errors: 0,
        items: [],
      })
      api.orgKeyUsage.mockResolvedValueOnce(null as never)
      renderDialog()
      fireEvent.click(await screen.findByTestId('access-key-usage-k'))
      expect(
        await screen.findByTestId('access-key-usage-empty'),
      ).toBeInTheDocument()
      fireEvent.click(screen.getByText('accessKeys.close'))

      api.orgKeyUsage.mockRejectedValue(new Error('down'))
      fireEvent.click(await screen.findByTestId('access-key-usage-k'))
      expect(
        await screen.findByText('accessKeys.usage.loadFailed'),
      ).toBeInTheDocument()
    })
  })

  describe('group admins', () => {
    it('only create keys for their own groups', async () => {
      api.createOrgKey.mockResolvedValue(created())
      renderDialog({
        isAdmin: false,
        canManageGroups: true,
        adminGroupIds: ['g2'],
      })
      await openCreateForm()

      const group = screen.getByTestId('access-key-group')
      await waitFor(() =>
        expect(
          within(group)
            .getAllByRole('option')
            .map((o) => o.textContent),
        ).toEqual(['Lehrstuhl B']),
      )
      expect(
        screen.getByText('accessKeys.form.groupAdminHint'),
      ).toBeInTheDocument()

      // Org-admin-only scopes are not offered to group admins.
      fireEvent.click(screen.getByTestId('access-key-advanced-toggle'))
      expect(
        screen.queryByTestId('access-key-scope-compliance:admin'),
      ).not.toBeInTheDocument()

      fillName()
      await act(async () => {
        submitForm()
      })
      await screen.findByTestId('access-key-secret-panel')
      expect(api.createOrgKey.mock.calls[0][1]).toMatchObject({
        group_id: 'g2',
      })
    })

    it('cannot create keys without an active admin group', async () => {
      renderDialog({ isAdmin: false, canManageGroups: true, adminGroupIds: [] })
      await waitFor(() => expect(api.listOrgKeys).toHaveBeenCalled())
      expect(screen.getByTestId('access-key-new')).toBeDisabled()
    })
  })
})
