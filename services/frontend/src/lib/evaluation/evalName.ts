/**
 * Shared helper for computing an evaluation config's default display name.
 *
 * Two evaluation configs that use the same metric (e.g. two `llm_judge_*`
 * configs with different judge models) otherwise render identically in the
 * evaluations-page method dropdown. This helper enriches the base metric
 * label with the resolved judge model so same-metric configs stay
 * distinguishable, while leaving non-judge configs untouched.
 *
 * The rule is intentionally simple and MUST stay in lockstep with the Python
 * reimplementation in
 * `services/api/scripts/backfill_eval_config_display_names.py` — both the
 * wizards (defaults) and the backfill produce identical names.
 */

import type { AvailableMetric, MetricParameters } from '@/lib/api/evaluation-types'

type MetricDefLike = Pick<AvailableMetric, 'display_name'> | undefined | null
type MetricParamsLike = MetricParameters | Record<string, any> | undefined | null

/**
 * Resolve the judge-model descriptor for a config, or `undefined` when none.
 *
 * Rule (must stay identical to the Python backfill):
 *  1. Build `(model_id, runs)` pairs from `metricParams.judges` — each element's
 *     `judge_model_id` with its `runs` (default 1 when missing). If `judges` is
 *     absent/empty but `metricParams.judge_model` is set, treat it as a single
 *     `(judge_model, 1)`.
 *  2. Aggregate runs per DISTINCT model by SUMMING across entries, preserving
 *     first-appearance order (NOT alphabetical).
 *  3. Per model token = `model` when summed runs <= 1, else `` `${model} ×${runs}` ``
 *     (U+00D7 multiplication sign).
 *  4. Join tokens with `' + '`.
 *
 * Run counts matter: two configs can share a model and differ only by run count
 * (e.g. gpt-5-mini ×1 vs ×3), which model-only naming would collide.
 */
function resolveJudgeModel(metricParams: MetricParamsLike): string | undefined {
  const pairs: Array<[string, number]> = []
  const judges = metricParams?.judges
  if (Array.isArray(judges) && judges.length > 0) {
    for (const j of judges) {
      const id = (j as any)?.judge_model_id
      if (typeof id !== 'string' || id.length === 0) continue
      const rawRuns = (j as any)?.runs
      const runs =
        typeof rawRuns === 'number' && Number.isFinite(rawRuns) ? rawRuns : 1
      pairs.push([id, runs])
    }
  } else {
    const legacy = metricParams?.judge_model
    if (typeof legacy === 'string' && legacy.length > 0) pairs.push([legacy, 1])
  }

  if (pairs.length === 0) return undefined

  // Sum runs per distinct model, preserving first-appearance order.
  const order: string[] = []
  const runsByModel = new Map<string, number>()
  for (const [model, runs] of pairs) {
    if (!runsByModel.has(model)) order.push(model)
    runsByModel.set(model, (runsByModel.get(model) || 0) + runs)
  }

  return order
    .map((model) => {
      const runs = runsByModel.get(model) || 0
      return runs <= 1 ? model : `${model} ×${runs}`
    })
    .join(' + ')
}

/**
 * Compute the default display name for an evaluation config.
 *
 * - Base label = `metricDef.display_name || metric`.
 * - For `llm_judge_*` metrics with a resolved judge model → `` `${base} (${model})` ``.
 * - Everything else (korrektur_*, automated metrics, judge-less configs) →
 *   `base` unchanged.
 * - Idempotent: if `base` already ends with `` `(${model})` ``, it is returned
 *   unchanged (no double-append).
 */
export function computeDefaultEvalName(
  metricDef: MetricDefLike,
  metricParams: MetricParamsLike,
  metric: string
): string {
  const base = metricDef?.display_name || metric
  const model = resolveJudgeModel(metricParams)

  if (metric.startsWith('llm_judge_') && model) {
    if (base.endsWith(`(${model})`)) return base
    return `${base} (${model})`
  }
  return base
}
