/**
 * Interval rows from hand-made metric statistics and analysis estimates,
 * and the analysis view's filters over estimates.
 */

import { makeEstimate, makeEstimates } from '@/test-utils/analysisFixtures'
import {
  commonReference,
  contrastLabel,
  estimandsOf,
  filterEstimates,
  groupBySeries,
  intervalRowsFromEstimates,
  intervalRowsFromStatistics,
  isJointTest,
  labelsOf,
  METRIC_CI_LEVEL,
  systemOf,
  systemsOf,
  type IntervalRow,
} from '../intervalRows'

const statistics = {
  by_model: {
    'model-a': {
      model_id: 'model-a',
      model_name: 'Model A',
      metrics: {
        bleu: { mean: 0.4, ci_lower: 0.3, ci_upper: 0.5, n: 20 },
        rouge: { mean: 0.6, ci_lower: 0.55, ci_upper: 0.65, n: 20 },
      },
    },
    'model-b': {
      model_id: 'model-b',
      metrics: {
        bleu: { mean: 0.2, ci_lower: 0.1, ci_upper: 0.3, n: 18 },
      },
    },
  },
}

describe('intervalRowsFromStatistics', () => {
  it('maps every model and metric to a row with its mean and 95 % CI', () => {
    const rows = intervalRowsFromStatistics(statistics)
    expect(
      rows.map((r) => [r.series, r.label, r.estimate, r.lower, r.upper, r.n]),
    ).toEqual([
      ['bleu', 'Model A', 0.4, 0.3, 0.5, 20],
      ['bleu', 'model-b', 0.2, 0.1, 0.3, 18],
      ['rouge', 'Model A', 0.6, 0.55, 0.65, 20],
    ])
    expect(rows.every((r) => r.level === METRIC_CI_LEVEL)).toBe(true)
    expect(rows.every((r) => r.status === 'ok' && !r.emphasis)).toBe(true)
    expect(rows[0].meta).toEqual({ metric: 'bleu', modelId: 'model-a' })
    expect(new Set(rows.map((r) => r.id)).size).toBe(3)
  })

  it('restricts and orders the series and applies the labels', () => {
    const rows = intervalRowsFromStatistics(statistics, {
      metrics: ['rouge', 'bleu', 'missing'],
      metricLabel: (m) => m.toUpperCase(),
      modelLabel: (id) => `#${id}`,
    })
    expect(rows.map((r) => `${r.series}/${r.label}`)).toEqual([
      'ROUGE/#model-a',
      'BLEU/#model-a',
      'BLEU/#model-b',
    ])
  })

  it('marks a missing mean and drops non-finite bounds', () => {
    const rows = intervalRowsFromStatistics({
      by_model: {
        m: {
          metrics: {
            x: { mean: null, ci_lower: Number.NaN, ci_upper: 1, n: null },
          },
        },
      },
    })
    expect(rows[0]).toMatchObject({
      estimate: null,
      lower: null,
      upper: 1,
      n: null,
      status: 'missing',
    })
  })

  it('returns nothing without per-model statistics', () => {
    expect(intervalRowsFromStatistics(null)).toEqual([])
    expect(intervalRowsFromStatistics({ by_model: null })).toEqual([])
    expect(intervalRowsFromStatistics({})).toEqual([])
  })
})

describe('intervalRowsFromEstimates', () => {
  it('maps estimates to rows of their contrast, pooled emphasised', () => {
    const rows = intervalRowsFromEstimates(makeEstimates(), {
      pooledLabel: 'Pooled',
    })
    expect(
      rows.map((r) => [r.id, r.series, r.label, r.estimate, r.emphasis]),
    ).toEqual([
      ['0', 'role', 'Pooled', -2.5, true],
      ['1', 'role', 'system = sys_a', -6, false],
      ['2', 'role', 'system = sys_b', 0.4, false],
      ['3', 'by_system · did sys_a', 'Pooled', null, true],
    ])
    expect(rows[1]).toMatchObject({
      lower: -8,
      upper: -4,
      level: 0.95,
      n: 12,
      p: 0.0001,
      p_adjusted: 0.0002,
      family: 'per_system',
      status: 'ok',
    })
    expect(rows[1].meta).toMatchObject({
      estimandId: 'role',
      contrastId: 'role',
      nullValue: 0,
      scopeValues: { system: 'sys_a' },
    })
    expect(rows[3]).toMatchObject({ status: 'error', lower: null })
    expect(rows[3].meta.message).toBe("unknown parameter 'x_p:system[sys_a]'")
  })

  it('sorts by engine position and leaves joint tests out', () => {
    const rows = intervalRowsFromEstimates(
      [
        makeEstimate({ position: 2, estimand_id: 'b', contrast_id: null }),
        makeEstimate({ position: 1, estimand_id: 'w', kind: 'wald' }),
        makeEstimate({ position: 0, estimand_id: 'a', contrast_id: null }),
      ],
      { pooledLabel: 'P' },
    )
    expect(rows.map((r) => r.series)).toEqual(['a', 'b'])
  })
})

describe('row helpers', () => {
  const row = (series: string, label: string, nullValue?: number) =>
    ({
      id: `${series}-${label}`,
      series,
      label,
      meta: nullValue === undefined ? {} : { nullValue },
    }) as unknown as IntervalRow

  it('groups by series and lists labels in first-seen order', () => {
    const rows = [row('b', 'x'), row('a', 'y'), row('b', 'y')]
    expect(
      groupBySeries(rows).map((g) => [g.series, g.rows.map((r) => r.label)]),
    ).toEqual([
      ['b', ['x', 'y']],
      ['a', ['y']],
    ])
    expect(labelsOf(rows)).toEqual(['x', 'y'])
  })

  it('finds the common reference value', () => {
    expect(commonReference([row('a', 'x', 0), row('a', 'y', 0)])).toBe(0)
    expect(commonReference([row('a', 'x', 0), row('a', 'y', 1)])).toBeNull()
    expect(commonReference([row('a', 'x')])).toBeNull()
    expect(commonReference([row('a', 'x'), row('a', 'y', 2)])).toBe(2)
  })

  it('labels contrasts and recognises joint tests', () => {
    expect(contrastLabel({ estimand_id: 'e', contrast_id: 'e' })).toBe('e')
    expect(contrastLabel({ estimand_id: 'e', contrast_id: null })).toBe('e')
    expect(contrastLabel({ estimand_id: 'e', contrast_id: 'b - a' })).toBe(
      'e · b - a',
    )
    expect(isJointTest({ kind: 'wald' })).toBe(true)
    expect(isJointTest({ kind: 'linear' })).toBe(false)
  })
})

describe('analysis filters', () => {
  const estimates = makeEstimates()

  it('lists systems, estimands and the system of an estimate', () => {
    expect(systemsOf(estimates)).toEqual(['sys_a', 'sys_b'])
    expect(estimandsOf(estimates)).toEqual(['role', 'by_system'])
    expect(systemOf(estimates[0])).toBeNull()
    expect(systemOf(makeEstimate({ scope_values: { system: 7 } }))).toBe('7')
    expect(systemOf(makeEstimate({ scope_values: null }))).toBeNull()
  })

  it('keeps everything without a filter', () => {
    expect(
      filterEstimates(estimates, {
        systems: null,
        estimands: null,
        family: null,
      }),
    ).toHaveLength(4)
  })

  it('filters by system and always keeps estimates without one', () => {
    const kept = filterEstimates(estimates, {
      systems: ['sys_b'],
      estimands: null,
      family: null,
    })
    expect(kept.map((e) => e.position)).toEqual([0, 2, 3])
    expect(
      filterEstimates(estimates, {
        systems: [],
        estimands: null,
        family: null,
      }).map((e) => e.position),
    ).toEqual([0, 3])
  })

  it('filters by estimand and by any family membership', () => {
    expect(
      filterEstimates(estimates, {
        systems: null,
        estimands: ['by_system'],
        family: null,
      }).map((e) => e.position),
    ).toEqual([3])
    expect(
      filterEstimates(estimates, {
        systems: null,
        estimands: null,
        family: 'per_system',
      }).map((e) => e.position),
    ).toEqual([1, 2])
    const secondary = makeEstimate({
      position: 9,
      family: 'a',
      adjustments: [
        { family: 'a', method: 'holm', group: [], size: 1, p_adjusted: 1 },
        { family: 'b', method: 'bh', group: [], size: 1, p_adjusted: 1 },
      ],
    })
    expect(
      filterEstimates([secondary], {
        systems: null,
        estimands: null,
        family: 'b',
      }),
    ).toHaveLength(1)
  })

  it('combines the filters', () => {
    expect(
      filterEstimates(estimates, {
        systems: ['sys_a'],
        estimands: ['role'],
        family: 'per_system',
      }).map((e) => e.position),
    ).toEqual([1])
  })
})
