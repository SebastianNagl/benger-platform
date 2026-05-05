/**
 * Pin behavior of the metric selector dropdown when an EvaluationRun
 * bundles multiple configs.
 *
 * The bug this catches: pre-fix, the dropdown grouped runs by
 * `evaluation_configs[0].metric` only, so a run dispatched with
 * 5 metrics (legitimate via the API's /run endpoint and the worker's
 * Celery task signature) showed only 1 entry in the selector. The
 * other 4 metrics' rows existed in the DB but the user couldn't
 * navigate to them via the UI.
 *
 * Test approach: extract the same grouping logic the component uses
 * into a pure function and exercise it with multi-config inputs.
 * If the production component is refactored to use the helper directly
 * the drift guard at the bottom catches that the multi-config branch
 * stays in EvaluationResults.tsx.
 */
import { readFileSync } from 'fs'
import { join } from 'path'

type EvalRun = {
  evaluation_id: string
  status: string
  samples_evaluated: number | null
  evaluation_configs?: Array<{
    metric: string
    id?: string
    display_name?: string
  }>
}

type MetricEntry = {
  id: string
  metric: string
  configId: string
  displayName: string
  samplesEvaluated: number
  runIds: string[]
}

// Mirror of the (post-fix) `availableMetricRuns` reducer in
// `EvaluationResults.tsx:197-246`. Kept in sync via the drift guard
// at the bottom of this file.
function groupRunsByMetric(runs: EvalRun[]): MetricEntry[] {
  const completed = runs.filter((e) => e.status === 'completed')
  const byMetric = new Map<string, MetricEntry>()
  for (const e of completed) {
    const cfgs =
      Array.isArray(e.evaluation_configs) && e.evaluation_configs.length > 0
        ? e.evaluation_configs
        : [{ metric: 'unknown', id: '', display_name: undefined } as any]
    for (const cfg of cfgs) {
      const metric = cfg?.metric || 'unknown'
      const existing = byMetric.get(metric)
      if (existing) {
        if (!existing.runIds.includes(e.evaluation_id)) {
          existing.runIds.push(e.evaluation_id)
        }
        existing.samplesEvaluated = Math.max(
          existing.samplesEvaluated,
          e.samples_evaluated || 0,
        )
      } else {
        byMetric.set(metric, {
          id: metric,
          metric,
          configId: cfg?.id || '',
          displayName: cfg?.display_name || metric || 'Unknown',
          samplesEvaluated: e.samples_evaluated || 0,
          runIds: [e.evaluation_id],
        })
      }
    }
  }
  return Array.from(byMetric.values())
}

describe('availableMetricRuns grouping (post multi-config fix)', () => {
  it('produces N entries for a single run bundling N metrics', () => {
    // The actual prod scenario: 1 run with all 5 Benchathon metrics.
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
    const result = groupRunsByMetric(runs)
    expect(result).toHaveLength(5)
    expect(result.map((r) => r.metric).sort()).toEqual([
      'bleu',
      'llm_judge_falloesung',
      'meteor',
      'rouge',
      'semantic_similarity',
    ])
    // The same run id is associated with EVERY metric — the user can
    // pick any metric and see the same underlying samples.
    for (const entry of result) {
      expect(entry.runIds).toEqual(['run-1'])
    }
  })

  it('still groups multiple single-metric runs of the same metric', () => {
    // The "old" pattern (one run per metric) must still work.
    const runs: EvalRun[] = [
      {
        evaluation_id: 'r1',
        status: 'completed',
        samples_evaluated: 50,
        evaluation_configs: [{ metric: 'bleu' }],
      },
      {
        evaluation_id: 'r2',
        status: 'completed',
        samples_evaluated: 40,
        evaluation_configs: [{ metric: 'bleu' }],
      },
    ]
    const result = groupRunsByMetric(runs)
    expect(result).toHaveLength(1)
    expect(result[0].metric).toBe('bleu')
    expect(result[0].runIds.sort()).toEqual(['r1', 'r2'])
    // samplesEvaluated keeps the max across the two runs.
    expect(result[0].samplesEvaluated).toBe(50)
  })

  it('does not double-count the same run under one metric', () => {
    // A single run somehow has two configs for the same metric — should
    // count the run once, not twice, in runIds.
    const runs: EvalRun[] = [
      {
        evaluation_id: 'rOnce',
        status: 'completed',
        samples_evaluated: 10,
        evaluation_configs: [
          { metric: 'rouge', id: 'cfg-a' },
          { metric: 'rouge', id: 'cfg-b' },
        ],
      },
    ]
    const result = groupRunsByMetric(runs)
    expect(result).toHaveLength(1)
    expect(result[0].runIds).toEqual(['rOnce'])
  })

  it('skips non-completed runs entirely', () => {
    const runs: EvalRun[] = [
      {
        evaluation_id: 'rPending',
        status: 'pending',
        samples_evaluated: 0,
        evaluation_configs: [{ metric: 'meteor' }],
      },
      {
        evaluation_id: 'rFailed',
        status: 'failed',
        samples_evaluated: 0,
        evaluation_configs: [{ metric: 'rouge' }],
      },
    ]
    expect(groupRunsByMetric(runs)).toHaveLength(0)
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
    const result = groupRunsByMetric(runs)
    expect(result).toHaveLength(1)
    expect(result[0].metric).toBe('unknown')
  })
})

describe('drift guard: EvaluationResults.tsx still iterates all configs', () => {
  it('source file walks evaluation_configs in a for-of, not [0]', () => {
    const tsxPath = join(
      __dirname,
      '..',
      'EvaluationResults.tsx',
    )
    const src = readFileSync(tsxPath, 'utf8')
    // Multi-config iteration must be present in the metric grouping.
    expect(src).toMatch(/for \(const cfg of cfgs\)/)
    // The pre-fix shortcut MUST NOT come back. We allow `evaluation_configs?.[0]`
    // elsewhere in the file (other components legitimately read the
    // first config), but the metric-grouping `useMemo` must use the
    // multi-config form. As a coarse but reliable check: the file must
    // contain BOTH the array-or-fallback expression and the for-of iteration.
    expect(src).toMatch(
      /Array\.isArray\(e\.evaluation_configs\) && e\.evaluation_configs\.length > 0/,
    )
  })
})
