/**
 * Model Comparison Chart Component
 *
 * Radar and bar charts for comparing multiple models across metrics.
 * Includes confidence intervals and error bars for publication-ready visualizations.
 * Issue #763: Per-sample evaluation results and visualization dashboard
 */

'use client'

import { useI18n } from '@/contexts/I18nContext'
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
  const { t } = useI18n()

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

  // Missing data warning component
  const MissingDataWarning = () =>
    modelsWithMissingData.size > 0 ? (
      <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-400">
        <strong>{t('evaluation.modelComparison.missingData')}:</strong> {t('evaluation.modelComparison.missingDataDetail', { models: Array.from(modelsWithMissingData).join(', ') })}
      </div>
    ) : null

  if (visualizationType === 'radar') {
    return (
      <div className="space-y-2">
        {title && (
          <h3 className="text-lg font-medium text-gray-900">{title}</h3>
        )}
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
              formatter={(value): any => (value as number).toFixed(3)}
            />
          </RadarChart>
        </ResponsiveContainer>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {title && (
        <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">
          {title}
        </h3>
      )}
      <MissingDataWarning />
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={barData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis
            dataKey="model"
            tick={{ fontSize: 12, fill: '#6b7280' }}
            stroke="#9ca3af"
          />
          <YAxis
            domain={[0, 1]}
            tick={{ fontSize: 10, fill: '#6b7280' }}
            stroke="#9ca3af"
            label={{
              value: t('evaluation.modelComparison.score'),
              angle: -90,
              position: 'insideLeft',
              style: { fontSize: 12, fill: '#6b7280' },
            }}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: 'white',
              border: '1px solid #d1d5db',
              borderRadius: '6px',
              boxShadow: '0 1px 3px rgba(0, 0, 0, 0.1)',
            }}
            formatter={(value, name): any => [
              (value as number).toFixed(3),
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
                  stroke="#374151"
                />
              )}
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>

      {/* Model performance summary table */}
      <div className="mt-4 overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th className="px-4 py-3 text-left font-semibold text-gray-700 dark:text-gray-300">
                {t('evaluation.modelComparison.model')}
              </th>
              {metrics.map((metric) => (
                <th
                  key={metric}
                  className="px-4 py-3 text-right font-semibold text-gray-700 dark:text-gray-300"
                >
                  {metric}
                </th>
              ))}
              <th className="px-4 py-3 text-right font-semibold text-gray-700 dark:text-gray-300">
                {t('evaluation.modelComparison.average')}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200 bg-white dark:divide-gray-700 dark:bg-gray-900">
            {models.map((model, index) => {
              const metricValues = metrics.map((m) =>
                getMetricValue(model.metrics[m] || 0)
              )
              const avg =
                metricValues.reduce((a, b) => a + b, 0) / metricValues.length

              return (
                <tr
                  key={model.model_id}
                  className="hover:bg-gray-50 dark:hover:bg-gray-800"
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div
                        className="h-3 w-3 rounded-full"
                        style={{
                          backgroundColor: COLORS[index % COLORS.length],
                        }}
                      />
                      <span className="font-medium text-gray-900 dark:text-gray-100">
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
                          <span className="font-medium text-gray-900 dark:text-gray-100">
                            {value.toFixed(3)}
                          </span>
                          {showConfidenceIntervals && hasCI && (
                            <span className="text-xs text-gray-500 dark:text-gray-400">
                              [
                              {(
                                metricData as MetricValue
                              ).confidenceInterval!.lower.toFixed(3)}
                              ,{' '}
                              {(
                                metricData as MetricValue
                              ).confidenceInterval!.upper.toFixed(3)}
                              ]
                            </span>
                          )}
                        </div>
                      </td>
                    )
                  })}
                  <td className="px-4 py-3 text-right font-bold tabular-nums text-gray-900 dark:text-gray-100">
                    {avg.toFixed(3)}
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
