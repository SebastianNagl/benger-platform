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
import { JudgeAgreementHeatmap } from '@/components/evaluation/JudgeAgreementHeatmap'
import { MetricDistributionChart } from '@/components/evaluation/MetricDistributionChart'
import { PerRunBreakdown, type PerRunRow } from '@/components/evaluation/PerRunBreakdown'
import { SampleResultsTable } from '@/components/evaluation/SampleResultsTable'
import { Badge } from '@/components/shared/Badge'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
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

interface JudgeRunSummary {
  judge_model_id: string
  run_index: number
  judge_run_id: string
  status?: string | null
  samples_evaluated?: number | null
}

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
    // Multi-run / multi-judge bookkeeping written by run_evaluation()
    // (migration 042). Keys are evaluation_config ids; values are the
    // configured (judge_model, run_index, judge_run_id) entries.
    judges_by_config?: Record<string, JudgeRunSummary[]>
    any_judge_failed?: boolean
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
    'overview' | 'samples' | 'confusion' | 'distributions' | 'judges'
  >('overview')
  // Multi-run statistics (lazy-loaded the first time the Judges tab is opened).
  const [multiRunStats, setMultiRunStats] = useState<any | null>(null)
  const [multiRunStatsLoading, setMultiRunStatsLoading] = useState(false)

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
      // Typed evaluations client (apiClient.evaluations) — no inline strings.
      // Backed by /api/evaluations/run/results/{id} for the eval shape and
      // /api/evaluations/{id}/samples for the per-sample drill-down.
      const evalData = await apiClient.evaluations.getResults(evaluationId)
      setEvaluation(evalData)

      if (evalData.has_sample_results) {
        const samplesData = await apiClient.evaluations.getSamples(evaluationId, {
          page: 1,
          page_size: 100,
        })
        setSamples((samplesData?.items as SampleResult[]) || [])

        // Auto-select first metric for distribution. evalData.metrics is the
        // aggregated map whose keys are composite `config|pred|ref|metric`
        // (or the legacy `:`-delimited form). The /distribution endpoint
        // expects just the bare metric name — strip the composite prefix.
        if (evalData.metrics && Object.keys(evalData.metrics).length > 0) {
          const firstKey = Object.keys(evalData.metrics)[0]
          const bareMetric = firstKey.includes('|')
            ? firstKey.split('|').pop() || firstKey
            : firstKey.includes(':')
              ? firstKey.split(':').slice(3).join(':') || firstKey
              : firstKey
          setSelectedMetric(bareMetric)
          loadMetricDistribution(bareMetric)
        }

        // Try to load confusion matrix for first classification field
        const classificationField = ((samplesData?.items || []) as SampleResult[]).find(
          (s) =>
            s.answer_type.includes('choice') ||
            s.answer_type.includes('classification')
        )

        if (classificationField) {
          try {
            const cmData = await apiClient.evaluations.getConfusionMatrix(
              evaluationId,
              classificationField.field_name,
            )
            setConfusionMatrix(cmData)
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

  // Lazy-load multi-run statistics on first visit to the Judges tab. Pulls
  // from the project-level endpoint scoped to the metrics this evaluation
  // produced; the response is the full StatisticsResponse including the new
  // runs_by_model_metric / task_consistency / judge_agreement blocks.
  const loadMultiRunStats = useCallback(async () => {
    if (!evaluation || multiRunStats || multiRunStatsLoading) return
    // The stats endpoint takes bare metric NAMES (e.g. "llm_judge_falloesung"),
    // not the composite field-keys ("config_id|pred|ref|metric") that the
    // evaluation.metrics dict uses for its keys. Pull the names from the
    // evaluation_configs list instead.
    const evalConfigs = (evaluation as any).evaluation_configs || []
    const metricsList: string[] = Array.from(
      new Set(evalConfigs.map((c: any) => c.metric).filter(Boolean))
    )
    if (metricsList.length === 0) return
    setMultiRunStatsLoading(true)
    try {
      const data = await apiClient.post(
        `/evaluations/projects/${evaluation.project_id}/statistics`,
        {
          metrics: metricsList,
          aggregation: 'model',
          methods: ['ci'],
        },
      )
      setMultiRunStats(data)
    } catch (err) {
      logger.error('Failed to load multi-run statistics', err)
      setMultiRunStats({ error: true })
    } finally {
      setMultiRunStatsLoading(false)
    }
  }, [evaluation, multiRunStats, multiRunStatsLoading])

  useEffect(() => {
    // Load multi-run stats for the tabs that consume them: Judges (heatmap +
    // PerRunBreakdown) and Samples (per-task consistency column). One fetch,
    // cached in state — both tabs share the same multiRunStats.
    if (activeTab === 'judges' || activeTab === 'samples') loadMultiRunStats()
  }, [activeTab, loadMultiRunStats])

  // Derive PerRunBreakdown rows from eval_metadata.judges_by_config (cheap;
  // no extra fetch) and merge with multi-run stats when those land. Returns
  // one row per (target_model, judge_model, run_index) — the mean_score
  // column is filled in once /statistics returns, otherwise null.
  const perRunRows: PerRunRow[] = (() => {
    if (!evaluation) return []
    const judgesByConfig = evaluation.eval_metadata?.judges_by_config
    if (!judgesByConfig) return []
    const rows: PerRunRow[] = []
    for (const cid of Object.keys(judgesByConfig)) {
      for (const entry of judgesByConfig[cid]) {
        rows.push({
          target_model_id: evaluation.model_id,
          judge_model_id: entry.judge_model_id,
          run_index: entry.run_index,
          judge_run_id: entry.judge_run_id,
          // Worker exposes per-child status + sample count under
          // judges_by_config (migration 042). Falls back to the evaluation's
          // own status / null for legacy rows that pre-date this enrichment.
          status: entry.status ?? evaluation.status ?? 'unknown',
          samples_evaluated: entry.samples_evaluated ?? null,
          mean_score: null, // Filled in below from multi-run stats once they load.
        })
      }
    }
    // Enrich with mean_score from the multi-run stats endpoint when it lands.
    // The endpoint returns runs aggregated per (target_model, metric) pair,
    // not per judge_run, so we can't derive a per-judge_run mean from it
    // directly. Leaving null until we add a per-judge breakdown to the stats
    // endpoint is honest — the table shows "—" rather than a fake number.
    return rows
  })()

  // First metric for which we have multi-run agreement (drives the heatmap).
  const judgeAgreementForFirstMetric = (() => {
    if (!multiRunStats?.judge_agreement_by_model_metric) return null
    const entries = Object.entries(multiRunStats.judge_agreement_by_model_metric)
    if (entries.length === 0) return null
    const [key, value] = entries[0] as [string, any]
    const [, metric] = key.split('|')
    // Empty objects are truthy in JS, so `cohens_kappa_pairwise || pearson_r_pairwise`
    // would lock onto the empty cohens dict and never fall through to pearson.
    // Check non-emptiness explicitly.
    const cohens = value.cohens_kappa_pairwise || {}
    const pearson = value.pearson_r_pairwise || {}
    const sourceDict = Object.keys(cohens).length > 0 ? cohens : pearson
    const judges = Object.keys(sourceDict).flatMap((k) => k.split('__'))
    const distinctJudges = Array.from(new Set(judges))
    return { metric, value, distinctJudges }
  })()

  const showJudgesTab = perRunRows.length > 0 || !!evaluation?.eval_metadata?.judges_by_config

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
          <Button className="mt-4" onClick={() => router.push('/runs?type=evaluation')}>
            {t('evaluation.human.preference.next')}
          </Button>
        </div>
      </div>
    )
  }

  // Extract bare metric names from the composite aggregated-metrics keys
  // (`config_id|pred_field|ref_field|metric_name` or legacy `:` form). The
  // /metrics/{name}/distribution endpoint expects the bare name; the
  // headline tile lookup needs the original composite key the value lives
  // under. Build both: a deduped bare-name list for the dropdown + a
  // bare→composite map so the metric tile can read the value.
  const _bareMetric = (key: string): string =>
    key.includes('|')
      ? key.split('|').pop() || key
      : key.includes(':')
        ? key.split(':').slice(3).join(':') || key
        : key
  const _allComposite = Object.keys(evaluation.metrics || {})
  const _bareToComposite = new Map<string, string>()
  for (const k of _allComposite) {
    const bare = _bareMetric(k)
    if (!_bareToComposite.has(bare)) _bareToComposite.set(bare, k)
  }
  const metricKeys = Array.from(_bareToComposite.keys())

  return (
    <div className="container mx-auto px-4 py-8">
        {/* Breadcrumb — root is /runs (the per-run inventory), not the
            cross-run /evaluations dashboard, so the user can hop back to
            sibling runs without losing the multi-run context. */}
        <div className="mb-4">
          <Breadcrumb
            items={[
              { label: 'Home', href: '/dashboard' },
              { label: t('runs.title', 'Läufe'), href: '/runs?type=evaluation' },
              { label: t('evaluation.human.results.title') },
            ]}
          />
        </div>
        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button variant="text" onClick={() => router.push('/runs?type=evaluation')}>
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
              {
                id: 'judges',
                label: t('evaluations.detail.judges', 'Judges & Läufe'),
                hidden: !showJudgesTab,
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
                {metricKeys.map((metric) => {
                  // metric here is the bare metric name; values live under
                  // the composite key. Look up via the bare→composite map.
                  // When the value isn't numeric (judge-error placeholders
                  // store dicts), fall back to "—" instead of crashing
                  // .toFixed.
                  const compositeKey = _bareToComposite.get(metric) || metric
                  const v = (evaluation.metrics as Record<string, unknown>)?.[compositeKey]
                  const display = typeof v === 'number' ? v.toFixed(3) : '—'
                  return (
                    <div key={metric} className="rounded-lg border bg-gray-50 p-4">
                      <div className="text-sm text-gray-600">{metric}</div>
                      <div className="mt-1 text-2xl font-bold text-blue-600">{display}</div>
                    </div>
                  )
                })}
              </div>
            </Card>
          </div>
        )}

        {/* Sample Results Tab */}
        {activeTab === 'samples' && (
          <div>
            <Card className="p-6">
              <h2 className="mb-4 text-lg font-medium">{t('evaluations.detail.perSampleResults')}</h2>
              <SampleResultsTable
                data={samples}
                consistencyByTaskId={(() => {
                  // Multi-run consistency lookup (migration 042). Flatten the
                  // task_consistency_by_model_metric block (keyed by
                  // "model|metric" → list of TaskConsistency) into a flat
                  // task_id → entry map. The first non-empty bucket wins
                  // when one task is rated by multiple metrics; that's a
                  // simplification (the table only has one task_id per row,
                  // so showing variance from any metric is more useful than
                  // showing nothing).
                  const map: Record<string, any> = {}
                  const block = multiRunStats?.task_consistency_by_model_metric || {}
                  for (const list of Object.values(block) as any[]) {
                    if (!Array.isArray(list)) continue
                    for (const entry of list) {
                      if (!entry?.task_id) continue
                      if (!map[entry.task_id]) {
                        map[entry.task_id] = {
                          n_runs: entry.n_runs,
                          variance: entry.variance,
                          fleiss_kappa: entry.fleiss_kappa,
                          percent_agreement: entry.percent_agreement,
                        }
                      }
                    }
                  }
                  return map
                })()}
              />
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

        {/* Judges & Runs Tab — multi-run feature.
             Shows the configured judge ensemble per (judge, run) row plus
             the inter-judge agreement heatmap when ≥2 distinct judges
             produced data for at least one metric. */}
        {activeTab === 'judges' && (
          <div className="space-y-6">
            <Card className="p-6">
              <h2 className="mb-4 text-lg font-medium">
                {t('evaluations.detail.perJudgeRun', 'Per Judge & Lauf')}
              </h2>
              {evaluation?.eval_metadata?.any_judge_failed && (
                <div className="mb-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
                  {t(
                    'evaluations.detail.someJudgesFailed',
                    'Mindestens ein Judge-Lauf ist fehlgeschlagen. Die Statistiken unten beruhen nur auf den erfolgreichen Läufen.',
                  )}
                </div>
              )}
              <PerRunBreakdown
                rows={perRunRows}
                metric={metricKeys[0] || ''}
                showTargetModel={false}
              />
            </Card>

            {multiRunStatsLoading && (
              <div className="flex items-center justify-center py-6">
                <LoadingSpinner />
              </div>
            )}

            {judgeAgreementForFirstMetric &&
              judgeAgreementForFirstMetric.distinctJudges.length >= 2 && (
                <JudgeAgreementHeatmap
                  judgeModelIds={judgeAgreementForFirstMetric.distinctJudges}
                  metric={judgeAgreementForFirstMetric.metric}
                  pairwise={
                    judgeAgreementForFirstMetric.value.pearson_r_pairwise &&
                    Object.keys(judgeAgreementForFirstMetric.value.pearson_r_pairwise).length > 0
                      ? judgeAgreementForFirstMetric.value.pearson_r_pairwise
                      : judgeAgreementForFirstMetric.value.cohens_kappa_pairwise || {}
                  }
                  scoreType={
                    judgeAgreementForFirstMetric.value.pearson_r_pairwise &&
                    Object.keys(judgeAgreementForFirstMetric.value.pearson_r_pairwise).length > 0
                      ? 'pearson'
                      : 'kappa'
                  }
                  fleissKappa={judgeAgreementForFirstMetric.value.fleiss_kappa ?? null}
                />
              )}
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
