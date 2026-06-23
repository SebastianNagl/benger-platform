/**
 * JudgeEnsembleControl
 *
 * Inline judge-ensemble + runs editor (multi-run feature). Renders for any
 * llm_judge_* metric in the wizard's parameters step. Writes to
 * metric_parameters.judges = [{ judge_model_id, runs }, ...] which the
 * worker resolves via _resolve_judges. The standalone LLMJudgeControlModal
 * used to own this UI; pulled inline so users see ensemble + runs in the
 * same flow where they pick the primary judge model.
 *
 * Extracted from EvaluationBuilder.tsx (was `renderJudgeEnsembleControl`).
 * Rendered output is identical; this is a behavior-preserving extraction.
 */

'use client'

import { useI18n } from '@/contexts/I18nContext'
import type { Model } from '@/hooks/useModels'

interface BuilderStateWithParameters {
  metric_parameters: Record<string, any>
}

export interface JudgeEnsembleControlProps<
  S extends BuilderStateWithParameters,
> {
  /** The current wizard `newEvaluation.metric_parameters`. */
  metricParameters: Record<string, any>
  /** Judge model catalog (from `useJudgeModelHelpers`). */
  judgeModels: Model[]
  /**
   * The wizard state setter. Only `metric_parameters` is updated here
   * (`judges` + `runs_per_judge`); other state slices are preserved by the
   * caller's reducer shape.
   */
  setNewEvaluation: (updater: (prev: S) => S) => void
}

export function JudgeEnsembleControl<S extends BuilderStateWithParameters>({
  metricParameters,
  judgeModels,
  setNewEvaluation,
}: JudgeEnsembleControlProps<S>) {
  const { t } = useI18n()

  const primaryJudge: string = metricParameters.judge_model || 'gpt-4o'
  const existingJudges = Array.isArray(metricParameters.judges)
    ? (metricParameters.judges as Array<{ judge_model_id: string; runs?: number }>)
    : []
  const runsPerJudge: number = Math.max(
    1,
    Math.min(
      25,
      Number(
        existingJudges[0]?.runs ??
          metricParameters.runs_per_judge ??
          1,
      ) || 1,
    ),
  )
  const additionalJudges: string[] = existingJudges
    .map((e) => e.judge_model_id)
    .filter((id) => id && id !== primaryJudge)

  const writeJudges = (additional: string[], runs: number) => {
    const next = [
      { judge_model_id: primaryJudge, runs },
      ...additional.map((id) => ({ judge_model_id: id, runs })),
    ]
    setNewEvaluation((prev) => ({
      ...prev,
      metric_parameters: {
        ...prev.metric_parameters,
        judges: next,
        runs_per_judge: runs,
      },
    }))
  }

  return (
    <div className="space-y-4 rounded-md border border-emerald-200 bg-emerald-50/40 p-3 dark:border-emerald-800/40 dark:bg-emerald-900/10">
      <div className="text-xs font-semibold text-emerald-800 dark:text-emerald-200">
        {t(
          'evaluationBuilder.parameters.ensembleAndRuns',
          'Ensemble & Läufe',
        )}
      </div>

      <div>
        <label className="mb-2 block text-xs font-medium text-gray-700 dark:text-gray-300">
          {t(
            'evaluationBuilder.parameters.runsPerJudge',
            'Läufe pro Judge',
          )}
        </label>
        <input
          type="number"
          min={1}
          max={25}
          value={runsPerJudge}
          onChange={(e) => {
            const r = Math.max(
              1,
              Math.min(25, parseInt(e.target.value) || 1),
            )
            writeJudges(additionalJudges, r)
          }}
          className="h-8 w-24 rounded-md border border-gray-300 px-2 text-sm dark:border-gray-600 dark:bg-gray-800"
        />
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          {t(
            'evaluationBuilder.parameters.runsPerJudgeHelp',
            'Wie oft jeder Judge die gleiche Probe bewertet (Varianzanalyse). Cap 25.',
          )}
        </p>
      </div>

      <div>
        <label className="mb-2 block text-xs font-medium text-gray-700 dark:text-gray-300">
          {t(
            'evaluationBuilder.parameters.additionalJudges',
            'Zusätzliche Judges (Ensemble)',
          )}
        </label>
        <div className="grid grid-cols-2 gap-2">
          {judgeModels
            .filter((m) => m.id !== primaryJudge)
            .map((m) => {
              const checked = additionalJudges.includes(m.id)
              return (
                <label
                  key={m.id}
                  className="flex items-center gap-2 rounded-md border border-gray-200 p-2 text-xs dark:border-gray-700"
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={(e) => {
                      const next = e.target.checked
                        ? [...additionalJudges, m.id]
                        : additionalJudges.filter((id) => id !== m.id)
                      writeJudges(next, runsPerJudge)
                    }}
                    className="h-3.5 w-3.5 rounded border-gray-300 text-emerald-600"
                  />
                  <span className="truncate">
                    {m.name}{' '}
                    <span className="text-gray-400">({m.provider})</span>
                  </span>
                </label>
              )
            })}
        </div>
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          {t(
            'evaluationBuilder.parameters.additionalJudgesHelp',
            'Mehrere Judges erzeugen Inter-Judge-Agreement (Cohen/Fleiss kappa, Pearson).',
          )}
        </p>
      </div>
    </div>
  )
}
