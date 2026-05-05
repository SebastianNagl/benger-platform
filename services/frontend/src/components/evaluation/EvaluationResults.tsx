/**
 * Evaluation Results Component
 *
 * Displays results from evaluations with N:M field mapping.
 * Shows status, progress, and scores grouped by evaluation config.
 *
 * Phase 9 Feature: Results accessible on evaluations page.
 */

'use client'

import { Badge } from '@/components/shared/Badge'
import { Button } from '@/components/shared/Button'
import { Card } from '@/components/shared/Card'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'
import { useToast } from '@/components/shared/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { TaskDataViewModal } from '@/components/tasks/TaskDataViewModal'
import { canStartGeneration } from '@/utils/permissions'
import { apiClient } from '@/lib/api/client'
import { projectsAPI } from '@/lib/api/projects'
import { Task as LabelStudioTask } from '@/types/labelStudio'
import { Task } from '@/lib/api/types'
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/react'
import {
  ArrowDownTrayIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  ClockIcon,
  ClipboardDocumentIcon,
  ExclamationCircleIcon,
  PlayIcon,
  QueueListIcon,
  XCircleIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { METRIC_ORDER } from '@/lib/api/evaluation-types'
import { getMetricDetail } from '@/lib/extensions/metricRenderers'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/shared/Select'

/** Statistics data structure from computeStatistics API */
interface StatisticsData {
  by_model?: Record<
    string,
    {
      model_name?: string
      metrics: Record<
        string,
        {
          mean: number
          std: number
          se?: number
          ci_lower: number
          ci_upper: number
          n: number
        }
      >
      sample_count: number
    }
  >
}

/** Statistical methods that can be selected for display */
type StatisticalMethod =
  | 'ci'
  | 'se'
  | 'std'
  | 'ttest'
  | 'bootstrap'
  | 'cohens_d'
  | 'cliffs_delta'
  | 'correlation'

interface EvaluationResultsProps {
  projectId: string | number
  selectedModels?: string[]
  selectedMetrics?: string[]
  selectedEvalTypes?: ('automated' | 'llm-judge' | 'human')[]
  onRefresh?: () => void
  hasConfiguration?: boolean
  onRunEvaluation?: () => void
  isRunningEvaluation?: boolean
  onResultsLoaded?: (hasResults: boolean) => void
  onDataLoaded?: (data: ChartData[]) => void
  viewType?: 'data' | 'chart' // 'data' shows plain table, 'chart' shows progress bars
  /** Statistics data from computeStatistics API */
  statisticsData?: StatisticsData
  /** Selected statistical methods to display inline */
  selectedStatistics?: StatisticalMethod[]
  /** Key to trigger re-fetch when parent data changes */
  refreshKey?: number
  /** Model ID to display name map (for models not yet in evaluation results) */
  modelNames?: Record<string, string>
  /** Project evaluation configs for targeted re-evaluation */
  evaluationConfigs?: Array<{
    id: string
    metric: string
    display_name?: string
    metric_parameters?: Record<string, any>
    prediction_fields: string[]
    reference_fields: string[]
    enabled: boolean
  }>
}

// Data structure for chart visualization
export interface ChartData {
  model_id: string
  model_name?: string
  metrics: Record<string, number>
  samples_evaluated: number
}

interface EvaluationResult {
  evaluation_id: string
  model_id: string
  status: string
  created_at: string | null
  completed_at: string | null
  samples_evaluated: number
  sample_results_count: number
  error_message: string | null
  evaluation_configs: Array<{
    id: string
    metric: string
    display_name?: string
    metric_type?: string
    metric_parameters?: Record<string, any>
    prediction_fields: string[]
    reference_fields: string[]
    enabled: boolean
  }>
  results_by_config: Record<
    string,
    {
      field_results: Array<{
        combo_key: string
        prediction_field: string
        reference_field: string
        scores: Record<string, number>
      }>
      aggregate_score: number | null
    }
  >
  progress: {
    samples_passed: number
    samples_failed: number
    samples_skipped: number
  }
}

interface ProjectEvaluationResults {
  project_id: string
  evaluations: EvaluationResult[]
  total_count: number
}

export function EvaluationResults({
  projectId,
  selectedModels = [],
  selectedMetrics = [],
  selectedEvalTypes = ['automated', 'llm-judge', 'human'],
  onRefresh,
  hasConfiguration,
  onRunEvaluation,
  isRunningEvaluation = false,
  onResultsLoaded,
  onDataLoaded,
  viewType = 'chart',
  statisticsData,
  selectedStatistics = [],
  refreshKey,
  modelNames: externalModelNames = {},
  evaluationConfigs = [],
}: EvaluationResultsProps) {
  const { addToast } = useToast()
  const { user } = useAuth()
  const { t } = useI18n()
  const [loading, setLoading] = useState(true)
  const [results, setResults] = useState<ProjectEvaluationResults | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showHistory, setShowHistory] = useState(false)
  const [selectedMetricRunId, setSelectedMetricRunId] = useState<string | null>(null)
  const [exportDropdownOpen, setExportDropdownOpen] = useState(false)
  const exportDropdownRef = useRef<HTMLDivElement>(null)

  // Available metric methods — one entry per evaluation method (NOT per
  // EvaluationRun). Multiple runs of the same metric (e.g. dozens of
  // immediate-eval submissions) collapse into a single dropdown entry.
  // Selecting a method passes ALL matching run IDs to the by-task-model
  // endpoint, which already deduplicates to the latest result per
  // (generation_id, field_name) via row_number() OVER ... — so the user
  // sees the most recent score per cell across the entire metric history.
  // Sorted by the evaluation config order from the project page wizard.
  const availableMetricRuns = useMemo(() => {
    if (!results?.evaluations) return []

    // Include in-flight runs (`pending`, `running`) alongside `completed`
    // so the user can navigate to a metric the moment its run is
    // dispatched and watch rows fill in live, instead of waiting for the
    // whole run to finish before the dropdown surfaces it. Cells render
    // from `task_evaluations` rows directly — every committed row is
    // visible immediately, regardless of run status.
    const visible = results.evaluations
      .filter((e) =>
        e.status === 'completed' ||
        e.status === 'running' ||
        e.status === 'pending'
      )
      .filter((e) => {
        if (!selectedMetrics || selectedMetrics.length === 0) return true
        return e.evaluation_configs?.some((c: any) => selectedMetrics.includes(c.metric))
      })

    type MetricEntry = {
      id: string             // metric key (e.g. "llm_judge_falloesung")
      metric: string         // same as id
      configId: string
      displayName: string
      samplesEvaluated: number
      runIds: string[]
    }

    const byMetric = new Map<string, MetricEntry>()
    for (const e of visible) {
      // A single EvaluationRun may bundle multiple metrics (the API's
      // /run endpoint accepts multi-config requests, and the worker
      // dispatch accepts a list of configs). Walk EVERY config in the
      // run, not just the first — otherwise metrics 2..N silently
      // disappear from the dropdown even though their rows live in the
      // DB. The same run id then appears under each metric it ran.
      const cfgs =
        Array.isArray(e.evaluation_configs) && e.evaluation_configs.length > 0
          ? e.evaluation_configs
          : [{ metric: 'unknown', id: '', display_name: undefined } as any]
      for (const cfg of cfgs) {
        const metric = cfg?.metric || 'unknown'
        const existing = byMetric.get(metric)
        if (existing) {
          if (!existing.runIds.includes(e.evaluation_id)) {
            existing.runIds.push(e.evaluation_id)
          }
          existing.samplesEvaluated = Math.max(existing.samplesEvaluated, e.samples_evaluated || 0)
        } else {
          byMetric.set(metric, {
            id: metric,
            metric,
            configId: cfg?.id || '',
            displayName: cfg?.display_name || metric || 'Unknown',
            samplesEvaluated: e.samples_evaluated || 0,
            runIds: [e.evaluation_id],
          })
        }
      }
    }

    // Sort by GROUPED_METRICS order (same order as the evaluation wizard)
    const runs = Array.from(byMetric.values())
    const orderMap = new Map(METRIC_ORDER.map((m, i) => [m, i]))
    runs.sort((a, b) => {
      const orderA = orderMap.get(a.metric) ?? 999
      const orderB = orderMap.get(b.metric) ?? 999
      return orderA - orderB
    })

    return runs
  }, [results, selectedMetrics, evaluationConfigs])

  // Auto-select metric run — restore from localStorage or default to first
  useEffect(() => {
    if (availableMetricRuns.length === 0) return

    // If current selection is still valid, keep it
    if (selectedMetricRunId && availableMetricRuns.some((r) => r.id === selectedMetricRunId)) {
      return
    }

    // Try to restore from localStorage by metric name
    const savedMetric = localStorage.getItem(`eval-selected-metric-${projectId}`)
    if (savedMetric) {
      const match = availableMetricRuns.find((r) => r.metric === savedMetric)
      if (match) {
        setSelectedMetricRunId(match.id)
        return
      }
    }

    // Default to first
    setSelectedMetricRunId(availableMetricRuns[0].id)
  }, [availableMetricRuns, selectedMetricRunId])

  // Per-task/model data table state
  const [taskModelData, setTaskModelData] = useState<{
    evaluation_id: string
    models: string[]
    model_names: Record<string, string>
    tasks: Array<{
      task_id: string
      task_preview: string
      scores: Record<string, number>
      has_annotation?: boolean
      generation_models?: string[]
      annotator_columns?: string[]
    }>
    summary: Record<string, { avg: number; count: number; model_name: string }>
  } | null>(null)
  const [taskModelLoading, setTaskModelLoading] = useState(false)

  // Modal state for task data view
  const [taskModalOpen, setTaskModalOpen] = useState(false)
  const [selectedTask, setSelectedTask] = useState<Task | null>(null)
  const [taskLoading, setTaskLoading] = useState(false)

  // Modal state for generation and evaluation result view
  const [resultModalOpen, setResultModalOpen] = useState(false)
  const [resultModalTaskId, setResultModalTaskId] = useState<string | null>(null)
  const [resultModalModelId, setResultModalModelId] = useState<string | null>(null)
  // Generation results - array of results (one per structure key)
  const [generationData, setGenerationData] = useState<Array<{
    task_id: string
    model_id: string
    generation_id: string
    status: string
    result?: {
      generated_text?: string
      created_at?: string
      usage_stats?: Record<string, any>
      fields?: Record<string, any>
    }
    generated_at?: string
    generation_time_seconds?: number
    prompt_used?: string
    parameters?: Record<string, any>
    error_message?: string
    structure_key?: string
  }> | null>(null)
  const [evaluationData, setEvaluationData] = useState<{
    task_id: string
    model_id: string
    results: Array<{
      id: string
      evaluation_id: string
      field_name: string
      answer_type: string
      ground_truth: any
      prediction: any
      metrics: Record<string, any>
      passed: boolean
      confidence_score?: number
      error_message?: string
      processing_time_ms?: number
      created_at?: string
      evaluation_context?: {
        evaluation_type: string
        status: string
        eval_metadata?: Record<string, any>
      }
    }>
    total_count: number
    message?: string
  } | null>(null)
  const [annotationData, setAnnotationData] = useState<Array<{
    id: string
    task_id: number
    completed_by: string
    result: Array<{ value: any; from_name: string; to_name: string; type: string; [key: string]: any }>
    was_cancelled: boolean
    ground_truth: boolean
    lead_time?: number
    created_at: string
    updated_at?: string
    metadata?: Record<string, any>
  }> | null>(null)
  const [annotationLoading, setAnnotationLoading] = useState(false)
  const [generationLoading, setGenerationLoading] = useState(false)
  const [evaluationLoading, setEvaluationLoading] = useState(false)

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
      setError(err?.message || t('evaluation.multiFieldResults.failedLoadResults'))
    } finally {
      setLoading(false)
    }
  }, [projectId, showHistory])

  // Filter evaluations based on selected filters
  const filteredEvaluations =
    results?.evaluations?.filter((evaluation) => {
      // Filter by selected models
      if (selectedModels && selectedModels.length > 0) {
        if (!selectedModels.includes(evaluation.model_id)) {
          return false
        }
      }

      // Filter by eval types based on metrics in evaluation configs
      if (selectedEvalTypes && selectedEvalTypes.length > 0) {
        const evalConfigs = evaluation.evaluation_configs || []
        const evalHasSelectedType = evalConfigs.some((config) => {
          const metricName = config.metric || ''
          // LLM-Judge metrics: exact match or prefix (backend sends "llm_judge")
          const isLlmJudge =
            metricName === 'llm_judge' || metricName.startsWith('llm_judge_')

          if (selectedEvalTypes.includes('llm-judge') && isLlmJudge) {
            return true
          }
          if (selectedEvalTypes.includes('automated') && !isLlmJudge) {
            return true
          }
          // Human evaluations would have different structure - check for human type
          if (
            selectedEvalTypes.includes('human') &&
            config.metric_type === 'human'
          ) {
            return true
          }
          return false
        })

        // If no eval types matched and we have specific types selected, filter out
        if (!evalHasSelectedType && !selectedEvalTypes.includes('automated')) {
          return false
        }
      }
      return true
    }) || []

  // When showHistory is off, deduplicate to latest run per metric
  const displayEvaluations = useMemo(() => {
    if (showHistory) return filteredEvaluations
    const latestByMetric = new Map<string, typeof filteredEvaluations[0]>()
    for (const evaluation of filteredEvaluations) {
      const metric = evaluation.evaluation_configs?.[0]?.metric || 'unknown'
      const existing = latestByMetric.get(metric)
      if (!existing || (evaluation.created_at && existing.created_at && evaluation.created_at > existing.created_at)) {
        latestByMetric.set(metric, evaluation)
      }
    }
    return [...latestByMetric.values()]
  }, [filteredEvaluations, showHistory])

  // Close export dropdown on click outside
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (exportDropdownRef.current && !exportDropdownRef.current.contains(e.target as Node)) {
        setExportDropdownOpen(false)
      }
    }
    if (exportDropdownOpen) {
      document.addEventListener('mousedown', handleClick)
      return () => document.removeEventListener('mousedown', handleClick)
    }
  }, [exportDropdownOpen])

  // Initial fetch and refresh when parent signals data change
  useEffect(() => {
    fetchResults()
  }, [fetchResults, refreshKey])

  // Notify parent when results are loaded
  useEffect(() => {
    if (!loading && results) {
      const hasResults = (results.evaluations?.length ?? 0) > 0
      onResultsLoaded?.(hasResults)
    }
  }, [loading, results, onResultsLoaded])

  // Extract chart data when taskModelData is available (has correct model names)
  // This useEffect triggers after taskModelData is fetched, providing accurate per-model data
  useEffect(() => {
    if (!onDataLoaded) return

    // Get the latest completed evaluation to extract metric names
    const latestEval = results?.evaluations?.find(
      (e) => e.status === 'completed'
    )

    // Determine the primary metric name from evaluation configs
    // Backend uses preference: llm_judge_custom > score > overall_score
    let primaryMetricName = 'score'
    if (latestEval?.evaluation_configs) {
      const llmJudgeConfig = latestEval.evaluation_configs.find(
        (c) => c.metric === 'llm_judge_custom'
      )
      if (llmJudgeConfig) {
        primaryMetricName = 'llm_judge_custom'
      } else if (latestEval.evaluation_configs.length > 0) {
        // Use the first configured metric as the primary
        primaryMetricName = latestEval.evaluation_configs[0].metric
      }
    }

    // If we have taskModelData with summary, use it for chart data (preferred - has real model names)
    if (taskModelData?.summary && Object.keys(taskModelData.summary).length > 0) {
      const chartData: ChartData[] = Object.entries(taskModelData.summary).map(
        ([modelId, summaryData]) => ({
          model_id: modelId,
          model_name: summaryData.model_name || modelId,
          metrics: { [primaryMetricName]: summaryData.avg },
          samples_evaluated: summaryData.count,
        })
      )
      onDataLoaded(chartData)
      return
    }

    // Fallback: Extract from evaluation results if taskModelData not available yet
    if (!loading && results) {
      const hasResults = (results.evaluations?.length ?? 0) > 0
      if (hasResults && latestEval) {
        const chartData: ChartData[] = []
        const metrics: Record<string, number> = {}
        for (const [configId, configResult] of Object.entries(
          latestEval.results_by_config || {}
        )) {
          const config = latestEval.evaluation_configs?.find(
            (c) => c.id === configId
          )
          if (config && configResult.aggregate_score !== null) {
            metrics[config.metric] = configResult.aggregate_score
          }
        }
        if (Object.keys(metrics).length > 0) {
          chartData.push({
            model_id: latestEval.model_id && latestEval.model_id !== 'unknown' ? latestEval.model_id : 'All Models',
            metrics,
            samples_evaluated: latestEval.samples_evaluated || 0,
          })
        }
        onDataLoaded(chartData)
      }
    }
  }, [loading, results, taskModelData, onDataLoaded])

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

  // Fetch per-task/model data — filtered by ALL EvaluationRun IDs that
  // belong to the selected metric. The backend's row_number() OVER
  // (PARTITION BY generation_id, field_name ORDER BY created_at DESC)
  // collapses overlapping runs to the latest score per cell, so passing
  // every run for the metric is the safe aggregation primitive.
  //
  // Use a comma-joined string as the dep (stable primitive) instead of
  // the runIds array — array references would change on every render
  // and re-trigger the fetch in an infinite loop.
  const selectedRunIdsKey = availableMetricRuns
    .find(r => r.id === selectedMetricRunId)
    ?.runIds.join(',') ?? ''

  // The selected metric name is sent to the API so the backend can filter
  // rows when a run bundles multiple metrics. Without this, multiple
  // metric rows for the same (task, model) collapse during the loop's
  // dict assignment and only the last metric's score survives.
  const selectedMetricKey = availableMetricRuns
    .find(r => r.id === selectedMetricRunId)
    ?.metric ?? ''

  // The worker commits each TaskEvaluation row to Postgres immediately
  // after the evaluator returns (`db.commit()` per row), so an in-flight
  // run already has queryable rows. We stream cell-by-cell updates via
  // a WebSocket: the backend pushes a "tick" event when row counts or
  // run statuses change, and the frontend re-fetches the per-cell
  // view on each tick. WebSocket connection failures fall back to 5 s
  // polling — same UX, slightly higher latency. Pattern mirrors the
  // Generations page (`GenerationProgress.tsx:90-227`).
  const hasInflightSelectedRun = useMemo(() => {
    if (!results?.evaluations || !selectedRunIdsKey) return false
    const selectedSet = new Set(selectedRunIdsKey.split(','))
    return results.evaluations.some(
      (e) =>
        selectedSet.has(e.evaluation_id) &&
        (e.status === 'running' || e.status === 'pending')
    )
  }, [results, selectedRunIdsKey])

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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- taskModelData
    // intentionally excluded; otherwise the effect re-fires on every
    // setTaskModelData call and creates a fetch-loop.
  }, [projectId, selectedRunIdsKey, selectedMetricKey, showHistory])

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

        ws.onclose = () => {
          if (closed) return
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

  const handleRefresh = () => {
    setLoading(true)
    fetchResults()
    onRefresh?.()
  }

  // Handle task click to show task data modal
  const handleTaskClick = async (taskId: string) => {
    setTaskLoading(true)
    setTaskModalOpen(true)
    try {
      const task = await projectsAPI.getTask(taskId)
      // Cast to Task type expected by TaskDataViewModal
      // Both types have compatible 'data' property which is the main field used
      setSelectedTask(task as unknown as Task)
    } catch (err) {
      console.error('Failed to fetch task:', err)
      addToast(t('evaluation.multiFieldResults.failedLoadTaskData'), 'error')
    } finally {
      setTaskLoading(false)
    }
  }

  // Handle score cell click to show generation and evaluation result modal
  const handleScoreClick = async (taskId: string, modelId: string) => {
    const isAnnotatorCell = modelId.startsWith('annotator:')

    // Open modal and set context
    setResultModalOpen(true)
    setResultModalTaskId(taskId)
    setResultModalModelId(modelId)
    setAnnotationData(null)
    setGenerationData(null)
    setEvaluationData(null)
    setAnnotationLoading(true)
    setGenerationLoading(true)
    setEvaluationLoading(true)

    // Fetch annotations only for annotator cells
    if (isAnnotatorCell) {
      const annotatorUsername = modelId.split(':')[1]
      try {
        const annotations = await projectsAPI.getTaskAnnotations(
          taskId,
          true,
          annotatorUsername,
          !showHistory,
        )
        setAnnotationData(annotations || [])
      } catch (err) {
        console.error('Failed to fetch annotations:', err)
      } finally {
        setAnnotationLoading(false)
      }
    } else {
      setAnnotationData([])
      setAnnotationLoading(false)
    }

    // Fetch generation results only for model cells
    if (isAnnotatorCell) {
      setGenerationData([])
      setGenerationLoading(false)
    } else {
      try {
        const params = new URLSearchParams({ task_id: taskId, model_id: modelId })
        if (showHistory) {
          params.append('include_history', 'true')
        }
        const result = await apiClient.get(`/generation-tasks/generation-result?${params}`)
        setGenerationData(result.results || [])
      } catch (err) {
        console.error('Failed to fetch generation result:', err)
      } finally {
        setGenerationLoading(false)
      }
    }

    // Fetch per-task evaluation results
    try {
      const result = await apiClient.getTaskEvaluation(taskId, modelId, showHistory)
      setEvaluationData(result)
    } catch (err) {
      console.error('Failed to fetch evaluation sample result:', err)
    } finally {
      setEvaluationLoading(false)
    }
  }

  // Re-fetch modal data when showHistory toggles while modal is open
  useEffect(() => {
    if (resultModalOpen && resultModalTaskId && resultModalModelId) {
      handleScoreClick(resultModalTaskId, resultModalModelId)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showHistory])

  // Handle re-evaluate for a specific task x model cell
  const handleCellReEvaluate = useCallback(
    async (taskId: string, modelId: string, selectedConfigIds: string[]) => {
      if (!projectId || evaluationConfigs.length === 0) return

      const selectedConfigs = evaluationConfigs.filter(
        (c) => selectedConfigIds.includes(c.id) && c.enabled !== false
      )
      if (selectedConfigs.length === 0) {
        addToast(t('evaluation.multiFieldResults.reEvaluateFailed'), 'error')
        return
      }

      try {
        await apiClient.evaluations.runEvaluation({
          project_id: String(projectId),
          evaluation_configs: selectedConfigs,
          force_rerun: true,
          task_ids: [taskId],
          model_ids: [modelId],
        })

        addToast(t('evaluation.multiFieldResults.reEvaluateQueued'), 'success')

        // Refresh results after a delay to allow processing
        setTimeout(() => {
          setLoading(true)
          fetchResults()
        }, 2000)
      } catch (error: any) {
        addToast(
          error.message || t('evaluation.multiFieldResults.reEvaluateFailed'),
          'error'
        )
      }
    },
    [projectId, evaluationConfigs, addToast, t, fetchResults]
  )

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircleIcon className="h-5 w-5 text-green-500" />
      case 'running':
        return <ArrowPathIcon className="h-5 w-5 animate-spin text-blue-500" />
      case 'pending':
        return <ClockIcon className="h-5 w-5 text-yellow-500" />
      case 'failed':
        return <XCircleIcon className="h-5 w-5 text-red-500" />
      default:
        return <ExclamationCircleIcon className="h-5 w-5 text-gray-400" />
    }
  }

  const getStatusBadgeColor = (status: string) => {
    switch (status) {
      case 'completed':
        return 'green'
      case 'running':
        return 'blue'
      case 'pending':
        return 'yellow'
      case 'failed':
        return 'red'
      default:
        return 'gray'
    }
  }

  const formatTimeAgo = (dateStr: string | null) => {
    if (!dateStr) return t('evaluation.multiFieldResults.unknown')
    const date = new Date(dateStr)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)

    if (diffMins < 1) return t('evaluation.multiFieldResults.justNow')
    if (diffMins < 60) return t('evaluation.multiFieldResults.minutesAgo', { count: diffMins })
    const diffHours = Math.floor(diffMins / 60)
    if (diffHours < 24) return t('evaluation.multiFieldResults.hoursAgo', { count: diffHours })
    const diffDays = Math.floor(diffHours / 24)
    return t('evaluation.multiFieldResults.daysAgo', { count: diffDays })
  }

  // Academic formatting: 3 decimal places for 0-1 scores (ACL/NeurIPS standard)
  // Returns 'N/A' for null/undefined scores (e.g., failed evaluations)
  const formatScore = (score: number | null | undefined) => {
    if (score === null || score === undefined) {
      return 'N/A'
    }
    return score.toFixed(3)
  }

  // Format inline statistics based on selected methods
  const formatInlineStats = (
    modelId: string,
    metricName: string
  ): string | null => {
    if (!statisticsData?.by_model || selectedStatistics.length === 0) {
      return null
    }

    const modelStats = statisticsData.by_model[modelId]
    if (!modelStats?.metrics?.[metricName]) {
      return null
    }

    const stats = modelStats.metrics[metricName]
    const parts: string[] = []

    // Standard Error
    if (selectedStatistics.includes('se') && stats.se !== undefined) {
      parts.push(`±${stats.se.toFixed(3)}`)
    }

    // Standard Deviation
    if (selectedStatistics.includes('std') && stats.std !== undefined) {
      parts.push(`σ${stats.std.toFixed(3)}`)
    }

    // 95% Confidence Interval
    if (selectedStatistics.includes('ci') && stats.ci_lower !== undefined && stats.ci_upper !== undefined) {
      parts.push(`[${(stats.ci_lower * 100).toFixed(1)}%, ${(stats.ci_upper * 100).toFixed(1)}%]`)
    }

    return parts.length > 0 ? parts.join(' ') : null
  }

  // Get model statistics for display
  const getModelStats = (modelId: string, metricName: string) => {
    if (!statisticsData?.by_model) return null
    return statisticsData.by_model[modelId]?.metrics?.[metricName] || null
  }

  const getScoreBarWidth = (score: number) => {
    // Normalize score to 0-100 for bar width
    const normalized =
      score >= 0 && score <= 1
        ? score * 100
        : Math.min(100, Math.max(0, score * 100))
    return `${normalized}%`
  }

  const getMetricDisplayName = (
    configId: string,
    configs: EvaluationResult['evaluation_configs']
  ) => {
    const config = configs.find((c) => c.id === configId)
    if (!config) return configId

    if (config.display_name) return config.display_name

    // Format metric name
    let name = config.metric.replace(/_/g, ' ')
    name = name.charAt(0).toUpperCase() + name.slice(1)

    // Add parameters if present
    if (config.metric_parameters) {
      const params = Object.entries(config.metric_parameters)
        .map(([k, v]) => `${k}=${v}`)
        .join(', ')
      if (params) name += ` (${params})`
    }

    return name
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <LoadingSpinner />
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-900/20">
        <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
        <button
          onClick={handleRefresh}
          className="mt-2 text-sm font-medium text-red-600 hover:text-red-500 dark:text-red-400"
        >
          {t('evaluation.multiFieldResults.tryAgain')}
        </button>
      </div>
    )
  }

  // When not configured, return null and let the parent page handle the empty state
  if (hasConfiguration === false) {
    return null
  }

  // Check if we have no evaluation results at all
  if (!results?.evaluations || results.evaluations.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-emerald-300 p-8 text-center dark:border-emerald-700">
        <PlayIcon className="mx-auto h-12 w-12 text-emerald-500" />
        <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-gray-100">
          {t('evaluation.multiFieldResults.noResultsYet')}
        </h3>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          {t('evaluation.multiFieldResults.noResultsYetDesc')}
        </p>
        {onRunEvaluation && (
          <button
            onClick={onRunEvaluation}
            disabled={isRunningEvaluation}
            className="mt-4 inline-flex items-center gap-2 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isRunningEvaluation ? (
              <>
                <ArrowPathIcon className="h-4 w-4 animate-spin" />
                {t('evaluation.multiFieldResults.starting')}
              </>
            ) : (
              <>
                <PlayIcon className="h-4 w-4" />
                {t('evaluation.multiFieldResults.runEvaluationNow')}
              </>
            )}
          </button>
        )}
      </div>
    )
  }

  // Note: We don't early-return when filteredEvaluations.length === 0 because
  // the Per-Task table uses Generation.model_id which has correct per-model data
  // even when Evaluation.model_id = 'unknown' for evaluations

  return (
    <div className="space-y-4">
      {/* Header with metric selector, controls, and action buttons */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h3 className="text-lg font-medium text-gray-900 dark:text-white">
            {t('evaluation.multiFieldResults.title')}
          </h3>
          {/* Metric selector dropdown */}
          {availableMetricRuns.length > 0 && selectedMetricRunId && (() => {
            const selectedRun = availableMetricRuns.find((r) => r.id === selectedMetricRunId)
            // The previous label had `(${selectedRun.samplesEvaluated})` — but
            // that field is the run-level total samples_evaluated, which is
            // shared across every metric in a bundled multi-metric run. Every
            // metric ended up showing the same number (the run total),
            // misleading users into thinking each metric had been computed for
            // that many cells. Drop the count rather than show a wrong one.
            const displayText = selectedRun
              ? selectedRun.displayName
              : t('evaluation.multiFieldResults.selectMetric')
            return (
              <Select
                value={selectedMetricRunId}
                onValueChange={(v) => {
                  setSelectedMetricRunId(v)
                  // Persist selection by metric name for page refresh
                  const run = availableMetricRuns.find((r) => r.id === v)
                  if (run) localStorage.setItem(`eval-selected-metric-${projectId}`, run.metric)
                }}
                displayValue={displayText}
              >
                <SelectTrigger className="w-auto min-w-[200px]">
                  <SelectValue placeholder={t('evaluation.multiFieldResults.selectMetric')} />
                </SelectTrigger>
                <SelectContent>
                  {availableMetricRuns.map((run) => (
                    <SelectItem key={run.id} value={run.id}>
                      {run.displayName}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )
          })()}
          {/* Include history toggle */}
          <label className="flex cursor-pointer items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
            <input
              type="checkbox"
              checked={showHistory}
              onChange={(e) => setShowHistory(e.target.checked)}
              className="rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
            />
            {t('evaluation.multiFieldResults.includeHistory')}
          </label>
        </div>
        <div className="flex items-center gap-2">
          {/* Export dropdown */}
          {taskModelData && taskModelData.tasks.length > 0 && (() => {
            const doExport = (format: 'json' | 'csv') => {
              const displayModels = selectedModels?.length
                ? selectedModels
                : taskModelData.models
              const metricName = availableMetricRuns.find(r => r.id === selectedMetricRunId)?.displayName || 'evaluation'
              const fileName = `evaluation-${metricName.toLowerCase().replace(/\s+/g, '-')}`

              if (format === 'json') {
                const exportData = {
                  metric: metricName,
                  models: displayModels.map(mid => ({
                    id: mid,
                    name: taskModelData.model_names[mid] || mid,
                  })),
                  tasks: taskModelData.tasks.map(task => ({
                    task_id: task.task_id,
                    preview: task.task_preview,
                    scores: Object.fromEntries(
                      displayModels.map(mid => [
                        taskModelData.model_names[mid] || mid,
                        task.scores[mid] ?? null,
                      ])
                    ),
                  })),
                }
                const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
                const url = URL.createObjectURL(blob)
                const a = document.createElement('a')
                a.href = url
                a.download = `${fileName}.json`
                a.click()
                URL.revokeObjectURL(url)
              } else {
                const modelHeaders = displayModels.map(mid => taskModelData.model_names[mid] || mid)
                const header = ['task_id', 'preview', ...modelHeaders].join(',')
                const rows = taskModelData.tasks.map(task => {
                  const scores = displayModels.map(mid => task.scores[mid] ?? '')
                  return [task.task_id, `"${(task.task_preview || '').replace(/"/g, '""')}"`, ...scores].join(',')
                })
                const csv = [header, ...rows].join('\n')
                const blob = new Blob([csv], { type: 'text/csv' })
                const url = URL.createObjectURL(blob)
                const a = document.createElement('a')
                a.href = url
                a.download = `${fileName}.csv`
                a.click()
                URL.revokeObjectURL(url)
              }
              setExportDropdownOpen(false)
            }

            return (
              <div className="relative" ref={exportDropdownRef}>
                <Button
                  variant="outline"
                  onClick={() => setExportDropdownOpen(!exportDropdownOpen)}
                >
                  <ArrowDownTrayIcon className="h-4 w-4" />
                  {t('common.export') || 'Export'}
                </Button>
                {exportDropdownOpen && (
                  <div className="absolute right-0 z-50 mt-1 w-32 rounded-lg border border-gray-200 bg-white py-1 shadow-lg dark:border-gray-700 dark:bg-gray-800">
                    <button
                      type="button"
                      onClick={() => doExport('json')}
                      className="flex w-full items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 dark:text-gray-200 dark:hover:bg-gray-700"
                    >
                      <ArrowDownTrayIcon className="h-4 w-4" />
                      JSON
                    </button>
                    <button
                      type="button"
                      onClick={() => doExport('csv')}
                      className="flex w-full items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 dark:text-gray-200 dark:hover:bg-gray-700"
                    >
                      <ArrowDownTrayIcon className="h-4 w-4" />
                      CSV
                    </button>
                  </div>
                )}
              </div>
            )
          })()}
          {onRunEvaluation && (
            <Button
              variant="filled"
              onClick={onRunEvaluation}
              disabled={isRunningEvaluation}
            >
              {isRunningEvaluation ? (
                <>
                  <ArrowPathIcon className="h-4 w-4 animate-spin" />
                  {t('evaluation.multiFieldResults.running')}
                </>
              ) : (
                <>
                  <PlayIcon className="h-4 w-4" />
                  {t('evaluation.multiFieldResults.runNow')}
                </>
              )}
            </Button>
          )}
          <Button
            variant="outline"
            onClick={handleRefresh}
            disabled={loading}
          >
            <ArrowPathIcon
              className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`}
            />
            {t('evaluation.multiFieldResults.refresh')}
          </Button>
        </div>
      </div>

      {/* Per-Task/Model Data Table */}
      {viewType === 'data' &&
       taskModelData &&
       taskModelData.tasks.length > 0 &&
       // Hide table when user has explicitly deselected all metrics
       (selectedMetrics === undefined || selectedMetrics.length > 0) &&
       (() => {
        // Show selected models as columns, even if they have no results yet (will show "—")
        // Fall back to models from evaluation data if no filter is active
        const displayModels = selectedModels?.length
          ? selectedModels
          : taskModelData.models

        return (
        <Card className="overflow-hidden">
          <div className="border-b border-gray-200 bg-gray-50 px-4 py-3 dark:border-gray-700 dark:bg-gray-800">
            <h4 className="font-medium text-gray-900 dark:text-white">
              {t('evaluation.multiFieldResults.perTaskResults')}
            </h4>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {taskModelData.tasks.length} {t('common.tasks')} • {displayModels.length} {displayModels.length !== 1 ? t('common.models') : t('common.model')}
              {taskModelData.models.length > 0 && selectedModels?.length > 0 && taskModelData.models.length !== displayModels.length && ` (${taskModelData.models.length} ${t('evaluation.multiFieldResults.withResults')})`}
            </p>
          </div>
          {taskModelLoading ? (
            <div className="flex items-center justify-center py-8">
              <LoadingSpinner />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800/50">
                    <th className="sticky left-0 min-w-[200px] bg-gray-50 px-4 py-2 text-left font-medium text-gray-600 dark:bg-gray-800/50 dark:text-gray-300">
                      {t('evaluation.multiFieldResults.task')}
                    </th>
                    {displayModels.map((modelId) => {
                      const isAnnotator = modelId.startsWith('annotator:')
                      // For annotators, show just the username (strip "Annotator: " prefix and "annotator:" id prefix)
                      const displayName = isAnnotator
                        ? modelId.replace(/^annotator:/, '')
                        : (taskModelData.model_names[modelId] || externalModelNames[modelId] || modelId)
                      return (
                      <th
                        key={modelId}
                        className="min-w-[100px] px-4 py-2 text-right font-medium text-gray-600 dark:text-gray-300"
                      >
                        <div className="flex flex-col items-end">
                          <span className={`rounded px-2 py-0.5 text-xs ${
                            isAnnotator
                              ? 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200'
                              : 'bg-gray-200 dark:bg-gray-700'
                          }`}>
                            {displayName}
                          </span>
                        </div>
                      </th>
                      )
                    })}
                  </tr>
                </thead>
                <tbody>
                  {taskModelData.tasks.map((task, idx) => {
                    // Find best score for this task (only among displayed models)
                    const displayedScores = displayModels
                      .map((m) => task.scores[m])
                      .filter((s) => s !== undefined && s !== null)
                    const maxScore = displayedScores.length > 0 ? Math.max(...displayedScores) : null

                    return (
                      <tr
                        key={task.task_id}
                        className={`border-b border-gray-100 dark:border-gray-700 ${idx % 2 === 0 ? 'bg-white dark:bg-gray-900' : 'bg-gray-50 dark:bg-gray-800/30'}`}
                      >
                        <td className="sticky left-0 bg-inherit px-4 py-2 text-gray-700 dark:text-gray-300">
                          <div
                            className="max-w-[250px] truncate cursor-pointer hover:text-blue-600 dark:hover:text-blue-400 hover:underline"
                            title={`${task.task_preview} - ${t('evaluation.multiFieldResults.clickToViewTaskData')}`}
                            onClick={() => handleTaskClick(task.task_id)}
                          >
                            {task.task_preview || `${t('common.task')} ${task.task_id.slice(0, 8)}`}
                          </div>
                        </td>
                        {displayModels.map((modelId) => {
                          const score = task.scores[modelId]
                          const hasScore = score !== undefined && score !== null
                          const isBest = hasScore && score === maxScore && displayedScores.length > 1
                          const isAnnotatorModel = modelId.startsWith('annotator:')
                          // n/a is clickable when the underlying source data
                          // exists, even though no score is yet recorded:
                          //  - LLM model column: a generation by that model exists
                          //  - Annotator column: an annotation by that user exists
                          //    (case: human Korrektur metric where the answer
                          //     is present but not yet graded)
                          const hasClickableData = isAnnotatorModel
                            ? task.annotator_columns?.includes(modelId)
                            : task.generation_models?.includes(modelId)

                          return (
                            <td key={modelId} className="px-4 py-2 text-right">
                              {hasScore ? (
                                <span
                                  className={`font-mono font-medium cursor-pointer hover:underline ${isBest ? 'text-emerald-600 dark:text-emerald-400' : 'text-gray-900 dark:text-white'}`}
                                  title={t('evaluation.multiFieldResults.clickToViewResponse')}
                                  onClick={() => handleScoreClick(task.task_id, modelId)}
                                >
                                  {formatScore(score)}
                                </span>
                              ) : hasClickableData ? (
                                <span
                                  className="cursor-pointer text-blue-600 underline dark:text-blue-400"
                                  onClick={() => handleScoreClick(task.task_id, modelId)}
                                >
                                  n/a
                                </span>
                              ) : (
                                <span className="text-gray-400 dark:text-gray-500">n/a</span>
                              )}
                            </td>
                          )
                        })}
                      </tr>
                    )
                  })}
                  {/* Summary row */}
                  <tr className="border-t-2 border-gray-300 bg-gray-100 font-medium dark:border-gray-600 dark:bg-gray-800">
                    <td className="sticky left-0 bg-gray-100 px-4 py-2 text-gray-900 dark:bg-gray-800 dark:text-white">
                      {t('evaluation.multiFieldResults.average')}
                    </td>
                    {displayModels.map((modelId) => {
                      const summary = taskModelData.summary[modelId]
                      const hasAvg = summary?.avg !== undefined && summary?.avg !== null

                      // Find best average (only among displayed models)
                      const displayedAvgs = displayModels
                        .map((m) => taskModelData.summary[m]?.avg)
                        .filter((a) => a !== undefined && a !== null)
                      const maxAvg = displayedAvgs.length > 0 ? Math.max(...displayedAvgs) : null
                      const isBest = hasAvg && summary.avg === maxAvg && displayedAvgs.length > 1

                      // Get inline stats for the first available metric (Average is per-model aggregate)
                      const modelStats = statisticsData?.by_model?.[modelId]
                      const firstMetric = modelStats?.metrics ? Object.keys(modelStats.metrics)[0] : null
                      const inlineStats = firstMetric ? formatInlineStats(modelId, firstMetric) : null

                      return (
                        <td key={modelId} className="px-4 py-2 text-right">
                          {hasAvg ? (
                            <div className="flex flex-col items-end">
                              <span
                                className={`font-mono font-semibold ${isBest ? 'text-emerald-600 dark:text-emerald-400' : 'text-gray-900 dark:text-white'}`}
                              >
                                {formatScore(summary.avg)}
                              </span>
                              {inlineStats && (
                                <span className="text-xs font-normal text-gray-500 dark:text-gray-400">
                                  {inlineStats}
                                </span>
                              )}
                            </div>
                          ) : (
                            <span className="text-gray-400 dark:text-gray-500">n/a</span>
                          )}
                        </td>
                      )
                    })}
                  </tr>
                </tbody>
              </table>
            </div>
          )}
        </Card>
        )
      })()}

      {/* Evaluation cards - show in chart view */}
      {viewType !== 'data' &&
        displayEvaluations.map((evaluation) => (
          <Card key={evaluation.evaluation_id} className="overflow-hidden">
            {/* Evaluation header */}
            <div className="flex items-center justify-between border-b border-gray-200 bg-gray-50 px-4 py-3 dark:border-gray-700 dark:bg-gray-800">
              <div className="flex items-center gap-3">
                {getStatusIcon(evaluation.status)}
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-gray-900 dark:text-white">
                      {t('evaluation.multiFieldResults.evaluation')}
                    </span>
                    <Badge
                      variant={getStatusBadgeColor(evaluation.status) as any}
                    >
                      {evaluation.status}
                    </Badge>
                    {evaluation.model_id && evaluation.model_id !== 'unknown' && (
                      <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-500 dark:bg-gray-700 dark:text-gray-400">
                        {evaluation.model_id}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {evaluation.completed_at
                      ? t('evaluation.multiFieldResults.completedAgo', { time: formatTimeAgo(evaluation.completed_at) })
                      : t('evaluation.multiFieldResults.startedAgo', { time: formatTimeAgo(evaluation.created_at) })}
                  </p>
                </div>
              </div>
              <div className="text-right text-sm">
                <p className="text-gray-600 dark:text-gray-300">
                  {t('evaluation.multiFieldResults.samplesEvaluated', { count: evaluation.samples_evaluated })}
                </p>
                {evaluation.status === 'running' && (
                  <p className="text-xs text-blue-600 dark:text-blue-400">
                    {t('evaluation.multiFieldResults.processing')}
                  </p>
                )}
              </div>
            </div>

            {/* Progress bar for running evaluations */}
            {evaluation.status === 'running' && (
              <div className="px-4 py-2">
                <div className="h-2 w-full overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
                  <div
                    className="h-2 rounded-full bg-blue-500 transition-all duration-500"
                    style={{
                      // Calculate actual progress from passed + failed samples
                      width:
                        evaluation.samples_evaluated > 0
                          ? `${Math.min(100, Math.max(5, ((evaluation.progress.samples_passed + evaluation.progress.samples_failed) / evaluation.samples_evaluated) * 100))}%`
                          : '5%',
                    }}
                  />
                </div>
                <p className="mt-1 text-center text-xs text-gray-500 dark:text-gray-400">
                  {t('evaluation.multiFieldResults.samplesProcessed', { processed: evaluation.progress.samples_passed + evaluation.progress.samples_failed, total: evaluation.samples_evaluated })}
                </p>
              </div>
            )}

            {/* Error message */}
            {evaluation.error_message && (
              <div className="border-b border-red-200 bg-red-50 px-4 py-2 dark:border-red-800 dark:bg-red-900/20">
                <p className="text-sm text-red-600 dark:text-red-400">
                  {evaluation.error_message}
                </p>
              </div>
            )}

            {/* Results by config */}
            <div className="divide-y divide-gray-200 dark:divide-gray-700">
              {evaluation.evaluation_configs.map((config) => {
                const configResults = evaluation.results_by_config[config.id]

                return (
                  <div key={config.id} className="p-4">
                    <div className="mb-3 flex items-center justify-between">
                      <h4 className="font-medium text-gray-900 dark:text-white">
                        {getMetricDisplayName(
                          config.id,
                          evaluation.evaluation_configs
                        )}
                      </h4>
                      {configResults?.aggregate_score != null && (
                        <span className="text-lg font-semibold text-emerald-600 dark:text-emerald-400">
                          {formatScore(configResults.aggregate_score)}
                        </span>
                      )}
                    </div>

                    {configResults?.field_results &&
                    configResults.field_results.length > 0 ? (
                      <div className="space-y-2">
                        {configResults.field_results.map((fieldResult) => (
                          <div
                            key={fieldResult.combo_key}
                            className="rounded-lg bg-gray-50 p-3 dark:bg-gray-800"
                          >
                            <div className="mb-2 flex items-center justify-between text-sm">
                              <span className="text-gray-600 dark:text-gray-300">
                                <span className="font-medium">
                                  {fieldResult.prediction_field}
                                </span>{' '}
                                {t('evaluation.multiFieldResults.vs')}{' '}
                                <span className="font-medium">
                                  {fieldResult.reference_field}
                                </span>
                              </span>
                            </div>
                            {/* Score display - progress bars in chart view */}
                            <div className="space-y-1">
                              {Object.entries(fieldResult.scores || {}).map(
                                ([scoreName, scoreValue]) => (
                                  <div
                                    key={scoreName}
                                    className="flex items-center gap-2"
                                  >
                                    <span className="w-20 text-xs text-gray-500 dark:text-gray-400">
                                      {scoreName}
                                    </span>
                                    <div className="flex-1">
                                      <div className="h-2 w-full overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
                                        <div
                                          className="h-2 rounded-full bg-emerald-500 transition-all"
                                          style={{
                                            width:
                                              getScoreBarWidth(scoreValue),
                                          }}
                                        />
                                      </div>
                                    </div>
                                    <span className="w-16 text-right text-xs font-medium text-gray-700 dark:text-gray-300">
                                      {formatScore(scoreValue)}
                                    </span>
                                  </div>
                                )
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : evaluation.status === 'completed' ? (
                      <p className="text-sm text-gray-500 dark:text-gray-400">
                        {t('evaluation.multiFieldResults.noResultsForConfig')}
                      </p>
                    ) : (
                      <p className="text-sm text-gray-500 dark:text-gray-400">
                        {t('evaluation.multiFieldResults.waitingForResults')}
                      </p>
                    )}
                  </div>
                )
              })}

              {evaluation.evaluation_configs.length === 0 && (
                <div className="p-4">
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    {t('evaluation.multiFieldResults.noConfigsFound')}
                  </p>
                </div>
              )}
            </div>

            {/* Footer with statistics */}
            {evaluation.status === 'completed' && (
              <div className="flex items-center justify-between border-t border-gray-200 bg-gray-50 px-4 py-2 text-xs dark:border-gray-700 dark:bg-gray-800">
                <div className="flex items-center gap-4">
                  <span className="text-green-600 dark:text-green-400">
                    {t('evaluation.multiFieldResults.passedCount', { count: evaluation.progress.samples_passed })}
                  </span>
                  <span className="text-red-600 dark:text-red-400">
                    {t('evaluation.multiFieldResults.failedCount', { count: evaluation.progress.samples_failed })}
                  </span>
                  {evaluation.progress.samples_skipped > 0 && (
                    <span className="text-gray-500 dark:text-gray-400">
                      {t('evaluation.multiFieldResults.skippedCount', { count: evaluation.progress.samples_skipped })}
                    </span>
                  )}
                </div>
                <span className="text-gray-500 dark:text-gray-400">
                  ID: {evaluation.evaluation_id.slice(0, 8)}...
                </span>
              </div>
            )}
          </Card>
        ))}

      {/* Task Data Modal */}
      <TaskDataViewModal
        task={selectedTask}
        isOpen={taskModalOpen}
        onClose={() => {
          setTaskModalOpen(false)
          setSelectedTask(null)
        }}
      />

      {/* Generation & Evaluation Result Modal */}
      <ResultDetailsModal
        isOpen={resultModalOpen}
        onClose={() => {
          setResultModalOpen(false)
          setResultModalTaskId(null)
          setResultModalModelId(null)
          setAnnotationData(null)
          setGenerationData(null)
          setEvaluationData(null)
        }}
        taskId={resultModalTaskId}
        modelId={resultModalModelId}
        annotationData={annotationData}
        generationData={generationData}
        evaluationData={evaluationData}
        annotationLoading={annotationLoading}
        generationLoading={generationLoading}
        evaluationLoading={evaluationLoading}
        onReEvaluate={
          canStartGeneration(user) ? handleCellReEvaluate : undefined
        }
        evaluationConfigs={evaluationConfigs}
        selectedMetricName={
          availableMetricRuns.find((r) => r.id === selectedMetricRunId)?.metric ?? null
        }
      />
    </div>
  )
}

/**
 * Modal component for displaying generation and evaluation result details with tabs
 */
function ResultDetailsModal({
  isOpen,
  onClose,
  taskId,
  modelId,
  annotationData,
  generationData,
  evaluationData,
  annotationLoading,
  generationLoading,
  evaluationLoading,
  onReEvaluate,
  evaluationConfigs = [],
  selectedMetricName = null,
}: {
  isOpen: boolean
  onClose: () => void
  taskId: string | null
  modelId: string | null
  annotationData: Array<{
    id: string
    task_id: number
    completed_by: string
    result: Array<{ value: any; from_name: string; to_name: string; type: string; [key: string]: any }>
    was_cancelled: boolean
    ground_truth: boolean
    lead_time?: number
    created_at: string
    updated_at?: string
    metadata?: Record<string, any>
  }> | null
  generationData: Array<{
    task_id: string
    model_id: string
    generation_id: string
    status: string
    result?: {
      generated_text?: string
      created_at?: string
      usage_stats?: Record<string, any>
      fields?: Record<string, any>
    }
    generated_at?: string
    generation_time_seconds?: number
    prompt_used?: string
    parameters?: Record<string, any>
    error_message?: string
    structure_key?: string
  }> | null
  evaluationData: {
    task_id: string
    model_id: string
    results: Array<{
      id: string
      evaluation_id: string
      field_name: string
      answer_type: string
      ground_truth: any
      prediction: any
      metrics: Record<string, any>
      passed: boolean
      confidence_score?: number
      error_message?: string
      processing_time_ms?: number
      created_at?: string
      evaluation_context?: {
        evaluation_type: string
        status: string
        eval_metadata?: Record<string, any>
      }
    }>
    total_count: number
    message?: string
  } | null
  annotationLoading: boolean
  generationLoading: boolean
  evaluationLoading: boolean
  onReEvaluate?: (taskId: string, modelId: string, selectedConfigIds: string[]) => void
  evaluationConfigs?: Array<{
    id: string
    metric: string
    display_name?: string
    enabled: boolean
  }>
  /** Filters Evaluation Results tab to rows for this metric only.
   * `field_name` shape: "<metric>-<slug>|<pred>|<ref>"; we match by prefix
   * before the first `-`. Pass null/undefined to show everything. */
  selectedMetricName?: string | null
}) {
  const { t } = useI18n()
  const isAnnotatorCell = modelId?.startsWith('annotator:') ?? false
  const [activeTab, setActiveTab] = useState<'annotation' | 'generation' | 'evaluation'>('annotation')
  const [copySuccess, setCopySuccess] = useState(false)
  const [selectedStructureIndex, setSelectedStructureIndex] = useState(0)
  const [selectedEvalConfigIds, setSelectedEvalConfigIds] = useState<Set<string>>(new Set())
  const [showMetricSelection, setShowMetricSelection] = useState(false)

  // Reset structure index, metric selection, and default tab when modal opens
  useEffect(() => {
    if (isOpen) {
      setSelectedStructureIndex(0)
      setActiveTab(isAnnotatorCell ? 'annotation' : 'generation')
      // Select all enabled configs by default
      const enabledIds = evaluationConfigs
        .filter((c) => c.enabled !== false)
        .map((c) => c.id)
      setSelectedEvalConfigIds(new Set(enabledIds))
      setShowMetricSelection(false)
    }
  }, [isOpen, generationData, evaluationConfigs, isAnnotatorCell])

  const handleCopyToClipboard = async () => {
    const dataToCopy = activeTab === 'annotation' ? annotationData : activeTab === 'generation' ? generationData : evaluationData
    if (!dataToCopy) return
    try {
      await navigator.clipboard.writeText(JSON.stringify(dataToCopy, null, 2))
      setCopySuccess(true)
      setTimeout(() => setCopySuccess(false), 2000)
    } catch (error) {
      console.error('Failed to copy to clipboard:', error)
    }
  }

  // Format metric value for display
  const formatMetricValue = (value: any): string => {
    if (value === null || value === undefined) {
      return 'N/A'
    }
    if (typeof value === 'number') {
      return value.toFixed(3)
    }
    if (typeof value === 'string') {
      return value
    }
    return JSON.stringify(value)
  }

  return (
    <Dialog open={isOpen} onClose={onClose} className="relative z-50">
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/30" aria-hidden="true" />

      {/* Full-screen container */}
      <div className="fixed inset-0 flex w-screen items-center justify-center p-4">
        <DialogPanel className="w-full max-w-4xl rounded-lg bg-white shadow-xl dark:bg-zinc-900">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-zinc-200 p-6 dark:border-zinc-700">
            <div>
              <DialogTitle className="text-lg font-semibold text-zinc-900 dark:text-white">
                {t('evaluation.multiFieldResults.taskDetails')}
              </DialogTitle>
              {modelId && (
                <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                  {t('evaluation.multiFieldResults.model')}: {modelId} {taskId && `| ${t('evaluation.multiFieldResults.task')}: ${taskId.slice(0, 8)}...`}
                </p>
              )}
            </div>

            <div className="flex items-center gap-3">
              {/* Copy button */}
              <button
                onClick={handleCopyToClipboard}
                disabled={activeTab === 'annotation' ? !annotationData : activeTab === 'generation' ? !generationData : !evaluationData}
                className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                  copySuccess
                    ? 'bg-green-100 text-green-800 dark:bg-green-900/20 dark:text-green-400'
                    : 'bg-zinc-100 text-zinc-700 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700'
                } disabled:opacity-50`}
              >
                <ClipboardDocumentIcon className="h-4 w-4" />
                {copySuccess ? t('evaluation.multiFieldResults.copied') : t('evaluation.multiFieldResults.copyJson')}
              </button>

              {/* Close button */}
              <button
                onClick={onClose}
                className="rounded-lg p-2 text-zinc-600 transition-colors hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-white"
              >
                <XMarkIcon className="h-5 w-5" />
              </button>
            </div>
          </div>

          {/* Tab Navigation - show only relevant tabs per cell type */}
          <div className="border-b border-zinc-200 dark:border-zinc-700">
            <nav className="flex px-6" aria-label="Tabs">
              {isAnnotatorCell && (
                <button
                  onClick={() => setActiveTab('annotation')}
                  className={`relative px-4 py-3 text-sm font-medium transition-colors ${
                    activeTab === 'annotation'
                      ? 'text-emerald-600 dark:text-emerald-400'
                      : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white'
                  }`}
                >
                  {t('evaluation.multiFieldResults.annotationResult', 'Annotation Result')}
                  {activeTab === 'annotation' && (
                    <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-emerald-600 dark:bg-emerald-400" />
                  )}
                </button>
              )}
              {!isAnnotatorCell && (
                <button
                  onClick={() => setActiveTab('generation')}
                  className={`relative px-4 py-3 text-sm font-medium transition-colors ${
                    activeTab === 'generation'
                      ? 'text-emerald-600 dark:text-emerald-400'
                      : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white'
                  }`}
                >
                  {t('evaluation.multiFieldResults.generationResults')}
                  {activeTab === 'generation' && (
                    <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-emerald-600 dark:bg-emerald-400" />
                  )}
                </button>
              )}
              <button
                onClick={() => setActiveTab('evaluation')}
                className={`relative px-4 py-3 text-sm font-medium transition-colors ${
                  activeTab === 'evaluation'
                    ? 'text-emerald-600 dark:text-emerald-400'
                    : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white'
                }`}
              >
                {t('evaluation.multiFieldResults.evaluationResults')}
                {activeTab === 'evaluation' && (
                  <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-emerald-600 dark:bg-emerald-400" />
                )}
              </button>
            </nav>
          </div>

          {/* Content */}
          <div className="max-h-[60vh] overflow-y-auto p-6">
            {activeTab === 'annotation' ? (
              // Annotation Result Tab
              annotationLoading ? (
                <div className="flex items-center justify-center py-12">
                  <LoadingSpinner />
                </div>
              ) : annotationData && annotationData.length > 0 ? (
                <div className="space-y-6">
                  {annotationData.map((annotation, annIndex) => (
                    <div key={annotation.id} className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-700">
                      {/* Annotation Header */}
                      <div className="mb-4 flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                            annotation.ground_truth
                              ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-400'
                              : 'bg-zinc-100 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-300'
                          }`}>
                            {annotation.ground_truth ? t('evaluation.multiFieldResults.groundTruth', 'Ground Truth') : t('evaluation.multiFieldResults.annotation', 'Annotation')}
                          </span>
                          <span className="text-sm text-zinc-600 dark:text-zinc-400">
                            {t('evaluation.multiFieldResults.annotator', 'Annotator')}: {annotation.completed_by}
                          </span>
                        </div>
                        <span className="text-xs text-zinc-500 dark:text-zinc-400">
                          {new Date(annotation.created_at).toLocaleString()}
                        </span>
                      </div>

                      {/* Annotation Results */}
                      {annotation.result && annotation.result.length > 0 ? (
                        <div className="space-y-3">
                          {annotation.result.map((res, resIndex) => (
                            <div key={resIndex} className="rounded-lg bg-zinc-50 p-3 dark:bg-zinc-800">
                              <div className="mb-1 flex items-center gap-2">
                                <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
                                  {res.from_name}
                                </span>
                                <span className="text-xs text-zinc-400 dark:text-zinc-500">
                                  ({res.type})
                                </span>
                              </div>
                              <div className="text-sm text-zinc-900 dark:text-white">
                                {typeof res.value === 'string' ? (
                                  <p className="whitespace-pre-wrap">{res.value}</p>
                                ) : (
                                  <pre className="whitespace-pre-wrap text-xs">
                                    {JSON.stringify(res.value, null, 2)}
                                  </pre>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-sm text-zinc-500 dark:text-zinc-400">
                          {t('evaluation.multiFieldResults.noAnnotationResults', 'No annotation results')}
                        </p>
                      )}

                      {/* Metadata */}
                      <div className="mt-4 grid grid-cols-2 gap-4 text-sm">
                        {annotation.lead_time != null && (
                          <div className="rounded-lg bg-zinc-50 p-3 dark:bg-zinc-800">
                            <span className="text-zinc-500 dark:text-zinc-400">{t('evaluation.multiFieldResults.duration')}:</span>
                            <span className="ml-2 text-zinc-900 dark:text-white">
                              {annotation.lead_time.toFixed(1)}s
                            </span>
                          </div>
                        )}
                        {annotation.was_cancelled && (
                          <div className="rounded-lg bg-red-50 p-3 dark:bg-red-900/20">
                            <span className="text-red-700 dark:text-red-300">{t('evaluation.multiFieldResults.cancelled', 'Cancelled')}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}

                  {/* Full JSON Section (collapsed) */}
                  <details className="group">
                    <summary className="cursor-pointer font-medium text-zinc-900 dark:text-white">
                      {t('evaluation.multiFieldResults.rawJsonResponse')}
                    </summary>
                    <div className="mt-2 rounded-lg bg-zinc-50 p-4 dark:bg-zinc-800">
                      <pre className="overflow-x-auto text-xs text-zinc-700 dark:text-zinc-300">
                        {JSON.stringify(annotationData, null, 2)}
                      </pre>
                    </div>
                  </details>
                </div>
              ) : (
                <div className="py-12 text-center text-zinc-500 dark:text-zinc-400">
                  {t('evaluation.multiFieldResults.noAnnotationData', 'No annotation data available for this task')}
                </div>
              )
            ) : activeTab === 'generation' ? (
              // Generation Results Tab
              generationLoading ? (
                <div className="flex items-center justify-center py-12">
                  <LoadingSpinner />
                </div>
              ) : generationData && generationData.length > 0 ? (
                <div className="space-y-6">
                  {/* Structure Tabs (if multiple structures) */}
                  {generationData.length > 1 && (
                    <div className="border-b border-zinc-200 dark:border-zinc-700">
                      <nav className="-mb-px flex space-x-4">
                        {generationData.map((result, index) => (
                          <button
                            key={index}
                            onClick={() => setSelectedStructureIndex(index)}
                            className={`whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium ${
                              selectedStructureIndex === index
                                ? 'border-emerald-500 text-emerald-600 dark:text-emerald-400'
                                : 'border-transparent text-zinc-500 hover:border-zinc-300 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-300'
                            }`}
                          >
                            {result.structure_key || t('evaluation.multiFieldResults.default')}
                          </button>
                        ))}
                      </nav>
                    </div>
                  )}

                  {/* Selected Structure Content */}
                  {(() => {
                    const selectedGen = generationData[selectedStructureIndex]
                    if (!selectedGen) return null
                    return (
                      <>
                        {/* Generated Text Section */}
                        {selectedGen.result?.generated_text && (
                          <div>
                            <h4 className="mb-2 font-medium text-zinc-900 dark:text-white">
                              {t('evaluation.multiFieldResults.generatedResponse')}
                            </h4>
                            <div className="rounded-lg bg-zinc-50 p-4 dark:bg-zinc-800">
                              <pre className="whitespace-pre-wrap text-sm text-zinc-700 dark:text-zinc-300">
                                {selectedGen.result.generated_text}
                              </pre>
                            </div>
                          </div>
                        )}

                        {/* Fields Section (for structured outputs) */}
                        {selectedGen.result?.fields && Object.keys(selectedGen.result.fields).length > 0 && (
                          <div>
                            <h4 className="mb-2 font-medium text-zinc-900 dark:text-white">
                              {t('evaluation.multiFieldResults.generatedFields')}
                            </h4>
                            <div className="rounded-lg bg-zinc-50 p-4 dark:bg-zinc-800">
                              <pre className="whitespace-pre-wrap text-sm text-zinc-700 dark:text-zinc-300">
                                {JSON.stringify(selectedGen.result.fields, null, 2)}
                              </pre>
                            </div>
                          </div>
                        )}

                        {/* Prompt Used Section */}
                        {selectedGen.prompt_used && (
                          <div>
                            <h4 className="mb-2 font-medium text-zinc-900 dark:text-white">
                              {t('evaluation.multiFieldResults.promptUsed')}
                            </h4>
                            <div className="rounded-lg bg-blue-50 p-4 dark:bg-blue-900/20">
                              <pre className="whitespace-pre-wrap text-sm text-blue-800 dark:text-blue-200">
                                {selectedGen.prompt_used}
                              </pre>
                            </div>
                          </div>
                        )}

                        {/* Metadata Section */}
                        <div>
                          <h4 className="mb-2 font-medium text-zinc-900 dark:text-white">
                            {t('evaluation.multiFieldResults.metadata')}
                          </h4>
                          <div className="grid grid-cols-2 gap-4 text-sm">
                            <div className="rounded-lg bg-zinc-50 p-3 dark:bg-zinc-800">
                              <span className="text-zinc-500 dark:text-zinc-400">{t('evaluation.multiFieldResults.statusLabel')}:</span>
                              <span className="ml-2 text-zinc-900 dark:text-white">
                                {selectedGen.status}
                              </span>
                            </div>
                            {selectedGen.generated_at && (
                              <div className="rounded-lg bg-zinc-50 p-3 dark:bg-zinc-800">
                                <span className="text-zinc-500 dark:text-zinc-400">{t('evaluation.multiFieldResults.generated')}:</span>
                                <span className="ml-2 text-zinc-900 dark:text-white">
                                  {new Date(selectedGen.generated_at).toLocaleString()}
                                </span>
                              </div>
                            )}
                            {selectedGen.generation_time_seconds != null && (
                              <div className="rounded-lg bg-zinc-50 p-3 dark:bg-zinc-800">
                                <span className="text-zinc-500 dark:text-zinc-400">{t('evaluation.multiFieldResults.duration')}:</span>
                                <span className="ml-2 text-zinc-900 dark:text-white">
                                  {selectedGen.generation_time_seconds.toFixed(2)}s
                                </span>
                              </div>
                            )}
                          </div>
                        </div>

                        {/* Full JSON Section (collapsed) */}
                        <details className="group">
                          <summary className="cursor-pointer font-medium text-zinc-900 dark:text-white">
                            {t('evaluation.multiFieldResults.rawJsonResponse')}
                          </summary>
                          <div className="mt-2 rounded-lg bg-zinc-50 p-4 dark:bg-zinc-800">
                            <pre className="overflow-x-auto text-xs text-zinc-700 dark:text-zinc-300">
                              {JSON.stringify(selectedGen, null, 2)}
                            </pre>
                          </div>
                        </details>
                      </>
                    )
                  })()}
                </div>
              ) : (
                <div className="py-12 text-center text-zinc-500 dark:text-zinc-400">
                  {t('evaluation.multiFieldResults.noGenerationData')}
                </div>
              )
            ) : (
              // Evaluation Results Tab
              evaluationLoading ? (
                <div className="flex items-center justify-center py-12">
                  <LoadingSpinner />
                </div>
              ) : evaluationData && evaluationData.results.length > 0 ? (() => {
                // Filter to entries for the currently-selected metric.
                // field_name shape from worker: "<metric>-<slug>|<pred>|<ref>"
                // (see tasks.py: field_key = f"{config_id}|...", config_id = "{metric}-{slug}")
                const visibleResults = selectedMetricName
                  ? evaluationData.results.filter((r) => {
                      const fieldMetric = (r.field_name || '').split('-')[0]
                      const inMetricsKeys =
                        r.metrics &&
                        Object.keys(r.metrics).some(
                          (k) => k === selectedMetricName || k.startsWith(`${selectedMetricName}_`)
                        )
                      return fieldMetric === selectedMetricName || inMetricsKeys
                    })
                  : evaluationData.results
                if (visibleResults.length === 0) {
                  return (
                    <div className="py-8 text-center text-sm text-zinc-500 dark:text-zinc-400">
                      {t('evaluation.multiFieldResults.noResultsForMetric', {
                        defaultValue: 'No evaluation results for the selected metric.',
                      })}
                    </div>
                  )
                }
                return (
                <div className="space-y-6">
                  {visibleResults.map((result, index) => (
                    <div key={result.id} className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-700">
                      {/* Result Header */}
                      <div className="mb-4 flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                            result.passed === null
                              ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/20 dark:text-amber-400'
                              : result.passed
                                ? 'bg-green-100 text-green-800 dark:bg-green-900/20 dark:text-green-400'
                                : 'bg-red-100 text-red-800 dark:bg-red-900/20 dark:text-red-400'
                          }`}>
                            {result.passed === null ? t('evaluation.multiFieldResults.error') : result.passed ? t('evaluation.multiFieldResults.passed') : t('evaluation.multiFieldResults.failed')}
                          </span>
                          <span className="text-sm font-medium text-zinc-900 dark:text-white">
                            {t('evaluation.multiFieldResults.field')}: {result.field_name}
                          </span>
                          <span className="text-xs text-zinc-500 dark:text-zinc-400">
                            ({result.answer_type})
                          </span>
                        </div>
                        {result.confidence_score != null && (
                          <span className="text-sm text-zinc-600 dark:text-zinc-400">
                            {t('evaluation.multiFieldResults.confidence')}: {(result.confidence_score * 100).toFixed(1)}%
                          </span>
                        )}
                      </div>

                      {/* Metrics */}
                      {result.metrics && Object.keys(result.metrics).length > 0 && (() => {
                        // Separate _response objects from numeric metrics
                        const llmResponses: Record<string, Record<string, any>> = {}
                        const numericMetrics: Record<string, any> = {}

                        Object.entries(result.metrics).forEach(([key, value]) => {
                          if (key.endsWith('_response') && value && typeof value === 'object') {
                            llmResponses[key.replace('_response', '')] = value as Record<string, any>
                          } else if (!key.endsWith('_response')) {
                            numericMetrics[key] = value
                          }
                        })

                        return (
                          <div className="mb-4">
                            <h5 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
                              {t('evaluation.multiFieldResults.metrics')}
                            </h5>
                            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                              {Object.entries(numericMetrics).map(([key, value]) => {
                                // Extension hook: extended metrics may register
                                // a detail component that renders the full
                                // structured payload (dimensions, justification,
                                // grade points, etc.) instead of the bare
                                // formatMetricValue. Falls back to generic
                                // numeric display when nothing is registered.
                                const DetailComp = getMetricDetail(key)
                                if (DetailComp) {
                                  return (
                                    <div key={key} className="col-span-full">
                                      <DetailComp value={value} evaluation={result as unknown as Record<string, unknown>} />
                                    </div>
                                  )
                                }
                                return (
                                  <div key={key} className="rounded bg-zinc-50 p-2 dark:bg-zinc-800">
                                    <span className="text-xs text-zinc-500 dark:text-zinc-400">{key}:</span>
                                    <span className="ml-1 font-mono text-sm text-zinc-900 dark:text-white">
                                      {formatMetricValue(value)}
                                    </span>
                                  </div>
                                )
                              })}
                            </div>

                            {/* Full LLM Judge Response */}
                            {Object.keys(llmResponses).length > 0 && (
                              <div className="mt-4">
                                <h5 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
                                  {t('evaluation.multiFieldResults.llmJudgeResponse')}
                                </h5>
                                {Object.entries(llmResponses).map(([metric, response]) => (
                                  <div key={metric} className="mb-3 rounded-lg border border-amber-200 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-900/20">
                                    <span className="mb-2 block text-xs font-medium text-amber-700 dark:text-amber-400">
                                      {metric}
                                    </span>
                                    <div className="space-y-2">
                                      {Object.entries(response).map(([fieldKey, fieldValue]) => {
                                        if (fieldKey === 'score') return null
                                        return (
                                          <div key={fieldKey} className="text-sm">
                                            <span className="font-medium text-amber-800 dark:text-amber-300">
                                              {fieldKey}:
                                            </span>
                                            {typeof fieldValue === 'string' ? (
                                              <p className="mt-1 whitespace-pre-wrap text-amber-900 dark:text-amber-200">
                                                {fieldValue}
                                              </p>
                                            ) : (
                                              <pre className="mt-1 overflow-x-auto rounded bg-amber-100 p-2 text-xs text-amber-900 dark:bg-amber-900/40 dark:text-amber-200">
                                                {JSON.stringify(fieldValue, null, 2)}
                                              </pre>
                                            )}
                                          </div>
                                        )
                                      })}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )
                      })()}

                      {/* Ground Truth vs Prediction */}
                      <div className="grid gap-4 md:grid-cols-2">
                        <div>
                          <h5 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
                            {t('evaluation.multiFieldResults.groundTruth')}
                          </h5>
                          <div className="rounded-lg bg-green-50 p-3 dark:bg-green-900/20">
                            <pre className="whitespace-pre-wrap text-xs text-green-800 dark:text-green-200">
                              {typeof result.ground_truth === 'string'
                                ? result.ground_truth
                                : JSON.stringify(result.ground_truth, null, 2)}
                            </pre>
                          </div>
                        </div>
                        <div>
                          <h5 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
                            {t('evaluation.multiFieldResults.modelPrediction')}
                          </h5>
                          <div className="rounded-lg bg-blue-50 p-3 dark:bg-blue-900/20">
                            <pre className="whitespace-pre-wrap text-xs text-blue-800 dark:text-blue-200">
                              {typeof result.prediction === 'string'
                                ? result.prediction
                                : JSON.stringify(result.prediction, null, 2)}
                            </pre>
                          </div>
                        </div>
                      </div>

                      {/* Error Message if any */}
                      {result.error_message && (
                        <div className="mt-4 rounded-lg bg-red-50 p-3 dark:bg-red-900/20">
                          <p className="text-sm text-red-700 dark:text-red-300">
                            {t('evaluation.multiFieldResults.error')}: {result.error_message}
                          </p>
                        </div>
                      )}

                      {/* Evaluation Context */}
                      {result.evaluation_context && (
                        <div className="mt-4 text-xs text-zinc-500 dark:text-zinc-400">
                          {t('evaluation.multiFieldResults.evaluation')}: {result.evaluation_context.evaluation_type} ({result.evaluation_context.status})
                          {result.created_at && ` | ${new Date(result.created_at).toLocaleString()}`}
                        </div>
                      )}
                    </div>
                  ))}

                  {/* Full JSON Section (collapsed) */}
                  <details className="group">
                    <summary className="cursor-pointer font-medium text-zinc-900 dark:text-white">
                      {t('evaluation.multiFieldResults.rawJsonResponse')}
                    </summary>
                    <div className="mt-2 rounded-lg bg-zinc-50 p-4 dark:bg-zinc-800">
                      <pre className="overflow-x-auto text-xs text-zinc-700 dark:text-zinc-300">
                        {JSON.stringify(evaluationData, null, 2)}
                      </pre>
                    </div>
                  </details>
                </div>
                )
              })() : (
                <div className="py-12 text-center text-zinc-500 dark:text-zinc-400">
                  {evaluationData?.message || t('evaluation.multiFieldResults.noEvalResults')}
                </div>
              )
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between border-t border-zinc-200 p-4 dark:border-zinc-700">
            <div className="flex items-center gap-3">
              {onReEvaluate && taskId && modelId && evaluationConfigs.length > 0 && (
                <>
                  {showMetricSelection && (
                    <div className="flex flex-wrap items-center gap-2">
                      {evaluationConfigs
                        .filter((c) => c.enabled !== false)
                        .map((config) => (
                          <label
                            key={config.id}
                            className="flex items-center gap-1.5 rounded-md bg-zinc-50 px-2 py-1 text-xs dark:bg-zinc-800"
                          >
                            <input
                              type="checkbox"
                              checked={selectedEvalConfigIds.has(config.id)}
                              onChange={(e) => {
                                setSelectedEvalConfigIds((prev) => {
                                  const next = new Set(prev)
                                  if (e.target.checked) {
                                    next.add(config.id)
                                  } else {
                                    next.delete(config.id)
                                  }
                                  return next
                                })
                              }}
                              className="h-3.5 w-3.5 rounded border-zinc-300 text-blue-600 focus:ring-blue-500 dark:border-zinc-600"
                            />
                            <span className="text-zinc-700 dark:text-zinc-300">
                              {config.display_name || config.metric.replace(/_/g, ' ')}
                            </span>
                          </label>
                        ))}
                    </div>
                  )}
                  <div className="flex items-center gap-2">
                    {evaluationConfigs.filter((c) => c.enabled !== false).length > 1 && (
                      <button
                        onClick={() => setShowMetricSelection(!showMetricSelection)}
                        className="text-xs text-zinc-500 underline hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
                      >
                        {t('evaluation.multiFieldResults.selectMetrics')}
                      </button>
                    )}
                    <button
                      onClick={() => {
                        onReEvaluate(taskId, modelId, [...selectedEvalConfigIds])
                        onClose()
                      }}
                      disabled={selectedEvalConfigIds.size === 0}
                      className="flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-blue-500 dark:hover:bg-blue-600"
                    >
                      <ArrowPathIcon className="h-4 w-4" />
                      {t('evaluation.multiFieldResults.reEvaluate')}
                    </button>
                  </div>
                </>
              )}
            </div>
            <button
              onClick={onClose}
              className="rounded-md bg-zinc-100 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
            >
              {t('evaluation.multiFieldResults.close')}
            </button>
          </div>
        </DialogPanel>
      </div>
    </Dialog>
  )
}
