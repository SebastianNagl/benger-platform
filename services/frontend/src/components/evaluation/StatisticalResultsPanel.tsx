/**
 * Statistical Results Panel Component
 *
 * Displays comprehensive statistical analysis results:
 * - Metric statistics with CI bars
 * - Pairwise comparisons with significance indicators
 * - Effect size badges
 * - Correlation matrix heatmap
 */

'use client'

import { Badge } from '@/components/shared/Badge'
import { Card } from '@/components/shared/Card'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'
import { useI18n } from '@/contexts/I18nContext'
import {
  CheckCircleIcon,
  InformationCircleIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline'

interface MetricStatistics {
  mean: number
  median?: number
  std: number
  se?: number  // Standard Error = std / sqrt(n)
  min?: number
  max?: number
  ci_lower: number
  ci_upper: number
  n: number
}

interface PairwiseComparison {
  model_a: string
  model_b: string
  metric: string
  ttest_p?: number
  ttest_significant?: boolean
  bootstrap_p?: number
  bootstrap_significant?: boolean
  cohens_d?: number
  cohens_d_interpretation?: string
  cliffs_delta?: number
  cliffs_delta_interpretation?: string
  significant: boolean
}

interface ModelStatistics {
  model_id: string
  model_name?: string
  metrics: Record<string, MetricStatistics>
  sample_count: number
}

interface FieldStatistics {
  field_name: string
  metrics: Record<string, MetricStatistics>
  sample_count: number
}

interface RawScore {
  task_id?: string
  model_id: string
  field_name?: string
  metric: string
  value: number
}

interface StatisticsData {
  aggregation: string
  metrics: Record<string, MetricStatistics>
  /** Per-model statistics (for 'model' aggregation) */
  by_model?: Record<string, ModelStatistics>
  /** Per-field statistics (for 'field' aggregation) */
  by_field?: Record<string, FieldStatistics>
  /** Raw scores (for 'sample' aggregation - box plots) */
  raw_scores?: RawScore[]
  pairwise_comparisons?: PairwiseComparison[]
  correlations?: Record<string, Record<string, number | null>>
  /** Bonferroni correction information */
  bonferroni_correction?: {
    applied: boolean
    num_comparisons: number
    original_alpha: number
    corrected_alpha: number
  }
  /** Warnings about data quality or limitations */
  warnings?: string[]
  /** Multi-aggregation results (when multiple levels selected) */
  _multiAggregation?: Record<string, StatisticsData | null>
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

interface StatisticalResultsPanelProps {
  data: StatisticsData | null
  loading?: boolean
  error?: string | null
  /** Show Bonferroni correction information if available */
  showBonferroniInfo?: boolean
  /** Selected statistical methods to display. If empty, shows all. */
  selectedStatistics?: StatisticalMethod[]
  className?: string
}

const formatValue = (value: number): string => {
  if (value >= 0 && value <= 1) {
    return `${(value * 100).toFixed(1)}%`
  }
  return value.toFixed(4)
}

const formatPValue = (p: number): string => {
  if (p < 0.001) return '<0.001'
  if (p < 0.01) return p.toFixed(3)
  return p.toFixed(2)
}

const getSignificanceStars = (p?: number): string => {
  if (!p) return ''
  if (p < 0.001) return '***'
  if (p < 0.01) return '**'
  if (p < 0.05) return '*'
  return ''
}

const getEffectSizeColor = (interpretation?: string): string => {
  switch (interpretation) {
    case 'large':
      return 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300'
    case 'medium':
      return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300'
    case 'small':
      return 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300'
    default:
      return 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300'
  }
}

const getCorrelationColor = (value: number | null): string => {
  if (value === null) return 'bg-gray-100 dark:bg-gray-800'
  const abs = Math.abs(value)
  if (abs > 0.7) return value > 0 ? 'bg-green-500' : 'bg-red-500'
  if (abs > 0.4) return value > 0 ? 'bg-green-300' : 'bg-red-300'
  if (abs > 0.2) return value > 0 ? 'bg-green-100' : 'bg-red-100'
  return 'bg-gray-100 dark:bg-gray-700'
}

export function StatisticalResultsPanel({
  data,
  loading = false,
  error = null,
  showBonferroniInfo = true,
  selectedStatistics = [],
  className = '',
}: StatisticalResultsPanelProps) {
  const { t } = useI18n()

  // Helper to check if a statistic should be shown
  // If no statistics selected, show all (default behavior)
  const showStat = (stat: StatisticalMethod): boolean => {
    if (selectedStatistics.length === 0) return true
    return selectedStatistics.includes(stat)
  }

  // Check if any significance tests are selected
  const showSignificanceTests = showStat('ttest') || showStat('bootstrap')
  // Check if any effect size metrics are selected
  const showEffectSizes = showStat('cohens_d') || showStat('cliffs_delta')
  if (loading) {
    return (
      <Card className={`p-6 ${className}`}>
        <div className="flex items-center justify-center py-8">
          <LoadingSpinner />
          <span className="ml-2 text-gray-500">{t('evaluation.statisticalResults.computingStatistics')}</span>
        </div>
      </Card>
    )
  }

  if (error) {
    return (
      <Card className={`p-6 ${className}`}>
        <div className="py-8 text-center">
          <XCircleIcon className="mx-auto h-12 w-12 text-red-500" />
          <p className="mt-2 text-red-600 dark:text-red-400">{error}</p>
        </div>
      </Card>
    )
  }

  if (!data) {
    return (
      <Card className={`p-6 ${className}`}>
        <div className="py-8 text-center text-gray-500 dark:text-gray-400">
          <InformationCircleIcon className="mx-auto mb-2 h-12 w-12" />
          <p>{t('evaluation.statisticalResults.selectMetricsPrompt')}</p>
        </div>
      </Card>
    )
  }

  const metricNames = Object.keys(data.metrics)
  const hasModelBreakdown = data.by_model && Object.keys(data.by_model).length > 0
  const hasFieldBreakdown = data.by_field && Object.keys(data.by_field).length > 0

  return (
    <div className={`space-y-6 ${className}`}>
      {/* Warnings */}
      {data.warnings && data.warnings.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-900/20">
          <div className="flex items-start gap-3">
            <InformationCircleIcon className="h-5 w-5 shrink-0 text-amber-600 dark:text-amber-400" />
            <div className="space-y-1">
              {data.warnings.map((warning, idx) => (
                <p
                  key={idx}
                  className="text-sm text-amber-700 dark:text-amber-300"
                >
                  {warning}
                </p>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Aggregation Level Indicator */}
      <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
        <span>{t('evaluation.statisticalResults.aggregation')}:</span>
        <Badge className="bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300">
          {data.aggregation}
        </Badge>
      </div>

      {/* Per-Model Statistics (for 'model' aggregation) */}
      {hasModelBreakdown && (
        <Card className="p-6">
          <h3 className="mb-4 text-lg font-medium dark:text-white">
            {t('evaluation.statisticalResults.perModelStatistics')}
          </h3>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead>
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-medium uppercase text-gray-500">
                    {t('evaluation.statisticalResults.model')}
                  </th>
                  {metricNames.map((metric) => (
                    <th
                      key={metric}
                      className="px-4 py-2 text-right text-xs font-medium uppercase text-gray-500"
                    >
                      {metric}
                    </th>
                  ))}
                  <th className="px-4 py-2 text-right text-xs font-medium uppercase text-gray-500">
                    {t('evaluation.statisticalResults.n')}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                {Object.entries(data.by_model!).map(([modelId, modelStats]) => (
                  <tr
                    key={modelId}
                    className="hover:bg-gray-50 dark:hover:bg-gray-800"
                  >
                    <td className="px-4 py-3 text-sm font-medium text-gray-900 dark:text-gray-100">
                      {modelStats.model_name || modelId}
                    </td>
                    {metricNames.map((metric) => {
                      const stats = modelStats.metrics[metric]
                      return (
                        <td
                          key={metric}
                          className="px-4 py-3 text-right font-mono text-sm text-gray-700 dark:text-gray-300"
                        >
                          {stats ? (
                            <div title={showStat('ci') ? `CI: [${formatValue(stats.ci_lower)}, ${formatValue(stats.ci_upper)}]` : undefined}>
                              <span>{formatValue(stats.mean)}</span>
                              {showStat('se') && stats.se !== undefined && (
                                <span className="ml-1 text-xs text-gray-400">
                                  ±{stats.se.toFixed(3)}
                                </span>
                              )}
                            </div>
                          ) : (
                            '—'
                          )}
                        </td>
                      )
                    })}
                    <td className="px-4 py-3 text-right text-sm text-gray-600 dark:text-gray-400">
                      {modelStats.sample_count}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Per-Field Statistics (for 'field' aggregation) */}
      {hasFieldBreakdown && (
        <Card className="p-6">
          <h3 className="mb-4 text-lg font-medium dark:text-white">
            {t('evaluation.statisticalResults.perFieldStatistics')}
          </h3>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead>
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-medium uppercase text-gray-500">
                    {t('evaluation.statisticalResults.field')}
                  </th>
                  {metricNames.map((metric) => (
                    <th
                      key={metric}
                      className="px-4 py-2 text-right text-xs font-medium uppercase text-gray-500"
                    >
                      {metric}
                    </th>
                  ))}
                  <th className="px-4 py-2 text-right text-xs font-medium uppercase text-gray-500">
                    {t('evaluation.statisticalResults.n')}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                {Object.entries(data.by_field!).map(([fieldName, fieldStats]) => (
                  <tr
                    key={fieldName}
                    className="hover:bg-gray-50 dark:hover:bg-gray-800"
                  >
                    <td
                      className="max-w-xs truncate px-4 py-3 text-sm font-medium text-gray-900 dark:text-gray-100"
                      title={fieldName}
                    >
                      {fieldName}
                    </td>
                    {metricNames.map((metric) => {
                      const stats = fieldStats.metrics[metric]
                      return (
                        <td
                          key={metric}
                          className="px-4 py-3 text-right font-mono text-sm text-gray-700 dark:text-gray-300"
                        >
                          {stats ? (
                            <div title={showStat('ci') ? `CI: [${formatValue(stats.ci_lower)}, ${formatValue(stats.ci_upper)}]` : undefined}>
                              <span>{formatValue(stats.mean)}</span>
                              {showStat('se') && stats.se !== undefined && (
                                <span className="ml-1 text-xs text-gray-400">
                                  ±{stats.se.toFixed(3)}
                                </span>
                              )}
                            </div>
                          ) : (
                            '—'
                          )}
                        </td>
                      )
                    })}
                    <td className="px-4 py-3 text-right text-sm text-gray-600 dark:text-gray-400">
                      {fieldStats.sample_count}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Overall Metric Statistics */}
      <Card className="p-6">
        <h3 className="mb-4 text-lg font-medium dark:text-white">
          {hasModelBreakdown || hasFieldBreakdown
            ? t('evaluation.statisticalResults.overallStatistics')
            : t('evaluation.statisticalResults.metricStatistics')}
        </h3>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead>
              <tr>
                <th className="px-4 py-2 text-left text-xs font-medium uppercase text-gray-500">
                  {t('evaluation.statisticalResults.metric')}
                </th>
                <th className="px-4 py-2 text-right text-xs font-medium uppercase text-gray-500">
                  {t('evaluation.statisticalResults.mean')}
                </th>
                {showStat('ci') && (
                  <th className="px-4 py-2 text-right text-xs font-medium uppercase text-gray-500">
                    {t('evaluation.statisticalResults.ci95')}
                  </th>
                )}
                <th className="px-4 py-2 text-right text-xs font-medium uppercase text-gray-500">
                  {t('evaluation.statisticalResults.std')}
                </th>
                {showStat('se') && (
                  <th className="px-4 py-2 text-right text-xs font-medium uppercase text-gray-500">
                    {t('evaluation.statisticalResults.se')}
                  </th>
                )}
                <th className="px-4 py-2 text-right text-xs font-medium uppercase text-gray-500">
                  {t('evaluation.statisticalResults.n')}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {metricNames.map((metric) => {
                const stats = data.metrics[metric]
                return (
                  <tr
                    key={metric}
                    className="hover:bg-gray-50 dark:hover:bg-gray-800"
                  >
                    <td className="px-4 py-3 text-sm font-medium text-gray-900 dark:text-gray-100">
                      {metric}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-sm text-gray-700 dark:text-gray-300">
                      {formatValue(stats.mean)}
                    </td>
                    {showStat('ci') && (
                      <td className="px-4 py-3 text-right font-mono text-sm text-gray-600 dark:text-gray-400">
                        [{formatValue(stats.ci_lower)},{' '}
                        {formatValue(stats.ci_upper)}]
                      </td>
                    )}
                    <td className="px-4 py-3 text-right font-mono text-sm text-gray-600 dark:text-gray-400">
                      {stats.std.toFixed(4)}
                    </td>
                    {showStat('se') && (
                      <td className="px-4 py-3 text-right font-mono text-sm text-gray-600 dark:text-gray-400">
                        {stats.se !== undefined ? stats.se.toFixed(4) : '—'}
                      </td>
                    )}
                    <td className="px-4 py-3 text-right text-sm text-gray-600 dark:text-gray-400">
                      {stats.n}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Pairwise Comparisons - only show if significance tests or effect sizes are selected */}
      {showSignificanceTests && data.pairwise_comparisons && data.pairwise_comparisons.length > 0 && (
        <Card className="p-6">
          <div className="mb-4 flex items-start justify-between">
            <h3 className="text-lg font-medium dark:text-white">
              {t('evaluation.statisticalResults.pairwiseComparisons')}
            </h3>

            {/* Bonferroni Correction Indicator */}
            {showBonferroniInfo && data.bonferroni_correction && (
              <div
                className={`flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs ${
                  data.bonferroni_correction.applied
                    ? 'border border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-300'
                    : 'border border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300'
                }`}
              >
                <InformationCircleIcon className="h-4 w-4" />
                <div>
                  {data.bonferroni_correction.applied ? (
                    <>
                      <span className="font-medium">{t('evaluation.statisticalResults.bonferroniCorrected')}</span>
                      <span className="ml-1 text-gray-500 dark:text-gray-400">
                        ({data.bonferroni_correction.num_comparisons}{' '}
                        comparisons, α ={' '}
                        {data.bonferroni_correction.corrected_alpha.toFixed(4)})
                      </span>
                    </>
                  ) : (
                    <>
                      <span className="font-medium">{t('evaluation.statisticalResults.multipleComparisons')}</span>
                      <span className="ml-1 text-gray-500 dark:text-gray-400">
                        ({data.bonferroni_correction.num_comparisons} tests,
                        uncorrected α ={' '}
                        {data.bonferroni_correction.original_alpha})
                      </span>
                    </>
                  )}
                </div>
              </div>
            )}

            {/* Auto-detect multiple comparisons warning if no bonferroni_correction data */}
            {showBonferroniInfo &&
              !data.bonferroni_correction &&
              data.pairwise_comparisons.length > 1 && (
                <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
                  <InformationCircleIcon className="h-4 w-4" />
                  <span>
                    {t('evaluation.statisticalResults.considerBonferroni', { count: data.pairwise_comparisons.length })}
                  </span>
                </div>
              )}
          </div>

          <div className="mb-3 text-xs text-gray-500">
            * p&lt;0.05, ** p&lt;0.01, *** p&lt;0.001
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead>
                <tr>
                  <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">
                    {t('evaluation.statisticalResults.modelA')}
                  </th>
                  <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">
                    {t('evaluation.statisticalResults.modelB')}
                  </th>
                  <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">
                    {t('evaluation.statisticalResults.metric')}
                  </th>
                  <th className="px-3 py-2 text-center text-xs font-medium uppercase text-gray-500">
                    {t('evaluation.statisticalResults.pValue')}
                  </th>
                  {showEffectSizes && (
                    <th className="px-3 py-2 text-center text-xs font-medium uppercase text-gray-500">
                      {t('evaluation.statisticalResults.effectSize')}
                    </th>
                  )}
                  <th className="px-3 py-2 text-center text-xs font-medium uppercase text-gray-500">
                    {t('evaluation.statisticalResults.significant')}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                {data.pairwise_comparisons.map((comp, idx) => (
                  <tr
                    key={idx}
                    className="hover:bg-gray-50 dark:hover:bg-gray-800"
                  >
                    <td className="px-3 py-2 text-sm text-gray-900 dark:text-gray-100">
                      {comp.model_a}
                    </td>
                    <td className="px-3 py-2 text-sm text-gray-900 dark:text-gray-100">
                      {comp.model_b}
                    </td>
                    <td className="px-3 py-2 text-sm text-gray-700 dark:text-gray-300">
                      {comp.metric}
                    </td>
                    <td className="px-3 py-2 text-center font-mono text-sm">
                      {comp.ttest_p !== undefined && (
                        <span className="text-gray-700 dark:text-gray-300">
                          {formatPValue(comp.ttest_p)}
                          <sup className="ml-0.5 font-bold text-emerald-600">
                            {getSignificanceStars(comp.ttest_p)}
                          </sup>
                        </span>
                      )}
                    </td>
                    {showEffectSizes && (
                      <td className="px-3 py-2 text-center">
                        {comp.cohens_d !== undefined && (
                          <Badge
                            className={`text-xs ${getEffectSizeColor(comp.cohens_d_interpretation)}`}
                          >
                            d={comp.cohens_d.toFixed(2)} (
                            {comp.cohens_d_interpretation})
                          </Badge>
                        )}
                      </td>
                    )}
                    <td className="px-3 py-2 text-center">
                      {comp.significant ? (
                        <CheckCircleIcon className="mx-auto h-5 w-5 text-green-500" />
                      ) : (
                        <XCircleIcon className="mx-auto h-5 w-5 text-gray-400" />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Correlation Matrix - only show if correlation is selected */}
      {showStat('correlation') && data.correlations && Object.keys(data.correlations).length > 0 && (
        <Card className="p-6">
          <h3 className="mb-4 text-lg font-medium dark:text-white">
            {t('evaluation.statisticalResults.correlationMatrix')}
          </h3>
          <div className="overflow-x-auto">
            <table className="min-w-full">
              <thead>
                <tr>
                  <th className="px-2 py-2 text-xs font-medium text-gray-500"></th>
                  {metricNames.map((metric) => (
                    <th
                      key={metric}
                      className="px-2 py-2 text-center text-xs font-medium text-gray-500"
                      style={{
                        writingMode: 'vertical-rl',
                        transform: 'rotate(180deg)',
                      }}
                    >
                      {metric}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {metricNames.map((metricA) => (
                  <tr key={metricA}>
                    <td className="px-2 py-2 text-xs font-medium text-gray-700 dark:text-gray-300">
                      {metricA}
                    </td>
                    {metricNames.map((metricB) => {
                      const value =
                        data.correlations?.[metricA]?.[metricB] ?? null
                      return (
                        <td
                          key={metricB}
                          className={`px-2 py-2 text-center font-mono text-xs ${getCorrelationColor(value)}`}
                          title={
                            value !== null ? `r = ${value.toFixed(3)}` : 'N/A'
                          }
                        >
                          {value !== null ? value.toFixed(2) : '-'}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-3 flex items-center gap-4 text-xs text-gray-500">
            <div className="flex items-center gap-1">
              <div className="h-3 w-3 rounded bg-green-500" />
              <span>{t('evaluation.statisticalResults.strongPositive')}</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="h-3 w-3 rounded bg-red-500" />
              <span>{t('evaluation.statisticalResults.strongNegative')}</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="h-3 w-3 rounded bg-gray-200 dark:bg-gray-700" />
              <span>{t('evaluation.statisticalResults.weakNone')}</span>
            </div>
          </div>
        </Card>
      )}
    </div>
  )
}
