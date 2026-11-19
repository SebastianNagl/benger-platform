'use client'

/**
 * The spec of an analysis run (normalized, with every convention filled in
 * and hashed, or as submitted) and the per-fit summaries of the worker.
 */

import { CopyValueButton } from '@/components/analysis/RunProvenance'
import { useI18n } from '@/contexts/I18nContext'
import { MISSING } from '@/lib/analysis/results'
import type { AnalysisFit, AnalysisRun } from '@/lib/api/analysis'
import { useState } from 'react'

type SpecView = 'normalized' | 'submitted'

export function RunSpec({ run }: { run: AnalysisRun }) {
  const { t } = useI18n()
  const [view, setView] = useState<SpecView>('normalized')
  const json = JSON.stringify(
    view === 'normalized' ? run.normalized_spec : run.spec,
    null,
    2,
  )
  return (
    <div data-testid="run-spec">
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <div
          role="tablist"
          aria-label={t('analysis.spec.title')}
          className="inline-flex items-center gap-0.5 rounded-full bg-zinc-100 p-0.5 dark:bg-zinc-800"
        >
          {(['normalized', 'submitted'] as SpecView[]).map((v) => (
            <button
              key={v}
              type="button"
              role="tab"
              aria-selected={view === v}
              onClick={() => setView(v)}
              className={`h-7 rounded-full px-3 text-xs font-medium whitespace-nowrap transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 ${
                view === v
                  ? 'bg-white text-zinc-900 shadow-sm dark:bg-zinc-700 dark:text-white'
                  : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white'
              }`}
            >
              {t(`analysis.spec.${v}`)}
            </button>
          ))}
        </div>
        <span className="text-xs text-zinc-500 dark:text-zinc-400">
          {t(`analysis.spec.${view}Hint`)}
        </span>
        <span className="ml-auto">
          <CopyValueButton value={json} label={t('analysis.spec.copy')} />
        </span>
      </div>
      <pre className="max-h-[32rem] overflow-auto rounded-lg border border-zinc-200 bg-zinc-50 p-3 font-mono text-xs leading-relaxed text-zinc-800 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-200">
        {json}
      </pre>
    </div>
  )
}

const list = (values: unknown) =>
  Array.isArray(values) && values.length > 0 ? values.join(' × ') : MISSING

export function RunFits({ fits }: { fits: readonly AnalysisFit[] }) {
  const { t } = useI18n()
  if (fits.length === 0) {
    return (
      <p className="text-sm text-zinc-500 dark:text-zinc-400">
        {t('analysis.fits.empty')}
      </p>
    )
  }
  const th =
    'px-3 py-2 text-left text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400'
  const td = 'px-3 py-1.5 font-mono text-xs text-zinc-800 dark:text-zinc-200'
  return (
    <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
      <table
        className="min-w-full divide-y divide-zinc-200 dark:divide-zinc-800"
        data-testid="run-fits"
      >
        <thead className="bg-zinc-50 dark:bg-zinc-900/40">
          <tr>
            <th className={th}>{t('analysis.estimates.estimand')}</th>
            <th className={th}>{t('analysis.estimates.scope')}</th>
            <th className={th}>{t('analysis.fits.rows')}</th>
            <th className={th}>{t('analysis.fits.parameters')}</th>
            <th className={th}>{t('analysis.fits.clusters')}</th>
            <th className={th}>{t('analysis.fits.fixedEffects')}</th>
            <th className={th}>{t('analysis.fits.notes')}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100 bg-white dark:divide-zinc-800 dark:bg-zinc-950">
          {fits.map((fit, i) => {
            const notes = [
              ...(Array.isArray(fit.dropped) && fit.dropped.length > 0
                ? [
                    t('analysis.fits.dropped', {
                      columns: fit.dropped.join(', '),
                    }),
                  ]
                : []),
              ...(Array.isArray(fit.warnings) ? fit.warnings : []),
              ...(typeof fit.error === 'string' ? [fit.error] : []),
            ]
            return (
              <tr
                key={`${fit.estimand}-${fit.scope}-${i}`}
                className="align-top"
              >
                <td className={td}>{fit.estimand}</td>
                <td className={`${td} break-all`}>{fit.scope}</td>
                <td className={td}>
                  {fit.n ?? fit.rows ?? MISSING}
                  {typeof fit.rows_dropped_missing === 'number' &&
                    fit.rows_dropped_missing > 0 && (
                      <span className="text-zinc-500">
                        {' '}
                        {t('analysis.fits.missingRows', {
                          count: fit.rows_dropped_missing,
                        })}
                      </span>
                    )}
                </td>
                <td className={td}>
                  {Array.isArray(fit.parameters)
                    ? fit.parameters.join(', ')
                    : MISSING}
                </td>
                <td className={td}>{list(fit.n_clusters)}</td>
                <td className={td}>{list(fit.fe_levels)}</td>
                <td className="px-3 py-1.5 text-xs text-zinc-600 dark:text-zinc-400">
                  {notes.length > 0 ? notes.join('; ') : MISSING}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
