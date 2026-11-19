/**
 * One shape for every interval result the evaluations page draws.
 *
 * Metric statistics (mean and confidence interval per model and metric) and
 * analysis estimates (estimate and confidence interval per contrast and
 * scope) both map into interval rows, and the forest, bar and table views
 * draw interval rows whatever produced them. Nothing here computes
 * statistics: every number is copied from the API response.
 */

import { inFamily, scopeDescription } from '@/lib/analysis/results'
import type { AnalysisEstimate } from '@/lib/api/analysis'

/** One estimate with its interval, whatever produced it. */
export interface IntervalRow {
  /** Unique within one set of rows. */
  id: string
  /** What the row belongs to (a metric, a contrast). */
  series: string
  /** What the row is about (a model, a scope). */
  label: string
  estimate: number | null
  lower: number | null
  upper: number | null
  /** Confidence level of the interval, e.g. 0.95. */
  level: number | null
  n: number | null
  p: number | null
  p_adjusted: number | null
  family: string | null
  /** `ok`, or the reason the row has no usable estimate. */
  status: string
  /** Drawn emphasised (e.g. a pooled estimate). */
  emphasis: boolean
  /** Source-specific facts (model id, estimand id, scope values, ...). */
  meta: Record<string, unknown>
}

const finite = (v: unknown): number | null =>
  typeof v === 'number' && Number.isFinite(v) ? v : null

/** Level of the metric statistics' confidence intervals (t interval). */
export const METRIC_CI_LEVEL = 0.95

/** The statistics response fields the metric adapter reads. */
export interface MetricStatisticsLike {
  by_model?: Record<
    string,
    {
      model_id?: string
      model_name?: string
      metrics?: Record<
        string,
        {
          mean?: number | null
          ci_lower?: number | null
          ci_upper?: number | null
          n?: number | null
        }
      >
    }
  > | null
}

export interface MetricRowOptions {
  /** Restrict and order the series (metric names); default: all, as given. */
  metrics?: readonly string[]
  /** Display label of a metric (default: the metric name). */
  metricLabel?: (metric: string) => string
  /** Display label of a model (default: model_name, else the id). */
  modelLabel?: (modelId: string, modelName?: string) => string
}

/**
 * Interval rows from the statistics response of the evaluations page: one
 * row per model and metric with the mean and its 95 % confidence interval,
 * grouped by metric (the series), models in response order.
 */
export function intervalRowsFromStatistics(
  data: MetricStatisticsLike | null | undefined,
  options: MetricRowOptions = {},
): IntervalRow[] {
  const byModel = data?.by_model
  if (!byModel) return []
  const models = Object.entries(byModel)
  const metricOrder: string[] = []
  if (options.metrics) {
    metricOrder.push(...options.metrics)
  } else {
    for (const [, stats] of models) {
      for (const metric of Object.keys(stats?.metrics ?? {})) {
        if (!metricOrder.includes(metric)) metricOrder.push(metric)
      }
    }
  }
  const rows: IntervalRow[] = []
  for (const metric of metricOrder) {
    const series = options.metricLabel?.(metric) ?? metric
    for (const [modelId, stats] of models) {
      const value = stats?.metrics?.[metric]
      if (!value) continue
      const estimate = finite(value.mean)
      rows.push({
        id: `${metric}\u0000${modelId}`,
        series,
        label:
          options.modelLabel?.(modelId, stats.model_name) ??
          (stats.model_name || modelId),
        estimate,
        lower: finite(value.ci_lower),
        upper: finite(value.ci_upper),
        level: METRIC_CI_LEVEL,
        n: finite(value.n),
        p: null,
        p_adjusted: null,
        family: null,
        status: estimate === null ? 'missing' : 'ok',
        emphasis: false,
        meta: { metric, modelId },
      })
    }
  }
  return rows
}

/** Label of one contrast of one estimand, e.g. "effect · b - a". */
export function contrastLabel(
  estimate: Pick<AnalysisEstimate, 'estimand_id' | 'contrast_id'>,
): string {
  return estimate.contrast_id && estimate.contrast_id !== estimate.estimand_id
    ? `${estimate.estimand_id} · ${estimate.contrast_id}`
    : estimate.estimand_id
}

/** Whether an estimate is a joint (Wald) test rather than one contrast. */
export const isJointTest = (e: Pick<AnalysisEstimate, 'kind'>) =>
  e.kind === 'wald'

export interface EstimateRowOptions {
  /** Label of the pooled scope (translated by the caller). */
  pooledLabel: string
}

/**
 * Interval rows from the estimates of an analysis run: one row per estimate
 * of a contrast in engine order, the contrast as the series and the scope as
 * the label (the pooled fit emphasised). Joint tests have no interval and
 * are left out.
 */
export function intervalRowsFromEstimates(
  estimates: readonly AnalysisEstimate[],
  options: EstimateRowOptions,
): IntervalRow[] {
  return [...estimates]
    .filter((e) => !isJointTest(e))
    .sort((a, b) => a.position - b.position)
    .map((e) => {
      const scope = scopeDescription(e)
      return {
        id: String(e.position),
        series: contrastLabel(e),
        label: scope ?? options.pooledLabel,
        estimate: finite(e.estimate),
        lower: finite(e.ci_lower),
        upper: finite(e.ci_upper),
        level: finite(e.ci_level),
        n: finite(e.n_obs),
        p: finite(e.p_value),
        p_adjusted: finite(e.p_adjusted),
        family: e.family,
        status: e.status,
        emphasis: scope === null,
        meta: {
          estimandId: e.estimand_id,
          contrastId: e.contrast_id,
          scope: e.scope,
          scopeValues: e.scope_values,
          nullValue: finite(e.null_value),
          outcome: e.outcome,
          message: e.message,
          position: e.position,
        },
      }
    })
}

/** Rows grouped by series, series in first-seen order. */
export function groupBySeries(
  rows: readonly IntervalRow[],
): { series: string; rows: IntervalRow[] }[] {
  const groups = new Map<string, IntervalRow[]>()
  for (const row of rows) {
    const list = groups.get(row.series)
    if (list) list.push(row)
    else groups.set(row.series, [row])
  }
  return [...groups.entries()].map(([series, list]) => ({
    series,
    rows: list,
  }))
}

/** Distinct labels in first-seen order (the columns of a series x label table). */
export function labelsOf(rows: readonly IntervalRow[]): string[] {
  const labels: string[] = []
  for (const row of rows) {
    if (!labels.includes(row.label)) labels.push(row.label)
  }
  return labels
}

/**
 * The common reference value of a set of rows (an analysis contrast's null
 * value), or null when the rows disagree or carry none.
 */
export function commonReference(rows: readonly IntervalRow[]): number | null {
  let value: number | null = null
  for (const row of rows) {
    const v = finite(row.meta.nullValue)
    if (v === null) continue
    if (value === null) value = v
    else if (value !== v) return null
  }
  return value
}

// ---------------------------------------------------------------------------
// Filters of the analysis view
// ---------------------------------------------------------------------------

/** Scope column the Systems filter reads. */
export const SYSTEM_COLUMN = 'system'

/** The system an estimate is scoped to, or null (pooled, other scopes). */
export function systemOf(
  estimate: Pick<AnalysisEstimate, 'scope_values'>,
): string | null {
  const value = estimate.scope_values?.[SYSTEM_COLUMN]
  return value === undefined || value === null ? null : String(value)
}

/** Distinct systems the estimates are scoped to, sorted. */
export function systemsOf(estimates: readonly AnalysisEstimate[]): string[] {
  const ids = new Set<string>()
  for (const e of estimates) {
    const system = systemOf(e)
    if (system !== null) ids.add(system)
  }
  return [...ids].sort()
}

/** Distinct estimand ids in engine order. */
export function estimandsOf(estimates: readonly AnalysisEstimate[]): string[] {
  const ids: string[] = []
  for (const e of [...estimates].sort((a, b) => a.position - b.position)) {
    if (!ids.includes(e.estimand_id)) ids.push(e.estimand_id)
  }
  return ids
}

export interface EstimateFilter {
  /** Systems to keep (null: all). Estimates without a system always stay. */
  systems: readonly string[] | null
  /** Estimand ids to keep (null: all). */
  estimands: readonly string[] | null
  /** A family the estimates must belong to (null: any). */
  family: string | null
}

/** The estimates the filter keeps, in their given order. */
export function filterEstimates(
  estimates: readonly AnalysisEstimate[],
  filter: EstimateFilter,
): AnalysisEstimate[] {
  return estimates.filter((e) => {
    if (filter.estimands && !filter.estimands.includes(e.estimand_id))
      return false
    if (filter.family && !inFamily(e, filter.family)) return false
    if (filter.systems) {
      const system = systemOf(e)
      if (system !== null && !filter.systems.includes(system)) return false
    }
    return true
  })
}
