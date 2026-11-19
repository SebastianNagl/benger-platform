'use client'

/**
 * Views of interval rows (`@/lib/results/intervalRows`): a forest plot or a
 * bar chart per series, and a series x label table. Metric statistics and
 * analysis estimates both arrive here as interval rows, so one renderer
 * serves both result types. The views draw the given numbers and compute
 * nothing.
 */

import {
  ForestPlot,
  type ForestPlotRow,
} from '@/components/analysis/ForestPlot'
import { useI18n } from '@/contexts/I18nContext'
import {
  formatInterval,
  formatLevel,
  formatNumber,
  formatP,
  MISSING,
} from '@/lib/analysis/results'
import {
  commonReference,
  groupBySeries,
  labelsOf,
  type IntervalRow,
} from '@/lib/results/intervalRows'

function toForestRows(rows: readonly IntervalRow[]): ForestPlotRow[] {
  return rows.map((row) => ({
    id: row.id,
    label: row.label,
    estimate: row.estimate,
    lower: row.lower,
    upper: row.upper,
    emphasis: row.emphasis,
    note:
      row.estimate === null
        ? typeof row.meta.message === 'string' && row.meta.message
          ? row.meta.message
          : null
        : null,
  }))
}

/** The confidence level the rows share, or null when they differ. */
function commonLevel(rows: readonly IntervalRow[]): number | null {
  let level: number | null = null
  for (const row of rows) {
    if (row.level === null) continue
    if (level === null) level = row.level
    else if (level !== row.level) return null
  }
  return level
}

export interface IntervalForestChartProps {
  rows: readonly IntervalRow[]
  /** `point` (forest plot) or `bar` (bars from the reference value). */
  mode?: 'point' | 'bar'
  /** Shown when there are no rows. */
  emptyMessage?: string
}

/** One forest plot (or bar chart) per series, series in row order. */
export function IntervalForestChart({
  rows,
  mode = 'point',
  emptyMessage,
}: IntervalForestChartProps) {
  const { t, locale } = useI18n()
  const groups = groupBySeries(rows)
  if (groups.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-zinc-500 dark:text-zinc-400">
        {emptyMessage ?? t('evaluation.charts.noData')}
      </p>
    )
  }
  return (
    <div className="space-y-6" data-testid="interval-forest-chart">
      {groups.map((group) => {
        const level = commonLevel(group.rows)
        const reference = commonReference(group.rows)
        return (
          <figure key={group.series} className="min-w-0">
            <figcaption className="mb-2 text-sm font-medium [overflow-wrap:anywhere] text-zinc-800 dark:text-zinc-200">
              {group.series}
            </figcaption>
            <ForestPlot
              rows={toForestRows(group.rows)}
              nullValue={reference}
              mode={mode}
              ariaLabel={t('evaluation.charts.intervalAriaLabel', {
                series: group.series,
              })}
              legend={
                level !== null
                  ? {
                      interval: t('evaluation.charts.intervalLegend', {
                        level: formatLevel(level, locale),
                      }),
                    }
                  : undefined
              }
              data-testid={mode === 'bar' ? 'interval-bar-plot' : 'forest-plot'}
            />
          </figure>
        )
      })}
    </div>
  )
}

export interface IntervalTableProps {
  rows: readonly IntervalRow[]
  /** Header of the first column (what a series is, e.g. "Contrast"). */
  seriesHeader: string
  emptyMessage?: string
}

/**
 * Series as rows, labels as columns (e.g. contrasts by system): each cell
 * holds the estimate with its interval, and the adjusted p-value when the
 * row has one.
 */
export function IntervalTable({
  rows,
  seriesHeader,
  emptyMessage,
}: IntervalTableProps) {
  const { t, locale } = useI18n()
  const groups = groupBySeries(rows)
  const labels = labelsOf(rows)
  if (groups.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-zinc-500 dark:text-zinc-400">
        {emptyMessage ?? t('evaluation.charts.noData')}
      </p>
    )
  }
  const th =
    'px-3 py-2 text-left text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400'
  return (
    <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
      <table
        className="min-w-full divide-y divide-zinc-200 text-sm dark:divide-zinc-800"
        data-testid="interval-table"
      >
        <thead className="bg-zinc-50 dark:bg-zinc-900/40">
          <tr>
            <th className={th}>{seriesHeader}</th>
            {labels.map((label) => (
              <th key={label} className={`${th} text-right normal-case`}>
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100 bg-white text-zinc-900 dark:divide-zinc-800 dark:bg-zinc-950 dark:text-zinc-100">
          {groups.map((group) => (
            <tr key={group.series} className="align-top">
              <td className="max-w-[16rem] px-3 py-2 font-medium [overflow-wrap:anywhere]">
                {group.series}
              </td>
              {labels.map((label) => {
                const row = group.rows.find((r) => r.label === label)
                if (!row) {
                  return (
                    <td
                      key={label}
                      className="px-3 py-2 text-right text-zinc-400"
                    >
                      {MISSING}
                    </td>
                  )
                }
                return (
                  <td
                    key={label}
                    className="px-3 py-2 text-right font-mono text-xs whitespace-nowrap"
                    data-testid="interval-table-cell"
                  >
                    <div className="text-zinc-900 dark:text-zinc-100">
                      {formatNumber(row.estimate, locale)}
                    </div>
                    <div className="text-zinc-500 dark:text-zinc-400">
                      {formatInterval(row.lower, row.upper, locale)}
                    </div>
                    {row.p_adjusted !== null && (
                      <div className="text-zinc-500 dark:text-zinc-400">
                        {t('evaluation.charts.pAdjustedShort', {
                          p: formatP(row.p_adjusted, locale),
                        })}
                      </div>
                    )}
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
