'use client'

import { useEffect, useState } from 'react'

import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import { useOptionalApiClient } from '@/contexts/ApiClientContext'
import apiClientSingleton from '@/lib/api'

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
  evaluationConfigs?: Array<{ metric?: string; prediction_fields: string[] }>
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
  cfgs: Array<{ metric?: string; prediction_fields: string[] }> | undefined,
): string {
  if (!cfgs || cfgs.length === 0) return ''
  return cfgs.map(c => `${c.metric ?? ''}:${c.prediction_fields.join(',')}`).join('|')
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
  note: string
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
  modelIds = [],
  judgeModels = [],
  runsPerCall,
  samplesPerTask = 1,
  enabled = true,
  annotatorUserIds,
  evaluationConfigs,
  generationMode,
  structureKeys,
}: CostEstimatePanelProps) {
  const { t } = useI18n()
  const { addToast } = useToast()
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
          model_ids: modelIds,
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
          const msg = err?.response?.data?.detail || err?.message || 'Failed to estimate cost'
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
    modelIds.join(','),
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
    <div className="rounded-md border border-zinc-200 bg-zinc-50 p-3 text-sm dark:border-zinc-800 dark:bg-zinc-900/40">
      <div className="text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
        {t('costEstimate.title', 'Kostenschätzung')}
      </div>

      {loading && (
        <div className="mt-2 flex items-center gap-2 text-xs text-zinc-500">
          <div className="h-3 w-3 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
          {t('costEstimate.loading', 'Tokens zählen und Preise ermitteln…')}
        </div>
      )}

      {error && !loading && (
        <div className="mt-2 rounded border border-red-300 bg-red-50 p-2 text-xs text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
          {error}
        </div>
      )}

      {estimate && !loading && (
        <div className="mt-2 space-y-3">
          <div className="flex items-baseline justify-between">
            <span className="text-xs text-zinc-600 dark:text-zinc-400">
              {t('costEstimate.totalLabel', 'Geschätzte Gesamtkosten')}
              {/* E4: staleness hint — subject_count depends on live DB
                  state (a generation completing in the background changes
                  it). Surface "as of HH:MM:SS" so users have a paper trail
                  if the actual cost diverges. Only shown for the eval-with-
                  configs path because the legacy tasks-count formula is
                  effectively static within a session. */}
              {estimate.subject_count > 0 && estimate.estimated_at && (
                <span
                  className="ml-2 cursor-help text-zinc-400"
                  title={(() => {
                    try {
                      const ts = new Date(estimate.estimated_at)
                      return String(t('costEstimate.estimatedAt', 'Berechnet um {time}'))
                        .replace('{time}', ts.toLocaleTimeString())
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
              ${estimate.total_usd.toFixed(2)}
            </span>
          </div>
          <div className="text-xs text-zinc-500 dark:text-zinc-500">
            {(() => {
              // When the eval modal supplies configs the backend prices the
              // actual cell count; surface that instead of the project-wide
              // task count so the breakdown matches the dollar number.
              if (estimate.subject_count > 0) {
                // Runs are folded per-judge into the backend's per-model cell
                // count (issue #132), so we no longer surface a separate
                // "× runs" multiplier — it would mislead about how the dollar
                // figure is composed.
                const tpl = t('costEstimate.breakdownCells', '{cells} Zellen über {models} Judge-Modell(e)')
                return String(tpl)
                  .replace('{cells}', String(estimate.subject_count))
                  .replace('{models}', String(estimate.per_model.length))
              }
              const tpl = t('costEstimate.breakdown', '{tasks} Tasks × {runs} Lauf/Läufe × {models} Modell(e)')
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
            (estimate.per_model[0] && !estimate.per_model[0].pricing_known)) && (
          <div className="overflow-hidden rounded border border-zinc-200 dark:border-zinc-800">
            <table className="min-w-full divide-y divide-zinc-200 text-xs dark:divide-zinc-800">
              <thead className="bg-zinc-100 text-[10px] uppercase text-zinc-500 dark:bg-zinc-800/50 dark:text-zinc-400">
                <tr>
                  <th className="px-2 py-1.5 text-left font-medium">{t('costEstimate.modelCol', 'Modell')}</th>
                  <th className="px-2 py-1.5 text-right font-medium">{t('costEstimate.perCallCol', 'Pro Aufruf')}</th>
                  <th className="px-2 py-1.5 text-right font-medium">{t('costEstimate.perRunCol', 'Pro Lauf')}</th>
                  <th className="px-2 py-1.5 text-right font-medium">{t('costEstimate.totalCol', 'Gesamt')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                {estimate.per_model.map((m) => (
                  <tr key={m.model_id}>
                    <td className="px-2 py-1.5 font-mono text-[11px]">{m.model_id}</td>
                    <td className="px-2 py-1.5 text-right">
                      {m.pricing_known ? `$${m.per_call_usd.toFixed(4)}` : '—'}
                    </td>
                    <td className="px-2 py-1.5 text-right">
                      {m.pricing_known ? `$${m.per_run_usd.toFixed(2)}` : '—'}
                    </td>
                    <td className="px-2 py-1.5 text-right font-medium">
                      {m.pricing_known ? `$${m.total_usd.toFixed(2)}` : (
                        <span className="text-amber-600 dark:text-amber-400">
                          {t('costEstimate.noPricing', 'Keine Preisdaten')}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          )}

          <div className="rounded bg-blue-50 p-2 text-[11px] text-blue-900 dark:bg-blue-900/20 dark:text-blue-200">
            <div className="font-medium">{t('costEstimate.tokenLabel', 'Token-Schätzung pro Aufruf')}</div>
            <div className="mt-0.5">
              Input: {estimate.token_estimate.input_mean.toFixed(0)} (mean) /{' '}
              {estimate.token_estimate.input_p95.toFixed(0)} (p95) ·{' '}
              Output: {estimate.token_estimate.output_estimate.toFixed(0)} ·{' '}
              Encoding: {estimate.token_estimate.encoding} ·{' '}
              Sample: {estimate.sample_size} Tasks
            </div>
          </div>

          {/* Disclaimer / note assembled by the API: "Estimate accuracy
              ± ~20%…" plus mode-specific utilization detail and (when
              eval-with-configs is active) a wider-variance caveat for
              the subject-count formula. Surfaces what assumptions the
              cost number rests on. */}
          {estimate.note && (
            <div className="text-[11px] leading-snug text-zinc-500 dark:text-zinc-500">
              {estimate.note}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
