/**
 * Evaluation Results Viewer
 *
 * Clean, dropdown-based interface for viewing evaluation results.
 * All evaluation configuration and starting belongs in project details.
 */

'use client'

import {
  AggregationLevel,
  AggregationSelector,
} from '@/components/evaluation/AggregationSelector'
import {
  ChartTypeSelector,
  type ChartType,
} from '@/components/evaluation/ChartTypeSelector'
import { DynamicChartRenderer } from '@/components/evaluation/DynamicChartRenderer'
import { EvaluationResultsTable } from '@/components/evaluation/EvaluationResultsTable'
import {
  FieldPairSelector,
  type FieldPair,
} from '@/components/evaluation/FieldPairSelector'
import { EvaluationControlModal } from '@/components/evaluation/EvaluationControlModal'
import {
  ChartData,
  EvaluationResults,
} from '@/components/evaluation/EvaluationResults'
import { ScoreCard } from '@/components/evaluation/ScoreCard'
import { StatisticalResultsPanel } from '@/components/evaluation/StatisticalResultsPanel'
import {
  StatisticalMethod,
  StatisticsSelector,
} from '@/components/evaluation/StatisticsSelector'
import { HistoricalTrendChart } from '@/components/evaluation/charts/HistoricalTrendChart'
import { SignificanceHeatmap } from '@/components/evaluation/charts/SignificanceHeatmap'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Button } from '@/components/shared/Button'
import { Card } from '@/components/shared/Card'
import { FeatureFlag } from '@/components/shared/FeatureFlag'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/shared/Select'
import { useToast } from '@/components/shared/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { useOperationToasts } from '@/hooks/useOperationToasts'
import { apiClient } from '@/lib/api/client'
import { projectsAPI } from '@/lib/api/projects'
import { Project } from '@/types/labelStudio'
import { parseSubdomain } from '@/lib/utils/subdomain'
import { canAccessProjectData } from '@/utils/permissions'
import {
  ChartBarIcon,
  ChevronDownIcon,
  ExclamationTriangleIcon,
  PlayIcon,
} from '@heroicons/react/24/outline'
import { useRouter, useSearchParams } from 'next/navigation'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

// Evaluation types for filtering
type EvalType = 'automated' | 'llm-judge' | 'human'

// Interface for items with configuration and result status
interface ItemWithStatus {
  id: string
  label: string
  isConfigured: boolean
  hasResults: boolean
  resultCount?: number
}

// Model with status flags
interface ModelWithStatus {
  model_id: string
  model_name: string
  provider: string
  is_configured: boolean
  has_generations: boolean
  has_results: boolean
  evaluation_count: number
  total_samples: number
  last_evaluated: string | null
  average_score: number | null
  ci_lower: number | null
  ci_upper: number | null
}

interface EvaluationResult {
  id: string
  project_id: string
  project_name: string
  model_id: string
  metrics: Record<string, number>
  samples_evaluated: number
  created_at: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  evaluation_type: 'automated' | 'human'
}

export default function EvaluationDashboard() {
  const router = useRouter()
  const { addToast } = useToast()
  const { startEvaluation, updateEvaluation, renderToasts } =
    useOperationToasts()
  const { t } = useI18n()
  const searchParams = useSearchParams()
  const { user, isLoading: authLoading } = useAuth()
  const { isPrivateMode } = typeof window !== 'undefined' ? parseSubdomain() : { isPrivateMode: true }

  // Filter state - all in one compact bar
  const [selectedProject, setSelectedProject] = useState<Project | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [projectDropdownOpen, setProjectDropdownOpen] = useState(false)
  const [selectedModels, setSelectedModels] = useState<string[]>([])
  const [selectedMetrics, setSelectedMetrics] = useState<string[]>([])
  const [availableMetrics, setAvailableMetrics] = useState<string[]>([])
  const [selectedEvalTypes, setSelectedEvalTypes] = useState<EvalType[]>([
    'automated',
    'llm-judge',
    'human',
  ])
  const [modelsDropdownOpen, setModelsDropdownOpen] = useState(false)
  const [aggregationLevels, setAggregationLevels] = useState<
    AggregationLevel[]
  >(['model'])
  const [statisticalMethods, setStatisticalMethods] = useState<
    StatisticalMethod[]
  >([])

  const [chartType, setChartType] = useState<ChartType>('data')
  const [selectedFieldPairs, setSelectedFieldPairs] = useState<string[]>([])
  const [fieldPairs, setFieldPairs] = useState<FieldPair[]>([])
  const [showEvaluationModal, setShowEvaluationModal] = useState(false)

  // Metric parameter state for metrics with configurable parameters
  const [metricParams, setMetricParams] = useState<{
    // ROUGE
    rougeVariant: 'rouge1' | 'rouge2' | 'rougeL' | 'rougeLsum'
    // BLEU
    bleuNgram: 1 | 2 | 3 | 4
    bleuSmoothing: 'method1' | 'method2' | 'method3' | 'method4'
    // METEOR
    meteorAlpha: number
    meteorBeta: number
    meteorGamma: number
    // chrF
    chrfCharOrder: number
    chrfWordOrder: number
    chrfBeta: number
  }>({
    rougeVariant: 'rougeL',
    bleuNgram: 4,
    bleuSmoothing: 'method1',
    meteorAlpha: 0.9,
    meteorBeta: 3.0,
    meteorGamma: 0.5,
    chrfCharOrder: 6,
    chrfWordOrder: 0,
    chrfBeta: 2,
  })
  const [metricParamsDropdownOpen, setMetricParamsDropdownOpen] =
    useState(false)
  const metricParamsDropdownRef = useRef<HTMLDivElement>(null)

  // Helper to check which metrics with params are selected
  const hasMetricWithParams = selectedMetrics.some((m) =>
    ['rouge', 'bleu', 'meteor', 'chrf'].includes(m.toLowerCase())
  )

  // Project evaluation config - source of truth for available eval types and metrics
  const [projectEvalConfig, setProjectEvalConfig] = useState<{
    selected_methods?: Record<
      string,
      {
        automated: Array<
          string | { name: string; parameters: Record<string, any> }
        >
        human: string[]
        field_mapping?: {
          prediction_field: string
          reference_field: string
        }
      }
    >
    evaluation_configs?: Array<{
      id: string
      metric: string
      display_name?: string
      metric_parameters?: Record<string, any>
      prediction_fields: string[]
      reference_fields: string[]
      enabled: boolean
    }>
  } | null>(null)
  // Available eval types derived from project config (not hard-coded)
  const [availableEvalTypes, setAvailableEvalTypes] = useState<EvalType[]>([])
  // Track if project has any evaluation configuration
  const [hasAnyConfiguration, setHasAnyConfiguration] = useState(false)
  // Track which metrics have actual results
  const [metricsWithStatus, setMetricsWithStatus] = useState<ItemWithStatus[]>(
    []
  )
  const [metricsDropdownOpen, setMetricsDropdownOpen] = useState(false)
  const metricsDropdownRef = useRef<HTMLDivElement>(null)
  // Track if evaluation is currently running
  const [runningEvaluation, setRunningEvaluation] = useState(false)
  // Track if evaluation results exist (reported by EvaluationResults)
  const [hasEvaluationResults, setHasEvaluationResults] = useState(false)
  // Track if auto-run has been attempted for current project (prevents duplicate runs)
  const [autoRunAttempted, setAutoRunAttempted] = useState(false)
  // Chart data from evaluation results
  const [evaluationChartData, setEvaluationChartData] = useState<ChartData[]>(
    []
  )
  // Key to trigger EvaluationResults refresh when evaluation completes
  const [resultsRefreshKey, setResultsRefreshKey] = useState(0)

  // Results state - auto-updated when filters change
  const [loading, setLoading] = useState(false)
  const [evaluationResults, setEvaluationResults] = useState<
    EvaluationResult[]
  >([])
  const [evaluatedModels, setEvaluatedModels] = useState<any[]>([])
  const [historicalData, setHistoricalData] = useState<any>(null)
  const [significanceData, setSignificanceData] = useState<any[]>([])
  const [significanceError, setSignificanceError] = useState<string | null>(null)
  const [statisticsData, setStatisticsData] = useState<any>(null)
  const [statisticsLoading, setStatisticsLoading] = useState(false)
  const [statisticsError, setStatisticsError] = useState<string | null>(null)

  const projectDropdownRef = useRef<HTMLDivElement>(null)
  const modelsDropdownRef = useRef<HTMLDivElement>(null)

  // Load projects after auth completes
  useEffect(() => {
    if (authLoading) return
    const loadProjects = async () => {
      try {
        const response = await projectsAPI.list(1, 100)
        // API returns 'items' field for paginated results
        setProjects(response.items || [])
      } catch (err) {
        console.error('Failed to load projects:', err)
      }
    }
    loadProjects()
  }, [authLoading])

  // Close dropdowns when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        projectDropdownRef.current &&
        !projectDropdownRef.current.contains(event.target as Node)
      ) {
        setProjectDropdownOpen(false)
      }
      if (
        modelsDropdownRef.current &&
        !modelsDropdownRef.current.contains(event.target as Node)
      ) {
        setModelsDropdownOpen(false)
      }
      if (
        metricParamsDropdownRef.current &&
        !metricParamsDropdownRef.current.contains(event.target as Node)
      ) {
        setMetricParamsDropdownOpen(false)
      }
      if (
        metricsDropdownRef.current &&
        !metricsDropdownRef.current.contains(event.target as Node)
      ) {
        setMetricsDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Track if we've applied URL filters (to avoid re-applying on data refresh)
  const urlFiltersApplied = useRef(false)
  // Skip URL sync until initial hydration is complete (prevents flicker)
  const isHydrated = useRef(false)

  // Load project from URL on mount, or fall back to last selected project from localStorage
  useEffect(() => {
    const projectId = searchParams?.get('projectId') || localStorage.getItem('evaluations_lastProjectId')
    if (projectId && projects.length > 0 && !selectedProject) {
      const project = projects.find((p) => p.id.toString() === projectId)
      if (project) {
        setSelectedProject(project)
      }
    }

    // Load non-data-dependent filters from URL immediately
    const urlChartType = searchParams?.get('chartType') as ChartType
    if (urlChartType && ['data', 'bar', 'radar', 'box', 'heatmap', 'table'].includes(urlChartType)) {
      setChartType(urlChartType)
    }

    const urlAggregation = searchParams?.get('aggregation')
    if (urlAggregation) {
      const levels = urlAggregation.split(',').filter(Boolean) as AggregationLevel[]
      if (levels.length > 0) {
        setAggregationLevels(levels)
      }
    }

    const urlStats = searchParams?.get('stats')
    if (urlStats) {
      const methods = urlStats.split(',').filter(Boolean) as StatisticalMethod[]
      if (methods.length > 0) {
        setStatisticalMethods(methods)
      }
    }
  }, [searchParams, projects, selectedProject])

  // Apply URL filters for models/metrics AFTER data is loaded
  useEffect(() => {
    if (urlFiltersApplied.current) return
    if (evaluatedModels.length === 0 && availableMetrics.length === 0) return

    const urlModels = searchParams?.get('models')
    const urlMetrics = searchParams?.get('metrics')

    // Only mark as applied if we actually have URL params to apply
    // Otherwise, the defaults from fetchProjectData will be used
    if (urlModels || urlMetrics) {
      urlFiltersApplied.current = true

      if (urlModels && evaluatedModels.length > 0) {
        const modelIds = urlModels.split(',').filter(Boolean)
        // Only set models that exist in evaluatedModels
        const validModels = modelIds.filter(id =>
          evaluatedModels.some(m => m.model_id === id)
        )
        if (validModels.length > 0) {
          setSelectedModels(validModels)
        }
      }

      if (urlMetrics && availableMetrics.length > 0) {
        const metricIds = urlMetrics.split(',').filter(Boolean)
        // Only set metrics that exist in availableMetrics
        const validMetrics = metricIds.filter(id => availableMetrics.includes(id))
        if (validMetrics.length > 0) {
          setSelectedMetrics(validMetrics)
        }
      }
    }
  }, [searchParams, evaluatedModels, availableMetrics])

  // Fetch data when project changes (instant reactive loading)
  useEffect(() => {
    if (selectedProject) {
      // Persist last selected project for next visit
      localStorage.setItem('evaluations_lastProjectId', selectedProject.id.toString())
      // Reset URL filters applied flag when project changes
      urlFiltersApplied.current = false
      fetchProjectData(selectedProject.id.toString())
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fetchProjectData is stable, only re-run when selectedProject changes
  }, [selectedProject])

  // Sync all filters to URL (skip during initial hydration to avoid flicker)
  useEffect(() => {
    if (!selectedProject) return
    if (!isHydrated.current) {
      isHydrated.current = true
      return
    }

    const params = new URLSearchParams()
    params.set('projectId', selectedProject.id.toString())

    // Only save models to URL if not all models are selected (avoid long URLs)
    if (selectedModels.length > 0 && selectedModels.length < evaluatedModels.length) {
      params.set('models', selectedModels.join(','))
    }
    // Only save metrics to URL if not all metrics are selected
    if (selectedMetrics.length > 0 && selectedMetrics.length < availableMetrics.length) {
      params.set('metrics', selectedMetrics.join(','))
    }
    if (chartType !== 'data') {
      params.set('chartType', chartType)
    }
    if (aggregationLevels.length > 0 && aggregationLevels[0] !== 'model') {
      params.set('aggregation', aggregationLevels.join(','))
    }
    if (statisticalMethods.length > 0 && !(statisticalMethods.length === 1 && statisticalMethods[0] === 'ci')) {
      params.set('stats', statisticalMethods.join(','))
    }

    router.replace(`/evaluations?${params.toString()}`, { scroll: false })
    // eslint-disable-next-line react-hooks/exhaustive-deps -- Only sync when filter values change
  }, [selectedProject, selectedModels, selectedMetrics, chartType, aggregationLevels, statisticalMethods, evaluatedModels.length, availableMetrics.length])

  // Fetch comparison data when models/metrics change (instant reactive)
  useEffect(() => {
    if (
      selectedProject &&
      selectedModels.length > 0 &&
      selectedMetrics.length > 0
    ) {
      fetchComparisonData()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fetchComparisonData is stable, only re-run when filter selections change
  }, [selectedModels, selectedMetrics, selectedProject])

  // Auto-compute statistics when aggregation/methods/models change
  useEffect(() => {
    if (
      selectedProject &&
      selectedMetrics.length > 0 &&
      aggregationLevels.length > 0
    ) {
      computeStatistics()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- computeStatistics is stable, only re-run when filter selections change
  }, [aggregationLevels, statisticalMethods, selectedMetrics, selectedModels, selectedProject])

  // Auto-run evaluation when configured but no results exist yet
  useEffect(() => {
    // Only auto-run if:
    // 1. Project is selected
    // 2. Has evaluation configuration
    // 3. No evaluation results exist yet
    // 4. Haven't attempted auto-run for this project visit
    // 5. Not currently loading or running
    if (
      selectedProject &&
      hasAnyConfiguration &&
      !hasEvaluationResults &&
      !autoRunAttempted &&
      !loading &&
      !runningEvaluation
    ) {
      setAutoRunAttempted(true)
      // Small delay to ensure UI is ready
      const timer = setTimeout(() => {
        handleRunEvaluation()
      }, 1000)
      return () => clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- handleRunEvaluation is stable, only re-run when conditions change
  }, [
    selectedProject,
    hasAnyConfiguration,
    hasEvaluationResults,
    autoRunAttempted,
    loading,
    runningEvaluation,
  ])

  const fetchProjectData = async (projectId: string) => {
    setLoading(true)
    try {
      // 1. Fetch project evaluation config - source of truth for available methods
      // NO FALLBACK - if config fetch fails, show empty state
      let evalConfig: any = null
      try {
        evalConfig =
          await apiClient.evaluations.getProjectEvaluationConfig(projectId)
        setProjectEvalConfig(evalConfig)
      } catch (configError) {
        console.error('Failed to fetch evaluation config:', configError)
        setProjectEvalConfig(null)
      }

      // 2. Fetch configured methods with result status
      let configuredMethods: any = null
      try {
        configuredMethods =
          await apiClient.evaluations.getConfiguredMethods(projectId)
      } catch {
        configuredMethods = { fields: [] }
      }

      // 3. Check if project has evaluation configuration
      const selectedMethods = evalConfig?.selected_methods || {}
      // Support current key (evaluation_configs) and legacy key (multi_field_evaluations)
      let evaluationConfigs = evalConfig?.evaluation_configs || evalConfig?.multi_field_evaluations || []

      // Bridge: derive evaluation configs from selected_methods for legacy projects
      const hasSelectedMethods = Object.values(selectedMethods).some(
        (m: any) => m.automated?.length > 0 || m.human?.length > 0
      )
      if (evaluationConfigs.length === 0 && hasSelectedMethods) {
        evaluationConfigs = Object.entries(selectedMethods)
          .flatMap(([fieldName, selections]: [string, any]) =>
            (selections.automated || []).map((metric: any) => {
              const metricName = typeof metric === 'string' ? metric : metric.name
              return {
                id: `${fieldName}_${metricName}`,
                metric: metricName,
                display_name: metricName.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase()),
                prediction_fields: [selections.field_mapping?.prediction_field || fieldName].filter(Boolean),
                reference_fields: [selections.field_mapping?.reference_field || fieldName].filter(Boolean),
                enabled: true,
                metric_parameters: typeof metric === 'object' ? metric.parameters : undefined,
              }
            })
          )
      }

      const hasConfig = evaluationConfigs.length > 0

      setHasAnyConfiguration(hasConfig)

      // 4. Derive eval types from config only - do NOT show historical results without config
      if (!hasConfig) {
        // No config - show empty state, don't derive from historical results
        setAvailableEvalTypes([])
        setSelectedEvalTypes([])
        setAvailableMetrics([])
        setSelectedMetrics([])
        setMetricsWithStatus([])
      } else {
        const enabledEvalConfigs = evaluationConfigs.filter(
          (e: any) => e.enabled !== false
        )
        const hasAutomatedConfig = enabledEvalConfigs.some(
          (e: any) => !e.metric?.startsWith('llm_judge')
        )
        const hasLlmJudgeConfig = enabledEvalConfigs.some(
          (e: any) => e.metric?.startsWith('llm_judge')
        )
        const hasHumanConfig = Object.values(selectedMethods).some(
          (m: any) => m.human?.length > 0
        )

        // Build eval types from config
        const derivedEvalTypes: EvalType[] = []

        if (hasAutomatedConfig) {
          derivedEvalTypes.push('automated')
        }
        if (hasLlmJudgeConfig) {
          derivedEvalTypes.push('llm-judge')
        }
        if (hasHumanConfig) {
          derivedEvalTypes.push('human')
        }

        setAvailableEvalTypes(derivedEvalTypes)
        setSelectedEvalTypes(derivedEvalTypes)

        // Build metrics with status from config only - NO FALLBACK
        const configuredMetricNames = enabledEvalConfigs.map(
          (e: any) => e.metric
        )
        const uniqueMetrics = [...new Set(configuredMetricNames)] as string[]

        // Flatten automated_methods from configuredMethods for status lookup
        const allAutomatedMethods = (configuredMethods?.fields || []).flatMap(
          (f: any) => f.automated_methods || []
        )

        const metricsStatus: ItemWithStatus[] = uniqueMetrics.map(
          (metricName) => {
            const methodInfo = allAutomatedMethods.find(
              (m: any) => m.method_name === metricName
            )
            return {
              id: metricName,
              label: metricName
                .replace(/_/g, ' ')
                .replace(/\b\w/g, (c: string) => c.toUpperCase()),
              isConfigured: true,
              hasResults: methodInfo?.has_results || false,
              resultCount: methodInfo?.result_count || 0,
            }
          }
        )

        setAvailableMetrics(uniqueMetrics)
        // Check if URL has metrics param - if so, don't override
        const urlMetrics = searchParams?.get('metrics')
        if (!urlMetrics) {
          // Select all metrics by default
          setSelectedMetrics(uniqueMetrics)
        }
        setMetricsWithStatus(metricsStatus)
      }

      // 5. Fetch evaluation results
      try {
        const resultsResponse = await apiClient.get(
          `/evaluations/results/${projectId}`
        )
        setEvaluationResults(resultsResponse.data || [])
      } catch {
        setEvaluationResults([])
      }

      // 6. Fetch models with include_configured=true to show all configured models
      try {
        const modelsResponse = await apiClient.evaluations.getEvaluatedModels(
          projectId,
          true
        )
        setEvaluatedModels(modelsResponse || [])

        // Check if URL has models param - if so, don't override
        const urlModels = searchParams?.get('models')
        if (!urlModels) {
          // Select ALL models by default
          if (modelsResponse?.length > 0) {
            setSelectedModels(modelsResponse.map((m: any) => m.model_id))
          }
        }
      } catch {
        setEvaluatedModels([])
      }

    } catch (error) {
      console.error('Failed to fetch project data:', error)
      addToast(t('toasts.evaluation.dataFailed'), 'error')
    } finally {
      setLoading(false)
    }
  }

  const fetchComparisonData = async () => {
    if (!selectedProject) return
    try {
      // Historical data
      if (selectedMetrics.length > 0) {
        try {
          const history = await apiClient.evaluations.getEvaluationHistory({
            projectId: selectedProject.id.toString(),
            modelIds: selectedModels,
            metric: selectedMetrics[0],
          })
          setHistoricalData(history)
        } catch {
          setHistoricalData(null)
        }
      }

      // Significance data
      if (selectedModels.length > 1) {
        try {
          const significance = await apiClient.evaluations.getSignificanceTests(
            {
              projectId: selectedProject.id.toString(),
              modelIds: selectedModels,
              metrics: selectedMetrics,
            }
          )
          setSignificanceData(significance.comparisons || [])
          setSignificanceError(null)
        } catch (err: any) {
          setSignificanceData([])
          setSignificanceError(err?.message || 'Failed to load significance data')
        }
      } else {
        setSignificanceError(null)
      }
    } catch (err) {
      console.error('Failed to fetch comparison data:', err)
    }
  }

  const computeStatistics = async () => {
    if (
      !selectedProject ||
      selectedMetrics.length === 0 ||
      aggregationLevels.length === 0
    )
      return

    setStatisticsLoading(true)
    setStatisticsError(null)
    try {
      // Call API for each selected aggregation level and combine results
      const results: Record<string, any> = {}
      const errors: string[] = []

      for (const aggregation of aggregationLevels) {
        try {
          const result = await apiClient.evaluations.computeStatistics({
            projectId: selectedProject.id.toString(),
            metrics: selectedMetrics,
            aggregation: aggregation,
            methods: statisticalMethods,
            compareModels: selectedModels.length > 1 ? selectedModels : undefined,
          })
          results[aggregation] = result
        } catch (err: any) {
          // Capture error message for this aggregation level
          const errorMsg = err?.message || err?.detail || `Failed to compute ${aggregation} statistics`
          errors.push(errorMsg)
          results[aggregation] = null
        }
      }

      // If all aggregations failed, show error
      const successfulResults = Object.values(results).filter(r => r !== null)
      if (successfulResults.length === 0 && errors.length > 0) {
        setStatisticsError(errors[0]) // Show first error
        setStatisticsData(null)
        return
      }

      // If only one aggregation selected, use the legacy format for backward compatibility
      if (aggregationLevels.length === 1) {
        setStatisticsData(results[aggregationLevels[0]])
      } else {
        // Multiple aggregations: store as object keyed by level
        // For display, use the first non-null result as the primary
        const primaryResult = aggregationLevels.find(
          (level) => results[level] !== null
        )
        setStatisticsData({
          ...results[primaryResult || aggregationLevels[0]],
          _multiAggregation: results, // Store all results for multi-view
        })
      }
    } catch (err: any) {
      const errorMsg = err?.message || 'Failed to compute statistics'
      setStatisticsError(errorMsg)
      setStatisticsData(null)
    } finally {
      setStatisticsLoading(false)
    }
  }

  // Subscribe to evaluation status via SSE for real-time updates
  const subscribeToEvaluationStatus = useCallback(
    (evaluationId: string, configCount: number) => {
      // Use same-origin proxy route to avoid CORS issues with EventSource
      // The proxy forwards cookies to the backend API
      const eventSource = new EventSource(
        `/api/evaluations/stream/${evaluationId}`
      )

      eventSource.addEventListener('status', (event) => {
        const data = JSON.parse(event.data)
        if (data.status === 'running') {
          updateEvaluation(
            evaluationId,
            'running',
            t('evaluation.viewer.status.processing'),
            `${data.samples_evaluated || 0} ${t('evaluation.viewer.status.samplesEvaluated')}`
          )
        } else if (data.status === 'pending') {
          updateEvaluation(
            evaluationId,
            'started',
            t('evaluation.viewer.status.queued'),
            t('evaluation.viewer.status.waitingWorker')
          )
        }
      })

      eventSource.addEventListener('done', (event) => {
        const data = JSON.parse(event.data)
        if (data.status === 'completed') {
          updateEvaluation(
            evaluationId,
            'completed',
            t('evaluation.viewer.status.complete'),
            `${data.samples_evaluated} ${t('evaluation.viewer.status.samplesEvaluated')}`
          )
          // Summary toast for completion
          addToast(
            t('toasts.evaluation.complete', { count: data.samples_evaluated || 0 }),
            'success'
          )
          // Refresh data after completion
          if (selectedProject) {
            fetchProjectData(selectedProject.id.toString())
          }
          // Trigger EvaluationResults refresh
          setResultsRefreshKey((prev) => prev + 1)
        } else if (data.status === 'failed') {
          updateEvaluation(
            evaluationId,
            'failed',
            t('evaluation.viewer.status.failed'),
            data.error_message || t('evaluation.viewer.status.unknownError')
          )
          // Summary toast for failure
          addToast(t('toasts.evaluation.failed'), 'error')
        }
        setRunningEvaluation(false)
        eventSource.close()
      })

      eventSource.addEventListener('error', () => {
        updateEvaluation(
          evaluationId,
          'failed',
          t('evaluation.viewer.status.connectionLost'),
          t('evaluation.viewer.status.unableToTrack')
        )
        setRunningEvaluation(false)
        eventSource.close()
      })

      return eventSource
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fetchProjectData is stable
    [updateEvaluation, selectedProject]
  )

  // Handler to run evaluation on the spot
  const handleRunEvaluation = async (forceRerun: boolean = false) => {
    if (!selectedProject) return

    setRunningEvaluation(true)
    try {
      // Get configs from the current project's evaluation_config
      // Support current key (evaluation_configs) and legacy key (multi_field_evaluations)
      let evaluationConfigs =
        projectEvalConfig?.evaluation_configs || (projectEvalConfig as any)?.multi_field_evaluations || []

      // Bridge: derive from selected_methods for legacy projects
      if (evaluationConfigs.length === 0) {
        const sm = projectEvalConfig?.selected_methods || {}
        const hasSM = Object.values(sm).some(
          (m: any) => m.automated?.length > 0
        )
        if (hasSM) {
          evaluationConfigs = Object.entries(sm)
            .flatMap(([fieldName, selections]: [string, any]) =>
              (selections.automated || []).map((metric: any) => {
                const metricName = typeof metric === 'string' ? metric : metric.name
                return {
                  id: `${fieldName}_${metricName}`,
                  metric: metricName,
                  prediction_fields: [selections.field_mapping?.prediction_field || fieldName].filter(Boolean),
                  reference_fields: [selections.field_mapping?.reference_field || fieldName].filter(Boolean),
                  enabled: true,
                  metric_parameters: typeof metric === 'object' ? metric.parameters : undefined,
                }
              })
            )
        }
      }

      const configs = evaluationConfigs.filter((e: any) => e.enabled !== false)

      if (configs.length === 0) {
        addToast(
          t('evaluation.noMethodsConfigured'),
          'error'
        )
        setRunningEvaluation(false)
        return
      }

      const response = await apiClient.evaluations.runEvaluation({
        project_id: selectedProject.id.toString(),
        evaluation_configs: configs,
        force_rerun: forceRerun,
      })

      // Use operation toast for real-time status updates
      const evaluationId = response.evaluation_id
      startEvaluation(evaluationId, configs.length)

      // Subscribe to SSE for real-time status updates
      subscribeToEvaluationStatus(evaluationId, configs.length)
    } catch (err: any) {
      console.error('Failed to start evaluation:', err)
      addToast(err.message || t('toasts.evaluation.startFailed'), 'error')
      setRunningEvaluation(false)
    }
  }

  // Filter results by selected models
  const filteredResults = evaluationResults.filter((r) => {
    // Filter by selected models (if any selected)
    // Also match llm-judge:model-id patterns (e.g., llm-judge:gpt-4o matches gpt-4o)
    const modelMatch =
      selectedModels.length === 0 ||
      selectedModels.includes(r.model_id) ||
      selectedModels.some((m) => r.model_id === `llm-judge:${m}`)

    return modelMatch
  })

  // Check permissions
  useEffect(() => {
    if (!authLoading && !canAccessProjectData(user, { isPrivateMode })) {
      router.replace('/projects?error=no-permission')
    }
  }, [user, authLoading, router])

  if (authLoading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <LoadingSpinner />
      </div>
    )
  }

  if (!canAccessProjectData(user, { isPrivateMode })) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <div className="text-center">
          <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">
            {t('evaluation.accessDenied') || 'Access Denied'}
          </h3>
          <Button onClick={() => router.push('/projects')} className="mt-4">
            {t('common.backToProjects') || 'Back to Projects'}
          </Button>
        </div>
      </div>
    )
  }

  const toggleModel = (modelId: string) => {
    if (selectedModels.includes(modelId)) {
      setSelectedModels(selectedModels.filter((m) => m !== modelId))
    } else {
      setSelectedModels([...selectedModels, modelId])
    }
  }


  // Compute disabled chart types dynamically based on actual data availability
  const chartDisabledInfo = useMemo(() => {
    const modelCount = Math.max(
      evaluatedModels.length,
      filteredResults.length > 0 ? filteredResults.length : evaluationChartData.length
    )

    // Check if we have raw_scores for box plot (requires sample aggregation)
    const hasRawScores =
      statisticsData?.raw_scores?.length > 0 ||
      statisticsData?._multiAggregation?.sample?.raw_scores?.length > 0

    const disabledTypes: ChartType[] = []
    const disabledReasons: Partial<Record<ChartType, string>> = {}

    // Heatmap requires 2+ models
    if (modelCount < 2) {
      disabledTypes.push('heatmap')
      disabledReasons.heatmap = t('evaluation.viewer.chart.disabledReasons.heatmapNeedsModels')
    }

    // Box plot requires distribution data (raw scores from sample aggregation)
    if (!hasRawScores) {
      disabledTypes.push('box')
      // Provide clear, actionable messaging based on current state
      if (!aggregationLevels.includes('sample')) {
        disabledReasons.box = t('evaluation.viewer.chart.disabledReasons.boxNeedsSampleAggregation')
      } else if (statisticsError) {
        disabledReasons.box = `Error: ${statisticsError}`
      } else if (statisticsLoading) {
        disabledReasons.box = t('evaluation.viewer.chart.disabledReasons.boxComputingScores')
      } else {
        disabledReasons.box = t('evaluation.viewer.chart.disabledReasons.boxNoSampleData')
      }
    }

    return { disabledTypes, disabledReasons }
  }, [evaluatedModels, filteredResults, evaluationChartData, statisticsData, aggregationLevels, statisticsError, statisticsLoading, t])

  // Prepare model data with scores for box plots
  const modelsWithScores = useMemo(() => {
    // Get base model data
    const baseModels = filteredResults.length > 0
      ? filteredResults.map((r) => ({
          model_id: r.model_id,
          model_name: r.model_id,
          metrics: r.metrics || {},
          scores: [] as number[],
        }))
      : evaluationChartData.map((r) => ({
          model_id: r.model_id,
          model_name: r.model_name || r.model_id,
          metrics: r.metrics || {},
          scores: [] as number[],
        }))

    // If we have raw_scores, add them to the models
    const rawScores =
      statisticsData?.raw_scores ||
      statisticsData?._multiAggregation?.sample?.raw_scores ||
      []

    if (rawScores.length > 0) {
      // Group scores by model for the selected metrics
      const scoresByModel = new Map<string, number[]>()
      for (const score of rawScores) {
        if (selectedMetrics.includes(score.metric)) {
          const existing = scoresByModel.get(score.model_id) || []
          existing.push(score.value)
          scoresByModel.set(score.model_id, existing)
        }
      }

      // Add scores to matching models
      for (const model of baseModels) {
        const modelScores = scoresByModel.get(model.model_id)
        if (modelScores) {
          model.scores = modelScores
        }
      }
    }

    return baseModels
  }, [filteredResults, evaluationChartData, statisticsData, selectedMetrics])

  return (
    <FeatureFlag
      flag="evaluations"
      fallback={
        <ResponsiveContainer
          size="full"
          className="px-4 pb-10 pt-8 sm:px-6 lg:px-8"
        >
          <div className="py-12 text-center">
            <h1 className="mb-4 text-2xl font-semibold text-gray-600">
              {t('evaluation.notAvailable') ||
                'Evaluation System Not Available'}
            </h1>
          </div>
        </ResponsiveContainer>
      }
    >
      <ResponsiveContainer
        size="full"
        className="px-4 pb-10 pt-8 sm:px-6 lg:px-8"
      >
        {/* Breadcrumb */}
        <div className="mb-4">
          <Breadcrumb
            items={[
              { label: t('navigation.dashboard'), href: '/dashboard' },
              {
                label: t('navigation.evaluation') || 'Evaluation',
                href: '/evaluations',
              },
            ]}
          />
        </div>

        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">
              {t('evaluation.viewer.title')}
            </h1>
            <p className="mt-1 text-gray-600 dark:text-gray-400">
              {selectedProject
                ? t('evaluation.viewer.viewingResults', { project: selectedProject.title })
                : t('evaluation.viewer.selectProjectDescription')}
            </p>
          </div>
          <Button
            variant="outline"
            onClick={() => router.push('/leaderboards?tab=llm')}
          >
            <ChartBarIcon className="mr-2 h-4 w-4" />
            {t('evaluation.viewer.llmLeaderboard')}
          </Button>
        </div>

        {/* Filter Bar - All dropdowns in one row */}
        <Card className="mb-2 p-4">
          <div className="flex flex-wrap items-end gap-3">
            {/* Project Dropdown */}
            <div className="relative" ref={projectDropdownRef}>
              <label className="mb-1 block text-xs font-medium text-gray-500">
                {t('evaluation.viewer.filters.project')}
              </label>
              <Button
                variant="outline"
                onClick={() => setProjectDropdownOpen(!projectDropdownOpen)}
                className="w-40 justify-between"
              >
                <span className="truncate">
                  {selectedProject?.title || t('evaluation.viewer.filters.selectProject')}
                </span>
                <ChevronDownIcon
                  className={`ml-2 h-4 w-4 opacity-70 transition-transform ${projectDropdownOpen ? 'rotate-180' : ''}`}
                />
              </Button>
              {projectDropdownOpen && (
                <div className="absolute z-50 mt-1 max-h-60 w-64 overflow-auto rounded-lg border border-gray-200 bg-white shadow-lg dark:border-gray-700 dark:bg-gray-800">
                  {projects.map((project) => (
                    <button
                      key={project.id}
                      onClick={() => {
                        setSelectedProject(project)
                        setProjectDropdownOpen(false)
                        setAutoRunAttempted(false) // Reset auto-run for new project
                      }}
                      className={`w-full px-3 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-700 ${
                        selectedProject?.id === project.id
                          ? 'bg-emerald-50 dark:bg-emerald-900/20'
                          : ''
                      }`}
                    >
                      <div className="font-medium">{project.title}</div>
                      <div className="text-xs text-gray-500">
                        {project.task_count || 0} {t('evaluation.viewer.filters.tasks')}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Models Dropdown */}
            {selectedProject && evaluatedModels.length > 0 && (
              <div className="relative" ref={modelsDropdownRef}>
                <label className="mb-1 block text-xs font-medium text-gray-500">
                  {t('evaluation.viewer.filters.models')}
                </label>
                <Button
                  variant="outline"
                  onClick={() => setModelsDropdownOpen(!modelsDropdownOpen)}
                  className="w-32 justify-between"
                >
                  <span className="truncate">
                    {selectedModels.length === 0
                      ? t('evaluation.viewer.filters.allModels')
                      : selectedModels.length === evaluatedModels.length
                        ? t('evaluation.viewer.filters.allModels')
                        : `${selectedModels.length} ${t('evaluation.viewer.filters.selected')}`}
                  </span>
                  <ChevronDownIcon
                    className={`ml-2 h-4 w-4 opacity-70 transition-transform ${modelsDropdownOpen ? 'rotate-180' : ''}`}
                  />
                </Button>
                {modelsDropdownOpen && (
                  <div className="absolute z-50 mt-1 max-h-60 w-64 overflow-auto rounded-lg border border-gray-200 bg-white p-2 shadow-lg dark:border-gray-700 dark:bg-gray-800">
                    <button
                      type="button"
                      onClick={() =>
                        setSelectedModels(
                          evaluatedModels
                            .filter((m) => m.has_results !== false)
                            .map((m) => m.model_id)
                        )
                      }
                      className="mb-1 w-full px-2 py-1 text-left text-xs text-emerald-600 hover:text-emerald-700 dark:text-emerald-400"
                    >
                      {t('evaluation.viewer.filters.selectAll')}
                    </button>
                    <button
                      type="button"
                      onClick={() => setSelectedModels([])}
                      className="mb-2 w-full px-2 py-1 text-left text-xs text-gray-500 hover:text-gray-700 dark:text-gray-400"
                    >
                      {t('evaluation.viewer.filters.clearAll')}
                    </button>
                    {evaluatedModels.map((model) => (
                      <label
                        key={model.model_id}
                        className={`flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 ${
                          model.has_results !== false
                            ? 'hover:bg-gray-50 dark:hover:bg-gray-700'
                            : 'opacity-50'
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={selectedModels.includes(model.model_id)}
                          onChange={() => toggleModel(model.model_id)}
                          className="rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
                        />
                        <span className={`flex-1 truncate text-sm ${model.model_id.startsWith('annotator:') ? 'text-blue-700 dark:text-blue-300' : ''}`}>
                          {model.model_id.startsWith('annotator:')
                            ? model.model_id.replace(/^annotator:/, '')
                            : (model.model_name || model.model_id)}
                        </span>
                        {model.has_results === false && (
                          <span className="flex items-center gap-0.5 whitespace-nowrap text-xs text-amber-600 dark:text-amber-400">
                            <ExclamationTriangleIcon className="h-3 w-3" />
                            {t('evaluation.viewer.filters.noResults')}
                          </span>
                        )}
                        {model.is_configured && !model.has_generations && (
                          <span className="flex items-center gap-0.5 whitespace-nowrap text-xs text-gray-400">
                            <ExclamationTriangleIcon className="h-3 w-3" />
                            {t('evaluation.viewer.filters.notRun')}
                          </span>
                        )}
                      </label>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Metrics Dropdown - shows all configured metric variants */}
            {selectedProject && metricsWithStatus.length > 0 && (
              <div className="relative" ref={metricsDropdownRef}>
                <label className="mb-1 block text-xs font-medium text-gray-500">
                  {t('evaluation.viewer.filters.metrics')}
                </label>
                <Button
                  variant="outline"
                  onClick={() => setMetricsDropdownOpen(!metricsDropdownOpen)}
                  className="w-36 justify-between"
                >
                  <span className="truncate">
                    {selectedMetrics.length === 0
                      ? t('evaluation.viewer.filters.selectMetrics')
                      : selectedMetrics.length === metricsWithStatus.length
                        ? t('evaluation.viewer.filters.allMetrics')
                        : `${selectedMetrics.length} ${t('evaluation.viewer.filters.selected')}`}
                  </span>
                  <ChevronDownIcon
                    className={`ml-2 h-4 w-4 opacity-70 transition-transform ${metricsDropdownOpen ? 'rotate-180' : ''}`}
                  />
                </Button>
                {metricsDropdownOpen && (
                  <div className="absolute z-50 mt-1 max-h-60 w-56 overflow-auto rounded-lg border border-gray-200 bg-white p-2 shadow-lg dark:border-gray-700 dark:bg-gray-800">
                    <button
                      type="button"
                      onClick={() =>
                        setSelectedMetrics(metricsWithStatus.map((m) => m.id))
                      }
                      className="mb-1 w-full px-2 py-1 text-left text-xs text-emerald-600 hover:text-emerald-700 dark:text-emerald-400"
                    >
                      {t('evaluation.viewer.filters.selectAll')}
                    </button>
                    <button
                      type="button"
                      onClick={() => setSelectedMetrics([])}
                      className="mb-2 w-full px-2 py-1 text-left text-xs text-gray-500 hover:text-gray-700 dark:text-gray-400"
                    >
                      {t('evaluation.viewer.filters.clearAll')}
                    </button>
                    {metricsWithStatus.map((metric) => (
                      <label
                        key={metric.id}
                        className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 hover:bg-gray-50 dark:hover:bg-gray-700"
                      >
                        <input
                          type="checkbox"
                          checked={selectedMetrics.includes(metric.id)}
                          onChange={() => {
                            if (selectedMetrics.includes(metric.id)) {
                              setSelectedMetrics(
                                selectedMetrics.filter((m) => m !== metric.id)
                              )
                            } else {
                              setSelectedMetrics([
                                ...selectedMetrics,
                                metric.id,
                              ])
                            }
                          }}
                          className="rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
                        />
                        <span className="flex-1 truncate text-sm">
                          {metric.label}
                        </span>
                        {metric.hasResults && (
                          <span className="text-xs text-emerald-600 dark:text-emerald-400">
                            ✓
                          </span>
                        )}
                      </label>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Aggregation Dropdown */}
            {selectedProject && (
              <div className="w-36">
                <label className="mb-1 block text-xs font-medium text-gray-500">
                  {t('evaluation.viewer.filters.aggregation')}
                </label>
                <AggregationSelector
                  levels={aggregationLevels}
                  onChange={setAggregationLevels}
                />
              </div>
            )}

            {/* Statistics Methods */}
            {selectedProject && (
              <div className="w-32">
                <label className="mb-1 block text-xs font-medium text-gray-500">
                  {t('evaluation.viewer.filters.statistics')}
                </label>
                <StatisticsSelector
                  selectedMethods={statisticalMethods}
                  onChange={setStatisticalMethods}
                />
              </div>
            )}

            {/* Metric Parameters - show when metrics with parameters are selected */}
            {selectedProject && hasMetricWithParams && (
              <div className="relative" ref={metricParamsDropdownRef}>
                <label className="mb-1 block text-xs font-medium text-gray-500">
                  {t('evaluation.viewer.filters.params')}
                </label>
                <Button
                  variant="outline"
                  onClick={() =>
                    setMetricParamsDropdownOpen(!metricParamsDropdownOpen)
                  }
                  className="w-28 justify-between"
                >
                  <span className="truncate text-xs">
                    {[
                      selectedMetrics.some(
                        (m) => m.toLowerCase() === 'rouge'
                      ) && metricParams.rougeVariant,
                      selectedMetrics.some((m) => m.toLowerCase() === 'bleu') &&
                        `B${metricParams.bleuNgram}`,
                      selectedMetrics.some(
                        (m) => m.toLowerCase() === 'meteor'
                      ) && 'MET',
                      selectedMetrics.some((m) => m.toLowerCase() === 'chrf') &&
                        `chr${metricParams.chrfCharOrder}`,
                    ]
                      .filter(Boolean)
                      .join(', ') || t('evaluation.viewer.params.configure')}
                  </span>
                  <ChevronDownIcon
                    className={`ml-1 h-3 w-3 opacity-70 transition-transform ${metricParamsDropdownOpen ? 'rotate-180' : ''}`}
                  />
                </Button>
                {metricParamsDropdownOpen && (
                  <div className="absolute z-50 mt-1 max-h-80 w-64 space-y-4 overflow-y-auto rounded-lg border border-gray-200 bg-white p-3 shadow-lg dark:border-gray-700 dark:bg-gray-800">
                    {/* ROUGE Parameters */}
                    {selectedMetrics.some(
                      (m) => m.toLowerCase() === 'rouge'
                    ) && (
                      <div className="space-y-2">
                        <div className="text-xs font-semibold uppercase tracking-wide text-emerald-600 dark:text-emerald-400">
                          {t('evaluation.viewer.params.rouge.title')}
                        </div>
                        <div>
                          <label className="mb-1 block text-xs text-gray-600 dark:text-gray-400">
                            {t('evaluation.viewer.params.rouge.variant')}
                          </label>
                          <Select
                            value={metricParams.rougeVariant}
                            onValueChange={(v) =>
                              setMetricParams((prev) => ({
                                ...prev,
                                rougeVariant: v as any,
                              }))
                            }
                          >
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="rouge1">{t('evaluation.viewer.params.rouge.rouge1')}</SelectItem>
                              <SelectItem value="rouge2">{t('evaluation.viewer.params.rouge.rouge2')}</SelectItem>
                              <SelectItem value="rougeL">{t('evaluation.viewer.params.rouge.rougeL')}</SelectItem>
                              <SelectItem value="rougeLsum">{t('evaluation.viewer.params.rouge.rougeLsum')}</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                      </div>
                    )}
                    {/* BLEU Parameters */}
                    {selectedMetrics.some(
                      (m) => m.toLowerCase() === 'bleu'
                    ) && (
                      <div className="space-y-2">
                        <div className="text-xs font-semibold uppercase tracking-wide text-blue-600 dark:text-blue-400">
                          {t('evaluation.viewer.params.bleu.title')}
                        </div>
                        <div>
                          <label className="mb-1 block text-xs text-gray-600 dark:text-gray-400">
                            {t('evaluation.viewer.params.bleu.ngramOrder')}
                          </label>
                          <Select
                            value={metricParams.bleuNgram.toString()}
                            onValueChange={(v) =>
                              setMetricParams((prev) => ({
                                ...prev,
                                bleuNgram: parseInt(v) as any,
                              }))
                            }
                          >
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="1">{t('evaluation.viewer.params.bleu.bleu1')}</SelectItem>
                              <SelectItem value="2">{t('evaluation.viewer.params.bleu.bleu2')}</SelectItem>
                              <SelectItem value="3">{t('evaluation.viewer.params.bleu.bleu3')}</SelectItem>
                              <SelectItem value="4">{t('evaluation.viewer.params.bleu.bleu4')}</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                        <div>
                          <label className="mb-1 block text-xs text-gray-600 dark:text-gray-400">
                            {t('evaluation.viewer.params.bleu.smoothing')}
                          </label>
                          <Select
                            value={metricParams.bleuSmoothing}
                            onValueChange={(v) =>
                              setMetricParams((prev) => ({
                                ...prev,
                                bleuSmoothing: v as any,
                              }))
                            }
                          >
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="method1">{t('evaluation.viewer.params.bleu.method1')}</SelectItem>
                              <SelectItem value="method2">{t('evaluation.viewer.params.bleu.method2')}</SelectItem>
                              <SelectItem value="method3">{t('evaluation.viewer.params.bleu.method3')}</SelectItem>
                              <SelectItem value="method4">{t('evaluation.viewer.params.bleu.method4')}</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                      </div>
                    )}
                    {/* METEOR Parameters */}
                    {selectedMetrics.some(
                      (m) => m.toLowerCase() === 'meteor'
                    ) && (
                      <div className="space-y-2">
                        <div className="text-xs font-semibold uppercase tracking-wide text-purple-600 dark:text-purple-400">
                          {t('evaluation.viewer.params.meteor.title')}
                        </div>
                        <div className="grid grid-cols-3 gap-2">
                          <div>
                            <label className="mb-1 block text-xs text-gray-600 dark:text-gray-400">
                              {t('evaluation.viewer.params.meteor.alpha')}
                            </label>
                            <input
                              type="number"
                              value={metricParams.meteorAlpha}
                              onChange={(e) =>
                                setMetricParams((prev) => ({
                                  ...prev,
                                  meteorAlpha: parseFloat(e.target.value),
                                }))
                              }
                              min={0}
                              max={1}
                              step={0.1}
                              className="w-full rounded border border-gray-300 bg-white px-2 py-1 text-sm dark:border-gray-600 dark:bg-gray-700"
                            />
                          </div>
                          <div>
                            <label className="mb-1 block text-xs text-gray-600 dark:text-gray-400">
                              {t('evaluation.viewer.params.meteor.beta')}
                            </label>
                            <input
                              type="number"
                              value={metricParams.meteorBeta}
                              onChange={(e) =>
                                setMetricParams((prev) => ({
                                  ...prev,
                                  meteorBeta: parseFloat(e.target.value),
                                }))
                              }
                              min={0}
                              max={10}
                              step={0.5}
                              className="w-full rounded border border-gray-300 bg-white px-2 py-1 text-sm dark:border-gray-600 dark:bg-gray-700"
                            />
                          </div>
                          <div>
                            <label className="mb-1 block text-xs text-gray-600 dark:text-gray-400">
                              {t('evaluation.viewer.params.meteor.gamma')}
                            </label>
                            <input
                              type="number"
                              value={metricParams.meteorGamma}
                              onChange={(e) =>
                                setMetricParams((prev) => ({
                                  ...prev,
                                  meteorGamma: parseFloat(e.target.value),
                                }))
                              }
                              min={0}
                              max={1}
                              step={0.1}
                              className="w-full rounded border border-gray-300 bg-white px-2 py-1 text-sm dark:border-gray-600 dark:bg-gray-700"
                            />
                          </div>
                        </div>
                      </div>
                    )}
                    {/* chrF Parameters */}
                    {selectedMetrics.some(
                      (m) => m.toLowerCase() === 'chrf'
                    ) && (
                      <div className="space-y-2">
                        <div className="text-xs font-semibold uppercase tracking-wide text-orange-600 dark:text-orange-400">
                          {t('evaluation.viewer.params.chrf.title')}
                        </div>
                        <div className="grid grid-cols-3 gap-2">
                          <div>
                            <label className="mb-1 block text-xs text-gray-600 dark:text-gray-400">
                              {t('evaluation.viewer.params.chrf.charNgram')}
                            </label>
                            <Select
                              value={metricParams.chrfCharOrder.toString()}
                              onValueChange={(v) =>
                                setMetricParams((prev) => ({
                                  ...prev,
                                  chrfCharOrder: parseInt(v),
                                }))
                              }
                            >
                              <SelectTrigger>
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                {[1, 2, 3, 4, 5, 6].map((n) => (
                                  <SelectItem key={n} value={n.toString()}>
                                    {n}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>
                          <div>
                            <label className="mb-1 block text-xs text-gray-600 dark:text-gray-400">
                              {t('evaluation.viewer.params.chrf.wordNgram')}
                            </label>
                            <Select
                              value={metricParams.chrfWordOrder.toString()}
                              onValueChange={(v) =>
                                setMetricParams((prev) => ({
                                  ...prev,
                                  chrfWordOrder: parseInt(v),
                                }))
                              }
                            >
                              <SelectTrigger>
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                {[0, 1, 2].map((n) => (
                                  <SelectItem key={n} value={n.toString()}>
                                    {n}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>
                          <div>
                            <label className="mb-1 block text-xs text-gray-600 dark:text-gray-400">
                              {t('evaluation.viewer.params.chrf.beta')}
                            </label>
                            <Select
                              value={metricParams.chrfBeta.toString()}
                              onValueChange={(v) =>
                                setMetricParams((prev) => ({
                                  ...prev,
                                  chrfBeta: parseInt(v),
                                }))
                              }
                            >
                              <SelectTrigger>
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                {[1, 2, 3].map((n) => (
                                  <SelectItem key={n} value={n.toString()}>
                                    {n}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* View Type Selector - inline with dropdowns */}
            {selectedProject && (
              <div className="flex flex-col">
                <label className="mb-1 block text-xs font-medium text-gray-500">
                  {t('evaluation.viewer.filters.view')}
                </label>
                <ChartTypeSelector
                  selectedType={chartType}
                  onChange={setChartType}
                  disabledTypes={chartDisabledInfo.disabledTypes}
                  disabledReasons={chartDisabledInfo.disabledReasons}
                  size="sm"
                />
              </div>
            )}

            {/* Field Pair Selector */}
            {selectedProject && fieldPairs.length > 0 && (
              <FieldPairSelector
                fieldPairs={fieldPairs}
                selectedPairs={selectedFieldPairs}
                onChange={setSelectedFieldPairs}
                className="w-52"
              />
            )}
          </div>
        </Card>

        {/* Clear All Filters - below the filter box */}
        {selectedProject && (
          <button
            type="button"
            onClick={() => {
              setChartType('data')
              setAggregationLevels(['model'])
              setStatisticalMethods([])
              setSelectedModels(evaluatedModels.map((m) => m.model_id))
              setSelectedMetrics(availableMetrics)
              setSelectedFieldPairs([])
              setSelectedEvalTypes(['automated', 'llm-judge', 'human'])
            }}
            className="mb-4 text-sm text-gray-500 transition hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
          >
            {t('evaluation.viewer.filters.clearAllFilters')}
          </button>
        )}

        {/* Loading State */}
        {loading && (
          <div className="flex items-center justify-center py-12">
            <LoadingSpinner />
          </div>
        )}

        {/* Results Section - Only show when project selected and not loading */}
        {selectedProject && !loading && (
          <div className="space-y-6">
            {/* Score Cards */}
            {filteredResults.length > 0 && (
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
                {filteredResults.slice(0, 1).flatMap((result) =>
                  Object.entries(result.metrics || {})
                    .slice(0, 4)
                    .map(([key, value]) => (
                      <ScoreCard
                        key={key}
                        metric={key}
                        value={value}
                        description={`${key} for ${result.model_id}`}
                        higherIsBetter={true}
                        formatAs="decimal"
                        sampleSize={result.samples_evaluated}
                      />
                    ))
                )}
              </div>
            )}

            {/* Dynamic Chart Rendering - use evaluationChartData when filteredResults is empty */}
            {/* For 'data' view, only show the view selector and table - no charts */}
            {(filteredResults.length > 0 || evaluationChartData.length > 0) &&
              selectedMetrics.length > 0 &&
              chartType !== 'data' && (
                <Card className="p-6">
                  <div className="mb-4 flex items-center justify-between">
                    <h3 className="text-lg font-medium dark:text-white">
                      {t('evaluation.viewer.chart.title')}
                    </h3>
                    <ChartTypeSelector
                      selectedType={chartType}
                      onChange={setChartType}
                      disabledTypes={chartDisabledInfo.disabledTypes}
                      disabledReasons={chartDisabledInfo.disabledReasons}
                      size="sm"
                    />
                  </div>
                  <DynamicChartRenderer
                    chartType={chartType}
                    models={modelsWithScores}
                    metrics={selectedMetrics}
                    significanceData={significanceData}
                    height={400}
                    showErrorBars={true}
                    emptyMessage={t('evaluation.viewer.chart.noData')}
                  />
                </Card>
              )}

            {/* Results Table */}
            {filteredResults.length > 0 && (
              <Card className="p-6">
                <h3 className="mb-4 text-lg font-medium dark:text-white">
                  {t('evaluation.viewer.results.title')}
                </h3>
                <EvaluationResultsTable
                  results={filteredResults.map((r, idx) => ({
                    modelId: r.model_id,
                    metrics: r.metrics || {},
                    rank: idx + 1,
                  }))}
                />
              </Card>
            )}

            {/* Statistical Results Panel - hidden in data view (stats shown inline there) */}
            {chartType !== 'data' &&
              (statisticsData || statisticsLoading || statisticsError) && (
              <StatisticalResultsPanel
                data={statisticsData}
                loading={statisticsLoading}
                error={statisticsError}
                showBonferroniInfo={true}
                selectedStatistics={statisticalMethods}
              />
            )}

            {/* Historical Trend Chart - hidden in data view */}
            {historicalData?.data?.length > 0 &&
              selectedMetrics.length > 0 &&
              chartType !== 'data' && (
                <Card className="p-6">
                  <h3 className="mb-4 text-lg font-medium dark:text-white">
                    {t('evaluation.viewer.results.historicalTrends')}
                  </h3>
                  <HistoricalTrendChart
                    data={historicalData.data}
                    modelIds={selectedModels}
                    metric={selectedMetrics[0]}
                    height={400}
                    showConfidenceIntervals={true}
                  />
                </Card>
              )}

            {/* Significance Heatmap - hidden in data view */}
            {selectedModels.length > 1 && chartType !== 'data' && (
              <Card className="p-6">
                <h3 className="mb-4 text-lg font-medium dark:text-white">
                  {t('evaluation.viewer.results.statisticalSignificance')}
                </h3>
                {significanceError && (
                  <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-4 text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-400">
                    <strong>{t('evaluation.viewer.results.significanceError')}</strong> {significanceError}
                  </div>
                )}
                {significanceData.length > 0 ? (
                  <SignificanceHeatmap
                    modelIds={selectedModels}
                    metric={selectedMetrics[0] || t('evaluation.viewer.results.score')}
                    significanceData={significanceData}
                    height={500}
                  />
                ) : !significanceError ? (
                  <div className="py-8 text-center text-gray-500 dark:text-gray-400">
                    {t('evaluation.viewer.results.noSignificanceData')}
                  </div>
                ) : null}
              </Card>
            )}

            {/* Evaluation Results - only show Card when configured or has results */}
            {(hasAnyConfiguration || hasEvaluationResults) && (
              <Card className="p-6">
                <EvaluationResults
                  projectId={selectedProject.id}
                  selectedModels={selectedModels}
                  selectedMetrics={selectedMetrics}
                  selectedEvalTypes={selectedEvalTypes}
                  onRefresh={() =>
                    fetchProjectData(selectedProject.id.toString())
                  }
                  hasConfiguration={hasAnyConfiguration}
                  onRunEvaluation={() => setShowEvaluationModal(true)}
                  isRunningEvaluation={runningEvaluation}
                  onResultsLoaded={setHasEvaluationResults}
                  onDataLoaded={setEvaluationChartData}
                  viewType={chartType === 'data' ? 'data' : 'chart'}
                  statisticsData={statisticsData}
                  selectedStatistics={statisticalMethods}
                  refreshKey={resultsRefreshKey}
                  modelNames={Object.fromEntries(
                    evaluatedModels.map((m: any) => [m.model_id, m.model_name || m.model_id])
                  )}
                  evaluationConfigs={projectEvalConfig?.evaluation_configs || []}
                />
              </Card>
            )}

            {/* Empty State - only show when no config exists (EvaluationResults handles its own empty state when configured) */}
            {filteredResults.length === 0 && !hasEvaluationResults && !hasAnyConfiguration && (
              <Card className="p-12 text-center">
                <ChartBarIcon className="mx-auto h-12 w-12 text-gray-400" />
                <h3 className="mt-4 text-lg font-medium text-gray-900 dark:text-white">
                  {t('evaluation.viewer.emptyStates.notConfigured.title')}
                </h3>
                <p className="mt-2 text-gray-500 dark:text-gray-400">
                  {t('evaluation.viewer.emptyStates.notConfigured.description')}
                </p>
                <Button
                  variant="outline"
                  onClick={() =>
                    router.push(`/projects/${selectedProject?.id}`)
                  }
                  className="mt-4"
                >
                  {t('evaluation.viewer.emptyStates.notConfigured.action')}
                </Button>
              </Card>
            )}
          </div>
        )}

        {/* No Project Selected */}
        {!selectedProject && !loading && (
          <Card className="p-12 text-center">
            <ChartBarIcon className="mx-auto h-12 w-12 text-gray-400" />
            <h3 className="mt-4 text-lg font-medium text-gray-900 dark:text-white">
              {t('evaluation.viewer.emptyStates.selectProject.title')}
            </h3>
            <p className="mt-2 text-gray-500 dark:text-gray-400">
              {t('evaluation.viewer.emptyStates.selectProject.description')}
            </p>
          </Card>
        )}

        {/* Operation Toasts for evaluation status */}
        {renderToasts()}

        {/* Evaluation Control Modal */}
        <EvaluationControlModal
          isOpen={showEvaluationModal}
          onClose={() => setShowEvaluationModal(false)}
          onRunWithMode={handleRunEvaluation}
          onSuccess={() => setShowEvaluationModal(false)}
        />
      </ResponsiveContainer>
    </FeatureFlag>
  )
}
