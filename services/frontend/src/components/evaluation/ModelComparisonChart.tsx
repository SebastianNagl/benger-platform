/**
 * Model Comparison Chart Component
 *
 * Radar and bar charts for comparing multiple models across metrics.
 * Includes confidence intervals and error bars for publication-ready visualizations.
 * Issue #763: Per-sample evaluation results and visualization dashboard
 */

'use client'

import { useI18n } from '@/contexts/I18nContext'
import { formatDecimal } from '@/lib/i18n/locales'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ErrorBar,
  Legend,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

interface MetricValue {
  value: number
  confidenceInterval?: {
    lower: number
    upper: number
  }
  error?: number
}

interface ModelMetrics {
  model_id: string
  metrics: Record<string, number | MetricValue>
}

interface ModelComparisonChartProps {
  models: ModelMetrics[]
  metrics: string[]
  visualizationType?: 'radar' | 'bar'
  title?: string
  height?: number
  showErrorBars?: boolean
  showConfidenceIntervals?: boolean
}

const COLORS = [
  '#3b82f6', // blue
  '#10b981', // green
  '#f59e0b', // amber
  '#ef4444', // red
  '#8b5cf6', // purple
  '#ec4899', // pink
]

const getMetricValue = (metric: number | MetricValue): number => {
  return typeof metric === 'number' ? metric : metric.value
}

const getErrorValue = (metric: number | MetricValue): number | undefined => {
  if (typeof metric === 'number') return undefined
  if (metric.error !== undefined) return metric.error
  if (metric.confidenceInterval) {
    return (
      (metric.confidenceInterval.upper - metric.confidenceInterval.lower) / 2
    )
  }
  return undefined
}

export function ModelComparisonChart({
  models,
  metrics,
  visualizationType = 'radar',
  title,
  height = 400,
  showErrorBars = true,
  showConfidenceIntervals = true,
}: ModelComparisonChartProps) {
  const { t, locale } = useI18n()

  // Track models with missing data for scientific transparency
  const modelsWithMissingData = new Set<string>()

  // Transform data for radar chart
  const radarData = metrics.map((metric) => {
    const dataPoint: Record<string, any> = { metric }
    models.forEach((model) => {
      const metricData = model.metrics[metric]
      if (metricData === undefined || metricData === null) {
        modelsWithMissingData.add(model.model_id)
      }
      dataPoint[model.model_id] = getMetricValue(metricData || 0)
    })
    return dataPoint
  })

  // Transform data for bar chart with error bars
  const barData = models.map((model) => {
    const dataPoint: Record<string, any> = { model: model.model_id }
    metrics.forEach((metric) => {
      const metricData = model.metrics[metric]
      if (metricData === undefined || metricData === null) {
        modelsWithMissingData.add(model.model_id)
      }
      dataPoint[metric] = getMetricValue(metricData || 0)
      if (showErrorBars) {
        const error = getErrorValue(metricData || 0)
        if (error !== undefined) {
          dataPoint[`${metric}_error`] = error
        }
      }
    })
    return dataPoint
  })

  // Missing data warning component.
  // Collapsed by default to a single-line count so a large number of models
  // with incomplete metrics doesn't render as a giant amber wall; the full
  // comma-joined list is revealed only when the <details> is expanded.
  const MissingDataWarning = () =>
    modelsWithMissingData.size > 0 ? (
      <details className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-400">
        <summary className="cursor-pointer">
          <strong>{t('evaluation.modelComparison.missingData')}:</strong>{' '}
          {t('evaluation.modelComparison.missingDataSummary', {
            count: modelsWithMissingData.size,
          })}
        </summary>
        <div className="mt-2 wrap-break-word">
          {Array.from(modelsWithMissingData).join(', ')}
        </div>
      </details>
    ) : null

  if (visualizationType === 'radar') {
    return (
      <div className="space-y-2">
        {title && (
          <h3 className="text-lg font-medium text-zinc-900">{title}</h3>
        )}
        {/* eslint-disable-next-line react-hooks/static-components */}
        <MissingDataWarning />
        <ResponsiveContainer width="100%" height={height}>
          <RadarChart data={radarData}>
            <PolarGrid />
            <PolarAngleAxis dataKey="metric" tick={{ fontSize: 12 }} />
            <PolarRadiusAxis
              angle={90}
              domain={[0, 1]}
              tick={{ fontSize: 10 }}
            />
            {models.map((model, index) => (
              <Radar
                key={model.model_id}
                name={model.model_id}
                dataKey={model.model_id}
                stroke={COLORS[index % COLORS.length]}
                fill={COLORS[index % COLORS.length]}
                fillOpacity={0.3}
                strokeWidth={2}
              />
            ))}
            <Legend wrapperStyle={{ fontSize: '14px' }} iconType="circle" />
            <Tooltip
              contentStyle={{
                backgroundColor: 'white',
                border: '1px solid #ccc',
                borderRadius: '4px',
              }}
              formatter={(value): any =>
                formatDecimal(value as number, locale, 3)
              }
            />
          </RadarChart>
        </ResponsiveContainer>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {title && (
        <h3 className="text-lg font-medium text-zinc-900 dark:text-zinc-100">
          {title}
        </h3>
      )}
      {/* eslint-disable-next-line react-hooks/static-components */}
      <MissingDataWarning />
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={barData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e4e4e7" />
          <XAxis
            dataKey="model"
            tick={{ fontSize: 12, fill: '#71717a' }}
            stroke="#a1a1aa"
          />
          <YAxis
            domain={[0, 1]}
            tick={{ fontSize: 10, fill: '#71717a' }}
            stroke="#a1a1aa"
            label={{
              value: t('evaluation.modelComparison.score'),
              angle: -90,
              position: 'insideLeft',
              style: { fontSize: 12, fill: '#71717a' },
            }}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: 'white',
              border: '1px solid #d4d4d8',
              borderRadius: '6px',
              boxShadow: '0 1px 3px rgba(0, 0, 0, 0.1)',
            }}
            formatter={(value, name): any => [
              formatDecimal(value as number, locale, 3),
              name,
            ]}
          />
          <Legend
            wrapperStyle={{ fontSize: '14px', paddingTop: '10px' }}
            iconType="circle"
          />
          {metrics.map((metric, index) => (
            <Bar
              key={metric}
              dataKey={metric}
              fill={COLORS[index % COLORS.length]}
              name={metric}
              radius={[4, 4, 0, 0]}
            >
              {showErrorBars && (
                <ErrorBar
                  dataKey={`${metric}_error`}
                  width={4}
                  strokeWidth={2}
                  stroke="#3f3f46"
                />
              )}
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>

      {/* Model performance summary table */}
      <div className="mt-4 overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-700">
        <table className="w-full text-sm">
          <thead className="bg-zinc-50 dark:bg-zinc-800">
            <tr>
              <th className="px-4 py-3 text-left font-semibold text-zinc-700 dark:text-zinc-300">
                {t('evaluation.modelComparison.model')}
              </th>
              {metrics.map((metric) => (
                <th
                  key={metric}
                  className="px-4 py-3 text-right font-semibold text-zinc-700 dark:text-zinc-300"
                >
                  {metric}
                </th>
              ))}
              <th className="px-4 py-3 text-right font-semibold text-zinc-700 dark:text-zinc-300">
                {t('evaluation.modelComparison.average')}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-200 bg-white dark:divide-zinc-700 dark:bg-zinc-900">
            {models.map((model, index) => {
              const metricValues = metrics.map((m) =>
                getMetricValue(model.metrics[m] || 0),
              )
              const avg =
                metricValues.reduce((a, b) => a + b, 0) / metricValues.length

              return (
                <tr
                  key={model.model_id}
                  className="hover:bg-zinc-50 dark:hover:bg-zinc-800"
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div
                        className="h-3 w-3 rounded-full"
                        style={{
                          backgroundColor: COLORS[index % COLORS.length],
                        }}
                      />
                      <span className="font-medium text-zinc-900 dark:text-zinc-100">
                        {model.model_id}
                      </span>
                    </div>
                  </td>
                  {metrics.map((metric) => {
                    const metricData = model.metrics[metric]
                    const value = getMetricValue(metricData || 0)
                    const hasCI =
                      typeof metricData === 'object' &&
                      metricData.confidenceInterval

                    return (
                      <td
                        key={metric}
                        className="px-4 py-3 text-right tabular-nums"
                      >
                        <div className="flex flex-col items-end">
                          <span className="font-medium text-zinc-900 dark:text-zinc-100">
                            {formatDecimal(value, locale, 3)}
                          </span>
                          {showConfidenceIntervals && hasCI && (
                            <span className="text-xs text-zinc-500 dark:text-zinc-400">
                              [
                              {formatDecimal(
                                (metricData as MetricValue).confidenceInterval!
                                  .lower,
                                locale,
                                3,
                              )}
                              ,{' '}
                              {formatDecimal(
                                (metricData as MetricValue).confidenceInterval!
                                  .upper,
                                locale,
                                3,
                              )}
                              ]
                            </span>
                          )}
                        </div>
                      </td>
                    )
                  })}
                  <td className="px-4 py-3 text-right font-bold text-zinc-900 tabular-nums dark:text-zinc-100">
                    {formatDecimal(avg, locale, 3)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
