'use client'

import { Button } from '@/components/shared/Button'
import { Input } from '@/components/shared/Input'
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
      {({ open, close }) => (
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
            <ChevronDownIcon
              className={clsx(
                'h-4 w-4 opacity-70 transition-transform',
                open && 'rotate-180',
              )}
            />
          </PopoverButton>

          <PopoverPanel
            className="absolute left-0 z-50 mt-2 w-72 overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-lg focus:outline-none dark:border-zinc-700 dark:bg-zinc-800"
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
              <div className="relative border-b border-zinc-200 p-2 dark:border-zinc-700">
                <MagnifyingGlassIcon className="pointer-events-none absolute top-1/2 left-5 h-4 w-4 -translate-y-1/2 text-zinc-400" />
                <ComboboxInput
                  as={Input}
                  autoFocus
                  className="pl-8 text-sm"
                  placeholder={t(
                    'admin.organizations.filters.switcherSearchPlaceholder',
                  )}
                  displayValue={() => query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </div>
              <ComboboxOptions
                static
                className="max-h-72 overflow-y-auto overscroll-contain py-1 focus:outline-none"
              >
                {filteredOrganizations.length === 0 ? (
                  <div className="px-4 py-2 text-sm text-zinc-500 dark:text-zinc-400">
                    {t('admin.organizations.noOrganizations')}
                  </div>
                ) : (
                  filteredOrganizations.map((org) => (
                    <ComboboxOption
                      key={`org-switcher-${org.id}`}
                      value={org}
                      title={org.name}
                      className={({ focus }) =>
                        clsx(
                          'flex w-full min-w-0 cursor-default items-center px-4 py-2 text-sm text-zinc-700 select-none dark:text-zinc-300',
                          focus && 'bg-zinc-100 dark:bg-zinc-700',
                        )
                      }
                    >
                      {({ selected }) => (
                        <>
                          <BuildingOfficeIcon className="mr-3 h-4 w-4 shrink-0" />
                          <span className="min-w-0 flex-1">
                            <span className="block truncate">{org.name}</span>
                            {org.description && (
                              <span className="block truncate text-xs text-zinc-500 dark:text-zinc-400">
                                {org.description}
                              </span>
                            )}
                          </span>
                          {selected && (
                            <CheckIcon
                              className="ml-2 h-4 w-4 shrink-0 text-amber-600"
                              aria-hidden="true"
                            />
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
