/**
 * Profiles of analysis estimates: the estimates of one contrast drawn over
 * an ordered or numeric scope column (the x axis), one line per value of a
 * series column and one panel per value of a facet column. This covers a
 * mean per position of a per-slot frame, a response over a numeric factor
 * and a rate per level. Every point is a stored estimate with its stored
 * interval; nothing is re-estimated.
 */

import type { AnalysisEstimate, AnalysisRun } from '@/lib/api/analysis'
import { levelText, systemLabels } from './labels'

export interface ProfilePoint {
  /** Position on the x axis: the value, or the index of an ordinal level. */
  x: number
  estimate: number
  lower: number | null
  upper: number | null
  n: number | null
}

export interface ProfileLine {
  /** The series value (empty for a single line). */
  key: string
  /** Short direct label at the line end; `title` names the line in full. */
  label: string
  title: string
  points: ProfilePoint[]
}

/** A shaded band per x, e.g. the range an ideal answer may take. */
export interface ProfileBandPoint {
  x: number
  low: number
  high: number
}

export interface ProfilePanel {
  /** The facet values of the panel (empty for a single panel). */
  key: string
  title: string | null
  lines: ProfileLine[]
  band?: ProfileBandPoint[]
}

export interface ProfileData {
  panels: ProfilePanel[]
  /** Tick labels of an ordinal x axis (`x` is the level's index). */
  xLevels: string[] | null
  /** Means of every point, the anchor of a slope line. */
  xMean: number
  yMean: number
}

/** A straight line of the given slope through the points' means. */
export interface ProfileSlope {
  slope: number
  label: string
}

export interface ProfileColumns {
  x: string
  series: string | null
  facet: string | null
}

const isNumber = (v: unknown): v is number =>
  typeof v === 'number' && Number.isFinite(v)

const SYSTEM = 'system'

/**
 * Scope columns the estimates vary over (more than one value), numeric
 * columns first, each group sorted by name.
 */
export function scopeColumns(
  estimates: readonly AnalysisEstimate[],
): { name: string; numeric: boolean; values: number }[] {
  const values = new Map<string, Set<string>>()
  const numeric = new Map<string, boolean>()
  for (const e of estimates) {
    for (const [k, v] of Object.entries(e.scope_values ?? {})) {
      if (v === null || v === undefined) continue
      values.set(k, (values.get(k) ?? new Set()).add(levelText(v)))
      numeric.set(k, (numeric.get(k) ?? true) && isNumber(v))
    }
  }
  return [...values]
    .filter(([, s]) => s.size > 1)
    .map(([name, s]) => ({
      name,
      numeric: numeric.get(name) ?? false,
      values: s.size,
    }))
    .sort((a, b) =>
      a.numeric !== b.numeric
        ? a.numeric
          ? -1
          : 1
        : a.name < b.name
          ? -1
          : a.name > b.name
            ? 1
            : 0,
    )
}

/**
 * The default columns of a profile: the first numeric scope column other
 * than the system as x (else the first ordered one), the system as series
 * when the estimates vary over it, no facet. Null when nothing varies.
 */
export function defaultProfileColumns(
  estimates: readonly AnalysisEstimate[],
): ProfileColumns | null {
  const columns = scopeColumns(estimates)
  const x =
    columns.find((c) => c.numeric && c.name !== SYSTEM) ??
    columns.find((c) => c.name !== SYSTEM) ??
    null
  if (!x) return null
  const series = columns.some((c) => c.name === SYSTEM) ? SYSTEM : null
  return { x: x.name, series, facet: null }
}

function naturalCompare(a: string, b: string): number {
  return a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' })
}

/**
 * A profile from the estimates of one contrast: points over `x`, lines by
 * `series`, panels by `facet` and by any further scope column (so lines of
 * different scopes never mix). Estimates without a value of `x` or without
 * an estimate are left out. A numeric `x` is drawn at its values, any other
 * at the index of its level in natural order.
 */
export function profileFromEstimates(
  estimates: readonly AnalysisEstimate[],
  columns: ProfileColumns,
  options: { allLabel?: string } = {},
): ProfileData {
  const used = estimates.filter((e) => {
    const v = e.scope_values?.[columns.x]
    return v !== null && v !== undefined && isNumber(e.estimate)
  })
  const numericX = used.every((e) => isNumber(e.scope_values?.[columns.x]))
  const xLevels = numericX
    ? null
    : [
        ...new Set(used.map((e) => levelText(e.scope_values?.[columns.x]))),
      ].sort(naturalCompare)
  const xOf = (e: AnalysisEstimate): number => {
    const v = e.scope_values?.[columns.x]
    return numericX ? (v as number) : xLevels!.indexOf(levelText(v))
  }
  const seriesOf = (e: AnalysisEstimate) =>
    columns.series ? levelText(e.scope_values?.[columns.series]) : ''
  const labels =
    columns.series === SYSTEM
      ? systemLabels(used.map(seriesOf))
      : new Map<string, string>()

  const panels = new Map<string, Map<string, ProfilePoint[]>>()
  const titles = new Map<string, string>()
  let xs = 0
  let ys = 0
  for (const e of used) {
    const scope = e.scope_values ?? {}
    // The facet first, then every further scope column.
    const others = Object.keys(scope)
      .filter((k) => k !== columns.x && k !== columns.series)
      .sort((a, b) =>
        a === columns.facet ? -1 : b === columns.facet ? 1 : a < b ? -1 : 1,
      )
    const panelKey = others
      .map((k) => `${k} = ${levelText(scope[k])}`)
      .join(', ')
    titles.set(panelKey, panelKey)
    const lines = panels.get(panelKey) ?? new Map<string, ProfilePoint[]>()
    const key = seriesOf(e)
    const points = lines.get(key) ?? []
    const x = xOf(e)
    points.push({
      x,
      estimate: e.estimate as number,
      lower: isNumber(e.ci_lower) ? e.ci_lower : null,
      upper: isNumber(e.ci_upper) ? e.ci_upper : null,
      n: isNumber(e.n_obs) ? e.n_obs : null,
    })
    lines.set(key, points)
    panels.set(panelKey, lines)
    xs += x
    ys += e.estimate as number
  }
  const count = Math.max(1, used.length)
  return {
    xLevels,
    xMean: xs / count,
    yMean: ys / count,
    panels: [...panels]
      .sort(([a], [b]) => naturalCompare(a, b))
      .map(([key, lines]) => ({
        key,
        title: key ? (titles.get(key) ?? key) : null,
        lines: [...lines]
          .sort(([a], [b]) => naturalCompare(a, b))
          .map(([series, points]) => ({
            key: series,
            label:
              labels.get(series) || series || (options.allLabel ?? columns.x),
            title: columns.series
              ? `${columns.series} = ${series}`
              : (options.allLabel ?? ''),
            points: points.sort((a, b) => a.x - b.x),
          })),
      })),
  }
}

// ---------------------------------------------------------------------------
// The run's spec
// ---------------------------------------------------------------------------

/** An estimand of a run's normalized spec (the keys the views read). */
export interface SpecEstimand {
  id: string
  estimator: string
  outcome?: string
  reference?: unknown
  players?: string[]
  link?: string
  terms?: unknown[]
  contrasts?: unknown
}

/** The estimands of a run's normalized spec. */
export function specEstimands(
  run: Pick<AnalysisRun, 'normalized_spec'> | null,
): SpecEstimand[] {
  const spec = (run?.normalized_spec ?? {}) as { estimands?: unknown }
  return Array.isArray(spec.estimands)
    ? (spec.estimands as SpecEstimand[]).filter(
        (e) => e && typeof e.id === 'string',
      )
    : []
}

/** The designs a run reads from its own project (`inputs.designs`). */
export function specDesigns(
  run: Pick<AnalysisRun, 'normalized_spec'> | null,
): string[] {
  const spec = (run?.normalized_spec ?? {}) as {
    inputs?: { designs?: unknown }
  }
  const designs = spec.inputs?.designs
  return Array.isArray(designs)
    ? designs.filter((d): d is string => typeof d === 'string')
    : []
}

/** The linear contrasts of a spec estimand with their weights. */
function linearContrasts(
  estimand: SpecEstimand,
): { id: string; weights: Record<string, number> }[] {
  if (!Array.isArray(estimand.contrasts)) return []
  return (estimand.contrasts as Record<string, unknown>[])
    .filter(
      (c) =>
        c &&
        (c.kind ?? 'linear') === 'linear' &&
        typeof c.id === 'string' &&
        c.weights &&
        typeof c.weights === 'object',
    )
    .map((c) => ({
      id: c.id as string,
      weights: c.weights as Record<string, number>,
    }))
}

/**
 * The fitted slope that belongs to a profile over `column`: the pooled
 * estimate of a linear contrast whose only weight is 1 on the term `column`,
 * in an estimand with the same outcome. Null when the run has none.
 */
export function slopeEstimate(
  run: Pick<AnalysisRun, 'normalized_spec'> | null,
  estimates: readonly AnalysisEstimate[],
  outcome: string | null,
  column: string,
): AnalysisEstimate | null {
  for (const estimand of specEstimands(run)) {
    if (outcome && estimand.outcome !== outcome) continue
    for (const contrast of linearContrasts(estimand)) {
      const keys = Object.keys(contrast.weights)
      if (keys.length !== 1 || keys[0] !== column) continue
      if (contrast.weights[column] !== 1) continue
      const found = estimates.find(
        (e) =>
          e.estimand_id === estimand.id &&
          e.contrast_id === contrast.id &&
          e.scope === 'pooled' &&
          isNumber(e.estimate),
      )
      if (found) return found
    }
  }
  return null
}
