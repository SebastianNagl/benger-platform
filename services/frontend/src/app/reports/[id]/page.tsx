/**
 * Report Viewer Page - Display Published Project Reports
 *
 * Displays complete project reports with:
 * - Project information and custom content
 * - Statistics (tasks, annotations, participants, models)
 * - Participant list with contribution counts
 * - Model information
 * - Evaluation results with interactive charts
 *
 * Issue #770: Project Reports Publishing System
 */

'use client'

import { Breadcrumb } from '@/components/shared/Breadcrumb'
import {
  ChartTypeSelector,
  type ChartType,
} from '@/components/evaluation/ChartTypeSelector'
import { DynamicChartRenderer } from '@/components/evaluation/DynamicChartRenderer'
import { useI18n } from '@/contexts/I18nContext'
import { getReportData, type ReportDataResponse } from '@/lib/api/reports'
import { ChevronDownIcon } from '@heroicons/react/24/outline'
import { useRouter } from 'next/navigation'
import { use, useCallback, useEffect, useMemo, useRef, useState } from 'react'

const REPORT_VIEW_TYPES: ChartType[] = ['data', 'bar', 'radar', 'table', 'heatmap']
const DEFAULT_REPORT_VIEW: ChartType = 'data'
const DEFAULT_AVAILABLE_VIEWS: ChartType[] = ['data']

interface ChartsConfig {
  visible_metrics?: string[]
  available_views?: ChartType[]
  default_view?: ChartType
}

function MetricMultiSelect({
  metrics,
  labels,
  selected,
  onChange,
  placeholder,
}: {
  metrics: string[]
  labels: Record<string, string>
  selected: Set<string>
  onChange: (next: Set<string>) => void
  placeholder: string
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const summary =
    selected.size === 0
      ? placeholder
      : selected.size === metrics.length
        ? `${metrics.length} / ${metrics.length}`
        : `${selected.size} / ${metrics.length}`

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex h-8 items-center justify-between gap-2 whitespace-nowrap rounded-full bg-white px-4 py-1.5 text-sm font-medium text-zinc-900 ring-1 ring-zinc-900/10 transition hover:ring-zinc-900/20 focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:bg-white/5 dark:text-white dark:ring-inset dark:ring-white/10 dark:hover:ring-white/20"
      >
        <span>{summary}</span>
        <ChevronDownIcon
          className={`h-4 w-4 shrink-0 opacity-70 transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>
      {open && (
        <div className="absolute left-0 z-50 mt-1 max-h-72 w-64 overflow-auto rounded-lg border border-gray-200 bg-white py-1 shadow-lg dark:border-gray-700 dark:bg-gray-800">
          {metrics.map((metric) => {
            const checked = selected.has(metric)
            return (
              <label
                key={metric}
                className="flex cursor-pointer items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-gray-700"
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => {
                    const next = new Set(selected)
                    if (next.has(metric)) next.delete(metric)
                    else next.add(metric)
                    onChange(next)
                  }}
                  className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500"
                />
                <span className="capitalize">{labels[metric] || metric}</span>
              </label>
            )
          })}
        </div>
      )}
    </div>
  )
}

interface ParticipantsModalProps {
  isOpen: boolean
  onClose: () => void
  participants: Array<{
    id: string
    username: string
    annotation_count: number
  }>
}

function ParticipantsModal({
  isOpen,
  onClose,
  participants,
}: ParticipantsModalProps) {
  const { t } = useI18n()
  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
      <div className="max-h-[80vh] w-full max-w-2xl overflow-auto rounded-lg bg-white p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-xl font-semibold">{t('reports.detail.participants')}</h3>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700"
          >
            ✕
          </button>
        </div>

        <div className="space-y-3">
          {participants.map((participant) => (
            <div
              key={participant.id}
              className="flex items-center justify-between rounded border border-gray-200 p-3"
            >
              <span className="font-medium">{participant.username}</span>
              <span className="text-gray-600">
                {t('reports.detail.annotationCount', { count: participant.annotation_count })}
              </span>
            </div>
          ))}
        </div>

        <div className="mt-6 flex justify-end">
          <button
            onClick={onClose}
            className="rounded bg-gray-200 px-4 py-2 hover:bg-gray-300"
          >
            {t('reports.detail.close')}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function ReportViewerPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { t } = useI18n()
  const router = useRouter()
  const { id } = use(params)
  const [reportData, setReportData] = useState<ReportDataResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showParticipants, setShowParticipants] = useState(false)
  const [chartView, setChartView] = useState<ChartType | null>(null)
  const [selectedMetrics, setSelectedMetrics] = useState<Set<string> | null>(
    null
  )

  const loadReportData = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await getReportData(id)
      setReportData(data)
    } catch (err: any) {
      console.error('Failed to load report data:', err)
      setError(err.message || t('reports.detail.failedToLoadReport'))
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    loadReportData()
  }, [loadReportData])

  // ---- Hooks below this line must run on every render. Place all useMemo /
  // useEffect calls here, BEFORE any early returns, so React's hook order is
  // stable across loading / error / loaded states.

  const sectionsForCharts = reportData?.report.content.sections
  const evaluationChartsResp = reportData?.evaluation_charts

  const chartConfig = useMemo(() => {
    if (!evaluationChartsResp?.by_model || !sectionsForCharts) return null

    const allKeys = Object.keys(evaluationChartsResp.by_model)
    if (allKeys.length === 0) return null

    const llmModelNames = allKeys.filter((k) => !k.startsWith('annotator:'))
    const annotatorNames = allKeys.filter((k) => k.startsWith('annotator:'))

    const allMetricNames = Array.from(
      new Set(
        allKeys.flatMap((k) =>
          Object.keys(evaluationChartsResp.by_model[k] || {})
        )
      )
    )
    if (allMetricNames.length === 0) return null

    const visibleSelection = (
      sectionsForCharts.evaluation as { charts_config?: ChartsConfig }
    ).charts_config?.visible_metrics
    const metricNames = Array.isArray(visibleSelection)
      ? allMetricNames.filter((m) => visibleSelection.includes(m))
      : allMetricNames
    if (metricNames.length === 0) return null

    const metadata = evaluationChartsResp.metric_metadata || {}

    const scale01Metrics: string[] = []
    const scale15Metrics: string[] = []
    metricNames.forEach((metricName) => {
      const meta = metadata[metricName]
      if (meta && meta.range) {
        const [min, max] = meta.range
        if (min >= 1 && max <= 5) {
          scale15Metrics.push(metricName)
        } else {
          scale01Metrics.push(metricName)
        }
      } else {
        scale01Metrics.push(metricName)
      }
    })

    return {
      llmModelNames,
      annotatorNames,
      scale01Metrics,
      scale15Metrics,
      metadata,
    }
  }, [evaluationChartsResp, sectionsForCharts])

  const hasLlmCharts = (chartConfig?.llmModelNames.length ?? 0) > 0
  const hasAnnotatorCharts = (chartConfig?.annotatorNames.length ?? 0) > 0

  const evaluationChartsConfig: ChartsConfig = useMemo(
    () =>
      (sectionsForCharts?.evaluation as { charts_config?: ChartsConfig })
        ?.charts_config || {},
    [sectionsForCharts]
  )

  const availableViewsList = useMemo(() => {
    const fromConfig = evaluationChartsConfig.available_views
    return Array.isArray(fromConfig) && fromConfig.length > 0
      ? fromConfig.filter((v) => REPORT_VIEW_TYPES.includes(v))
      : DEFAULT_AVAILABLE_VIEWS
  }, [evaluationChartsConfig.available_views])

  const defaultViewFromConfig: ChartType = useMemo(() => {
    const persisted = evaluationChartsConfig.default_view
    if (persisted && availableViewsList.includes(persisted)) return persisted
    return availableViewsList[0] || DEFAULT_REPORT_VIEW
  }, [evaluationChartsConfig.default_view, availableViewsList])

  const activeView = chartView ?? defaultViewFromConfig
  // The 'data' view on /evaluations is a "no chart, just the table" mode.
  // DynamicChartRenderer doesn't have a dedicated 'data' branch, so alias it
  // to 'table' for rendering. The selector still shows 'data' to the user.
  const renderedView: ChartType = activeView === 'data' ? 'table' : activeView

  const metricLabels = useMemo(() => {
    const meta = evaluationChartsResp?.metric_metadata || {}
    const labels: Record<string, string> = {}
    if (chartConfig) {
      const universe = new Set<string>([
        ...chartConfig.scale01Metrics,
        ...chartConfig.scale15Metrics,
      ])
      universe.forEach((m) => {
        labels[m] = (meta[m] && meta[m].name) || m.replace(/_/g, ' ')
      })
    }
    return labels
  }, [evaluationChartsResp, chartConfig])

  const allChartMetrics = useMemo(
    () =>
      chartConfig
        ? Array.from(
            new Set([
              ...chartConfig.scale01Metrics,
              ...chartConfig.scale15Metrics,
            ])
          )
        : [],
    [chartConfig]
  )

  useEffect(() => {
    if (selectedMetrics === null && allChartMetrics.length > 0) {
      setSelectedMetrics(new Set(allChartMetrics))
    }
  }, [allChartMetrics, selectedMetrics])

  const activeMetrics = selectedMetrics
    ? allChartMetrics.filter((m) => selectedMetrics.has(m))
    : allChartMetrics

  // ---- End of hooks. Early returns below are now safe.

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-lg">{t('reports.detail.loadingReport')}</div>
      </div>
    )
  }

  if (error || !reportData) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="rounded-lg border border-red-200 bg-red-50 p-6 dark:border-red-800 dark:bg-red-950/50">
          <div className="text-red-700 dark:text-red-400">
            {error || t('reports.detail.reportNotFound')}
          </div>
          <div className="mt-4 flex gap-3">
            <button
              onClick={loadReportData}
              className="rounded-md bg-red-600 px-4 py-2 text-white hover:bg-red-700 dark:bg-red-700 dark:hover:bg-red-600"
            >
              {t('reports.detail.retry')}
            </button>
            <button
              onClick={() => router.push('/reports')}
              className="rounded-md bg-gray-200 px-4 py-2 hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600"
            >
              {t('reports.detail.backToReports')}
            </button>
          </div>
        </div>
      </div>
    )
  }

  const { report, statistics, participants, models, evaluation_charts } =
    reportData
  const { sections } = report.content

  const generationReady =
    sections.generation.status === 'completed' ||
    Boolean(sections.generation.custom_text) ||
    models.length > 0

  const evaluationReady =
    sections.evaluation.status === 'completed' ||
    Boolean(sections.evaluation.custom_interpretation) ||
    Boolean(sections.evaluation.conclusions) ||
    hasLlmCharts ||
    hasAnnotatorCharts

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      {/* Breadcrumb */}
      <div className="mb-4">
        <Breadcrumb
          items={[
            {
              label: t('navigation.dashboard') || 'Dashboard',
              href: '/dashboard',
            },
            {
              label: t('navigation.reports') || 'Reports',
              href: '/reports',
            },
            {
              label: report.project_title,
              href: `/reports/${id}`,
            },
          ]}
        />
      </div>

      {/* Project Info Section */}
      <div className="mb-8 rounded-lg bg-white p-6 shadow">
        <h2 className="mb-4 text-2xl font-semibold">
          {t('reports.detail.project')}
        </h2>
        <p className="text-lg font-medium text-gray-900">
          {sections.project_info.custom_title || report.project_title}
        </p>
        <p className="mt-2 text-gray-700">
          {sections.project_info.custom_description ||
            sections.project_info.description}
        </p>
        {report.published_at && (
          <p className="mt-3 text-sm text-gray-500">
            {t('reports.detail.publishedOn', { date: new Date(report.published_at).toLocaleDateString() })}
          </p>
        )}
      </div>

      {/* Statistics Grid */}
      <div className="mb-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg bg-white p-6 shadow">
          <div className="text-sm font-medium text-gray-500">{t('reports.detail.tasks')}</div>
          <div className="mt-2 text-3xl font-bold">{statistics.task_count}</div>
        </div>

        {sections.annotations.visible && sections.annotations.show_count && (
          <div className="rounded-lg bg-white p-6 shadow">
            <div className="text-sm font-medium text-gray-500">{t('reports.detail.annotations')}</div>
            <div className="mt-2 text-3xl font-bold">
              {statistics.annotation_count}
            </div>
          </div>
        )}

        {sections.annotations.visible &&
          sections.annotations.show_participants && (
            <div className="rounded-lg bg-white p-6 shadow">
              <div className="text-sm font-medium text-gray-500">
                {t('reports.detail.participants')}
              </div>
              <div className="mt-2 flex items-baseline justify-between">
                <div className="text-3xl font-bold">
                  {statistics.participant_count}
                </div>
                <button
                  onClick={() => setShowParticipants(true)}
                  className="text-sm text-blue-600 hover:underline"
                >
                  {t('reports.detail.viewAll')}
                </button>
              </div>
            </div>
          )}

        <div className="rounded-lg bg-white p-6 shadow">
          <div className="text-sm font-medium text-gray-500">
            {t('reports.detail.modelsEvaluated')}
          </div>
          <div className="mt-2 text-3xl font-bold">
            {statistics.model_count}
          </div>
        </div>
      </div>

      {/* Data Section */}
      {sections.data.visible && (
        <div className="mb-8 rounded-lg bg-white p-6 shadow">
          <h2 className="mb-4 text-2xl font-semibold">{t('reports.detail.data')}</h2>
          <p className="text-gray-700">
            {sections.data.custom_text ||
              t('reports.detail.defaultDataText', { count: statistics.task_count })}
          </p>
        </div>
      )}

      {/* Annotations Section */}
      {sections.annotations.visible && (
        <div className="mb-8 rounded-lg bg-white p-6 shadow">
          <h2 className="mb-4 text-2xl font-semibold">{t('reports.detail.annotationsSection')}</h2>
          <p className="text-gray-700">
            {sections.annotations.custom_text ||
              t('reports.detail.defaultAnnotationsText', { annotationCount: statistics.annotation_count, participantCount: statistics.participant_count })}
          </p>
          {sections.annotations.acknowledgment_text && (
            <div className="mt-4 rounded-lg bg-gray-50 p-4">
              <p className="text-sm italic text-gray-700">
                {sections.annotations.acknowledgment_text}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Generation Section */}
      {sections.generation.visible && generationReady && (
        <div className="mb-8 rounded-lg bg-white p-6 shadow">
          <h2 className="mb-4 text-2xl font-semibold">{t('reports.detail.generation')}</h2>
          <p className="mb-4 text-gray-700">
            {sections.generation.custom_text ||
              t('reports.detail.defaultGenerationText')}
          </p>
          {sections.generation.show_models !== false && models.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {models.map((model) => (
                <span
                  key={model}
                  className="inline-block rounded bg-blue-100 px-3 py-1 text-sm font-medium text-blue-800"
                >
                  {model}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Evaluation Section */}
      {sections.evaluation.visible && evaluationReady && (
        <div className="mb-8 rounded-lg bg-white p-6 shadow">
          <h2 className="mb-4 text-2xl font-semibold">{t('reports.detail.evaluationResults')}</h2>

          {sections.evaluation.custom_interpretation && (
            <div className="mb-6">
              <h3 className="mb-2 text-lg font-medium">{t('reports.detail.interpretation')}</h3>
              <p className="text-gray-700">
                {sections.evaluation.custom_interpretation}
              </p>
            </div>
          )}

          {/* Viewer controls — pick which metrics to display and how. */}
          {chartConfig && (hasLlmCharts || hasAnnotatorCharts) && (
            <div className="mb-6 flex flex-wrap items-center gap-3">
              <MetricMultiSelect
                metrics={allChartMetrics}
                labels={metricLabels}
                selected={selectedMetrics ?? new Set(allChartMetrics)}
                onChange={setSelectedMetrics}
                placeholder={t('common.filters.search') || 'Metrics'}
              />
              <ChartTypeSelector
                selectedType={activeView}
                onChange={setChartView}
                availableTypes={availableViewsList}
              />
            </div>
          )}

          {chartConfig && hasLlmCharts && (
            <div className="mb-6">
              <h3 className="mb-4 text-lg font-medium">
                {t('reports.detail.performanceByModel')}
              </h3>
              <div className="rounded border border-gray-200 p-4 dark:border-gray-700">
                <DynamicChartRenderer
                  chartType={renderedView}
                  models={chartConfig.llmModelNames.map((id) => ({
                    model_id: id,
                    metrics:
                      (evaluation_charts?.by_model[id] as Record<
                        string,
                        number
                      >) || {},
                  }))}
                  metrics={activeMetrics}
                  height={Math.max(
                    400,
                    chartConfig.llmModelNames.length * 24 + 160
                  )}
                  showErrorBars={false}
                />
              </div>
            </div>
          )}

          {chartConfig && hasAnnotatorCharts && (
            <div className="mb-6">
              <h3 className="mb-4 text-lg font-medium">
                {t('reports.detail.performanceByAnnotator')}
              </h3>
              <div className="rounded border border-gray-200 p-4 dark:border-gray-700">
                <DynamicChartRenderer
                  chartType={renderedView}
                  models={chartConfig.annotatorNames.map((id) => ({
                    model_id: id,
                    model_name: id.startsWith('annotator:')
                      ? id.slice('annotator:'.length)
                      : id,
                    metrics:
                      (evaluation_charts?.by_model[id] as Record<
                        string,
                        number
                      >) || {},
                  }))}
                  metrics={activeMetrics}
                  height={Math.max(
                    400,
                    chartConfig.annotatorNames.length * 22 + 160
                  )}
                  showErrorBars={false}
                />
              </div>
            </div>
          )}

          {sections.evaluation.conclusions && (
            <div className="rounded-lg bg-gray-50 p-4">
              <h3 className="mb-2 text-lg font-medium">{t('reports.detail.conclusions')}</h3>
              <p className="text-gray-700">{sections.evaluation.conclusions}</p>
            </div>
          )}
        </div>
      )}

      {/* Participants Modal */}
      <ParticipantsModal
        isOpen={showParticipants}
        onClose={() => setShowParticipants(false)}
        participants={participants}
      />
    </div>
  )
}
