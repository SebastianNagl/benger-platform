/**
 * EvaluationTab - Display evaluation metrics and results for project tasks
 */

'use client'

import { Badge } from '@/components/shared/Badge'
import { Button } from '@/components/shared/Button'
import { Input } from '@/components/shared/Input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/shared/Select'
import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import { useProgress } from '@/contexts/ProgressContext'
import { useProjectStore } from '@/stores/projectStore'
import { Task as LabelStudioTask } from '@/types/labelStudio'
import {
  ArrowDownTrayIcon,
  ArrowPathIcon,
  ChartBarIcon,
  CheckCircleIcon,
  ChevronDownIcon,
  ClockIcon,
  MagnifyingGlassIcon,
} from '@heroicons/react/24/outline'
import { formatDistanceToNow } from 'date-fns'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'

interface EvaluationTabProps {
  projectId: string
}

interface EvaluationMetrics {
  accuracy?: number
  f1_score?: number
  precision?: number
  recall?: number
  confidence?: number
  model?: string
  evaluated_at?: string
}

export function EvaluationTab({ projectId }: EvaluationTabProps) {
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
  const [sortBy, setSortBy] = useState<string>('id')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')
  const [filterStatus, setFilterStatus] = useState<
    'all' | 'evaluated' | 'pending'
  >('all')

  // Load tasks with evaluation data
  useEffect(() => {
    const loadTasks = async () => {
      setIsLoading(true)
      try {
        const labelStudioTasks = await fetchProjectTasks(projectId)
        // Filter to only show tasks with evaluation data or that need evaluation
        const tasksForEvaluation = labelStudioTasks.filter(
          (task) =>
            (task as any).llm_evaluations ||
            (task as any).llm_responses ||
            task.total_generations > 0
        )
        setTasks(tasksForEvaluation)
        setFilteredTasks(tasksForEvaluation)
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
        const evalData = (task as any).llm_evaluations
          ? JSON.stringify((task as any).llm_evaluations).toLowerCase()
          : ''
        return (
          taskData.includes(searchLower) ||
          evalData.includes(searchLower) ||
          task.id.toString().includes(searchLower)
        )
      })
    }

    // Status filter
    if (filterStatus !== 'all') {
      filtered = filtered.filter((task) => {
        if (filterStatus === 'evaluated')
          return (
            (task as any).llm_evaluations &&
            Object.keys((task as any).llm_evaluations).length > 0
          )
        if (filterStatus === 'pending')
          return (
            !(task as any).llm_evaluations ||
            Object.keys((task as any).llm_evaluations || {}).length === 0
          )
        return true
      })
    }

    // Apply sorting
    filtered.sort((a, b) => {
      let aVal, bVal

      switch (sortBy) {
        case 'id':
          aVal = a.id
          bVal = b.id
          break
        case 'status':
          aVal =
            (a as any).llm_evaluations &&
            Object.keys((a as any).llm_evaluations).length > 0
              ? 1
              : 0
          bVal =
            (b as any).llm_evaluations &&
            Object.keys((b as any).llm_evaluations).length > 0
              ? 1
              : 0
          break
        case 'accuracy':
          aVal = getEvaluationScore(a, 'accuracy')
          bVal = getEvaluationScore(b, 'accuracy')
          break
        case 'confidence':
          aVal = getEvaluationScore(a, 'confidence')
          bVal = getEvaluationScore(b, 'confidence')
          break
        case 'created':
          aVal = new Date(a.created_at).getTime()
          bVal = new Date(b.created_at).getTime()
          break
        default:
          aVal = a.id
          bVal = b.id
      }

      if (sortOrder === 'asc') {
        return aVal < bVal ? -1 : aVal > bVal ? 1 : 0
      } else {
        return aVal > bVal ? -1 : aVal < bVal ? 1 : 0
      }
    })

    setFilteredTasks(filtered)
  }, [tasks, searchQuery, filterStatus, sortBy, sortOrder])

  // Get evaluation score from task
  const getEvaluationScore = (
    task: LabelStudioTask,
    metric: string
  ): number => {
    if (!task.llm_evaluations) return 0
    const evaluations = Object.values(task.llm_evaluations)
    if (evaluations.length === 0) return 0

    const latestEval = evaluations[evaluations.length - 1] as any
    return latestEval[metric] || 0
  }

  // Get evaluation metrics for display
  const getEvaluationMetrics = (
    task: LabelStudioTask
  ): EvaluationMetrics | null => {
    if (
      !task.llm_evaluations ||
      Object.keys(task.llm_evaluations).length === 0
    ) {
      return null
    }

    // Get the latest evaluation
    const evaluations = Object.values(task.llm_evaluations)
    const latestEval = evaluations[evaluations.length - 1] as any

    return {
      accuracy: latestEval.accuracy || null,
      f1_score: latestEval.f1_score || null,
      precision: latestEval.precision || null,
      recall: latestEval.recall || null,
      confidence: latestEval.confidence || null,
      model: latestEval.model || 'Unknown',
      evaluated_at: latestEval.evaluated_at || task.updated_at,
    }
  }

  // Handle sorting
  const handleSort = (column: string) => {
    if (sortBy === column) {
      setSortOrder((prev) => (prev === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortBy(column)
      setSortOrder('desc')
    }
  }

  // Export evaluations
  const handleExport = async () => {
    const progressId = `export-evaluations-${Date.now()}`

    try {
      startProgress(progressId, 'Exporting evaluations...', {
        sublabel: `Preparing ${filteredTasks.length} evaluations`,
        indeterminate: false,
      })

      updateProgress(progressId, 30, 'Formatting data...')

      // Create export data with evaluation metrics
      const exportData = filteredTasks.map((task) => ({
        task_id: task.id,
        data: (task as any).data,
        evaluations: task.llm_evaluations || {},
        metrics: getEvaluationMetrics(task),
        created_at: task.created_at,
        updated_at: task.updated_at,
      }))

      updateProgress(progressId, 70, 'Creating download...')

      // Create and download JSON file
      const blob = new Blob([JSON.stringify(exportData, null, 2)], {
        type: 'application/json',
      })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${currentProject?.title || 'project'}_evaluations_${new Date().toISOString().split('T')[0]}.json`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)

      updateProgress(progressId, 100, 'Export complete!')
      completeProgress(progressId, 'success')

      addToast(`Exported ${filteredTasks.length} evaluations`, 'success')
    } catch (error: any) {
      completeProgress(progressId, 'error')
      addToast(
        `Export failed: ${error.message || 'Failed to export evaluations'}`,
        'error'
      )
    }
  }

  // Refresh data
  const handleRefresh = async () => {
    const progressId = `refresh-evaluations-${Date.now()}`

    try {
      startProgress(progressId, 'Refreshing evaluations...', {
        indeterminate: true,
      })

      const labelStudioTasks = await fetchProjectTasks(projectId)
      const tasksForEvaluation = labelStudioTasks.filter(
        (task) =>
          (task as any).llm_evaluations ||
          (task as any).llm_responses ||
          task.total_generations > 0
      )
      setTasks(tasksForEvaluation)

      completeProgress(progressId, 'success')
      addToast(t('toasts.evaluation.refreshed'), 'success')
    } catch (error) {
      completeProgress(progressId, 'error')
      addToast(t('toasts.evaluation.refreshFailed'), 'error')
    }
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

  // Format score for display
  const formatScore = (score: number | null | undefined): string => {
    if (score === null || score === undefined) return '—'
    return `${(score * 100).toFixed(1)}%`
  }

  // Get status badge variant
  const getStatusVariant = (
    metrics: EvaluationMetrics | null
  ): 'default' | 'secondary' | 'outline' | 'destructive' => {
    if (!metrics) return 'default'
    const score = metrics.accuracy || metrics.f1_score || 0
    if (score >= 0.8) return 'default' // Use default for success
    if (score >= 0.6) return 'secondary' // Use secondary for warning
    if (score > 0) return 'destructive' // Use destructive for error
    return 'outline'
  }

  return (
    <>
      {/* Action Bar */}
      <div className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="px-4 py-3 sm:px-6">
          <div className="flex flex-col space-y-3 lg:flex-row lg:items-center lg:justify-between lg:space-y-0">
            {/* Stats */}
            <div className="flex items-center space-x-6 text-sm">
              <div className="flex items-center space-x-2">
                <ChartBarIcon className="h-4 w-4 text-zinc-500" />
                <span className="text-zinc-600 dark:text-zinc-400">
                  {t('projects.evaluationTab.evaluatedCount', {
                    count: tasks.filter(
                      (tk) =>
                        (tk as any).llm_evaluations &&
                        Object.keys((tk as any).llm_evaluations).length > 0
                    ).length
                  })}
                </span>
              </div>
              <div className="flex items-center space-x-2">
                <ClockIcon className="h-4 w-4 text-zinc-500" />
                <span className="text-zinc-600 dark:text-zinc-400">
                  {t('projects.evaluationTab.pendingCount', {
                    count: tasks.filter(
                      (tk) =>
                        !(tk as any).llm_evaluations ||
                        Object.keys((tk as any).llm_evaluations || {}).length ===
                          0
                    ).length
                  })}
                </span>
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center space-x-2">
              {/* Status Filter */}
              <Select value={filterStatus} onValueChange={(v) => setFilterStatus(v as any)}>
                <SelectTrigger>
                  <SelectValue placeholder={t('projects.evaluationTab.allTasks')} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t('projects.evaluationTab.allTasks')}</SelectItem>
                  <SelectItem value="evaluated">{t('projects.evaluationTab.evaluated')}</SelectItem>
                  <SelectItem value="pending">{t('projects.evaluationTab.pending')}</SelectItem>
                </SelectContent>
              </Select>

              <Button
                variant="outline"
                onClick={handleExport}
                disabled={filteredTasks.length === 0}
              >
                <ArrowDownTrayIcon className="mr-2 h-4 w-4" />
                {t('projects.evaluationTab.export')}
              </Button>

              <Button
                variant="outline"
                onClick={handleRefresh}
                disabled={loading}
                data-testid="refresh-evaluations-button"
                aria-label="Refresh evaluations"
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
              placeholder={t('projects.evaluationTab.searchPlaceholder')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10"
            />
          </div>
        </div>

        {/* Results count */}
        <div className="mb-4 text-sm text-zinc-600 dark:text-zinc-400">
          {t('projects.evaluationTab.showingTasks', { showing: filteredTasks.length, total: tasks.length })}
        </div>

        {/* Data Table */}
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-emerald-500"></div>
          </div>
        ) : filteredTasks.length > 0 ? (
          <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[800px]">
                <thead className="border-b border-zinc-200 bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800">
                  <tr>
                    <th
                      className="cursor-pointer px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
                      onClick={() => handleSort('id')}
                    >
                      <div className="flex items-center space-x-1">
                        <span>{t('projects.evaluationTab.taskId')}</span>
                        {sortBy === 'id' && (
                          <ChevronDownIcon
                            className={`h-3 w-3 transition-transform ${sortOrder === 'asc' ? 'rotate-180' : ''}`}
                          />
                        )}
                      </div>
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-600 dark:text-zinc-400">
                      {t('projects.evaluationTab.taskData')}
                    </th>
                    <th
                      className="cursor-pointer px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
                      onClick={() => handleSort('status')}
                    >
                      <div className="flex items-center space-x-1">
                        <span>{t('projects.evaluationTab.status')}</span>
                        {sortBy === 'status' && (
                          <ChevronDownIcon
                            className={`h-3 w-3 transition-transform ${sortOrder === 'asc' ? 'rotate-180' : ''}`}
                          />
                        )}
                      </div>
                    </th>
                    <th
                      className="cursor-pointer px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
                      onClick={() => handleSort('accuracy')}
                    >
                      <div className="flex items-center space-x-1">
                        <span>{t('projects.evaluationTab.accuracy')}</span>
                        {sortBy === 'accuracy' && (
                          <ChevronDownIcon
                            className={`h-3 w-3 transition-transform ${sortOrder === 'asc' ? 'rotate-180' : ''}`}
                          />
                        )}
                      </div>
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-600 dark:text-zinc-400">
                      {t('projects.evaluationTab.f1Score')}
                    </th>
                    <th
                      className="cursor-pointer px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
                      onClick={() => handleSort('confidence')}
                    >
                      <div className="flex items-center space-x-1">
                        <span>{t('projects.evaluationTab.confidence')}</span>
                        {sortBy === 'confidence' && (
                          <ChevronDownIcon
                            className={`h-3 w-3 transition-transform ${sortOrder === 'asc' ? 'rotate-180' : ''}`}
                          />
                        )}
                      </div>
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-600 dark:text-zinc-400">
                      {t('projects.evaluationTab.model')}
                    </th>
                    <th
                      className="cursor-pointer px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
                      onClick={() => handleSort('created')}
                    >
                      <div className="flex items-center space-x-1">
                        <span>{t('projects.evaluationTab.evaluatedColumn')}</span>
                        {sortBy === 'created' && (
                          <ChevronDownIcon
                            className={`h-3 w-3 transition-transform ${sortOrder === 'asc' ? 'rotate-180' : ''}`}
                          />
                        )}
                      </div>
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-200 dark:divide-zinc-700">
                  {filteredTasks.map((task) => {
                    const metrics = getEvaluationMetrics(task)
                    const isEvaluated = metrics !== null

                    return (
                      <tr
                        key={task.id}
                        className="cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-800/50"
                        onClick={() =>
                          router.push(`/projects/${projectId}/tasks/${task.id}`)
                        }
                      >
                        <td className="px-4 py-4 font-mono text-sm text-zinc-900 dark:text-white">
                          {task.id}
                        </td>
                        <td className="px-4 py-4">
                          <p className="line-clamp-2 text-sm text-zinc-900 dark:text-white">
                            {getTaskDisplayValue(task)}
                          </p>
                        </td>
                        <td className="px-4 py-4">
                          <Badge variant={getStatusVariant(metrics)}>
                            {isEvaluated ? (
                              <div className="flex items-center space-x-1">
                                <CheckCircleIcon className="h-3 w-3" />
                                <span>{t('projects.evaluationTab.evaluated')}</span>
                              </div>
                            ) : (
                              <div className="flex items-center space-x-1">
                                <ClockIcon className="h-3 w-3" />
                                <span>{t('projects.evaluationTab.pending')}</span>
                              </div>
                            )}
                          </Badge>
                        </td>
                        <td className="px-4 py-4">
                          <span
                            className={`text-sm font-medium ${
                              metrics?.accuracy && metrics.accuracy >= 0.8
                                ? 'text-emerald-600'
                                : metrics?.accuracy && metrics.accuracy >= 0.6
                                  ? 'text-amber-600'
                                  : metrics?.accuracy
                                    ? 'text-red-600'
                                    : 'text-zinc-500'
                            }`}
                          >
                            {formatScore(metrics?.accuracy)}
                          </span>
                        </td>
                        <td className="px-4 py-4">
                          <span className="text-sm text-zinc-600 dark:text-zinc-400">
                            {formatScore(metrics?.f1_score)}
                          </span>
                        </td>
                        <td className="px-4 py-4">
                          <span className="text-sm text-zinc-600 dark:text-zinc-400">
                            {formatScore(metrics?.confidence)}
                          </span>
                        </td>
                        <td className="px-4 py-4">
                          <span className="text-sm text-zinc-600 dark:text-zinc-400">
                            {metrics?.model || '—'}
                          </span>
                        </td>
                        <td className="px-4 py-4">
                          <span className="text-sm text-zinc-600 dark:text-zinc-400">
                            {metrics?.evaluated_at
                              ? formatDistanceToNow(
                                  new Date(metrics.evaluated_at),
                                  { addSuffix: true }
                                )
                              : '—'}
                          </span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <div className="rounded-lg border border-zinc-200 bg-white py-12 text-center dark:border-zinc-800 dark:bg-zinc-900">
            <ChartBarIcon className="mx-auto mb-4 h-12 w-12 text-zinc-300 dark:text-zinc-700" />
            <p className="text-zinc-600 dark:text-zinc-400">
              {searchQuery || filterStatus !== 'all'
                ? t('projects.evaluationTab.noMatchingEvaluations')
                : t('projects.evaluationTab.noEvaluationData')}
            </p>
            <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-500">
              {t('projects.evaluationTab.metricsWillAppear')}
            </p>
          </div>
        )}
      </div>

    </>
  )
}
