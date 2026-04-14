/**
 * Individual Evaluation Dashboard Page
 *
 * Comprehensive visualization dashboard for a single evaluation showing:
 * - Aggregate metrics
 * - Confusion matrix
 * - Metric distributions
 * - Per-sample drill-down table
 * - Model comparison (when multiple evaluations exist)
 *
 * Issue #763: Per-sample evaluation results and visualization dashboard
 */

'use client'

import { logger } from '@/lib/utils/logger'
import { ConfusionMatrixChart } from '@/components/evaluation/ConfusionMatrixChart'
import { MetricDistributionChart } from '@/components/evaluation/MetricDistributionChart'
import { SampleResultsTable } from '@/components/evaluation/SampleResultsTable'
import { Badge } from '@/components/shared/Badge'
import { Button } from '@/components/shared/Button'
import { Card } from '@/components/shared/Card'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/shared/Select'
import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import { apiClient } from '@/lib/api/client'
import {
  ArrowLeftIcon,
  ArrowPathIcon,
  ChartBarIcon,
} from '@heroicons/react/24/outline'
import { useRouter } from 'next/navigation'
import { useCallback, useEffect, useState } from 'react'

interface EvaluationData {
  id: string
  project_id: string
  model_id: string
  status: string
  samples_evaluated: number
  metrics: Record<string, number>
  eval_metadata: {
    samples_passed: number
    samples_failed: number
    pass_rate: number
  }
  created_at: string
}

interface SampleResult {
  id: string
  task_id: string
  field_name: string
  answer_type: string
  ground_truth: Record<string, any>
  prediction: Record<string, any>
  metrics: Record<string, number>
  passed: boolean
  confidence_score: number | null
  error_message: string | null
  processing_time_ms: number | null
}

export default function EvaluationDashboard({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const router = useRouter()
  const { t } = useI18n()
  const { addToast } = useToast()

  const [evaluationId, setEvaluationId] = useState<string | null>(null)
  const [evaluation, setEvaluation] = useState<EvaluationData | null>(null)
  const [samples, setSamples] = useState<SampleResult[]>([])
  const [confusionMatrix, setConfusionMatrix] = useState<any>(null)
  const [selectedMetric, setSelectedMetric] = useState<string>('')
  const [metricDistribution, setMetricDistribution] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<
    'overview' | 'samples' | 'confusion' | 'distributions'
  >('overview')

  // Unwrap async params (Next.js 15)
  useEffect(() => {
    params?.then(({ id }) => setEvaluationId(id))
  }, [params])

  const loadMetricDistribution = useCallback(
    async (metricName: string) => {
      if (!evaluationId) return
      try {
        const response = await apiClient.get(
          `/evaluations/${evaluationId}/metrics/${metricName}/distribution`
        )
        setMetricDistribution(response.data)
      } catch (error) {
        console.error('Failed to load metric distribution:', error)
        addToast(t('evaluation.human.preference.saveFailed'), 'error')
      }
    },
    [evaluationId, addToast, t]
  )

  const loadEvaluationData = useCallback(async () => {
    if (!evaluationId) return
    setLoading(true)
    try {
      // Load evaluation details
      const evalResponse = await apiClient.get(`/evaluations/${evaluationId}`)
      const evalData = evalResponse.data
      setEvaluation(evalData)

      // Load sample results
      if (evalData.has_sample_results) {
        const samplesResponse = await apiClient.get(
          `/evaluations/${evaluationId}/samples`,
          { params: { page: 1, page_size: 100 } }
        )
        setSamples(samplesResponse.data.items || [])

        // Auto-select first metric for distribution
        if (evalData.metrics && Object.keys(evalData.metrics).length > 0) {
          const firstMetric = Object.keys(evalData.metrics)[0]
          setSelectedMetric(firstMetric)
          loadMetricDistribution(firstMetric)
        }

        // Try to load confusion matrix for first classification field
        const classificationField = samplesResponse.data.items.find(
          (s: SampleResult) =>
            s.answer_type.includes('choice') ||
            s.answer_type.includes('classification')
        )

        if (classificationField) {
          try {
            const cmResponse = await apiClient.get(
              `/evaluations/${evaluationId}/confusion-matrix`,
              { params: { field_name: classificationField.field_name } }
            )
            setConfusionMatrix(cmResponse.data)
          } catch (err) {
            // Confusion matrix not available for this field
            logger.debug('No confusion matrix available')
          }
        }
      }
    } catch (error) {
      console.error('Failed to load evaluation:', error)
      addToast(t('evaluation.human.preference.saveFailed'), 'error')
    } finally {
      setLoading(false)
    }
  }, [evaluationId, addToast, t, loadMetricDistribution])

  useEffect(() => {
    if (!evaluationId) return
    loadEvaluationData()
  }, [evaluationId, loadEvaluationData])

  const handleMetricChange = (metric: string) => {
    setSelectedMetric(metric)
    loadMetricDistribution(metric)
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <LoadingSpinner />
      </div>
    )
  }

  if (!evaluation) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="text-center">
          <p className="text-gray-600">
            {t('evaluation.human.results.noResults')}
          </p>
          <Button className="mt-4" onClick={() => router.push('/evaluations')}>
            {t('evaluation.human.preference.next')}
          </Button>
        </div>
      </div>
    )
  }

  const metricKeys = Object.keys(evaluation.metrics || {})

  return (
    <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button variant="text" onClick={() => router.push('/evaluations')}>
              <ArrowLeftIcon className="mr-2 h-4 w-4" />
              {t('evaluations.detail.back')}
            </Button>
            <div>
              <h1 className="text-2xl font-bold">
                {t('evaluation.human.results.title')}
              </h1>
              <div className="mt-1 flex items-center gap-2 text-sm text-gray-600">
                <span>{t('evaluations.detail.model')}: {evaluation.model_id}</span>
                <span>•</span>
                <span>{t('evaluations.detail.project')}: {evaluation.project_id}</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge
              variant={
                evaluation.status === 'completed' ? 'default' : 'secondary'
              }
            >
              {evaluation.status}
            </Badge>
            <Button variant="outline" onClick={loadEvaluationData}>
              <ArrowPathIcon className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* Tabs */}
        <div className="mb-6 border-b border-gray-200">
          <nav className="-mb-px flex space-x-8">
            {[
              { id: 'overview', label: t('evaluation.human.results.summary') },
              { id: 'samples', label: t('evaluation.human.results.detailed') },
              {
                id: 'confusion',
                label: t('evaluations.detail.confusionMatrix'),
                hidden: !confusionMatrix,
              },
              {
                id: 'distributions',
                label: t('evaluation.human.results.distribution'),
              },
            ].map(
              (tab) =>
                !tab.hidden && (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id as any)}
                    className={`${
                      activeTab === tab.id
                        ? 'border-blue-500 text-blue-600'
                        : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700'
                    } whitespace-nowrap border-b-2 px-1 py-4 text-sm font-medium`}
                  >
                    {tab.label}
                  </button>
                )
            )}
          </nav>
        </div>

        {/* Overview Tab */}
        {activeTab === 'overview' && (
          <div className="space-y-6">
            {/* Summary Cards */}
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
              <Card className="p-4">
                <div className="text-sm text-gray-600">{t('evaluations.detail.totalSamples')}</div>
                <div className="mt-1 text-3xl font-bold">
                  {evaluation.samples_evaluated}
                </div>
              </Card>
              <Card className="p-4">
                <div className="text-sm text-gray-600">{t('evaluations.detail.passRate')}</div>
                <div className="mt-1 text-3xl font-bold text-green-600">
                  {((evaluation.eval_metadata?.pass_rate || 0) * 100).toFixed(
                    1
                  )}
                  %
                </div>
              </Card>
              <Card className="p-4">
                <div className="text-sm text-gray-600">{t('evaluations.detail.passed')}</div>
                <div className="mt-1 text-3xl font-bold text-green-600">
                  {evaluation.eval_metadata?.samples_passed || 0}
                </div>
              </Card>
              <Card className="p-4">
                <div className="text-sm text-gray-600">{t('evaluations.detail.failed')}</div>
                <div className="mt-1 text-3xl font-bold text-red-600">
                  {evaluation.eval_metadata?.samples_failed || 0}
                </div>
              </Card>
            </div>

            {/* Aggregate Metrics */}
            <Card className="p-6">
              <h2 className="mb-4 flex items-center gap-2 text-lg font-medium">
                <ChartBarIcon className="h-5 w-5" />
                {t('evaluations.detail.aggregateMetrics')}
              </h2>
              <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
                {metricKeys.map((metric) => (
                  <div
                    key={metric}
                    className="rounded-lg border bg-gray-50 p-4"
                  >
                    <div className="text-sm text-gray-600">{metric}</div>
                    <div className="mt-1 text-2xl font-bold text-blue-600">
                      {evaluation.metrics[metric].toFixed(3)}
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        )}

        {/* Sample Results Tab */}
        {activeTab === 'samples' && (
          <div>
            <Card className="p-6">
              <h2 className="mb-4 text-lg font-medium">{t('evaluations.detail.perSampleResults')}</h2>
              <SampleResultsTable data={samples} />
            </Card>
          </div>
        )}

        {/* Confusion Matrix Tab */}
        {activeTab === 'confusion' && confusionMatrix && (
          <div>
            <Card className="p-6">
              <ConfusionMatrixChart data={confusionMatrix} />
            </Card>
          </div>
        )}

        {/* Distributions Tab */}
        {activeTab === 'distributions' && (
          <div className="space-y-6">
            {/* Metric Selector */}
            <Card className="p-4">
              <label className="mb-2 block text-sm font-medium text-gray-700">
                {t('evaluations.detail.selectMetric')}
              </label>
              <Select value={selectedMetric} onValueChange={handleMetricChange}>
                <SelectTrigger>
                  <SelectValue placeholder={t('evaluations.detail.selectMetric')} />
                </SelectTrigger>
                <SelectContent>
                  {metricKeys.map((metric) => (
                    <SelectItem key={metric} value={metric}>
                      {metric}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Card>

            {/* Distribution Chart */}
            {metricDistribution && (
              <Card className="p-6">
                <MetricDistributionChart data={metricDistribution} />
              </Card>
            )}
          </div>
        )}
    </div>
  )
}
