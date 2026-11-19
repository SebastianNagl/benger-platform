/**
 * Units of a variant design in the views: declared spans cut into text
 * pieces, twin tasks paired along one factor, and the factor a contrast of
 * an analysis run most likely compares (the default focus of the unit
 * viewer; the reader can pick another).
 */

import type { AnalysisEstimate } from '@/lib/api/analysis'
import type { UnitTask, UnitView, VariantFactor } from '@/lib/api/variantViews'
import { levelText } from './labels'
import { specEstimands, type SpecEstimand } from './profile'

/** Text cut into plain and highlighted pieces by `[start, end)` spans. */
export function segments(
  text: string,
  spans: readonly (readonly [number, number])[],
): { text: string; marked: boolean }[] {
  const out: { text: string; marked: boolean }[] = []
  let cursor = 0
  for (const [start, end] of [...spans].sort((a, b) => a[0] - b[0])) {
    const s = Math.max(cursor, Math.min(start, text.length))
    const e = Math.max(s, Math.min(end, text.length))
    if (s > cursor) out.push({ text: text.slice(cursor, s), marked: false })
    if (e > s) out.push({ text: text.slice(s, e), marked: true })
    cursor = e
  }
  if (cursor < text.length)
    out.push({ text: text.slice(cursor), marked: false })
  return out
}

/** What the unit viewer pairs: a factor with a reference and a treated level. */
export interface UnitFocus {
  factor?: string | null
  reference?: unknown
  level?: unknown
}

/** The task factors that vary inside a unit (the ones twins differ in). */
export function withinUnitFactors(
  factors: readonly VariantFactor[],
): VariantFactor[] {
  return factors.filter(
    (f) =>
      (f.source ?? 'task') === 'task' &&
      (f.varies ?? 'within_unit') === 'within_unit',
  )
}

/** The levels of a factor in the tasks of a unit, declared order first. */
export function unitLevels(view: UnitView, factor: string): string[] {
  const declared = (
    view.design.factors.find((f) => f.name === factor)?.levels ?? []
  ).map(levelText)
  const seen = new Set(view.tasks.map((t) => levelText(t.factors[factor])))
  return [
    ...declared.filter((l) => seen.has(l)),
    ...[...seen].filter((l) => l !== '' && !declared.includes(l)).sort(),
  ]
}

/**
 * The focus the viewer uses: the given one where the unit has it, else the
 * first within-unit factor with its first two levels. Null factor when the
 * design has no within-unit task factor (the tasks are shown one by one).
 */
export function resolveFocus(
  view: UnitView,
  focus: UnitFocus,
): { factor: string | null; reference: string; level: string } {
  const within = withinUnitFactors(view.design.factors).map((f) => f.name)
  const factor =
    focus.factor && within.includes(focus.factor)
      ? focus.factor
      : (within[0] ?? null)
  if (!factor) return { factor: null, reference: '', level: '' }
  const levels = unitLevels(view, factor)
  const want = (value: unknown, fallback: string) => {
    const text = levelText(value)
    return levels.includes(text) ? text : fallback
  }
  const given = factor === focus.factor
  const wantedLevel = given ? want(focus.level, '') : ''
  const reference = want(
    given ? focus.reference : undefined,
    levels.find((l) => l !== wantedLevel) ?? '',
  )
  const level =
    wantedLevel && wantedLevel !== reference
      ? wantedLevel
      : (levels.find((l) => l !== reference) ?? '')
  return { factor, reference, level }
}

/**
 * Twin pairs of a unit along one factor: (reference task, treated task)
 * agreeing on every other within-unit factor of the design. None when the
 * two levels are the same (a task is not its own twin).
 */
export function twinPairs(
  view: UnitView,
  factor: string,
  reference: string,
  level: string,
): [UnitTask, UnitTask][] {
  if (reference === level) return []
  const others = withinUnitFactors(view.design.factors)
    .map((f) => f.name)
    .filter((n) => n !== factor)
  const sig = (t: UnitTask) =>
    JSON.stringify(others.map((n) => levelText(t.factors[n])))
  const pairs: [UnitTask, UnitTask][] = []
  for (const treated of view.tasks) {
    if (levelText(treated.factors[factor]) !== level) continue
    for (const ref of view.tasks) {
      if (
        levelText(ref.factors[factor]) === reference &&
        sig(ref) === sig(treated)
      ) {
        pairs.push([ref, treated])
      }
    }
  }
  return pairs
}

// ---------------------------------------------------------------------------
// The factor a contrast compares
// ---------------------------------------------------------------------------

/** `name[level]` of a dummy term's parameter. */
const DUMMY = /^([^[\]:]+)\[(.+)\]$/

interface MeasureSpec {
  kind?: string
  expr?: string
}

function measuresOf(
  spec: Record<string, unknown>,
): Record<string, MeasureSpec> {
  const measures = spec.measures
  return measures && typeof measures === 'object'
    ? (measures as Record<string, MeasureSpec>)
    : {}
}

/** Names an expression reads (identifiers outside quoted strings). */
function identifiers(expr: string): string[] {
  const bare = expr.replace(/'[^']*'|"[^"]*"/g, ' ')
  return [...new Set(bare.match(/[A-Za-z_][A-Za-z0-9_]*/g) ?? [])]
}

/** A literal compared with a factor in an expression (`factor == 'X'`). */
function comparedLevel(expr: string, factor: string): string | null {
  const re = new RegExp(
    `\\b${factor.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*==\\s*['"]([^'"]+)['"]`,
  )
  return expr.match(re)?.[1] ?? null
}

/**
 * The design factor a term of the frame stands for: the factor itself, a
 * dummy of it (`factor[level]`, with the term's declared reference), or an
 * expression measure that reads exactly one of the candidate factors.
 */
function factorOfTerm(
  term: string,
  factors: readonly string[],
  measures: Record<string, MeasureSpec>,
  dummyReferences: Record<string, unknown>,
  depth = 0,
): UnitFocus | null {
  const dummy = term.match(DUMMY)
  if (dummy && factors.includes(dummy[1])) {
    return {
      factor: dummy[1],
      level: dummy[2],
      reference: dummyReferences[dummy[1]],
    }
  }
  if (factors.includes(term)) return { factor: term }
  const measure = measures[term]
  if (depth < 4 && measure?.kind === 'expression' && measure.expr) {
    const found = identifiers(measure.expr)
      .map((name) =>
        name === term
          ? null
          : factorOfTerm(name, factors, measures, dummyReferences, depth + 1),
      )
      .filter((f): f is UnitFocus => f !== null)
    const names = [...new Set(found.map((f) => f.factor))]
    if (names.length === 1) {
      const level = comparedLevel(measure.expr, names[0]!)
      return level !== null
        ? { factor: names[0], level }
        : (found.find((f) => f.factor === names[0]) ?? null)
    }
  }
  return null
}

function dummyReferencesOf(estimand: SpecEstimand): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  const walk = (term: unknown) => {
    if (!term || typeof term !== 'object') return
    const t = term as Record<string, unknown>
    if (typeof t.dummies === 'string') out[t.dummies] = t.reference
    if (Array.isArray(t.interact)) t.interact.forEach(walk)
  }
  ;(estimand.terms ?? []).forEach(walk)
  return out
}

/**
 * The factor focus a contrast suggests, read from the run's spec: an `ame`
 * contrast names its column and levels; a linear contrast with weight on a
 * single term points to the factor that term stands for. Empty when the
 * spec says nothing usable; the viewer then falls back to its default.
 */
export function focusForContrast(
  normalizedSpec: Record<string, unknown> | null | undefined,
  estimate: Pick<AnalysisEstimate, 'estimand_id' | 'contrast_id'>,
  factors: readonly string[],
): UnitFocus {
  const spec = normalizedSpec ?? {}
  const estimand = specEstimands({ normalized_spec: spec }).find(
    (e) => e.id === estimate.estimand_id,
  )
  if (!estimand || !Array.isArray(estimand.contrasts)) return {}
  const contrast = (estimand.contrasts as Record<string, unknown>[]).find(
    (c) => c && c.id === estimate.contrast_id,
  )
  if (!contrast) return {}
  if (contrast.kind === 'ame' && typeof contrast.column === 'string') {
    return factors.includes(contrast.column)
      ? {
          factor: contrast.column,
          reference: contrast.reference,
          level: contrast.level,
        }
      : {}
  }
  const weights =
    contrast.weights && typeof contrast.weights === 'object'
      ? Object.keys(contrast.weights as Record<string, unknown>)
      : []
  if (weights.length !== 1) return {}
  // An interaction term compares its first part across the others.
  const term = weights[0]!.split(':')[0]!
  return (
    factorOfTerm(
      term,
      factors,
      measuresOf(spec),
      dummyReferencesOf(estimand),
    ) ?? {}
  )
}
