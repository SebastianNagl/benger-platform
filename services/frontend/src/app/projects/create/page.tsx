/**
 * Create Project page - Label Studio aligned with multi-step wizard
 *
 * Three-step wizard for creating projects:
 * 1. Project Info - Name and description
 * 2. Data Import - Upload or connect data (optional)
 * 3. Labeling Setup - Configure annotation interface
 */

'use client'

import { ProjectCreationWizard } from '@/components/projects/ProjectCreationWizard'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { parseSubdomain } from '@/lib/utils/subdomain'
import { canCreateProjects } from '@/utils/permissions'
import { useRouter } from 'next/navigation'
import { useEffect } from 'react'

export default function CreateProjectPage() {
  const { t } = useI18n()
  const { user, isLoading } = useAuth()
  const router = useRouter()
  const { isPrivateMode } = typeof window !== 'undefined' ? parseSubdomain() : { isPrivateMode: true }

  // Check permissions - redirect if user cannot create projects
  useEffect(() => {
    if (!isLoading) {
      if (!canCreateProjects(user, { isPrivateMode })) {
        // Redirect to projects list with error message
        router.replace('/projects?error=no-permission')
      }
    }
  }, [user, isLoading, router, isPrivateMode])

  // Show loading state while checking permissions
  if (isLoading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <div className="text-center">
          <div className="mx-auto h-12 w-12 animate-spin rounded-full border-b-2 border-emerald-500"></div>
          <p className="mt-4 text-zinc-600 dark:text-zinc-400">
            {t('common.loading') || 'Loading...'}
          </p>
        </div>
      </div>
    )
  }

  // Show permission denied if user cannot create projects
  if (!canCreateProjects(user, { isPrivateMode })) {
    return (
      <ResponsiveContainer size="xl" className="pb-10 pt-8">
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
            {t('projects.create.accessDenied')}
          </h3>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            {t('projects.create.permissionDenied')}
          </p>
          <div className="mt-6">
            <button
              type="button"
              onClick={() => router.push('/projects')}
              className="inline-flex items-center rounded-md bg-emerald-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-emerald-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-600"
            >
              {t('projects.backToProjects')}
            </button>
          </div>
        </div>
      </ResponsiveContainer>
    )
  }

  return (
    <ResponsiveContainer size="xl" className="pb-10 pt-8">
      {/* Breadcrumb */}
      <div className="mb-4">
        <Breadcrumb
          items={[
            { label: t('navigation.dashboard'), href: '/dashboard' },
            { label: t('navigation.projects'), href: '/projects' },
            {
              label: t('projects.create.title') || 'Create',
              href: '/projects/create',
            },
          ]}
        />
      </div>

      <ProjectCreationWizard />
    </ResponsiveContainer>
  )
}
