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
import { InflightRunsBanner } from '@/components/evaluation/InflightRunsBanner'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { TaskDataViewModal } from '@/components/tasks/TaskDataViewModal'
import { canStartGeneration } from '@/utils/permissions'
import { apiClient } from '@/lib/api/client'
import { projectsAPI } from '@/lib/api/projects'
import { Task as LabelStudioTask } from '@/types/labelStudio'
import { Task } from '@/lib/api/types'
import {
  ArrowDownTrayIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  ClockIcon,
  ExclamationCircleIcon,
  PlayIcon,
  QueueListIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { METRIC_ORDER } from '@/lib/api/evaluation-types'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/shared/Select'
import { ResultDetailsModal } from '@/components/evaluation/results/ResultsModal'
import { useResultsData, useTaskModelData } from '@/components/evaluation/results/useResultsData'
import type {
  ChartData,
  SampleEvaluationResult,
  StatisticalMethod,
  StatisticsData,
} from '@/components/evaluation/results/types'

// Re-exported so existing consumers (`@/app/evaluations/page.tsx`,
// tests) that import `ChartData` from this module keep working after
// the shape moved to `results/types`.
export type { ChartData } from '@/components/evaluation/results/types'

interface EvaluationResultsProps {
  projectId: string | number
  selectedModels?: string[]
  /**
   * Issue #111: per-config selection (one entry per
   * `evaluation_config.id`) instead of per-metric-name. Two configs
   * sharing the same `metric` type but distinct `display_name`s now
   * filter independently — the page-level dropdown is keyed on
   * `evaluation_config_id` so this prop matches.
   */
  selectedConfigIds?: string[]
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

export function EvaluationResults({
  projectId,
  selectedModels = [],
  selectedConfigIds = [],
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
  const [showHistory, setShowHistory] = useState(false)

  // Project evaluation results fetch unit (initial fetch + polling +
  // refetch) lives in useResultsData. `refetch` re-fetches without
  // touching the loading flag; manual refresh / re-evaluate call
  // setLoading(true) first to surface the spinner. Declared up-front so
  // the metric-grouping useMemo and chart effect below can read
  // `results`/`taskModelData`.
  const {
    results,
    loading,
    error,
    refetch: fetchResults,
    setLoading,
  } = useResultsData({
    projectId,
    refreshKey,
    showHistory,
    failedLoadMessage: t('evaluation.multiFieldResults.failedLoadResults'),
  })
  const [selectedMetricRunId, setSelectedMetricRunId] = useState<string | null>(null)
  const [exportDropdownOpen, setExportDropdownOpen] = useState(false)
  // Multi-run "By run" chart toggle (migration 042). When on, the chart data
  // splits each model into one entry per (judge_run) so the user can compare
  // the same model's repeats side-by-side. Off by default — keeps the
  // single-bar-per-model view for projects without multi-run data.
  const [byRunChart, setByRunChart] = useState(false)
  const exportDropdownRef = useRef<HTMLDivElement>(null)

  // Issue #111: this dropdown now lists one entry per
  // `evaluation_config.id` (not per metric_name). Two configs sharing
  // the same `metric` type but distinct `display_name`s render as
  // separate, independently-selectable entries — the page-level filter
  // in the parent component is keyed on `evaluation_config_id`, so this
  // results-card-scoped dropdown mirrors that. Every EvaluationRun of a
  // config (immediate re-submissions, cron sweeps, batch/missing-only)
  // is unioned server-side by the config-id fetch, so one method = one
  // entry. Sorted by the evaluation config order from the project wizard
  // using `cfg.metric` for GROUPED_METRICS lookup (configs of the same
  // metric group together).
  const availableMetricRuns = useMemo(() => {
    type ConfigEntry = {
      id: string             // evaluation_config.id — primary key + fetch scope
      metric: string         // raw metric name, kept for METRIC_ORDER sort + score extraction
      configId: string       // same as id (kept for backward-compat reading sites)
      displayName: string
      samplesEvaluated: number
      running: boolean       // any run for this method is in-flight (cosmetic)
    }

    const byConfig = new Map<string, ConfigEntry>()

    // The dropdown is ONE entry per evaluation METHOD — the project's enabled
    // eval configs, keyed by their stable `evaluation_config.id` (issue #111).
    // Per-cell scores come from the by-task-model fetch scoped to that config
    // id, which scans ALL of the project's runs (immediate KI-Votum, the
    // hourly cron sweep, manual batch/missing-only) and unions generation +
    // annotation cells. So runs NEVER mint their own entries — that split was
    // what pinned the grid to one (possibly empty) run and rendered all-N/A.
    for (const cfg of evaluationConfigs ?? []) {
      if (cfg?.enabled === false) continue
      const cfgId = cfg?.id || cfg?.metric
      if (!cfgId || byConfig.has(cfgId)) continue
      if (
        selectedConfigIds &&
        selectedConfigIds.length > 0 &&
        !selectedConfigIds.includes(cfgId)
      ) {
        continue
      }
      byConfig.set(cfgId, {
        id: cfgId,
        metric: cfg?.metric || 'unknown',
        configId: cfgId,
        displayName: cfg?.display_name || cfg?.metric || 'Unknown',
        samplesEvaluated: 0,
        running: false,
      })
    }

    // Annotate metadata from runs (samplesEvaluated + in-flight status). A run
    // is matched to an entry by config id (exact) else by metric — immediate
    // runs carry inconsistent eval_metadata config ids, so metric is the
    // reliable fallback; this attribution is COSMETIC since the data cells come
    // from the DB `evaluation_config_id` filter, which stays isolated per
    // method. Defensive: a run pinned to a full canonical config id (contains
    // '-', not a bare metric name) that is NOT among the enabled configs — a
    // wizard edit that changed an id, or a project whose config list failed to
    // load — is surfaced as its own entry so its scores never silently vanish.
    const visible = (results?.evaluations ?? []).filter(
      (e) =>
        e.status === 'completed' ||
        e.status === 'running' ||
        e.status === 'pending'
    )
    for (const e of visible) {
      const inflight = e.status === 'running' || e.status === 'pending'
      const cfgs = Array.isArray(e.evaluation_configs) ? e.evaluation_configs : []
      for (const cfg of cfgs) {
        const rawId = cfg?.id || ''
        const metric = cfg?.metric || 'unknown'
        if (
          rawId &&
          rawId.includes('-') &&
          rawId !== metric &&
          !byConfig.has(rawId) &&
          (!selectedConfigIds ||
            selectedConfigIds.length === 0 ||
            selectedConfigIds.includes(rawId))
        ) {
          byConfig.set(rawId, {
            id: rawId,
            metric,
            configId: rawId,
            displayName: cfg?.display_name || metric || 'Unknown',
            samplesEvaluated: 0,
            running: false,
          })
        }
        const targets = byConfig.has(rawId)
          ? [byConfig.get(rawId)!]
          : Array.from(byConfig.values()).filter((x) => x.metric === metric)
        for (const entry of targets) {
          entry.samplesEvaluated = Math.max(
            entry.samplesEvaluated,
            e.samples_evaluated || 0,
          )
          if (inflight) entry.running = true
        }
      }
    }

    // Sort by GROUPED_METRICS order (same as wizard) using cfg.metric
    // — this keeps configs of the same metric type adjacent.
    const runs = Array.from(byConfig.values())
    const orderMap = new Map(METRIC_ORDER.map((m, i) => [m, i]))
    runs.sort((a, b) => {
      const orderA = orderMap.get(a.metric) ?? 999
      const orderB = orderMap.get(b.metric) ?? 999
      return orderA - orderB
    })

    return runs
  }, [results, selectedConfigIds, evaluationConfigs])

  // Auto-select config — restore from localStorage or default to first.
  // Issue #111: storage now keys on evaluation_config.id (not metric
  // name) so two configs of the same metric type round-trip cleanly.
  // Stale legacy values that don't match any config_id fall back to
  // the first available entry (clean break, no metric-name shim).
  useEffect(() => {
    if (availableMetricRuns.length === 0) return

    // If current selection is still valid, keep it
    if (selectedMetricRunId && availableMetricRuns.some((r) => r.id === selectedMetricRunId)) {
      return
    }

    // Try to restore from localStorage by config_id
    const savedConfigId = localStorage.getItem(`eval-selected-config-${projectId}`)
    if (savedConfigId) {
      const match = availableMetricRuns.find((r) => r.id === savedConfigId)
      if (match) {
        setSelectedMetricRunId(match.id)
        return
      }
    }

    // Default to first
    setSelectedMetricRunId(availableMetricRuns[0].id)
  }, [availableMetricRuns, selectedMetricRunId, projectId])

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

  // When showHistory is off, deduplicate to latest run per config.
  // Issue #111: key by evaluation_config.id (not metric name) so two
  // configs of the same metric type stay distinct — keying by metric
  // would surface only one of them in the result-card list.
  const displayEvaluations = useMemo(() => {
    if (showHistory) return filteredEvaluations
    const latestByConfig = new Map<string, typeof filteredEvaluations[0]>()
    for (const evaluation of filteredEvaluations) {
      const cfgId =
        evaluation.evaluation_configs?.[0]?.id ||
        evaluation.evaluation_configs?.[0]?.metric ||
        'unknown'
      const existing = latestByConfig.get(cfgId)
      if (!existing || (evaluation.created_at && existing.created_at && evaluation.created_at > existing.created_at)) {
        latestByConfig.set(cfgId, evaluation)
      }
    }
    return [...latestByConfig.values()]
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

  // Notify parent when results are loaded
  useEffect(() => {
    if (!loading && results) {
      const hasResults = (results.evaluations?.length ?? 0) > 0
      onResultsLoaded?.(hasResults)
    }
  }, [loading, results, onResultsLoaded])

  // Per-task/model data is fetched by the selected method's stable
  // `evaluation_config_id`. The backend scans ALL of the project's runs for
  // that config and unions generation + annotation cells (its row_number()
  // OVER (PARTITION BY generation_id|annotation_id, field_name ORDER BY
  // created_at DESC) collapses overlapping runs to the latest score per cell),
  // so a method's full result set is always shown regardless of which run
  // produced each cell — no run-id pinning, no n/a for data that exists.
  const selectedEntry = availableMetricRuns.find((r) => r.id === selectedMetricRunId)
  const selectedConfigId = selectedEntry?.id ?? ''

  // The metric name is also sent so the backend can pick the primary score
  // (`_extract_primary_score`) and guard multi-metric-per-row bundles.
  const selectedMetricKey = selectedEntry?.metric ?? ''

  // The worker commits each TaskEvaluation row to Postgres immediately after
  // the evaluator returns, so an in-flight run already has queryable rows. We
  // stream cell-by-cell updates via a WebSocket (5 s polling fallback) while
  // the selected method has any run in flight — computed in the memo above.
  const hasInflightSelectedRun = selectedEntry?.running ?? false

  // Per-task/model fetch unit (selected-config-scoped fetch + WebSocket /
  // polling live updates) lives in useTaskModelData.
  const { taskModelData, taskModelLoading } = useTaskModelData({
    projectId,
    showHistory,
    selectedConfigId,
    selectedMetricKey,
    hasInflightSelectedRun,
  })

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
      // "By run" toggle (migration 042 + issue #111): split each model
      // into one entry per judge_run when
      // statisticsData.per_run_means_by_model_metric has data for it.
      // The composite key shape changed from "model_id|metric" (2-part)
      // to "model_id|config_id|metric" (3-part) — the chart aggregates
      // ACROSS configs of the same metric here (the per-config split is
      // done by the parent page's filter), so we scan all matching
      // 3-part keys for this (model, metric) and concatenate their run
      // entries. Configs are surfaced in the judge label so users can
      // still tell them apart in the by-run view.
      const perRunBlock = (statisticsData as any)?.per_run_means_by_model_metric
      if (byRunChart && perRunBlock) {
        const chartData: ChartData[] = []
        for (const [modelId, summaryData] of Object.entries(taskModelData.summary)) {
          const matchedRuns: Array<{
            cfgId: string
            run: { judge_run_id: string; judge_model_id: string | null; run_index: number; mean: number; n_tasks: number }
          }> = []
          const prefix = `${modelId}|`
          const suffix = `|${primaryMetricName}`
          for (const [k, v] of Object.entries(perRunBlock)) {
            if (k.startsWith(prefix) && k.endsWith(suffix)) {
              // k === "model_id|config_id|metric"
              const parts = k.split('|')
              const cfgId = parts.length >= 3 ? parts.slice(1, -1).join('|') : 'unknown'
              for (const run of (v as any[]) || []) {
                matchedRuns.push({ cfgId, run })
              }
            }
          }
          if (matchedRuns.length > 0) {
            for (const { cfgId, run } of matchedRuns) {
              const judgeLabel = run.judge_model_id ?? 'human'
              chartData.push({
                model_id: `${modelId}__${cfgId}__${judgeLabel}__r${run.run_index}`,
                model_name: `${summaryData.model_name || modelId} · ${cfgId} · ${judgeLabel} · run ${run.run_index}`,
                metrics: { [primaryMetricName]: run.mean },
                samples_evaluated: run.n_tasks,
              })
            }
          } else {
            // No per-run data for this model — fall back to single bar.
            chartData.push({
              model_id: modelId,
              model_name: summaryData.model_name || modelId,
              metrics: { [primaryMetricName]: summaryData.avg },
              samples_evaluated: summaryData.count,
            })
          }
        }
        onDataLoaded(chartData)
        return
      }

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
  }, [loading, results, taskModelData, onDataLoaded, byRunChart, statisticsData])

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

    // Fetch generation results only for model cells. Capture the
    // single generation_id we'll lock the Evaluation tab to so all
    // three tabs describe the same generation. Without this lock the
    // Generation tab can show today's output while the Evaluation tab
    // shows yesterday's eval of a stale generation.
    let lockedGenerationId: string | undefined
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
        const gens = result.results || []
        setGenerationData(gens)
        // The endpoint returns latest first when include_history=false; with
        // include_history=true it still returns most-recent first. Either way
        // the first row is the generation the user expects to see.
        lockedGenerationId = gens[0]?.generation_id
      } catch (err) {
        console.error('Failed to fetch generation result:', err)
      } finally {
        setGenerationLoading(false)
      }
    }

    // Fetch per-task evaluation results scoped to lockedGenerationId
    // (annotator cells skip this scope — annotations are subjects, not
    // generations). Without the scope the eval tab silently shows
    // evaluations of any historical generation.
    try {
      const result = await apiClient.getTaskEvaluation(
        taskId,
        modelId,
        showHistory,
        isAnnotatorCell ? undefined : lockedGenerationId,
      )
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

  /**
   * Multi-run aggregate (migration 042 + issue #111). When ≥2 runs
   * exist for this (model, metric) pair, return a "± std (N runs)"
   * suffix to append after the per-sample stats line. Always-on
   * display — independent of the selectedStatistics toggle since it's
   * a fundamentally different statistic (variance ACROSS runs, not
   * within a single run).
   *
   * The composite key shape changed from `"model_id|metric"` (2-part)
   * to `"model_id|config_id|metric"` (3-part). Issue #111:
   *  - If exactly one config is selected, do an exact 3-part lookup so
   *    the summary row matches the per-config chart/table below.
   *  - Otherwise (multiple configs selected) the summary row spans
   *    multiple configs; pick the entry with the highest `n_runs` —
   *    the user-facing intent is "how many distinct runs were there for
   *    this model + metric?".
   */
  const formatRunsAggregate = (
    modelId: string,
    metricName: string
  ): string | null => {
    const block = (statisticsData as any)?.runs_by_model_metric
    if (!block) return null
    let entry: any = null
    if (selectedConfigIds.length === 1) {
      const exactKey = `${modelId}|${selectedConfigIds[0]}|${metricName}`
      entry = block[exactKey] ?? null
    }
    if (!entry) {
      const prefix = `${modelId}|`
      const suffix = `|${metricName}`
      for (const [k, v] of Object.entries(block)) {
        if (k.startsWith(prefix) && k.endsWith(suffix)) {
          if (!entry || ((v as any)?.n_runs ?? 0) > (entry.n_runs ?? 0)) {
            entry = v
          }
        }
      }
    }
    if (!entry || !entry.n_runs || entry.n_runs < 2) return null
    const std = typeof entry.std_of_means === 'number' ? entry.std_of_means : null
    return std !== null
      ? `± ${std.toFixed(3)} (${entry.n_runs} runs)`
      : `(${entry.n_runs} runs)`
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
    configs: SampleEvaluationResult['evaluation_configs']
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
      {/* In-flight runs banner — surfaces every `pending`/`running` run
          with per-run cancel and a bulk "cancel all" so an operator can
          stop a runaway or duplicate dispatch without resorting to
          kubectl exec / direct SQL. Partial scores survive cancel; a
          subsequent `force_rerun=false` re-trigger picks up where the
          cancelled run left off. */}
      <InflightRunsBanner
        projectId={String(projectId)}
        evaluations={results.evaluations}
        onChanged={fetchResults}
      />
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
                  // Issue #111: persist by evaluation_config.id so two
                  // configs of the same metric type round-trip
                  // independently across page reloads.
                  localStorage.setItem(`eval-selected-config-${projectId}`, v)
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
          {/* By-run chart toggle (multi-run feature, migration 042). Only
              meaningful when statisticsData has per_run_means_by_model_metric
              data; hidden otherwise so the toggle isn't a no-op. */}
          {(statisticsData as any)?.per_run_means_by_model_metric && (
            <label className="flex cursor-pointer items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
              <input
                type="checkbox"
                checked={byRunChart}
                onChange={(e) => setByRunChart(e.target.checked)}
                className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              {t('evaluation.multiFieldResults.byRunChart', 'Diagramm pro Lauf splitten')}
            </label>
          )}
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
       (selectedConfigIds === undefined || selectedConfigIds.length > 0) &&
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
                      const runsLine = firstMetric ? formatRunsAggregate(modelId, firstMetric) : null

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
                              {runsLine && (
                                <span
                                  className="text-xs font-normal text-blue-600 dark:text-blue-400"
                                  title={t('evaluation.multiFieldResults.runsAggregateTooltip', 'Standard deviation across distinct evaluation runs (multi-run feature)')}
                                >
                                  {runsLine}
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
