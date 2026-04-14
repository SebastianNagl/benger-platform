/**
 * Archived Projects page
 *
 * Page for listing and managing archived projects with unarchive functionality
 */

'use client'

import { ProjectListTable } from '@/components/projects/ProjectListTable'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useI18n } from '@/contexts/I18nContext'

export default function ArchivedProjectsPage() {
  const { t } = useI18n()
  return (
    <ResponsiveContainer
      size="full"
      className="px-4 pb-10 pt-8 sm:px-6 lg:px-8"
    >
      {/* Breadcrumb */}
      <div className="mb-4">
        <Breadcrumb
          items={[
            { label: t('navigation.dashboard'), href: '/dashboard' },
            { label: t('navigation.projects'), href: '/projects' },
            {
              label: t('projects.archived') || 'Archived',
              href: '/projects/archived',
            },
          ]}
        />
      </div>

      <ProjectListTable showArchivedOnly={true} />
    </ResponsiveContainer>
  )
}
