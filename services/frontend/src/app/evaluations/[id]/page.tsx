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

import { ConfusionMatrixChart } from '@/components/evaluation/ConfusionMatrixChart'
import { EvaluationRunRubricHost } from '@/components/evaluation/EvaluationRunRubricHost'
import { JudgeAgreementHeatmap } from '@/components/evaluation/JudgeAgreementHeatmap'
import { MetricDistributionChart } from '@/components/evaluation/MetricDistributionChart'
import {
  PerRunBreakdown,
  type PerRunRow,
} from '@/components/evaluation/PerRunBreakdown'
import { SampleResultsTable } from '@/components/evaluation/SampleResultsTable'
import { Alert } from '@/components/shared/Alert'
import { Badge } from '@/components/shared/Badge'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Button } from '@/components/shared/Button'
import { Card } from '@/components/shared/Card'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shared/Select'
import { Tabs, TabsList, TabsTrigger } from '@/components/shared/Tabs'
import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import { apiClient } from '@/lib/api/client'
import { projectsAPI } from '@/lib/api/projects'
import {
  bareMetricName,
  BENIGN_MATCH_REASONS,
  configDisplayLabel,
  configMetricMean,
  describeBillingBlock,
  describeConfigMatchReason,
  fieldSelectorLabel,
  formatMetricNumber,
  isSidecarMetricKey,
  metricDisplayLabel,
  metricKeyConfigId,
  runStatusLabel,
  type ConfigMatchRecord,
  type RunConfigLabel,
} from '@/lib/evaluation/runDisplay'
import { logger } from '@/lib/utils/logger'
import {
  ArrowLeftIcon,
  ArrowPathIcon,
  ChartBarIcon,
} from '@heroicons/react/24/outline'
import clsx from 'clsx'
import Link from 'next/link'
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
  // Set when the run failed. A run that matched nothing to grade fails with
  // a diagnostic naming the config and what to change.
  error_message?: string | null
  samples_evaluated: number
  metrics: Record<string, number>
  // Per config and field pair, the metric values (`{config: {pair: {metric}}}`).
  results_by_config?: Record<string, Record<string, Record<string, unknown>>>
  // The configs this run was dispatched with (snapshot in eval_metadata).
  evaluation_configs?: RunConfigLabel[]
  eval_metadata: {
    samples_passed: number
    samples_failed: number
    pass_rate: number
    // Multi-run / multi-judge bookkeeping written by run_evaluation()
    // (migration 042). Keys are evaluation_config ids; values are the
    // configured (judge_model, run_index, judge_run_id) entries.
    judges_by_config?: Record<string, JudgeRunSummary[]>
    any_judge_failed?: boolean
    // Per config, why it contributed nothing to grade (reason null = matched).
    // Written by run_evaluation for every run.
    match_by_config?: Record<string, ConfigMatchRecord>
  }
  // Issue #69: scope filters resolved to display form. null when the run
  // was a full sweep; otherwise carries the narrowed-to set so the UI
  // can render a "Scoped to:" line.
  scope?: {
    task_ids: string[]
    model_ids: string[]
    annotators: { user_id: string; display: string }[]
  } | null
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

interface ProjectSummary {
  title?: string
  label_config?: string | null
  evaluation_config?: { evaluation_configs?: RunConfigLabel[] } | null
}

type TabId = 'overview' | 'samples' | 'confusion' | 'distributions' | 'judges'

function StatTile({
  label,
  value,
  toneClass,
  testId,
}: {
  label: string
  value: string | number
  toneClass: string
  testId?: string
}) {
  return (
    <Card className="p-5">
      <div className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
        {label}
      </div>
      <div
        data-testid={testId}
        className={clsx('mt-2 text-3xl font-semibold tabular-nums', toneClass)}
      >
        {value}
      </div>
    </Card>
  )
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold text-zinc-900 dark:text-white">
      {children}
    </h2>
  )
}

export default function EvaluationDashboard({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const router = useRouter()
  const { t, locale } = useI18n()
  const { addToast } = useToast()

  const [evaluationId, setEvaluationId] = useState<string | null>(null)
  const [evaluation, setEvaluation] = useState<EvaluationData | null>(null)
  const [project, setProject] = useState<ProjectSummary | null>(null)
  const [samples, setSamples] = useState<SampleResult[]>([])
  const [confusionMatrix, setConfusionMatrix] = useState<any>(null)
  const [selectedMetric, setSelectedMetric] = useState<string>('')
  const [metricDistribution, setMetricDistribution] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<TabId>('overview')
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
          `/evaluations/${evaluationId}/metrics/${metricName}/distribution`,
        )
        setMetricDistribution(response.data)
      } catch (error) {
        console.error('Failed to load metric distribution:', error)
        addToast(t('evaluation.human.preference.saveFailed'), 'error')
      }
    },
    [evaluationId, addToast, t],
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
        const samplesData = await apiClient.evaluations.getSamples(
          evaluationId,
          {
            page: 1,
            page_size: 100,
          },
        )
        // The API client types items as Record<string, unknown>[]; the
        // actual response shape matches SampleResult by contract. Two-step
        // cast through `unknown` is the standard TS escape hatch for this
        // mismatch.
        setSamples((samplesData?.items as unknown as SampleResult[]) || [])

        // Auto-select the first result metric for the distribution.
        // evalData.metrics is keyed `config|pred|ref|metric` (or the legacy
        // `:` form); the /distribution endpoint expects the bare metric name.
        // Companion keys (raw_score, *_passed) are not results.
        const firstKey = Object.keys(evalData.metrics || {}).find(
          (key) => !isSidecarMetricKey(key),
        )
        if (firstKey) {
          const bareMetric = bareMetricName(firstKey)
          setSelectedMetric(bareMetric)
          loadMetricDistribution(bareMetric)
        }

        // Try to load confusion matrix for first classification field
        const classificationField = (
          (samplesData?.items || []) as unknown as SampleResult[]
        ).find(
          (s) =>
            s.answer_type.includes('choice') ||
            s.answer_type.includes('classification'),
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
      addToast(t('evaluations.detail.loadFailed'), 'error')
    } finally {
      setLoading(false)
    }
  }, [evaluationId, addToast, t, loadMetricDistribution])

  useEffect(() => {
    if (!evaluationId) return
    loadEvaluationData()
  }, [evaluationId, loadEvaluationData])

  // The project's title for the header and its current configs as a naming
  // fallback. Best effort: without it the header links to the project by a
  // generic label instead of showing its raw id.
  const projectId = evaluation?.project_id
  useEffect(() => {
    if (!projectId) return
    let cancelled = false
    projectsAPI
      .get(projectId)
      .then((data) => {
        if (!cancelled) setProject((data as ProjectSummary) ?? null)
      })
      .catch((err) => {
        logger.debug('Project for evaluation run not loaded', err)
      })
    return () => {
      cancelled = true
    }
  }, [projectId])

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
      new Set(evalConfigs.map((c: any) => c.metric).filter(Boolean)),
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
          config_id: cid,
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
    const entries = Object.entries(
      multiRunStats.judge_agreement_by_model_metric,
    )
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

  // Configs that matched nothing to grade, with the worker's reason. The two
  // benign reasons are not failures: everything was already graded, or the
  // metric is human grading that is never dispatched.
  const unmatchedConfigs = Object.entries(
    evaluation?.eval_metadata?.match_by_config ?? {},
  ).filter(([, rec]) => !!rec?.reason && !BENIGN_MATCH_REASONS.has(rec.reason))

  const showJudgesTab =
    perRunRows.length > 0 || !!evaluation?.eval_metadata?.judges_by_config

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <LoadingSpinner />
      </div>
    )
  }

  if (!evaluation) {
    return (
      <div className="mx-auto max-w-7xl px-4 pt-16 pb-10 sm:px-6 lg:px-8">
        <Card className="px-6 py-12 text-center">
          <p className="text-zinc-600 dark:text-zinc-400">
            {t('evaluations.detail.notFound')}
          </p>
          <Button
            className="mt-4"
            onClick={() => router.push('/runs?type=evaluation')}
          >
            {t('evaluations.detail.backToRuns')}
          </Button>
        </Card>
      </div>
    )
  }

  // Names for configs: the run's own snapshot first, then the project's
  // current configs for runs whose snapshot predates display names.
  const configs: RunConfigLabel[] = [
    ...(evaluation.evaluation_configs ?? []),
    ...(project?.evaluation_config?.evaluation_configs ?? []),
  ]

  // Aggregated metrics as the reader sees them: companion keys hidden, one
  // tile per (config, metric), labelled from the metric registry. The config
  // name is added only when the run holds more than one config.
  const metricEntries: Array<{
    key: string
    bare: string
    configId: string | null
  }> = []
  const seenEntries = new Set<string>()
  for (const key of Object.keys(evaluation.metrics || {})) {
    if (isSidecarMetricKey(key)) continue
    const bare = bareMetricName(key)
    const configId = metricKeyConfigId(key)
    const id = `${configId ?? ''}|${bare}`
    if (seenEntries.has(id)) continue
    seenEntries.add(id)
    metricEntries.push({ key, bare, configId })
  }
  const showConfigNames =
    new Set(metricEntries.map((entry) => entry.configId)).size > 1
  // Deduped bare names for the distribution dropdown (the endpoint takes the
  // bare name) and the per-run breakdown.
  const metricKeys = Array.from(new Set(metricEntries.map((e) => e.bare)))

  // Rows for the judges tab, each carrying the metric of the config its
  // judge run graded. A run may mix metrics across configs (an immediate
  // grading holds one config per judge tier), so the first aggregated metric
  // is only the fallback for a config the snapshot does not name. A config
  // graded by a single judge run gets that run's mean from the config's own
  // aggregate; the per-judge means of an ensemble stay "—" until the stats
  // endpoint breaks them down per judge run.
  const judgesByConfig = evaluation.eval_metadata?.judges_by_config ?? {}
  const judgeRows: PerRunRow[] = perRunRows.map((row) => {
    const cid = row.config_id
    const metric =
      (cid ? configs.find((c) => c.id === cid)?.metric : undefined) ??
      metricKeys[0]
    if (!metric) return row
    const labelled: PerRunRow = {
      ...row,
      metric,
      metric_label: metricDisplayLabel(metric, undefined, t),
    }
    if (row.mean_score !== null || !cid) return labelled
    if (judgesByConfig[cid]?.length !== 1) return labelled
    return {
      ...labelled,
      mean_score: configMetricMean(evaluation.results_by_config, cid, metric),
    }
  })
  // The table names one metric in its header when every row shares it; a
  // mixed table names the metric per row instead.
  const judgeTableMetric =
    judgeRows.find((row) => row.metric)?.metric ?? metricKeys[0] ?? ''

  const evaluated = (evaluation.samples_evaluated ?? 0) > 0
  const samplesFailed = evaluation.eval_metadata?.samples_failed || 0
  const statusVariant =
    evaluation.status === 'completed'
      ? 'default'
      : evaluation.status === 'failed'
        ? 'destructive'
        : 'secondary'
  const createdAt = evaluation.created_at
    ? new Date(evaluation.created_at)
    : null
  const createdLabel =
    createdAt && !Number.isNaN(createdAt.getTime())
      ? createdAt.toLocaleString(locale === 'en' ? 'en-US' : 'de-DE', {
          dateStyle: 'medium',
          timeStyle: 'short',
        })
      : null

  // Each unmatched config phrased in the reader's language. When every one
  // could be phrased, the worker's English diagnostic moves into a technical
  // details disclosure; otherwise it stays in view as the explanation.
  const phrasedUnmatched = unmatchedConfigs.map(([configId, rec]) => ({
    configId,
    rec,
    sentence: describeConfigMatchReason(rec, t),
  }))
  const allPhrased =
    phrasedUnmatched.length > 0 &&
    phrasedUnmatched.every((item) => item.sentence !== null)
  // A run the billing policy refused says why in the reader's language.
  const billingBlock = describeBillingBlock(evaluation?.error_message, t)

  const tabs: Array<{ id: TabId; label: string; hidden?: boolean }> = [
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
  ]

  return (
    <div className="mx-auto max-w-7xl px-4 pt-16 pb-10 sm:px-6 lg:px-8">
      <EvaluationRunRubricHost projectId={evaluation.project_id}>
        {/* Header */}
        <div className="mb-8">
          {/* Breadcrumb — root is /runs (the per-run inventory), not the
              cross-run /evaluations dashboard, so the user can hop back to
              sibling runs without losing the multi-run context. */}
          <div className="mb-4">
            <Breadcrumb
              items={[
                { label: t('navigation.dashboard'), href: '/dashboard' },
                {
                  label: t('runs.title', 'Läufe'),
                  href: '/runs?type=evaluation',
                },
                { label: t('evaluation.human.results.title') },
              ]}
            />
          </div>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="text-3xl font-bold text-zinc-900 dark:text-white">
                  {t('evaluation.human.results.title')}
                </h1>
                <span data-testid="evaluation-detail-status">
                  <Badge variant={statusVariant}>
                    {runStatusLabel(evaluation.status, t)}
                  </Badge>
                </span>
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-zinc-500 dark:text-zinc-400">
                <span data-testid="evaluation-detail-project">
                  {t('evaluations.detail.project')}:{' '}
                  <Link
                    href={`/projects/${evaluation.project_id}`}
                    className="font-medium text-emerald-600 hover:text-emerald-700 dark:text-emerald-400 dark:hover:text-emerald-300"
                  >
                    {project?.title || t('evaluations.detail.openProject')}
                  </Link>
                </span>
                {/* A run over submitted answers has no model: the worker
                    records 'unknown', which says nothing useful here. */}
                {evaluation.model_id && evaluation.model_id !== 'unknown' && (
                  <>
                    <span aria-hidden="true">·</span>
                    <span data-testid="evaluation-detail-model">
                      {t('evaluations.detail.model')}:{' '}
                      <span className="font-medium text-zinc-700 dark:text-zinc-300">
                        {evaluation.model_id}
                      </span>
                    </span>
                  </>
                )}
                {createdLabel && (
                  <>
                    <span aria-hidden="true">·</span>
                    <span>
                      {t('evaluations.detail.createdAt', {
                        date: createdLabel,
                      })}
                    </span>
                  </>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                onClick={() => router.push('/runs?type=evaluation')}
              >
                <ArrowLeftIcon className="h-4 w-4" />
                {t('evaluations.detail.back')}
              </Button>
              <Button
                variant="outline"
                onClick={loadEvaluationData}
                aria-label={t('evaluation.multiFieldResults.refresh')}
                title={t('evaluation.multiFieldResults.refresh')}
              >
                <ArrowPathIcon className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>

        {/* Why the run failed. A run that matched nothing used to be stored
            as a success and shown as an empty results panel; it now fails,
            and this is where the reason and the affected configs become
            visible. */}
        {evaluation.status === 'failed' && (
          <div
            role="alert"
            data-testid="evaluation-run-failed"
            className="mb-6"
          >
            <Alert variant="error">
              <div className="text-sm text-red-800 dark:text-red-200">
                <p className="font-medium">
                  {t(
                    'evaluations.detail.runFailedTitle',
                    'Evaluierung fehlgeschlagen',
                  )}
                </p>
                {phrasedUnmatched.length > 0 && (
                  <div className="mt-3">
                    <p className="font-medium">
                      {t(
                        'evaluations.detail.unmatchedConfigsTitle',
                        'Evaluierungen ohne passende Daten',
                      )}
                    </p>
                    <ul
                      className="mt-2 space-y-2"
                      data-testid="evaluation-unmatched-configs"
                    >
                      {phrasedUnmatched.map(({ configId, rec, sentence }) => {
                        const fields = [
                          ...(rec.human_fields ?? []),
                          ...(rec.llm_fields ?? []),
                        ]
                        return (
                          <li key={configId}>
                            <span className="font-medium">
                              {rec.display_name ||
                                configDisplayLabel(
                                  configId,
                                  configs,
                                  rec.metric,
                                  t,
                                ) ||
                                configId}
                            </span>{' '}
                            <span className="text-red-700 dark:text-red-300">
                              ({metricDisplayLabel(rec.metric, undefined, t)})
                            </span>
                            {sentence && <span>: {sentence}</span>}
                            <span className="mt-1 flex flex-wrap items-center gap-2 text-xs">
                              <code className="rounded bg-red-100 px-1.5 py-0.5 font-mono dark:bg-red-900/40">
                                {rec.reason}
                              </code>
                              {fields.length > 0 && (
                                <span>
                                  {fields
                                    .map((f) => fieldSelectorLabel(f, t))
                                    .join(', ')}
                                </span>
                              )}
                            </span>
                          </li>
                        )
                      })}
                    </ul>
                  </div>
                )}
                {billingBlock && (
                  <p className="mt-2" data-testid="evaluation-billing-blocked">
                    {billingBlock}
                  </p>
                )}
                {evaluation.error_message &&
                  (allPhrased || billingBlock ? (
                    <details className="mt-3">
                      <summary className="cursor-pointer font-medium">
                        {t('evaluations.detail.technicalDetails')}
                      </summary>
                      <p className="mt-1 break-words whitespace-pre-wrap">
                        {evaluation.error_message}
                      </p>
                    </details>
                  ) : (
                    <p className="mt-2 break-words whitespace-pre-wrap">
                      {evaluation.error_message}
                    </p>
                  ))}
              </div>
            </Alert>
          </div>
        )}

        {/* Tabs */}
        <Tabs
          value={activeTab}
          defaultValue="overview"
          onValueChange={(value) => setActiveTab(value as TabId)}
          className="mb-6"
        >
          <TabsList className="h-auto flex-wrap justify-start">
            {tabs
              .filter((tab) => !tab.hidden)
              .map((tab) => (
                <TabsTrigger key={tab.id} value={tab.id}>
                  {tab.label}
                </TabsTrigger>
              ))}
          </TabsList>
        </Tabs>

        {/* Overview Tab */}
        {activeTab === 'overview' && (
          <div className="space-y-6">
            {evaluation.scope && (
              <div className="rounded-lg border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-700 dark:border-zinc-800 dark:bg-zinc-800/50 dark:text-zinc-300">
                <span className="font-medium">
                  {t('evaluations.detail.scopedTo', 'Eingeschränkt auf:')}
                </span>{' '}
                {[
                  evaluation.scope.model_ids.length > 0 &&
                    t(
                      'evaluations.detail.scopeModelsCount',
                      '{count} Modell(e)',
                    ).replace(
                      '{count}',
                      String(evaluation.scope.model_ids.length),
                    ),
                  evaluation.scope.annotators.length > 0 &&
                    `${
                      evaluation.scope.annotators.length === 1
                        ? t(
                            'evaluations.detail.scopeOneAnnotator',
                            '1 Annotator:in',
                          )
                        : t(
                            'evaluations.detail.scopeAnnotatorsCount',
                            '{count} Annotator:innen',
                          ).replace(
                            '{count}',
                            String(evaluation.scope.annotators.length),
                          )
                    } (${evaluation.scope.annotators.map((a) => a.display).join(', ')})`,
                  evaluation.scope.task_ids.length > 0 &&
                    t(
                      'evaluations.detail.scopeTasksCount',
                      '{count} Task(s)',
                    ).replace(
                      '{count}',
                      String(evaluation.scope.task_ids.length),
                    ),
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </div>
            )}

            {/* Summary tiles. Green only once something was graded: a 0.0%
                pass rate on a run with no samples is not a success. */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <StatTile
                label={t('evaluations.detail.totalSamples')}
                value={evaluation.samples_evaluated ?? 0}
                toneClass="text-zinc-900 dark:text-white"
              />
              <StatTile
                label={t('evaluations.detail.passRate')}
                value={`${((evaluation.eval_metadata?.pass_rate || 0) * 100).toFixed(1)}%`}
                toneClass={
                  evaluated
                    ? 'text-emerald-600 dark:text-emerald-400'
                    : 'text-zinc-500 dark:text-zinc-400'
                }
                testId="evaluation-detail-pass-rate"
              />
              <StatTile
                label={t('evaluations.detail.passed')}
                value={evaluation.eval_metadata?.samples_passed || 0}
                toneClass={
                  evaluated
                    ? 'text-emerald-600 dark:text-emerald-400'
                    : 'text-zinc-500 dark:text-zinc-400'
                }
              />
              <StatTile
                label={t('evaluations.detail.failed')}
                value={samplesFailed}
                toneClass={
                  samplesFailed > 0
                    ? 'text-red-600 dark:text-red-400'
                    : 'text-zinc-500 dark:text-zinc-400'
                }
              />
            </div>

            {/* Aggregate Metrics */}
            <Card className="p-6">
              <SectionTitle>
                <ChartBarIcon className="h-5 w-5 text-zinc-400" />
                {t('evaluations.detail.aggregateMetrics')}
              </SectionTitle>
              {metricEntries.length === 0 ? (
                <p className="text-sm text-zinc-500 dark:text-zinc-400">
                  {t('evaluations.detail.noMetrics')}
                </p>
              ) : (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                  {metricEntries.map(({ key, bare, configId }) => {
                    // When the value isn't numeric (judge-error placeholders
                    // store dicts), fall back to "—" instead of crashing
                    // .toFixed.
                    const v = (evaluation.metrics as Record<string, unknown>)?.[
                      key
                    ]
                    const display =
                      typeof v === 'number' ? formatMetricNumber(bare, v) : '—'
                    const configName = showConfigNames
                      ? configDisplayLabel(configId, configs, undefined, t)
                      : null
                    return (
                      <div
                        key={key}
                        data-testid="evaluation-aggregate-metric"
                        className="rounded-lg border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-800 dark:bg-zinc-800/50"
                      >
                        <div className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                          {metricDisplayLabel(bare, undefined, t)}
                        </div>
                        {configName && (
                          <div className="text-xs text-zinc-500 dark:text-zinc-400">
                            {configName}
                          </div>
                        )}
                        <div className="mt-2 text-2xl font-semibold text-zinc-900 tabular-nums dark:text-white">
                          {display}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </Card>
          </div>
        )}

        {/* Sample Results Tab */}
        {activeTab === 'samples' && (
          <Card className="p-6">
            <SectionTitle>
              {t('evaluations.detail.perSampleResults')}
            </SectionTitle>
            <SampleResultsTable
              data={samples}
              configs={configs}
              labelConfig={project?.label_config}
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
                const block =
                  multiRunStats?.task_consistency_by_model_metric || {}
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
        )}

        {/* Confusion Matrix Tab */}
        {activeTab === 'confusion' && confusionMatrix && (
          <Card className="p-6">
            <ConfusionMatrixChart data={confusionMatrix} />
          </Card>
        )}

        {/* Judges & Runs Tab — multi-run feature.
            Shows the configured judge ensemble per (judge, run) row plus
            the inter-judge agreement heatmap when ≥2 distinct judges
            produced data for at least one metric. */}
        {activeTab === 'judges' && (
          <div className="space-y-6">
            <Card className="p-6">
              <SectionTitle>
                {t('evaluations.detail.perJudgeRun', 'Per Judge & Lauf')}
              </SectionTitle>
              {evaluation?.eval_metadata?.any_judge_failed && (
                <Alert variant="warning" className="mb-4">
                  <p className="text-sm text-amber-800 dark:text-amber-200">
                    {t(
                      'evaluations.detail.someJudgesFailed',
                      'Mindestens ein Judge-Lauf ist fehlgeschlagen. Die Statistiken unten beruhen nur auf den erfolgreichen Läufen.',
                    )}
                  </p>
                </Alert>
              )}
              <PerRunBreakdown
                rows={judgeRows}
                metric={judgeTableMetric}
                metricLabel={
                  judgeTableMetric
                    ? metricDisplayLabel(judgeTableMetric, undefined, t)
                    : undefined
                }
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
                    Object.keys(
                      judgeAgreementForFirstMetric.value.pearson_r_pairwise,
                    ).length > 0
                      ? judgeAgreementForFirstMetric.value.pearson_r_pairwise
                      : judgeAgreementForFirstMetric.value
                          .cohens_kappa_pairwise || {}
                  }
                  scoreType={
                    judgeAgreementForFirstMetric.value.pearson_r_pairwise &&
                    Object.keys(
                      judgeAgreementForFirstMetric.value.pearson_r_pairwise,
                    ).length > 0
                      ? 'pearson'
                      : 'kappa'
                  }
                  fleissKappa={
                    judgeAgreementForFirstMetric.value.fleiss_kappa ?? null
                  }
                />
              )}
          </div>
        )}

        {/* Distributions Tab */}
        {activeTab === 'distributions' && (
          <div className="space-y-6">
            <Card className="p-6">
              <label className="mb-2 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                {t('evaluations.detail.selectMetric')}
              </label>
              <Select value={selectedMetric} onValueChange={handleMetricChange}>
                <SelectTrigger>
                  <SelectValue
                    placeholder={t('evaluations.detail.selectMetric')}
                  />
                </SelectTrigger>
                <SelectContent>
                  {metricKeys.map((metric) => (
                    <SelectItem key={metric} value={metric}>
                      {metricDisplayLabel(metric, undefined, t)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Card>

            {metricDistribution && (
              <MetricDistributionChart
                data={metricDistribution}
                title={t('evaluation.metricDistribution.titleWithMetric', {
                  metric: metricDisplayLabel(
                    metricDistribution.metric_name || selectedMetric,
                    undefined,
                    t,
                  ),
                })}
              />
            )}
          </div>
        )}
      </EvaluationRunRubricHost>
    </div>
  )
}
