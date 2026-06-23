/**
 * useResultsData — consolidates the effect-driven data-fetch units of
 * EvaluationResults into two cohesive hooks:
 *
 *  - `useResultsData`: the project evaluation results fetch
 *    (`getProjectEvaluationResults`) — the initial fetch, the 5 s poll
 *    while any run is in-flight, and the `refetch` callback used by
 *    manual refresh / InflightRunsBanner / re-evaluate.
 *  - `useTaskModelData`: the per-task/model data fetch
 *    (`getProjectResultsByTaskModel`) plus the WebSocket-primary /
 *    5 s-polling-fallback live cell updates. Kept separate because its
 *    inputs (selected metric run ids, in-flight flag) are derived from
 *    `results` + the metric-selection UI state that lives in the
 *    component — splitting avoids a render-ordering cycle.
 *
 * UI-only state (showHistory, selected metric, modal open/tab, etc.)
 * stays in the component and is passed in as inputs.
 *
 * Extracted verbatim from EvaluationResults.tsx — behavior preserved.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { apiClient } from '@/lib/api/client'
import { redirectToLoginAsExpired } from '@/lib/auth/sessionExpired'

import type { ProjectEvaluationResults, TaskModelData } from './types'

interface UseResultsDataParams {
  projectId: string | number
  /** Key to trigger re-fetch when parent data changes */
  refreshKey?: number
  /** Include all runs in display filtering (does not change the API fetch). */
  showHistory: boolean
  /** Translated fallback message for a failed results load. */
  failedLoadMessage: string
}

export interface UseResultsDataResult {
  results: ProjectEvaluationResults | null
  loading: boolean
  error: string | null
  /** Raw re-fetch of project evaluation results (no loading flip). */
  refetch: () => Promise<void>
  /** Exposed so manual-refresh / re-evaluate can flip the spinner. */
  setLoading: React.Dispatch<React.SetStateAction<boolean>>
}

export function useResultsData({
  projectId,
  refreshKey,
  showHistory,
  failedLoadMessage,
}: UseResultsDataParams): UseResultsDataResult {
  const [loading, setLoading] = useState(true)
  const [results, setResults] = useState<ProjectEvaluationResults | null>(null)
  const [error, setError] = useState<string | null>(null)

  const fetchResults = useCallback(async () => {
    try {
      // Always fetch all runs so the metric selector can list all completed metrics.
      // showHistory controls display filtering, not the API fetch.
      const displayData = await apiClient.getProjectEvaluationResults(
        String(projectId),
        false
      )
      setResults(displayData)
      setError(null)
    } catch (err: any) {
      console.error('Failed to fetch evaluation results:', err)
      setError(err?.message || failedLoadMessage)
    } finally {
      setLoading(false)
    }
  }, [projectId, showHistory]) // eslint-disable-line react-hooks/exhaustive-deps

  // Initial fetch and refresh when parent signals data change
  useEffect(() => {
    fetchResults()
  }, [fetchResults, refreshKey])

  // Poll for running evaluations
  useEffect(() => {
    const hasRunningEval = results?.evaluations?.some(
      (e) => e.status === 'running' || e.status === 'pending'
    )

    if (hasRunningEval) {
      const interval = setInterval(fetchResults, 5000)
      return () => clearInterval(interval)
    }
  }, [results, fetchResults])

  return {
    results,
    loading,
    error,
    refetch: fetchResults,
    setLoading,
  }
}

interface UseTaskModelDataParams {
  projectId: string | number
  /** Include all runs in the per-task/model fetch (display filtering). */
  showHistory: boolean
  /** Comma-joined run ids for the selected metric (stable primitive dep). */
  selectedRunIdsKey: string
  /** Selected metric name sent to the per-task/model endpoint. */
  selectedMetricKey: string
  /** Whether the selected run is still pending/running (drives WS+poll). */
  hasInflightSelectedRun: boolean
}

export interface UseTaskModelDataResult {
  taskModelData: TaskModelData | null
  taskModelLoading: boolean
}

export function useTaskModelData({
  projectId,
  showHistory,
  selectedRunIdsKey,
  selectedMetricKey,
  hasInflightSelectedRun,
}: UseTaskModelDataParams): UseTaskModelDataResult {
  const [taskModelData, setTaskModelData] = useState<TaskModelData | null>(null)
  const [taskModelLoading, setTaskModelLoading] = useState(false)

  const fetchTaskModelDataRef = useRef<() => Promise<void>>(async () => {})

  useEffect(() => {
    let cancelled = false
    const fetchTaskModelData = async () => {
      if (!projectId) {
        if (!cancelled) setTaskModelData(null)
        return
      }

      // Initial fetch shows a loading state; subsequent refreshes don't,
      // so the table doesn't visibly flash on each tick.
      if (!taskModelData) setTaskModelLoading(true)
      try {
        const runIds = selectedRunIdsKey ? selectedRunIdsKey.split(',') : undefined
        const data = await apiClient.getProjectResultsByTaskModel(
          String(projectId),
          runIds,
          showHistory,
          selectedMetricKey || null,
        )
        if (!cancelled) setTaskModelData(data)
      } catch (err) {
        console.error('Failed to fetch task-model data:', err)
        if (!cancelled) setTaskModelData(null)
      } finally {
        if (!cancelled) setTaskModelLoading(false)
      }
    }
    fetchTaskModelDataRef.current = fetchTaskModelData
    fetchTaskModelData()

    return () => {
      cancelled = true
    }

    // intentionally excluded; otherwise the effect re-fires on every
    // setTaskModelData call and creates a fetch-loop.
  }, [projectId, selectedRunIdsKey, selectedMetricKey, showHistory]) // eslint-disable-line react-hooks/exhaustive-deps

  // WebSocket primary + 5 s polling fallback for live cell-by-cell updates.
  // Only opens while a selected run is in-flight; closes immediately when
  // the run finishes (saves backend connections + frontend timers).
  useEffect(() => {
    if (!projectId || !hasInflightSelectedRun) return

    let ws: WebSocket | null = null
    let reconnectAttempts = 0
    let reconnectTimeout: ReturnType<typeof setTimeout> | null = null
    let pollInterval: ReturnType<typeof setInterval> | null = null
    let closed = false

    const startPollingFallback = () => {
      if (pollInterval) return
      pollInterval = setInterval(() => {
        fetchTaskModelDataRef.current()
      }, 5000)
    }

    const connect = () => {
      try {
        const apiUrl =
          (typeof window !== 'undefined' &&
            (window as any).__BENGER_API_URL__) ||
          (typeof window !== 'undefined' ? window.location.origin : '')
        const wsProtocol = apiUrl.startsWith('https') ? 'wss' : 'ws'
        const wsHost = apiUrl.replace(/^https?:\/\//, '')
        const wsUrl = `${wsProtocol}://${wsHost}/api/ws/projects/${projectId}/evaluation-progress`
        ws = new WebSocket(wsUrl)

        ws.onopen = () => {
          reconnectAttempts = 0
          // Stop any polling fallback that was running before WS came up.
          if (pollInterval) {
            clearInterval(pollInterval)
            pollInterval = null
          }
        }

        ws.onmessage = (ev) => {
          try {
            const data = JSON.parse(ev.data)
            if (data.type === 'tick' || data.type === 'idle') {
              fetchTaskModelDataRef.current()
            }
          } catch {
            /* ignore malformed messages */
          }
        }

        ws.onerror = () => {
          // Let onclose handle reconnect/fallback so we don't double-fire.
        }

        ws.onclose = (ev) => {
          if (closed) return
          // 4401 / 4403 are application-defined close codes the backend
          // emits when the WS handshake fails auth (no/invalid token) or
          // access (no project membership). Reconnecting cannot fix these.
          // Fire the standard "session expired" UX: red toast + redirect to
          // /login (full reload, same flow used for HTTP 401). Bail out of
          // the WS connect/poll bookkeeping — the page is about to unmount.
          if (ev.code === 4401 || ev.code === 4403) {
            closed = true
            redirectToLoginAsExpired()
            return
          }
          // Exponential backoff up to 5 attempts, then drop to polling.
          if (reconnectAttempts < 5) {
            const delay = Math.min(1000 * 2 ** reconnectAttempts, 10000)
            reconnectAttempts += 1
            reconnectTimeout = setTimeout(connect, delay)
          } else {
            startPollingFallback()
          }
        }
      } catch {
        startPollingFallback()
      }
    }

    connect()

    return () => {
      closed = true
      if (ws) {
        try {
          ws.close()
        } catch {
          /* noop */
        }
      }
      if (reconnectTimeout) clearTimeout(reconnectTimeout)
      if (pollInterval) clearInterval(pollInterval)
    }
  }, [projectId, hasInflightSelectedRun])

  return { taskModelData, taskModelLoading }
}
