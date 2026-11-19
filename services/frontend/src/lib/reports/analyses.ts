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
import type { AnalysisEstimate, AnalysisRun } from '@/lib/api/analysis'
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
  | 'estimand_id'
  | 'contrast_id'
  | 'kind'
  | 'scope'
  | 'scope_values'
  | 'family'
  | 'adjustments'
>

/** What `estimateSystems` reads of a run: its normalized spec and fits. */
export type AnalysisRunDefinition = Pick<
  AnalysisRun,
  'normalized_spec' | 'fits'
>

/** The frame columns holding a system key (or the bare model id). */
const SYSTEM_COLUMNS = ['system', 'model_id']
const SYSTEM_PARAMETER = /(?:^|:)(?:system|model_id)\[([^[\]]*)\]/g

type Json = Record<string, unknown>

const isObject = (value: unknown): value is Json =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const asList = (value: unknown): unknown[] =>
  Array.isArray(value) ? value : []

/**
 * The system an estimate is scoped to: its `system` (or `model_id`) scope
 * value, or null for a pooled estimate or another scope.
 */
export function estimateSystem(
  estimate: Pick<AnalysisEstimate, 'scope_values'>,
): string | null {
  const values = estimate.scope_values
  if (values && typeof values === 'object') {
    for (const column of SYSTEM_COLUMNS) {
      const value = (values as Record<string, unknown>)[column]
      if (value !== null && value !== undefined) return String(value)
    }
  }
  return null
}

function levelsOf(source: Json, keys: string[]): string[] {
  return keys
    .map((k) => source[k])
    .filter((v) => v !== null && v !== undefined)
    .map(String)
}

/** (parameter names, system levels) a spec contrast refers to. */
function weightKeys(contrast: Json): [string[], string[]] {
  if (contrast.kind === 'ame') {
    return SYSTEM_COLUMNS.includes(contrast.column as string)
      ? [[], levelsOf(contrast, ['level', 'reference'])]
      : [[], []]
  }
  const parts =
    contrast.kind === 'ratio'
      ? [contrast.numerator, contrast.denominator]
      : [contrast]
  return [
    parts.flatMap((part) =>
      isObject(part) && isObject(part.weights) ? Object.keys(part.weights) : [],
    ),
    [],
  ]
}

function globPattern(pattern: string): RegExp {
  const escape = (part: string) => part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return new RegExp('^' + pattern.split('*').map(escape).join('.*') + '$')
}

/**
 * The systems an estimate involves: the one it is scoped to plus every
 * system level its contrast or joint test names in the run's normalized
 * spec (`system[<level>]` or `model_id[<level>]` parameters). The editor's
 * copy of `estimate_systems` in services/shared/report_snapshot.py.
 */
export function estimateSystems(
  estimate: EstimateLike,
  run: AnalysisRunDefinition | null | undefined,
): Set<string> {
  const systems = new Set<string>()
  const scoped = estimateSystem(estimate)
  if (scoped !== null) systems.add(scoped)
  const spec = run?.normalized_spec
  const est =
    (asList(isObject(spec) ? spec.estimands : undefined).find(
      (e) => isObject(e) && e.id === estimate.estimand_id,
    ) as Json | undefined) ?? {}
  const treat = est.treatment
  if (isObject(treat) && SYSTEM_COLUMNS.includes(treat.factor as string)) {
    for (const level of levelsOf(treat, ['level', 'reference']))
      systems.add(level)
  }
  const byId = new Map<unknown, Json>()
  for (const c of asList(est.contrasts)) if (isObject(c)) byId.set(c.id, c)
  const cid = estimate.contrast_id
  const names: unknown[] = []
  const contrasts: Json[] = []
  const test =
    estimate.kind === 'wald'
      ? (asList(est.joint_tests).find((t) => isObject(t) && t.id === cid) as
          Json | undefined)
      : undefined
  if (!test) {
    const listed = byId.get(cid)
    if (listed) contrasts.push(listed)
    else names.push(cid)
  } else if (Array.isArray(test.rows)) {
    for (const row of test.rows)
      if (isObject(row)) names.push(...Object.keys(row))
  } else if (Array.isArray(test.parameters)) {
    const patterns = test.parameters.filter(
      (p): p is string => typeof p === 'string',
    )
    names.push(...patterns.filter((p) => !p.includes('*')))
    const compiled = patterns.map(globPattern)
    for (const fit of run?.fits ?? []) {
      if (fit.estimand !== estimate.estimand_id || fit.scope !== estimate.scope)
        continue
      for (const n of fit.parameters ?? [])
        if (typeof n === 'string' && compiled.some((c) => c.test(n)))
          names.push(n)
    }
  } else {
    for (const ref of asList(test.contrasts)) {
      const listed = byId.get(ref)
      if (listed) contrasts.push(listed)
      else names.push(ref)
    }
  }
  for (const contrast of contrasts) {
    const [keys, levels] = weightKeys(contrast)
    names.push(...keys)
    for (const level of levels) systems.add(level)
  }
  for (const name of names) {
    if (typeof name !== 'string') continue
    for (const m of name.matchAll(SYSTEM_PARAMETER)) systems.add(m[1])
  }
  return systems
}

const restricts = (values: string[] | undefined): values is string[] =>
  Array.isArray(values) && values.length > 0

/**
 * Whether an exhibit with `filters` shows `estimate`, whose involved
 * systems (`estimateSystems`) are `systems`: every given filter holds. A
 * systems filter keeps an estimate exactly when it involves at least one
 * system and all of them are listed, so a pooled estimate involving no
 * system shows only without a systems filter.
 */
export function exhibitSelects(
  estimate: EstimateLike,
  filters: ReportExhibitFilters | undefined,
  systems: ReadonlySet<string>,
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
    const allowed = filters.systems
    if (systems.size === 0 || [...systems].some((s) => !allowed.includes(s)))
      return false
  }
  return true
}

/** The estimates an exhibit with `filters` shows, in engine order. */
export function selectEstimates<T extends EstimateLike & { position: number }>(
  estimates: readonly T[],
  filters: ReportExhibitFilters | undefined,
  run: AnalysisRunDefinition | null | undefined,
): T[] {
  return [...estimates]
    .filter((e) => exhibitSelects(e, filters, estimateSystems(e, run)))
    .sort((a, b) => a.position - b.position)
}

/** The values each filter can take for a run's estimates. */
export type ExhibitFilterOptions = Record<ExhibitFilterKey, string[]>

export function exhibitFilterOptions(
  estimates: readonly AnalysisEstimate[],
  run: AnalysisRunDefinition | null | undefined,
): ExhibitFilterOptions {
  const sorted = [...estimates].sort((a, b) => a.position - b.position)
  const unique = (values: (string | null)[]) => [
    ...new Set(values.filter((v): v is string => typeof v === 'string')),
  ]
  return {
    estimands: unique(sorted.map((e) => e.estimand_id)),
    contrasts: unique(sorted.map((e) => e.contrast_id)),
    families: familiesOf(sorted),
    systems: unique(sorted.flatMap((e) => [...estimateSystems(e, run)])).sort(),
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
