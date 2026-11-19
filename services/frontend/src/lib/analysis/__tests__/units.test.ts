/**
 * Units of a variant design (`@/lib/analysis/units`): span segments, twin
 * pairs along a factor, the viewer's focus and the factor a contrast of a
 * run's spec compares.
 */

import { makeUnitView } from '@/test-utils/variantViewFixtures'
import {
  focusForContrast,
  resolveFocus,
  segments,
  twinPairs,
  unitLevels,
} from '../units'

describe('segments', () => {
  it('cuts text into plain and marked pieces', () => {
    expect(segments('The tenant Ida asks.', [[11, 14]])).toEqual([
      { text: 'The tenant ', marked: false },
      { text: 'Ida', marked: true },
      { text: ' asks.', marked: false },
    ])
  })

  it('sorts, clips and skips overlapping spans', () => {
    expect(
      segments('abcdef', [
        [4, 99],
        [0, 2],
        [1, 3],
      ]),
    ).toEqual([
      { text: 'ab', marked: true },
      { text: 'c', marked: true },
      { text: 'd', marked: false },
      { text: 'ef', marked: true },
    ])
    expect(segments('', [[0, 3]])).toEqual([])
  })
})

describe('twin pairs and the focus', () => {
  it('pairs tasks that agree on every other within-unit factor', () => {
    const view = makeUnitView()
    const pairs = twinPairs(view, 'party', 'first', 'second')
    expect(pairs.map(([r, t]) => [r.id, t.id])).toEqual([
      ['t1', 't2'],
      ['t3', 't4'],
    ])
    expect(
      twinPairs(view, 'order', 'early', 'late').map(([r, t]) => [r.id, t.id]),
    ).toEqual([
      ['t1', 't3'],
      ['t2', 't4'],
    ])
  })

  it('pairs nothing along the same level', () => {
    expect(twinPairs(makeUnitView(), 'party', 'first', 'first')).toEqual([])
  })

  it('lists levels in declared order', () => {
    expect(unitLevels(makeUnitView(), 'party')).toEqual(['first', 'second'])
  })

  it('keeps a valid focus and fills in the rest', () => {
    const view = makeUnitView()
    expect(resolveFocus(view, {})).toEqual({
      factor: 'party',
      reference: 'first',
      level: 'second',
    })
    expect(resolveFocus(view, { factor: 'order', level: 'early' })).toEqual({
      factor: 'order',
      reference: 'late',
      level: 'early',
    })
    // A between-unit factor cannot pair twins: the default is used.
    expect(resolveFocus(view, { factor: 'level' }).factor).toBe('party')
    const flat = makeUnitView({
      design: { ...makeUnitView().design, factors: [] },
    })
    expect(resolveFocus(flat, {}).factor).toBeNull()
  })
})

describe('focusForContrast', () => {
  const spec = {
    measures: {
      x_first: { kind: 'expression', expr: "1 * (party == 'first')" },
      both: { kind: 'expression', expr: 'x_first * (order == other)' },
      share: { kind: 'field', field: 'share' },
    },
    estimands: [
      {
        id: 'party',
        estimator: 'fe_ols',
        terms: ['x_first', { dummies: 'order', reference: 'early' }, 'level'],
        contrasts: [
          { id: 'measure', kind: 'linear', weights: { x_first: 1 } },
          { id: 'dummy', kind: 'linear', weights: { 'order[late]': 1 } },
          { id: 'numeric', kind: 'linear', weights: { level: 1 } },
          {
            id: 'interaction',
            kind: 'linear',
            weights: { 'x_first:system[b]': 1 },
          },
          { id: 'two', kind: 'linear', weights: { x_first: 1, level: 1 } },
          { id: 'mixed', kind: 'linear', weights: { both: 1 } },
          {
            id: 'ame',
            kind: 'ame',
            column: 'party',
            level: 'second',
            reference: 'first',
          },
        ],
      },
    ],
  }
  const factors = ['party', 'order', 'level']
  const focus = (contrast: string) =>
    focusForContrast(
      spec,
      { estimand_id: 'party', contrast_id: contrast },
      factors,
    )

  it('reads the factor an expression measure compares', () => {
    expect(focus('measure')).toEqual({ factor: 'party', level: 'first' })
    expect(focus('interaction')).toEqual({ factor: 'party', level: 'first' })
  })

  it('reads dummies, factors and average marginal effects', () => {
    expect(focus('dummy')).toEqual({
      factor: 'order',
      level: 'late',
      reference: 'early',
    })
    expect(focus('numeric')).toEqual({ factor: 'level' })
    expect(focus('ame')).toEqual({
      factor: 'party',
      level: 'second',
      reference: 'first',
    })
  })

  it('says nothing when the contrast compares several factors', () => {
    expect(focus('two')).toEqual({})
    expect(focus('mixed')).toEqual({})
    expect(focus('missing')).toEqual({})
    expect(
      focusForContrast(null, { estimand_id: 'x', contrast_id: 'y' }, factors),
    ).toEqual({})
  })
})
