'use client'

import { Button } from '@/components/shared/Button'
import { Card } from '@/components/shared/Card'
import { Input } from '@/components/shared/Input'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/shared/Select'
import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import { useProjectStore } from '@/stores/projectStore'
import {
  ArrowDownTrayIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  ClipboardDocumentIcon,
  CpuChipIcon,
  DocumentTextIcon,
  MagnifyingGlassIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline'
import { formatDistanceToNow } from 'date-fns'
import { useEffect, useState } from 'react'

interface LLMResponse {
  id: string
  task_id: string
  model_id: string
  response_content: string
  case_data: any
  created_at: string
  status: string
}

interface GenerationResult {
  task_id: string
  task_data: any
  responses: Record<string, LLMResponse>
}

interface GenerationResultsProps {
  projectId: string
  generationIds?: string[]
}

export function GenerationResults({
  projectId,
  generationIds,
}: GenerationResultsProps) {
  const { addToast } = useToast()
  const { t } = useI18n()
  const { fetchProjectTasks } = useProjectStore()
  const [results, setResults] = useState<GenerationResult[]>([])
  const [filteredResults, setFilteredResults] = useState<GenerationResult[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedModel, setSelectedModel] = useState<string>('all')
  const [expandedTasks, setExpandedTasks] = useState<Set<string>>(new Set())
  const [isLoading, setIsLoading] = useState(true)
  const [availableModels, setAvailableModels] = useState<string[]>([])

  // Load generation results
  useEffect(() => {
    const loadResults = async () => {
      setIsLoading(true)
      try {
        // Fetch tasks with LLM responses
        const tasks = await fetchProjectTasks(projectId)

        const formattedResults: GenerationResult[] = []
        const modelSet = new Set<string>()

        tasks.forEach((task) => {
          if (
            task.llm_responses &&
            Object.keys(task.llm_responses).length > 0
          ) {
            const responses: Record<string, LLMResponse> = {}

            Object.entries(task.llm_responses).forEach(([model, response]) => {
              modelSet.add(model)
              responses[model] = {
                id: `${task.id}_${model}`,
                task_id: task.id,
                model_id: model,
                response_content:
                  typeof response === 'string'
                    ? response
                    : JSON.stringify(response),
                case_data: task.data,
                created_at: task.created_at,
                status: 'completed',
              }
            })

            formattedResults.push({
              task_id: task.id,
              task_data: task.data,
              responses,
            })
          }
        })

        setResults(formattedResults)
        setFilteredResults(formattedResults)
        setAvailableModels(Array.from(modelSet))
      } catch (error) {
        console.error('Failed to load results:', error)
        addToast(t('toasts.generation.resultsFailed'), 'error')
      } finally {
        setIsLoading(false)
      }
    }

    loadResults()
  }, [projectId, fetchProjectTasks, addToast])

  // Apply filters
  useEffect(() => {
    let filtered = [...results]

    // Search filter
    if (searchQuery) {
      const query = searchQuery.toLowerCase()
      filtered = filtered.filter((result) => {
        const taskData = JSON.stringify(result.task_data).toLowerCase()
        const responses = JSON.stringify(result.responses).toLowerCase()
        return taskData.includes(query) || responses.includes(query)
      })
    }

    // Model filter
    if (selectedModel !== 'all') {
      filtered = filtered.filter((result) => {
        return selectedModel in result.responses
      })
    }

    setFilteredResults(filtered)
  }, [results, searchQuery, selectedModel])

  const toggleTaskExpansion = (taskId: string) => {
    setExpandedTasks((prev) => {
      const newSet = new Set(prev)
      if (newSet.has(taskId)) {
        newSet.delete(taskId)
      } else {
        newSet.add(taskId)
      }
      return newSet
    })
  }

  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      addToast(t('toasts.clipboard.copied'), 'success')
    } catch (error) {
      addToast(t('toasts.clipboard.copyFailed'), 'error')
    }
  }

  const exportResults = async () => {
    try {
      const exportData = {
        project_id: projectId,
        exported_at: new Date().toISOString(),
        total_tasks: filteredResults.length,
        models: availableModels,
        results: filteredResults.map((result) => ({
          task_id: result.task_id,
          task_data: result.task_data,
          responses: Object.entries(result.responses).map(
            ([model, response]) => ({
              model: model,
              response: response.response_content,
              created_at: response.created_at,
            })
          ),
        })),
      }

      const blob = new Blob([JSON.stringify(exportData, null, 2)], {
        type: 'application/json',
      })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `generation_results_${projectId}_${new Date().toISOString().split('T')[0]}.json`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)

      addToast(t('toasts.generation.exported', { count: filteredResults.length }), 'success')
    } catch (error) {
      addToast(t('toasts.generation.exportFailed'), 'error')
    }
  }

  const getTaskPreview = (taskData: any): string => {
    if (taskData.text) return taskData.text
    if (taskData.question) return taskData.question
    if (taskData.prompt) return taskData.prompt

    const firstString = Object.values(taskData).find(
      (v) => typeof v === 'string'
    )
    return (firstString as string) || `Task ${taskData.id || ''}`
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <LoadingSpinner size="large" />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Filters and Actions */}
      <Card>
        <div className="p-4">
          <div className="flex flex-col space-y-4 lg:flex-row lg:items-center lg:justify-between lg:space-y-0">
            <div className="flex flex-1 items-center space-x-4">
              {/* Search */}
              <div className="relative max-w-md flex-1">
                <MagnifyingGlassIcon className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 transform text-zinc-400" />
                <Input
                  type="text"
                  placeholder={t('generation.results.searchPlaceholder')}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-10"
                />
              </div>

              {/* Model Filter */}
              <Select value={selectedModel} onValueChange={setSelectedModel}>
                <SelectTrigger>
                  <SelectValue placeholder={t('generation.results.allModels')} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t('generation.results.allModels')}</SelectItem>
                  {availableModels.map((model) => (
                    <SelectItem key={model} value={model}>
                      {model}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Export Button */}
            <Button
              variant="outline"
              onClick={exportResults}
              disabled={filteredResults.length === 0}
            >
              <ArrowDownTrayIcon className="mr-2 h-4 w-4" />
              {t('generation.results.exportResults')}
            </Button>
          </div>

          {/* Stats */}
          <div className="mt-4 flex items-center space-x-6 text-sm text-zinc-600 dark:text-zinc-400">
            <div className="flex items-center space-x-2">
              <DocumentTextIcon className="h-4 w-4" />
              <span>{filteredResults.length} {t('generation.results.tasksWithResponses')}</span>
            </div>
            <div className="flex items-center space-x-2">
              <CpuChipIcon className="h-4 w-4" />
              <span>{availableModels.length} {t('generation.results.modelsUsed')}</span>
            </div>
          </div>
        </div>
      </Card>

      {/* Results List */}
      {filteredResults.length > 0 ? (
        <div className="space-y-4">
          {filteredResults.map((result) => {
            const isExpanded = expandedTasks.has(result.task_id)
            const modelCount = Object.keys(result.responses).length

            return (
              <Card key={result.task_id} className="overflow-hidden">
                {/* Task Header */}
                <div
                  className="cursor-pointer p-4 transition-colors hover:bg-zinc-50 dark:hover:bg-zinc-800/50"
                  onClick={() => toggleTaskExpansion(result.task_id)}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                      <button className="p-0.5">
                        {isExpanded ? (
                          <ChevronDownIcon className="h-5 w-5 text-zinc-500" />
                        ) : (
                          <ChevronRightIcon className="h-5 w-5 text-zinc-500" />
                        )}
                      </button>
                      <div>
                        <div className="flex items-center space-x-2">
                          <span className="font-mono text-xs text-zinc-500">
                            {t('generation.results.taskPrefix')} #{result.task_id}
                          </span>
                          <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">
                            {modelCount}{' '}
                            {modelCount === 1 ? t('generation.results.response') : t('generation.results.responses')}
                          </span>
                        </div>
                        <p className="mt-1 line-clamp-2 text-sm text-zinc-700 dark:text-zinc-300">
                          {getTaskPreview(result.task_data)}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Expanded Content */}
                {isExpanded && (
                  <div className="border-t border-zinc-200 dark:border-zinc-700">
                    {/* Task Data */}
                    <div className="bg-zinc-50 p-4 dark:bg-zinc-800/50">
                      <div className="mb-2 flex items-center justify-between">
                        <h4 className="flex items-center space-x-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
                          <DocumentTextIcon className="h-4 w-4" />
                          <span>{t('generation.results.taskData')}</span>
                        </h4>
                        <Button
                          variant="text"
                          onClick={(e) => {
                            e.stopPropagation()
                            copyToClipboard(
                              JSON.stringify(result.task_data, null, 2)
                            )
                          }}
                        >
                          <ClipboardDocumentIcon className="h-4 w-4" />
                        </Button>
                      </div>
                      <pre className="overflow-x-auto rounded-md border border-zinc-200 bg-white p-3 text-xs text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300">
                        {JSON.stringify(result.task_data, null, 2)}
                      </pre>
                    </div>

                    {/* Model Responses */}
                    <div className="p-4">
                      <h4 className="mb-3 flex items-center space-x-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
                        <SparklesIcon className="h-4 w-4" />
                        <span>{t('generation.results.modelResponses')}</span>
                      </h4>

                      <div className="space-y-3">
                        {Object.entries(result.responses).map(
                          ([model, response]) => (
                            <div
                              key={model}
                              className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-700"
                            >
                              <div className="mb-2 flex items-center justify-between">
                                <div className="flex items-center space-x-2">
                                  <CpuChipIcon className="h-4 w-4 text-emerald-500" />
                                  <span className="font-medium text-zinc-900 dark:text-white">
                                    {model}
                                  </span>
                                </div>
                                <Button
                                  variant="text"
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    copyToClipboard(response.response_content)
                                  }}
                                >
                                  <ClipboardDocumentIcon className="h-4 w-4" />
                                </Button>
                              </div>
                              <div className="rounded-md bg-zinc-50 p-3 dark:bg-zinc-800/50">
                                <pre className="whitespace-pre-wrap text-sm text-zinc-700 dark:text-zinc-300">
                                  {response.response_content}
                                </pre>
                              </div>
                              <div className="mt-2 text-xs text-zinc-500">
                                {t('generation.results.generated')}{' '}
                                {formatDistanceToNow(
                                  new Date(response.created_at),
                                  {
                                    addSuffix: true,
                                  }
                                )}
                              </div>
                            </div>
                          )
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </Card>
            )
          })}
        </div>
      ) : (
        <Card className="p-8 text-center">
          <SparklesIcon className="mx-auto mb-4 h-12 w-12 text-zinc-300 dark:text-zinc-700" />
          <p className="text-zinc-600 dark:text-zinc-400">
            {searchQuery || selectedModel !== 'all'
              ? t('generation.results.noMatchingResults')
              : t('generation.results.noResultsYet')}
          </p>
          <p className="mt-2 text-sm text-zinc-500">
            {t('generation.results.generateFirst')}
          </p>
        </Card>
      )}
    </div>
  )
}
