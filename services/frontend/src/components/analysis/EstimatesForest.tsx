'use client'

/**
 * The forest view of a run's estimates: Bradley-Terry estimands as strength
 * forests (players against the reference, per scope), every other estimate
 * in the contrast forest plot (one contrast across its scopes).
 */

import { useI18n } from '@/contexts/I18nContext'
import { specEstimands } from '@/lib/analysis/profile'
import { MISSING } from '@/lib/analysis/results'
import type { AnalysisEstimate, AnalysisRun } from '@/lib/api/analysis'
import { useMemo } from 'react'
import { ContrastForestPlot } from './ContrastForestPlot'
import { StrengthForestPlot } from './StrengthForestPlot'

const BRADLEY_TERRY = 'bradley_terry'

export function EstimatesForest({
  run,
  estimates,
}: {
  run: AnalysisRun
  estimates: readonly AnalysisEstimate[]
}) {
  const { t } = useI18n()
  const strengths = useMemo(
    () => specEstimands(run).filter((e) => e.estimator === BRADLEY_TERRY),
    [run],
  )
  const strengthIds = new Set(strengths.map((e) => e.id))
  const others = estimates.filter((e) => !strengthIds.has(e.estimand_id))
  const shown = strengths
    .map((estimand) => ({
      estimand,
      rows: estimates.filter((e) => e.estimand_id === estimand.id),
    }))
    .filter((s) => s.rows.length > 0)
  return (
    <div className="min-w-0 space-y-6">
      {(others.length > 0 || shown.length === 0) && (
        <ContrastForestPlot estimates={others} />
      )}
      {shown.map(({ estimand, rows }) => (
        <figure key={estimand.id} className="min-w-0" data-testid="strengths">
          <figcaption className="mb-1 text-sm font-medium text-zinc-800 dark:text-zinc-200">
            {t('analysis.views.strength.title', { estimand: estimand.id })}
          </figcaption>
          <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">
            {t('analysis.views.strength.description', {
              players: (estimand.players ?? []).join(', '),
              reference:
                estimand.reference === undefined || estimand.reference === null
                  ? MISSING
                  : String(estimand.reference),
            })}
          </p>
          <StrengthForestPlot estimand={estimand} estimates={rows} />
        </figure>
      ))}
    </div>
  )
}
