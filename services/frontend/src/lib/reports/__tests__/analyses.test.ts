/**
 * The Analyses exhibit rule. The cases are the ones the API tests run
 * against the server rule (services/api/tests/integration/
 * test_report_analyses.py, test_exhibit_selects_exactly_the_filtered_rows),
 * so the editor's preview shows the rows the snapshot will copy.
 */

import {
  cleanFilters,
  estimateSystem,
  exhibitEstimates,
  exhibitFilterOptions,
  exhibitSelects,
  newExhibitId,
  selectEstimates,
} from '@/lib/reports/analyses'
import { REPORT_ANALYSES_FIXTURE } from '@/lib/reports/fixture'
import { makeEstimate } from '@/test-utils/analysisFixtures'
import type { ReportExhibitFilters } from '@/types/report'

const OPEN = 'open-model@p1'
const SECRET = 'custom-secret-model@p2'

// position, estimand, contrast, scope values, families
const ROWS: Array<
  [number, string, string, Record<string, string> | null, string[]]
> = [
  [0, 'framing_effect', 'loaded_vs_neutral', null, ['primary']],
  [1, 'framing_effect', 'loaded_vs_neutral', { system: OPEN }, ['primary']],
  [2, 'framing_effect', 'loaded_vs_neutral', { system: SECRET }, ['primary']],
  [3, 'framing_effect', 'order_effect', null, ['primary', 'secondary']],
  [4, 'framing_effect', 'order_effect', { system: OPEN }, ['secondary']],
  [5, 'length_effect', 'long_vs_short', null, []],
  [6, 'length_effect', 'long_vs_short', { system: OPEN }, ['secondary']],
  [7, 'length_effect', `system[T.${SECRET}]`, null, []],
]

const estimates = ROWS.map(([position, estimand, contrast, scope, families]) =>
  makeEstimate({
    position,
    estimand_id: estimand,
    contrast_id: contrast,
    scope: scope ? 'system' : 'pooled',
    scope_values: scope,
    family: families[0] ?? null,
    adjustments: families.map((family) => ({
      family,
      method: 'holm',
      group: [],
      size: 4,
      p_adjusted: 0.1,
    })),
  }),
)

describe('exhibitSelects', () => {
  const cases: Array<[ReportExhibitFilters, number[]]> = [
    [{}, [0, 1, 2, 3, 4, 5, 6, 7]],
    [{ estimands: ['length_effect'] }, [5, 6, 7]],
    [{ contrasts: ['order_effect'] }, [3, 4]],
    [{ estimands: ['framing_effect'], contrasts: ['long_vs_short'] }, []],
    [{ families: ['secondary'] }, [3, 4, 6]],
    [{ families: ['primary', 'secondary'] }, [0, 1, 2, 3, 4, 6]],
    [{ systems: [OPEN] }, [0, 1, 3, 4, 5, 6, 7]],
    [{ systems: ['nobody'] }, [0, 3, 5, 7]],
    [
      {
        estimands: ['framing_effect'],
        systems: [OPEN],
        families: ['primary'],
      },
      [0, 1, 3],
    ],
  ]

  it.each(cases)(
    'selects exactly the filtered rows for %j',
    (filters, expected) => {
      expect(
        estimates
          .filter((e) => exhibitSelects(e, filters))
          .map((e) => e.position),
      ).toEqual(expected)
    },
  )

  it('treats empty lists and no filters as no restriction', () => {
    expect(selectEstimates(estimates, undefined)).toHaveLength(8)
    expect(
      selectEstimates(estimates, { estimands: [], systems: [] }),
    ).toHaveLength(8)
  })

  it('reads a model_id scope as the system and skips a null contrast', () => {
    const row = makeEstimate({
      scope_values: { model_id: 'm1' },
      contrast_id: null,
    })
    expect(estimateSystem(row)).toBe('m1')
    expect(exhibitSelects(row, { systems: ['m1'] })).toBe(true)
    expect(exhibitSelects(row, { systems: ['m2'] })).toBe(false)
    expect(exhibitSelects(row, { contrasts: ['c'] })).toBe(false)
    expect(estimateSystem(makeEstimate({ scope_values: null }))).toBeNull()
  })

  it('returns the selection in engine order', () => {
    const shuffled = [...estimates].reverse()
    expect(
      selectEstimates(shuffled, { families: ['secondary'] }).map(
        (e) => e.position,
      ),
    ).toEqual([3, 4, 6])
  })
})

describe('exhibit helpers', () => {
  it('lists the values each filter can take', () => {
    expect(exhibitFilterOptions(estimates)).toEqual({
      estimands: ['framing_effect', 'length_effect'],
      contrasts: [
        'loaded_vs_neutral',
        'order_effect',
        'long_vs_short',
        `system[T.${SECRET}]`,
      ],
      families: ['primary', 'secondary'],
      systems: [SECRET, OPEN],
    })
  })

  it('stores filters without empty lists and with sorted values', () => {
    expect(
      cleanFilters({
        systems: ['b', 'a', 'b'],
        families: [],
        estimands: undefined,
      }),
    ).toEqual({ systems: ['a', 'b'] })
    expect(cleanFilters(undefined)).toEqual({})
  })

  it('maps an exhibit to the estimates of its positions', () => {
    const [run] = REPORT_ANALYSES_FIXTURE.runs
    expect(exhibitEstimates(run, [4, 0, 99]).map((e) => e.position)).toEqual([
      4, 0,
    ])
  })

  it('picks an exhibit id that is not taken', () => {
    expect(newExhibitId([])).toBe('exhibit-1')
    expect(newExhibitId(['exhibit-2', 'exhibit-3'])).toBe('exhibit-4')
    expect(newExhibitId(['exhibit-1', 'x'])).toBe('exhibit-3')
    expect(newExhibitId(['exhibit-3', 'exhibit-1'])).toBe('exhibit-4')
  })
})
