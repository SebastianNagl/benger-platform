'use client'

import { Button } from '@/components/shared/Button'
import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import { logger } from '@/lib/utils/logger'
import { Pagination } from '@/components/shared/Pagination'
import { SearchInput } from '@/components/shared/SearchInput'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/shared/Select'
import { useAuth } from '@/contexts/AuthContext'
import { apiClient, getApiUrl } from '@/lib/api/client'
import { Project } from '@/types/labelStudio'
import { canStartGeneration } from '@/utils/permissions'
import {
  ArrowPathIcon,
  CheckCircleIcon,
  ClockIcon,
  PlayIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline'
import { useCallback, useEffect, useRef, useState } from 'react'
import { GenerationControlModal } from './GenerationControlModal'
import { GenerationResultModal } from './GenerationResultModal'

interface TaskGenerationStatus {
  task_id: string
  model_id: string
  structure_key: string | null
  status: string | null
  generation_id: string | null
  generated_at: string | null
  error_message: string | null
  result_preview: string | null
}

interface TaskWithGenerationStatus {
  id: string
  data: Record<string, any>
  meta?: Record<string, any>
  created_at: string
  generation_status: Record<string, TaskGenerationStatus[]> // model_id -> array of statuses (one per structure)
}

interface PaginatedTaskGenerationResponse {
  tasks: TaskWithGenerationStatus[]
  total: number
  page: number
  page_size: number
  total_pages: number
  models: string[]
  structures: string[]
}

interface GenerationTaskListProps {
  projectId: string
}

// Helper function to get aggregate status for a model (across all structures)
function getAggregateStatus(
  modelStatuses: TaskGenerationStatus[] | TaskGenerationStatus | undefined
): { status: string | null; hasResults: boolean } {
  if (!modelStatuses) {
    return { status: null, hasResults: false }
  }

  const statusArray = Array.isArray(modelStatuses)
    ? modelStatuses
    : [modelStatuses]

  if (statusArray.length === 0) {
    return { status: null, hasResults: false }
  }

  const hasResults = statusArray.some(
    (s) => s.status === 'completed' || s.status === 'failed'
  )

  const hasCompleted = statusArray.some((s) => s.status === 'completed')
  const hasRunning = statusArray.some(
    (s) => s.status === 'running' || s.status === 'pending'
  )
  const hasFailed = statusArray.some((s) => s.status === 'failed')

  if (hasCompleted) return { status: 'completed', hasResults }
  if (hasRunning) return { status: 'running', hasResults }
  if (hasFailed) return { status: 'failed', hasResults }
  return { status: null, hasResults }
}

export function GenerationTaskList({ projectId }: GenerationTaskListProps) {
  const { t } = useI18n()
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState<PaginatedTaskGenerationResponse | null>(null)
  const [project, setProject] = useState<Project | null>(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<string | null>(null)
  const [showControlModal, setShowControlModal] = useState(false)
  const [showResultModal, setShowResultModal] = useState(false)
  const [selectedTaskModel, setSelectedTaskModel] = useState<{
    taskId: string
    modelId: string
  } | null>(null)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [generatingCell, setGeneratingCell] = useState<{
    taskId: string
    modelId: string
  } | null>(null)
  const [contextMenu, setContextMenu] = useState<{
    x: number
    y: number
    taskId: string
    modelId: string
    status: string | null
    hasResults: boolean
  } | null>(null)
  const { user } = useAuth()
  const { addToast } = useToast()
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const fetchDataRef = useRef<() => void>(() => {})

  // Use refs for filter params so fetchData has a stable identity
  const pageRef = useRef(page)
  const pageSizeRef = useRef(pageSize)
  const searchRef = useRef(search)
  const statusFilterRef = useRef(statusFilter)
  pageRef.current = page
  pageSizeRef.current = pageSize
  searchRef.current = search
  statusFilterRef.current = statusFilter

  const fetchProjectData = useCallback(async () => {
    if (!projectId) return
    try {
      const projectData = await apiClient.get(`/projects/${projectId}`)
      setProject(projectData)
    } catch (error) {
      console.error('[GenerationTaskList] Failed to fetch project data:', error)
    }
  }, [projectId])

  // Stable fetchData - reads filter params from refs, only changes when projectId changes
  const fetchData = useCallback(async () => {
    try {
      logger.debug(
        '[GenerationTaskList] fetchData called for projectId:',
        projectId
      )
      const params = new URLSearchParams({
        page: pageRef.current.toString(),
        page_size: pageSizeRef.current.toString(),
      })

      if (searchRef.current) params.append('search', searchRef.current)
      if (statusFilterRef.current)
        params.append('status_filter', statusFilterRef.current)

      const url = `/generation-tasks/projects/${projectId}/task-status?${params}`
      logger.debug('[GenerationTaskList] Fetching from:', url)

      const responseData = await apiClient.get(url)
      logger.debug('[GenerationTaskList] Received data:', responseData)
      setData(responseData)
      setFetchError(null)
    } catch (error: any) {
      console.error(
        '[GenerationTaskList] Failed to fetch task generation status:',
        error
      )
      setFetchError(error.message || t('generation.taskList.loadError'))
    } finally {
      setLoading(false)
    }
  }, [projectId])

  // Fetch on mount, projectId change, and filter changes
  useEffect(() => {
    fetchData()
  }, [fetchData, page, pageSize, search, statusFilter])

  // Fetch project data when projectId changes
  useEffect(() => {
    fetchProjectData()
  }, [fetchProjectData])

  // Keep fetchDataRef updated to avoid stale closures in WebSocket handler
  useEffect(() => {
    fetchDataRef.current = fetchData
  }, [fetchData])

  // Connect to WebSocket for real-time updates
  useEffect(() => {
    let mounted = true

    const connectWebSocket = () => {
      if (!mounted) return
      try {
        // Get WebSocket URL from API URL
        const apiUrl = getApiUrl()
        const wsProtocol = apiUrl.startsWith('https') ? 'wss' : 'ws'
        const wsHost = apiUrl.replace(/^https?:\/\//, '')
        const wsUrl = `${wsProtocol}://${wsHost}/api/ws/projects/${projectId}/generation-progress`

        logger.debug('Connecting to WebSocket for generation status:', wsUrl)

        const ws = new WebSocket(wsUrl)
        wsRef.current = ws

        ws.onopen = () => {
          logger.debug('WebSocket connected for generation status')
          reconnectAttemptsRef.current = 0
        }

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data)
            logger.debug('WebSocket message for status update:', data)

            // Handle generation status updates - refresh on any non-connection message
            // Backend sends: 'connection' (initial), 'progress' (updates), or forwarded Redis messages
            if (data.type !== 'connection') {
              // Refresh data when we get an update (use ref to avoid stale closure)
              fetchDataRef.current()
            }
          } catch (error) {
            console.error('Failed to parse WebSocket message:', error)
          }
        }

        ws.onerror = (error) => {
          console.error('WebSocket error:', error)
        }

        ws.onclose = () => {
          logger.debug('WebSocket disconnected')

          // Attempt to reconnect with exponential backoff (only if still mounted)
          if (mounted && reconnectAttemptsRef.current < 5) {
            const timeout = Math.min(
              1000 * Math.pow(2, reconnectAttemptsRef.current),
              30000
            )
            reconnectTimeoutRef.current = setTimeout(() => {
              reconnectAttemptsRef.current++
              connectWebSocket()
            }, timeout)
          }
        }
      } catch (error) {
        console.error('Failed to connect WebSocket:', error)
      }
    }

    connectWebSocket()

    // Cleanup on unmount
    return () => {
      mounted = false
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [projectId]) // fetchData accessed via ref to avoid stale closure

  const getStatusIcon = (status: string | null) => {
    switch (status) {
      case 'completed':
        return <CheckCircleIcon className="h-5 w-5 text-green-600" />
      case 'failed':
        return <XCircleIcon className="h-5 w-5 text-red-600" />
      case 'running':
      case 'pending':
        return <ClockIcon className="h-5 w-5 animate-pulse text-yellow-600" />
      default:
        return <XCircleIcon className="h-5 w-5 text-gray-400" />
    }
  }

  const handleCellGenerate = useCallback(
    async (taskId: string, modelId: string, selectedStructureKeys?: string[]) => {
      if (!project) return
      setGeneratingCell({ taskId, modelId })
      try {
        const generationConfig = project.generation_config || ({} as any)
        const promptStructures = generationConfig.prompt_structures || {}
        const allKeys = Object.keys(promptStructures)
        const keysToUse = selectedStructureKeys || allKeys

        const requestBody: Record<string, any> = {
          mode: 'single',
          model_ids: [modelId],
          task_ids: [taskId],
        }
        if (keysToUse.length > 0) {
          requestBody.structure_keys = keysToUse
        }

        await apiClient.post(
          `/generation-tasks/projects/${projectId}/generate`,
          requestBody
        )
        addToast(t('generation.taskList.cellGenerationQueued'), 'success')
        fetchData()
      } catch (error: any) {
        addToast(
          error.response?.data?.detail ||
            t('generation.taskList.cellGenerationFailed'),
          'error'
        )
      } finally {
        setGeneratingCell(null)
      }
    },
    [project, projectId, fetchData, addToast, t]
  )

  // Close context menu on outside click
  useEffect(() => {
    if (!contextMenu) return
    const handleClick = () => setContextMenu(null)
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [contextMenu])

  const getFirstDataField = (data: Record<string, any>) => {
    // Get first meaningful text field from task data
    const textFields = ['text', 'question', 'content', 'title', 'input']
    for (const field of textFields) {
      if (data[field]) {
        const text = String(data[field])
        return text.length > 100 ? text.substring(0, 100) + '...' : text
      }
    }
    // Fallback to first string value
    const firstString = Object.values(data).find((v) => typeof v === 'string')
    if (firstString) {
      const text = String(firstString)
      return text.length > 100 ? text.substring(0, 100) + '...' : text
    }
    return t('generation.taskList.noTextData')
  }

  if (loading && !data) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-12 w-12 animate-spin rounded-full border-b-2 border-blue-600"></div>
      </div>
    )
  }

  if (fetchError && !data) {
    return (
      <div className="py-12 text-center">
        <p className="text-red-600 dark:text-red-400">{t('generation.taskList.loadError')}</p>
        <p className="mt-2 text-sm text-gray-400">{fetchError}</p>
        <Button variant="outline" onClick={() => fetchData()} className="mt-4">
          {t('common.retry')}
        </Button>
      </div>
    )
  }

  if (!data || data.models.length === 0) {
    return (
      <div className="py-12 text-center">
        <p className="text-gray-500">{t('generation.taskList.noModels')}</p>
        <p className="mt-2 text-sm text-gray-400">
          {t('generation.taskList.configureFirst')}
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Header with controls */}
      <div className="mb-4 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:space-x-4">
          <SearchInput
            value={search}
            onChange={setSearch}
            placeholder={t('generation.taskList.searchPlaceholder')}
            className="w-full sm:w-auto"
          />
          <Select
            value={statusFilter || ''}
            onValueChange={(v) => setStatusFilter(v || null)}
          >
            <SelectTrigger className="sm:w-44">
              <SelectValue placeholder={t('generation.taskList.allStatuses')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="">{t('generation.taskList.allStatuses')}</SelectItem>
              <SelectItem value="completed">{t('generation.taskList.completed')}</SelectItem>
              <SelectItem value="failed">{t('generation.taskList.failed')}</SelectItem>
              <SelectItem value="running">{t('generation.taskList.running')}</SelectItem>
              <SelectItem value="pending">{t('generation.taskList.pending')}</SelectItem>
              <SelectItem value="not_generated">{t('generation.taskList.notGenerated')}</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {canStartGeneration(user) && (
          <Button
            variant="filled"
            onClick={() => setShowControlModal(true)}
            className="w-full sm:w-auto"
          >
            {t('generation.taskList.startGeneration')}
          </Button>
        )}
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                {t('generation.taskList.task')}
              </th>
              {data.models.map((model) => (
                <th
                  key={model}
                  className="px-6 py-3 text-center text-xs font-medium uppercase tracking-wider text-gray-500"
                >
                  {model}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200 bg-white">
            {data.tasks.map((task) => (
              <tr key={task.id} className="hover:bg-gray-50">
                <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-900">
                  <div className="max-w-xs truncate">
                    {getFirstDataField(task.data)}
                  </div>
                  <div className="mt-1 text-xs text-gray-500">
                    ID: {task.id.substring(0, 8)}...
                  </div>
                </td>
                {data.models.map((model) => {
                  const rawStatuses = task.generation_status[model]
                  // Handle both array and object formats
                  const modelStatuses = !rawStatuses
                    ? []
                    : Array.isArray(rawStatuses)
                      ? rawStatuses
                      : [rawStatuses]
                  const { status, hasResults } =
                    getAggregateStatus(modelStatuses)

                  // Build tooltip showing status of each structure
                  const structureCount = modelStatuses.length
                  const completedCount = modelStatuses.filter(
                    (s) => s.status === 'completed'
                  ).length
                  const runningCount = modelStatuses.filter(
                    (s) => s.status === 'running' || s.status === 'pending'
                  ).length
                  const failedCount = modelStatuses.filter(
                    (s) => s.status === 'failed'
                  ).length

                  let tooltip = ''
                  if (structureCount > 0) {
                    tooltip = t('generation.taskList.tooltipStats', { completed: completedCount, running: runningCount, failed: failedCount })
                    if (hasResults) {
                      tooltip += ' - ' + t('generation.taskList.clickToView')
                    }
                  } else {
                    tooltip = t('generation.taskList.notYetGenerated')
                  }

                  const isGenerating =
                    generatingCell?.taskId === task.id &&
                    generatingCell?.modelId === model
                  const isRunningOrPending =
                    status === 'running' || status === 'pending'
                  const canGenerate =
                    canStartGeneration(user) &&
                    !isRunningOrPending &&
                    !isGenerating

                  return (
                    <td
                      key={model}
                      className="relative whitespace-nowrap px-6 py-4 text-center"
                      onContextMenu={(e) => {
                        if (!canStartGeneration(user)) return
                        e.preventDefault()
                        setContextMenu({
                          x: e.clientX,
                          y: e.clientY,
                          taskId: task.id,
                          modelId: model,
                          status,
                          hasResults,
                        })
                      }}
                    >
                      <button
                        onClick={() => {
                          setSelectedTaskModel({
                            taskId: task.id,
                            modelId: model,
                          })
                          setShowResultModal(true)
                        }}
                        className="inline-flex cursor-pointer items-center justify-center transition-transform hover:scale-110"
                        title={tooltip}
                      >
                        {isGenerating ? (
                          <div className="h-5 w-5 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
                        ) : (
                          getStatusIcon(status)
                        )}
                      </button>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {data.total > 0 && (
        <div className="mt-4">
          <Pagination
            currentPage={page}
            totalPages={data.total_pages}
            totalItems={data.total}
            pageSize={pageSize}
            onPageChange={setPage}
            onPageSizeChange={(newPageSize) => {
              setPageSize(newPageSize)
              setPage(1) // Reset to first page when changing page size
            }}
            pageSizeOptions={[25, 50, 100]}
          />
        </div>
      )}

      {/* Modals */}
      {showControlModal && (
        <GenerationControlModal
          isOpen={showControlModal}
          projectId={projectId}
          models={data.models}
          project={project || undefined}
          onClose={() => setShowControlModal(false)}
          onSuccess={() => {
            setShowControlModal(false)
            fetchData()
          }}
        />
      )}

      {showResultModal && selectedTaskModel && (
        <GenerationResultModal
          isOpen={showResultModal}
          taskId={selectedTaskModel.taskId}
          modelId={selectedTaskModel.modelId}
          onClose={() => {
            setShowResultModal(false)
            setSelectedTaskModel(null)
          }}
          onRegenerate={
            canStartGeneration(user) ? handleCellGenerate : undefined
          }
          availableStructureKeys={Object.keys(project?.generation_config?.prompt_structures || {})}
        />
      )}

      {/* Context menu for cell actions */}
      {contextMenu && (
        <div
          className="fixed z-50 min-w-[160px] rounded-lg bg-white py-1 shadow-lg ring-1 ring-black ring-opacity-5"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onMouseDown={(e) => e.stopPropagation()}
        >
          {contextMenu.hasResults && (
            <button
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-gray-700 hover:bg-gray-100"
              onClick={() => {
                setSelectedTaskModel({
                  taskId: contextMenu.taskId,
                  modelId: contextMenu.modelId,
                })
                setShowResultModal(true)
                setContextMenu(null)
              }}
            >
              <CheckCircleIcon className="h-4 w-4" />
              {t('generation.taskList.viewResults')}
            </button>
          )}
          {contextMenu.status !== 'running' &&
            contextMenu.status !== 'pending' && (
              <button
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-gray-700 hover:bg-gray-100"
                onClick={() => {
                  handleCellGenerate(contextMenu.taskId, contextMenu.modelId)
                  setContextMenu(null)
                }}
              >
                {contextMenu.status === null ? (
                  <>
                    <PlayIcon className="h-4 w-4" />
                    {t('generation.taskList.generate')}
                  </>
                ) : (
                  <>
                    <ArrowPathIcon className="h-4 w-4" />
                    {t('generation.taskList.regenerate')}
                  </>
                )}
              </button>
            )}
        </div>
      )}
    </div>
  )
}
