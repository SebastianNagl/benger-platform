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

import {
  getMetricDefinitions,
  type AvailableMetric,
  type MetricParameters,
} from '@/lib/api/evaluation-types'
import { hasTranslation, translateKey } from '@/lib/i18n/catalog'
import { LOCALES } from '@/lib/i18n/locales'

type MetricDefLike = Pick<AvailableMetric, 'display_name'> | undefined | null
type MetricParamsLike =
  MetricParameters | Record<string, any> | undefined | null

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
  metric: string,
): string {
  const base = metricDef?.display_name || metric
  const model = resolveJudgeModel(metricParams)

  if (metric.startsWith('llm_judge_') && model) {
    if (base.endsWith(`(${model})`)) return base
    return `${base} (${model})`
  }
  return base
}

type Translate = (key: string) => string

/** `[text, key]` for every UI language's text of each name key of a metric:
 * its `displayNameKey` (plus the registry literal `display_name`) and its
 * `presetNameKeys`. */
function knownNames(def: AvailableMetric): Array<[string, string]> {
  const names: Array<[string, string]> = []
  const keys = [def.displayNameKey, ...(def.presetNameKeys ?? [])]
  for (const key of keys) {
    if (!key) continue
    for (const locale of LOCALES) {
      if (hasTranslation(locale, key)) {
        names.push([String(translateKey(locale, key)), key])
      }
    }
  }
  if (def.displayNameKey && def.display_name) {
    names.push([def.display_name, def.displayNameKey])
  }
  return names
}

/**
 * The name of an evaluation config in the reader's language.
 *
 * Configs store their name as text (`display_name`), written in whatever
 * language the preset or the wizard used, so a French reader would see a
 * German preset name. A stored name that is still a name the system gave
 * the config (the metric's own name or one of its `presetNameKeys`, in any
 * UI language, optionally followed by a ` (…)` suffix such as the judge
 * model) renders in the reader's language with the suffix kept. Any other
 * name was typed by someone and stays exactly as stored. Display only: the
 * stored name stays what configs are matched by.
 */
export function localizedEvalConfigName(
  name: string,
  metric: string | null | undefined,
  t: Translate,
  definitions: Record<string, AvailableMetric> = getMetricDefinitions(),
): string {
  const def = metric ? definitions[metric] : undefined
  const stored = name.trim()
  if (!def || !stored) return name
  const names = knownNames(def)
  const render = (key: string) => {
    const text = t(key)
    return text === key ? null : text
  }
  for (const [text, key] of names) {
    if (text === stored) return render(key) ?? name
  }
  const suffixed = /^(.*\S) (\([^()]*\))$/.exec(stored)
  if (suffixed) {
    for (const [text, key] of names) {
      if (text === suffixed[1]) {
        const head = render(key)
        return head ? `${head} ${suffixed[2]}` : name
      }
    }
  }
  return name
}
