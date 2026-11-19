/**
 * The pure helpers of the analysis results page: formatting, grouping
 * estimates into contrasts, equivalence bands, families and axis ticks.
 * Every expected value is hand-computed from the invented inputs.
 */

import {
  axisTicks,
  commonNullValue,
  contrastKey,
  equivalenceBands,
  familiesOf,
  formatInterval,
  formatLevel,
  formatNumber,
  formatP,
  groupByContrast,
  inFamily,
  MISSING,
  scopeDescription,
  shortHash,
  tostFor,
} from '@/lib/analysis/results'
import { makeEstimate as estimate } from '@/test-utils/analysisFixtures'

describe('formatNumber', () => {
  it('keeps four significant digits in the locale', () => {
    expect(formatNumber(-4.728991596638656, 'en')).toBe('-4.729')
    expect(formatNumber(-4.728991596638656, 'de')).toBe('-4,729')
    expect(formatNumber(12.0859375, 'en')).toBe('12.09')
    expect(formatNumber(0.264056674863263, 'en')).toBe('0.2641')
  })

  it('switches to scientific notation for very small and large values', () => {
    expect(formatNumber(0.0000123, 'en')).toBe('1.23E-5')
    expect(formatNumber(2500000, 'en')).toBe('2.5E6')
  })

  it('shows zero and missing values plainly', () => {
    expect(formatNumber(0, 'en')).toBe('0')
    expect(formatNumber(null, 'en')).toBe(MISSING)
    expect(formatNumber(Number.NaN, 'en')).toBe(MISSING)
    expect(formatNumber(undefined, 'en')).toBe(MISSING)
  })
})

describe('formatP', () => {
  it('uses three decimals from 0.001 on', () => {
    expect(formatP(0.035771022248036584, 'en')).toBe('0.036')
    expect(formatP(0.29483039730333405, 'de')).toBe('0,295')
    expect(formatP(1, 'en')).toBe('1.000')
  })

  it('uses scientific notation below 0.001', () => {
    expect(formatP(3.6722255476159427e-16, 'en')).toBe('3.7E-16')
    expect(formatP(0.00033881731598338376, 'de')).toBe('3,4E-4')
  })

  it('handles zero and missing values', () => {
    expect(formatP(0, 'en')).toBe('0')
    expect(formatP(null, 'en')).toBe(MISSING)
  })
})

describe('formatInterval, formatLevel, shortHash', () => {
  it('formats a closed interval or the placeholder', () => {
    expect(formatInterval(-5.85489725833395, -3.603085934943363, 'en')).toBe(
      '[-5.855, -3.603]',
    )
    expect(formatInterval(null, 1, 'en')).toBe(MISSING)
  })

  it('formats a level as a percentage', () => {
    expect(formatLevel(0.95, 'en')).toBe('95%')
    expect(formatLevel(0.9, 'de')).toBe('90\u00a0%')
    expect(formatLevel(null, 'en')).toBe(MISSING)
  })

  it('shortens a digest to 12 characters', () => {
    expect(shortHash('e8b39e3aff6d9c532c85baca77dc4d16')).toBe('e8b39e3aff6d')
    expect(shortHash('abc')).toBe('abc')
    expect(shortHash(null)).toBe(MISSING)
  })
})

describe('scopeDescription', () => {
  it('is null for the pooled fit', () => {
    expect(scopeDescription({ scope: 'pooled', scope_values: {} })).toBeNull()
  })

  it('lists the scope columns and values', () => {
    expect(
      scopeDescription({
        scope: 'system=sys_a@000000000000',
        scope_values: { system: 'sys_a@000000000000' },
      }),
    ).toBe('system = sys_a@000000000000')
    expect(
      scopeDescription({
        scope: 'system=a,first=P',
        scope_values: { system: 'a', first: 'P' },
      }),
    ).toBe('system = a, first = P')
  })

  it('falls back to the scope string without values', () => {
    expect(scopeDescription({ scope: 'system=a', scope_values: null })).toBe(
      'system=a',
    )
  })
})

describe('groupByContrast', () => {
  it('groups by estimand and contrast in engine order', () => {
    const rows = [
      estimate({ position: 2, scope: 'system=a' }),
      estimate({ position: 1, contrast_id: 'order' }),
      estimate({ position: 0 }),
      estimate({ position: 3, estimand_id: 'slope', contrast_id: 'slope' }),
    ]
    const groups = groupByContrast(rows)
    expect(groups.map((g) => [g.estimandId, g.contrastId])).toEqual([
      ['role', 'role'],
      ['role', 'order'],
      ['slope', 'slope'],
    ])
    expect(groups[0].estimates.map((e) => e.position)).toEqual([0, 2])
    expect(groups[0].key).toBe(contrastKey(rows[0]))
  })

  it('keeps a contrast id equal to another estimand apart', () => {
    const groups = groupByContrast([
      estimate({ position: 0, estimand_id: 'a', contrast_id: 'b' }),
      estimate({ position: 1, estimand_id: 'a\u0000b', contrast_id: null }),
    ])
    expect(groups).toHaveLength(2)
  })
})

describe('equivalence bands', () => {
  const tost = [
    {
      lower: -3,
      upper: 3,
      level: 0.9,
      ci_lower: -5.67,
      ci_upper: -3.78,
      p_lower: 0.99,
      p_upper: 0,
      p_tost: 0.99,
      equivalent: false,
    },
    {
      lower: -2,
      upper: 2,
      level: 0.9,
      ci_lower: -5.67,
      ci_upper: -3.78,
      p_lower: 1,
      p_upper: 0,
      p_tost: 1,
      equivalent: false,
    },
  ]

  it('lists the bound sets of the first estimate that carries them', () => {
    const rows = [
      estimate({ position: 0, status: 'error', tost: null }),
      estimate({ position: 1, tost }),
    ]
    expect(equivalenceBands(rows)).toEqual([
      { index: 0, lower: -3, upper: 3, level: 0.9 },
      { index: 1, lower: -2, upper: 2, level: 0.9 },
    ])
  })

  it('is empty without any TOST', () => {
    expect(equivalenceBands([estimate()])).toEqual([])
  })

  it('reads one bound set of an estimate', () => {
    expect(tostFor(estimate({ tost }), 1)?.lower).toBe(-2)
    expect(tostFor(estimate({ tost }), 5)).toBeNull()
    expect(tostFor(estimate(), 0)).toBeNull()
  })
})

describe('commonNullValue', () => {
  it('returns the shared null value or null when they differ', () => {
    expect(commonNullValue([estimate(), estimate({ position: 1 })])).toBe(0)
    expect(
      commonNullValue([estimate(), estimate({ position: 1, null_value: 1 })]),
    ).toBeNull()
    expect(commonNullValue([estimate({ null_value: null })])).toBeNull()
  })
})

describe('families', () => {
  const rows = [
    estimate({
      family: 'primary',
      p_adjusted: 0.03,
      adjustments: [
        {
          family: 'primary',
          method: 'holm',
          group: [],
          size: 3,
          p_adjusted: 0.03,
        },
        {
          family: 'all',
          method: 'bonferroni',
          group: [],
          size: 9,
          p_adjusted: 0.09,
        },
      ],
    }),
    estimate({ position: 1 }),
  ]

  it('collects every family id, also later memberships', () => {
    expect(familiesOf(rows)).toEqual(['all', 'primary'])
  })

  it('matches an estimate by any membership', () => {
    expect(inFamily(rows[0], 'all')).toBe(true)
    expect(inFamily(rows[0], 'primary')).toBe(true)
    expect(inFamily(rows[1], 'primary')).toBe(false)
  })
})

describe('axisTicks', () => {
  it('covers the values with nice steps', () => {
    expect(axisTicks([-5.85, -3.6, 0, 3])).toEqual({
      min: -6,
      max: 4,
      ticks: [-6, -4, -2, 0, 2, 4],
    })
    expect(axisTicks([0.21, 0.63])).toEqual({
      min: 0.2,
      max: 0.7,
      ticks: [0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
    })
  })

  it('widens a single value and ignores missing ones', () => {
    expect(axisTicks([2, null, Number.NaN, 2])).toEqual({
      min: 1,
      max: 3,
      ticks: [1, 1.5, 2, 2.5, 3],
    })
    expect(axisTicks([0])).toEqual({
      min: -1,
      max: 1,
      ticks: [-1, -0.5, 0, 0.5, 1],
    })
    expect(axisTicks([])).toEqual({ min: -1, max: 1, ticks: [-1, 0, 1] })
  })
})
