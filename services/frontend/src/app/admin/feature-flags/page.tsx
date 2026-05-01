'use client'

import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Button } from '@/components/shared/Button'
import { FilterToolbar } from '@/components/shared/FilterToolbar'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/shared/Select'
import { useToast } from '@/components/shared/Toast'
import { ToggleSwitch } from '@/components/shared/ToggleSwitch'
import { useAuth } from '@/contexts/AuthContext'
import { useFeatureFlags } from '@/contexts/FeatureFlagContext'
import { useI18n } from '@/contexts/I18nContext'
import { api } from '@/lib/api'
import { FeatureFlag } from '@/lib/api/types'
import { ChevronDownIcon, ChevronUpIcon } from '@heroicons/react/24/outline'
import { useCallback, useEffect, useState } from 'react'

export default function FeatureFlagsAdminPage() {
  const { user } = useAuth()
  const { addToast } = useToast()
  const { refreshFlags } = useFeatureFlags()
  const { t } = useI18n()
  const [flags, setFlags] = useState<FeatureFlag[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [sortField, setSortField] = useState<'name' | 'created_at'>('name')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc')
  const [pendingChanges, setPendingChanges] = useState<Map<string, boolean>>(
    new Map()
  )
  const [isSaving, setIsSaving] = useState(false)

  const loadFlags = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const flagsData = await api.getAllFeatureFlagsForAdmin()
      const flagsArray = Array.isArray(flagsData) ? flagsData : []
      setFlags(flagsArray)
    } catch (err) {
      console.error('Failed to load feature flags:', err)
      const errorMessage =
        err instanceof Error
          ? err.message
          : t('admin.featureFlagsPage.applyFailed')
      setError(errorMessage)
      setFlags([])
      addToast(t('admin.featureFlagsPage.applyFailed'), 'error')
    } finally {
      setLoading(false)
    }
  }, [addToast, t])

  useEffect(() => {
    loadFlags()
  }, [loadFlags])

  // Check if user is superadmin
  if (!user?.is_superadmin) {
    return (
      <ResponsiveContainer size="xl" className="pb-10 pt-8">
        {/* Breadcrumb */}
        <div className="mb-4">
          <Breadcrumb
            items={[
              { label: t('navigation.dashboard'), href: '/dashboard' },
              { label: t('admin.featureFlagsPage.title'), href: '/admin/feature-flags' },
            ]}
          />
        </div>

        <div className="text-center">
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

  const handleToggleFlag = (flag: FeatureFlag) => {
    const newEnabled = !flag.is_enabled

    // Update local state
    setFlags((prevFlags) =>
      prevFlags.map((f) =>
        f.id === flag.id ? { ...f, is_enabled: newEnabled } : f
      )
    )

    // Track the pending change
    setPendingChanges((prev) => {
      const newChanges = new Map(prev)
      newChanges.set(flag.id, newEnabled)
      return newChanges
    })
  }

  const handleApplyChanges = async () => {
    if (pendingChanges.size === 0) {
      addToast(t('toasts.admin.noChanges'), 'info')
      return
    }

    setIsSaving(true)
    try {
      // Apply all pending changes
      const promises = Array.from(pendingChanges.entries()).map(
        ([flagId, enabled]) =>
          api.updateFeatureFlag(flagId, { is_enabled: enabled })
      )

      await Promise.all(promises)

      addToast(t('admin.featureFlagsPage.applied'), 'success')

      // Clear pending changes; refresh the live flag list. Do NOT hard-reload
      // — the previous setTimeout(reload, 500) destroyed this very toast
      // before the user could read it.
      setPendingChanges(new Map())
      await loadFlags()
    } catch (err) {
      addToast(
        err instanceof Error
          ? err.message
          : t('admin.featureFlagsPage.applyFailed'),
        'error'
      )
      // Reload flags to revert to server state
      await loadFlags()
      setPendingChanges(new Map())
    } finally {
      setIsSaving(false)
    }
  }

  const handleDiscardChanges = () => {
    if (pendingChanges.size === 0) return

    // Reload flags from server
    loadFlags()
    setPendingChanges(new Map())
    addToast(t('toasts.admin.changesDiscarded'), 'info')
  }

  // Filter and sort flags
  const filteredFlags = flags.filter(
    (flag) =>
      flag.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (flag.description?.toLowerCase().includes(searchQuery.toLowerCase()) ??
        false)
  )

  const sortedFlags = [...filteredFlags].sort((a, b) => {
    const aValue = sortField === 'name' ? a.name : a.created_at
    const bValue = sortField === 'name' ? b.name : b.created_at

    if (sortOrder === 'asc') {
      return aValue.localeCompare(bValue)
    } else {
      return bValue.localeCompare(aValue)
    }
  })

  const handleSort = (field: 'name' | 'created_at') => {
    if (sortField === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortOrder('asc')
    }
  }

  if (loading) {
    return (
      <ResponsiveContainer size="xl" className="pb-10 pt-8">
        {/* Breadcrumb */}
        <div className="mb-4">
          <Breadcrumb
            items={[
              { label: t('navigation.dashboard'), href: '/dashboard' },
              { label: t('admin.featureFlagsPage.title'), href: '/admin/feature-flags' },
            ]}
          />
        </div>

        <div className="py-12 text-center">
          <div className="mx-auto h-12 w-12 animate-spin rounded-full border-b-2 border-emerald-600"></div>
          <p className="mt-4 text-zinc-600 dark:text-zinc-400">
            Loading feature flags...
          </p>
        </div>
      </ResponsiveContainer>
    )
  }

  return (
    <ResponsiveContainer
      size="full"
      className="px-4 pb-10 pt-8 sm:px-6 lg:px-8"
    >
      {/* Breadcrumb */}
      <div className="mb-4">
        <Breadcrumb
          items={[
            { label: 'Dashboard', href: '/dashboard' },
            { label: 'Feature Flags', href: '/admin/feature-flags' },
          ]}
        />
      </div>

      <div className="py-6">
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-zinc-900 dark:text-zinc-100">
              {t('admin.featureFlagsPage.title')}
            </h1>
            <p className="mt-2 text-zinc-600 dark:text-zinc-400">
              {t('admin.featureFlagsPage.description')}
            </p>
          </div>
          {pendingChanges.size > 0 && (
            <div className="flex items-center gap-4">
              <Button
                onClick={handleDiscardChanges}
                className="bg-zinc-500 text-white hover:bg-zinc-600"
                disabled={isSaving}
              >
                {t('admin.featureFlagsPage.discardChanges')}
              </Button>
              <Button
                onClick={handleApplyChanges}
                className="bg-blue-600 text-white hover:bg-blue-700"
                disabled={isSaving}
              >
                {isSaving
                  ? t('admin.featureFlagsPage.applying')
                  : `${t('admin.featureFlagsPage.applyChanges')} (${pendingChanges.size})`}
              </Button>
            </div>
          )}
        </div>

        {error && (
          <div className="mb-6 rounded-md border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-950">
            <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
          </div>
        )}

        {/* Search and filters */}
        <div className="mb-6">
          <FilterToolbar
            searchValue={searchQuery}
            onSearchChange={setSearchQuery}
            searchPlaceholder={t('admin.featureFlagsPage.searchPlaceholder')}
            searchLabel={t('common.filters.search')}
            filtersLabel={t('common.filters.filters')}
            hasActiveFilters={
              sortField !== 'name' ||
              sortOrder !== 'asc' ||
              searchQuery.trim() !== ''
            }
            onClearFilters={() => {
              setSortField('name')
              setSortOrder('asc')
              setSearchQuery('')
            }}
            clearLabel={t('common.filters.clearAll')}
          >
            <FilterToolbar.Field label={t('common.filters.sortBy')}>
              <Select
                value={sortField}
                onValueChange={(v) => setSortField(v as 'name' | 'created_at')}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="name">{t('admin.featureFlagsPage.sortByName')}</SelectItem>
                  <SelectItem value="created_at">{t('admin.featureFlagsPage.sortByDate')}</SelectItem>
                </SelectContent>
              </Select>
            </FilterToolbar.Field>
            <FilterToolbar.Field label={t('common.filters.order')}>
              <Select
                value={sortOrder}
                onValueChange={(v) => setSortOrder(v as 'asc' | 'desc')}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="asc">{t('common.filters.asc')}</SelectItem>
                  <SelectItem value="desc">{t('common.filters.desc')}</SelectItem>
                </SelectContent>
              </Select>
            </FilterToolbar.Field>
          </FilterToolbar>
        </div>

        {/* Feature Flags Table */}
        <div className="overflow-hidden bg-white shadow dark:bg-zinc-900 sm:rounded-lg">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-zinc-200 dark:divide-zinc-700">
              <thead className="bg-zinc-50 dark:bg-zinc-800">
                <tr>
                  <th
                    scope="col"
                    className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400"
                  >
                    <button
                      onClick={() => handleSort('name')}
                      className="group inline-flex items-center space-x-1 hover:text-zinc-900 dark:hover:text-zinc-100"
                    >
                      <span>{t('admin.featureFlagsPage.name')}</span>
                      {sortField === 'name' &&
                        (sortOrder === 'asc' ? (
                          <ChevronUpIcon className="h-4 w-4" />
                        ) : (
                          <ChevronDownIcon className="h-4 w-4" />
                        ))}
                    </button>
                  </th>
                  <th
                    scope="col"
                    className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400"
                  >
                    Description
                  </th>
                  <th
                    scope="col"
                    className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400"
                  >
                    Status
                  </th>
                  <th
                    scope="col"
                    className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400"
                  >
                    <button
                      onClick={() => handleSort('created_at')}
                      className="group inline-flex items-center space-x-1 hover:text-zinc-900 dark:hover:text-zinc-100"
                    >
                      <span>{t('admin.featureFlagsPage.created')}</span>
                      {sortField === 'created_at' &&
                        (sortOrder === 'asc' ? (
                          <ChevronUpIcon className="h-4 w-4" />
                        ) : (
                          <ChevronDownIcon className="h-4 w-4" />
                        ))}
                    </button>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-200 bg-white dark:divide-zinc-700 dark:bg-zinc-900">
                {sortedFlags.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-6 py-12 text-center">
                      <div className="text-zinc-500 dark:text-zinc-400">
                        {searchQuery ? (
                          <>
                            <p>
                              No feature flags found matching "{searchQuery}"
                            </p>
                            <Button
                              onClick={() => setSearchQuery('')}
                              variant="text"
                              className="mt-2 text-emerald-600 hover:text-emerald-700"
                            >
                              Clear search
                            </Button>
                          </>
                        ) : (
                          <p>{t('admin.featureFlagsPage.noFlags')}</p>
                        )}
                      </div>
                    </td>
                  </tr>
                ) : (
                  sortedFlags.map((flag) => {
                    const hasPendingChange = pendingChanges.has(flag.id)
                    return (
                      <tr
                        key={flag.id}
                        className={`transition-colors hover:bg-zinc-50 dark:hover:bg-zinc-800/50 ${
                          hasPendingChange
                            ? 'bg-amber-50 dark:bg-amber-950/20'
                            : ''
                        }`}
                      >
                        <td className="whitespace-nowrap px-6 py-4">
                          <div className="flex items-center gap-2">
                            <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                              {flag.name}
                            </div>
                            {hasPendingChange && (
                              <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800 dark:bg-amber-900 dark:text-amber-200">
                                Pending
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-6 py-4">
                          <div className="max-w-xs truncate text-sm text-zinc-600 dark:text-zinc-400">
                            {flag.description || '-'}
                          </div>
                        </td>
                        <td className="whitespace-nowrap px-6 py-4">
                          <div className="flex items-center space-x-2">
                            <ToggleSwitch
                              enabled={flag.is_enabled}
                              onChange={() => handleToggleFlag(flag)}
                            />
                            <span
                              className={`text-sm ${flag.is_enabled ? 'text-emerald-600 dark:text-emerald-400' : 'text-zinc-500 dark:text-zinc-400'}`}
                            >
                              {flag.is_enabled
                                ? t('admin.featureFlagsPage.enabled')
                                : t('admin.featureFlagsPage.disabled')}
                            </span>
                          </div>
                        </td>
                        <td className="whitespace-nowrap px-6 py-4 text-sm text-zinc-500 dark:text-zinc-400">
                          {flag.created_at
                            ? new Date(flag.created_at).toLocaleDateString()
                            : '-'}
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </ResponsiveContainer>
  )
}
