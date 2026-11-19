'use client'

/**
 * Strength forest plot of a Bradley-Terry estimand: one row per player
 * level with its strength against the reference level (fixed at 0) and the
 * interval, one plot per scope (the pooled fit, each system), chosen with a
 * row of chips. The strengths are the engine's stored estimates
 * (parameters `strength[<level>]`); nothing is re-estimated.
 */

import { useI18n } from '@/contexts/I18nContext'
import { levelText } from '@/lib/analysis/labels'
import type { SpecEstimand } from '@/lib/analysis/profile'
import { formatLevel, scopeDescription } from '@/lib/analysis/results'
import type { AnalysisEstimate } from '@/lib/api/analysis'
import clsx from 'clsx'
import { useState } from 'react'
import { ForestPlot, type ForestPlotRow } from './ForestPlot'

const STRENGTH = /^strength\[(.+)\]$/

/** The player level a strength parameter names (`strength[b]` is `b`). */
export function strengthLevel(contrastId: string | null): string | null {
  return contrastId?.match(STRENGTH)?.[1] ?? null
}

/** Whether an estimate is a player strength (not a term or a contrast). */
export const isStrength = (e: Pick<AnalysisEstimate, 'contrast_id' | 'kind'>) =>
  e.kind !== 'wald' && strengthLevel(e.contrast_id) !== null

export function StrengthForestPlot({
  estimand,
  estimates,
}: {
  estimand: SpecEstimand
  /** The estimand's estimates (every scope). */
  estimates: readonly AnalysisEstimate[]
}) {
  const { t, locale } = useI18n()
  const rows = estimates.filter(isStrength)
  const scopes = [...new Set(rows.map((e) => e.scope))]
  const [picked, setPicked] = useState<string | null>(null)
  const scope =
    picked && scopes.includes(picked)
      ? picked
      : (scopes.find((s) => s === 'pooled') ?? scopes[0])
  const shown = rows.filter((e) => e.scope === scope)
  const reference =
    estimand.reference !== undefined && estimand.reference !== null
      ? levelText(estimand.reference)
      : null
  const scopeLabel = (s: string) => {
    const sample = rows.find((e) => e.scope === s)
    return (sample && scopeDescription(sample)) ?? t('analysis.scope.pooled')
  }
  const plotRows: ForestPlotRow[] = [
    ...(reference
      ? [
          {
            id: 'reference',
            label: reference,
            estimate: 0,
            lower: null,
            upper: null,
            emphasis: true,
          },
        ]
      : []),
    ...shown.map((e) => ({
      id: String(e.id ?? e.position),
      label: strengthLevel(e.contrast_id) ?? '',
      estimate: e.estimate,
      lower: e.ci_lower,
      upper: e.ci_upper,
      note: e.estimate === null ? (e.message ?? e.status) : null,
    })),
  ]
  if (rows.length === 0) return null
  return (
    <div className="min-w-0 space-y-3" data-testid="strength-forest">
      {scopes.length > 1 && (
        <div
          className="flex flex-wrap gap-2"
          role="group"
          aria-label={t('analysis.views.strength.scopes')}
        >
          {scopes.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setPicked(s)}
              aria-pressed={s === scope}
              className={clsx(
                'max-w-[16rem] truncate rounded-full px-3 py-1 text-xs ring-1 ring-inset',
                s === scope
                  ? 'bg-zinc-900 text-white ring-zinc-900 dark:bg-emerald-400/10 dark:text-emerald-300 dark:ring-emerald-400/30'
                  : 'text-zinc-700 ring-zinc-300 hover:bg-zinc-50 dark:text-zinc-300 dark:ring-zinc-700 dark:hover:bg-zinc-800',
              )}
              title={scopeLabel(s)}
            >
              {scopeLabel(s)}
            </button>
          ))}
        </div>
      )}
      <ForestPlot
        rows={plotRows}
        nullValue={0}
        ariaLabel={t('analysis.views.strength.aria', {
          estimand: estimand.id,
          scope: scopeLabel(scope),
        })}
        axisLabel={
          estimand.link === 'linear'
            ? t('analysis.views.strength.axisLinear')
            : t('analysis.views.strength.axisLogit')
        }
        legend={{
          interval: t('analysis.forest.legendInterval', {
            level: formatLevel(shown[0]?.ci_level, locale),
          }),
        }}
        data-testid="strength-forest-plot"
      />
    </div>
  )
}
