'use client'

import { Card } from '@/components/shared/Card'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'
import { SearchInput } from '@/components/shared/SearchInput'
import { useI18n } from '@/contexts/I18nContext'
import { useProjects } from '@/hooks/useProjects'
import { Project } from '@/types/labelStudio'
import { CheckCircleIcon, XMarkIcon } from '@heroicons/react/24/outline'
import { useRouter } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'

interface ProjectSelectorProps {
  onProjectSelect: (project: Project) => void
  selectedProjectId?: string
}

export function ProjectSelector({
  onProjectSelect,
  selectedProjectId,
}: ProjectSelectorProps) {
  const { t } = useI18n()
  const router = useRouter()
  const { projects, loading, error, fetchProjects } = useProjects()
  const [searchQuery, setSearchQuery] = useState('')

  useEffect(() => {
    fetchProjects()
  }, [fetchProjects])

  // Derive filtered projects from projects and searchQuery
  const filteredProjects = useMemo(() => {
    if (!projects) return []

    return projects.filter((project) => {
      if (!searchQuery) return true
      const query = searchQuery.toLowerCase()
      return (
        project.title.toLowerCase().includes(query) ||
        project.description?.toLowerCase().includes(query) ||
        project.organization?.name?.toLowerCase().includes(query)
      )
    })
  }, [projects, searchQuery])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <LoadingSpinner size="large" />
      </div>
    )
  }

  if (error) {
    return (
      <Card className="border-red-200 bg-red-50 p-6 dark:border-red-800 dark:bg-red-900/20">
        <p className="text-red-800 dark:text-red-200">
          Failed to load projects: {error}
        </p>
      </Card>
    )
  }

  const handleStatusPillNavigation = (projectId: string) => {
    router.push(`/projects/${projectId}`)
  }

  // Sort projects alphabetically
  const sortedProjects = [...filteredProjects].sort((a, b) =>
    a.title.toLowerCase().localeCompare(b.title.toLowerCase())
  )

  return (
    <div className="space-y-4">
      {/* Search Bar */}
      <SearchInput
        placeholder={t('generation.projectSelector.searchPlaceholder')}
        value={searchQuery}
        onChange={setSearchQuery}
        className="w-full"
        data-testid="project-search-input"
      />

      {/* Results Info */}
      <div className="mb-4 flex items-center justify-between text-sm text-zinc-600 dark:text-zinc-400">
        <p>
          {t('generation.projectSelector.showing', {
            count: sortedProjects.length,
            total: projects?.length || 0,
          })}
        </p>
      </div>

      {/* Table Header */}
      {sortedProjects.length > 0 && (
        <div className="mb-2 overflow-x-auto rounded-lg border border-zinc-200 bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800/50">
          <div className="min-w-[640px]">
            <div className="grid grid-cols-[32px_1fr_80px_80px_80px_80px_120px] items-center gap-2 px-4 py-3 text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400 md:grid-cols-[32px_1fr_96px_96px_96px_96px_140px] md:gap-3 lg:grid-cols-[32px_1fr_96px_128px_128px_128px_160px] lg:gap-4">
              <div>{/* Checkbox */}</div>
              <div>{t('generation.projectSelector.tableHeaders.project')}</div>
              <div className="text-center">
                {t('generation.projectSelector.tableHeaders.tasks')}
              </div>
              <div className="text-center">
                {t('generation.projectSelector.tableHeaders.models')}
              </div>
              <div className="text-center">
                {t('generation.projectSelector.tableHeaders.prompts')}
              </div>
              <div className="text-center">
                {t('generation.projectSelector.tableHeaders.config')}
              </div>
              <div className="text-center">
                {t('generation.projectSelector.tableHeaders.status')}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Projects List */}
      {sortedProjects.length > 0 ? (
        <div className="space-y-3 overflow-x-auto">
          {sortedProjects.map((project) => {
            const isSelected = project.id === selectedProjectId
            return (
              <div
                key={project.id}
                data-testid={`project-row-${project.id}`}
                data-project-id={project.id}
                className={`group cursor-pointer rounded-lg border transition-all hover:shadow-md ${
                  isSelected
                    ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-900/20'
                    : 'border-zinc-200 bg-white hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800 dark:hover:bg-zinc-700/50'
                }`}
                onClick={(e) => {
                  e.preventDefault()
                  e.stopPropagation()
                  onProjectSelect(project)
                }}
                onMouseDown={(e) => e.preventDefault()}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    onProjectSelect(project)
                  }
                }}
              >
                {/* Table-like row using grid for perfect alignment */}
                <div className="min-w-[640px]">
                  <div className="grid grid-cols-[32px_1fr_80px_80px_80px_80px_120px] items-center gap-2 px-4 py-4 md:grid-cols-[32px_1fr_96px_96px_96px_96px_140px] md:gap-3 lg:grid-cols-[32px_1fr_96px_128px_128px_128px_160px] lg:gap-4">
                    {/* Checkbox/selection column */}
                    <div className="flex justify-center">
                      {isSelected ? (
                        <CheckCircleIcon className="h-5 w-5 text-emerald-600" />
                      ) : (
                        <div className="h-5 w-5 rounded border-2 border-zinc-300 bg-white group-hover:border-zinc-400 dark:border-zinc-600 dark:bg-zinc-800" />
                      )}
                    </div>

                    {/* Project info column */}
                    <div className="overflow-hidden">
                      <div className="min-w-0">
                        <div
                          className={`truncate text-sm font-medium ${
                            isSelected
                              ? 'text-emerald-900 dark:text-emerald-100'
                              : 'text-zinc-900 dark:text-white'
                          }`}
                        >
                          {project.title}
                        </div>
                        {project.description && (
                          <div className="mt-0.5 truncate text-xs text-zinc-500 dark:text-zinc-400">
                            {project.description}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Tasks column */}
                    <div className="text-center">
                      <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                        {project.task_count || 0}
                      </span>
                    </div>

                    {/* Models column */}
                    <div className="text-center">
                      <span className="text-sm text-zinc-600 dark:text-zinc-400">
                        {project.generation_models_count || 0}
                      </span>
                    </div>

                    {/* Prompts column */}
                    <div className="flex justify-center">
                      {project.generation_prompts_ready ? (
                        <CheckCircleIcon className="h-5 w-5 text-emerald-500" />
                      ) : (
                        <XMarkIcon className="h-5 w-5 text-red-500" />
                      )}
                    </div>

                    {/* Config column */}
                    <div className="flex justify-center">
                      {project.generation_config_ready ? (
                        <CheckCircleIcon className="h-5 w-5 text-emerald-500" />
                      ) : (
                        <XMarkIcon className="h-5 w-5 text-red-500" />
                      )}
                    </div>

                    {/* Status column */}
                    <div className="flex justify-center">
                      {project.generation_completed ? (
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            handleStatusPillNavigation(project.id)
                          }}
                          className="inline-flex cursor-pointer items-center rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-medium text-blue-800 transition-colors hover:bg-blue-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 dark:bg-blue-900/50 dark:text-blue-200 dark:hover:bg-blue-900/70"
                          aria-label={`Navigate to ${project.title} settings`}
                        >
                          {t(
                            'generation.projectSelector.statusLabels.complete'
                          )}
                        </button>
                      ) : project.generation_prompts_ready &&
                        project.generation_config_ready ? (
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            handleStatusPillNavigation(project.id)
                          }}
                          className="inline-flex cursor-pointer items-center rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-medium text-emerald-800 transition-colors hover:bg-emerald-200 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-1 dark:bg-emerald-900/50 dark:text-emerald-200 dark:hover:bg-emerald-900/70"
                          aria-label={`Navigate to ${project.title} settings`}
                        >
                          {t('generation.projectSelector.statusLabels.ready')}
                        </button>
                      ) : (
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            handleStatusPillNavigation(project.id)
                          }}
                          className="inline-flex cursor-pointer items-center rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-800 transition-colors hover:bg-amber-200 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:ring-offset-1 dark:bg-amber-900/50 dark:text-amber-200 dark:hover:bg-amber-900/70"
                          aria-label={`Navigate to ${project.title} settings`}
                        >
                          {t(
                            'generation.projectSelector.statusLabels.setupNeeded'
                          )}
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        <div className="rounded-lg border border-zinc-200 bg-white p-8 text-center dark:border-zinc-700 dark:bg-zinc-800">
          <p className="text-zinc-600 dark:text-zinc-400">
            {searchQuery
              ? t('generation.projectSelector.emptyStates.noProjectsFound')
              : t('generation.projectSelector.emptyStates.noProjects')}
          </p>
          {!searchQuery && (
            <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-500">
              {t('generation.projectSelector.emptyStates.createFirst')}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
