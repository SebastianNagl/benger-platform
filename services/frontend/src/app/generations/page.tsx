'use client'

import { GenerationTaskList } from '@/components/generation/GenerationTaskList'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Button } from '@/components/shared/Button'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { projectsAPI } from '@/lib/api/projects'
import { Project } from '@/types/labelStudio'
import { parseSubdomain } from '@/lib/utils/subdomain'
import { canAccessProjectData } from '@/utils/permissions'
import { useRouter, useSearchParams } from 'next/navigation'
import { useCallback, useEffect, useState } from 'react'

export default function GenerationPage() {
  const { t } = useI18n()
  const { user, isLoading } = useAuth()
  const router = useRouter()
  const searchParams = useSearchParams()

  const [selectedProject, setSelectedProject] = useState<Project | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const { isPrivateMode } =
    typeof window !== 'undefined'
      ? parseSubdomain()
      : { isPrivateMode: true }

  // Check permissions
  useEffect(() => {
    if (!isLoading && !canAccessProjectData(user, { isPrivateMode })) {
      router.replace('/projects?error=no-permission')
    }
  }, [user, isLoading, router, isPrivateMode])

  // Persist selection and sync URL
  const handleProjectSelect = useCallback(
    (project: Project) => {
      setSelectedProject(project)
      localStorage.setItem('generations_lastProjectId', project.id.toString())
      const params = new URLSearchParams(searchParams?.toString() || '')
      params.set('projectId', project.id.toString())
      router.replace(`/generations?${params.toString()}`, { scroll: false })
    },
    [searchParams, router]
  )

  // Load projects
  useEffect(() => {
    if (isLoading) return
    const loadProjects = async () => {
      try {
        const response = await projectsAPI.list(1, 100)
        setProjects(response.items || [])
      } catch (err) {
        console.error('Failed to load projects:', err)
      }
    }
    loadProjects()
  }, [isLoading])

  // Auto-select project from URL or localStorage (without triggering router.replace)
  useEffect(() => {
    if (projects.length === 0 || selectedProject) return
    const projectId =
      searchParams?.get('projectId') ||
      localStorage.getItem('generations_lastProjectId')
    if (projectId) {
      const project = projects.find((p) => p.id.toString() === projectId)
      if (project) {
        setSelectedProject(project)
        localStorage.setItem('generations_lastProjectId', project.id.toString())
      }
    }
  }, [projects, selectedProject, searchParams])

  if (isLoading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <div className="text-center">
          <div className="mx-auto h-12 w-12 animate-spin rounded-full border-b-2 border-emerald-500"></div>
          <p className="mt-4 text-zinc-600 dark:text-zinc-400">
            {t('common.loading')}
          </p>
        </div>
      </div>
    )
  }

  if (!canAccessProjectData(user, { isPrivateMode })) {
    return (
      <ResponsiveContainer size="xl" className="pb-10 pt-8">
        <div className="text-center">
          <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-gray-100">
            {t('dataManagement.accessDenied')}
          </h3>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            {t('dataManagement.accessDeniedDescription')}
          </p>
          <div className="mt-6">
            <Button variant="filled" onClick={() => router.push('/projects')}>
              {t('common.backToProjects')}
            </Button>
          </div>
        </div>
      </ResponsiveContainer>
    )
  }

  return (
    <ResponsiveContainer
      size="full"
      className="px-4 pb-10 pt-8 sm:px-6 lg:px-8"
    >
      <div className="mb-4">
        <Breadcrumb
          items={[
            { label: t('navigation.dashboard'), href: '/dashboard' },
            { label: t('navigation.generation'), href: '/generations' },
          ]}
        />
      </div>

      <div className="mx-auto max-w-7xl">
        <div className="mt-8">
          <h1 className="mb-6 text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
            {t('generation.title')}
          </h1>

          <GenerationTaskList
            projectId={selectedProject?.id ?? ''}
            projects={projects}
            selectedProject={selectedProject}
            onProjectChange={handleProjectSelect}
          />
        </div>
      </div>
    </ResponsiveContainer>
  )
}
