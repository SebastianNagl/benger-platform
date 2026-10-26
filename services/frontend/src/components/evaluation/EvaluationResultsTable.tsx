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
import { formatDecimal } from '@/lib/i18n/locales'
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
  higherIsBetter: boolean = true,
): string => {
  const score = higherIsBetter ? value : 1 - value

  if (score >= 0.7) {
    return 'bg-emerald-100 text-emerald-900 dark:bg-emerald-900/30 dark:text-emerald-100'
  } else if (score >= 0.5) {
    return 'bg-amber-100 text-amber-900 dark:bg-amber-900/30 dark:text-amber-100'
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

const formatMetricValue = (value: number, locale: string): string => {
  // Format based on value range
  if (value >= 0 && value <= 1) {
    return formatDecimal(value * 100, locale, 1) + '%'
  }
  return formatDecimal(value, locale, 3)
}

export function EvaluationResultsTable({
  results,
  metricNames = {},
  metricDescriptions = {},
  higherIsBetter = {},
  baselineModel,
  className = '',
}: EvaluationResultsTableProps) {
  const { t, locale } = useI18n()
  const [sortConfig, setSortConfig] = useState<SortConfig>({
    column: 'modelId',
    direction: 'asc',
  })
  const [selectedMetric, setSelectedMetric] = useState<string | null>(null)

  // Extract all unique metric keys
  const metricKeys = Array.from(
    new Set(results.flatMap((result) => Object.keys(result.metrics || {}))),
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
      return <ArrowsUpDownIcon className="h-4 w-4 text-zinc-400" />
    }
    return sortConfig.direction === 'asc' ? (
      <ArrowUpIcon className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
    ) : (
      <ArrowDownIcon className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
    )
  }

  if (results.length === 0) {
    return (
      <div className="rounded-lg border border-zinc-200 bg-white p-8 text-center dark:border-zinc-700 dark:bg-zinc-800">
        <p className="text-zinc-500 dark:text-zinc-400">
          {t('evaluation.resultsTable.noResults')}
        </p>
      </div>
    )
  }

  return (
    <div className={`space-y-4 ${className}`}>
      {/* Legend */}
      <div className="flex items-center gap-4 rounded-lg bg-zinc-50 p-3 text-xs dark:bg-zinc-800">
        <div className="flex items-center gap-1">
          <div className="h-3 w-3 rounded bg-emerald-500" />
          <span className="text-zinc-600 dark:text-zinc-400">
            {t('evaluation.resultsTable.scoreHigh')}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <div className="h-3 w-3 rounded bg-amber-500" />
          <span className="text-zinc-600 dark:text-zinc-400">
            {t('evaluation.resultsTable.scoreMedium')}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <div className="h-3 w-3 rounded bg-red-500" />
          <span className="text-zinc-600 dark:text-zinc-400">
            {t('evaluation.resultsTable.scoreLow')}
          </span>
        </div>
        {baselineModel && (
          <div className="ml-auto text-zinc-600 dark:text-zinc-400">
            {t('evaluation.resultsTable.significanceLegend')}
          </div>
        )}
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-700">
        <table className="min-w-full divide-y divide-zinc-200 dark:divide-zinc-700">
          <thead className="bg-zinc-50 dark:bg-zinc-800">
            <tr>
              {/* Rank Column */}
              <th
                className="cursor-pointer px-4 py-3 text-left text-xs font-semibold tracking-wider text-zinc-700 uppercase transition-colors hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-700"
                onClick={() => handleSort('rank')}
              >
                <div className="flex items-center gap-1">
                  {t('evaluation.resultsTable.rank')}
                  {getSortIcon('rank')}
                </div>
              </th>

              {/* Model Column */}
              <th
                className="cursor-pointer px-4 py-3 text-left text-xs font-semibold tracking-wider text-zinc-700 uppercase transition-colors hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-700"
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
                  className="cursor-pointer px-4 py-3 text-center text-xs font-semibold tracking-wider text-zinc-700 uppercase transition-colors hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-700"
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
          <tbody className="divide-y divide-zinc-200 bg-white dark:divide-zinc-700 dark:bg-zinc-900">
            {sortedResults.map((result, idx) => {
              const isBaseline = result.modelId === baselineModel

              return (
                <tr
                  key={result.modelId}
                  className={`transition-colors hover:bg-zinc-50 dark:hover:bg-zinc-800 ${
                    isBaseline ? 'bg-zinc-50 dark:bg-zinc-800/50' : ''
                  }`}
                >
                  {/* Rank */}
                  <td className="px-4 py-3 text-sm font-medium whitespace-nowrap text-zinc-900 dark:text-zinc-100">
                    {result.rank !== undefined ? (
                      <span
                        className={`inline-flex items-center justify-center rounded-full px-2 py-1 ${
                          result.rank === 1
                            ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-200'
                            : result.rank === 2
                              ? 'bg-zinc-100 text-zinc-800 dark:bg-zinc-700 dark:text-zinc-200'
                              : result.rank === 3
                                ? 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-200'
                                : 'bg-zinc-50 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400'
                        }`}
                      >
                        #{result.rank}
                      </span>
                    ) : (
                      <span className="text-zinc-400">-</span>
                    )}
                  </td>

                  {/* Model Name */}
                  <td className="px-4 py-3 text-sm font-medium whitespace-nowrap text-zinc-900 dark:text-zinc-100">
                    <div>
                      {result.modelName || result.modelId}
                      {isBaseline && (
                        <span className="ml-2 inline-flex items-center rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-800 dark:bg-zinc-800 dark:text-zinc-300">
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
                      metricHigherIsBetter,
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
                        className="px-4 py-3 text-center text-sm whitespace-nowrap"
                      >
                        {metric !== undefined ? (
                          <div className="inline-flex flex-col items-center">
                            <span
                              className={`rounded-md px-2 py-1 font-mono font-semibold ${colorClass}`}
                            >
                              {formatMetricValue(value, locale)}
                              {significance && (
                                <sup className="ml-0.5 font-bold">
                                  {significance}
                                </sup>
                              )}
                            </span>
                            {hasCI && (
                              <span className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                                [
                                {formatMetricValue(
                                  (metric as MetricValue).confidenceInterval!
                                    .lower,
                                  locale,
                                )}
                                ,{' '}
                                {formatMetricValue(
                                  (metric as MetricValue).confidenceInterval!
                                    .upper,
                                  locale,
                                )}
                                ]
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="text-zinc-400">-</span>
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
        <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-3 text-xs text-zinc-700 dark:border-zinc-700 dark:bg-zinc-800/50 dark:text-zinc-300">
          <p>
            {t('evaluation.resultsTable.baselineNote', {
              model: baselineModel,
            })}
          </p>
        </div>
      )}
    </div>
  )
}
