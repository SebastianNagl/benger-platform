/**
 * Pure helpers for the report's Analyses section: which estimates an
 * exhibit shows, the values its filters can take, and the estimates of an
 * exhibit in a snapshot.
 *
 * `exhibitSelects` is the editor preview's copy of the server rule the
 * snapshot applies (`exhibit_selects` in services/shared/report_snapshot.py);
 * both are tested against the same cases.
 */

import { familiesOf } from '@/lib/analysis/results'
import type { AnalysisEstimate } from '@/lib/api/analysis'
import type {
  ReportAnalysisRun,
  ReportExhibitFilters,
  ReportExhibitType,
} from '@/types/report'

export const EXHIBIT_TYPES: readonly ReportExhibitType[] = ['forest', 'table']

export const EXHIBIT_FILTER_KEYS = [
  'estimands',
  'contrasts',
  'families',
  'systems',
] as const

export type ExhibitFilterKey = (typeof EXHIBIT_FILTER_KEYS)[number]

/** Estimates one run contributes to a report (MAX_REPORT_ESTIMATES_PER_RUN). */
export const MAX_REPORT_ESTIMATES_PER_RUN = 1000

/** Runs the Analyses section takes (MAX_REPORT_ANALYSIS_RUNS). */
export const MAX_REPORT_ANALYSIS_RUNS = 10

/** Exhibits one run takes (MAX_RUN_EXHIBITS). */
export const MAX_RUN_EXHIBITS = 12

type EstimateLike = Pick<
  AnalysisEstimate,
  'estimand_id' | 'contrast_id' | 'scope_values' | 'family' | 'adjustments'
>

/**
 * The system an estimate is scoped to: its `system` (or `model_id`) scope
 * value, or null for a pooled estimate or another scope.
 */
export function estimateSystem(
  estimate: Pick<AnalysisEstimate, 'scope_values'>,
): string | null {
  const values = estimate.scope_values
  if (values && typeof values === 'object') {
    for (const column of ['system', 'model_id']) {
      const value = (values as Record<string, unknown>)[column]
      if (value !== null && value !== undefined) return String(value)
    }
  }
  return null
}

const restricts = (values: string[] | undefined): values is string[] =>
  Array.isArray(values) && values.length > 0

/**
 * Whether an exhibit with `filters` shows `estimate`: every given filter
 * holds. A systems filter keeps the listed systems and every estimate that
 * is not scoped to a system (pooled ones).
 */
export function exhibitSelects(
  estimate: EstimateLike,
  filters: ReportExhibitFilters | undefined,
): boolean {
  if (!filters) return true
  if (
    restricts(filters.estimands) &&
    !filters.estimands.includes(estimate.estimand_id)
  )
    return false
  if (
    restricts(filters.contrasts) &&
    (estimate.contrast_id === null ||
      !filters.contrasts.includes(estimate.contrast_id))
  )
    return false
  if (restricts(filters.families)) {
    const member = new Set<string>()
    if (estimate.family) member.add(estimate.family)
    for (const a of estimate.adjustments ?? []) {
      if (a?.family) member.add(a.family)
    }
    if (!filters.families.some((f) => member.has(f))) return false
  }
  if (restricts(filters.systems)) {
    const system = estimateSystem(estimate)
    if (system !== null && !filters.systems.includes(system)) return false
  }
  return true
}

/** The estimates an exhibit with `filters` shows, in engine order. */
export function selectEstimates<T extends EstimateLike & { position: number }>(
  estimates: readonly T[],
  filters: ReportExhibitFilters | undefined,
): T[] {
  return [...estimates]
    .filter((e) => exhibitSelects(e, filters))
    .sort((a, b) => a.position - b.position)
}

/** The values each filter can take for a run's estimates. */
export type ExhibitFilterOptions = Record<ExhibitFilterKey, string[]>

export function exhibitFilterOptions(
  estimates: readonly AnalysisEstimate[],
): ExhibitFilterOptions {
  const sorted = [...estimates].sort((a, b) => a.position - b.position)
  const unique = (values: (string | null)[]) => [
    ...new Set(values.filter((v): v is string => typeof v === 'string')),
  ]
  return {
    estimands: unique(sorted.map((e) => e.estimand_id)),
    contrasts: unique(sorted.map((e) => e.contrast_id)),
    families: familiesOf(sorted),
    systems: unique(sorted.map(estimateSystem)).sort(),
  }
}

/** A filter object without empty lists, its values sorted (the stored form). */
export function cleanFilters(
  filters: ReportExhibitFilters | undefined,
): ReportExhibitFilters {
  const out: ReportExhibitFilters = {}
  for (const key of EXHIBIT_FILTER_KEYS) {
    const values = filters?.[key]
    if (restricts(values)) out[key] = [...new Set(values)].sort()
  }
  return out
}

/** The estimates of a snapshot exhibit, in engine order. */
export function exhibitEstimates(
  run: Pick<ReportAnalysisRun, 'estimates'>,
  positions: readonly number[],
): ReportAnalysisRun['estimates'] {
  const byPosition = new Map(run.estimates.map((e) => [e.position, e]))
  return positions
    .map((p) => byPosition.get(p))
    .filter((e): e is ReportAnalysisRun['estimates'][number] => Boolean(e))
}

/** An exhibit id not yet used in `existing`. */
export function newExhibitId(existing: readonly string[]): string {
  const taken = new Set(existing)
  for (let i = existing.length + 1; ; i++) {
    const id = `exhibit-${i}`
    if (!taken.has(id)) return id
  }
}
