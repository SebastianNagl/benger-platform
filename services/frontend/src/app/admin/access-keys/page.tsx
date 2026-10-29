'use client'

/**
 * Superadmin overview of every access key (`bgr_...`): filter by
 * organization, owner type and status, revoke any key at once, download the
 * usage CSV. Keys are managed by their owners in the organization dialog or
 * on the profile page; this page is the emergency brake and the audit view.
 */

import NotFound from '@/app/not-found'
import {
  AccessKeyStatusBadge,
  RevokeKeyPanel,
  ScopeChips,
} from '@/components/accessKeys/AccessKeyParts'
import { formatDate } from '@/components/accessKeys/accessKeyUtils'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Button } from '@/components/shared/Button'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shared/Select'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { usePublicApiEnabled } from '@/hooks/usePublicApiEnabled'
import { accessKeysAPI } from '@/lib/api/accessKeys'
import { organizationsAPI } from '@/lib/api/organizations'
import type {
  AccessKey,
  AccessKeyOwnerType,
  AccessKeyStatus,
  Organization,
} from '@/lib/api/types'
import { useCallback, useEffect, useState } from 'react'

// The Select treats an empty value as unset, so "all" gets a sentinel.
const ALL = '__all__'
const fromSelect = (v: string) => (v === ALL ? '' : v)

export default function AdminAccessKeysPage() {
  const { user } = useAuth()
  const { t, locale } = useI18n()
  const isSuperadmin = Boolean(user?.is_superadmin)
  // The page does not exist unless the public API is on for this user.
  const publicApiEnabled = usePublicApiEnabled()
  const canView = isSuperadmin && publicApiEnabled === true

  const [organizations, setOrganizations] = useState<Organization[]>([])
  const [orgFilter, setOrgFilter] = useState('')
  const [ownerFilter, setOwnerFilter] = useState<AccessKeyOwnerType | ''>('')
  const [statusFilter, setStatusFilter] = useState<AccessKeyStatus | ''>('')
  const [keys, setKeys] = useState<AccessKey[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)
  const [revoking, setRevoking] = useState<AccessKey | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const load = useCallback(
    async (after?: string) => {
      setLoading(true)
      setError(false)
      try {
        const page = await accessKeysAPI.adminListKeys({
          organization_id: orgFilter || undefined,
          owner_type: ownerFilter || undefined,
          status: statusFilter || undefined,
          cursor: after,
        })
        setKeys((prev) => (after ? [...prev, ...page.items] : page.items))
        setCursor(page.next_cursor)
      } catch {
        setError(true)
      } finally {
        setLoading(false)
      }
    },
    [orgFilter, ownerFilter, statusFilter],
  )

  useEffect(() => {
    if (!canView) return
    void load()
  }, [canView, load])

  useEffect(() => {
    if (!canView) return
    organizationsAPI
      .getOrganizations()
      .then((rows) => setOrganizations(rows ?? []))
      .catch(() => setOrganizations([]))
  }, [canView])

  const orgName = (id: string | null) =>
    id ? (organizations.find((o) => o.id === id)?.name ?? id) : ''

  const breadcrumb = (
    <div className="mb-4">
      <Breadcrumb
        items={[
          { label: t('navigation.dashboard'), href: '/dashboard' },
          { label: t('accessKeys.admin.title'), href: '/admin/access-keys' },
        ]}
      />
    </div>
  )

  if (publicApiEnabled === null) {
    return (
      <div
        className="flex justify-center py-16"
        data-testid="admin-access-keys-loading"
      >
        <LoadingSpinner />
      </div>
    )
  }

  if (!publicApiEnabled) {
    return <NotFound />
  }

  if (!isSuperadmin) {
    return (
      <ResponsiveContainer size="xl" className="pt-8 pb-10">
        {breadcrumb}
        <div className="text-center" data-testid="admin-access-keys-denied">
          <h1 className="text-2xl font-bold text-red-600">
            {t('admin.accessDenied')}
          </h1>
          <p className="mt-2 text-zinc-600 dark:text-zinc-400">
            {t('admin.accessDeniedDesc')}
          </p>
        </div>
      </ResponsiveContainer>
    )
  }

  return (
    <ResponsiveContainer size="xl" className="pt-8 pb-10">
      {breadcrumb}
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
            {t('accessKeys.admin.title')}
          </h1>
          <p className="mt-2 text-zinc-600 dark:text-zinc-400">
            {t('accessKeys.admin.description')}
          </p>
        </div>
        <a
          href={accessKeysAPI.adminUsageExportUrl({
            organization_id: orgFilter || undefined,
          })}
          className="text-sm text-emerald-600 hover:underline dark:text-emerald-400"
          data-testid="admin-access-keys-export"
        >
          {t('accessKeys.admin.exportCsv')}
        </a>
      </div>

      {revoking ? (
        <div className="max-w-xl rounded-lg border border-zinc-200 p-4 dark:border-zinc-700">
          <RevokeKeyPanel
            accessKey={revoking}
            onCancel={() => setRevoking(null)}
            onConfirm={async (reason) => {
              await accessKeysAPI.adminRevokeKey(revoking.id, reason)
              setRevoking(null)
              setNotice(t('accessKeys.revoke.success'))
              await load()
            }}
          />
        </div>
      ) : (
        <>
          <div className="mb-4 grid gap-4 sm:grid-cols-3">
            <div>
              <span className="block text-sm font-medium text-zinc-900 dark:text-zinc-100">
                {t('accessKeys.admin.filterOrg')}
              </span>
              <Select
                value={orgFilter || ALL}
                onValueChange={(v) => setOrgFilter(fromSelect(v))}
              >
                <SelectTrigger
                  className="mt-1"
                  aria-label={t('accessKeys.admin.filterOrg')}
                  data-testid="admin-access-keys-org"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL}>
                    {t('accessKeys.admin.allOrgs')}
                  </SelectItem>
                  {organizations.map((o) => (
                    <SelectItem key={o.id} value={o.id}>
                      {o.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <span className="block text-sm font-medium text-zinc-900 dark:text-zinc-100">
                {t('accessKeys.admin.filterOwner')}
              </span>
              <Select
                value={ownerFilter || ALL}
                onValueChange={(v) =>
                  setOwnerFilter(fromSelect(v) as AccessKeyOwnerType | '')
                }
              >
                <SelectTrigger
                  className="mt-1"
                  aria-label={t('accessKeys.admin.filterOwner')}
                  data-testid="admin-access-keys-owner"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL}>
                    {t('accessKeys.admin.all')}
                  </SelectItem>
                  <SelectItem value="org">
                    {t('accessKeys.ownerOrg')}
                  </SelectItem>
                  <SelectItem value="user">
                    {t('accessKeys.ownerUser')}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <span className="block text-sm font-medium text-zinc-900 dark:text-zinc-100">
                {t('accessKeys.admin.filterStatus')}
              </span>
              <Select
                value={statusFilter || ALL}
                onValueChange={(v) =>
                  setStatusFilter(fromSelect(v) as AccessKeyStatus | '')
                }
              >
                <SelectTrigger
                  className="mt-1"
                  aria-label={t('accessKeys.admin.filterStatus')}
                  data-testid="admin-access-keys-status"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL}>
                    {t('accessKeys.admin.all')}
                  </SelectItem>
                  <SelectItem value="active">
                    {t('accessKeys.status.active')}
                  </SelectItem>
                  <SelectItem value="expired">
                    {t('accessKeys.status.expired')}
                  </SelectItem>
                  <SelectItem value="revoked">
                    {t('accessKeys.status.revoked')}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {notice && (
            <div
              className="mb-4 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-400"
              data-testid="admin-access-keys-notice"
            >
              {notice}
            </div>
          )}

          {error ? (
            <p className="text-sm text-red-600 dark:text-red-400" role="alert">
              {t('accessKeys.loadFailed')}
            </p>
          ) : keys.length === 0 && !loading ? (
            <p
              className="text-sm text-zinc-500"
              data-testid="admin-access-keys-empty"
            >
              {t('accessKeys.empty')}
            </p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-700">
              <table
                className="min-w-full divide-y divide-zinc-200 text-sm dark:divide-zinc-700"
                data-testid="admin-access-keys-table"
              >
                <thead className="bg-zinc-50 text-left text-xs font-medium text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
                  <tr>
                    <th className="px-4 py-3 text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                      {t('accessKeys.columns.name')}
                    </th>
                    <th className="px-4 py-3 text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                      {t('accessKeys.columns.owner')}
                    </th>
                    <th className="px-4 py-3 text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                      {t('accessKeys.columns.scopes')}
                    </th>
                    <th className="px-4 py-3 text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                      {t('accessKeys.columns.expires')}
                    </th>
                    <th className="px-4 py-3 text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                      {t('accessKeys.columns.lastUsed')}
                    </th>
                    <th className="px-4 py-3 text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                      {t('accessKeys.columns.status')}
                    </th>
                    <th className="px-4 py-3 text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                      <span className="sr-only">
                        {t('accessKeys.columns.actions')}
                      </span>
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                  {keys.map((key) => (
                    <tr key={key.id} data-testid={`admin-access-key-${key.id}`}>
                      <td className="px-4 py-3">
                        <div className="font-medium text-zinc-900 dark:text-white">
                          {key.name}
                        </div>
                        <div className="font-mono text-xs text-zinc-500">
                          {key.key_prefix}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-xs text-zinc-600 dark:text-zinc-400">
                        {key.owner_type === 'org'
                          ? `${t('accessKeys.ownerOrg')}: ${orgName(key.organization_id)}`
                          : `${t('accessKeys.ownerUser')}: ${key.user_id}`}
                      </td>
                      <td className="px-4 py-3">
                        <ScopeChips scopes={key.scopes} />
                      </td>
                      <td className="px-4 py-3 text-xs">
                        {key.expires_at
                          ? formatDate(key.expires_at, locale)
                          : t('accessKeys.noExpiry')}
                      </td>
                      <td className="px-4 py-3 text-xs">
                        {key.last_used_at
                          ? formatDate(key.last_used_at, locale)
                          : t('accessKeys.never')}
                      </td>
                      <td className="px-4 py-3">
                        <AccessKeyStatusBadge status={key.status} />
                      </td>
                      <td className="px-4 py-3 text-right">
                        {key.status === 'active' && (
                          <Button
                            type="button"
                            variant="outline"
                            onClick={() => {
                              setNotice(null)
                              setRevoking(key)
                            }}
                            data-testid={`admin-access-key-revoke-${key.id}`}
                          >
                            {t('accessKeys.actions.revoke')}
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {cursor && (
            <div className="mt-4 flex justify-center">
              <Button
                type="button"
                variant="outline"
                disabled={loading}
                onClick={() => load(cursor)}
                data-testid="admin-access-keys-more"
              >
                {t('accessKeys.admin.loadMore')}
              </Button>
            </div>
          )}
        </>
      )}
    </ResponsiveContainer>
  )
}
