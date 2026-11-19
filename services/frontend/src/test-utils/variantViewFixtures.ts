/**
 * Invented variant units, request records and estimates for the variant and
 * analysis view tests, in the shapes the API writes.
 */

import type { AnalysisEstimate, AnalysisRun } from '@/lib/api/analysis'
import type {
  TrialRequestView,
  UnitGeneration,
  UnitTask,
  UnitView,
  VariantDesignRow,
} from '@/lib/api/variantViews'
import { makeEstimate, makeRun } from './analysisFixtures'

export const SYSTEM_A = 'sim-alpha@aaaaaaaaaaaa'
export const SYSTEM_B = 'sim-beta@bbbbbbbbbbbb'

const NAMES: Record<string, string> = {
  first: 'Ida Brook',
  second: 'Olaf Penn',
}

export function caseText(party: string): {
  text: string
  spans: [number, number][]
} {
  const name = NAMES[party] ?? party
  const text = `The tenant ${name} asks for the deposit back.`
  const at = text.indexOf(name)
  return { text, spans: [[at, at + name.length]] }
}

export function makeGeneration(
  overrides: Partial<UnitGeneration> = {},
): UnitGeneration {
  return {
    id: 'gen-1',
    parent_id: 'run-1',
    model_id: 'sim-alpha',
    system_key: SYSTEM_A,
    structure_key: 'default',
    run_index: 0,
    status: 'completed',
    response: '{"share": 40}',
    response_truncated: false,
    fields: { share: 40 },
    parse_status: 'success',
    refusal: false,
    truncated: false,
    finish_reason: 'stop',
    retried: false,
    has_request_record: true,
    request_sha256: 'ab'.repeat(32),
    created_at: '2026-11-19T00:00:00+00:00',
    ...overrides,
  }
}

function unitTask(
  id: string,
  party: string,
  order: string,
  generations: UnitGeneration[],
): UnitTask {
  const { text, spans } = caseText(party)
  return {
    id,
    inner_id: Number(id.replace(/\D/g, '')) || null,
    factors: { party, order, level: 2 },
    texts: [
      { path: 'facts', kind: 'spanned', text, truncated: false, spans },
      {
        path: 'reference',
        kind: 'free',
        text: '41',
        truncated: false,
        spans: [],
      },
    ],
    gold: [{ name: 'reference', path: 'reference', value: 41 }],
    generations,
  }
}

/** A unit of a two-factor design (party x order), every task answered once. */
export function makeUnitView(overrides: Partial<UnitView> = {}): UnitView {
  const tasks = [
    unitTask('t1', 'first', 'early', [makeGeneration({ id: 'g1' })]),
    unitTask('t2', 'second', 'early', [
      makeGeneration({
        id: 'g2',
        has_request_record: false,
        request_sha256: null,
      }),
    ]),
    unitTask('t3', 'first', 'late', [makeGeneration({ id: 'g3' })]),
    unitTask('t4', 'second', 'late', [makeGeneration({ id: 'g4' })]),
  ]
  return {
    project_id: 'p1',
    design: {
      key: 'swap',
      version: 1,
      status: 'frozen',
      content_hash: 'c'.repeat(64),
      frozen_at: null,
      unit_name: 'case',
      factors: [
        { name: 'party', type: 'nominal', levels: ['first', 'second'] },
        {
          name: 'order',
          type: 'nominal',
          levels: ['early', 'late'],
          role: 'counterbalanced',
        },
        { name: 'level', type: 'numeric', varies: 'between_units' },
      ],
      invariance: { fields: ['facts'], free: ['reference'] },
    },
    unit: 'u1',
    system: SYSTEM_A,
    systems: [SYSTEM_A, SYSTEM_B],
    tasks,
    tasks_truncated: false,
    check: {
      ok: true,
      task_count: 4,
      assignments: { ok: true, problem_count: 0, problems: [] },
      balance: { ok: true, problem_count: 0, problems: [] },
      invariance: { ok: true, problem_count: 0, problems: [] },
    },
    ...overrides,
  }
}

export function makeDesignRow(
  overrides: Partial<VariantDesignRow> = {},
): VariantDesignRow {
  return {
    id: 'd1',
    project_id: 'p1',
    key: 'swap',
    version: 2,
    status: 'frozen',
    spec: {
      title: 'Name swap',
      unit: { name: 'case' },
      factors: [
        { name: 'party', type: 'nominal', levels: ['first', 'second'] },
        {
          name: 'level',
          type: 'numeric',
          minimum: 0,
          maximum: 100,
          varies: 'between_units',
        },
      ],
      gold: [{ name: 'reference', path: 'reference' }],
      invariance: { fields: ['facts'], free: ['reference'] },
    },
    spec_sha256: 's'.repeat(64),
    content_hash: 'c'.repeat(64),
    frozen_at: '2026-11-19T00:00:00+00:00',
    task_count: 48,
    ...overrides,
  }
}

export function makeTrialRequest(
  overrides: Partial<TrialRequestView> = {},
): TrialRequestView {
  return {
    id: 'g1',
    run_index: 0,
    request_record: {
      version: 1,
      provider: 'openai',
      api: 'chat.completions',
      capture: 'http_body',
      model: 'sim-alpha',
      messages: [
        { role: 'system', content: 'Answer with a number.' },
        { role: 'user', content: caseText('first').text },
      ],
      response_format: { type: 'json_object' },
      parameters: { temperature: 0 },
      requests: [{ body: { model: 'sim-alpha' } }],
    },
    request_sha256: 'ab'.repeat(32),
    computed_sha256: 'ab'.repeat(32),
    hash_matches: true,
    parent_id: 'run-1',
    task_id: 't1',
    model_id: 'sim-alpha',
    system_key: SYSTEM_A,
    structure_key: 'default',
    retried: false,
    first_response: null,
    first_response_truncated: false,
    ...overrides,
  }
}

/**
 * A per-slot run: a mean per position (1-4) for two systems in two groups,
 * rising by 0.5 per position, plus the pooled slope of a linear contrast on
 * the position.
 */
export function makePositionEstimates(): AnalysisEstimate[] {
  const out: AnalysisEstimate[] = []
  let position = 0
  for (const [system, offset] of [
    [SYSTEM_A, 1],
    [SYSTEM_B, 2],
  ] as const) {
    for (const group of ['g1', 'g2']) {
      for (const pos of [1, 2, 3, 4]) {
        const estimate = offset + 0.5 * pos + (group === 'g2' ? 0.25 : 0)
        out.push(
          makeEstimate({
            position: position++,
            estimand_id: 'mean_by_position',
            contrast_id: '(mean)',
            estimator: 'mean_rate',
            outcome: 'risk',
            scope: `by system, group, pos`,
            scope_values: { system, group, pos },
            estimate,
            ci_lower: estimate - 0.2,
            ci_upper: estimate + 0.2,
            null_value: null,
            n_obs: 20,
          }),
        )
      }
    }
  }
  out.push(
    makeEstimate({
      position: position++,
      estimand_id: 'position',
      contrast_id: 'per position',
      outcome: 'risk',
      scope: 'pooled',
      scope_values: {},
      estimate: 0.5,
      ci_lower: 0.4,
      ci_upper: 0.6,
    }),
  )
  return out
}

export function makePositionRun(): AnalysisRun {
  return makeRun({
    normalized_spec: {
      spec_version: 1,
      inputs: { designs: ['roster'] },
      frame: { unit: 'slot' },
      estimands: [
        {
          id: 'mean_by_position',
          estimator: 'mean_rate',
          outcome: 'risk',
          scopes: [{ by: ['system', 'group', 'pos'] }],
          contrasts: 'terms',
        },
        {
          id: 'position',
          estimator: 'fe_ols',
          outcome: 'risk',
          terms: ['pos'],
          scopes: ['pooled'],
          contrasts: [
            {
              id: 'per position',
              kind: 'linear',
              weights: { pos: 1 },
              null: 0,
            },
          ],
        },
      ],
    },
  })
}

/**
 * The gap of party b against a per position (an fe_ols coefficient scoped
 * by position), flat at zero, next to the position run's level slope.
 */
export function makeGapEstimates(): AnalysisEstimate[] {
  return [1, 2, 3, 4].map((pos, i) =>
    makeEstimate({
      position: 100 + i,
      estimand_id: 'party_gap',
      contrast_id: 'party b',
      estimator: 'fe_ols',
      outcome: 'risk',
      scope: 'by pos',
      scope_values: { pos },
      estimate: 0,
      ci_lower: -0.1,
      ci_upper: 0.1,
    }),
  )
}

const PARTY = { dummies: 'party', reference: 'a' }

/**
 * A run with a party by position interaction: the mean per party and
 * position, and an fe_ols fit whose slope of position is 0.2 for party a
 * (the reference) and 0.2 + 0.7 for party b. The interaction column is
 * named as the engine names `{interact: ["pos", party]}`: `pos:party[b]`.
 */
export function makeInteractionRun(): AnalysisRun {
  return makeRun({
    normalized_spec: {
      spec_version: 1,
      estimands: [
        {
          id: 'mean_by_party',
          estimator: 'mean_rate',
          outcome: 'risk',
          scopes: [{ by: ['party', 'pos'] }],
          contrasts: 'terms',
        },
        {
          id: 'slopes',
          estimator: 'fe_ols',
          outcome: 'risk',
          terms: ['pos', PARTY, { interact: ['pos', PARTY] }],
          scopes: ['pooled'],
          contrasts: [
            { id: 'slope a', kind: 'linear', weights: { pos: 1 } },
            {
              id: 'slope b',
              kind: 'linear',
              weights: { pos: 1, 'pos:party[b]': 1 },
            },
            { id: 'gap slope', kind: 'linear', weights: { 'pos:party[b]': 1 } },
          ],
        },
      ],
    },
  })
}

export function makeInteractionEstimates(): AnalysisEstimate[] {
  const out: AnalysisEstimate[] = []
  for (const [party, slope] of [
    ['a', 0.2],
    ['b', 0.9],
  ] as const) {
    for (const pos of [1, 2, 3]) {
      out.push(
        makeEstimate({
          position: out.length,
          estimand_id: 'mean_by_party',
          contrast_id: '(mean)',
          estimator: 'mean_rate',
          outcome: 'risk',
          scope: 'by party, pos',
          scope_values: { party, pos },
          estimate: 1 + slope * pos,
          null_value: null,
        }),
      )
    }
  }
  for (const [id, estimate] of [
    ['slope a', 0.2],
    ['slope b', 0.9],
    ['gap slope', 0.7],
  ] as const) {
    out.push(
      makeEstimate({
        position: out.length,
        estimand_id: 'slopes',
        contrast_id: id,
        outcome: 'risk',
        scope: 'pooled',
        scope_values: {},
        estimate,
        ci_lower: estimate - 0.1,
        ci_upper: estimate + 0.1,
      }),
    )
  }
  return out
}

/** Bradley-Terry strengths of players b and c against a, pooled and per system. */
export function makeStrengthEstimates(): AnalysisEstimate[] {
  const rows: AnalysisEstimate[] = []
  let position = 0
  for (const [scope, values, shift] of [
    ['pooled', {}, 0],
    ['by system', { system: SYSTEM_A }, 0.3],
    ['by system', { system: SYSTEM_B }, -0.3],
  ] as const) {
    for (const [level, value] of [
      ['b', 0.8],
      ['c', -0.4],
    ] as const) {
      rows.push(
        makeEstimate({
          position: position++,
          estimand_id: 'pairs',
          contrast_id: `strength[${level}]`,
          estimator: 'bradley_terry',
          outcome: 'won',
          scope: scope === 'pooled' ? 'pooled' : `system=${values.system}`,
          scope_values: values,
          estimate: value + shift,
          ci_lower: value + shift - 0.3,
          ci_upper: value + shift + 0.3,
        }),
      )
    }
  }
  return rows
}

export function makeStrengthRun(): AnalysisRun {
  return makeRun({
    normalized_spec: {
      spec_version: 1,
      inputs: { designs: ['pairs'] },
      estimands: [
        {
          id: 'pairs',
          estimator: 'bradley_terry',
          outcome: 'won',
          players: ['left', 'right'],
          reference: 'a',
          link: 'logit',
        },
      ],
    },
  })
}
