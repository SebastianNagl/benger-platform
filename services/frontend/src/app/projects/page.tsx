/**
 * Projects page - Label Studio aligned
 *
 * Main page for listing all projects, replacing the old tasks page
 */

'use client'

import { ProjectListTable } from '@/components/projects/ProjectListTable'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'

export default function ProjectsPage() {
  const { t } = useI18n()
  const { isLoading } = useAuth()

  // Show loading state while checking permissions
  if (isLoading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <div className="text-center">
          <div className="mx-auto h-12 w-12 animate-spin rounded-full border-2 border-zinc-300 border-t-emerald-500 dark:border-zinc-600 dark:border-t-emerald-400"></div>
          <p className="mt-4 text-zinc-600 dark:text-zinc-400">
            {t('common.loading')}
          </p>
        </div>
      </div>
    )
  }

  return (
    <ResponsiveContainer size="full" className="pt-8 pb-10">
      {/* Breadcrumb */}
      <div className="mb-4">
        <Breadcrumb
          items={[
            { label: t('navigation.dashboard'), href: '/dashboard' },
            { label: t('navigation.projects'), href: '/projects' },
          ]}
        />
      </div>

      <ProjectListTable />
    </ResponsiveContainer>
  )
}
