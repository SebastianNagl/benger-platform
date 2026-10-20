'use client'

import { useEffect, useState } from 'react'

import { Alert } from '@/components/shared/Alert'
import { useToast } from '@/components/shared/Toast'
import { useOptionalApiClient } from '@/contexts/ApiClientContext'
import { useI18n } from '@/contexts/I18nContext'
import apiClientSingleton from '@/lib/api'
import { formatDecimal, intlTag } from '@/lib/i18n/locales'

export interface CostEstimatePanelProps {
  projectId: string
  mode: 'generation' | 'evaluation'
  modelIds?: string[]
  judgeModels?: string[]
  runsPerCall: number
  samplesPerTask?: number
  /** When true, fetches and renders. Trigger modals pass `isOpen` here so the
   *  estimate fetch only fires when the modal is actually visible. */
  enabled?: boolean
  /** Eval-only (issue #69): scope filters that narrow the (subject ×
   *  prediction_field) cell count the backend prices against. The
   *  optional `metric` lets the backend apply per-metric classification
   *  rules (e.g. llm_judge_falloesung's unprefixed-field convention). */
  annotatorUserIds?: string[]
  evaluationConfigs?: Array<{
    id?: string
    metric?: string
    prediction_fields: string[]
  }>
  /** Mirror of the trigger endpoint's `mode` argument (all/missing/single).
   *  When 'missing', the backend counts only the cells whose latest
   *  generation failed or is absent — matching what the worker will
   *  actually queue. Without this the estimate over-states cost for any
   *  partial-rerun scenario. */
  generationMode?: 'all' | 'missing' | 'single'
  /** Active prompt structures the user picked. The backend uses these to
   *  count cells per (task × structure) instead of just per task. */
  structureKeys?: string[]
}

interface PerModelCost {
  model_id: string
  per_call_usd: number
  per_run_usd: number
  total_usd: number
  pricing_known: boolean
  cells_to_generate?: number
}

/**
 * Stable string representation of the eval-configs prop for use in a
 * `useEffect` deps array. JSON.stringify works but allocates a fresh
 * string each render and is opaque in DevTools — this `metric:fields|...`
 * shape is short, comparable, and reads cleanly in the deps list.
 */
function hashConfigs(
  cfgs:
    | Array<{ id?: string; metric?: string; prediction_fields: string[] }>
    | undefined,
): string {
  if (!cfgs || cfgs.length === 0) return ''
  return cfgs
    .map(
      (c) => `${c.id ?? ''}:${c.metric ?? ''}:${c.prediction_fields.join(',')}`,
    )
    .join('|')
}

interface CostEstimateResponse {
  mode: 'generation' | 'evaluation'
  runs_per_call: number
  sample_size: number
  tasks_total: number
  /** (subject × prediction_field) cells the eval will (re-)score; 0 for
   *  generation mode or eval-without-configs (legacy fallback). */
  subject_count: number
  /** ISO timestamp (UTC) of when subject_count was computed. Surfaced as
   *  an "as of …" tooltip so users know how stale the preview is — the
   *  count moves whenever a generation completes between preview and
   *  Run-click. */
  estimated_at: string
  per_model: PerModelCost[]
  total_usd: number
  token_estimate: {
    input_mean: number
    input_p95: number
    output_estimate: number
    encoding: string
  }
  /** English summary; only rendered when the structured fields are absent
   *  (older API). */
  note: string
  accuracy_percent?: number
  encoding?: string
  input_basis?: 'task_data' | 'generation_outputs' | 'rendered_judge_prompt'
  output_utilization_percent?: number | null
  output_basis?: 'utilization' | 'judge_steps' | 'judge_profile'
  missing_only?: boolean
  per_judge_cells?: boolean
}

type Translate = (key: string, vars?: Record<string, unknown>) => unknown

function fill(template: unknown, values: Record<string, string | number>) {
  return Object.entries(values).reduce(
    (text, [name, value]) => text.split(`{${name}}`).join(String(value)),
    String(template),
  )
}

/** The estimate's assumptions in the reader's language, built from the
 *  structured response fields. Falls back to the API's English `note`. */
function estimateNote(estimate: CostEstimateResponse, t: Translate): string {
  if (estimate.accuracy_percent == null) return estimate.note
  const encoding = estimate.encoding || estimate.token_estimate.encoding
  const basis = {
    task_data: t('costEstimate.note.basisTaskData'),
    generation_outputs: t('costEstimate.note.basisGenerationOutputs'),
    rendered_judge_prompt: t('costEstimate.note.basisRenderedJudgePrompt'),
  }[estimate.input_basis ?? 'task_data']
  const parts = [
    fill(t('costEstimate.note.accuracy'), {
      percent: estimate.accuracy_percent,
    }),
    String(basis),
    estimate.mode === 'evaluation' && estimate.output_basis === 'judge_steps'
      ? String(t('costEstimate.note.outputJudgeSteps'))
      : estimate.mode === 'evaluation' &&
          estimate.output_basis === 'judge_profile'
        ? String(t('costEstimate.note.outputJudgeProfile'))
        : estimate.mode === 'evaluation'
          ? fill(t('costEstimate.note.outputJudge'), {
              percent: estimate.output_utilization_percent ?? 15,
            })
          : String(t('costEstimate.note.outputGeneration')),
    fill(t('costEstimate.note.encoding'), { encoding }),
  ]
  if (estimate.missing_only) {
    parts.push(String(t('costEstimate.note.countingMissing')))
  } else if (estimate.mode === 'generation') {
    parts.push(String(t('costEstimate.note.countingAll')))
  }
  if (estimate.per_judge_cells) {
    parts.push(String(t('costEstimate.note.perJudgeCells')))
  }
  return parts.join(' ')
}

/**
 * Inline cost-preview panel embedded into Start Generation / Start Evaluation
 * modals. Calls /api/llm-models/cost-estimate when `enabled` flips to true and
 * renders per-model + total cost with a "± ~20%" caveat. (File renamed from
 * `CostEstimateModal.tsx` once the standalone-dialog flavor was retired —
 * the trigger modals now render this inline.)
 */
export function CostEstimatePanel({
  projectId,
  mode,
  modelIds: modelIdsProp,
  judgeModels = [],
  runsPerCall,
  samplesPerTask = 1,
  enabled = true,
  annotatorUserIds,
  evaluationConfigs,
  generationMode,
  structureKeys,
}: CostEstimatePanelProps) {
  const { t, locale } = useI18n()
  const { addToast } = useToast()
  // In evaluation mode an empty list means no model is selected (only
  // submitted answers get graded), so it is sent as is; leaving the prop out
  // means no model filter.
  const modelIds = modelIdsProp ?? []
  // Prefer the org-wired client threaded via AuthProvider; fall back to the
  // global singleton when rendered outside the authenticated tree (e.g. in
  // isolated unit tests). Behavior is identical — both carry org context.
  const contextClient = useOptionalApiClient()
  const apiClient = contextClient ?? apiClientSingleton
  const [loading, setLoading] = useState(false)
  const [estimate, setEstimate] = useState<CostEstimateResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!enabled) return
    if (mode === 'generation' && modelIds.length === 0) return
    if (mode === 'evaluation' && judgeModels.length === 0) return

    let cancelled = false
    const run = async () => {
      setLoading(true)
      setError(null)
      try {
        const data = await apiClient.post('/llm-models/cost-estimate', {
          project_id: projectId,
          mode,
          model_ids: mode === 'evaluation' ? modelIdsProp : modelIds,
          judge_models: judgeModels,
          runs_per_call: runsPerCall,
          samples_per_task: samplesPerTask,
          annotator_user_ids: annotatorUserIds,
          evaluation_configs: evaluationConfigs,
          generation_mode: generationMode,
          structure_keys: structureKeys,
        })
        if (!cancelled) setEstimate(data)
      } catch (err: any) {
        if (!cancelled) {
          const msg =
            err?.response?.data?.detail ||
            err?.message ||
            'Failed to estimate cost'
          setError(msg)
          addToast(msg, 'error')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    run()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    apiClient,
    enabled,
    projectId,
    mode,
    modelIdsProp === undefined ? '-' : modelIds.join(','),
    judgeModels.join(','),
    runsPerCall,
    samplesPerTask,
    (annotatorUserIds ?? []).join(','),
    hashConfigs(evaluationConfigs),
    generationMode,
    (structureKeys || []).join(','),
  ])

  if (!enabled) return null
  if (mode === 'generation' && modelIds.length === 0) return null
  if (mode === 'evaluation' && judgeModels.length === 0) return null

  return (
    <div className="rounded-lg border border-zinc-200 p-4 text-sm dark:border-zinc-700">
      <div className="text-sm font-medium text-zinc-900 dark:text-white">
        {t('costEstimate.title')}
      </div>

      {loading && (
        <div className="mt-2 flex items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400">
          <div className="h-3 w-3 animate-spin rounded-full border-2 border-emerald-600 border-t-transparent dark:border-emerald-400 dark:border-t-transparent" />
          {t('costEstimate.loading')}
        </div>
      )}

      {error && !loading && (
        <Alert variant="error" className="mt-2 p-3">
          <p className="text-xs text-red-700 dark:text-red-300">{error}</p>
        </Alert>
      )}

      {estimate && !loading && (
        <div className="mt-2 space-y-3">
          <div className="flex items-baseline justify-between">
            <span className="text-sm text-zinc-600 dark:text-zinc-400">
              {t('costEstimate.totalLabel')}
              {/* E4: staleness hint — subject_count depends on live DB
                  state (a generation completing in the background changes
                  it). Surface "as of HH:MM:SS" so users have a paper trail
                  if the actual cost diverges. Only shown for the eval-with-
                  configs path because the legacy tasks-count formula is
                  effectively static within a session. */}
              {estimate.subject_count > 0 && estimate.estimated_at && (
                <span
                  className="ml-2 cursor-help text-zinc-400 dark:text-zinc-500"
                  title={(() => {
                    try {
                      const ts = new Date(estimate.estimated_at)
                      return t('costEstimate.estimatedAt', {
                        time: ts.toLocaleTimeString(intlTag(locale)),
                      })
                    } catch {
                      return estimate.estimated_at
                    }
                  })()}
                >
                  ⓘ
                </span>
              )}
            </span>
            <span className="text-xl font-semibold text-zinc-900 dark:text-white">
              ${formatDecimal(estimate.total_usd, locale, 2)}
            </span>
          </div>
          <div className="text-xs text-zinc-500 dark:text-zinc-400">
            {(() => {
              // When the eval modal supplies configs the backend prices the
              // actual cell count; surface that instead of the project-wide
              // task count so the breakdown matches the dollar number.
              if (estimate.per_judge_cells || estimate.subject_count > 0) {
                // Runs are folded per-judge into the backend's per-model cell
                // count (issue #132), so we no longer surface a separate
                // "× runs" multiplier — it would mislead about how the dollar
                // figure is composed.
                const tpl = t('costEstimate.breakdownCells')
                // The judge calls actually priced, not the raw subject pool.
                const cells = estimate.per_judge_cells
                  ? estimate.per_model.reduce(
                      (sum, m) => sum + (m.cells_to_generate ?? 0),
                      0,
                    )
                  : estimate.subject_count
                return String(tpl)
                  .replace('{cells}', String(cells))
                  .replace('{models}', String(estimate.per_model.length))
              }
              const tpl = t('costEstimate.breakdown')
              return String(tpl)
                .replace('{tasks}', String(estimate.tasks_total))
                .replace('{runs}', String(estimate.runs_per_call))
                .replace('{models}', String(estimate.per_model.length))
            })()}
          </div>

          {/* Per-model table only adds info when there are ≥2 rows (or
              the single row carries unknown-pricing context worth seeing).
              For one priced model the headline already shows the same
              number — repeating it once more is just noise. */}
          {(estimate.per_model.length > 1 ||
            (estimate.per_model[0] &&
              !estimate.per_model[0].pricing_known)) && (
            <div className="overflow-hidden rounded-lg border border-zinc-200 dark:border-zinc-700">
              <table className="min-w-full divide-y divide-zinc-200 text-xs dark:divide-zinc-700">
                <thead className="bg-zinc-50 text-zinc-500 dark:bg-zinc-800/50 dark:text-zinc-400">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">
                      {t('costEstimate.modelCol')}
                    </th>
                    <th className="px-3 py-2 text-right font-medium">
                      {t('costEstimate.perCallCol')}
                    </th>
                    <th className="px-3 py-2 text-right font-medium">
                      {t('costEstimate.perRunCol')}
                    </th>
                    <th className="px-3 py-2 text-right font-medium">
                      {t('costEstimate.totalCol')}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-100 text-zinc-700 dark:divide-zinc-700/60 dark:text-zinc-300">
                  {estimate.per_model.map((m) => (
                    <tr key={m.model_id}>
                      <td className="px-3 py-2 font-mono text-[11px]">
                        {m.model_id}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {m.pricing_known
                          ? `$${formatDecimal(m.per_call_usd, locale, 4)}`
                          : '—'}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {m.pricing_known
                          ? `$${formatDecimal(m.per_run_usd, locale, 2)}`
                          : '—'}
                      </td>
                      <td className="px-3 py-2 text-right font-medium">
                        {m.pricing_known ? (
                          `$${formatDecimal(m.total_usd, locale, 2)}`
                        ) : (
                          <span className="text-amber-600 dark:text-amber-400">
                            {t('costEstimate.noPricing')}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="border-t border-zinc-200 pt-3 text-xs text-zinc-600 dark:border-zinc-700 dark:text-zinc-400">
            <div className="font-medium text-zinc-700 dark:text-zinc-300">
              {t('costEstimate.tokenLabel')}
            </div>
            <div className="mt-0.5">
              {fill(t('costEstimate.tokenLine'), {
                mean: formatDecimal(estimate.token_estimate.input_mean, locale),
                p95: formatDecimal(estimate.token_estimate.input_p95, locale),
                output: formatDecimal(
                  estimate.token_estimate.output_estimate,
                  locale,
                ),
                encoding: estimate.token_estimate.encoding,
                sample: estimate.sample_size,
              })}
            </div>
          </div>

          {/* The assumptions the cost number rests on (accuracy band, what
              the input was measured on, output utilization, tokenizer,
              which cells are counted), phrased from the structured
              response fields in the reader's language. */}
          {(estimate.accuracy_percent != null || estimate.note) && (
            <div className="text-xs leading-snug text-zinc-500 dark:text-zinc-400">
              {estimateNote(estimate, t)}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
