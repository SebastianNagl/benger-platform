/**
 * Pin behavior of the metric selector dropdown.
 *
 * The dropdown is ONE entry per evaluation METHOD — the project's enabled
 * `evaluation_configs`, keyed by the stable `evaluation_config.id` (issue
 * #111). Per-cell scores come from a by-task-model fetch scoped to that
 * config id, which scans ALL of the project's runs (immediate KI-Votum, the
 * hourly cron sweep, manual batch/missing-only) and unions generation-side
 * (model columns) with annotation-side (annotator columns) rows for the one
 * method. Runs NEVER mint their own dropdown entries — that split used to pin
 * the grid to a single (sometimes empty) run and render every cell N/A even
 * though the scores existed under another run.
 *
 * Regressions this catches:
 *   1. issue #111 — two configs of the same metric TYPE must stay two
 *      distinct entries (they differ only in metric_parameters/display_name).
 *   2. the n/a-grid bug — a batch/missing-only run (real model_id on a mixed
 *      project, or model_id='unknown' on a pure human project) must NOT spawn
 *      a competing entry; it just annotates the config's single entry.
 *
 * The pure-function mirror below tracks the production `availableMetricRuns`
 * reducer; a drift guard at the bottom asserts the source keeps the invariants.
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

type Cfg = { id?: string; metric?: string; display_name?: string; enabled?: boolean }

type ConfigEntry = {
  id: string
  metric: string
  configId: string
  displayName: string
  samplesEvaluated: number
  running: boolean
}

// Mirror of the (post-fix) `availableMetricRuns` reducer in
// `EvaluationResults.tsx`. Entries come from the project's enabled configs;
// runs only annotate metadata (samplesEvaluated + in-flight). Kept in sync via
// the drift guard at the bottom.
function buildConfigEntries(
  configs: Cfg[],
  runs: EvalRun[] = [],
  selectedConfigIds: string[] = [],
): ConfigEntry[] {
  const byConfig = new Map<string, ConfigEntry>()

  // One entry per enabled method.
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
      running: false,
    })
  }

  // Annotate from runs; defensively surface an orphaned canonical config id.
  const visible = (runs ?? []).filter(
    (e) => e.status === 'completed' || e.status === 'running' || e.status === 'pending',
  )
  for (const e of visible) {
    const inflight = e.status === 'running' || e.status === 'pending'
    const cfgs = Array.isArray(e.evaluation_configs) ? e.evaluation_configs : []
    for (const cfg of cfgs) {
      const rawId = cfg?.id || ''
      const metric = cfg?.metric || 'unknown'
      if (
        rawId &&
        rawId.includes('-') &&
        rawId !== metric &&
        !byConfig.has(rawId) &&
        (selectedConfigIds.length === 0 || selectedConfigIds.includes(rawId))
      ) {
        byConfig.set(rawId, {
          id: rawId,
          metric,
          configId: rawId,
          displayName: cfg?.display_name || metric || 'Unknown',
          samplesEvaluated: 0,
          running: false,
        })
      }
      const targets = byConfig.has(rawId)
        ? [byConfig.get(rawId)!]
        : Array.from(byConfig.values()).filter((x) => x.metric === metric)
      for (const entry of targets) {
        entry.samplesEvaluated = Math.max(entry.samplesEvaluated, e.samples_evaluated || 0)
        if (inflight) entry.running = true
      }
    }
  }

  return Array.from(byConfig.values())
}

describe('availableMetricRuns — one entry per enabled config (method)', () => {
  it('produces N entries for N enabled configs of distinct metrics', () => {
    // The Benchathon scenario: one run bundled 5 metrics; the project has the
    // matching 5 enabled configs → 5 selectable entries.
    const configs: Cfg[] = [
      { id: 'cfg1', metric: 'llm_judge_falloesung', display_name: 'LLM Judge', enabled: true },
      { id: 'cfg2', metric: 'rouge', display_name: 'ROUGE', enabled: true },
      { id: 'cfg3', metric: 'bleu', display_name: 'BLEU', enabled: true },
      { id: 'cfg4', metric: 'semantic_similarity', display_name: 'Semantic Similarity', enabled: true },
      { id: 'cfg5', metric: 'meteor', display_name: 'METEOR', enabled: true },
    ]
    const runs: EvalRun[] = [
      {
        evaluation_id: 'run-1',
        status: 'completed',
        samples_evaluated: 268,
        evaluation_configs: configs.map((c) => ({ metric: c.metric!, id: c.id, display_name: c.display_name })),
      },
    ]
    const result = buildConfigEntries(configs, runs)
    expect(result).toHaveLength(5)
    expect(result.map((r) => r.metric).sort()).toEqual([
      'bleu',
      'llm_judge_falloesung',
      'meteor',
      'rouge',
      'semantic_similarity',
    ])
    // Each entry picks up the run's sample count via the metadata annotation.
    for (const entry of result) {
      expect(entry.samplesEvaluated).toBe(268)
    }
  })

  // Issue #111: the headline test. Three llm_judge_falloesung configs sharing
  // the same metric type but differing in display_name/metric_parameters MUST
  // surface as three distinct, independently-selectable entries.
  it('produces N entries when N configs share the same metric type', () => {
    const configs: Cfg[] = [
      { id: 'cfg-judges-a', metric: 'llm_judge_falloesung', display_name: 'Judge lineup A (Anne+Sebastian)', enabled: true },
      { id: 'cfg-judges-b', metric: 'llm_judge_falloesung', display_name: 'Judge lineup B (Aleyna+Anne+Sebastian)', enabled: true },
      { id: 'cfg-judges-c', metric: 'llm_judge_falloesung', display_name: 'Judge lineup C (3-judge ensemble)', enabled: true },
    ]
    const result = buildConfigEntries(configs, [])
    expect(result).toHaveLength(3)
    expect(result.map((r) => r.id).sort()).toEqual(['cfg-judges-a', 'cfg-judges-b', 'cfg-judges-c'])
    expect(result.map((r) => r.displayName).sort()).toEqual([
      'Judge lineup A (Anne+Sebastian)',
      'Judge lineup B (Aleyna+Anne+Sebastian)',
      'Judge lineup C (3-judge ensemble)',
    ])
    for (const entry of result) {
      expect(entry.metric).toBe('llm_judge_falloesung')
    }
  })

  // THE n/a-grid fix. A pure human-annotator project (immediate KI-Votum runs)
  // where an org admin also fired a batch/missing-only run (model_id='unknown',
  // its own config id, 0 rows). Must be ONE entry — no competing bare-metric or
  // config-id entry pinned to the empty run.
  it('collapses immediate + a non-immediate batch run into a single entry', () => {
    const configs: Cfg[] = [
      { id: 'cfg-judge', metric: 'llm_judge_falloesung', display_name: 'Falllösung LLM Judge', enabled: true },
    ]
    const runs: EvalRun[] = [
      { evaluation_id: 'imm-1', model_id: 'immediate', status: 'completed', samples_evaluated: 1,
        evaluation_configs: [{ metric: 'llm_judge_falloesung', id: 'llm_judge_falloesung', display_name: 'Falllösung LLM Judge' }] },
      { evaluation_id: 'imm-2', model_id: 'immediate', status: 'completed', samples_evaluated: 1,
        evaluation_configs: [{ metric: 'llm_judge_falloesung', id: 'llm_judge_falloesung', display_name: 'Falllösung LLM Judge' }] },
      // org-admin missing-only run on a pure human project → model_id 'unknown', own cfg id, 0 rows
      { evaluation_id: 'batch-unknown', model_id: 'unknown', status: 'completed', samples_evaluated: 0,
        evaluation_configs: [{ metric: 'llm_judge_falloesung', id: 'cfg-judge', display_name: 'Falllösung LLM Judge' }] },
    ]
    const result = buildConfigEntries(configs, runs)
    expect(result).toHaveLength(1)
    expect(result[0].id).toBe('cfg-judge')
    expect(result[0].metric).toBe('llm_judge_falloesung')
    // No `runIds` on the entry anymore — the fetch scopes by config id, scan-all.
    expect(result[0]).not.toHaveProperty('runIds')
  })

  // The MIXED project the redesign targets: one method with both LLM-generation
  // runs (real model_id) and human-annotation immediate runs. Still ONE entry.
  it('keeps a mixed generation+annotation method as a single entry', () => {
    const configs: Cfg[] = [
      { id: 'cfg-fall', metric: 'llm_judge_falloesung', display_name: 'Falllösung LLM Judge', enabled: true },
    ]
    const runs: EvalRun[] = [
      { evaluation_id: 'gen-run', model_id: 'gpt-5', status: 'completed', samples_evaluated: 40,
        evaluation_configs: [{ metric: 'llm_judge_falloesung', id: 'cfg-fall' }] },
      { evaluation_id: 'imm-a', model_id: 'immediate', status: 'completed', samples_evaluated: 1,
        evaluation_configs: [{ metric: 'llm_judge_falloesung', id: 'llm_judge_falloesung' }] },
    ]
    const result = buildConfigEntries(configs, runs)
    expect(result).toHaveLength(1)
    expect(result[0].id).toBe('cfg-fall')
    expect(result[0].samplesEvaluated).toBe(40)
  })

  it('lists a human-graded korrektur config that has no EvaluationRun', () => {
    const configs: Cfg[] = [
      { id: 'cfg-judge', metric: 'llm_judge_falloesung', display_name: 'Falllösung LLM Judge', enabled: true },
      { id: 'cfg-korrektur', metric: 'korrektur_falloesung', display_name: 'Korrektur (Standard Falllösung)', enabled: true },
    ]
    const runs: EvalRun[] = [
      { evaluation_id: 'imm-1', model_id: 'immediate', status: 'completed', samples_evaluated: 14,
        evaluation_configs: [{ metric: 'llm_judge_falloesung', id: 'cfg-judge', display_name: 'Falllösung LLM Judge' }] },
    ]
    const result = buildConfigEntries(configs, runs)
    expect(result.find((r) => r.id === 'cfg-korrektur')).toBeTruthy()
    expect(result.find((r) => r.id === 'cfg-korrektur')!.metric).toBe('korrektur_falloesung')
    expect(result.find((r) => r.id === 'cfg-judge')).toBeTruthy()
  })

  it('marks an entry running when any of its runs is in-flight', () => {
    const configs: Cfg[] = [{ id: 'cfg-bleu', metric: 'bleu', enabled: true }]
    const runs: EvalRun[] = [
      { evaluation_id: 'r1', status: 'running', samples_evaluated: 0,
        evaluation_configs: [{ metric: 'bleu', id: 'cfg-bleu' }] },
    ]
    const result = buildConfigEntries(configs, runs)
    expect(result[0].running).toBe(true)
  })

  it('excludes disabled configs', () => {
    const configs: Cfg[] = [
      { id: 'cfg-on', metric: 'korrektur_falloesung', enabled: true },
      { id: 'cfg-off', metric: 'korrektur_custom', enabled: false },
    ]
    const result = buildConfigEntries(configs, [])
    expect(result.map((r) => r.id)).toEqual(['cfg-on'])
  })

  it('respects the page-level selectedConfigIds filter', () => {
    const configs: Cfg[] = [
      { id: 'cfg-a', metric: 'korrektur_falloesung', enabled: true },
      { id: 'cfg-b', metric: 'llm_judge_falloesung', enabled: true },
    ]
    const result = buildConfigEntries(configs, [], ['cfg-b'])
    expect(result.map((r) => r.id)).toEqual(['cfg-b'])
  })

  it('defensively surfaces an orphaned canonical config id from a run', () => {
    // A run references a full canonical config id no longer among the enabled
    // configs (wizard edit / config list failed to load) — its scores must not
    // vanish, so it appears as its own entry.
    const configs: Cfg[] = []
    const runs: EvalRun[] = [
      { evaluation_id: 'r1', model_id: 'gpt-5', status: 'completed', samples_evaluated: 12,
        evaluation_configs: [{ metric: 'bleu', id: 'bleu-mabc123-xy', display_name: 'BLEU (old)' }] },
    ]
    const result = buildConfigEntries(configs, runs)
    expect(result).toHaveLength(1)
    expect(result[0].id).toBe('bleu-mabc123-xy')
    expect(result[0].samplesEvaluated).toBe(12)
  })

  it('does NOT surface a bare-metric immediate id as an orphan entry', () => {
    // An immediate run with a bare-metric id and no matching enabled config
    // must not create a phantom entry (bare metric ids have no '-').
    const result = buildConfigEntries([], [
      { evaluation_id: 'imm', model_id: 'immediate', status: 'completed', samples_evaluated: 1,
        evaluation_configs: [{ metric: 'llm_judge_falloesung', id: 'llm_judge_falloesung' }] },
    ])
    expect(result).toHaveLength(0)
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

describe('drift guard: EvaluationResults.tsx groups by config id and scans all runs', () => {
  it('builds entries from evaluationConfigs, keyed by cfg id, with no run-id pinning', () => {
    const tsxPath = join(__dirname, '..', 'EvaluationResults.tsx')
    const src = readFileSync(tsxPath, 'utf8')

    // Entries are sourced from the project's enabled configs.
    expect(src).toMatch(/for \(const cfg of evaluationConfigs \?\? \[\]\)/)
    expect(src).toMatch(/cfg\?\.enabled === false/)
    // Grouped in a byConfig map keyed on cfg.id (issue #111).
    expect(src).toMatch(/byConfig/)
    expect(src).toMatch(/cfg\?\.id \|\| cfg\?\.metric/)
    // Runs are still walked (to annotate metadata), multi-config aware.
    expect(src).toMatch(/for \(const cfg of cfgs\)/)

    // The removed run-driven grouping MUST NOT come back: no immediate special
    // case and no `runIds` on the dropdown entries (fetch scopes by config id).
    expect(src).not.toMatch(/model_id === 'immediate'/)
    expect(src).not.toMatch(/runIds:/)
  })

  it('the task-model fetch is scoped by the selected config id, not run ids', () => {
    const hookPath = join(__dirname, '..', 'results', 'useResultsData.ts')
    const src = readFileSync(hookPath, 'utf8')
    // The hook passes a config id (not a comma-joined run-id key) to the client.
    expect(src).toMatch(/selectedConfigId/)
    expect(src).not.toMatch(/selectedRunIdsKey/)
  })
})
