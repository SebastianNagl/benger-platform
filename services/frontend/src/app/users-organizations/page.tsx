'use client'

import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { usePublicApiEnabled } from '@/hooks/usePublicApiEnabled'
import { UserOrganizationPermissions } from '@/lib/permissions/userOrganizationPermissions'
import { Tab, TabGroup, TabList, TabPanel, TabPanels } from '@headlessui/react'
import {
  BuildingOfficeIcon,
  CommandLineIcon,
  UserGroupIcon,
} from '@heroicons/react/24/outline'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'
import { GlobalUsersTab } from '../admin/users-organizations/components/GlobalUsersTab'
import { OrganizationsTab } from '../admin/users-organizations/components/OrganizationsTab'

export default function UsersOrganizationsPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { user, organizations } = useAuth()
  const { t } = useI18n()
  const publicApiEnabled = usePublicApiEnabled()

  const tabFromUrl = searchParams?.get('tab')
  const initialTab =
    tabFromUrl === 'organizations' ? 1 : tabFromUrl === 'users' ? 0 : 0
  const [selectedTab, setSelectedTab] = useState(initialTab)
  const [loading, setLoading] = useState(true)

  const userWithOrganizations = useMemo(
    () =>
      user
        ? {
            ...user,
            organizations: organizations.map((org) => ({
              id: org.id,
              role: org.role!,
            })),
          }
        : null,
    [user, organizations],
  )

  useEffect(() => {
    if (!user) {
      router.push('/login')
      return
    }

    // If not superadmin and on global users tab, switch to organizations
    if (
      selectedTab === 0 &&
      !UserOrganizationPermissions.canManageGlobalUsers(userWithOrganizations)
    ) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSelectedTab(1)
    }

    setLoading(false)
  }, [userWithOrganizations, router, selectedTab, user])

  if (loading) {
    return (
      <ResponsiveContainer>
        <div className="flex h-64 items-center justify-center">
          <div className="text-zinc-500">{t('auth.guard.loading')}</div>
        </div>
      </ResponsiveContainer>
    )
  }

  const canAccessGlobalUsers = UserOrganizationPermissions.canManageGlobalUsers(
    userWithOrganizations,
  )

  const breadcrumbItems = [
    { label: t('navigation.dashboard'), href: '/dashboard' },
    {
      label: t('admin.usersOrganizations'),
      href: '/users-organizations',
    },
  ]

  return (
    <ResponsiveContainer
      size="full"
      className="px-4 pt-8 pb-10 sm:px-6 lg:px-8"
    >
      <div className="mb-4">
        <Breadcrumb items={breadcrumbItems} />
      </div>

      <div className="mx-auto max-w-7xl">
        <div className="mt-8">
          <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
            {t('admin.usersOrganizations')}
          </h1>
          <p className="mt-2 text-lg text-zinc-600 dark:text-zinc-400">
            {t('admin.usersOrganizationsDescription')}
          </p>
          {user?.is_superadmin && publicApiEnabled === true && (
            <Link
              href="/admin/access-keys"
              className="mt-2 inline-flex items-center gap-1 text-sm text-emerald-600 hover:underline dark:text-emerald-400"
              data-testid="admin-access-keys-link"
            >
              <CommandLineIcon className="h-4 w-4" />
              {t('accessKeys.admin.entry')}
            </Link>
          )}
        </div>

        <div className="mt-6">
          <TabGroup
            selectedIndex={selectedTab}
            onChange={(index) => {
              setSelectedTab(index)
              const tabName = canAccessGlobalUsers
                ? index === 0
                  ? 'users'
                  : 'organizations'
                : 'organizations'
              // Preserve existing URL params (like org) when switching tabs
              const params = new URLSearchParams(searchParams?.toString() || '')
              params.set('tab', tabName)
              router.push(`/users-organizations?${params.toString()}`)
            }}
          >
            <div>
              <TabList className="inline-flex max-w-full items-center gap-0.5 overflow-x-auto rounded-full bg-zinc-100 p-0.5 dark:bg-zinc-800">
                {canAccessGlobalUsers && (
                  <Tab
                    className={({ selected }) =>
                      `flex items-center gap-2 rounded-full px-3 py-1 text-sm font-medium whitespace-nowrap transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 ${
                        selected
                          ? 'bg-white text-zinc-900 shadow-sm dark:bg-zinc-700 dark:text-white'
                          : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white'
                      }`
                    }
                  >
                    <UserGroupIcon className="h-4 w-4" />
                    {t('admin.globalUsers')}
                  </Tab>
                )}
                <Tab
                  className={({ selected }) =>
                    `flex items-center gap-2 rounded-full px-3 py-1 text-sm font-medium whitespace-nowrap transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 ${
                      selected
                        ? 'bg-white text-zinc-900 shadow-sm dark:bg-zinc-700 dark:text-white'
                        : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white'
                    }`
                  }
                >
                  <BuildingOfficeIcon className="h-4 w-4" />
                  {t('admin.organizations.tabLabel')}
                </Tab>
              </TabList>
            </div>
            <TabPanels className="mt-6">
              {canAccessGlobalUsers && (
                <TabPanel>
                  <GlobalUsersTab />
                </TabPanel>
              )}
              <TabPanel>
                <OrganizationsTab />
              </TabPanel>
            </TabPanels>
          </TabGroup>
        </div>
      </div>
    </ResponsiveContainer>
  )
}
