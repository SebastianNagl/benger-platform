/**
 * Project Data page - displays annotation interface for project data management
 */

'use client'

import { AnnotationTab } from '@/components/projects/tabs/AnnotationTab'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { useProjectStore } from '@/stores/projectStore'
import { parseSubdomain } from '@/lib/utils/subdomain'
import { canAccessProjectData } from '@/utils/permissions'
import { useRouter } from 'next/navigation'
import { use, useEffect } from 'react'

interface ProjectDataPageProps {
  params: Promise<{
    id: string
  }>
}

export default function ProjectDataPage({ params }: ProjectDataPageProps) {
  const resolvedParams = use(params)
  const projectId = resolvedParams.id
  const { t } = useI18n()
  const { user, isLoading } = useAuth()
  const router = useRouter()
  const { isPrivateMode } = typeof window !== 'undefined' ? parseSubdomain() : { isPrivateMode: true }

  const { currentProject, fetchProject } = useProjectStore()

  // Check permissions - redirect if user cannot access project data
  useEffect(() => {
    if (!isLoading) {
      if (!canAccessProjectData(user, { isPrivateMode })) {
        // Redirect to project overview with error message
        router.replace(`/projects/${projectId}?error=no-data-access`)
      }
    }
  }, [user, isLoading, router, projectId])

  // Load project if not already loaded
  useEffect(() => {
    if (!currentProject || currentProject.id !== projectId) {
      fetchProject(projectId)
    }
  }, [projectId, currentProject, fetchProject])

  // Show loading state while checking permissions or loading project
  if (isLoading || !currentProject) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <div className="text-center">
          <div className="mx-auto h-12 w-12 animate-spin rounded-full border-b-2 border-emerald-500"></div>
          <p className="mt-4 text-zinc-600 dark:text-zinc-400">
            {t('project.loading') || 'Loading project...'}
          </p>
        </div>
      </div>
    )
  }

  // Show permission denied if user cannot access project data
  if (!canAccessProjectData(user, { isPrivateMode })) {
    return (
      <div className="min-h-screen bg-zinc-50 dark:bg-zinc-900">
        <div className="flex min-h-[50vh] items-center justify-center">
          <div className="text-center">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/20">
              <svg
                className="h-6 w-6 text-red-600 dark:text-red-400"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"
                />
              </svg>
            </div>
            <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-gray-100">
              {t('projects.data.accessDenied')}
            </h3>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              {t('projects.data.accessDeniedDescription')}
            </p>
            <div className="mt-6">
              <button
                type="button"
                onClick={() => router.push(`/projects/${projectId}`)}
                className="inline-flex items-center rounded-md bg-emerald-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-emerald-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-600"
              >
                {t('projects.data.backToOverview')}
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-900">
      {/* Header */}
      <div className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="px-6 py-4">
          {/* Breadcrumb */}
          <div className="mb-4">
            <Breadcrumb
              items={[
                {
                  label: t('navigation.dashboard') || 'Dashboard',
                  href: '/dashboard',
                },
                {
                  label: t('navigation.projects') || 'Projects',
                  href: '/projects',
                },
                { label: currentProject.title, href: `/projects/${projectId}` },
                {
                  label: t('navigation.projectData') || 'Data',
                  href: `/projects/${projectId}/data`,
                },
              ]}
            />
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="px-6 py-4">
        <AnnotationTab projectId={projectId} />
      </div>
    </div>
  )
}
