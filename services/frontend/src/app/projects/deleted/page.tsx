'use client'

import { useRouter } from 'next/navigation'
import { useEffect } from 'react'

import { ProjectListTable } from '@/components/projects/ProjectListTable'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'

/**
 * Superadmin-only view of soft-deleted projects (migration 093). A normal
 * "delete" anywhere on the platform only hides the project; everything can
 * be restored from here, and ONLY here can data really be destroyed. It is
 * the shared project list in its deleted mode, so a row opens the project
 * (read-only while deleted) like the active and archived lists do.
 */
export default function DeletedProjectsPage() {
  const { t } = useI18n()
  const { user, isLoading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!isLoading && user && !user.is_superadmin) router.replace('/projects')
  }, [isLoading, user, router])

  if (isLoading || !user?.is_superadmin) return null

  return (
    <ResponsiveContainer size="full" className="pt-8 pb-10">
      <div className="mb-4">
        <Breadcrumb
          items={[
            { label: t('navigation.dashboard'), href: '/dashboard' },
            { label: t('navigation.projects'), href: '/projects' },
            { label: t('projects.deleted.title'), href: '/projects/deleted' },
          ]}
        />
      </div>

      <ProjectListTable showDeletedOnly={true} />
    </ResponsiveContainer>
  )
}
