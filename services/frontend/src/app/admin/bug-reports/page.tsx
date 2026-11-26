'use client'

import { Suspense } from 'react'

import { BugReportsAdmin } from '@/components/admin/bugReports/BugReportsAdmin'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { FeatureFlagGate } from '@/components/shared/FeatureFlagGate'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { BUG_REPORTS } from '@/lib/featureFlags/platformFlags'

/**
 * Host route for the list of problem reports (flag `bug_reports`).
 *
 * Superadmin guard and page shell follow the other src/app/admin/* pages;
 * with the flag off the route answers as not found, like the API.
 */
export default function BugReportsAdminPage() {
  const { user } = useAuth()
  const { t } = useI18n()

  if (!user?.is_superadmin) {
    return (
      <ResponsiveContainer size="xl" className="pt-8 pb-10">
        <div className="mb-4">
          <Breadcrumb
            items={[
              { label: t('navigation.dashboard'), href: '/dashboard' },
              {
                label: t('bugReport.admin.title'),
                href: '/admin/bug-reports',
              },
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

  return (
    <FeatureFlagGate flag={BUG_REPORTS}>
      <Suspense fallback={null}>
        <BugReportsAdmin />
      </Suspense>
    </FeatureFlagGate>
  )
}
