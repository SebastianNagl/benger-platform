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
import { useI18n } from '@/contexts/I18nContext'
import { getReportData, type ReportDataResponse } from '@/lib/api/reports'
import dynamic from 'next/dynamic'
import { useRouter } from 'next/navigation'
import { use, useCallback, useEffect, useState } from 'react'

// Dynamically import Plotly to avoid SSR issues
const Plot = dynamic(() => import('react-plotly.js'), { ssr: false })

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

  // Prepare chart data for evaluation metrics, grouped by scale
  const prepareChartData = () => {
    if (!evaluation_charts?.by_model) return null

    const modelNames = Object.keys(evaluation_charts.by_model)
    if (modelNames.length === 0) return null

    const metricNames = Object.keys(
      evaluation_charts.by_model[modelNames[0]] || {}
    )
    if (metricNames.length === 0) return null

    const metadata = evaluation_charts.metric_metadata || {}

    // Group metrics by scale range
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
        // Default to 0-1 scale
        scale01Metrics.push(metricName)
      }
    })

    return { modelNames, scale01Metrics, scale15Metrics, metadata }
  }

  const chartConfig = prepareChartData()

  // Helper to create chart traces for a set of metrics
  const createChartTraces = (metricNames: string[], modelNames: string[]) => {
    const metadata = evaluation_charts?.metric_metadata || {}
    return metricNames.map((metricName) => {
      const meta = metadata[metricName]
      const displayName = meta?.name || metricName.replace(/_/g, ' ')
      return {
        x: modelNames,
        y: modelNames.map(
          (model) => evaluation_charts?.by_model[model]?.[metricName] || 0
        ),
        type: 'bar' as const,
        name: displayName,
      }
    })
  }

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
              label: sections.project_info.custom_title || sections.project_info.title,
              href: `/reports/${id}`,
            },
          ]}
        />
      </div>

      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">
          {sections.project_info.custom_title || sections.project_info.title}
        </h1>
        <p className="mt-2 text-gray-600">
          {sections.project_info.custom_description ||
            sections.project_info.description}
        </p>
        {report.published_at && (
          <p className="mt-2 text-sm text-gray-500">
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
      {sections.generation.visible && (
        <div className="mb-8 rounded-lg bg-white p-6 shadow">
          <h2 className="mb-4 text-2xl font-semibold">{t('reports.detail.generation')}</h2>
          <p className="mb-4 text-gray-700">
            {sections.generation.custom_text ||
              t('reports.detail.defaultGenerationText')}
          </p>
          {sections.generation.show_models && (
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
      {sections.evaluation.visible && (
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

          {/* Evaluation Charts */}
          {chartConfig && (
            <div className="mb-6 space-y-6">
              <h3 className="mb-4 text-lg font-medium">{t('reports.detail.performanceByModel')}</h3>

              {/* QA Metrics Chart (0-1 scale) */}
              {chartConfig.scale01Metrics.length > 0 && (
                <div className="rounded border border-gray-200 p-4">
                  <Plot
                    data={createChartTraces(
                      chartConfig.scale01Metrics,
                      chartConfig.modelNames
                    )}
                    layout={{
                      title: { text: t('reports.detail.qaMetrics') },
                      barmode: 'group',
                      xaxis: { title: { text: t('reports.detail.model') } },
                      yaxis: {
                        title: { text: t('reports.detail.score') },
                        range: [0, 1],
                      },
                      autosize: true,
                      legend: { orientation: 'h', y: -0.2 },
                    }}
                    config={{ responsive: true }}
                    style={{ width: '100%', height: '400px' }}
                  />
                </div>
              )}

              {/* LLM Judge Metrics Chart (1-5 scale) */}
              {chartConfig.scale15Metrics.length > 0 && (
                <div className="rounded border border-gray-200 p-4">
                  <Plot
                    data={createChartTraces(
                      chartConfig.scale15Metrics,
                      chartConfig.modelNames
                    )}
                    layout={{
                      title: { text: t('reports.detail.llmJudgeMetrics') },
                      barmode: 'group',
                      xaxis: { title: { text: t('reports.detail.model') } },
                      yaxis: {
                        title: { text: t('reports.detail.score') },
                        range: [0, 5],
                      },
                      autosize: true,
                      legend: { orientation: 'h', y: -0.2 },
                    }}
                    config={{ responsive: true }}
                    style={{ width: '100%', height: '400px' }}
                  />
                </div>
              )}
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
