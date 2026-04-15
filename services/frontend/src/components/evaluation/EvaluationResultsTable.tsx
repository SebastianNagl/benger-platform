/**
 * Evaluation Results Table Component
 *
 * Publication-ready comparison table with:
 * - Side-by-side model comparisons
 * - Color-coded scores (green/yellow/red thresholds)
 * - Statistical significance indicators (*, **, ***)
 * - Sortable columns by any metric
 * - Clear column headers with metric names
 */

'use client'

import { useI18n } from '@/contexts/I18nContext'
import {
  ArrowDownIcon,
  ArrowUpIcon,
  ArrowsUpDownIcon,
} from '@heroicons/react/24/outline'
import { useState } from 'react'

interface MetricValue {
  value: number
  confidenceInterval?: {
    lower: number
    upper: number
  }
  significance?: number // p-value
}

interface ModelResult {
  modelId: string
  modelName?: string
  metrics: Record<string, MetricValue | number>
  rank?: number
}

interface EvaluationResultsTableProps {
  results: ModelResult[]
  metricNames?: Record<string, string> // Map metric keys to display names
  metricDescriptions?: Record<string, string>
  higherIsBetter?: Record<string, boolean>
  baselineModel?: string // Model ID to compare against for significance
  className?: string
}

type SortDirection = 'asc' | 'desc' | null
type SortConfig = {
  column: string
  direction: SortDirection
}

const getScoreColorClass = (
  value: number,
  higherIsBetter: boolean = true
): string => {
  const score = higherIsBetter ? value : 1 - value

  if (score >= 0.7) {
    return 'bg-green-100 text-green-900 dark:bg-green-900/30 dark:text-green-100'
  } else if (score >= 0.5) {
    return 'bg-yellow-100 text-yellow-900 dark:bg-yellow-900/30 dark:text-yellow-100'
  } else {
    return 'bg-red-100 text-red-900 dark:bg-red-900/30 dark:text-red-100'
  }
}

const getSignificanceIndicator = (pValue?: number): string => {
  if (!pValue) return ''
  if (pValue < 0.001) return '***'
  if (pValue < 0.01) return '**'
  if (pValue < 0.05) return '*'
  return ''
}

const getMetricValue = (metric: MetricValue | number): number => {
  return typeof metric === 'number' ? metric : metric.value
}

const formatMetricValue = (value: number): string => {
  // Format based on value range
  if (value >= 0 && value <= 1) {
    return (value * 100).toFixed(1) + '%'
  }
  return value.toFixed(3)
}

export function EvaluationResultsTable({
  results,
  metricNames = {},
  metricDescriptions = {},
  higherIsBetter = {},
  baselineModel,
  className = '',
}: EvaluationResultsTableProps) {
  const { t } = useI18n()
  const [sortConfig, setSortConfig] = useState<SortConfig>({
    column: 'modelId',
    direction: 'asc',
  })
  const [selectedMetric, setSelectedMetric] = useState<string | null>(null)

  // Extract all unique metric keys
  const metricKeys = Array.from(
    new Set(results.flatMap((result) => Object.keys(result.metrics || {})))
  ).sort()

  // Sort results based on current sort config
  const sortedResults = [...results].sort((a, b) => {
    if (sortConfig.direction === null) return 0

    let aValue: any
    let bValue: any

    if (sortConfig.column === 'modelId') {
      aValue = a.modelId
      bValue = b.modelId
    } else if (sortConfig.column === 'rank') {
      aValue = a.rank ?? Infinity
      bValue = b.rank ?? Infinity
    } else {
      // Metric column
      aValue = getMetricValue(a.metrics[sortConfig.column] ?? 0)
      bValue = getMetricValue(b.metrics[sortConfig.column] ?? 0)
    }

    const direction = sortConfig.direction === 'asc' ? 1 : -1

    if (typeof aValue === 'string') {
      return aValue.localeCompare(bValue) * direction
    }
    return (aValue - bValue) * direction
  })

  const handleSort = (column: string) => {
    setSortConfig((current) => {
      if (current.column !== column) {
        return { column, direction: 'desc' }
      }

      if (current.direction === 'desc') {
        return { column, direction: 'asc' }
      } else if (current.direction === 'asc') {
        return { column, direction: null }
      } else {
        return { column, direction: 'desc' }
      }
    })
  }

  const getSortIcon = (column: string) => {
    if (sortConfig.column !== column || sortConfig.direction === null) {
      return <ArrowsUpDownIcon className="h-4 w-4 text-gray-400" />
    }
    return sortConfig.direction === 'asc' ? (
      <ArrowUpIcon className="h-4 w-4 text-blue-600" />
    ) : (
      <ArrowDownIcon className="h-4 w-4 text-blue-600" />
    )
  }

  if (results.length === 0) {
    return (
      <div className="rounded-lg border border-gray-200 bg-white p-8 text-center dark:border-gray-700 dark:bg-gray-800">
        <p className="text-gray-500 dark:text-gray-400">
          {t('evaluation.resultsTable.noResults')}
        </p>
      </div>
    )
  }

  return (
    <div className={`space-y-4 ${className}`}>
      {/* Legend */}
      <div className="flex items-center gap-4 rounded-lg bg-gray-50 p-3 text-xs dark:bg-gray-800">
        <div className="flex items-center gap-1">
          <div className="h-3 w-3 rounded bg-green-500" />
          <span className="text-gray-600 dark:text-gray-400">{t('evaluation.resultsTable.scoreHigh')}</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="h-3 w-3 rounded bg-yellow-500" />
          <span className="text-gray-600 dark:text-gray-400">
            {t('evaluation.resultsTable.scoreMedium')}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <div className="h-3 w-3 rounded bg-red-500" />
          <span className="text-gray-600 dark:text-gray-400">
            {t('evaluation.resultsTable.scoreLow')}
          </span>
        </div>
        {baselineModel && (
          <div className="ml-auto text-gray-600 dark:text-gray-400">
            {t('evaluation.resultsTable.significanceLegend')}
          </div>
        )}
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              {/* Rank Column */}
              <th
                className="cursor-pointer px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-700 transition-colors hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700"
                onClick={() => handleSort('rank')}
              >
                <div className="flex items-center gap-1">
                  {t('evaluation.resultsTable.rank')}
                  {getSortIcon('rank')}
                </div>
              </th>

              {/* Model Column */}
              <th
                className="cursor-pointer px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-700 transition-colors hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700"
                onClick={() => handleSort('modelId')}
              >
                <div className="flex items-center gap-1">
                  {t('evaluation.resultsTable.model')}
                  {getSortIcon('modelId')}
                </div>
              </th>

              {/* Metric Columns */}
              {metricKeys.map((metricKey) => (
                <th
                  key={metricKey}
                  className="cursor-pointer px-4 py-3 text-center text-xs font-semibold uppercase tracking-wider text-gray-700 transition-colors hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700"
                  onClick={() => handleSort(metricKey)}
                  title={metricDescriptions[metricKey] || metricKey}
                >
                  <div className="flex items-center justify-center gap-1">
                    {metricNames[metricKey] || metricKey}
                    {getSortIcon(metricKey)}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200 bg-white dark:divide-gray-700 dark:bg-gray-900">
            {sortedResults.map((result, idx) => {
              const isBaseline = result.modelId === baselineModel

              return (
                <tr
                  key={result.modelId}
                  className={`transition-colors hover:bg-gray-50 dark:hover:bg-gray-800 ${
                    isBaseline ? 'bg-blue-50 dark:bg-blue-900/20' : ''
                  }`}
                >
                  {/* Rank */}
                  <td className="whitespace-nowrap px-4 py-3 text-sm font-medium text-gray-900 dark:text-gray-100">
                    {result.rank !== undefined ? (
                      <span
                        className={`inline-flex items-center justify-center rounded-full px-2 py-1 ${
                          result.rank === 1
                            ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-200'
                            : result.rank === 2
                              ? 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200'
                              : result.rank === 3
                                ? 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-200'
                                : 'bg-gray-50 text-gray-600 dark:bg-gray-800 dark:text-gray-400'
                        }`}
                      >
                        #{result.rank}
                      </span>
                    ) : (
                      <span className="text-gray-400">-</span>
                    )}
                  </td>

                  {/* Model Name */}
                  <td className="whitespace-nowrap px-4 py-3 text-sm font-medium text-gray-900 dark:text-gray-100">
                    <div>
                      {result.modelName || result.modelId}
                      {isBaseline && (
                        <span className="ml-2 inline-flex items-center rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-800 dark:bg-blue-900/30 dark:text-blue-200">
                          {t('evaluation.resultsTable.baseline')}
                        </span>
                      )}
                    </div>
                  </td>

                  {/* Metric Values */}
                  {metricKeys.map((metricKey) => {
                    const metric = (result.metrics || {})[metricKey]
                    const value = getMetricValue(metric ?? 0)
                    const metricHigherIsBetter =
                      higherIsBetter[metricKey] ?? true
                    const colorClass = getScoreColorClass(
                      value,
                      metricHigherIsBetter
                    )

                    const significance =
                      typeof metric === 'object' && metric.significance
                        ? getSignificanceIndicator(metric.significance)
                        : ''

                    const hasCI =
                      typeof metric === 'object' && metric.confidenceInterval

                    return (
                      <td
                        key={metricKey}
                        className="whitespace-nowrap px-4 py-3 text-center text-sm"
                      >
                        {metric !== undefined ? (
                          <div className="inline-flex flex-col items-center">
                            <span
                              className={`rounded-md px-2 py-1 font-mono font-semibold ${colorClass}`}
                            >
                              {formatMetricValue(value)}
                              {significance && (
                                <sup className="ml-0.5 font-bold">
                                  {significance}
                                </sup>
                              )}
                            </span>
                            {hasCI && (
                              <span className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                                [
                                {formatMetricValue(
                                  (metric as MetricValue).confidenceInterval!
                                    .lower
                                )}
                                ,{' '}
                                {formatMetricValue(
                                  (metric as MetricValue).confidenceInterval!
                                    .upper
                                )}
                                ]
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="text-gray-400">-</span>
                        )}
                      </td>
                    )
                  })}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Footer Notes */}
      {baselineModel && (
        <div className="rounded-lg bg-blue-50 p-3 text-xs text-blue-800 dark:bg-blue-900/20 dark:text-blue-200">
          <p>
            {t('evaluation.resultsTable.baselineNote', { model: baselineModel })}
          </p>
        </div>
      )}
    </div>
  )
}
