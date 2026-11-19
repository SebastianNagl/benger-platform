/**
 * The Analyses exhibit rule. The cases are the ones the API tests run
 * against the server rule (services/api/tests/integration/
 * test_report_analyses.py, test_exhibit_selects_exactly_the_filtered_rows),
 * so the editor's preview shows the rows the snapshot will copy.
 */

import type { AnalysisEstimate, AnalysisFit } from '@/lib/api/analysis'
import {
  type AnalysisRunDefinition,
  cleanFilters,
  estimateSystem,
  estimateSystems,
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
const OTHER = 'other-model@p3'

// The run's normalized spec and fits: model_gap has a contrast with a
// neutral label that weights the private system and a joint test whose
// parameter pattern matches both systems of its fit. The fits record the
// reference of their system dummies: OTHER for model_gap, SECRET for
// length_effect, whose terms contrasts are therefore measured against the
// private system.
const RUN: AnalysisRunDefinition = {
  normalized_spec: {
    inputs: { designs: ['framing'] },
    estimands: [
      {
        id: 'framing_effect',
        contrasts: [
          {
            id: 'loaded_vs_neutral',
            kind: 'linear',
            weights: { 'framing[loaded]': 1 },
          },
          {
            id: 'order_effect',
            kind: 'linear',
            weights: { 'order[second]': 1 },
          },
        ],
      },
      { id: 'length_effect', contrasts: 'terms' },
      {
        id: 'model_gap',
        contrasts: [
          {
            id: 'secret_vs_ref',
            kind: 'linear',
            weights: { [`system[${SECRET}]`]: 1 },
          },
        ],
        joint_tests: [{ id: 'any_system', parameters: ['system[*]'] }],
      },
    ],
  },
  fits: [
    {
      estimand: 'model_gap',
      scope: 'pooled',
      parameters: ['(intercept)', `system[${OPEN}]`, `system[${SECRET}]`],
      references: { system: OTHER },
    },
    {
      estimand: 'length_effect',
      scope: 'pooled',
      parameters: ['(intercept)', `system[${OPEN}]`, `system[${OTHER}]`],
      references: { system: SECRET },
    },
  ],
}

// position, estimand, contrast, scope values, families, kind. Involved
// systems: none for 0, 3, 5; OPEN for 1, 4, 6; SECRET for 2; the terms
// contrasts against the SECRET reference involve OTHER and SECRET (7) or
// OPEN and SECRET (8); the neutral-label contrast 9 involves SECRET
// (through its weights only) and the OTHER reference; the joint test 10
// involves OPEN, SECRET and OTHER.
const ROWS: Array<
  [number, string, string, Record<string, string> | null, string[], string]
> = [
  [0, 'framing_effect', 'loaded_vs_neutral', null, ['primary'], 'linear'],
  [
    1,
    'framing_effect',
    'loaded_vs_neutral',
    { system: OPEN },
    ['primary'],
    'linear',
  ],
  [
    2,
    'framing_effect',
    'loaded_vs_neutral',
    { system: SECRET },
    ['primary'],
    'linear',
  ],
  [
    3,
    'framing_effect',
    'order_effect',
    null,
    ['primary', 'secondary'],
    'linear',
  ],
  [
    4,
    'framing_effect',
    'order_effect',
    { system: OPEN },
    ['secondary'],
    'linear',
  ],
  [5, 'length_effect', 'long_vs_short', null, [], 'linear'],
  [
    6,
    'length_effect',
    'long_vs_short',
    { system: OPEN },
    ['secondary'],
    'linear',
  ],
  [7, 'length_effect', `system[${OTHER}]`, null, [], 'linear'],
  [8, 'length_effect', `system[${OPEN}]`, null, [], 'linear'],
  [9, 'model_gap', 'secret_vs_ref', null, [], 'linear'],
  [10, 'model_gap', 'any_system', null, [], 'wald'],
]

const scopeOf = (values: Record<string, string> | null) =>
  values
    ? Object.entries(values)
        .map(([k, v]) => `${k}=${v}`)
        .join(',')
    : 'pooled'

const estimates = ROWS.map(
  ([position, estimand, contrast, scope, families, kind]) =>
    makeEstimate({
      position,
      estimand_id: estimand,
      contrast_id: contrast,
      kind,
      scope: scopeOf(scope),
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
    [{}, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]],
    [{ estimands: ['length_effect'] }, [5, 6, 7, 8]],
    [{ contrasts: ['order_effect'] }, [3, 4]],
    [{ estimands: ['framing_effect'], contrasts: ['long_vs_short'] }, []],
    [{ families: ['secondary'] }, [3, 4, 6]],
    [{ families: ['primary', 'secondary'] }, [0, 1, 2, 3, 4, 6]],
    [{ systems: [OPEN] }, [1, 4, 6]],
    [{ systems: [OPEN, SECRET] }, [1, 2, 4, 6, 8]],
    [{ systems: [OPEN, SECRET, OTHER] }, [1, 2, 4, 6, 7, 8, 9, 10]],
    [{ systems: ['nobody'] }, []],
    [
      {
        estimands: ['framing_effect'],
        systems: [OPEN],
        families: ['primary'],
      },
      [1],
    ],
    [{ estimands: ['model_gap'] }, [9, 10]],
  ]

  it.each(cases)(
    'selects exactly the filtered rows for %j',
    (filters, expected) => {
      expect(
        estimates
          .filter((e) => exhibitSelects(e, filters, estimateSystems(e, RUN)))
          .map((e) => e.position),
      ).toEqual(expected)
    },
  )

  it('keeps contrasts of another system or reference out of a systems filter', () => {
    // A pooled terms contrast of OTHER against the reference is not a row
    // about OPEN, and neither is OPEN against the SECRET reference.
    const shown = selectEstimates(estimates, { systems: [OPEN] }, RUN).map(
      (e) => e.contrast_id,
    )
    expect(shown).not.toContain(`system[${OTHER}]`)
    expect(shown).not.toContain(`system[${OPEN}]`)
  })

  it('treats empty lists and no filters as no restriction', () => {
    expect(selectEstimates(estimates, undefined, RUN)).toHaveLength(11)
    expect(
      selectEstimates(estimates, { estimands: [], systems: [] }, RUN),
    ).toHaveLength(11)
  })

  it('reads a model_id scope as the system and skips a null contrast', () => {
    const row = makeEstimate({
      scope_values: { model_id: 'm1' },
      contrast_id: null,
    })
    const systems = estimateSystems(row, null)
    expect(estimateSystem(row)).toBe('m1')
    expect([...systems]).toEqual(['m1'])
    expect(exhibitSelects(row, { systems: ['m1'] }, systems)).toBe(true)
    expect(exhibitSelects(row, { systems: ['m2'] }, systems)).toBe(false)
    expect(exhibitSelects(row, { contrasts: ['c'] }, systems)).toBe(false)
    expect(estimateSystem(makeEstimate({ scope_values: null }))).toBeNull()
  })

  it('returns the selection in engine order', () => {
    const shuffled = [...estimates].reverse()
    expect(
      selectEstimates(shuffled, { families: ['secondary'] }, RUN).map(
        (e) => e.position,
      ),
    ).toEqual([3, 4, 6])
  })
})

describe('estimateSystems', () => {
  const FIT: AnalysisFit = {
    estimand: 'e',
    scope: 'pooled',
    parameters: [],
    references: {},
  }
  const cases: Array<
    [
      Record<string, unknown>,
      AnalysisFit[] | null,
      Partial<AnalysisEstimate>,
      string[],
    ]
  > = [
    [
      {
        id: 'e',
        contrasts: [],
        joint_tests: [
          { id: 'j', rows: [{ 'system[a@1]': 1 }, { 'x[1]:system[b@2]': 1 }] },
        ],
      },
      null,
      { contrast_id: 'j', kind: 'wald' },
      ['a@1', 'b@2'],
    ],
    [
      {
        id: 'e',
        contrasts: [{ id: 'c1', weights: { 'model_id[m]': 1 } }],
        joint_tests: [{ id: 'j', contrasts: ['c1'] }],
      },
      null,
      { contrast_id: 'j', kind: 'wald' },
      ['m'],
    ],
    [
      {
        id: 'e',
        contrasts: 'terms',
        joint_tests: [{ id: 'j', parameters: ['system[a@1]'] }],
      },
      null,
      { contrast_id: 'j', kind: 'wald' },
      ['a@1'],
    ],
    [
      {
        id: 'e',
        contrasts: [
          {
            id: 'r',
            kind: 'ratio',
            numerator: { weights: { 'system[a@1]': 1 } },
            denominator: { weights: { 'system[b@2]': 1 } },
          },
        ],
      },
      null,
      { contrast_id: 'r', kind: 'ratio' },
      ['a@1', 'b@2'],
    ],
    [
      {
        id: 'e',
        contrasts: [
          {
            id: 'm',
            kind: 'ame',
            column: 'system',
            level: 'a@1',
            reference: 'b@2',
          },
        ],
      },
      null,
      { contrast_id: 'm', kind: 'ame' },
      ['a@1', 'b@2'],
    ],
    [
      {
        id: 'e',
        contrasts: [
          {
            id: 'm',
            kind: 'ame',
            column: 'framing',
            level: 'x',
            reference: 'y',
          },
        ],
      },
      null,
      { contrast_id: 'm', kind: 'ame' },
      [],
    ],
    [
      {
        id: 'e',
        treatment: { factor: 'system', level: 'a@1', reference: 'b@2' },
        contrasts: 'terms',
      },
      null,
      { contrast_id: '(difference)', kind: 'linear' },
      ['a@1', 'b@2'],
    ],
    [
      {
        id: 'e',
        contrasts: 'terms',
        terms: [{ dummies: 'system', reference: 'd@9' }],
      },
      [{ ...FIT, references: { system: 'r@0' } }],
      { contrast_id: 'system[a@1]', kind: 'linear' },
      ['a@1', 'r@0'],
    ],
    [
      { id: 'e', contrasts: 'terms' },
      [{ ...FIT, references: { system: 'r@0', framing: 'neutral' } }],
      { contrast_id: 'framing[loaded]:system[a@1]', kind: 'linear' },
      ['a@1', 'r@0'],
    ],
    [
      { id: 'e', contrasts: 'terms' },
      [{ ...FIT, references: { system: 'r@0', framing: 'neutral' } }],
      { contrast_id: 'framing[loaded]', kind: 'linear' },
      [],
    ],
    [
      {
        id: 'e',
        contrasts: 'terms',
        terms: [{ interact: [{ dummies: 'system', reference: 'd@9' }, 'x'] }],
      },
      [{ estimand: 'e', scope: 'pooled', parameters: [] }],
      { contrast_id: 'system[a@1]:x', kind: 'linear' },
      ['a@1', 'd@9'],
    ],
    [
      { id: 'e', contrasts: 'terms', terms: [{ dummies: 'system' }] },
      null,
      { contrast_id: 'system[a@1]', kind: 'linear' },
      ['a@1'],
    ],
    [
      { id: 'e', estimator: 'bradley_terry', contrasts: 'terms' },
      [{ ...FIT, references: { strength: 'r@0' }, players_are_systems: true }],
      { contrast_id: 'strength[a@1]', kind: 'linear' },
      ['a@1', 'r@0'],
    ],
    [
      { id: 'e', estimator: 'bradley_terry', contrasts: 'terms' },
      [{ ...FIT, references: { strength: 'r@0' }, players_are_systems: false }],
      { contrast_id: 'strength[a@1]', kind: 'linear' },
      [],
    ],
  ]

  it.each(cases)('reads the spec of %j', (estimand, fits, row, expected) => {
    const estimate = makeEstimate({
      estimand_id: 'e',
      scope: 'pooled',
      scope_values: null,
      ...row,
    })
    expect(
      [
        ...estimateSystems(estimate, {
          normalized_spec: { estimands: [estimand] },
          fits,
        }),
      ].sort(),
    ).toEqual(expected)
  })
})

describe('exhibit helpers', () => {
  it('lists the values each filter can take', () => {
    expect(exhibitFilterOptions(estimates, RUN)).toEqual({
      estimands: ['framing_effect', 'length_effect', 'model_gap'],
      contrasts: [
        'loaded_vs_neutral',
        'order_effect',
        'long_vs_short',
        `system[${OTHER}]`,
        `system[${OPEN}]`,
        'secret_vs_ref',
        'any_system',
      ],
      families: ['primary', 'secondary'],
      systems: [SECRET, OPEN, OTHER],
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
