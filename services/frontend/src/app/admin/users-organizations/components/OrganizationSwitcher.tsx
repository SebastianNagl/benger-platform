'use client'

import { Button } from '@/components/shared/Button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from '@/components/shared/Select'
import { useI18n } from '@/contexts/I18nContext'
import { Organization } from '@/lib/api'
import {
  BuildingOfficeIcon,
  ChevronDownIcon,
} from '@heroicons/react/24/outline'

interface OrganizationSwitcherProps<T extends Organization> {
  organizations: T[]
  selectedOrganization: T | null
  onSelect: (organization: T) => void
}

/**
 * The organizations page switcher: the shared searchable Select, so the
 * organizations sort alphabetically and filter by name or description like
 * every other data dropdown.
 */
export function OrganizationSwitcher<T extends Organization>({
  organizations,
  selectedOrganization,
  onSelect,
}: OrganizationSwitcherProps<T>) {
  const { t } = useI18n()

  return (
    <Select
      searchable
      value={selectedOrganization?.id ?? ''}
      onValueChange={(id) => {
        const organization = organizations.find((org) => org.id === id)
        if (organization) onSelect(organization)
      }}
      searchPlaceholder={t(
        'admin.organizations.filters.switcherSearchPlaceholder',
      )}
    >
      <SelectTrigger
        as={Button}
        variant="outline"
        unstyled
        data-testid="org-switcher-button"
      >
        <BuildingOfficeIcon className="h-4 w-4" />
        {selectedOrganization
          ? selectedOrganization.name
          : t('admin.organizations.selectOrganization')}
        <ChevronDownIcon className="h-4 w-4 opacity-70" />
      </SelectTrigger>
      <SelectContent>
        {organizations.map((org) => (
          <SelectItem
            key={`org-switcher-${org.id}`}
            value={org.id}
            textValue={[org.name, org.description].filter(Boolean).join(' ')}
          >
            <span className="block truncate" title={org.name}>
              {org.name}
            </span>
            {org.description && (
              <span className="block truncate text-xs font-normal text-zinc-500 dark:text-zinc-400">
                {org.description}
              </span>
            )}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
