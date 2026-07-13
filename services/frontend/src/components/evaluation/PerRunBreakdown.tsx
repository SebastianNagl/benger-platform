/**
 * Per-run breakdown table for an evaluation (multi-run feature).
 *
 * Renders one row per (target_model, judge_model, run_index) showing the run's
 * mean score, sample count, and status. Used in two modes:
 *   1. Same-model multi-run (one judge × N runs) — shows per-run variance.
 *   2. Judge ensemble (M judges × N runs each) — shows per-judge means.
 *
 * The data shape comes from the multi-run statistics endpoint (see
 * `runs_by_model_metric` in metadata.py); this component is generic over
 * what produced the rows.
 */

'use client'

import { useI18n } from '@/contexts/I18nContext'
import { useMemo } from 'react'

export interface PerRunRow {
  target_model_id: string
  judge_model_id: string | null
  run_index: number
  judge_run_id: string
  status: string
  samples_evaluated: number | null
  mean_score: number | null
}

export interface PerRunBreakdownProps {
  rows: PerRunRow[]
  metric: string
  /** When true, render the target_model column. Hide for single-target evaluations. */
  showTargetModel?: boolean
}

function formatScore(score: number | null): string {
  if (score === null || score === undefined || Number.isNaN(score)) return '—'
  return score.toFixed(3)
}

function statusBadgeClass(status: string): string {
  switch (status) {
    case 'completed':
      return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300'
    case 'failed':
      return 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300'
    case 'running':
      return 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300'
    case 'paused':
      return 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300'
    default:
      return 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300'
  }
}

export function PerRunBreakdown({
  rows,
  metric,
  showTargetModel = true,
}: PerRunBreakdownProps) {
  const { t } = useI18n()

  const sortedRows = useMemo(() => {
    return [...rows].sort((a, b) => {
      // Sort by target_model, then judge_model, then run_index ascending.
      if (a.target_model_id !== b.target_model_id) {
        return a.target_model_id.localeCompare(b.target_model_id)
      }
      const ja = a.judge_model_id ?? ''
      const jb = b.judge_model_id ?? ''
      if (ja !== jb) return ja.localeCompare(jb)
      return a.run_index - b.run_index
    })
  }, [rows])

  if (sortedRows.length === 0) {
    return (
      <div className="rounded border border-zinc-200 bg-white p-6 text-center text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
        {t('eval.perRun.empty', 'Keine Lauf-Daten für diese Metrik.')}
      </div>
    )
  }

  return (
    <div className="overflow-hidden rounded border border-zinc-200 dark:border-zinc-800">
      <table className="min-w-full divide-y divide-zinc-200 text-sm dark:divide-zinc-800">
        <thead className="bg-zinc-50 text-xs uppercase text-zinc-500 dark:bg-zinc-800/50 dark:text-zinc-400">
          <tr>
            {showTargetModel && (
              <th className="px-3 py-2 text-left font-medium">
                {t('eval.perRun.targetModel', 'Ziel-Modell')}
              </th>
            )}
            <th className="px-3 py-2 text-left font-medium">
              {t('eval.perRun.judge', 'Judge')}
            </th>
            <th className="px-3 py-2 text-right font-medium">
              {t('eval.perRun.runIndex', 'Lauf #')}
            </th>
            <th className="px-3 py-2 text-right font-medium">
              {t('eval.perRun.samples', 'Samples')}
            </th>
            <th className="px-3 py-2 text-right font-medium">
              {t('eval.perRun.meanScore', `Mean ${metric}`)}
            </th>
            <th className="px-3 py-2 text-left font-medium">
              {t('eval.perRun.status', 'Status')}
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {sortedRows.map((row) => (
            <tr key={row.judge_run_id}>
              {showTargetModel && (
                <td className="px-3 py-2 font-mono text-xs">{row.target_model_id}</td>
              )}
              <td className="px-3 py-2 font-mono text-xs">
                {row.judge_model_id ?? (
                  <span className="text-zinc-400">{t('eval.perRun.deterministic', '(deterministic)')}</span>
                )}
              </td>
              <td className="px-3 py-2 text-right tabular-nums">{row.run_index}</td>
              <td className="px-3 py-2 text-right tabular-nums">
                {row.samples_evaluated ?? '—'}
              </td>
              <td className="px-3 py-2 text-right tabular-nums">{formatScore(row.mean_score)}</td>
              <td className="px-3 py-2">
                <span
                  className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${statusBadgeClass(row.status)}`}
                >
                  {row.status}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
