/**
 * GenerationTab - Display LLM generated responses and prompts for project tasks
 */

'use client'

import { Badge } from '@/components/shared/Badge'
import { Button } from '@/components/shared/Button'
import { Card } from '@/components/shared/Card'
import { Input } from '@/components/shared/Input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/shared/Select'
import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import { useProgress } from '@/contexts/ProgressContext'
import { Task } from '@/lib/api/types'
import { useProjectStore } from '@/stores/projectStore'
import { Task as LabelStudioTask } from '@/types/labelStudio'
import { labelStudioTaskToApi } from '@/utils/taskTypeAdapter'
import {
  ArrowDownTrayIcon,
  ArrowPathIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  ClockIcon,
  CpuChipIcon,
  DocumentTextIcon,
  MagnifyingGlassIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline'
import { formatDistanceToNow } from 'date-fns'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'

interface GenerationTabProps {
  projectId: string
}

interface ExpandedTasks {
  [key: string]: boolean
}

export function GenerationTab({ projectId }: GenerationTabProps) {
  const router = useRouter()
  const { addToast } = useToast()
  const { t } = useI18n()
  const { startProgress, updateProgress, completeProgress } = useProgress()

  const { currentProject, loading, fetchProjectTasks } = useProjectStore()

  // State
  const [tasks, setTasks] = useState<LabelStudioTask[]>([])
  const [filteredTasks, setFilteredTasks] = useState<LabelStudioTask[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [expandedTasks, setExpandedTasks] = useState<ExpandedTasks>({})
  const [filterModel, setFilterModel] = useState<string>('all')

  // Load tasks with LLM responses
  useEffect(() => {
    const loadTasks = async () => {
      setIsLoading(true)
      try {
        const labelStudioTasks = await fetchProjectTasks(projectId)
        // Filter to only show tasks with LLM responses or generations
        const tasksWithGenerations = labelStudioTasks.filter(
          (task) => (task as any).llm_responses || task.total_generations > 0
        )
        setTasks(tasksWithGenerations)
        setFilteredTasks(tasksWithGenerations)
      } finally {
        setIsLoading(false)
      }
    }
    if (projectId) {
      loadTasks()
    }
  }, [projectId, fetchProjectTasks])

  // Apply filters and search
  useEffect(() => {
    let filtered = [...tasks]

    // Search filter
    if (searchQuery) {
      filtered = filtered.filter((task) => {
        const searchLower = searchQuery.toLowerCase()
        const taskData = JSON.stringify((task as any).data).toLowerCase()
        const llmData = task.llm_responses
          ? JSON.stringify(task.llm_responses).toLowerCase()
          : ''
        return (
          taskData.includes(searchLower) ||
          llmData.includes(searchLower) ||
          task.id.toString().includes(searchLower)
        )
      })
    }

    // Model filter
    if (filterModel !== 'all') {
      filtered = filtered.filter((task) => {
        if (!task.llm_responses) return false
        const models = Object.keys(task.llm_responses)
        return models.includes(filterModel)
      })
    }

    setFilteredTasks(filtered)
  }, [tasks, searchQuery, filterModel])

  // Get unique models from all tasks
  const getUniqueModels = (): string[] => {
    const models = new Set<string>()
    tasks.forEach((task) => {
      if (task.llm_responses) {
        Object.keys(task.llm_responses).forEach((model) => models.add(model))
      }
    })
    return Array.from(models)
  }

  // Toggle task expansion
  const toggleTaskExpansion = (taskId: string) => {
    setExpandedTasks((prev) => ({
      ...prev,
      [taskId]: !prev[taskId],
    }))
  }

  // Get task display value
  const getTaskDisplayValue = (task: LabelStudioTask): string => {
    if ((task as any).data.text) return (task as any).data.text
    if ((task as any).data.question) return (task as any).data.question
    if ((task as any).data.prompt) return (task as any).data.prompt

    const firstStringValue = Object.values((task as any).data).find(
      (v) => typeof v === 'string'
    )
    if (firstStringValue) return firstStringValue as string

    return `Task ${task.id}`
  }

  // Format prompt from task data
  const formatPrompt = (task: Task): string => {
    // Try to find the actual prompt used
    if ((task as any).data.prompt) return (task as any).data.prompt
    if ((task as any).data.question)
      return `Question: ${(task as any).data.question}`
    if ((task as any).data.text) return `Text: ${(task as any).data.text}`

    // Fallback to showing all data as prompt context
    return JSON.stringify((task as any).data, null, 2)
  }

  // Export generations
  const handleExport = async () => {
    const progressId = `export-generations-${Date.now()}`

    try {
      startProgress(progressId, 'Exporting LLM generations...', {
        sublabel: `Preparing ${filteredTasks.length} tasks`,
        indeterminate: false,
      })

      updateProgress(progressId, 30, 'Formatting data...')

      // Create export data with prompts and responses
      const exportData = filteredTasks.map((task) => ({
        task_id: task.id,
        prompt: formatPrompt(labelStudioTaskToApi(task)),
        data: (task as any).data,
        llm_responses: task.llm_responses || {},
        created_at: task.created_at,
      }))

      updateProgress(progressId, 70, 'Creating download...')

      // Create and download JSON file
      const blob = new Blob([JSON.stringify(exportData, null, 2)], {
        type: 'application/json',
      })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${currentProject?.title || 'project'}_llm_generations_${new Date().toISOString().split('T')[0]}.json`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)

      updateProgress(progressId, 100, 'Export complete!')
      completeProgress(progressId, 'success')

      addToast(`Exported ${filteredTasks.length} LLM generations`, 'success')
    } catch (error: any) {
      completeProgress(progressId, 'error')
      addToast(
        `Export failed: ${error.message || 'Failed to export generations'}`,
        'error'
      )
    }
  }

  // Refresh data
  const handleRefresh = async () => {
    const progressId = `refresh-generations-${Date.now()}`

    try {
      startProgress(progressId, 'Refreshing LLM generations...', {
        indeterminate: true,
      })

      const labelStudioTasks = await fetchProjectTasks(projectId)
      const tasksWithGenerations = labelStudioTasks.filter(
        (task) => (task as any).llm_responses || task.total_generations > 0
      )
      setTasks(tasksWithGenerations)

      completeProgress(progressId, 'success')
      addToast(t('toasts.generation.refreshed'), 'success')
    } catch (error) {
      completeProgress(progressId, 'error')
      addToast(t('toasts.generation.refreshFailed'), 'error')
    }
  }

  const uniqueModels = getUniqueModels()

  return (
    <>
      {/* Action Bar */}
      <div className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="px-4 py-3 sm:px-6">
          <div className="flex flex-col space-y-3 lg:flex-row lg:items-center lg:justify-between lg:space-y-0">
            {/* Stats */}
            <div className="flex items-center space-x-6 text-sm">
              <div className="flex items-center space-x-2">
                <SparklesIcon className="h-4 w-4 text-zinc-500" />
                <span className="text-zinc-600 dark:text-zinc-400">
                  {t('projects.generationTab.tasksWithGenerations', { count: tasks.length })}
                </span>
              </div>
              <div className="flex items-center space-x-2">
                <CpuChipIcon className="h-4 w-4 text-zinc-500" />
                <span className="text-zinc-600 dark:text-zinc-400">
                  {t('projects.generationTab.modelsUsed', { count: uniqueModels.length })}
                </span>
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center space-x-2">
              {/* Model Filter */}
              <Select value={filterModel} onValueChange={setFilterModel}>
                <SelectTrigger>
                  <SelectValue placeholder={t('projects.generationTab.allModels')} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t('projects.generationTab.allModels')}</SelectItem>
                  {uniqueModels.map((model) => (
                    <SelectItem key={model} value={model}>
                      {model}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <Button
                variant="outline"
                onClick={handleExport}
                disabled={filteredTasks.length === 0}
              >
                <ArrowDownTrayIcon className="mr-2 h-4 w-4" />
                {t('projects.generationTab.export')}
              </Button>

              <Button
                variant="outline"
                onClick={handleRefresh}
                disabled={loading}
              >
                <ArrowPathIcon
                  className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`}
                />
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="px-4 py-4 sm:px-6 sm:py-6">
        {/* Search Bar */}
        <div className="mb-4 sm:mb-6">
          <div className="relative">
            <MagnifyingGlassIcon className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 transform text-zinc-400" />
            <Input
              placeholder={t('projects.generationTab.searchPlaceholder')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10"
            />
          </div>
        </div>

        {/* Results count */}
        <div className="mb-4 text-sm text-zinc-600 dark:text-zinc-400">
          {t('projects.generationTab.showingTasks', { showing: filteredTasks.length, total: tasks.length })}
        </div>

        {/* Task List */}
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-emerald-500"></div>
          </div>
        ) : filteredTasks.length > 0 ? (
          <div className="space-y-4">
            {filteredTasks.map((task) => {
              const isExpanded = expandedTasks[task.id]
              const hasResponses =
                task.llm_responses && Object.keys(task.llm_responses).length > 0

              return (
                <Card key={task.id} className="overflow-hidden">
                  {/* Task Header */}
                  <div
                    className="cursor-pointer p-4 transition-colors hover:bg-zinc-50 dark:hover:bg-zinc-800/50"
                    onClick={() => toggleTaskExpansion(task.id)}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="mb-2 flex items-center space-x-2">
                          <button className="p-0.5">
                            {isExpanded ? (
                              <ChevronDownIcon className="h-4 w-4 text-zinc-500" />
                            ) : (
                              <ChevronRightIcon className="h-4 w-4 text-zinc-500" />
                            )}
                          </button>
                          <span className="font-mono text-xs text-zinc-500">
                            {t('projects.generationTab.taskId', { id: task.id })}
                          </span>
                          {hasResponses && (
                            <Badge variant="default" className="text-xs">
                              {t('projects.generationTab.responses', { count: Object.keys(task.llm_responses!).length })}
                            </Badge>
                          )}
                        </div>
                        <p className="ml-6 line-clamp-2 text-sm text-zinc-900 dark:text-white">
                          {getTaskDisplayValue(task)}
                        </p>
                      </div>
                      <div className="flex items-center space-x-2 text-xs text-zinc-500">
                        <ClockIcon className="h-4 w-4" />
                        <span>
                          {formatDistanceToNow(new Date(task.created_at), {
                            addSuffix: true,
                          })}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Expanded Content */}
                  {isExpanded && (
                    <div className="border-t border-zinc-200 dark:border-zinc-700">
                      {/* Prompt Section */}
                      <div className="bg-zinc-50 p-4 dark:bg-zinc-800/50">
                        <div className="mb-2 flex items-center space-x-2">
                          <DocumentTextIcon className="h-4 w-4 text-zinc-500" />
                          <h4 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                            {t('projects.generationTab.prompt')}
                          </h4>
                        </div>
                        <pre className="whitespace-pre-wrap rounded-md border border-zinc-200 bg-white p-3 font-mono text-sm text-zinc-600 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-400">
                          {formatPrompt(labelStudioTaskToApi(task))}
                        </pre>
                      </div>

                      {/* LLM Responses */}
                      {hasResponses && (
                        <div className="space-y-4 p-4">
                          <div className="mb-2 flex items-center space-x-2">
                            <SparklesIcon className="h-4 w-4 text-zinc-500" />
                            <h4 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                              {t('projects.generationTab.llmResponses')}
                            </h4>
                          </div>

                          {Object.entries(task.llm_responses!).map(
                            ([model, response]) => (
                              <div key={model} className="space-y-2">
                                <div className="flex items-center space-x-2">
                                  <CpuChipIcon className="h-3 w-3 text-emerald-500" />
                                  <span className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
                                    {model}
                                  </span>
                                </div>
                                <div className="ml-5 rounded-md border border-zinc-200 bg-white p-3 dark:border-zinc-700 dark:bg-zinc-900">
                                  <pre className="whitespace-pre-wrap text-sm text-zinc-700 dark:text-zinc-300">
                                    {typeof response === 'string'
                                      ? response
                                      : JSON.stringify(response, null, 2)}
                                  </pre>
                                </div>
                              </div>
                            )
                          )}
                        </div>
                      )}

                      {/* View Details Button */}
                      <div className="px-4 pb-4">
                        <Button
                          variant="outline"
                          onClick={(e) => {
                            e.stopPropagation()
                            router.push(
                              `/projects/${projectId}/tasks/${task.id}`
                            )
                          }}
                          className="w-full"
                        >
                          {t('projects.generationTab.viewTaskDetails')}
                        </Button>
                      </div>
                    </div>
                  )}
                </Card>
              )
            })}
          </div>
        ) : (
          <div className="py-12 text-center">
            <SparklesIcon className="mx-auto mb-4 h-12 w-12 text-zinc-300 dark:text-zinc-700" />
            <p className="text-zinc-600 dark:text-zinc-400">
              {searchQuery || filterModel !== 'all'
                ? t('projects.generationTab.noMatchingGenerations')
                : t('projects.generationTab.noGenerationsFound')}
            </p>
            <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-500">
              {t('projects.generationTab.generateResponsesToSee')}
            </p>
          </div>
        )}
      </div>
    </>
  )
}
