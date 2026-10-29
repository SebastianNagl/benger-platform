'use client'

/**
 * Superadmin console for the feature flags, rendered by
 * /admin/feature-flags (the page holds the superadmin guard).
 *
 * Flags are grouped by owner (platform first, then each extension package);
 * a package's master flag (`extension.<id>`, `is_master`) leads its group.
 * One card per flag: name, description, a three-way state control
 * (Off / Everyone / Allowlist) and, for `allowlist`, the allowlist editor
 * (user search, organization picker, removable chips). Every change saves at
 * once, confirms with a toast and refreshes this browser's flag store so the
 * admin sees the effect without a reload. Switching a master flag off asks
 * first. Rows no loaded package registers any more are marked and can be
 * deleted.
 */

import { XMarkIcon } from '@heroicons/react/24/outline'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Card } from '@/components/shared/Card'
import { ConfirmationDialog } from '@/components/shared/ConfirmationDialog'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { SearchInput } from '@/components/shared/SearchInput'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shared/Select'
import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import apiClient from '@/lib/api'
import {
  featureFlagsAPI,
  type FeatureFlagAdminRow,
  type FeatureFlagState,
  type FeatureFlagTarget,
} from '@/lib/api/featureFlags'
import { refreshFeatureFlags } from '@/lib/featureFlags'
import { intlTag } from '@/lib/i18n/locales'

type T = (key: string, vars?: Record<string, unknown>) => string

const K = 'admin.featureFlagsConsole'

const STATES: FeatureFlagState[] = ['off', 'everyone', 'allowlist']

const PLATFORM_OWNER = 'platform'
// Rows no loaded package registers carry no owner; they get their own group
// at the end instead of landing under the platform.
const UNREGISTERED_GROUP = 'unregistered'

const USER_SEARCH_DEBOUNCE_MS = 300
const USER_SEARCH_LIMIT = 8

interface UserOption {
  id: string
  name?: string | null
  username?: string | null
  email?: string | null
  pseudonym?: string | null
}

interface OrgOption {
  id: string
  name: string
  display_name?: string | null
}

export interface FlagGroup {
  owner: string
  rows: FeatureFlagAdminRow[]
}

/**
 * Rows grouped by owner: platform first, then the packages by name, then the
 * rows no loaded package registers any more. Within a group the master flag
 * leads and the others follow by name.
 */
export function groupFlags(rows: FeatureFlagAdminRow[]): FlagGroup[] {
  const byOwner = new Map<string, FeatureFlagAdminRow[]>()
  for (const row of rows) {
    const owner =
      row.registered === false
        ? UNREGISTERED_GROUP
        : row.owner || PLATFORM_OWNER
    const list = byOwner.get(owner) ?? []
    list.push(row)
    byOwner.set(owner, list)
  }
  const rank = (row: FeatureFlagAdminRow) => (row.is_master ? 0 : 1)
  const order = (owner: string) =>
    owner === PLATFORM_OWNER ? 0 : owner === UNREGISTERED_GROUP ? 2 : 1
  return [...byOwner.entries()]
    .sort(([a], [b]) => order(a) - order(b) || a.localeCompare(b))
    .map(([owner, list]) => ({
      owner,
      rows: [...list].sort(
        (a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name),
      ),
    }))
}

function errorText(error: unknown): string | null {
  const detail = (error as { response?: { data?: { detail?: unknown } } })
    ?.response?.data?.detail
  if (detail && typeof detail === 'object' && 'message' in detail) {
    const message = (detail as { message?: unknown }).message
    if (typeof message === 'string' && message) return message
  }
  if (typeof detail === 'string' && detail) return detail
  return error instanceof Error && error.message ? error.message : null
}

/** "Pseudonym (Name)" when the account has a pseudonym, else the name. */
export function targetLabel(target: FeatureFlagTarget): string {
  if (target.kind === 'organization') {
    return target.name || target.organization_id || ''
  }
  const real = target.name || target.username || target.user_id || ''
  return target.pseudonym ? `${target.pseudonym} (${real})` : real
}

export function FeatureFlagsAdmin() {
  const { t, locale } = useI18n()
  const { addToast } = useToast()
  const [rows, setRows] = useState<FeatureFlagAdminRow[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [orgs, setOrgs] = useState<OrgOption[]>([])
  const [confirmOff, setConfirmOff] = useState<FeatureFlagAdminRow | null>(null)
  const [confirmDelete, setConfirmDelete] =
    useState<FeatureFlagAdminRow | null>(null)

  // `loadError` holds the server's message, or '' for "no message" (the
  // fallback text is picked at render time, so the loader has no deps).
  const load = useCallback(async () => {
    setLoading(true)
    try {
      const list = await featureFlagsAPI.list()
      setRows(Array.isArray(list) ? list : [])
      setLoadError(null)
    } catch (e) {
      setLoadError(errorText(e) ?? '')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    let cancelled = false
    Promise.resolve(apiClient.getOrganizations())
      .then((list: OrgOption[]) => {
        if (!cancelled && Array.isArray(list)) setOrgs(list)
      })
      .catch(() => {
        /* the org picker just stays empty */
      })
    return () => {
      cancelled = true
    }
  }, [])

  const groups = useMemo(() => groupFlags(rows), [rows])

  const formatDate = useCallback(
    (iso: string | null) => {
      if (!iso) return null
      const date = new Date(iso)
      if (Number.isNaN(date.getTime())) return null
      return new Intl.DateTimeFormat(intlTag(locale), {
        dateStyle: 'medium',
        timeStyle: 'short',
      }).format(date)
    },
    [locale],
  )

  const replaceRow = (
    name: string,
    update: (row: FeatureFlagAdminRow) => FeatureFlagAdminRow,
  ) =>
    setRows((current) =>
      current.map((row) => (row.name === name ? update(row) : row)),
    )

  const failed = (e: unknown) =>
    addToast(errorText(e) ?? t(`${K}.saveFailed`), 'error')

  const saveState = async (
    row: FeatureFlagAdminRow,
    state: FeatureFlagState,
  ) => {
    setBusy(row.name)
    try {
      const saved = await featureFlagsAPI.setState(row.name, state)
      replaceRow(row.name, (r) => ({ ...r, ...saved }))
      addToast(
        t(`${K}.stateSaved`, {
          flag: row.name,
          state: t(`${K}.state.${state}`),
        }),
        'success',
      )
      void refreshFeatureFlags()
    } catch (e) {
      failed(e)
    } finally {
      setBusy(null)
    }
  }

  const setState = (row: FeatureFlagAdminRow, state: FeatureFlagState) => {
    if (row.state === state || busy) return
    if (row.is_master && state === 'off') {
      setConfirmOff(row)
      return
    }
    void saveState(row, state)
  }

  const addTarget = async (
    row: FeatureFlagAdminRow,
    body: { user_id: string } | { organization_id: string },
  ) => {
    setBusy(row.name)
    try {
      const target = await featureFlagsAPI.addTarget(row.name, body)
      replaceRow(row.name, (r) => ({ ...r, targets: [...r.targets, target] }))
      addToast(
        t(`${K}.targetAdded`, { target: targetLabel(target) }),
        'success',
      )
      void refreshFeatureFlags()
    } catch (e) {
      failed(e)
    } finally {
      setBusy(null)
    }
  }

  const removeTarget = async (
    row: FeatureFlagAdminRow,
    target: FeatureFlagTarget,
  ) => {
    setBusy(row.name)
    try {
      await featureFlagsAPI.removeTarget(row.name, target.id)
      replaceRow(row.name, (r) => ({
        ...r,
        targets: r.targets.filter((x) => x.id !== target.id),
      }))
      addToast(
        t(`${K}.targetRemoved`, { target: targetLabel(target) }),
        'success',
      )
      void refreshFeatureFlags()
    } catch (e) {
      failed(e)
    } finally {
      setBusy(null)
    }
  }

  const removeRow = async (row: FeatureFlagAdminRow) => {
    setBusy(row.name)
    try {
      await featureFlagsAPI.remove(row.name)
      setRows((current) => current.filter((r) => r.name !== row.name))
      addToast(t(`${K}.deleted`, { flag: row.name }), 'success')
      void refreshFeatureFlags()
    } catch (e) {
      failed(e)
    } finally {
      setBusy(null)
    }
  }

  return (
    <ResponsiveContainer size="xl" className="pt-8 pb-10">
      <div className="mb-4">
        <Breadcrumb
          items={[
            { label: t('navigation.dashboard'), href: '/dashboard' },
            { label: t('admin.featureFlags'), href: '/admin/feature-flags' },
          ]}
        />
      </div>
      <div className="space-y-6" data-testid="feature-flags-admin">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
            {t('admin.featureFlags')}
          </h1>
          <p className="mt-2 text-zinc-600 dark:text-zinc-400">
            {t(`${K}.intro`)}
          </p>
        </div>

        {loadError !== null && (
          <p className="text-sm text-red-600" data-testid="feature-flags-error">
            {loadError || t(`${K}.loadFailed`)}
          </p>
        )}

        {loading && rows.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            {t('common.loading')}
          </p>
        ) : (
          groups.map((group) => (
            <section
              key={group.owner}
              className="space-y-3"
              data-testid={`ff-group-${group.owner}`}
            >
              <h2 className="text-sm font-semibold tracking-wide text-zinc-500 uppercase dark:text-zinc-400">
                {group.owner === PLATFORM_OWNER
                  ? t(`${K}.groupPlatform`)
                  : group.owner === UNREGISTERED_GROUP
                    ? t(`${K}.groupUnregistered`)
                    : t(`${K}.groupPackage`, { owner: group.owner })}
              </h2>
              {group.rows.map((row) => (
                <FlagCard
                  key={row.name}
                  row={row}
                  t={t}
                  busy={busy === row.name}
                  orgs={orgs}
                  updatedAt={formatDate(row.updated_at)}
                  onState={(state) => setState(row, state)}
                  onAdd={(body) => void addTarget(row, body)}
                  onRemove={(target) => void removeTarget(row, target)}
                  onDelete={() => setConfirmDelete(row)}
                />
              ))}
            </section>
          ))
        )}
      </div>

      <ConfirmationDialog
        isOpen={confirmOff !== null}
        onClose={() => setConfirmOff(null)}
        onConfirm={() => {
          const row = confirmOff
          setConfirmOff(null)
          if (row) void saveState(row, 'off')
        }}
        title={t(`${K}.masterOffTitle`, { owner: confirmOff?.owner ?? '' })}
        message={t(`${K}.masterOffMessage`)}
        confirmText={t(`${K}.masterOffConfirm`)}
        cancelText={t('common.cancel')}
        variant="danger"
      />

      <ConfirmationDialog
        isOpen={confirmDelete !== null}
        onClose={() => setConfirmDelete(null)}
        onConfirm={() => {
          const row = confirmDelete
          setConfirmDelete(null)
          if (row) void removeRow(row)
        }}
        title={t(`${K}.deleteTitle`, { flag: confirmDelete?.name ?? '' })}
        message={t(`${K}.deleteMessage`)}
        confirmText={t('common.delete')}
        cancelText={t('common.cancel')}
        variant="danger"
      />
    </ResponsiveContainer>
  )
}

function FlagCard({
  row,
  t,
  busy,
  orgs,
  updatedAt,
  onState,
  onAdd,
  onRemove,
  onDelete,
}: {
  row: FeatureFlagAdminRow
  t: T
  busy: boolean
  orgs: OrgOption[]
  updatedAt: string | null
  onState: (state: FeatureFlagState) => void
  onAdd: (body: { user_id: string } | { organization_id: string }) => void
  onRemove: (target: FeatureFlagTarget) => void
  onDelete: () => void
}) {
  const unregistered = row.registered === false
  return (
    <Card className="p-5" data-testid={`ff-row-${row.name}`}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-mono text-sm font-semibold break-all text-zinc-900 dark:text-white">
              {row.name}
            </h3>
            {row.is_master && (
              <span
                className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-medium text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300"
                data-testid={`ff-master-${row.name}`}
              >
                {t(`${K}.masterBadge`)}
              </span>
            )}
            {unregistered && (
              <span
                className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
                data-testid={`ff-unregistered-${row.name}`}
              >
                {t(`${K}.unregistered`)}
              </span>
            )}
          </div>
          {row.description && (
            <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
              {row.description}
            </p>
          )}
          {unregistered && (
            <p className="mt-1 text-sm text-amber-700 dark:text-amber-400">
              {t(`${K}.unregisteredHint`)}
            </p>
          )}
          <p className="mt-1 text-xs text-zinc-400 dark:text-zinc-500">
            {[
              row.default_state &&
                t(`${K}.default`, {
                  state: t(`${K}.state.${row.default_state}`),
                }),
              updatedAt && t(`${K}.updatedAt`, { date: updatedAt }),
            ]
              .filter(Boolean)
              .join(' · ')}
          </p>
        </div>
        {unregistered ? (
          <button
            type="button"
            disabled={busy}
            onClick={onDelete}
            className="h-8 shrink-0 rounded-full border border-red-300 px-3 text-sm font-medium text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-red-700 dark:text-red-400 dark:hover:bg-red-950"
            data-testid={`ff-delete-${row.name}`}
          >
            {t('common.delete')}
          </button>
        ) : (
          <div
            role="radiogroup"
            aria-label={row.name}
            className="inline-flex shrink-0 items-center gap-0.5 rounded-full bg-zinc-100 p-0.5 dark:bg-zinc-800"
          >
            {STATES.map((state) => {
              const active = row.state === state
              return (
                <button
                  key={state}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  disabled={busy}
                  onClick={() => onState(state)}
                  data-testid={`ff-state-${row.name}-${state}`}
                  className={`h-7 rounded-full px-3 text-sm font-medium whitespace-nowrap transition-colors disabled:cursor-not-allowed ${
                    active
                      ? 'bg-white text-zinc-900 shadow-sm dark:bg-zinc-700 dark:text-white'
                      : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white'
                  } focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-zinc-900`}
                >
                  {t(`${K}.state.${state}`)}
                </button>
              )
            })}
          </div>
        )}
      </div>

      {!unregistered && row.state === 'allowlist' && (
        <AllowlistEditor
          row={row}
          t={t}
          busy={busy}
          orgs={orgs}
          onAdd={onAdd}
          onRemove={onRemove}
        />
      )}
    </Card>
  )
}

function AllowlistEditor({
  row,
  t,
  busy,
  orgs,
  onAdd,
  onRemove,
}: {
  row: FeatureFlagAdminRow
  t: T
  busy: boolean
  orgs: OrgOption[]
  onAdd: (body: { user_id: string } | { organization_id: string }) => void
  onRemove: (target: FeatureFlagTarget) => void
}) {
  const [query, setQuery] = useState('')
  // Search answers keyed by their term: an answer only shows while the box
  // still holds that term, so clearing the box needs no state reset.
  const [found, setFound] = useState<{ term: string; users: UserOption[] }>({
    term: '',
    users: [],
  })
  const [orgId, setOrgId] = useState('')
  const term = query.trim()
  const results = term.length >= 2 && found.term === term ? found.users : []

  useEffect(() => {
    if (term.length < 2) return
    let cancelled = false
    const timer = setTimeout(() => {
      Promise.resolve(
        apiClient.getAllUsers({ search: term, limit: USER_SEARCH_LIMIT }),
      )
        .then((users: UserOption[]) => {
          if (!cancelled) {
            setFound({ term, users: Array.isArray(users) ? users : [] })
          }
        })
        .catch(() => {
          if (!cancelled) setFound({ term, users: [] })
        })
    }, USER_SEARCH_DEBOUNCE_MS)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [term])

  const listedUsers = new Set(row.targets.map((x) => x.user_id).filter(Boolean))
  const listedOrgs = new Set(
    row.targets.map((x) => x.organization_id).filter(Boolean),
  )
  const freeOrgs = orgs.filter((o) => !listedOrgs.has(o.id))

  return (
    <div
      className="mt-4 space-y-3 border-t border-zinc-200 pt-4 dark:border-zinc-700"
      data-testid={`ff-allowlist-${row.name}`}
    >
      {row.targets.length === 0 ? (
        <p className="text-sm text-amber-700 dark:text-amber-400">
          {t(`${K}.allowlistEmpty`)}
        </p>
      ) : (
        <ul className="flex flex-wrap gap-2">
          {row.targets.map((target) => (
            <li
              key={target.id}
              className="inline-flex items-center gap-1 rounded-full bg-zinc-100 py-1 pr-1 pl-3 text-sm text-zinc-800 dark:bg-zinc-800 dark:text-zinc-200"
              data-testid={`ff-target-${target.id}`}
              title={target.email ?? undefined}
            >
              <span className="text-xs text-zinc-500 dark:text-zinc-400">
                {target.kind === 'user'
                  ? t(`${K}.kindUser`)
                  : t(`${K}.kindOrg`)}
              </span>
              <span>{targetLabel(target)}</span>
              <button
                type="button"
                disabled={busy}
                onClick={() => onRemove(target)}
                aria-label={t('common.remove')}
                className="rounded-full p-0.5 text-zinc-500 hover:bg-zinc-200 hover:text-zinc-900 disabled:cursor-not-allowed dark:hover:bg-zinc-700 dark:hover:text-white"
                data-testid={`ff-target-remove-${target.id}`}
              >
                <XMarkIcon className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label
            className="block text-xs font-medium text-zinc-600 dark:text-zinc-400"
            htmlFor={`ff-user-search-${row.name}`}
          >
            {t(`${K}.addUser`)}
          </label>
          <SearchInput
            id={`ff-user-search-${row.name}`}
            value={query}
            onChange={setQuery}
            placeholder={t(`${K}.userSearch`)}
            className="mt-1"
            data-testid={`ff-user-search-${row.name}`}
          />
          {results.length > 0 && (
            <ul className="mt-1 max-h-48 overflow-y-auto rounded-md border border-zinc-200 dark:border-zinc-700">
              {results.map((user) => {
                const listed = listedUsers.has(user.id)
                return (
                  <li key={user.id}>
                    <button
                      type="button"
                      disabled={busy || listed}
                      onClick={() => {
                        onAdd({ user_id: user.id })
                        setQuery('')
                      }}
                      className="flex w-full flex-col items-start px-3 py-1.5 text-left text-sm hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-zinc-800"
                      data-testid={`ff-user-option-${user.id}`}
                    >
                      <span className="text-zinc-900 dark:text-white">
                        {user.pseudonym
                          ? `${user.pseudonym} (${user.name || user.username || user.id})`
                          : user.name || user.username || user.id}
                      </span>
                      {user.email && (
                        <span className="text-xs text-zinc-500 dark:text-zinc-400">
                          {user.email}
                        </span>
                      )}
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
        <div>
          <label
            className="block text-xs font-medium text-zinc-600 dark:text-zinc-400"
            htmlFor={`ff-org-select-${row.name}`}
          >
            {t(`${K}.addOrg`)}
          </label>
          <div className="mt-1 flex gap-2">
            <div className="min-w-0 flex-1">
              <Select value={orgId} onValueChange={setOrgId}>
                <SelectTrigger
                  id={`ff-org-select-${row.name}`}
                  data-testid={`ff-org-select-${row.name}`}
                >
                  <SelectValue placeholder={t(`${K}.pickOrg`)} />
                </SelectTrigger>
                <SelectContent>
                  {freeOrgs.map((org) => (
                    <SelectItem key={org.id} value={org.id}>
                      {org.display_name || org.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <button
              type="button"
              disabled={busy || !orgId}
              onClick={() => {
                onAdd({ organization_id: orgId })
                setOrgId('')
              }}
              className="h-8 shrink-0 rounded-full bg-zinc-900 px-3 text-sm font-medium text-white hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-emerald-500 dark:hover:bg-emerald-400"
              data-testid={`ff-org-add-${row.name}`}
            >
              {t('common.add')}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default FeatureFlagsAdmin
