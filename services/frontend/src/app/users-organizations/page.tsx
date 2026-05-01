'use client'

import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { UserOrganizationPermissions } from '@/lib/permissions/userOrganizationPermissions'
import { Tab, TabGroup, TabList, TabPanel, TabPanels } from '@headlessui/react'
import { BuildingOfficeIcon, UserGroupIcon } from '@heroicons/react/24/outline'
import { useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'
import { GlobalUsersTab } from '../admin/users-organizations/components/GlobalUsersTab'
import { OrganizationsTab } from '../admin/users-organizations/components/OrganizationsTab'

export default function UsersOrganizationsPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { user, organizations } = useAuth()
  const { t } = useI18n()

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
    [user, organizations]
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
      setSelectedTab(1)
    }

    setLoading(false)
  }, [userWithOrganizations, router, selectedTab, user])

  if (loading) {
    return (
      <ResponsiveContainer>
        <div className="flex h-64 items-center justify-center">
          <div className="text-gray-500">{t('auth.guard.loading')}</div>
        </div>
      </ResponsiveContainer>
    )
  }

  const canAccessGlobalUsers = UserOrganizationPermissions.canManageGlobalUsers(
    userWithOrganizations
  )

  const breadcrumbItems = [
    { label: t('navigation.dashboard'), href: '/dashboard' },
    {
      label: t('admin.usersOrganizations'),
      href: '/users-organizations',
    },
  ]

  return (
    <ResponsiveContainer size="full" className="px-4 pb-10 pt-8 sm:px-6 lg:px-8">
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
            <div className="border-b border-zinc-200 dark:border-zinc-700">
              <TabList className="-mb-px flex space-x-8">
                {canAccessGlobalUsers && (
                  <Tab
                    className={({ selected }) =>
                      `flex items-center gap-2 border-b-2 py-3 text-sm font-medium transition ${
                        selected
                          ? 'border-emerald-500 text-emerald-600 dark:text-emerald-400'
                          : 'border-transparent text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-300'
                      }`
                    }
                  >
                    <UserGroupIcon className="h-5 w-5" />
                    {t('admin.globalUsers')}
                  </Tab>
                )}
                <Tab
                  className={({ selected }) =>
                    `flex items-center gap-2 border-b-2 py-3 text-sm font-medium transition ${
                      selected
                        ? 'border-emerald-500 text-emerald-600 dark:text-emerald-400'
                        : 'border-transparent text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-300'
                    }`
                  }
                >
                  <BuildingOfficeIcon className="h-5 w-5" />
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
