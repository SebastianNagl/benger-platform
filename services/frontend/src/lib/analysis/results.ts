/**
 * Pure helpers for the analysis results page: number and p-value formatting,
 * grouping the estimates of a run into contrasts, the rows and equivalence
 * bands of a forest plot, and axis ticks.
 *
 * Nothing here computes statistics: every number comes from the engine's
 * stored estimates (services/shared/analysis), the page only arranges them.
 */

import type { AnalysisEstimate, AnalysisTost } from '@/lib/api/analysis'
import { intlTag } from '@/lib/i18n/locales'

/** Placeholder for a missing number. */
export const MISSING = '—'

const isNumber = (v: unknown): v is number =>
  typeof v === 'number' && Number.isFinite(v)

/** A number with `digits` significant digits in the UI locale. */
export function formatNumber(
  value: number | null | undefined,
  locale: string,
  digits = 4,
): string {
  if (!isNumber(value)) return MISSING
  if (value === 0) return '0'
  const abs = Math.abs(value)
  if (abs >= 1e6 || abs < 1e-4) {
    return new Intl.NumberFormat(intlTag(locale), {
      notation: 'scientific',
      maximumFractionDigits: Math.max(0, digits - 1),
    }).format(value)
  }
  return new Intl.NumberFormat(intlTag(locale), {
    maximumSignificantDigits: digits,
  }).format(value)
}

/**
 * A p-value: three decimals from 0.001 on, scientific notation below (the
 * exact value is in the cell's title).
 */
export function formatP(p: number | null | undefined, locale: string): string {
  if (!isNumber(p)) return MISSING
  if (p === 0) return '0'
  if (p < 0.001) {
    return new Intl.NumberFormat(intlTag(locale), {
      notation: 'scientific',
      maximumFractionDigits: 1,
    }).format(p)
  }
  return new Intl.NumberFormat(intlTag(locale), {
    minimumFractionDigits: 3,
    maximumFractionDigits: 3,
  }).format(p)
}

/** A closed interval, e.g. "[-5.855, -3.603]". */
export function formatInterval(
  lower: number | null | undefined,
  upper: number | null | undefined,
  locale: string,
  digits = 4,
): string {
  if (!isNumber(lower) || !isNumber(upper)) return MISSING
  return `[${formatNumber(lower, locale, digits)}, ${formatNumber(upper, locale, digits)}]`
}

/** A confidence level as a percentage, e.g. 0.95 -> "95 %" (locale aware). */
export function formatLevel(
  level: number | null | undefined,
  locale: string,
): string {
  if (!isNumber(level)) return MISSING
  return new Intl.NumberFormat(intlTag(locale), {
    style: 'percent',
    maximumFractionDigits: 1,
  }).format(level)
}

/** The first 12 characters of a hex digest (the full one goes in a title). */
export function shortHash(hash: string | null | undefined): string {
  if (!hash) return MISSING
  return hash.length > 12 ? hash.slice(0, 12) : hash
}

/**
 * The scope of an estimate as "column = value" pairs, or null for the pooled
 * fit (the caller translates "pooled").
 */
export function scopeDescription(
  estimate: Pick<AnalysisEstimate, 'scope' | 'scope_values'>,
): string | null {
  if (estimate.scope === 'pooled') return null
  const values = estimate.scope_values
  if (values && typeof values === 'object' && Object.keys(values).length > 0) {
    return Object.entries(values)
      .map(([column, value]) => `${column} = ${String(value)}`)
      .join(', ')
  }
  return estimate.scope
}

/** Key of one contrast of one estimand. */
export function contrastKey(
  estimate: Pick<AnalysisEstimate, 'estimand_id' | 'contrast_id'>,
): string {
  return `${estimate.estimand_id}\u0000${estimate.contrast_id ?? ''}`
}

/** The estimates of one contrast of one estimand, across its scopes. */
export interface ContrastGroup {
  key: string
  estimandId: string
  contrastId: string | null
  estimates: AnalysisEstimate[]
}

/** Group estimates by estimand and contrast, in engine order. */
export function groupByContrast(
  estimates: readonly AnalysisEstimate[],
): ContrastGroup[] {
  const groups = new Map<string, ContrastGroup>()
  const sorted = [...estimates].sort((a, b) => a.position - b.position)
  for (const estimate of sorted) {
    const key = contrastKey(estimate)
    let group = groups.get(key)
    if (!group) {
      group = {
        key,
        estimandId: estimate.estimand_id,
        contrastId: estimate.contrast_id,
        estimates: [],
      }
      groups.set(key, group)
    }
    group.estimates.push(estimate)
  }
  return [...groups.values()]
}

/** One equivalence bound set declared for a contrast. */
export interface EquivalenceBand {
  /** Index of the bound set in the estimates' `tost` lists. */
  index: number
  lower: number
  upper: number
  level: number
}

/**
 * The equivalence bound sets of a contrast, in declaration order (the
 * engine writes the same bound sets, in the same order, on every scope of a
 * contrast; the first estimate that carries them defines the list).
 */
export function equivalenceBands(
  estimates: readonly AnalysisEstimate[],
): EquivalenceBand[] {
  for (const estimate of estimates) {
    const tost = estimate.tost
    if (Array.isArray(tost) && tost.length > 0) {
      return tost
        .map((t, index) => ({
          index,
          lower: t.lower,
          upper: t.upper,
          level: t.level,
        }))
        .filter((b) => isNumber(b.lower) && isNumber(b.upper))
    }
  }
  return []
}

/** The TOST result of an estimate for one bound set, if it has one. */
export function tostFor(
  estimate: Pick<AnalysisEstimate, 'tost'>,
  index: number,
): AnalysisTost | null {
  const tost = estimate.tost
  if (!Array.isArray(tost)) return null
  return tost[index] ?? null
}

/** Whether every estimate has the same null value; returns it, else null. */
export function commonNullValue(
  estimates: readonly AnalysisEstimate[],
): number | null {
  let value: number | null = null
  for (const estimate of estimates) {
    if (!isNumber(estimate.null_value)) continue
    if (value === null) value = estimate.null_value
    else if (value !== estimate.null_value) return null
  }
  return value
}

/** Distinct family ids of a run's estimates (all memberships), sorted. */
export function familiesOf(estimates: readonly AnalysisEstimate[]): string[] {
  const ids = new Set<string>()
  for (const estimate of estimates) {
    if (estimate.family) ids.add(estimate.family)
    for (const adjustment of estimate.adjustments ?? []) {
      if (adjustment.family) ids.add(adjustment.family)
    }
  }
  return [...ids].sort()
}

/** Whether an estimate belongs to `family` (any of its memberships). */
export function inFamily(estimate: AnalysisEstimate, family: string): boolean {
  if (estimate.family === family) return true
  return (estimate.adjustments ?? []).some((a) => a.family === family)
}

/** Round to a "nice" step (1, 2, 2.5 or 5 times a power of ten). */
function niceStep(rough: number): number {
  const power = Math.pow(10, Math.floor(Math.log10(rough)))
  const fraction = rough / power
  const nice =
    fraction <= 1
      ? 1
      : fraction <= 2
        ? 2
        : fraction <= 2.5
          ? 2.5
          : fraction <= 5
            ? 5
            : 10
  return nice * power
}

/**
 * A padded axis domain and its tick values covering every given value.
 * Returns a unit domain around the value when all values coincide.
 */
export function axisTicks(
  values: readonly (number | null | undefined)[],
  target = 5,
): { min: number; max: number; ticks: number[] } {
  const finite = values.filter(isNumber)
  if (finite.length === 0) return { min: -1, max: 1, ticks: [-1, 0, 1] }
  let lo = Math.min(...finite)
  let hi = Math.max(...finite)
  if (lo === hi) {
    const pad = lo === 0 ? 1 : Math.abs(lo) * 0.5
    lo -= pad
    hi += pad
  }
  const step = niceStep((hi - lo) / Math.max(1, target))
  const min = Number((Math.floor(lo / step) * step).toPrecision(12))
  const max = Number((Math.ceil(hi / step) * step).toPrecision(12))
  const ticks: number[] = []
  // Integer steps avoid accumulating floating point error.
  const count = Math.round((max - min) / step)
  for (let i = 0; i <= count; i++) {
    ticks.push(Number((min + i * step).toPrecision(12)))
  }
  return { min, max, ticks }
}
