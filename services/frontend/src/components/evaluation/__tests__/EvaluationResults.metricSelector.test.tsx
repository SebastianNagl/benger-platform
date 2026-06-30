/**
 * Pin behavior of the metric selector dropdown when an EvaluationRun
 * bundles multiple configs AND/OR multiple configs of the same metric
 * type exist (issue #111).
 *
 * Two regressions this catches together:
 *
 * 1. Pre-fix-A (multi-config in one run): the dropdown grouped runs by
 *    `evaluation_configs[0].metric` only, so a run dispatched with N
 *    metrics showed only 1 entry. Other (N-1) metrics' rows existed in
 *    the DB but the user couldn't navigate to them via the UI.
 *
 * 2. Pre-fix-B (issue #111 — multiple configs sharing a metric type):
 *    the dropdown grouped by `cfg.metric`, so 3 `llm_judge_falloesung`
 *    configs differing only in `metric_parameters.judges` collapsed
 *    into 1 entry. Selecting it merged scores across all 3 configs and
 *    hid the cross-config variance that the research question depends
 *    on.
 *
 * The fix groups by `cfg.id` (each evaluation_config has a unique id)
 * and labels by `cfg.display_name`. The pure-function mirror below
 * tracks the production reducer; a drift guard at the bottom asserts
 * the source file keeps both invariants.
 */
import { readFileSync } from 'fs'
import { join } from 'path'

type EvalRun = {
  evaluation_id: string
  status: string
  samples_evaluated: number | null
  model_id?: string
  evaluation_configs?: Array<{
    metric: string
    id?: string
    display_name?: string
  }>
}

type ConfigEntry = {
  id: string
  metric: string
  configId: string
  displayName: string
  samplesEvaluated: number
  runIds: string[]
}

// Mirror of the (post-fix) `availableMetricRuns` reducer in
// `EvaluationResults.tsx`. Kept in sync via the drift guard at the
// bottom. Groups by evaluation_config.id so two configs of the same
// metric type stay distinct (issue #111).
function groupRunsByConfig(runs: EvalRun[]): ConfigEntry[] {
  const completed = runs.filter((e) => e.status === 'completed')
  const byConfig = new Map<string, ConfigEntry>()
  for (const e of completed) {
    const cfgs =
      Array.isArray(e.evaluation_configs) && e.evaluation_configs.length > 0
        ? e.evaluation_configs
        : [{ metric: 'unknown', id: '', display_name: undefined } as any]
    const isImmediate = e.model_id === 'immediate'
    for (const cfg of cfgs) {
      const metric = cfg?.metric || 'unknown'
      const cfgId = isImmediate ? metric : (cfg?.id || cfg?.metric || 'unknown')
      const existing = byConfig.get(cfgId)
      if (existing) {
        if (!isImmediate && !existing.runIds.includes(e.evaluation_id)) {
          existing.runIds.push(e.evaluation_id)
        }
        existing.samplesEvaluated = Math.max(
          existing.samplesEvaluated,
          e.samples_evaluated || 0,
        )
      } else {
        byConfig.set(cfgId, {
          id: cfgId,
          metric,
          configId: cfgId,
          displayName: cfg?.display_name || metric || 'Unknown',
          samplesEvaluated: e.samples_evaluated || 0,
          runIds: isImmediate ? [] : [e.evaluation_id],
        })
      }
    }
  }
  return Array.from(byConfig.values())
}

describe('availableMetricRuns grouping (post multi-config + issue #111 fix)', () => {
  it('produces N entries for a single run bundling N configs of distinct metrics', () => {
    // The Benchathon prod scenario: 1 run with 5 different metrics.
    const runs: EvalRun[] = [
      {
        evaluation_id: 'run-1',
        status: 'completed',
        samples_evaluated: 268,
        evaluation_configs: [
          { metric: 'llm_judge_falloesung', id: 'cfg1', display_name: 'LLM Judge' },
          { metric: 'rouge', id: 'cfg2', display_name: 'ROUGE' },
          { metric: 'bleu', id: 'cfg3', display_name: 'BLEU' },
          { metric: 'semantic_similarity', id: 'cfg4', display_name: 'Semantic Similarity' },
          { metric: 'meteor', id: 'cfg5', display_name: 'METEOR' },
        ],
      },
    ]
    const result = groupRunsByConfig(runs)
    expect(result).toHaveLength(5)
    expect(result.map((r) => r.metric).sort()).toEqual([
      'bleu',
      'llm_judge_falloesung',
      'meteor',
      'rouge',
      'semantic_similarity',
    ])
    // The same run id is associated with EVERY config — the user can
    // pick any config and see the same underlying samples.
    for (const entry of result) {
      expect(entry.runIds).toEqual(['run-1'])
    }
  })

  // Issue #111: the headline test. Three llm_judge_falloesung configs
  // sharing the same metric type but differing in display_name and
  // metric_parameters MUST surface as three distinct entries.
  it('produces N entries when N configs share the same metric type', () => {
    const runs: EvalRun[] = [
      {
        evaluation_id: 'run-multi',
        status: 'completed',
        samples_evaluated: 50,
        evaluation_configs: [
          {
            metric: 'llm_judge_falloesung',
            id: 'cfg-judges-a',
            display_name: 'Judge lineup A (Anne+Sebastian)',
          },
          {
            metric: 'llm_judge_falloesung',
            id: 'cfg-judges-b',
            display_name: 'Judge lineup B (Aleyna+Anne+Sebastian)',
          },
          {
            metric: 'llm_judge_falloesung',
            id: 'cfg-judges-c',
            display_name: 'Judge lineup C (3-judge ensemble)',
          },
        ],
      },
    ]
    const result = groupRunsByConfig(runs)
    expect(result).toHaveLength(3)
    expect(result.map((r) => r.id).sort()).toEqual([
      'cfg-judges-a',
      'cfg-judges-b',
      'cfg-judges-c',
    ])
    expect(result.map((r) => r.displayName).sort()).toEqual([
      'Judge lineup A (Anne+Sebastian)',
      'Judge lineup B (Aleyna+Anne+Sebastian)',
      'Judge lineup C (3-judge ensemble)',
    ])
    // All three carry the same metric for METRIC_ORDER sort fallback.
    for (const entry of result) {
      expect(entry.metric).toBe('llm_judge_falloesung')
    }
  })

  it('still groups multiple single-config runs of the same config id', () => {
    // The "old" pattern (one run per config) must still work.
    const runs: EvalRun[] = [
      {
        evaluation_id: 'r1',
        status: 'completed',
        samples_evaluated: 50,
        evaluation_configs: [{ metric: 'bleu', id: 'cfg-bleu' }],
      },
      {
        evaluation_id: 'r2',
        status: 'completed',
        samples_evaluated: 40,
        evaluation_configs: [{ metric: 'bleu', id: 'cfg-bleu' }],
      },
    ]
    const result = groupRunsByConfig(runs)
    expect(result).toHaveLength(1)
    expect(result[0].metric).toBe('bleu')
    expect(result[0].runIds.sort()).toEqual(['r1', 'r2'])
    expect(result[0].samplesEvaluated).toBe(50)
  })

  it('does not double-count the same run under one config', () => {
    // A single run somehow has two configs with the same id — should
    // count the run once, not twice, in runIds.
    const runs: EvalRun[] = [
      {
        evaluation_id: 'rOnce',
        status: 'completed',
        samples_evaluated: 10,
        evaluation_configs: [
          { metric: 'rouge', id: 'cfg-rouge' },
          { metric: 'rouge', id: 'cfg-rouge' },
        ],
      },
    ]
    const result = groupRunsByConfig(runs)
    expect(result).toHaveLength(1)
    expect(result[0].runIds).toEqual(['rOnce'])
  })

  it('skips non-completed runs entirely', () => {
    const runs: EvalRun[] = [
      {
        evaluation_id: 'rPending',
        status: 'pending',
        samples_evaluated: 0,
        evaluation_configs: [{ metric: 'meteor', id: 'cfg-meteor' }],
      },
      {
        evaluation_id: 'rFailed',
        status: 'failed',
        samples_evaluated: 0,
        evaluation_configs: [{ metric: 'rouge', id: 'cfg-rouge' }],
      },
    ]
    expect(groupRunsByConfig(runs)).toHaveLength(0)
  })

  it('handles run with no evaluation_configs (legacy)', () => {
    const runs: EvalRun[] = [
      {
        evaluation_id: 'rLegacy',
        status: 'completed',
        samples_evaluated: 100,
        // evaluation_configs missing — legacy run record
      },
    ]
    const result = groupRunsByConfig(runs)
    expect(result).toHaveLength(1)
    expect(result[0].metric).toBe('unknown')
  })
})

// Issue #111: the composite-key dicts on StatisticsResponse moved from
// 2-part (`"model_id|metric"`) to 3-part (`"model_id|config_id|metric"`).
// Pin the parser so a regression to 2-part keys gets caught.
describe('composite key parsing for *_by_model_metric blocks', () => {
  function parseCompositeKey(key: string): {
    modelId: string
    configId: string
    metric: string
  } | null {
    const parts = key.split('|')
    if (parts.length < 3) return null
    const modelId = parts[0]
    const metric = parts[parts.length - 1]
    const configId = parts.slice(1, -1).join('|')
    return { modelId, configId, metric }
  }

  it('splits a canonical 3-part key', () => {
    expect(parseCompositeKey('gpt-4|cfg-a|bleu')).toEqual({
      modelId: 'gpt-4',
      configId: 'cfg-a',
      metric: 'bleu',
    })
  })

  it('preserves config_ids that contain a pipe (defensive)', () => {
    // The dedicated column on TaskEvaluation is a free-form string, so
    // a config id could in theory contain a pipe. The parser slices the
    // middle so model_id and metric stay correct.
    const parsed = parseCompositeKey('gpt-4|weird|cfg|name|bleu')
    expect(parsed).toEqual({
      modelId: 'gpt-4',
      configId: 'weird|cfg|name',
      metric: 'bleu',
    })
  })

  it('returns null for legacy 2-part keys (so callers can fall back)', () => {
    expect(parseCompositeKey('gpt-4|bleu')).toBeNull()
  })

  it('returns null for malformed inputs', () => {
    expect(parseCompositeKey('')).toBeNull()
    expect(parseCompositeKey('only-one-part')).toBeNull()
  })
})

// Human-eval methods (korrektur_*) are graded by a person, not by a normal
// EvaluationRun, so their grades never appear in `results.evaluations`. The
// dropdown must still list them — sourced from the project's enabled
// `evaluation_configs` — with empty `runIds` so the by-task-model fetch sends
// only `?metric=` and the backend scans all project runs by metric key.
type Cfg = { id?: string; metric?: string; display_name?: string; enabled?: boolean }

// Mirror of the config-merge step appended to `availableMetricRuns` in
// EvaluationResults.tsx. Kept in sync via the drift guard below.
function mergeEnabledConfigs(
  entries: ConfigEntry[],
  configs: Cfg[],
  selectedConfigIds: string[] = [],
): ConfigEntry[] {
  const byConfig = new Map(entries.map((e) => [e.id, e]))
  for (const cfg of configs ?? []) {
    if (cfg?.enabled === false) continue
    const cfgId = cfg?.id || cfg?.metric
    if (!cfgId || byConfig.has(cfgId)) continue
    if (selectedConfigIds.length > 0 && !selectedConfigIds.includes(cfgId)) continue
    byConfig.set(cfgId, {
      id: cfgId,
      metric: cfg?.metric || 'unknown',
      configId: cfgId,
      displayName: cfg?.display_name || cfg?.metric || 'Unknown',
      samplesEvaluated: 0,
      runIds: [],
    })
  }
  return Array.from(byConfig.values())
}

describe('availableMetricRuns surfaces enabled configs without a run (human eval)', () => {
  it('lists a human-graded korrektur config that has no EvaluationRun', () => {
    // The Probeklausur prod scenario: llm_judge has immediate runs, the human
    // korrektur method is configured + enabled but its grades are not an
    // EvaluationRun, so it is absent from `results.evaluations`.
    const runs: EvalRun[] = [
      {
        evaluation_id: 'imm-1',
        status: 'completed',
        samples_evaluated: 14,
        evaluation_configs: [
          { metric: 'llm_judge_falloesung', id: 'cfg-judge', display_name: 'Falllösung LLM Judge' },
        ],
      },
    ]
    const configs: Cfg[] = [
      { id: 'cfg-judge', metric: 'llm_judge_falloesung', display_name: 'Falllösung LLM Judge', enabled: true },
      { id: 'cfg-korrektur', metric: 'korrektur_falloesung', display_name: 'Korrektur (Standard Falllösung)', enabled: true },
    ]
    const result = mergeEnabledConfigs(groupRunsByConfig(runs), configs)
    const korrektur = result.find((r) => r.id === 'cfg-korrektur')
    expect(korrektur).toBeTruthy()
    expect(korrektur!.metric).toBe('korrektur_falloesung')
    // Empty runIds → the fetch sends only `?metric=`, backend scans all runs.
    expect(korrektur!.runIds).toEqual([])
    // The run-backed automated entry keeps its run id.
    expect(result.find((r) => r.id === 'cfg-judge')!.runIds).toEqual(['imm-1'])
  })

  it('does not overwrite a config that already has runs', () => {
    const runs: EvalRun[] = [
      {
        evaluation_id: 'r1',
        status: 'completed',
        samples_evaluated: 10,
        evaluation_configs: [{ metric: 'bleu', id: 'cfg-bleu' }],
      },
    ]
    const configs: Cfg[] = [{ id: 'cfg-bleu', metric: 'bleu', enabled: true }]
    const result = mergeEnabledConfigs(groupRunsByConfig(runs), configs)
    expect(result).toHaveLength(1)
    expect(result[0].runIds).toEqual(['r1']) // not reset to []
  })

  it('excludes disabled configs', () => {
    const configs: Cfg[] = [
      { id: 'cfg-on', metric: 'korrektur_falloesung', enabled: true },
      { id: 'cfg-off', metric: 'korrektur_custom', enabled: false },
    ]
    const result = mergeEnabledConfigs([], configs)
    expect(result.map((r) => r.id)).toEqual(['cfg-on'])
  })

  it('respects the page-level selectedConfigIds filter', () => {
    const configs: Cfg[] = [
      { id: 'cfg-a', metric: 'korrektur_falloesung', enabled: true },
      { id: 'cfg-b', metric: 'llm_judge_falloesung', enabled: true },
    ]
    const result = mergeEnabledConfigs([], configs, ['cfg-b'])
    expect(result.map((r) => r.id)).toEqual(['cfg-b'])
  })
})

// The Probeklausur prod regression: per-annotation immediate ("KI-Votum")
// runs are one EvaluationRun per annotation. The same metric's runs carried
// inconsistent config ids (graded runs a bare metric id, empty-submission
// runs a full `<metric>-<hash>` id), splitting one metric into two same-named
// dropdown entries — and the empty-runs group pinned by-task-model to
// grade-less runs, rendering every annotator N/A. Immediate runs must collapse
// under the metric name with EMPTY runIds (so the fetch sends only `?metric=`).
describe('availableMetricRuns collapses per-annotation immediate runs', () => {
  it('merges immediate runs under the metric with empty runIds despite inconsistent config ids', () => {
    const runs: EvalRun[] = [
      {
        evaluation_id: 'graded-1', model_id: 'immediate', status: 'completed', samples_evaluated: 1,
        evaluation_configs: [{ metric: 'llm_judge_falloesung', id: 'llm_judge_falloesung', display_name: 'Falllösung LLM Judge' }],
      },
      {
        evaluation_id: 'graded-2', model_id: 'immediate', status: 'completed', samples_evaluated: 1,
        evaluation_configs: [{ metric: 'llm_judge_falloesung', id: 'llm_judge_falloesung', display_name: 'Falllösung LLM Judge' }],
      },
      {
        evaluation_id: 'empty-1', model_id: 'immediate', status: 'completed', samples_evaluated: 0,
        evaluation_configs: [{ metric: 'llm_judge_falloesung', id: 'llm_judge_falloesung-mqs141q8-o2oh', display_name: 'Falllösung LLM Judge' }],
      },
    ]
    const result = groupRunsByConfig(runs)
    // One entry keyed by metric — NOT split by the inconsistent config ids.
    expect(result).toHaveLength(1)
    expect(result[0].id).toBe('llm_judge_falloesung')
    expect(result[0].metric).toBe('llm_judge_falloesung')
    // Empty runIds → by-task-model sends only `?metric=` and scans every run,
    // so every annotator's grade surfaces instead of all-N/A.
    expect(result[0].runIds).toEqual([])
  })

  it('leaves non-immediate (model-comparison) runs pinned to their run ids', () => {
    const runs: EvalRun[] = [
      {
        evaluation_id: 'r1', model_id: 'gpt-5', status: 'completed', samples_evaluated: 10,
        evaluation_configs: [{ metric: 'llm_judge_falloesung', id: 'cfg-judge' }],
      },
    ]
    const result = groupRunsByConfig(runs)
    expect(result[0].id).toBe('cfg-judge')
    expect(result[0].runIds).toEqual(['r1'])
  })
})

describe('drift guard: EvaluationResults.tsx still iterates all configs and groups by id', () => {
  it('source file walks evaluation_configs in a for-of, not [0]', () => {
    const tsxPath = join(__dirname, '..', 'EvaluationResults.tsx')
    const src = readFileSync(tsxPath, 'utf8')
    // Multi-config iteration must be present in the metric grouping.
    expect(src).toMatch(/for \(const cfg of cfgs\)/)
    // The config-merge step (surfaces human-eval configs) must be present:
    // a for-of over evaluationConfigs that skips disabled ones.
    expect(src).toMatch(/for \(const cfg of evaluationConfigs \?\? \[\]\)/)
    expect(src).toMatch(/cfg\?\.enabled === false/)
    // The pre-fix shortcut MUST NOT come back. We allow `evaluation_configs?.[0]`
    // elsewhere in the file (other components legitimately read the
    // first config), but the metric-grouping `useMemo` must use the
    // multi-config form. As a coarse but reliable check: the file must
    // contain BOTH the array-or-fallback expression and the for-of iteration.
    expect(src).toMatch(
      /Array\.isArray\(e\.evaluation_configs\) && e\.evaluation_configs\.length > 0/,
    )
    // Issue #111: grouping moves from `byMetric` to `byConfig` keyed on
    // cfg.id. The presence of `byConfig` and a key derived from cfg.id
    // catches accidental reverts to the per-metric grouping.
    expect(src).toMatch(/byConfig/)
    expect(src).toMatch(/cfg\?\.id \|\| cfg\?\.metric \|\| 'unknown'/)
  })
})
