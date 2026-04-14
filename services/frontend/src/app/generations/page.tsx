'use client'

import { GenerationTaskList } from '@/components/generation/GenerationTaskList'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Button } from '@/components/shared/Button'
import { Card } from '@/components/shared/Card'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { projectsAPI } from '@/lib/api/projects'
import { Project } from '@/types/labelStudio'
import { parseSubdomain } from '@/lib/utils/subdomain'
import { canAccessProjectData } from '@/utils/permissions'
import { ChevronDownIcon } from '@heroicons/react/24/outline'
import { useRouter, useSearchParams } from 'next/navigation'
import { useCallback, useEffect, useRef, useState } from 'react'

export default function GenerationPage() {
  const { t } = useI18n()
  const { user, isLoading } = useAuth()
  const router = useRouter()
  const searchParams = useSearchParams()

  const [selectedProject, setSelectedProject] = useState<Project | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)
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
      setDropdownOpen(false)
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
        setDropdownOpen(false)
        localStorage.setItem('generations_lastProjectId', project.id.toString())
      }
    }
  }, [projects, selectedProject, searchParams])

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

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

          {/* Project dropdown */}
          <Card className="mb-6 p-4">
            <div className="flex flex-wrap items-end gap-3">
              <div className="relative" ref={dropdownRef}>
                <label className="mb-1 block text-xs font-medium text-gray-500">
                  {t('generation.project')}
                </label>
                <Button
                  variant="outline"
                  onClick={() => setDropdownOpen(!dropdownOpen)}
                  className="w-48 justify-between"
                >
                  <span className="truncate">
                    {selectedProject?.title ||
                      t('generation.selectProject')}
                  </span>
                  <ChevronDownIcon
                    className={`ml-2 h-4 w-4 opacity-70 transition-transform ${dropdownOpen ? 'rotate-180' : ''}`}
                  />
                </Button>
                {dropdownOpen && (
                  <div className="absolute z-50 mt-1 max-h-60 w-72 overflow-auto rounded-lg border border-gray-200 bg-white shadow-lg dark:border-gray-700 dark:bg-gray-800">
                    {projects.map((project) => (
                      <button
                        key={project.id}
                        onClick={() => handleProjectSelect(project)}
                        className={`w-full px-3 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-700 ${
                          selectedProject?.id === project.id
                            ? 'bg-emerald-50 dark:bg-emerald-900/20'
                            : ''
                        }`}
                      >
                        <div className="font-medium">{project.title}</div>
                        <div className="text-xs text-gray-500">
                          {project.task_count || 0} tasks
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </Card>

          {/* Generation task list */}
          {selectedProject && (
            <GenerationTaskList projectId={selectedProject.id} />
          )}
        </div>
      </div>
    </ResponsiveContainer>
  )
}
