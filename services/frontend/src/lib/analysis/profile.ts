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

/**
 * A straight line of the given slope: through the means of one line's
 * points when `line` names it (its series key), else through the means of
 * every point.
 */
export interface ProfileSlope {
  slope: number
  label: string
  lower?: number | null
  upper?: number | null
  line?: string
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

type SpecTerm =
  | string
  | {
      dummies?: unknown
      by?: unknown
      reference?: unknown
      levels?: unknown
      interact?: unknown
    }

function termReads(term: unknown, column: string): boolean {
  if (typeof term === 'string') return term === column
  if (!term || typeof term !== 'object') return false
  const t = term as Exclude<SpecTerm, string>
  if (Array.isArray(t.interact))
    return t.interact.some((s) => termReads(s, column))
  return t.dummies === column || t.by === column
}

/**
 * The factor of a term `{interact: [column, {dummies: factor}]}` (in either
 * order) with its declared reference level, or null for any other term.
 */
function slopeInteraction(
  term: unknown,
  column: string,
): { factor: string; reference: string | null } | null {
  if (!term || typeof term !== 'object') return null
  const parts = (term as { interact?: unknown }).interact
  if (!Array.isArray(parts) || parts.length !== 2) return null
  const dummies = parts.find((p) => p !== column) as
    Exclude<SpecTerm, string> | undefined
  if (
    !parts.includes(column) ||
    !dummies ||
    typeof dummies !== 'object' ||
    typeof dummies.dummies !== 'string' ||
    dummies.by
  )
    return null
  const declared =
    dummies.reference ??
    (Array.isArray(dummies.levels) ? dummies.levels[0] : undefined)
  return {
    factor: dummies.dummies,
    reference: declared === undefined ? null : levelText(declared),
  }
}

/**
 * Estimators the engine fits as a linear model on the outcome itself, so a
 * contrast on a term is a slope on the scale of a profile of means; the
 * coefficients of logit, Bradley-Terry, Plackett-Luce or the conditional
 * logit are on a link scale and are never drawn as one.
 */
const LINEAR_ESTIMATORS = new Set(['fe_ols', 'mixedlm'])

/** A fitted slope of a profile: for every line (`line` null) or for one. */
export interface ProfileSlopeEstimate {
  line: string | null
  estimate: AnalysisEstimate
}

/**
 * The fitted slopes that belong to a profile, so a line is only ever drawn
 * for a slope the run estimated of exactly what is plotted. Only a profile
 * of levels (the means of `mean_rate`) has one: the pooled estimate of a
 * linear contrast on the x column in a linear-model estimand (`fe_ols`,
 * `mixedlm`) of the same outcome that has `columns.x` as a term. Without an interaction of x the contrast
 * `{x: 1}` is the slope of every line. With one interaction of x and a
 * factor that is the series, each level gets its own slope: `{x: 1}` for
 * the declared reference level and `{x: 1, "factor[level]:x": 1}` for the
 * others. Any other profile (a difference, a coefficient) or estimand
 * shape gives none.
 */
export function profileSlopes(
  run: Pick<AnalysisRun, 'normalized_spec'> | null,
  estimates: readonly AnalysisEstimate[],
  profiled: readonly AnalysisEstimate[],
  columns: ProfileColumns,
): ProfileSlopeEstimate[] {
  const first = profiled[0]
  if (!first || first.estimator !== 'mean_rate' || !first.outcome) return []
  const x = columns.x
  for (const estimand of specEstimands(run)) {
    if (!LINEAR_ESTIMATORS.has(estimand.estimator)) continue
    if (estimand.outcome !== first.outcome) continue
    const terms = Array.isArray(estimand.terms) ? estimand.terms : []
    if (!terms.includes(x)) continue
    const others = terms.filter((t) => t !== x && termReads(t, x))
    const interaction =
      others.length === 1 ? slopeInteraction(others[0], x) : null
    if (
      others.length > 0 &&
      (!interaction || interaction.factor !== columns.series)
    )
      continue
    const pooled = (contrastId: string) =>
      estimates.find(
        (e) =>
          e.estimand_id === estimand.id &&
          e.contrast_id === contrastId &&
          e.scope === 'pooled' &&
          isNumber(e.estimate),
      )
    const found: ProfileSlopeEstimate[] = []
    for (const contrast of linearContrasts(estimand)) {
      const keys = Object.keys(contrast.weights)
      if (contrast.weights[x] !== 1) continue
      if (!keys.every((k) => contrast.weights[k] === 1)) continue
      let line: string | null
      if (keys.length === 1) {
        if (interaction && interaction.reference === null) continue
        line = interaction ? interaction.reference : null
      } else if (interaction && keys.length === 2) {
        const other = keys.find((k) => k !== x)!
        const prefix = `${interaction.factor}[`
        const name = other.startsWith(`${x}:`)
          ? other.slice(x.length + 1)
          : other.endsWith(`:${x}`)
            ? other.slice(0, -(x.length + 1))
            : ''
        if (!name.startsWith(prefix) || !name.endsWith(']')) continue
        line = name.slice(prefix.length, -1)
      } else continue
      const estimate = pooled(contrast.id)
      if (estimate && !found.some((f) => f.line === line))
        found.push({ line, estimate })
    }
    if (found.length > 0) return found
  }
  return []
}
