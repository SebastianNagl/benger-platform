/**
 * Evaluation Dashboard Component
 *
 * Unified dashboard integrating all evaluation visualization components:
 * - Project/model/metric selection
 * - Summary statistics cards
 * - Leaderboard table
 * - Model comparison charts
 * - Historical trends
 * - Statistical significance
 */

'use client'

import { ProjectSelector } from '@/components/generation/ProjectSelector'
import { Card } from '@/components/shared/Card'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'
import { useI18n } from '@/contexts/I18nContext'
import apiClient from '@/lib/api/client'
import { Project } from '@/types/labelStudio'
import { useCallback, useEffect, useState } from 'react'
import { HistoricalTrendChart } from './charts/HistoricalTrendChart'
import { EvaluationResultsTable } from './EvaluationResultsTable'
import { MetricSelector } from './MetricSelector'
import { ModelComparisonChart } from './ModelComparisonChart'
import { ModelSelector } from './ModelSelector'
import { ScoreCard } from './ScoreCard'

interface EvaluationDashboardProps {
  initialProjectId?: string
}

interface EvaluatedModel {
  model_id: string
  model_name: string
  provider: string
  evaluation_count: number
  total_samples: number
  last_evaluated: string | null
  average_score: number | null
  ci_lower: number | null
  ci_upper: number | null
}

interface SummaryStats {
  totalEvaluations: number
  modelsEvaluated: number
  bestModel: string | null
  avgScore: number
}

interface SignificanceTest {
  model_a: string
  model_b: string
  metric: string
  p_value: number
  significant: boolean
  effect_size: number
  stars: string
}

export function EvaluationDashboard({
  initialProjectId,
}: EvaluationDashboardProps) {
  const { t } = useI18n()
  const [selectedProject, setSelectedProject] = useState<Project | null>(null)
  const [selectedModels, setSelectedModels] = useState<string[]>([])
  const [selectedMetrics, setSelectedMetrics] = useState<string[]>([])
  const [availableMetrics, setAvailableMetrics] = useState<string[]>([])
  const [evaluatedModels, setEvaluatedModels] = useState<EvaluatedModel[]>([])
  const [summaryStats, setSummaryStats] = useState<SummaryStats | null>(null)
  const [historicalData, setHistoricalData] = useState<any>(null)
  const [significanceData, setSignificanceData] = useState<SignificanceTest[]>(
    []
  )
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (initialProjectId) {
      apiClient
        .getProject(parseInt(initialProjectId))
        .then((project: Project) => setSelectedProject(project))
        .catch((err: Error) =>
          setError(`Failed to load project: ${err.message}`)
        )
    }
  }, [initialProjectId])

  const fetchProjectData = useCallback(async () => {
    if (!selectedProject) return

    setLoading(true)
    setError(null)

    try {
      const [models, metrics] = await Promise.all([
        apiClient.evaluations.getEvaluatedModels(selectedProject.id.toString()),
        apiClient.getSupportedMetrics(),
      ])

      setEvaluatedModels(models)
      setAvailableMetrics(metrics.supported_metrics || metrics.metrics || [])

      const modelsWithScores = models.filter((m) => m.average_score !== null)
      const stats: SummaryStats = {
        totalEvaluations: models.reduce(
          (sum, m) => sum + m.evaluation_count,
          0
        ),
        modelsEvaluated: models.length,
        bestModel:
          modelsWithScores.length > 0
            ? modelsWithScores.sort(
                (a, b) => (b.average_score ?? 0) - (a.average_score ?? 0)
              )[0].model_name
            : null,
        avgScore:
          modelsWithScores.length > 0
            ? modelsWithScores.reduce(
                (sum, m) => sum + (m.average_score ?? 0),
                0
              ) / modelsWithScores.length
            : 0,
      }
      setSummaryStats(stats)

      if (models.length > 0) {
        const topModels = models.slice(0, 5).map((m) => m.model_id)
        setSelectedModels(topModels)
      }

      if (
        metrics.supported_metrics?.length > 0 ||
        metrics.metrics?.length > 0
      ) {
        const metricsArr = metrics.supported_metrics || metrics.metrics || []
        setSelectedMetrics(metricsArr.slice(0, 4))
      }
    } catch (err: any) {
      setError(`Failed to load project data: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }, [selectedProject])

  const fetchComparisonData = useCallback(async () => {
    if (
      !selectedProject ||
      selectedModels.length === 0 ||
      selectedMetrics.length === 0
    )
      return

    try {
      const [history, significance] = await Promise.all([
        selectedMetrics.length > 0
          ? apiClient.evaluations.getEvaluationHistory({
              projectId: selectedProject.id.toString(),
              modelIds: selectedModels,
              metric: selectedMetrics[0],
            })
          : Promise.resolve(null),
        selectedModels.length > 1
          ? apiClient.evaluations.getSignificanceTests({
              projectId: selectedProject.id.toString(),
              modelIds: selectedModels,
              metrics: selectedMetrics,
            })
          : Promise.resolve({ comparisons: [] }),
      ])

      setHistoricalData(history)
      setSignificanceData(significance.comparisons)
    } catch (err: any) {
      console.error('Failed to load comparison data:', err)
    }
  }, [selectedProject, selectedModels, selectedMetrics])

  useEffect(() => {
    if (selectedProject) {
      fetchProjectData()
    }
  }, [selectedProject, fetchProjectData])

  useEffect(() => {
    if (
      selectedProject &&
      selectedModels.length > 0 &&
      selectedMetrics.length > 0
    ) {
      fetchComparisonData()
    }
  }, [selectedProject, selectedModels, selectedMetrics, fetchComparisonData])

  const leaderboardData = evaluatedModels.map((model, index) => ({
    modelId: model.model_id,
    modelName: model.model_name,
    rank: index + 1,
    metrics: selectedMetrics.reduce(
      (acc, metric) => {
        acc[metric] = {
          value: model.average_score,
          confidenceInterval:
            model.ci_lower !== null && model.ci_upper !== null
              ? { lower: model.ci_lower, upper: model.ci_upper }
              : undefined,
        }
        return acc
      },
      {} as Record<string, any>
    ),
  }))

  const modelMetrics = evaluatedModels
    .filter((m) => selectedModels.includes(m.model_id))
    .map((model) => ({
      model_id: model.model_name,
      metrics: selectedMetrics.reduce(
        (acc, metric) => {
          acc[metric] = {
            value: model.average_score,
            confidenceInterval:
              model.ci_lower !== null && model.ci_upper !== null
                ? { lower: model.ci_lower, upper: model.ci_upper }
                : undefined,
          }
          return acc
        },
        {} as Record<string, any>
      ),
    }))

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">
          {t('evaluation.dashboard.title')}
        </h1>
        <p className="mt-2 text-gray-600 dark:text-gray-400">
          {t('evaluation.dashboard.description')}
        </p>
      </div>

      {/* Project Selector */}
      <Card className="p-6">
        <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">
          {t('evaluation.dashboard.selectProject')}
        </h2>
        <ProjectSelector
          selectedProjectId={selectedProject?.id.toString()}
          onProjectSelect={setSelectedProject}
        />
      </Card>

      {selectedProject && (
        <>
          {/* Model and Metric Selectors */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <ModelSelector
              projectId={selectedProject.id.toString()}
              selectedModels={selectedModels}
              onSelectionChange={setSelectedModels}
              maxSelections={8}
            />
            <MetricSelector
              availableMetrics={availableMetrics}
              selectedMetrics={selectedMetrics}
              onSelectionChange={setSelectedMetrics}
            />
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-12">
              <LoadingSpinner size="large" />
            </div>
          ) : error ? (
            <Card className="border-red-200 bg-red-50 p-6 dark:border-red-800 dark:bg-red-900/20">
              <p className="text-red-800 dark:text-red-200">{error}</p>
            </Card>
          ) : (
            <>
              {/* Summary Stats Cards */}
              {summaryStats && (
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
                  <ScoreCard
                    metric={t('evaluation.dashboard.totalEvaluations')}
                    value={summaryStats.totalEvaluations}
                    formatAs="raw"
                    valueRange={{
                      min: 0,
                      max: summaryStats.totalEvaluations * 2,
                    }}
                  />
                  <ScoreCard
                    metric={t('evaluation.dashboard.modelsEvaluated')}
                    value={summaryStats.modelsEvaluated}
                    formatAs="raw"
                    valueRange={{
                      min: 0,
                      max: summaryStats.modelsEvaluated * 2,
                    }}
                  />
                  <ScoreCard
                    metric={t('evaluation.dashboard.bestModel')}
                    value={summaryStats.bestModel ? 1 : 0}
                    description={
                      summaryStats.bestModel || t('evaluation.dashboard.noModelsEvaluated')
                    }
                    formatAs="raw"
                    valueRange={{ min: 0, max: 1 }}
                  />
                  <ScoreCard
                    metric={t('evaluation.dashboard.averageScore')}
                    value={summaryStats.avgScore}
                    formatAs="percentage"
                  />
                </div>
              )}

              {/* Main Content Grid */}
              <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                {/* Leaderboard Table */}
                <Card className="p-6 lg:col-span-2">
                  <h2 className="mb-4 text-xl font-semibold text-gray-900 dark:text-gray-100">
                    {t('evaluation.dashboard.modelLeaderboard')}
                  </h2>
                  <EvaluationResultsTable results={leaderboardData} />
                </Card>

                {/* Radar Chart */}
                <Card className="p-6">
                  <ModelComparisonChart
                    models={modelMetrics}
                    metrics={selectedMetrics}
                    visualizationType="radar"
                    title={t('evaluation.dashboard.modelComparisonRadar')}
                    height={350}
                    showErrorBars={false}
                  />
                </Card>

                {/* Bar Chart */}
                <Card className="p-6">
                  <ModelComparisonChart
                    models={modelMetrics}
                    metrics={selectedMetrics}
                    visualizationType="bar"
                    title={t('evaluation.dashboard.modelComparisonBar')}
                    height={350}
                    showErrorBars={true}
                  />
                </Card>
              </div>

              {/* Historical Trend Chart */}
              {historicalData && historicalData.data.length > 0 && (
                <Card className="p-6">
                  <HistoricalTrendChart
                    data={historicalData.data}
                    modelIds={selectedModels}
                    metric={selectedMetrics[0] || 'Score'}
                    height={400}
                    showConfidenceIntervals={true}
                  />
                </Card>
              )}

              {/* Significance Heatmap */}
              {significanceData.length > 0 && selectedModels.length > 1 && (
                <Card className="p-6">
                  <h2 className="mb-4 text-xl font-semibold text-gray-900 dark:text-gray-100">
                    {t('evaluation.dashboard.statisticalSignificance')}
                  </h2>
                  <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
                    {t('evaluation.dashboard.significanceDescription')}
                  </p>
                  <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                      <thead className="bg-gray-50 dark:bg-gray-800">
                        <tr>
                          <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-700 dark:text-gray-300">
                            {t('evaluation.dashboard.modelA')}
                          </th>
                          <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-700 dark:text-gray-300">
                            {t('evaluation.dashboard.modelB')}
                          </th>
                          <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-700 dark:text-gray-300">
                            {t('evaluation.dashboard.metric')}
                          </th>
                          <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wider text-gray-700 dark:text-gray-300">
                            {t('evaluation.dashboard.pValue')}
                          </th>
                          <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wider text-gray-700 dark:text-gray-300">
                            {t('evaluation.dashboard.significance')}
                          </th>
                          <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wider text-gray-700 dark:text-gray-300">
                            {t('evaluation.dashboard.effectSize')}
                          </th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-200 bg-white dark:divide-gray-700 dark:bg-gray-900">
                        {significanceData.map((test, idx) => (
                          <tr
                            key={idx}
                            className="hover:bg-gray-50 dark:hover:bg-gray-800"
                          >
                            <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-900 dark:text-gray-100">
                              {test.model_a}
                            </td>
                            <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-900 dark:text-gray-100">
                              {test.model_b}
                            </td>
                            <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
                              {test.metric}
                            </td>
                            <td className="whitespace-nowrap px-4 py-3 text-center text-sm tabular-nums text-gray-900 dark:text-gray-100">
                              {test.p_value.toFixed(4)}
                            </td>
                            <td className="whitespace-nowrap px-4 py-3 text-center">
                              <span
                                className={`inline-flex rounded-full px-2 py-1 text-xs font-semibold ${
                                  test.significant
                                    ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-200'
                                    : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200'
                                }`}
                              >
                                {test.stars || 'ns'}
                              </span>
                            </td>
                            <td className="whitespace-nowrap px-4 py-3 text-center text-sm tabular-nums text-gray-900 dark:text-gray-100">
                              {test.effect_size.toFixed(3)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Card>
              )}
            </>
          )}
        </>
      )}

      {!selectedProject && (
        <Card className="p-8 text-center">
          <p className="text-gray-500 dark:text-gray-400">
            {t('evaluation.dashboard.selectProjectPrompt')}
          </p>
        </Card>
      )}
    </div>
  )
}
