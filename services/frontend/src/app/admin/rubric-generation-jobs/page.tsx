'use client'

import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { useSlot } from '@/lib/extensions/slots'

/**
 * Host route for the list of grading sheet generation jobs.
 *
 * Superadmin guard and page shell follow the other src/app/admin/* pages;
 * the list itself (filters, failure reasons, retries) ships in the extended
 * package via the 'RubricGenerationJobsAdmin' slot and reads
 * GET /api/admin/rubric-generation-jobs.
 */
export default function AdminRubricGenerationJobsPage() {
  const { user } = useAuth()
  const { t } = useI18n()
  const RubricGenerationJobsAdmin = useSlot('RubricGenerationJobsAdmin')

  const breadcrumb = (
    <div className="mb-4">
      <Breadcrumb
        items={[
          { label: t('navigation.dashboard'), href: '/dashboard' },
          {
            label: t('admin.rubricGenerationJobs.title'),
            href: '/admin/rubric-generation-jobs',
          },
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

  if (!RubricGenerationJobsAdmin) {
    return (
      <ResponsiveContainer size="xl" className="pt-8 pb-10">
        {breadcrumb}
        <div className="flex min-h-[400px] items-center justify-center">
          <p className="text-zinc-500 dark:text-zinc-400">
            {t('admin.rubricGenerationJobs.extendedRequired')}
          </p>
        </div>
      </ResponsiveContainer>
    )
  }

  // The slot renders its own page shell, as on /admin/lti.
  // eslint-disable-next-line react-hooks/static-components
  return <RubricGenerationJobsAdmin />
}
