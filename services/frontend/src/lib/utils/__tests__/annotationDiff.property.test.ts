/**
 * Property-based tests for computeAnnotationDiff (annotationDiff.ts).
 *
 * These are the mutant-killing co-gate for the Stryker mutation run on
 * annotationDiff.ts. Where the example-based tests pin a handful of concrete
 * cases, these assert algebraic invariants over fast-check-generated inputs:
 * reflexivity, add/remove antisymmetry, summary integrity, and total absence
 * of crashes on arbitrary shapes. A mutation that breaks any of these (e.g.
 * flipping a status, off-by-one in a filter, swapping original/review) gets
 * caught by at least one property across the generated sample.
 */

import fc from 'fast-check'

import { computeAnnotationDiff } from '../annotationDiff'
import { AnnotationResult } from '@/types/labelStudio'

// --- Arbitraries ---------------------------------------------------------

// A reasonably small key space so collisions (same from_name appearing in
// both arrays, or duplicated within one array) actually happen during a run —
// that's where the match-by-from_name logic and Map-dedup behavior live.
const fromNameArb = fc.constantFrom('a', 'b', 'c', 'd', 'e', 'f', 'g', 'h')

// `value` deliberately ranges across the JSON-ish shapes the real annotation
// payloads carry: strings, numbers, null, nested objects, arrays.
const valueArb = fc.oneof(
  fc.string(),
  fc.integer(),
  fc.double({ noNaN: true }),
  fc.boolean(),
  fc.constant(null),
  fc.record({ text: fc.array(fc.string()) }),
  fc.array(fc.string()),
)

const annotationResultArb: fc.Arbitrary<AnnotationResult> = fc.record({
  from_name: fromNameArb,
  to_name: fc.string(),
  type: fc.constantFrom('textarea', 'labels', 'choices', 'rating'),
  value: valueArb,
})

const resultArrayArb = fc.array(annotationResultArb, { maxLength: 12 })

// Number of distinct from_name keys present across both arrays — this is the
// cardinality the diff collapses to, because results are matched/deduped by
// from_name via a Map.
function distinctKeyCount(
  original: AnnotationResult[],
  review: AnnotationResult[],
): number {
  const keys = new Set<string>()
  for (const r of original) keys.add(r.from_name)
  for (const r of review) keys.add(r.from_name)
  return keys.size
}

// --- Properties ----------------------------------------------------------

describe('computeAnnotationDiff — properties', () => {
  it('reflexivity: diffing an array against itself is all-unchanged', () => {
    fc.assert(
      fc.property(resultArrayArb, (xs) => {
        const { fields, summary } = computeAnnotationDiff(xs, xs)
        // Every field must be unchanged.
        expect(fields.every((f) => f.status === 'unchanged')).toBe(true)
        expect(summary.added).toBe(0)
        expect(summary.removed).toBe(0)
        expect(summary.modified).toBe(0)
        // unchanged count equals the total, and the total is the distinct-key
        // count (duplicate from_names within `xs` collapse via the Map).
        expect(summary.unchanged).toBe(summary.total)
        expect(summary.total).toBe(distinctKeyCount(xs, xs))
      }),
    )
  })

  it('add/remove antisymmetry: swapping args swaps added<->removed', () => {
    fc.assert(
      fc.property(resultArrayArb, resultArrayArb, (a, b) => {
        const ab = computeAnnotationDiff(a, b).summary
        const ba = computeAnnotationDiff(b, a).summary
        // A key present only in the review side is "added"; reverse the roles
        // and that same key is "removed". So added(a,b) === removed(b,a).
        expect(ab.added).toBe(ba.removed)
        expect(ab.removed).toBe(ba.added)
        // Modified and unchanged are symmetric (same overlapping keys).
        expect(ab.modified).toBe(ba.modified)
        expect(ab.unchanged).toBe(ba.unchanged)
      }),
    )
  })

  it('summary integrity: counts partition the field list and the key union', () => {
    fc.assert(
      fc.property(resultArrayArb, resultArrayArb, (a, b) => {
        const { fields, summary } = computeAnnotationDiff(a, b)

        // total === fields.length === |union of from_names|
        expect(summary.total).toBe(fields.length)
        expect(summary.total).toBe(distinctKeyCount(a, b))

        // The four status buckets partition the field list exactly.
        expect(
          summary.added + summary.removed + summary.modified + summary.unchanged,
        ).toBe(summary.total)

        // Each summary count matches the actual number of fields with that
        // status — a mutated filter predicate breaks this.
        const byStatus = (s: string) =>
          fields.filter((f) => f.status === s).length
        expect(summary.added).toBe(byStatus('added'))
        expect(summary.removed).toBe(byStatus('removed'))
        expect(summary.modified).toBe(byStatus('modified'))
        expect(summary.unchanged).toBe(byStatus('unchanged'))

        // Every emitted from_name is in the union, and each appears once.
        const emitted = fields.map((f) => f.from_name)
        expect(new Set(emitted).size).toBe(emitted.length)
        const union = new Set([
          ...a.map((r) => r.from_name),
          ...b.map((r) => r.from_name),
        ])
        for (const name of emitted) expect(union.has(name)).toBe(true)
      }),
    )
  })

  it('no-crash: never throws on arbitrary {from_name,to_name,type,value} arrays', () => {
    // Looser arbitrary than the typed one above: from_name is any string,
    // value can be anything JSON-serializable-ish.
    const looseResultArb = fc.record({
      from_name: fc.string(),
      to_name: fc.option(fc.string(), { nil: undefined }),
      type: fc.option(fc.string(), { nil: undefined }),
      value: fc.oneof(
        fc.string(),
        fc.integer(),
        fc.constant(null),
        fc.object(),
        fc.anything(),
      ),
    })
    const looseArrayArb = fc.array(looseResultArb, { maxLength: 12 })

    fc.assert(
      fc.property(looseArrayArb, looseArrayArb, (a, b) => {
        expect(() =>
          computeAnnotationDiff(a as AnnotationResult[], b as AnnotationResult[]),
        ).not.toThrow()
      }),
    )
  })
})
