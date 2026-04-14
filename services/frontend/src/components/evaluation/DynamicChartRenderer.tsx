/**
 * Dynamic Chart Renderer Component
 *
 * Renders the appropriate chart type based on user selection.
 * Supports smooth transitions between chart types.
 */

'use client'

import { LoadingSpinner } from '@/components/shared/LoadingSpinner'
import { useI18n } from '@/contexts/I18nContext'
import { useEffect, useRef, useState } from 'react'
import type { ChartType } from './ChartTypeSelector'
import { EvaluationResultsTable } from './EvaluationResultsTable'
import { ModelComparisonChart } from './ModelComparisonChart'
import {
  BoxPlotChart,
  calculateBoxPlotStats,
  type BoxPlotData,
} from './charts/BoxPlotChart'
import { SignificanceHeatmap } from './charts/SignificanceHeatmap'

interface ModelData {
  model_id: string
  model_name?: string
  metrics: Record<string, number>
  scores?: number[] // Raw scores for box plot
}

interface SignificanceComparison {
  model_a: string
  model_b: string
  p_value: number
  significant: boolean
  effect_size: number
  stars: string
}

interface DynamicChartRendererProps {
  chartType: ChartType
  models: ModelData[]
  metrics: string[]
  significanceData?: SignificanceComparison[]
  height?: number
  showErrorBars?: boolean
  colorScheme?: 'default' | 'accessible'
  isLoading?: boolean
  emptyMessage?: string
  className?: string
}

export function DynamicChartRenderer({
  chartType,
  models,
  metrics,
  significanceData = [],
  height = 400,
  showErrorBars = true,
  colorScheme = 'default',
  isLoading = false,
  emptyMessage,
  className = '',
}: DynamicChartRendererProps) {
  const { t } = useI18n()
  const resolvedEmptyMessage = emptyMessage || t('evaluation.charts.noData')
  const [displayedChartType, setDisplayedChartType] = useState(chartType)
  const prevChartTypeRef = useRef(chartType)

  // Track transition state - derived from comparison
  const isTransitioning = chartType !== displayedChartType

  // Handle chart type change with transition
  useEffect(() => {
    if (chartType !== prevChartTypeRef.current) {
      prevChartTypeRef.current = chartType
      const timer = setTimeout(() => {
        setDisplayedChartType(chartType)
      }, 150) // Short fade transition
      return () => clearTimeout(timer)
    }
  }, [chartType])

  // Generate box plot data from model scores - ONLY uses real distribution data
  // No synthetic data generation to maintain scientific integrity
  const boxPlotData: BoxPlotData[] = metrics.flatMap((metric) =>
    models
      .map((model) => {
        // Only generate box plot if raw scores are available
        if (model.scores && model.scores.length > 0) {
          return calculateBoxPlotStats(
            model.scores,
            `${model.model_name || model.model_id} - ${metric}`
          )
        }
        // Return null if no distribution data - do not generate synthetic data
        return null
      })
      .filter((d): d is BoxPlotData => d !== null)
  )

  // Track if box plot data is available
  const hasDistributionData = boxPlotData.length > 0

  // Generate table data
  const tableData = models.map((model, idx) => ({
    modelId: model.model_id,
    modelName: model.model_name,
    metrics: model.metrics,
    rank: idx + 1,
  }))

  // Check if we have enough data for certain chart types
  const hasMultipleModels = models.length > 1
  const hasData = models.length > 0 && metrics.length > 0

  if (isLoading) {
    return (
      <div
        className={`flex items-center justify-center ${className}`}
        style={{ height }}
      >
        <LoadingSpinner />
      </div>
    )
  }

  if (!hasData) {
    return (
      <div
        className={`flex items-center justify-center text-gray-500 dark:text-gray-400 ${className}`}
        style={{ height }}
      >
        {resolvedEmptyMessage}
      </div>
    )
  }

  const containerClasses = `transition-opacity duration-150 ${isTransitioning ? 'opacity-0' : 'opacity-100'} ${className}`

  const renderChart = () => {
    switch (displayedChartType) {
      case 'bar':
        return (
          <ModelComparisonChart
            models={models.map((m) => ({
              model_id: m.model_id,
              metrics: m.metrics,
            }))}
            metrics={metrics}
            visualizationType="bar"
            height={height}
            showErrorBars={showErrorBars}
          />
        )

      case 'radar':
        return (
          <ModelComparisonChart
            models={models.map((m) => ({
              model_id: m.model_id,
              metrics: m.metrics,
            }))}
            metrics={metrics}
            visualizationType="radar"
            height={height}
          />
        )

      case 'box':
        if (boxPlotData.length === 0) {
          return (
            <div
              className="flex items-center justify-center text-gray-500 dark:text-gray-400"
              style={{ height }}
            >
              {t('evaluation.charts.noDistributionData')}
            </div>
          )
        }
        return (
          <BoxPlotChart
            data={boxPlotData}
            height={height}
            colorScheme={colorScheme}
            showMean={true}
          />
        )

      case 'heatmap':
        if (!hasMultipleModels) {
          return (
            <div
              className="flex items-center justify-center text-gray-500 dark:text-gray-400"
              style={{ height }}
            >
              {t('evaluation.charts.heatmapRequiresMultipleModels')}
            </div>
          )
        }
        // If we have significance data, show significance heatmap
        if (significanceData.length > 0) {
          return (
            <SignificanceHeatmap
              modelIds={models.map((m) => m.model_id)}
              metric={metrics[0] || 'Score'}
              significanceData={significanceData}
              height={height}
            />
          )
        }
        // Otherwise, show a simple score heatmap
        return (
          <ScoreHeatmap
            models={models}
            metrics={metrics}
            height={height}
            colorScheme={colorScheme}
          />
        )

      case 'table':
        return (
          <div style={{ maxHeight: height, overflow: 'auto' }}>
            <EvaluationResultsTable results={tableData} />
          </div>
        )

      default:
        return (
          <div
            className="flex items-center justify-center text-gray-500 dark:text-gray-400"
            style={{ height }}
          >
            {t('evaluation.charts.unknownChartType', { type: displayedChartType })}
          </div>
        )
    }
  }

  return <div className={containerClasses}>{renderChart()}</div>
}

/**
 * Simple Score Heatmap Component
 * Shows model × metric matrix with color-coded scores
 */
interface ScoreHeatmapProps {
  models: ModelData[]
  metrics: string[]
  height?: number
  colorScheme?: 'default' | 'accessible'
}

function ScoreHeatmap({
  models,
  metrics,
  height = 400,
  colorScheme = 'default',
}: ScoreHeatmapProps) {
  const { t } = useI18n()
  // Get color for score value
  const getScoreColor = (value: number) => {
    if (colorScheme === 'accessible') {
      // Blue-white-red diverging scale
      if (value >= 0.7) return 'bg-blue-500 text-white'
      if (value >= 0.5) return 'bg-blue-200 text-gray-900'
      if (value >= 0.3) return 'bg-red-200 text-gray-900'
      return 'bg-red-500 text-white'
    }
    // Default green-yellow-red
    if (value >= 0.7) return 'bg-green-500 text-white'
    if (value >= 0.5) return 'bg-yellow-400 text-gray-900'
    if (value >= 0.3) return 'bg-orange-400 text-white'
    return 'bg-red-500 text-white'
  }

  return (
    <div style={{ maxHeight: height, overflow: 'auto' }}>
      <table className="min-w-full text-sm">
        <thead>
          <tr>
            <th className="sticky left-0 top-0 z-20 bg-white px-3 py-2 text-left font-medium text-gray-700 dark:bg-gray-900 dark:text-gray-300">
              {t('evaluation.charts.model')}
            </th>
            {metrics.map((metric) => (
              <th
                key={metric}
                className="sticky top-0 z-10 whitespace-nowrap bg-white px-3 py-2 text-center font-medium text-gray-700 dark:bg-gray-900 dark:text-gray-300"
              >
                {metric.replace(/_/g, ' ')}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {models.map((model) => (
            <tr key={model.model_id}>
              <td className="sticky left-0 z-10 whitespace-nowrap bg-white px-3 py-2 font-medium text-gray-900 dark:bg-gray-900 dark:text-gray-100">
                {model.model_name || model.model_id}
              </td>
              {metrics.map((metric) => {
                const value = model.metrics[metric]
                return (
                  <td
                    key={metric}
                    className={`px-3 py-2 text-center font-mono ${
                      value !== undefined
                        ? getScoreColor(value)
                        : 'bg-gray-100 text-gray-400 dark:bg-gray-800'
                    }`}
                  >
                    {value !== undefined ? value.toFixed(3) : '—'}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/**
 * Helper to determine best default chart type based on data
 */
export function getSmartChartDefault(
  models: ModelData[],
  metrics: string[],
  hasSignificanceData: boolean
): ChartType {
  const modelCount = models.length
  const metricCount = metrics.length

  // Single model: table is most useful
  if (modelCount === 1) {
    return 'table'
  }

  // Many metrics, few models: radar is best
  if (metricCount >= 3 && modelCount <= 5) {
    return 'radar'
  }

  // Many models with significance data: heatmap
  if (modelCount > 3 && hasSignificanceData) {
    return 'heatmap'
  }

  // Default: bar chart
  return 'bar'
}
