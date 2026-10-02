'use client'

import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { useSlot } from '@/lib/extensions/slots'

/**
 * Host route for the feature flags admin panel.
 *
 * Superadmin guard and page shell follow the other src/app/admin/* pages;
 * the flag registry, the state controls and the allowlist editor ship in the
 * proprietary extended package via the 'FeatureFlagsAdmin' slot. The
 * community edition has no feature flags.
 */
export default function FeatureFlagsAdminPage() {
  const { user } = useAuth()
  const { t } = useI18n()
  const FeatureFlagsAdmin = useSlot('FeatureFlagsAdmin')

  const breadcrumb = (
    <div className="mb-4">
      <Breadcrumb
        items={[
          { label: t('navigation.dashboard'), href: '/dashboard' },
          { label: t('admin.featureFlags'), href: '/admin/feature-flags' },
        ]}
      />
    </div>
  )

  if (!user?.is_superadmin) {
    return (
      <ResponsiveContainer size="xl" className="pt-8 pb-10">
        {breadcrumb}
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

  if (!FeatureFlagsAdmin) {
    return (
      <ResponsiveContainer size="xl" className="pt-8 pb-10">
        {breadcrumb}
        <div className="flex min-h-[400px] items-center justify-center">
          <p className="text-zinc-500 dark:text-zinc-400">
            {t('admin.featureFlagsNotAvailable')}
          </p>
        </div>
      </ResponsiveContainer>
    )
  }

  // eslint-disable-next-line react-hooks/static-components
  return <FeatureFlagsAdmin />
}
