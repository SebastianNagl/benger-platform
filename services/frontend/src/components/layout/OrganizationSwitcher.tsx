'use client'

import { useAuth } from '@/contexts/AuthContext'
import { Organization } from '@/lib/api'
import { parseSubdomain } from '@/lib/utils/subdomain'
import { Listbox } from '@headlessui/react'
import {
  BuildingOfficeIcon,
  CheckIcon,
  ChevronDownIcon,
  UserIcon,
} from '@heroicons/react/24/outline'

interface OrganizationSwitcherProps {
  className?: string
}

type SwitcherOption = Organization | { id: 'private'; name: 'Private'; slug: null }

export function OrganizationSwitcher({
  className = '',
}: OrganizationSwitcherProps) {
  const { organizations, currentOrganization, user, setCurrentOrganization } = useAuth()

  if (!user) {
    return null
  }

  const { isPrivateMode } = parseSubdomain()

  const privateOption: SwitcherOption = { id: 'private', name: 'Private', slug: null }
  const options: SwitcherOption[] = [privateOption, ...organizations]
  const selectedOption: SwitcherOption = isPrivateMode ? privateOption : (currentOrganization || privateOption)

  const handleChange = (option: SwitcherOption) => {
    if (option.id === 'private') {
      setCurrentOrganization(null)
    } else {
      setCurrentOrganization(option as Organization)
    }
  }

  return (
    <Listbox value={selectedOption} onChange={handleChange}>
      <div className={`relative ${className}`}>
        <Listbox.Button className="relative w-full cursor-default rounded-lg border border-gray-300 bg-white py-2 pl-3 pr-10 text-left shadow-md focus:outline-none focus-visible:border-indigo-500 focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-opacity-75 focus-visible:ring-offset-2 focus-visible:ring-offset-orange-300 sm:text-sm">
          <span className="flex items-center">
            {selectedOption.id === 'private' ? (
              <UserIcon className="mr-2 h-5 w-5 text-gray-400" />
            ) : (
              <BuildingOfficeIcon className="mr-2 h-5 w-5 text-gray-400" />
            )}
            <span className="block truncate">
              {selectedOption.name}
            </span>
          </span>
          <span className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2">
            <ChevronDownIcon
              className="h-4 w-4 text-gray-400"
              aria-hidden="true"
            />
          </span>
        </Listbox.Button>

        <Listbox.Options className="absolute z-50 mt-1 max-h-60 w-full overflow-auto rounded-md bg-white py-1 text-base shadow-lg ring-1 ring-black ring-opacity-5 transition duration-100 ease-in focus:outline-none data-[closed]:opacity-0 sm:text-sm">
          {options.map((option) => (
            <Listbox.Option
              key={option.id}
              className={({ active }) =>
                `relative cursor-default select-none py-2 pl-10 pr-4 ${
                  active ? 'bg-amber-100 text-amber-900' : 'text-gray-900'
                }`
              }
              value={option}
            >
              {({ selected }) => (
                <>
                  <div className="flex items-center">
                    {option.id === 'private' ? (
                      <UserIcon className="mr-2 h-4 w-4 text-gray-400" />
                    ) : (
                      <BuildingOfficeIcon className="mr-2 h-4 w-4 text-gray-400" />
                    )}
                    <span
                      className={`block truncate ${
                        selected ? 'font-medium' : 'font-normal'
                      }`}
                    >
                      {option.name}
                    </span>
                    {option.id !== 'private' && (option as Organization).member_count && (
                      <span className="ml-2 text-xs text-gray-500">
                        {(option as Organization).member_count} members
                      </span>
                    )}
                  </div>
                  {selected ? (
                    <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-amber-600">
                      <CheckIcon className="h-4 w-4" aria-hidden="true" />
                    </span>
                  ) : null}
                </>
              )}
            </Listbox.Option>
          ))}
        </Listbox.Options>
      </div>
    </Listbox>
  )
}
