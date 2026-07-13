'use client'

import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { useSlot } from '@/lib/extensions/slots'

/**
 * Host route for the LTI registrations admin panel.
 *
 * Superadmin guard and page shell follow the other src/app/admin/* pages;
 * the registration management UI itself (CRUD forms, key rotation,
 * deployments) ships in the proprietary extended package via the
 * 'LtiRegistrationsAdmin' slot.
 */
export default function AdminLtiPage() {
  const { user } = useAuth()
  const { t } = useI18n()
  const LtiRegistrationsAdmin = useSlot('LtiRegistrationsAdmin')

  const breadcrumb = (
    <div className="mb-4">
      <Breadcrumb
        items={[
          { label: t('navigation.dashboard'), href: '/dashboard' },
          { label: 'LTI', href: '/admin/lti' },
        ]}
      />
    </div>
  )

  if (!user?.is_superadmin) {
    return (
      <ResponsiveContainer size="xl" className="pb-10 pt-8">
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

  if (!LtiRegistrationsAdmin) {
    return (
      <ResponsiveContainer size="xl" className="pb-10 pt-8">
        {breadcrumb}
        <div className="flex min-h-[400px] items-center justify-center">
          <p className="text-zinc-500 dark:text-zinc-400">
            LTI administration requires the extended edition.
          </p>
        </div>
      </ResponsiveContainer>
    )
  }

  // eslint-disable-next-line react-hooks/static-components
  return <LtiRegistrationsAdmin />
}
