'use client'

import { FeatureFlagsAdmin } from '@/components/admin/featureFlags/FeatureFlagsAdmin'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'

/**
 * Host route for the feature flags admin console.
 *
 * Superadmin guard and page shell follow the other src/app/admin/* pages.
 * The flag engine and the console are platform code (CORE 2.42); extension
 * packages register their flags, including their master flag
 * `extension.<id>`, which switches the whole package per viewer at runtime.
 */
export default function FeatureFlagsAdminPage() {
  const { user } = useAuth()
  const { t } = useI18n()

  if (!user?.is_superadmin) {
    return (
      <ResponsiveContainer size="xl" className="pt-8 pb-10">
        <div className="mb-4">
          <Breadcrumb
            items={[
              { label: t('navigation.dashboard'), href: '/dashboard' },
              { label: t('admin.featureFlags'), href: '/admin/feature-flags' },
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

  return <FeatureFlagsAdmin />
}
