'use client'

import { useI18n } from '@/contexts/I18nContext'
import { apiClient } from '@/lib/api/client'
import { logger } from '@/lib/utils/logger'
import type { Task } from '@/types/labelStudio'
import { Dialog, DialogPanel, DialogTitle, Tab } from '@headlessui/react'
import {
  DocumentTextIcon,
  ExclamationTriangleIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'
import { useCallback, useEffect, useMemo, useState } from 'react'

interface TaskGenerationComparisonModalProps {
  task: Task | null
  isOpen: boolean
  onClose: () => void
  projectId: string
}

interface GenerationResult {
  task_id: string
  model_id: string
  generation_id: string
  status: string
  result?: Record<string, any>
  generated_at?: string
  generation_time_seconds?: number
  prompt_used?: string
  parameters?: Record<string, any>
  error_message?: string
  structure_key?: string
  created_by?: string
  created_by_name?: string
}

interface MultipleGenerationResults {
  task_id: string
  model_id: string
  results: GenerationResult[]
}

/**
 * Shows ALL generations for a task: one tab per model, each listing every
 * run (include_history) for that model so the totals reconcile with the
 * Generations count on the data table. Mirrors TaskAnnotationComparisonModal's
 * tab-per-actor pattern and uses the same scroll-safe flex layout.
 */
export function TaskGenerationComparisonModal({
  task,
  isOpen,
  onClose,
  projectId: _projectId,
}: TaskGenerationComparisonModalProps) {
  const { t } = useI18n()
  const [selectedTab, setSelectedTab] = useState(0)
  const [viewMode, setViewMode] = useState<'formatted' | 'raw'>('formatted')
  // Per-model result cache: model_id -> results (lazy-loaded on tab select).
  const [resultsByModel, setResultsByModel] = useState<
    Map<string, GenerationResult[]>
  >(new Map())
  const [loadingModel, setLoadingModel] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const models = useMemo(() => task?.generation_models || [], [task])

  // Reset when opening / switching task.
  useEffect(() => {
    if (isOpen) {
      setSelectedTab(0)
      setViewMode('formatted')
      setResultsByModel(new Map())
      setError(null)
    }
  }, [isOpen, task?.id])

  const fetchModelResults = useCallback(
    async (modelId: string) => {
      if (!task) return
      setLoadingModel(modelId)
      setError(null)
      try {
        const params = new URLSearchParams({
          task_id: task.id,
          model_id: modelId,
          include_history: 'true',
        })
        const data: MultipleGenerationResults = await apiClient.get(
          `/generation-tasks/generation-result?${params}`
        )
        setResultsByModel((prev) => {
          const next = new Map(prev)
          next.set(modelId, data.results || [])
          return next
        })
      } catch (err) {
        logger.debug('Failed to fetch generation results', err)
        setError(t('generation.comparison.modal.loadError'))
      } finally {
        setLoadingModel(null)
      }
    },
    [task, t]
  )

  // Lazy-load the selected model's results the first time its tab is shown.
  useEffect(() => {
    if (!isOpen || models.length === 0) return
    const modelId = models[selectedTab]
    if (modelId && !resultsByModel.has(modelId) && loadingModel !== modelId) {
      fetchModelResults(modelId)
    }
  }, [
    isOpen,
    models,
    selectedTab,
    resultsByModel,
    loadingModel,
    fetchModelResults,
  ])

  const formatResult = (data: any): string => {
    if (typeof data === 'string') return data
    if (typeof data === 'number' || typeof data === 'boolean')
      return String(data)
    if (Array.isArray(data)) return data.map(formatResult).join('\n')
    if (typeof data === 'object' && data !== null) {
      if (data.generated_text) return data.generated_text
      return Object.entries(data)
        .map(([key, value]) => `${key}: ${formatResult(value)}`)
        .join('\n')
    }
    return JSON.stringify(data)
  }

  const getStatusBadge = (status: string) => {
    const statusColors: Record<string, string> = {
      completed: 'bg-green-100 text-green-800',
      failed: 'bg-red-100 text-red-800',
      running: 'bg-yellow-100 text-yellow-800',
      pending: 'bg-gray-100 text-gray-800',
      cancelled: 'bg-orange-100 text-orange-800',
    }
    return (
      <span
        className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
          statusColors[status] || statusColors.pending
        }`}
      >
        {status}
      </span>
    )
  }

  const renderResult = (result: GenerationResult, index: number) => (
    <div
      key={result.generation_id || index}
      className="rounded-lg border border-gray-200 p-4 dark:border-gray-700"
    >
      <div className="mb-3 flex flex-wrap items-center gap-3 text-sm">
        {getStatusBadge(result.status)}
        {result.structure_key && (
          <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600 dark:bg-gray-800 dark:text-gray-300">
            {result.structure_key}
          </span>
        )}
        {result.generated_at && (
          <span className="text-gray-500 dark:text-gray-400">
            {new Date(result.generated_at).toLocaleString()}
          </span>
        )}
        {result.generation_time_seconds != null && (
          <span className="text-gray-400">
            {t('generation.resultModal.seconds', {
              value: result.generation_time_seconds.toFixed(2),
            })}
          </span>
        )}
        {result.created_by_name && (
          <span className="text-gray-400">
            {t('generation.resultModal.by', { user: result.created_by_name })}
          </span>
        )}
      </div>

      {result.status === 'completed' && result.result ? (
        <div className="max-h-80 overflow-y-auto rounded-lg bg-gray-50 p-3 dark:bg-gray-800">
          <pre className="whitespace-pre-wrap font-mono text-sm text-gray-800 dark:text-gray-100">
            {viewMode === 'raw'
              ? JSON.stringify(result.result, null, 2)
              : formatResult(result.result)}
          </pre>
        </div>
      ) : result.error_message ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 dark:border-red-900 dark:bg-red-900/20">
          <p className="text-sm text-red-600 dark:text-red-400">
            {result.error_message}
          </p>
        </div>
      ) : (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          {t('generation.comparison.modal.noResult')}
        </p>
      )}
    </div>
  )

  if (!task) return null

  return (
    <Dialog open={isOpen} onClose={onClose} className="relative z-50">
      <div className="fixed inset-0 bg-black/30" aria-hidden="true" />

      <div className="fixed inset-0 flex w-screen items-center justify-center p-2 sm:p-4">
        <DialogPanel className="flex max-h-[95vh] w-full max-w-5xl flex-col rounded-lg bg-white shadow-xl dark:bg-zinc-900 sm:max-h-[90vh]">
          {/* Header */}
          <div className="flex items-start justify-between border-b border-gray-200 p-4 dark:border-gray-700 sm:items-center sm:p-6">
            <div className="mr-2 min-w-0 flex-1">
              <DialogTitle className="truncate text-base font-semibold text-gray-900 dark:text-white sm:text-lg">
                {t('generation.comparison.modal.title')}
                <span className="hidden sm:inline">
                  {' '}
                  - {t('generation.comparison.modal.taskId', { taskId: task.id })}
                </span>
              </DialogTitle>
              <p className="mt-1 text-xs text-gray-600 dark:text-gray-400 sm:text-sm">
                {t('generation.comparison.modal.description')}
              </p>
            </div>
            <button
              onClick={onClose}
              className="rounded-lg p-1.5 text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-white sm:p-2"
            >
              <XMarkIcon className="h-4 w-4 sm:h-5 sm:w-5" />
            </button>
          </div>

          {/* Content (scroll-safe flex column) */}
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
            {models.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12">
                <DocumentTextIcon className="mb-4 h-12 w-12 text-gray-400" />
                <p className="text-gray-600 dark:text-gray-400">
                  {t('generation.comparison.modal.noGenerations')}
                </p>
              </div>
            ) : (
              <Tab.Group selectedIndex={selectedTab} onChange={setSelectedTab}>
                {/* Per-model tabs */}
                <div className="border-b border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800">
                  <Tab.List className="scrollbar-thin flex space-x-1 overflow-x-auto px-4 py-2 sm:px-6">
                    {models.map((modelId) => (
                      <Tab
                        key={modelId}
                        className={({ selected }) =>
                          `flex flex-shrink-0 items-center gap-2 whitespace-nowrap rounded-t-lg px-3 py-2 text-xs font-medium transition-colors sm:px-4 sm:text-sm ${
                            selected
                              ? 'border-b-2 border-blue-600 bg-white text-blue-600 dark:bg-zinc-900 dark:text-blue-400'
                              : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-700 dark:hover:text-white'
                          }`
                        }
                      >
                        <span className="max-w-[200px] truncate">{modelId}</span>
                      </Tab>
                    ))}
                  </Tab.List>
                </div>

                <Tab.Panels className="min-h-0 flex-1 overflow-y-auto">
                  {models.map((modelId) => {
                    const results = resultsByModel.get(modelId)
                    return (
                      <Tab.Panel key={modelId} className="space-y-4 p-4 sm:p-6">
                        {/* View mode toggle */}
                        <div className="flex justify-end">
                          <div className="flex rounded-lg bg-gray-100 p-1 dark:bg-gray-800">
                            {(['formatted', 'raw'] as const).map((mode) => (
                              <button
                                key={mode}
                                onClick={() => setViewMode(mode)}
                                className={`rounded-md px-3 py-1 text-sm font-medium transition-colors ${
                                  viewMode === mode
                                    ? 'bg-white text-gray-900 shadow-sm dark:bg-zinc-900 dark:text-white'
                                    : 'text-gray-600 hover:text-gray-900 dark:text-gray-400'
                                }`}
                              >
                                {mode === 'formatted'
                                  ? t('generation.resultModal.formatted')
                                  : t('generation.resultModal.rawJson')}
                              </button>
                            ))}
                          </div>
                        </div>

                        {error ? (
                          <div className="flex flex-col items-center justify-center py-12">
                            <ExclamationTriangleIcon className="mb-4 h-12 w-12 text-red-500" />
                            <p className="text-red-600">{error}</p>
                          </div>
                        ) : loadingModel === modelId || results === undefined ? (
                          <div className="flex items-center justify-center py-12">
                            <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-blue-600" />
                          </div>
                        ) : results.length === 0 ? (
                          <p className="py-8 text-center text-sm text-gray-500 dark:text-gray-400">
                            {t('generation.comparison.modal.noResult')}
                          </p>
                        ) : (
                          <div className="space-y-3">
                            {results.map((r, i) => renderResult(r, i))}
                          </div>
                        )}
                      </Tab.Panel>
                    )
                  })}
                </Tab.Panels>
              </Tab.Group>
            )}
          </div>
        </DialogPanel>
      </div>
    </Dialog>
  )
}
