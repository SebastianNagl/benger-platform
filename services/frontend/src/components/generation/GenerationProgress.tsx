'use client'

import { Button } from '@/components/shared/Button'
import { logger } from '@/lib/utils/logger'
import { Card } from '@/components/shared/Card'
import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import { apiClient, getApiUrl } from '@/lib/api/client'
import {
  ArrowPathIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  PauseIcon,
  PlayIcon,
  StopIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline'
import { useEffect, useRef, useState } from 'react'

interface GenerationStatus {
  id: string
  model_id: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'stopped' | 'paused'
  progress?: number
  message?: string
}

interface GenerationProgressProps {
  projectId: string
  generationIds: string[]
  models: string[]
  onComplete: () => void
}

export function GenerationProgress({
  projectId,
  generationIds,
  models,
  onComplete,
}: GenerationProgressProps) {
  const { t } = useI18n()
  const { addToast } = useToast()
  // Initialize statuses using lazy initializer
  const [statuses, setStatuses] = useState<Record<string, GenerationStatus>>(() => {
    const initialStatuses: Record<string, GenerationStatus> = {}
    generationIds.forEach((id, index) => {
      initialStatuses[id] = {
        id,
        model_id: models[index],
        status: 'pending',
      }
    })
    return initialStatuses
  })
  const [isConnected, setIsConnected] = useState(false)
  const [connectionError, setConnectionError] = useState<string | null>(null)
  const [overallProgress, setOverallProgress] = useState(0)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const reconnectAttemptsRef = useRef(0)

  // Connect to WebSocket
  useEffect(() => {
    const connectWebSocket = () => {
      try {
        // Get WebSocket URL from API URL
        const apiUrl = getApiUrl()
        const wsProtocol = apiUrl.startsWith('https') ? 'wss' : 'ws'
        const wsHost = apiUrl.replace(/^https?:\/\//, '')
        const wsUrl = `${wsProtocol}://${wsHost}/ws/projects/${projectId}/generation-progress`

        logger.debug('Connecting to WebSocket:', wsUrl)

        const ws = new WebSocket(wsUrl)
        wsRef.current = ws

        ws.onopen = () => {
          logger.debug('WebSocket connected')
          setIsConnected(true)
          setConnectionError(null)
          reconnectAttemptsRef.current = 0
        }

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data)
            logger.debug('WebSocket message:', data)

            if (data.type === 'progress' && data.generations) {
              // Update statuses
              const newStatuses: Record<string, GenerationStatus> = {}
              data.generations.forEach((gen: any) => {
                newStatuses[gen.id] = {
                  id: gen.id,
                  model_id: gen.model_id,
                  status: gen.status,
                  progress: gen.progress,
                  message: gen.message,
                }
              })
              setStatuses(newStatuses)

              // Calculate overall progress
              const completed = data.generations.filter(
                (g: any) => g.status === 'completed'
              ).length
              const total = data.generations.length
              setOverallProgress((completed / total) * 100)
            }

            if (data.type === 'complete') {
              logger.debug('Generation complete')

              // Calculate success/failure counts for toast notification
              const completedCount = data.generations?.filter(
                (g: any) => g.status === 'completed'
              ).length || 0
              const failedCount = data.generations?.filter(
                (g: any) => g.status === 'failed'
              ).length || 0
              const totalCount = data.generations?.length || 0

              // Show appropriate completion toast
              if (failedCount === 0 && completedCount > 0) {
                addToast(
                  t('generation.success.allComplete', { count: completedCount }),
                  'success'
                )
              } else if (failedCount > 0) {
                addToast(
                  t('generation.success.completeWithFailures', {
                    completed: completedCount,
                    failed: failedCount,
                    total: totalCount,
                  }),
                  'warning'
                )
              }

              onComplete()
            }

            if (data.type === 'error') {
              console.error('WebSocket error:', data.message)
              addToast(data.message, 'error')
            }
          } catch (error) {
            console.error('Failed to parse WebSocket message:', error)
          }
        }

        ws.onerror = (error) => {
          console.error('WebSocket error:', error)
          setConnectionError(t('generation.connectionError'))
        }

        ws.onclose = () => {
          logger.debug('WebSocket disconnected')
          setIsConnected(false)
          wsRef.current = null

          // Attempt to reconnect with exponential backoff
          if (reconnectAttemptsRef.current < 5) {
            const delay = Math.min(
              1000 * Math.pow(2, reconnectAttemptsRef.current),
              10000
            )
            reconnectAttemptsRef.current++

            logger.debug(
              `Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current})`
            )
            reconnectTimeoutRef.current = setTimeout(() => {
              connectWebSocket()
            }, delay)
          } else {
            setConnectionError(t('generation.connectionFallback'))
            // Fall back to polling
            startPolling()
          }
        }
      } catch (error) {
        console.error('Failed to connect WebSocket:', error)
        setConnectionError(t('generation.connectionFailed'))
        // Fall back to polling
        startPolling()
      }
    }

    // Start polling as fallback
    const startPolling = () => {
      const pollInterval = setInterval(async () => {
        try {
          const data = await apiClient.get(
            `/projects/${projectId}/generation-status`
          )

          if (data.generations) {
            const newStatuses: Record<string, GenerationStatus> = {}
            data.generations.forEach((gen: any) => {
              newStatuses[gen.id] = {
                id: gen.id,
                model_id: gen.model_id,
                status: gen.status,
                progress: gen.progress,
                message: gen.error_message,
              }
            })
            setStatuses(newStatuses)

            // Calculate overall progress
            const completed = data.generations.filter((g: any) =>
              ['completed', 'failed', 'stopped'].includes(g.status)
            ).length
            const total = data.generations.length
            setOverallProgress((completed / total) * 100)

            // Check if all are complete
            if (!data.is_running) {
              clearInterval(pollInterval)
              onComplete()
            }
          }
        } catch (error) {
          console.error('Polling error:', error)
        }
      }, 2000)

      return () => clearInterval(pollInterval)
    }

    connectWebSocket()

    // Cleanup
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [projectId, onComplete, addToast, t])

  const stopGeneration = async (generationId: string) => {
    try {
      await apiClient.post(`/generation/${generationId}/stop`)
      addToast(t('generation.success.stopped'), 'success')

      // Update local status
      setStatuses((prev) => ({
        ...prev,
        [generationId]: {
          ...prev[generationId],
          status: 'stopped',
        },
      }))
    } catch (error: any) {
      addToast(
        error.response?.data?.detail || t('generation.errors.stopFailed'),
        'error'
      )
    }
  }

  const pauseGeneration = async (generationId: string) => {
    try {
      await apiClient.post(`/generation/${generationId}/pause`)
      addToast(t('generation.success.paused'), 'success')

      // Update local status
      setStatuses((prev) => ({
        ...prev,
        [generationId]: {
          ...prev[generationId],
          status: 'paused',
        },
      }))
    } catch (error: any) {
      addToast(
        error.response?.data?.detail || t('generation.errors.pauseFailed'),
        'error'
      )
    }
  }

  const resumeGeneration = async (generationId: string) => {
    try {
      await apiClient.post(`/generation/${generationId}/resume`)
      addToast(t('generation.success.resumed'), 'success')

      // Update local status
      setStatuses((prev) => ({
        ...prev,
        [generationId]: {
          ...prev[generationId],
          status: 'running',
        },
      }))
    } catch (error: any) {
      addToast(
        error.response?.data?.detail || t('generation.errors.resumeFailed'),
        'error'
      )
    }
  }

  const retryGeneration = async (generationId: string) => {
    try {
      await apiClient.post(`/generation/${generationId}/retry`)
      addToast(t('generation.retrying'), 'success')

      // Update local status
      setStatuses((prev) => ({
        ...prev,
        [generationId]: {
          ...prev[generationId],
          status: 'pending',
          message: undefined,
        },
      }))
    } catch (error: any) {
      addToast(
        error.response?.data?.detail || t('generation.errors.retryFailed'),
        'error'
      )
    }
  }

  // Bulk actions
  const pauseAll = async () => {
    const runningGenerations = Object.values(statuses).filter(
      (s) => s.status === 'running'
    )
    for (const gen of runningGenerations) {
      await pauseGeneration(gen.id)
    }
  }

  const resumeAll = async () => {
    const pausedGenerations = Object.values(statuses).filter(
      (s) => s.status === 'paused'
    )
    for (const gen of pausedGenerations) {
      await resumeGeneration(gen.id)
    }
  }

  const retryAllFailed = async () => {
    const failedGenerations = Object.values(statuses).filter(
      (s) => s.status === 'failed'
    )
    for (const gen of failedGenerations) {
      await retryGeneration(gen.id)
    }
  }

  const getStatusIcon = (status: GenerationStatus['status']) => {
    switch (status) {
      case 'pending':
        return <ArrowPathIcon className="h-5 w-5 animate-pulse text-zinc-400" />
      case 'running':
        return <ArrowPathIcon className="h-5 w-5 animate-spin text-blue-500" />
      case 'completed':
        return <CheckCircleIcon className="h-5 w-5 text-emerald-500" />
      case 'failed':
        return <XCircleIcon className="h-5 w-5 text-red-500" />
      case 'stopped':
        return <StopIcon className="h-5 w-5 text-amber-500" />
      case 'paused':
        return <PauseIcon className="h-5 w-5 text-indigo-500" />
      default:
        return null
    }
  }

  const getStatusColor = (status: GenerationStatus['status']) => {
    switch (status) {
      case 'pending':
        return 'bg-zinc-100 dark:bg-zinc-800'
      case 'running':
        return 'bg-blue-50 dark:bg-blue-900/20'
      case 'completed':
        return 'bg-emerald-50 dark:bg-emerald-900/20'
      case 'failed':
        return 'bg-red-50 dark:bg-red-900/20'
      case 'stopped':
        return 'bg-amber-50 dark:bg-amber-900/20'
      case 'paused':
        return 'bg-indigo-50 dark:bg-indigo-900/20'
      default:
        return 'bg-zinc-100 dark:bg-zinc-800'
    }
  }

  return (
    <div className="space-y-4">
      {/* Connection Status */}
      {connectionError && (
        <Card className="border-amber-200 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-900/20">
          <div className="flex items-center space-x-2">
            <ExclamationTriangleIcon className="h-5 w-5 text-amber-600 dark:text-amber-400" />
            <span className="text-sm text-amber-800 dark:text-amber-200">
              {connectionError}
            </span>
          </div>
        </Card>
      )}

      {/* Overall Progress */}
      <Card>
        <div className="p-6">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-lg font-medium">
              {t('generation.overallProgress')}
            </h3>
            <span className="text-sm text-zinc-600 dark:text-zinc-400">
              {Math.round(overallProgress)}%
            </span>
          </div>

          <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-700">
            <div
              className="h-full bg-gradient-to-r from-emerald-500 to-emerald-600 transition-all duration-500"
              style={{ width: `${overallProgress}%` }}
            />
          </div>

          <div className="mt-2 flex items-center justify-between text-xs text-zinc-500">
            <span>
              {t('generation.modelsCompleted', {
                completed: Object.values(statuses).filter(
                  (s) => s.status === 'completed'
                ).length,
                total: Object.keys(statuses).length,
              })}
            </span>
            {isConnected && (
              <span className="flex items-center space-x-1">
                <div className="h-2 w-2 rounded-full bg-emerald-500" />
                <span>{t('generation.liveUpdates')}</span>
              </span>
            )}
          </div>

          {/* Bulk Actions */}
          <div className="mt-4 flex space-x-2">
            {Object.values(statuses).some((s) => s.status === 'running') && (
              <Button variant="outline" onClick={pauseAll}>
                <PauseIcon className="mr-1 h-3 w-3" />
                {t('generation.pauseAll')}
              </Button>
            )}
            {Object.values(statuses).some((s) => s.status === 'paused') && (
              <Button variant="outline" onClick={resumeAll}>
                <PlayIcon className="mr-1 h-3 w-3" />
                {t('generation.resumeAll')}
              </Button>
            )}
            {Object.values(statuses).some((s) => s.status === 'failed') && (
              <Button variant="outline" onClick={retryAllFailed}>
                <ArrowPathIcon className="mr-1 h-3 w-3" />
                {t('generation.retryFailed')}
              </Button>
            )}
          </div>
        </div>
      </Card>

      {/* Individual Model Progress */}
      <div className="space-y-3">
        {Object.values(statuses).map((status) => (
          <Card
            key={status.id}
            className={`transition-all ${getStatusColor(status.status)}`}
          >
            <div className="p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  {getStatusIcon(status.status)}
                  <div>
                    <h4 className="font-medium text-zinc-900 dark:text-white">
                      {status.model_id}
                    </h4>
                    <p className="text-sm text-zinc-600 dark:text-zinc-400">
                      {status.status === 'running'
                        ? t('generation.generatingResponses')
                        : status.status === 'completed'
                          ? t('generation.generationComplete')
                          : status.status === 'failed'
                            ? status.message || t('generation.generationFailed')
                            : status.status === 'stopped'
                              ? t('generation.generationStopped')
                              : status.status === 'paused'
                                ? t('generation.generationPaused')
                                : t('generation.waitingToStart')}
                    </p>
                  </div>
                </div>

                <div className="flex space-x-2">
                  {status.status === 'running' && (
                    <>
                      <Button
                        variant="outline"
                        onClick={() => pauseGeneration(status.id)}
                        title={t('generation.buttons.pause')}
                      >
                        <PauseIcon className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => stopGeneration(status.id)}
                        title={t('generation.buttons.stop')}
                      >
                        <StopIcon className="h-4 w-4" />
                      </Button>
                    </>
                  )}
                  {status.status === 'paused' && (
                    <>
                      <Button
                        variant="outline"
                        onClick={() => resumeGeneration(status.id)}
                        title={t('generation.buttons.resume')}
                      >
                        <PlayIcon className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => stopGeneration(status.id)}
                        title={t('generation.buttons.stop')}
                      >
                        <StopIcon className="h-4 w-4" />
                      </Button>
                    </>
                  )}
                  {(status.status === 'failed' ||
                    status.status === 'stopped') && (
                    <Button
                      variant="outline"
                      onClick={() => retryGeneration(status.id)}
                      title={t('generation.buttons.retry')}
                    >
                      <ArrowPathIcon className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              </div>

              {status.progress !== undefined && status.status === 'running' && (
                <div className="mt-3">
                  <div className="h-1 w-full overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-700">
                    <div
                      className="h-full bg-blue-500 transition-all"
                      style={{ width: `${status.progress}%` }}
                    />
                  </div>
                </div>
              )}
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}
