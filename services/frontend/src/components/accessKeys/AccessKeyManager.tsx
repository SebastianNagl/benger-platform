'use client'

/**
 * Access-key management shared by the organization dialog and the profile
 * section: the key list, the create form, the show-once secret panel with
 * the connection test, renewal, revocation and the usage panel.
 *
 * Organization mode adds role, group and project allowlist. Group admins
 * (isOrgAdmin false) only create keys for their own groups; the API only
 * lists those groups' keys to them anyway.
 */

import { Button } from '@/components/shared/Button'
import { useI18n } from '@/contexts/I18nContext'
import { accessKeysAPI } from '@/lib/api/accessKeys'
import { organizationsAPI } from '@/lib/api/organizations'
import { projectsAPI } from '@/lib/api/projects'
import type {
  AccessKey,
  AccessKeyCreate,
  AccessKeyCreated,
  ScopeCatalog,
} from '@/lib/api/types'
import {
  ArrowPathIcon,
  ChartBarIcon,
  ExclamationTriangleIcon,
  NoSymbolIcon,
  PlusIcon,
} from '@heroicons/react/24/outline'
import Link from 'next/link'
import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  AccessKeyCreateForm,
  type GroupOption,
  type ProjectOption,
} from './AccessKeyCreateForm'
import {
  AccessKeySecretPanel,
  AccessKeyStatusBadge,
  AccessKeyUsagePanel,
  RevokeKeyPanel,
  ScopeChips,
} from './AccessKeyParts'
import {
  type AccessKeyMode,
  apiErrorCode,
  apiErrorMessage,
  daysUntil,
  expiresSoon,
  formatDate,
  renewalBody,
} from './accessKeyUtils'

export interface AccessKeyManagerProps {
  mode: AccessKeyMode
  /** Required in org mode. */
  organizationId?: string
  /** Org-wide admin (or superadmin). */
  isAdmin?: boolean
  /** Active groups the caller administers (group admins). */
  adminGroupIds?: string[]
  /** Load data only while visible (the org dialog is mounted closed). */
  active?: boolean
}

type View =
  | { kind: 'list' }
  | { kind: 'create' }
  | { kind: 'secret'; created: AccessKeyCreated; renewOf?: AccessKey }
  | { kind: 'revoke'; key: AccessKey }
  | { kind: 'renew'; key: AccessKey }
  | { kind: 'usage'; key: AccessKey }

interface ProjectRow {
  id: string
  title: string
  is_public?: boolean
  organizations?: Array<{ id: string; group_id?: string | null }>
}

export function AccessKeyManager({
  mode,
  organizationId,
  isAdmin = false,
  adminGroupIds = [],
  active = true,
}: AccessKeyManagerProps) {
  const { t, locale } = useI18n()
  const isOrg = mode === 'org'
  const [keys, setKeys] = useState<AccessKey[]>([])
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState(false)
  const [view, setView] = useState<View>({ kind: 'list' })
  const [catalog, setCatalog] = useState<ScopeCatalog | null>(null)
  const [groups, setGroups] = useState<GroupOption[]>([])
  const [projects, setProjects] = useState<ProjectRow[]>([])
  const [notice, setNotice] = useState<{
    type: 'success' | 'error'
    text: string
  } | null>(null)
  const [renewError, setRenewError] = useState<string | null>(null)
  const [renewBusy, setRenewBusy] = useState(false)

  const adminGroupKey = adminGroupIds.join(',')

  const loadKeys = useCallback(async () => {
    setLoading(true)
    setLoadError(false)
    try {
      const rows =
        isOrg && organizationId
          ? await accessKeysAPI.listOrgKeys(organizationId)
          : await accessKeysAPI.listMyKeys()
      setKeys(rows)
    } catch {
      setLoadError(true)
    } finally {
      setLoading(false)
    }
  }, [isOrg, organizationId])

  useEffect(() => {
    if (!active) return
    void loadKeys()
    if (isOrg && organizationId) {
      organizationsAPI
        .getGroups(organizationId)
        .then((rows) => {
          const allowed = new Set(adminGroupKey.split(',').filter(Boolean))
          setGroups(
            (rows ?? [])
              .filter((g) => g.is_active !== false)
              .filter((g) => isAdmin || allowed.has(g.id))
              .map((g) => ({ id: g.id, name: g.name })),
          )
        })
        .catch(() => setGroups([]))
    }
  }, [active, loadKeys, isOrg, organizationId, isAdmin, adminGroupKey])

  const ensureCatalog = useCallback(async () => {
    if (catalog) return
    try {
      setCatalog(await accessKeysAPI.scopes())
    } catch {
      setCatalog({ scopes: [], presets: {} })
    }
  }, [catalog])

  const openCreate = async () => {
    setNotice(null)
    await ensureCatalog()
    if (isOrg && projects.length === 0) {
      try {
        const page = await projectsAPI.list(1, 500)
        setProjects((page?.items ?? []) as ProjectRow[])
      } catch {
        setProjects([])
      }
    }
    setView({ kind: 'create' })
  }

  const createKey = (body: AccessKeyCreate) =>
    isOrg && organizationId
      ? accessKeysAPI.createOrgKey(organizationId, body)
      : accessKeysAPI.createMyKey(body)

  const revokeKey = (key: AccessKey, reason: string) =>
    isOrg && organizationId
      ? accessKeysAPI.revokeOrgKey(organizationId, key.id, reason)
      : accessKeysAPI.revokeMyKey(key.id, reason)

  const createErrorMessage = (error: unknown) =>
    apiErrorCode(error) === 'too_many_keys'
      ? t('accessKeys.form.tooManyKeys')
      : t('accessKeys.form.createFailed', { message: apiErrorMessage(error) })

  const handleCreate = async (body: AccessKeyCreate) => {
    let created: AccessKeyCreated
    try {
      created = await createKey(body)
    } catch (error) {
      throw new Error(createErrorMessage(error))
    }
    setView({ kind: 'secret', created })
    void loadKeys()
  }

  const handleRenew = async (key: AccessKey) => {
    setRenewBusy(true)
    setRenewError(null)
    try {
      const created = await createKey(renewalBody(key))
      setView({ kind: 'secret', created, renewOf: key })
      void loadKeys()
    } catch (error) {
      setRenewError(
        apiErrorCode(error) === 'too_many_keys'
          ? t('accessKeys.form.tooManyKeys')
          : t('accessKeys.renew.failed', { message: apiErrorMessage(error) }),
      )
    } finally {
      setRenewBusy(false)
    }
  }

  const handleRevoke = async (key: AccessKey, reason: string) => {
    await revokeKey(key, reason)
    setNotice({ type: 'success', text: t('accessKeys.revoke.success') })
    setView({ kind: 'list' })
    void loadKeys()
  }

  const revokeOld = async (oldKey: AccessKey, newPrefix: string) => {
    try {
      await revokeKey(
        oldKey,
        t('accessKeys.renew.reason', { prefix: newPrefix }),
      )
      setNotice({ type: 'success', text: t('accessKeys.renew.oldRevoked') })
    } catch (error) {
      setNotice({
        type: 'error',
        text: t('accessKeys.revoke.failed', {
          message: apiErrorMessage(error),
        }),
      })
    }
    setView({ kind: 'list' })
    void loadKeys()
  }

  const groupName = useCallback(
    (id: string | null) =>
      id
        ? (groups.find((g) => g.id === id)?.name ?? id)
        : t('accessKeys.orgWide'),
    [groups, t],
  )

  // Projects the selected scope can list: public ones and those attached
  // to the org. The API checks again on create.
  const projectOptions: ProjectOption[] = useMemo(
    () =>
      projects
        .filter(
          (p) =>
            p.is_public ||
            (p.organizations ?? []).some((o) => o.id === organizationId),
        )
        .map((p) => ({ id: p.id, title: p.title })),
    [projects, organizationId],
  )

  const usageLoader = (key: AccessKey) => (granularity: 'day' | 'route') =>
    isOrg && organizationId
      ? accessKeysAPI.orgKeyUsage(organizationId, key.id, { granularity })
      : accessKeysAPI.myKeyUsage(key.id, { granularity })

  if (view.kind === 'create') {
    return (
      <AccessKeyCreateForm
        mode={mode}
        catalog={catalog}
        isOrgAdmin={isAdmin}
        groups={groups}
        projects={projectOptions}
        onSubmit={handleCreate}
        onCancel={() => setView({ kind: 'list' })}
      />
    )
  }

  if (view.kind === 'secret') {
    const { created, renewOf } = view
    return (
      <AccessKeySecretPanel
        secret={created.secret}
        accessKey={created.key}
        onDone={renewOf ? undefined : () => setView({ kind: 'list' })}
        footer={
          renewOf ? (
            <div
              className="space-y-3 rounded-md border border-zinc-200 p-3 dark:border-zinc-700"
              data-testid="access-key-renew-choices"
            >
              <p className="text-sm text-zinc-700 dark:text-zinc-300">
                {t('accessKeys.renew.oldStillActive', {
                  name: renewOf.name,
                  prefix: renewOf.key_prefix,
                })}
              </p>
              <div className="flex flex-wrap justify-end gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setView({ kind: 'list' })}
                  data-testid="access-key-keep-old"
                >
                  {t('accessKeys.renew.keepOld')}
                </Button>
                <Button
                  type="button"
                  variant="filled"
                  onClick={() => revokeOld(renewOf, created.key.key_prefix)}
                  data-testid="access-key-revoke-old"
                >
                  {t('accessKeys.renew.revokeOld')}
                </Button>
              </div>
            </div>
          ) : undefined
        }
      />
    )
  }

  if (view.kind === 'revoke') {
    return (
      <RevokeKeyPanel
        accessKey={view.key}
        onConfirm={(reason) => handleRevoke(view.key, reason)}
        onCancel={() => setView({ kind: 'list' })}
      />
    )
  }

  if (view.kind === 'renew') {
    const key = view.key
    return (
      <div className="space-y-4" data-testid="access-key-renew-panel">
        <h3 className="text-base font-semibold text-zinc-900 dark:text-white">
          {t('accessKeys.renew.title')}: {key.name}
        </h3>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          {t('accessKeys.renew.hint')}
        </p>
        {renewError && (
          <p className="text-sm text-red-600 dark:text-red-400" role="alert">
            {renewError}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setRenewError(null)
              setView({ kind: 'list' })
            }}
          >
            {t('accessKeys.cancel')}
          </Button>
          <Button
            type="button"
            variant="filled"
            disabled={renewBusy}
            onClick={() => handleRenew(key)}
            data-testid="access-key-renew-confirm"
          >
            {t('accessKeys.renew.confirm')}
          </Button>
        </div>
      </div>
    )
  }

  if (view.kind === 'usage') {
    return (
      <AccessKeyUsagePanel
        accessKey={view.key}
        load={usageLoader(view.key)}
        exportUrl={
          isOrg && organizationId
            ? accessKeysAPI.orgUsageExportUrl(organizationId)
            : undefined
        }
        onClose={() => setView({ kind: 'list' })}
      />
    )
  }

  return (
    <div className="space-y-4" data-testid="access-key-list-view">
      {notice && (
        <div
          className={`rounded-md border p-3 text-sm ${
            notice.type === 'success'
              ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-400'
              : 'border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/50 dark:text-red-400'
          }`}
          data-testid="access-key-notice"
        >
          {notice.text}
        </div>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Link
          href="/how-to#api-zugaenge"
          className="text-sm text-emerald-600 hover:underline dark:text-emerald-400"
        >
          {t('accessKeys.howToLink')}
        </Link>
        <Button
          type="button"
          variant="filled"
          onClick={openCreate}
          disabled={isOrg && !isAdmin && adminGroupIds.length === 0}
          data-testid="access-key-new"
        >
          <PlusIcon className="h-4 w-4" />
          {t('accessKeys.newKey')}
        </Button>
      </div>

      {loading && keys.length === 0 ? (
        <p className="text-sm text-zinc-500">{t('accessKeys.loading')}</p>
      ) : loadError ? (
        <p className="text-sm text-red-600 dark:text-red-400" role="alert">
          {t('accessKeys.loadFailed')}
        </p>
      ) : keys.length === 0 ? (
        <p className="text-sm text-zinc-500" data-testid="access-key-empty">
          {t('accessKeys.empty')}
        </p>
      ) : (
        <ul
          className="divide-y divide-zinc-200 rounded-lg border border-zinc-200 dark:divide-zinc-700 dark:border-zinc-700"
          data-testid="access-key-list"
        >
          {keys.map((key) => (
            <KeyRow
              key={key.id}
              accessKey={key}
              isOrg={isOrg}
              groupName={groupName}
              locale={locale}
              onUsage={() => setView({ kind: 'usage', key })}
              onRenew={() => {
                setRenewError(null)
                setView({ kind: 'renew', key })
              }}
              onRevoke={() => setView({ kind: 'revoke', key })}
            />
          ))}
        </ul>
      )}
    </div>
  )
}

interface KeyRowProps {
  accessKey: AccessKey
  isOrg: boolean
  groupName: (id: string | null) => string
  locale: string
  onUsage: () => void
  onRenew: () => void
  onRevoke: () => void
}

function KeyRow({
  accessKey: key,
  isOrg,
  groupName,
  locale,
  onUsage,
  onRenew,
  onRevoke,
}: KeyRowProps) {
  const { t } = useI18n()
  const soon = expiresSoon(key)
  const days = daysUntil(key.expires_at)
  const isActive = key.status === 'active'

  return (
    <li className="space-y-2 p-3" data-testid={`access-key-row-${key.id}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-zinc-900 dark:text-white">
            {key.name}
          </p>
          <p className="font-mono text-xs text-zinc-500">{key.key_prefix}</p>
        </div>
        <AccessKeyStatusBadge status={key.status} />
      </div>
      <ScopeChips scopes={key.scopes} />
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-zinc-600 sm:grid-cols-3 dark:text-zinc-400">
        {isOrg && (
          <>
            <div>
              <dt className="inline font-medium">
                {t('accessKeys.columns.role')}:{' '}
              </dt>
              <dd className="inline">
                {key.org_role === 'CONTRIBUTOR'
                  ? t('admin.organizations.roleContributor')
                  : t('admin.organizations.roleAnnotator')}
              </dd>
            </div>
            <div>
              <dt className="inline font-medium">
                {t('accessKeys.columns.group')}:{' '}
              </dt>
              <dd className="inline">{groupName(key.group_id)}</dd>
            </div>
          </>
        )}
        <div>
          <dt className="inline font-medium">
            {t('accessKeys.columns.projects')}:{' '}
          </dt>
          <dd className="inline">
            {key.project_ids
              ? t('accessKeys.projectsCount', { count: key.project_ids.length })
              : t('accessKeys.allProjects')}
          </dd>
        </div>
        <div>
          <dt className="inline font-medium">
            {t('accessKeys.columns.expires')}:{' '}
          </dt>
          <dd
            className={`inline ${soon ? 'font-medium text-amber-700 dark:text-amber-400' : ''}`}
          >
            {key.expires_at
              ? formatDate(key.expires_at, locale)
              : t('accessKeys.noExpiry')}
            {soon && days !== null && (
              <span
                className="ml-1 inline-flex items-center gap-0.5"
                data-testid="access-key-expiry-warning"
              >
                <ExclamationTriangleIcon className="h-3.5 w-3.5" />
                {t('accessKeys.expiresSoon', { days: Math.max(days, 0) })}
              </span>
            )}
          </dd>
        </div>
        <div>
          <dt className="inline font-medium">
            {t('accessKeys.columns.lastUsed')}:{' '}
          </dt>
          <dd className="inline">
            {key.last_used_at
              ? formatDate(key.last_used_at, locale)
              : t('accessKeys.never')}
          </dd>
        </div>
      </dl>
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          onClick={onUsage}
          data-testid={`access-key-usage-${key.id}`}
        >
          <ChartBarIcon className="h-4 w-4" />
          {t('accessKeys.actions.usage')}
        </Button>
        {isActive && (
          <>
            <Button
              type="button"
              variant="outline"
              onClick={onRenew}
              data-testid={`access-key-renew-${key.id}`}
            >
              <ArrowPathIcon className="h-4 w-4" />
              {t('accessKeys.actions.renew')}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={onRevoke}
              data-testid={`access-key-revoke-${key.id}`}
            >
              <NoSymbolIcon className="h-4 w-4" />
              {t('accessKeys.actions.revoke')}
            </Button>
          </>
        )}
      </div>
    </li>
  )
}
