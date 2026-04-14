/**
 * Metric Distribution Visualization Component
 *
 * Shows distribution of metric values using Recharts histograms and box plots.
 * Issue #763: Per-sample evaluation results and visualization dashboard
 */

'use client'

import { useI18n } from '@/contexts/I18nContext'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

interface MetricDistributionData {
  metric_name: string
  mean: number
  median: number
  std: number
  min: number
  max: number
  quartiles: {
    q1: number
    q2: number
    q3: number
  }
  histogram: Record<string, number>
}

interface MetricDistributionChartProps {
  data: MetricDistributionData
  title?: string
  height?: number
}

export function MetricDistributionChart({
  data,
  title,
  height = 400,
}: MetricDistributionChartProps) {
  const { t } = useI18n()
  // Convert histogram object to array for Recharts
  const histogramData = Object.entries(data.histogram).map(
    ([range, count]) => ({
      range,
      count,
    })
  )

  return (
    <div className="space-y-4">
      <div className="rounded-lg border bg-white p-4">
        <h3 className="mb-4 text-lg font-medium">
          {title || t('evaluation.metricDistribution.titleWithMetric', { metric: data.metric_name })}
        </h3>

        {/* Statistics Summary */}
        <div className="mb-6 grid grid-cols-2 gap-4 rounded-lg bg-gray-50 p-4 md:grid-cols-5">
          <div>
            <div className="text-xs text-gray-600">{t('evaluation.metricDistribution.mean')}</div>
            <div className="text-lg font-bold">{data.mean.toFixed(3)}</div>
          </div>
          <div>
            <div className="text-xs text-gray-600">{t('evaluation.metricDistribution.median')}</div>
            <div className="text-lg font-bold">{data.median.toFixed(3)}</div>
          </div>
          <div>
            <div className="text-xs text-gray-600">{t('evaluation.metricDistribution.stdDev')}</div>
            <div className="text-lg font-bold">{data.std.toFixed(3)}</div>
          </div>
          <div>
            <div className="text-xs text-gray-600">{t('evaluation.metricDistribution.min')}</div>
            <div className="text-lg font-bold">{data.min.toFixed(3)}</div>
          </div>
          <div>
            <div className="text-xs text-gray-600">{t('evaluation.metricDistribution.max')}</div>
            <div className="text-lg font-bold">{data.max.toFixed(3)}</div>
          </div>
        </div>

        {/* Histogram */}
        <div>
          <h4 className="mb-2 text-sm font-medium text-gray-700">
            {t('evaluation.metricDistribution.valueDistribution')}
          </h4>
          <ResponsiveContainer width="100%" height={height}>
            <BarChart data={histogramData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                dataKey="range"
                angle={-45}
                textAnchor="end"
                height={80}
                fontSize={11}
              />
              <YAxis
                label={{ value: t('evaluation.metricDistribution.count'), angle: -90, position: 'insideLeft' }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'white',
                  border: '1px solid #ccc',
                  borderRadius: '4px',
                }}
              />
              <Bar dataKey="count" name={t('evaluation.metricDistribution.sampleCount')}>
                {histogramData.map((entry, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={index % 2 === 0 ? '#3b82f6' : '#60a5fa'}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Quartiles Visualization */}
        <div className="mt-6">
          <h4 className="mb-2 text-sm font-medium text-gray-700">{t('evaluation.metricDistribution.quartiles')}</h4>
          <div className="relative h-8 w-full rounded bg-gradient-to-r from-red-200 via-yellow-200 to-green-200">
            {/* Q1 Marker */}
            <div
              className="absolute top-0 h-full w-0.5 bg-red-600"
              style={{
                left: `${((data.quartiles.q1 - data.min) / (data.max - data.min)) * 100}%`,
              }}
              title={`Q1: ${data.quartiles.q1.toFixed(3)}`}
            >
              <div className="absolute -top-6 left-1/2 -translate-x-1/2 text-xs font-medium">
                Q1
              </div>
            </div>
            {/* Median (Q2) Marker */}
            <div
              className="absolute top-0 h-full w-0.5 bg-yellow-600"
              style={{
                left: `${((data.quartiles.q2 - data.min) / (data.max - data.min)) * 100}%`,
              }}
              title={`${t('evaluation.metricDistribution.median')}: ${data.quartiles.q2.toFixed(3)}`}
            >
              <div className="absolute -top-6 left-1/2 -translate-x-1/2 text-xs font-medium">
                {t('evaluation.metricDistribution.median')}
              </div>
            </div>
            {/* Q3 Marker */}
            <div
              className="absolute top-0 h-full w-0.5 bg-green-600"
              style={{
                left: `${((data.quartiles.q3 - data.min) / (data.max - data.min)) * 100}%`,
              }}
              title={`Q3: ${data.quartiles.q3.toFixed(3)}`}
            >
              <div className="absolute -top-6 left-1/2 -translate-x-1/2 text-xs font-medium">
                Q3
              </div>
            </div>
          </div>
          <div className="mt-2 flex justify-between text-xs text-gray-600">
            <span>{t('evaluation.metricDistribution.min')}: {data.min.toFixed(3)}</span>
            <span>{t('evaluation.metricDistribution.max')}: {data.max.toFixed(3)}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
