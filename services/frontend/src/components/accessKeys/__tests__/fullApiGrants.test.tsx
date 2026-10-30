/**
 * @jest-environment jsdom
 *
 * Core 2.45 grant rules in the key create form: the ORG_ADMIN role (org-wide
 * keys of org-wide admins only), the grantable values org_admin_role and
 * superadmin, the full_access preset and ORG_ADMIN renewal.
 */

import type { ScopeCatalog } from '@/lib/api/types'
import { lookup } from '@/lib/i18n/catalog'
import { makeKey, mockTranslate } from '@/test-utils/accessKeyFixtures'
import { fireEvent, render, screen, within } from '@testing-library/react'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: mockTranslate, locale: 'en' }),
}))

import { AccessKeyCreateForm } from '../AccessKeyCreateForm'
import {
  isScopeGrantable,
  isScopeOffered,
  offeredScopes,
  presetIds,
  renewalBody,
  resolvePreset,
  scopeDescription,
} from '../accessKeyUtils'

const scope = (name: string, grantable = 'any', implies: string[] = []) => ({
  name,
  description_de: `DE ${name}`,
  description_en: `EN ${name}`,
  implies,
  grantable,
})

const CATALOG: ScopeCatalog = {
  scopes: [
    scope('org:read'),
    scope('projects:write', 'any', ['projects:read']),
    scope('tasks:read_reference', 'full_data_role'),
    scope('org:manage', 'org_admin_role', ['org:read']),
    scope('keys:manage', 'personal_only'),
    scope('admin:platform', 'superadmin'),
    scope('compliance:admin', 'org_admin'),
  ],
  presets: {
    benchmark_read: ['org:read'],
    full_access: ['org:read', 'projects:write', 'tasks:read_reference'],
    org_admin_kit: ['org:read', 'org:manage'],
  },
}

const byName = (name: string) => CATALOG.scopes.find((s) => s.name === name)!

describe('grant rules (accessKeyUtils)', () => {
  const orgAdmin = { mode: 'org' as const, isOrgAdmin: true }
  const groupAdmin = { mode: 'org' as const, isOrgAdmin: false }
  const personal = { mode: 'personal' as const, isOrgAdmin: false }

  it('offers org_admin_role to personal keys and org-wide admins only', () => {
    const s = byName('org:manage')
    expect(isScopeOffered(s, personal)).toBe(true)
    expect(isScopeOffered(s, orgAdmin)).toBe(true)
    expect(isScopeOffered(s, groupAdmin)).toBe(false)
    expect(isScopeGrantable(s, { ...orgAdmin, role: 'CONTRIBUTOR' })).toBe(
      false,
    )
    expect(isScopeGrantable(s, { ...orgAdmin, role: 'ORG_ADMIN' })).toBe(true)
    expect(isScopeGrantable(s, { ...personal, role: 'ANNOTATOR' })).toBe(true)
  })

  it('offers admin:platform only on a superadmin personal key', () => {
    const s = byName('admin:platform')
    expect(isScopeOffered(s, personal)).toBe(false)
    expect(isScopeOffered(s, { ...personal, isSuperadmin: true })).toBe(true)
    expect(isScopeOffered(s, { ...orgAdmin, isSuperadmin: true })).toBe(false)
  })

  it('lets ORG_ADMIN keys hold full_data_role scopes', () => {
    const s = byName('tasks:read_reference')
    expect(isScopeGrantable(s, { ...orgAdmin, role: 'ORG_ADMIN' })).toBe(true)
    expect(isScopeGrantable(s, { ...orgAdmin, role: 'ANNOTATOR' })).toBe(false)
  })

  it('lists only what the creator may grant', () => {
    const names = (ctx: Parameters<typeof offeredScopes>[1]) =>
      offeredScopes(CATALOG, ctx).map((s) => s.name)
    expect(names(groupAdmin)).toEqual([
      'org:read',
      'projects:write',
      'tasks:read_reference',
    ])
    expect(names({ ...personal, isSuperadmin: true })).toContain(
      'admin:platform',
    )
    expect(names(personal)).not.toContain('admin:platform')
  })

  it('resolves the minimum role of a preset', () => {
    expect(resolvePreset(CATALOG, 'full_access', orgAdmin)).toEqual({
      scopes: ['org:read', 'projects:write', 'tasks:read_reference'],
      minRole: 'CONTRIBUTOR',
      needsContributor: true,
    })
    expect(resolvePreset(CATALOG, 'org_admin_kit', orgAdmin).minRole).toBe(
      'ORG_ADMIN',
    )
    expect(resolvePreset(CATALOG, 'full_access', personal).minRole).toBeNull()
  })

  it('orders full_access with the known presets', () => {
    expect(presetIds(CATALOG)).toEqual([
      'benchmark_read',
      'full_access',
      'org_admin_kit',
    ])
  })

  it('renews an ORG_ADMIN key with its role', () => {
    const key = makeKey({ org_role: 'ORG_ADMIN', scopes: ['org:manage'] })
    expect(renewalBody(key).org_role).toBe('ORG_ADMIN')
  })

  it('names the full_access preset in every language', () => {
    for (const lang of ['de', 'en', 'fr'] as const) {
      expect(typeof lookup(lang, 'accessKeys.presets.full_access.label')).toBe(
        'string',
      )
    }
    expect(lookup('de', 'accessKeys.presets.full_access.label')).toBe(
      'Volle API für Forschungs-Pipelines',
    )
  })

  it('describes the new scopes from the catalog', () => {
    expect(scopeDescription(byName('org:manage'), 'de')).toBe(
      'Organisation verwalten (Mitglieder, Gruppen, Einladungen, Einstellungen)',
    )
    expect(scopeDescription(byName('admin:platform'), 'fr')).toBe(
      'Droits de superadministrateur de la plateforme',
    )
  })
})

describe('AccessKeyCreateForm with the 2.45 grant rules', () => {
  const groups = [{ id: 'g1', name: 'Lehrstuhl A' }]

  const renderForm = (
    props: Partial<Parameters<typeof AccessKeyCreateForm>[0]> = {},
  ) => {
    const onSubmit = jest.fn().mockResolvedValue(undefined)
    render(
      <AccessKeyCreateForm
        mode="org"
        catalog={CATALOG}
        isOrgAdmin
        groups={groups}
        onSubmit={onSubmit}
        onCancel={jest.fn()}
        {...props}
      />,
    )
    return onSubmit
  }

  const roleValues = () =>
    within(screen.getByTestId('access-key-role'))
      .getAllByRole('option')
      .map((o) => (o as HTMLOptionElement).value)

  it('offers ORG_ADMIN to an org-wide admin for an org-wide key only', () => {
    renderForm()
    expect(roleValues()).toEqual(['ANNOTATOR', 'CONTRIBUTOR', 'ORG_ADMIN'])

    fireEvent.change(screen.getByTestId('access-key-role'), {
      target: { value: 'ORG_ADMIN' },
    })
    fireEvent.change(screen.getByTestId('access-key-group'), {
      target: { value: 'g1' },
    })
    // A group key cannot be an admin key: the role drops to CONTRIBUTOR.
    expect(screen.getByTestId('access-key-role')).toHaveValue('CONTRIBUTOR')
    expect(screen.getByTestId('access-key-role-notice')).toHaveTextContent(
      'accessKeys.form.roleLoweredForGroup',
    )
    expect(roleValues()).toEqual(['ANNOTATOR', 'CONTRIBUTOR'])
  })

  it('never offers ORG_ADMIN to a group admin', () => {
    renderForm({ isOrgAdmin: false })
    expect(roleValues()).toEqual(['ANNOTATOR', 'CONTRIBUTOR'])
  })

  it('shows org_admin_role scopes disabled until the role is ORG_ADMIN', () => {
    renderForm()
    fireEvent.click(screen.getByTestId('access-key-advanced-toggle'))
    expect(screen.getByTestId('access-key-scope-org:manage')).toBeDisabled()
    expect(
      screen.getByTestId('access-key-scope-needs-org:manage'),
    ).toHaveTextContent('accessKeys.form.needsOrgAdmin')
    // Not grantable for this kind of key at all: not listed.
    expect(
      screen.queryByTestId('access-key-scope-admin:platform'),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByTestId('access-key-scope-keys:manage'),
    ).not.toBeInTheDocument()

    fireEvent.change(screen.getByTestId('access-key-role'), {
      target: { value: 'ORG_ADMIN' },
    })
    expect(screen.getByTestId('access-key-scope-org:manage')).toBeEnabled()
  })

  it('switches to ORG_ADMIN and org-wide for a preset that needs it', () => {
    renderForm()
    fireEvent.change(screen.getByTestId('access-key-group'), {
      target: { value: 'g1' },
    })
    fireEvent.click(screen.getByTestId('access-key-preset-org_admin_kit'))
    expect(screen.getByTestId('access-key-role')).toHaveValue('ORG_ADMIN')
    expect(screen.getByTestId('access-key-role-notice')).toHaveTextContent(
      'accessKeys.form.roleSwitchedAdmin',
    )
  })

  it('submits the full_access preset with the CONTRIBUTOR role', async () => {
    const onSubmit = renderForm()
    expect(
      screen.getByTestId('access-key-preset-full_access'),
    ).toBeInTheDocument()
    fireEvent.change(screen.getByTestId('access-key-name'), {
      target: { value: 'Pipeline' },
    })
    fireEvent.click(screen.getByTestId('access-key-preset-full_access'))
    expect(screen.getByTestId('access-key-role')).toHaveValue('CONTRIBUTOR')
    fireEvent.click(screen.getByTestId('access-key-create-submit'))
    await screen.findByTestId('access-key-create-form')
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        org_role: 'CONTRIBUTOR',
        group_id: null,
        scopes: ['org:read', 'projects:write', 'tasks:read_reference'],
      }),
    )
  })

  it('keeps ORG_ADMIN when a preset needs less', () => {
    renderForm()
    fireEvent.change(screen.getByTestId('access-key-role'), {
      target: { value: 'ORG_ADMIN' },
    })
    fireEvent.click(screen.getByTestId('access-key-preset-full_access'))
    expect(screen.getByTestId('access-key-role')).toHaveValue('ORG_ADMIN')
    expect(
      screen.queryByTestId('access-key-role-notice'),
    ).not.toBeInTheDocument()
  })

  it('lists admin:platform on a superadmin personal key only', () => {
    const { unmount } = render(
      <AccessKeyCreateForm
        mode="personal"
        catalog={CATALOG}
        isSuperadmin
        onSubmit={jest.fn()}
        onCancel={jest.fn()}
      />,
    )
    fireEvent.click(screen.getByTestId('access-key-advanced-toggle'))
    expect(screen.getByTestId('access-key-scope-admin:platform')).toBeEnabled()
    expect(screen.getByTestId('access-key-scope-org:manage')).toBeEnabled()
    unmount()

    render(
      <AccessKeyCreateForm
        mode="personal"
        catalog={CATALOG}
        onSubmit={jest.fn()}
        onCancel={jest.fn()}
      />,
    )
    fireEvent.click(screen.getByTestId('access-key-advanced-toggle'))
    expect(
      screen.queryByTestId('access-key-scope-admin:platform'),
    ).not.toBeInTheDocument()
  })
})

describe('AccessKeySecretPanel', () => {
  it('keeps the /api/v1/me test and points to both API references', () => {
    // Imported lazily so the API client module stays out of the other tests.
    const { AccessKeySecretPanel } = require('../AccessKeyParts')
    render(
      <AccessKeySecretPanel
        secret="bgr_live_abcd1234_SECRET"
        accessKey={makeKey()}
      />,
    )
    expect(screen.getByTestId('access-key-test')).toBeInTheDocument()
    expect(screen.getByTestId('access-key-curl')).toHaveTextContent(
      '/api/v1/me',
    )
    expect(screen.getByTestId('access-key-reference-full')).toHaveAttribute(
      'href',
      'http://localhost/api/v1/reference',
    )
    expect(screen.getByTestId('access-key-reference-v1')).toHaveAttribute(
      'href',
      'http://localhost/api/v1/docs',
    )
  })
})
