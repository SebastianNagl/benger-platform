'use client'

import { Button } from '@/components/shared/Button'
import { useI18n } from '@/contexts/I18nContext'
import { Organization } from '@/lib/api'
import {
  Combobox,
  ComboboxInput,
  ComboboxOption,
  ComboboxOptions,
  Popover,
  PopoverButton,
  PopoverPanel,
} from '@headlessui/react'
import {
  BuildingOfficeIcon,
  CheckIcon,
  ChevronDownIcon,
  MagnifyingGlassIcon,
} from '@heroicons/react/24/outline'
import clsx from 'clsx'
import { useMemo, useState } from 'react'

/** Alphabetical by name, ignoring case; German collation puts "Ä" with "A". */
export function sortOrganizationsByName<T extends { name?: string }>(
  organizations: T[],
): T[] {
  return [...organizations].sort((a, b) =>
    (a.name ?? '').localeCompare(b.name ?? '', 'de', { sensitivity: 'base' }),
  )
}

interface OrganizationSwitcherProps<T extends Organization> {
  organizations: T[]
  selectedOrganization: T | null
  onSelect: (organization: T) => void
}

export function OrganizationSwitcher<T extends Organization>({
  organizations,
  selectedOrganization,
  onSelect,
}: OrganizationSwitcherProps<T>) {
  const { t } = useI18n()
  const [query, setQuery] = useState('')

  const sortedOrganizations = useMemo(
    () => sortOrganizationsByName(organizations),
    [organizations],
  )

  const filteredOrganizations = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return sortedOrganizations
    return sortedOrganizations.filter(
      (org) =>
        org.name?.toLowerCase().includes(q) ||
        org.description?.toLowerCase().includes(q),
    )
  }, [sortedOrganizations, query])

  return (
    <Popover className="relative">
      {({ close }) => (
        <>
          <PopoverButton
            as={Button}
            variant="outline"
            data-testid="org-switcher-button"
          >
            <BuildingOfficeIcon className="h-4 w-4" />
            {selectedOrganization
              ? selectedOrganization.name
              : t('admin.organizations.selectOrganization')}
            <ChevronDownIcon className="h-4 w-4" />
          </PopoverButton>

          <PopoverPanel
            className="absolute left-0 z-50 mt-2 w-72 overflow-hidden rounded-lg bg-white shadow-lg ring-1 ring-black/5 focus:outline-none dark:bg-zinc-800 dark:ring-white/10"
            data-testid="org-switcher-panel"
          >
            <Combobox
              value={selectedOrganization}
              by="id"
              onChange={(org: T | null) => {
                if (!org) return
                onSelect(org)
                setQuery('')
                close()
              }}
            >
              <div className="relative border-b border-zinc-900/5 p-2 dark:border-white/10">
                <MagnifyingGlassIcon className="pointer-events-none absolute top-1/2 left-5 h-4 w-4 -translate-y-1/2 text-zinc-400" />
                <ComboboxInput
                  autoFocus
                  className="h-8 w-full rounded-full bg-white pr-3 pl-8 text-sm text-zinc-900 ring-1 ring-zinc-900/10 placeholder:text-zinc-500 focus:ring-2 focus:ring-emerald-500 focus:outline-none dark:bg-white/5 dark:text-zinc-100 dark:ring-white/10 dark:placeholder:text-zinc-400 dark:focus:ring-emerald-400"
                  placeholder={t(
                    'admin.organizations.filters.switcherSearchPlaceholder',
                  )}
                  displayValue={() => query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </div>
              <ComboboxOptions
                static
                className="max-h-72 overflow-auto py-1 text-sm focus:outline-none"
              >
                {filteredOrganizations.length === 0 ? (
                  <div className="px-4 py-3 text-zinc-500 dark:text-zinc-400">
                    {t('admin.organizations.noOrganizations')}
                  </div>
                ) : (
                  filteredOrganizations.map((org) => (
                    <ComboboxOption
                      key={`org-switcher-${org.id}`}
                      value={org}
                      className={({ focus }) =>
                        clsx(
                          'relative cursor-default py-2 pr-4 pl-10 select-none',
                          focus
                            ? 'bg-emerald-100 text-emerald-900 dark:bg-emerald-900 dark:text-emerald-100'
                            : 'text-zinc-900 dark:text-zinc-100',
                        )
                      }
                    >
                      {({ selected, focus }) => (
                        <>
                          <span
                            className={clsx(
                              'block truncate',
                              selected ? 'font-medium' : 'font-normal',
                            )}
                          >
                            {org.name}
                          </span>
                          {org.description && (
                            <span
                              className={clsx(
                                'block truncate text-xs',
                                focus
                                  ? 'text-emerald-800 dark:text-emerald-200'
                                  : 'text-zinc-500 dark:text-zinc-400',
                              )}
                            >
                              {org.description}
                            </span>
                          )}
                          {selected && (
                            <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-emerald-600 dark:text-emerald-400">
                              <CheckIcon
                                className="h-5 w-5"
                                aria-hidden="true"
                              />
                            </span>
                          )}
                        </>
                      )}
                    </ComboboxOption>
                  ))
                )}
              </ComboboxOptions>
            </Combobox>
          </PopoverPanel>
        </>
      )}
    </Popover>
  )
}
