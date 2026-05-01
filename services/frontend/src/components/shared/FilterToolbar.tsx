/**
 * FilterToolbar - shared action-bar primitive for list pages.
 *
 * Visual reference: services/frontend/src/components/data/GlobalDataTab.tsx (pre-refactor lines 298-587).
 *
 * Call sites (keep this list in sync when adding/removing usages):
 *   - components/data/GlobalDataTab.tsx
 *   - app/notifications/page.tsx
 *   - app/admin/users-organizations/components/GlobalUsersTab.tsx
 *   - app/admin/users-organizations/components/OrganizationsTab.tsx
 *   - components/leaderboards/LLMLeaderboardTable.tsx
 *   - components/projects/ProjectListTable.tsx
 *   - app/models/page.tsx
 *   - app/evaluations/page.tsx
 *   - app/projects/[id]/my-tasks/page.tsx
 *   - app/projects/[id]/members/page.tsx
 *   - app/admin/feature-flags/page.tsx
 *   - components/projects/AnnotationTab.tsx
 */

'use client'

import { Button } from '@/components/shared/Button'
import { FunnelIcon, MagnifyingGlassIcon, XMarkIcon } from '@heroicons/react/24/outline'
import clsx from 'clsx'
import {
  Children,
  ReactNode,
  useState,
  useEffect,
} from 'react'

interface FilterToolbarProps {
  searchValue?: string
  onSearchChange?: (value: string) => void
  searchPlaceholder?: string
  searchLabel?: string
  filtersLabel?: string
  clearLabel?: string
  searchHidden?: boolean
  hasActiveFilters?: boolean
  onClearFilters?: () => void
  defaultShowSearch?: boolean
  defaultShowFilters?: boolean
  leftExtras?: ReactNode
  rightExtras?: ReactNode
  children?: ReactNode
}

interface FilterFieldProps {
  label?: string
  className?: string
  children: ReactNode
}

function FilterField({ label, className, children }: FilterFieldProps) {
  return (
    <div className={className}>
      {label && (
        <label className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
          {label}
        </label>
      )}
      {children}
    </div>
  )
}

export function FilterToolbar({
  searchValue,
  onSearchChange,
  searchPlaceholder,
  searchLabel = 'Search',
  filtersLabel = 'Filters',
  clearLabel = 'Clear filters',
  searchHidden = false,
  hasActiveFilters = false,
  onClearFilters,
  defaultShowSearch = false,
  defaultShowFilters = false,
  leftExtras,
  rightExtras,
  children,
}: FilterToolbarProps) {
  const [showSearch, setShowSearch] = useState(defaultShowSearch)
  const [showFilters, setShowFilters] = useState(defaultShowFilters)

  // If the consumer flips defaults dynamically (e.g. URL-driven), keep state in sync.
  useEffect(() => {
    if (defaultShowSearch) setShowSearch(true)
  }, [defaultShowSearch])

  const hasFilterFields = Children.toArray(children).some(
    (c) => c !== null && c !== undefined && c !== ''
  )
  const filterDotVisible = hasActiveFilters || (showFilters && hasFilterFields)
  const searchDotVisible = Boolean(searchValue)

  const searchVisible = !searchHidden && onSearchChange && showSearch
  const filterPanelVisible = hasFilterFields && showFilters

  return (
    <div className="mb-6">
      <div className="space-y-3 rounded-lg border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
        <div className="flex flex-col space-y-3 lg:flex-row lg:items-center lg:justify-between lg:space-y-0">
          <div className="flex flex-wrap items-center gap-2 sm:gap-3">
            {!searchHidden && onSearchChange && (
              <Button
                variant="outline"
                onClick={() => setShowSearch(!showSearch)}
                className={clsx(
                  'h-8 py-0',
                  showSearch && 'bg-emerald-50 dark:bg-emerald-900/20'
                )}
                title={searchLabel}
              >
                <MagnifyingGlassIcon className="h-4 w-4" />
                <span className="ml-2 hidden sm:inline">{searchLabel}</span>
                {searchDotVisible && (
                  <span className="ml-2 h-2 w-2 rounded-full bg-emerald-500" />
                )}
              </Button>
            )}

            {leftExtras}

            {hasFilterFields && (
              <Button
                variant="outline"
                onClick={() => setShowFilters(!showFilters)}
                className={clsx(
                  'h-8 py-0',
                  showFilters && 'bg-emerald-50 dark:bg-emerald-900/20'
                )}
                title={filtersLabel}
              >
                <FunnelIcon className="h-4 w-4" />
                <span className="ml-2 hidden sm:inline">{filtersLabel}</span>
                {filterDotVisible && (
                  <span className="ml-2 h-2 w-2 rounded-full bg-emerald-500" />
                )}
              </Button>
            )}

            {onClearFilters && (
              <Button
                variant="outline"
                onClick={onClearFilters}
                disabled={!hasActiveFilters}
                title={clearLabel}
                aria-label={clearLabel}
                className={clsx(
                  'h-8 py-0',
                  hasActiveFilters &&
                    'bg-emerald-50 text-emerald-700 ring-emerald-300 hover:bg-emerald-100 dark:bg-emerald-900/20 dark:text-emerald-300 dark:ring-emerald-700'
                )}
              >
                <XMarkIcon className="h-4 w-4" />
              </Button>
            )}
          </div>

          {rightExtras && (
            <div className="flex items-center gap-2">{rightExtras}</div>
          )}
        </div>

        {searchVisible && (
          <div className="relative flex h-8 items-center rounded-full bg-white pl-2 pr-3 ring-1 ring-zinc-900/10 transition hover:ring-zinc-900/20 dark:bg-white/5 dark:ring-inset dark:ring-white/10 dark:hover:ring-white/20">
            <MagnifyingGlassIcon className="pointer-events-none h-5 w-5 stroke-current text-zinc-500 dark:text-zinc-400" />
            <input
              type="text"
              placeholder={searchPlaceholder}
              value={searchValue ?? ''}
              onChange={(e) => onSearchChange(e.target.value)}
              autoFocus
              className="flex-auto appearance-none bg-transparent pl-2 text-sm text-zinc-900 outline-none placeholder:text-zinc-500 dark:text-white dark:placeholder:text-zinc-400"
            />
          </div>
        )}

        {filterPanelVisible && (
          <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-700 dark:bg-zinc-800">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {children}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

FilterToolbar.Field = FilterField
