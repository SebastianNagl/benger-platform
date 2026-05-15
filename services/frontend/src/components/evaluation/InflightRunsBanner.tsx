/**
 * In-flight evaluation runs banner.
 *
 * Shows every EvaluationRun in `pending` or `running` state with a
 * per-run cancel and a bulk "cancel all" button. Lets operators stop
 * runaway or duplicate dispatches from the UI instead of needing
 * direct DB / kubectl exec access. Partial TaskEvaluation rows survive
 * cancel — the next `force_rerun=false` re-trigger picks them up via
 * the orchestrator's missing-only preload (PR #94).
 *
 * Hidden when there's nothing in flight.
 */

'use client'

import { Button } from '@/components/shared/Button'
import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import { apiClient } from '@/lib/api/client'
import { ExclamationTriangleIcon, XMarkIcon } from '@heroicons/react/24/outline'
import { useState } from 'react'

type EvaluationLike = {
  evaluation_id: string
  status: string
  samples_evaluated?: number
  eval_metadata?: {
    cells_dispatched?: number
    failures_by_reason?: Record<string, number>
  } | null
}

export interface InflightRunsBannerProps {
  projectId: string
  evaluations: EvaluationLike[]
  /** Called after a successful cancel so the parent refetches. */
  onChanged: () => void
}

export function InflightRunsBanner({
  projectId,
  evaluations,
  onChanged,
}: InflightRunsBannerProps) {
  const { t } = useI18n()
  const { addToast } = useToast()
  const [cancelling, setCancelling] = useState<Set<string>>(new Set())
  const [bulkCancelling, setBulkCancelling] = useState(false)

  const inflight = evaluations.filter(
    (e) => e.status === 'pending' || e.status === 'running'
  )

  if (inflight.length === 0) return null

  const markCancelling = (id: string, active: boolean) => {
    setCancelling((prev) => {
      const next = new Set(prev)
      if (active) next.add(id)
      else next.delete(id)
      return next
    })
  }

  const cancelOne = async (id: string) => {
    if (
      !window.confirm(
        t(
          'evaluation.cancel.confirmSingle',
          'Diesen Lauf abbrechen? Bereits berechnete Bewertungen bleiben erhalten.'
        )
      )
    ) {
      return
    }
    markCancelling(id, true)
    try {
      const result = await apiClient.evaluations.cancelEvaluationRun(id)
      addToast(
        result.cancelled_run_ids.length > 0
          ? t('evaluation.cancel.success', 'Lauf abgebrochen.') +
              ` (${result.preserved_task_evaluation_count} Bewertungen erhalten)`
          : result.message,
        'success'
      )
      onChanged()
    } catch (err) {
      addToast(
        t('evaluation.cancel.error', 'Abbruch fehlgeschlagen.') +
          ' ' +
          (err instanceof Error ? err.message : String(err)),
        'error'
      )
    } finally {
      markCancelling(id, false)
    }
  }

  const cancelAll = async () => {
    if (
      !window.confirm(
        t(
          'evaluation.cancel.confirmAll',
          `Alle ${inflight.length} laufenden/anstehenden Läufe abbrechen? Bereits berechnete Bewertungen bleiben erhalten.`
        )
      )
    ) {
      return
    }
    setBulkCancelling(true)
    try {
      const result = await apiClient.evaluations.cancelAllProjectEvaluations(
        projectId
      )
      addToast(
        result.cancelled_run_ids.length > 0
          ? t('evaluation.cancel.bulkSuccess', 'Läufe abgebrochen.') +
              ` (${result.cancelled_run_ids.length} Läufe, ${result.preserved_task_evaluation_count} Bewertungen erhalten)`
          : result.message,
        'success'
      )
      onChanged()
    } catch (err) {
      addToast(
        t('evaluation.cancel.error', 'Abbruch fehlgeschlagen.') +
          ' ' +
          (err instanceof Error ? err.message : String(err)),
        'error'
      )
    } finally {
      setBulkCancelling(false)
    }
  }

  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 dark:border-amber-700 dark:bg-amber-900/20">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm text-amber-900 dark:text-amber-100">
          <ExclamationTriangleIcon className="h-5 w-5 flex-shrink-0" />
          <span className="font-medium">
            {t(
              'evaluation.inflight.heading',
              `${inflight.length} Auswertung(en) laufen gerade`
            )}
          </span>
        </div>
        {inflight.length > 1 && (
          <Button
            size="sm"
            variant="secondary"
            onClick={cancelAll}
            disabled={bulkCancelling || cancelling.size > 0}
            className="text-amber-900 dark:text-amber-100"
          >
            {bulkCancelling
              ? t('evaluation.cancel.cancellingAll', 'Breche ab …')
              : t('evaluation.cancel.cancelAll', 'Alle abbrechen')}
          </Button>
        )}
      </div>
      <ul className="mt-2 space-y-1.5">
        {inflight.map((e) => {
          const cells = e.eval_metadata?.cells_dispatched ?? null
          const evald = e.samples_evaluated ?? 0
          const progress =
            cells && cells > 0
              ? ` — ${evald}/${cells}`
              : evald > 0
                ? ` — ${evald} ${t('evaluation.inflight.samples', 'Samples')}`
                : ''
          const isCancelling = cancelling.has(e.evaluation_id)
          return (
            <li
              key={e.evaluation_id}
              className="flex items-center justify-between gap-2 rounded bg-white/60 px-2 py-1 text-xs text-gray-700 dark:bg-zinc-900/40 dark:text-gray-300"
            >
              <span className="font-mono">
                {e.evaluation_id.slice(0, 8)}
                <span className="ml-2 text-gray-500 dark:text-gray-400">
                  ({e.status}
                  {progress})
                </span>
              </span>
              <button
                type="button"
                onClick={() => cancelOne(e.evaluation_id)}
                disabled={isCancelling || bulkCancelling}
                className="inline-flex items-center gap-1 rounded border border-amber-400 px-2 py-0.5 text-amber-800 hover:bg-amber-100 disabled:opacity-50 dark:border-amber-600 dark:text-amber-100 dark:hover:bg-amber-800/30"
                aria-label={t('evaluation.cancel.singleAria', 'Diesen Lauf abbrechen')}
              >
                <XMarkIcon className="h-3.5 w-3.5" />
                {isCancelling
                  ? t('evaluation.cancel.cancelling', 'Breche ab …')
                  : t('evaluation.cancel.cancel', 'Abbrechen')}
              </button>
            </li>
          )
        })}
      </ul>
      {/* Aggregate failure-reason breakdown across in-flight runs.
          Sub-tasks bump `samples_failed` for transient errors that
          *produce no TaskEvaluation row* (rate-limit, content policy,
          judge timeout, poison cell) — without this surface the user
          sees a pass_rate drop but no signal as to why. */}
      {(() => {
        const totals: Record<string, number> = {}
        for (const e of inflight) {
          const reasons = e.eval_metadata?.failures_by_reason
          if (!reasons) continue
          for (const [reason, n] of Object.entries(reasons)) {
            totals[reason] = (totals[reason] ?? 0) + n
          }
        }
        const entries = Object.entries(totals).sort((a, b) => b[1] - a[1])
        if (entries.length === 0) return null
        return (
          <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-amber-900 dark:text-amber-100">
            <span className="opacity-70">
              {t('evaluation.inflight.failuresLabel', 'Fehlschläge nach Grund:')}
            </span>
            {entries.map(([reason, n]) => (
              <span
                key={reason}
                className="rounded bg-amber-200/70 px-1.5 py-0.5 font-mono dark:bg-amber-800/40"
                title={reason}
              >
                {reason}: {n}
              </span>
            ))}
          </div>
        )
      })()}
    </div>
  )
}
