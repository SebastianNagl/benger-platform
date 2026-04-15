/**
 * Historical Trend Chart Component
 *
 * Line chart showing metric values over time with confidence intervals.
 * Supports multiple models with distinct colors and date range selection.
 */

'use client'

import { useI18n } from '@/contexts/I18nContext'
import { useMemo, useState } from 'react'
import {
  Area,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

interface DataPoint {
  date: string
  model_id: string
  value: number
  ci_lower?: number
  ci_upper?: number
}

interface HistoricalTrendChartProps {
  data: DataPoint[]
  modelIds: string[]
  metric: string
  height?: number
  showConfidenceIntervals?: boolean
}

const COLORS = [
  '#009E73', // green
  '#E69F00', // orange
  '#56B4E9', // sky blue
  '#CC79A7', // pink
  '#0072B2', // blue
  '#D55E00', // vermillion
  '#F0E442', // yellow
  '#999999', // gray
]

const formatDate = (dateStr: string, dateRange: number): string => {
  const date = new Date(dateStr)

  if (dateRange <= 7) {
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
    })
  } else if (dateRange <= 90) {
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  } else {
    return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
  }
}

const formatValue = (value: number): string => {
  if (value >= 0 && value <= 1) {
    return `${(value * 100).toFixed(1)}%`
  }
  return value.toFixed(2)
}

const calculateDateRange = (dates: string[]): number => {
  if (dates.length === 0) return 0
  const sortedDates = dates.map((d) => new Date(d).getTime()).sort()
  const rangeMs = sortedDates[sortedDates.length - 1] - sortedDates[0]
  return Math.ceil(rangeMs / (1000 * 60 * 60 * 24))
}

export function HistoricalTrendChart({
  data,
  modelIds,
  metric,
  height = 300,
  showConfidenceIntervals = true,
}: HistoricalTrendChartProps) {
  const { t } = useI18n()
  const [selectedDateRange, setSelectedDateRange] = useState<
    'all' | '7d' | '30d' | '90d'
  >('all')

  const { chartData, dateRange } = useMemo(() => {
    const now = new Date()
    let cutoffDate: Date | null = null

    if (selectedDateRange === '7d') {
      cutoffDate = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
    } else if (selectedDateRange === '30d') {
      cutoffDate = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000)
    } else if (selectedDateRange === '90d') {
      cutoffDate = new Date(now.getTime() - 90 * 24 * 60 * 60 * 1000)
    }

    const filteredData = cutoffDate
      ? data.filter((d) => new Date(d.date) >= cutoffDate)
      : data

    const dateMap: Record<string, Record<string, any>> = {}

    filteredData.forEach((point) => {
      if (!dateMap[point.date]) {
        dateMap[point.date] = { date: point.date }
      }
      dateMap[point.date][point.model_id] = point.value

      if (
        showConfidenceIntervals &&
        point.ci_lower !== undefined &&
        point.ci_upper !== undefined
      ) {
        dateMap[point.date][`${point.model_id}_ci`] = [
          point.ci_lower,
          point.ci_upper,
        ]
      }
    })

    const sortedData = Object.values(dateMap).sort(
      (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime()
    )

    const uniqueDates = sortedData.map((d) => d.date)
    const range = calculateDateRange(uniqueDates)

    return { chartData: sortedData, dateRange: range }
  }, [data, selectedDateRange, showConfidenceIntervals])

  const dateRangeButtons = [
    { label: t('evaluation.charts.trend.range7d'), value: '7d' as const },
    { label: t('evaluation.charts.trend.range30d'), value: '30d' as const },
    { label: t('evaluation.charts.trend.range90d'), value: '90d' as const },
    { label: t('evaluation.charts.trend.rangeAll'), value: 'all' as const },
  ]

  const isPercentage = useMemo(() => {
    return data.every((d) => d.value >= 0 && d.value <= 1)
  }, [data])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">
          {metric} - {t('evaluation.charts.trend.historicalTrend')}
        </h3>

        <div className="flex gap-1 rounded-lg border border-gray-200 bg-white p-1 dark:border-gray-700 dark:bg-gray-800">
          {dateRangeButtons.map((button) => (
            <button
              key={button.value}
              onClick={() => setSelectedDateRange(button.value)}
              className={`rounded px-3 py-1 text-sm font-medium transition-colors ${
                selectedDateRange === button.value
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700'
              }`}
            >
              {button.label}
            </button>
          ))}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />

          <XAxis
            dataKey="date"
            tick={{ fontSize: 11, fill: '#6b7280' }}
            stroke="#9ca3af"
            tickFormatter={(value) => formatDate(value, dateRange)}
          />

          <YAxis
            tick={{ fontSize: 10, fill: '#6b7280' }}
            stroke="#9ca3af"
            domain={isPercentage ? [0, 1] : ['auto', 'auto']}
            tickFormatter={(value) => formatValue(value)}
            label={{
              value: metric,
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
            labelFormatter={(label) => {
              const date = new Date(label)
              return date.toLocaleString('en-US', {
                month: 'short',
                day: 'numeric',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
              })
            }}
            formatter={(value, name): any => {
              if (typeof name === 'string' && name.endsWith('_ci')) return null
              return [formatValue(value as number), name]
            }}
          />

          <Legend
            wrapperStyle={{ fontSize: '14px', paddingTop: '10px' }}
            iconType="line"
          />

          {showConfidenceIntervals &&
            modelIds.map((modelId, index) => {
              const hasCI = chartData.some((d) => d[`${modelId}_ci`])
              if (!hasCI) return null

              const ciData = chartData.map((d) => ({
                date: d.date,
                value: d[`${modelId}_ci`] as [number, number] | undefined,
              }))

              return (
                <Area
                  key={`${modelId}_ci`}
                  dataKey={`${modelId}_ci`}
                  stroke="none"
                  fill={COLORS[index % COLORS.length]}
                  fillOpacity={0.2}
                  isAnimationActive={false}
                />
              )
            })}

          {modelIds.map((modelId, index) => (
            <Line
              key={modelId}
              type="monotone"
              dataKey={modelId}
              stroke={COLORS[index % COLORS.length]}
              strokeWidth={2}
              dot={{ r: 3 }}
              activeDot={{ r: 5 }}
              name={modelId}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>

      {chartData.length === 0 && (
        <div className="flex h-48 items-center justify-center text-gray-500 dark:text-gray-400">
          {t('evaluation.charts.trend.noDataForRange')}
        </div>
      )}
    </div>
  )
}
