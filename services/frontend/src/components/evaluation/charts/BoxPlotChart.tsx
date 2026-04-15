/**
 * Box Plot Chart Component
 *
 * Displays score distributions with quartiles, median, and outliers.
 * Uses custom Bar shape rendering for proper box plot visualization.
 *
 * Issue #934: Academic-quality evaluation results display
 */

'use client'

import { useI18n } from '@/contexts/I18nContext'
import { useMemo } from 'react'
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

export interface BoxPlotData {
  name: string
  min: number
  q1: number
  median: number
  q3: number
  max: number
  mean?: number
  outliers?: number[]
  count?: number
}

interface BoxPlotChartProps {
  data: BoxPlotData[]
  height?: number
  colorScheme?: 'default' | 'accessible'
  showMean?: boolean
  showOutliers?: boolean
  xAxisLabel?: string
  yAxisLabel?: string
  className?: string
}

// Custom tooltip
function CustomTooltip({ active, payload, t }: any) {
  if (!active || !payload || !payload[0]) return null
  const item = payload[0].payload as BoxPlotData & { color: string }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-3 shadow-lg dark:border-gray-700 dark:bg-gray-800">
      <p className="mb-2 font-semibold text-gray-900 dark:text-gray-100">
        {item.name}
      </p>
      <div className="space-y-1 text-sm">
        <div className="flex justify-between gap-4">
          <span className="text-gray-500">{t('evaluation.charts.boxPlot.max')}:</span>
          <span className="font-mono">{item.max?.toFixed(3)}</span>
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-gray-500">{t('evaluation.charts.boxPlot.q3')}:</span>
          <span className="font-mono">{item.q3?.toFixed(3)}</span>
        </div>
        <div className="flex justify-between gap-4">
          <span className="font-medium text-gray-500">{t('evaluation.charts.boxPlot.median')}:</span>
          <span className="font-mono font-medium">
            {item.median?.toFixed(3)}
          </span>
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-gray-500">{t('evaluation.charts.boxPlot.q1')}:</span>
          <span className="font-mono">{item.q1?.toFixed(3)}</span>
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-gray-500">{t('evaluation.charts.boxPlot.min')}:</span>
          <span className="font-mono">{item.min?.toFixed(3)}</span>
        </div>
        {item.mean !== undefined && (
          <div className="mt-1 flex justify-between gap-4 border-t border-gray-200 pt-1 dark:border-gray-700">
            <span className="text-gray-500">{t('evaluation.charts.boxPlot.mean')}:</span>
            <span className="font-mono">{item.mean?.toFixed(3)}</span>
          </div>
        )}
        {item.count !== undefined && (
          <div className="flex justify-between gap-4">
            <span className="text-gray-500">{t('evaluation.charts.boxPlot.n')}:</span>
            <span className="font-mono">{item.count?.toLocaleString()}</span>
          </div>
        )}
      </div>
    </div>
  )
}

// Color palettes
const COLORS = {
  default: [
    '#10b981', // emerald-500
    '#3b82f6', // blue-500
    '#f59e0b', // amber-500
    '#ef4444', // red-500
    '#8b5cf6', // violet-500
    '#ec4899', // pink-500
    '#06b6d4', // cyan-500
    '#84cc16', // lime-500
  ],
  accessible: [
    '#0571b0', // Blue
    '#ca0020', // Red
    '#f4a582', // Light orange
    '#92c5de', // Light blue
    '#404040', // Dark gray
    '#bababa', // Light gray
    '#dfc27d', // Tan
    '#018571', // Teal
  ],
}

// Custom shape for box plot - receives props from recharts Bar
const BoxPlotShape = (props: any) => {
  const { x, y, width, height, payload, background } = props

  if (!payload) return null

  const color = payload.color || '#10b981'
  const boxWidth = Math.min(width * 0.7, 35)
  const centerX = x + width / 2

  // Get the background dimensions which give us the full chart area
  // The bar's y and height are for the IQR (q1 to q3)
  // We need to calculate whisker positions relative to this

  // The bar is positioned from q1 (bottom) to q3 (top)
  // y = top of bar (q3 position)
  // y + height = bottom of bar (q1 position)
  const q3Y = y
  const q1Y = y + height

  // Calculate scale: pixels per unit value
  // height = (q3 - q1) in pixels
  // So scale = height / (q3 - q1)
  const iqr = payload.q3 - payload.q1
  if (iqr === 0) return null

  const scale = height / iqr

  // Calculate whisker positions using the same scale
  const minY = q1Y + (payload.q1 - payload.min) * scale // Below q1
  const maxY = q3Y - (payload.max - payload.q3) * scale // Above q3
  const medianY = q3Y + (payload.q3 - payload.median) * scale

  return (
    <g>
      {/* Vertical whisker line from min to max */}
      <line
        x1={centerX}
        y1={maxY}
        x2={centerX}
        y2={minY}
        stroke="#374151"
        strokeWidth={1.5}
      />

      {/* Max whisker cap (top) */}
      <line
        x1={centerX - boxWidth / 3}
        y1={maxY}
        x2={centerX + boxWidth / 3}
        y2={maxY}
        stroke="#374151"
        strokeWidth={2}
      />

      {/* Min whisker cap (bottom) */}
      <line
        x1={centerX - boxWidth / 3}
        y1={minY}
        x2={centerX + boxWidth / 3}
        y2={minY}
        stroke="#374151"
        strokeWidth={2}
      />

      {/* IQR Box (Q1 to Q3) */}
      <rect
        x={centerX - boxWidth / 2}
        y={q3Y}
        width={boxWidth}
        height={Math.max(1, q1Y - q3Y)}
        fill={color}
        fillOpacity={0.4}
        stroke={color}
        strokeWidth={2}
        rx={2}
      />

      {/* Median line */}
      <line
        x1={centerX - boxWidth / 2}
        y1={medianY}
        x2={centerX + boxWidth / 2}
        y2={medianY}
        stroke={color}
        strokeWidth={3}
      />
    </g>
  )
}

export function BoxPlotChart({
  data,
  height = 400,
  colorScheme = 'default',
  showMean = false,
  showOutliers = true,
  xAxisLabel,
  yAxisLabel,
  className = '',
}: BoxPlotChartProps) {
  const { t } = useI18n()
  const resolvedYAxisLabel = yAxisLabel ?? t('evaluation.charts.boxPlot.score')
  const colors = COLORS[colorScheme]

  // Transform data - the bar will represent the IQR (q1 to q3)
  const chartData = useMemo(() => {
    return data.map((item, index) => ({
      ...item,
      // Bar goes from q1 (base) to q3 (top), so height = iqr
      iqr: item.q3 - item.q1,
      color: colors[index % colors.length],
      index,
    }))
  }, [data, colors])

  // Calculate y-axis domain with padding
  const yDomain = useMemo(() => {
    const allValues = data.flatMap((d) => [d.min, d.max, ...(d.outliers || [])])
    if (allValues.length === 0) return [0, 1]
    const minVal = Math.min(...allValues)
    const maxVal = Math.max(...allValues)
    const padding = (maxVal - minVal) * 0.1 || 0.1
    return [Math.max(0, minVal - padding), Math.min(1, maxVal + padding)]
  }, [data])

  return (
    <div className={className}>
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart
          data={chartData}
          margin={{ top: 20, right: 30, left: 20, bottom: 80 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />

          <XAxis
            dataKey="name"
            type="category"
            tick={{ fontSize: 11 }}
            angle={-45}
            textAnchor="end"
            height={80}
            interval={0}
          />

          <YAxis
            domain={yDomain}
            tick={{ fontSize: 12 }}
            tickFormatter={(value) => value.toFixed(2)}
            label={
              resolvedYAxisLabel
                ? {
                    value: resolvedYAxisLabel,
                    angle: -90,
                    position: 'insideLeft',
                    style: { textAnchor: 'middle', fontSize: 12 },
                  }
                : undefined
            }
          />

          <Tooltip content={<CustomTooltip t={t} />} />

          {/* Stacked bars: first transparent bar up to q1, then IQR bar */}
          <Bar
            dataKey="q1"
            stackId="box"
            fill="transparent"
            barSize={50}
            isAnimationActive={false}
          />
          <Bar
            dataKey="iqr"
            stackId="box"
            barSize={50}
            isAnimationActive={false}
            shape={<BoxPlotShape />}
          >
            {chartData.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.color} />
            ))}
          </Bar>
        </ComposedChart>
      </ResponsiveContainer>

      {/* Legend for box plot elements */}
      <div className="mt-2 flex flex-wrap justify-center gap-4 text-xs text-gray-500 dark:text-gray-400">
        <div className="flex items-center gap-1.5">
          <div className="h-px w-4 bg-gray-600" />
          <span>{t('evaluation.charts.boxPlot.whiskers')}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="h-3 w-4 rounded-sm border-2 border-emerald-500 bg-emerald-500/40" />
          <span>{t('evaluation.charts.boxPlot.iqr')}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="h-0.5 w-4 bg-emerald-500" />
          <span>{t('evaluation.charts.boxPlot.medianLabel')}</span>
        </div>
      </div>
    </div>
  )
}

/**
 * Helper function to calculate box plot statistics from raw scores
 */
export function calculateBoxPlotStats(
  scores: number[],
  name: string
): BoxPlotData | null {
  if (scores.length === 0) return null

  const sorted = [...scores].sort((a, b) => a - b)
  const n = sorted.length

  const q1Index = Math.floor(n * 0.25)
  const medianIndex = Math.floor(n * 0.5)
  const q3Index = Math.floor(n * 0.75)

  const q1 = sorted[q1Index]
  const median = sorted[medianIndex]
  const q3 = sorted[q3Index]
  const iqr = q3 - q1

  // Whiskers extend to 1.5 * IQR or min/max if closer
  const lowerWhisker = Math.max(sorted[0], q1 - 1.5 * iqr)
  const upperWhisker = Math.min(sorted[n - 1], q3 + 1.5 * iqr)

  // Find outliers
  const outliers = sorted.filter((v) => v < lowerWhisker || v > upperWhisker)

  // Calculate mean
  const mean = scores.reduce((a, b) => a + b, 0) / n

  return {
    name,
    min: lowerWhisker,
    q1,
    median,
    q3,
    max: upperWhisker,
    mean,
    outliers,
    count: n,
  }
}
