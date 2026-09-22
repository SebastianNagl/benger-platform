/**
 * Archived Projects page
 *
 * Page for listing and managing archived projects with unarchive functionality
 */

'use client'

import { ProjectListTable } from '@/components/projects/ProjectListTable'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { canCreateProjects } from '@/utils/permissions'
import { useRouter } from 'next/navigation'
import { useEffect } from 'react'

export default function ArchivedProjectsPage() {
  const { t } = useI18n()
  const router = useRouter()
  const { user, isLoading } = useAuth()

  // Same gate as the Archive button; the backend access check is the
  // authoritative enforcement (the list only holds what the user may see).
  const allowed = canCreateProjects(user)
  useEffect(() => {
    if (!isLoading && user && !allowed) {
      router.replace('/projects')
    }
  }, [isLoading, user, allowed, router])

  if (!isLoading && user && !allowed) {
    return null
  }

  return (
    <ResponsiveContainer
      size="full"
      className="px-4 pt-8 pb-10 sm:px-6 lg:px-8"
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
