/**
 * In-flight evaluation runs banner.
 *
 * Shows every EvaluationRun in `pending`, `running` or `paused` state with
 * per-run lifecycle controls (issue #198 parity with generation):
 * - pending/running → Pause + Cancel
 * - paused          → Resume + Cancel
 * plus a bulk "cancel all" button, and — when the project's NEWEST run is
 * `failed` — a Retry row for it (missing-only re-dispatch, same run id).
 *
 * Partial TaskEvaluation rows survive pause and cancel — resume/retry and
 * the next `force_rerun=false` trigger pick them up via the orchestrator's
 * missing-only preload (PR #94).
 *
 * Hidden when there's nothing in flight and the newest run isn't failed.
 */

'use client'

import { Button } from '@/components/shared/Button'
import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import { useConfirm } from '@/hooks/useDialogs'
import { apiClient } from '@/lib/api/client'
import {
  ArrowPathIcon,
  ExclamationTriangleIcon,
  PauseIcon,
  PlayIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'
import { useState } from 'react'

type EvaluationLike = {
  evaluation_id: string
  status: string
  samples_evaluated?: number
  created_at?: string | null
  eval_metadata?: {
    cells_dispatched?: number
    failures_by_reason?: Record<string, number>
  } | null
}

export interface InflightRunsBannerProps {
  projectId: string
  evaluations: EvaluationLike[]
  /** Called after a successful lifecycle action so the parent refetches. */
  onChanged: () => void
}

// Cap the number of distinct failure-reason badges rendered.
// `_classify_cell_failure` whitelists 5 buckets server-side so this
// will normally show ≤5; the cap is defense-in-depth in case anyone
// ever bypasses the classifier.
const MAX_FAILURE_BADGES = 8

const LIFECYCLE_STATUSES = ['pending', 'running', 'paused']

export function InflightRunsBanner({
  projectId,
  evaluations,
  onChanged,
}: InflightRunsBannerProps) {
  const { t } = useI18n()
  const { addToast } = useToast()
  const confirm = useConfirm()
  const [busy, setBusy] = useState<Set<string>>(new Set())
  const [bulkCancelling, setBulkCancelling] = useState(false)

  const inflight = evaluations.filter((e) =>
    LIFECYCLE_STATUSES.includes(e.status)
  )
  const cancellable = inflight.filter(
    (e) => e.status === 'pending' || e.status === 'running'
  )

  // Retry affordance for the run the user just watched fail: only the
  // project's NEWEST run qualifies — older failed runs are history, not
  // something to nag about in an amber banner. The results endpoint
  // orders newest-first, but compute defensively via created_at.
  const newest = evaluations.reduce<EvaluationLike | null>(
    (a, b) => (!a ? b : (b.created_at ?? '') > (a.created_at ?? '') ? b : a),
    null
  )
  const latestFailed =
    newest && newest.status === 'failed' && inflight.length === 0
      ? newest
      : null

  if (inflight.length === 0 && !latestFailed) return null

  const markBusy = (id: string, active: boolean) => {
    setBusy((prev) => {
      const next = new Set(prev)
      if (active) next.add(id)
      else next.delete(id)
      return next
    })
  }

  const runLifecycleAction = async (
    id: string,
    action: 'pause' | 'resume' | 'retry'
  ) => {
    markBusy(id, true)
    try {
      const result =
        action === 'pause'
          ? await apiClient.evaluations.pauseEvaluationRun(id)
          : action === 'resume'
            ? await apiClient.evaluations.resumeEvaluationRun(id)
            : await apiClient.evaluations.retryEvaluationRun(id)
      addToast(result.message, result.changed ? 'success' : 'info')
      onChanged()
    } catch (err) {
      addToast(
        t('evaluation.lifecycle.errorWithDetail', {
          detail: err instanceof Error ? err.message : String(err),
          defaultValue: `Aktion fehlgeschlagen: ${err instanceof Error ? err.message : String(err)}`,
        } as any),
        'error'
      )
    } finally {
      markBusy(id, false)
    }
  }

  const cancelOne = async (id: string) => {
    const ok = await confirm({
      title: t('evaluation.cancel.confirmSingleTitle', 'Lauf abbrechen?'),
      message: t(
        'evaluation.cancel.confirmSingleMessage',
        'Bereits berechnete Bewertungen bleiben erhalten und werden beim nächsten Lauf wiederverwendet.'
      ),
      confirmText: t('evaluation.cancel.cancel', 'Abbrechen'),
      cancelText: t('evaluation.cancel.keepRunning', 'Weiterlaufen lassen'),
      variant: 'warning',
    })
    if (!ok) return
    markBusy(id, true)
    try {
      const result = await apiClient.evaluations.cancelEvaluationRun(id)
      addToast(
        result.cancelled_run_ids.length > 0
          ? t('evaluation.cancel.successWithCount', {
              preserved: result.preserved_task_evaluation_count,
              defaultValue: `Lauf abgebrochen. ${result.preserved_task_evaluation_count} Bewertungen erhalten.`,
            } as any)
          : result.message,
        'success'
      )
      onChanged()
    } catch (err) {
      addToast(
        t('evaluation.cancel.errorWithDetail', {
          detail: err instanceof Error ? err.message : String(err),
          defaultValue: `Abbruch fehlgeschlagen: ${err instanceof Error ? err.message : String(err)}`,
        } as any),
        'error'
      )
    } finally {
      markBusy(id, false)
    }
  }

  const cancelAll = async () => {
    const ok = await confirm({
      title: t('evaluation.cancel.confirmAllTitle', 'Alle Läufe abbrechen?'),
      message: t('evaluation.cancel.confirmAllMessage', {
        count: cancellable.length,
        defaultValue: `Alle ${cancellable.length} laufenden bzw. anstehenden Läufe abbrechen? Bereits berechnete Bewertungen bleiben erhalten und werden beim nächsten Lauf wiederverwendet.`,
      } as any),
      confirmText: t('evaluation.cancel.cancelAllConfirm', 'Alle abbrechen'),
      cancelText: t('evaluation.cancel.keepRunning', 'Weiterlaufen lassen'),
      variant: 'danger',
    })
    if (!ok) return
    setBulkCancelling(true)
    try {
      const result = await apiClient.evaluations.cancelAllProjectEvaluations(
        projectId
      )
      addToast(
        result.cancelled_run_ids.length > 0
          ? t('evaluation.cancel.bulkSuccessWithCount', {
              runs: result.cancelled_run_ids.length,
              preserved: result.preserved_task_evaluation_count,
              defaultValue: `${result.cancelled_run_ids.length} Läufe abgebrochen, ${result.preserved_task_evaluation_count} Bewertungen erhalten.`,
            } as any)
          : result.message,
        'success'
      )
      onChanged()
    } catch (err) {
      addToast(
        t('evaluation.cancel.errorWithDetail', {
          detail: err instanceof Error ? err.message : String(err),
          defaultValue: `Abbruch fehlgeschlagen: ${err instanceof Error ? err.message : String(err)}`,
        } as any),
        'error'
      )
    } finally {
      setBulkCancelling(false)
    }
  }

  // Aggregate failure-reason breakdown across in-flight runs.
  // Sub-tasks bump `samples_failed` for transient errors that *produce
  // no TaskEvaluation row* (rate-limit, content policy, judge timeout,
  // poison cell) — without this surface the user sees a pass_rate
  // drop with no signal as to why. Capped at MAX_FAILURE_BADGES to
  // bound the layout.
  const failureBuckets = (() => {
    const totals: Record<string, number> = {}
    for (const e of inflight) {
      const reasons = e.eval_metadata?.failures_by_reason
      if (!reasons) continue
      for (const [reason, n] of Object.entries(reasons)) {
        totals[reason] = (totals[reason] ?? 0) + n
      }
    }
    return Object.entries(totals).sort((a, b) => b[1] - a[1])
  })()
  const shownFailures = failureBuckets.slice(0, MAX_FAILURE_BADGES)
  const hiddenFailureCount = failureBuckets.length - shownFailures.length

  const lifecycleButtonClass =
    'inline-flex items-center gap-1 rounded border border-amber-400 px-2 py-0.5 text-amber-800 hover:bg-amber-100 disabled:opacity-50 dark:border-amber-600 dark:text-amber-100 dark:hover:bg-amber-800/30'

  const renderRow = (e: EvaluationLike) => {
    const cells = e.eval_metadata?.cells_dispatched ?? null
    const evald = e.samples_evaluated ?? 0
    const progress =
      cells && cells > 0
        ? ` — ${evald}/${cells}`
        : evald > 0
          ? ` — ${evald} ${t('evaluation.inflight.samples', 'Samples')}`
          : ''
    const isBusy = busy.has(e.evaluation_id)
    const isPaused = e.status === 'paused'
    const isFailed = e.status === 'failed'
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
        <span className="flex items-center gap-1.5">
          {isFailed ? (
            <button
              type="button"
              onClick={() => runLifecycleAction(e.evaluation_id, 'retry')}
              disabled={isBusy || bulkCancelling}
              className={lifecycleButtonClass}
              data-testid="eval-retry-button"
              aria-label={t(
                'evaluation.lifecycle.retryAria',
                'Diesen Lauf erneut versuchen'
              )}
            >
              <ArrowPathIcon className="h-3.5 w-3.5" />
              {isBusy
                ? t('evaluation.lifecycle.retrying', 'Starte neu …')
                : t('evaluation.lifecycle.retry', 'Erneut versuchen')}
            </button>
          ) : (
            <>
              <button
                type="button"
                onClick={() =>
                  runLifecycleAction(
                    e.evaluation_id,
                    isPaused ? 'resume' : 'pause'
                  )
                }
                disabled={isBusy || bulkCancelling}
                className={lifecycleButtonClass}
                data-testid={
                  isPaused ? 'eval-resume-button' : 'eval-pause-button'
                }
                aria-label={
                  isPaused
                    ? t(
                        'evaluation.lifecycle.resumeAria',
                        'Diesen Lauf fortsetzen'
                      )
                    : t(
                        'evaluation.lifecycle.pauseAria',
                        'Diesen Lauf pausieren'
                      )
                }
              >
                {isPaused ? (
                  <PlayIcon className="h-3.5 w-3.5" />
                ) : (
                  <PauseIcon className="h-3.5 w-3.5" />
                )}
                {isBusy
                  ? isPaused
                    ? t('evaluation.lifecycle.resuming', 'Setze fort …')
                    : t('evaluation.lifecycle.pausing', 'Pausiere …')
                  : isPaused
                    ? t('evaluation.lifecycle.resume', 'Fortsetzen')
                    : t('evaluation.lifecycle.pause', 'Pausieren')}
              </button>
              <button
                type="button"
                onClick={() => cancelOne(e.evaluation_id)}
                disabled={isBusy || bulkCancelling}
                className={lifecycleButtonClass}
                aria-label={t(
                  'evaluation.cancel.singleAria',
                  'Diesen Lauf abbrechen'
                )}
              >
                <XMarkIcon className="h-3.5 w-3.5" />
                {isBusy
                  ? t('evaluation.cancel.cancelling', 'Breche ab …')
                  : t('evaluation.cancel.cancel', 'Abbrechen')}
              </button>
            </>
          )}
        </span>
      </li>
    )
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-lg border border-amber-300 bg-amber-50 p-3 dark:border-amber-700 dark:bg-amber-900/20"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm text-amber-900 dark:text-amber-100">
          <ExclamationTriangleIcon className="h-5 w-5 flex-shrink-0" />
          <span className="font-medium">
            {latestFailed
              ? t(
                  'evaluation.lifecycle.latestFailedHeading',
                  'Letzte Auswertung fehlgeschlagen'
                )
              : t('evaluation.inflight.heading', {
                  count: inflight.length,
                  defaultValue: `${inflight.length} Auswertung(en) laufen gerade`,
                } as any)}
          </span>
        </div>
        {cancellable.length > 1 && (
          <Button
            size="sm"
            variant="secondary"
            onClick={cancelAll}
            disabled={bulkCancelling || busy.size > 0}
            className="text-amber-900 dark:text-amber-100"
          >
            {bulkCancelling
              ? t('evaluation.cancel.cancellingAll', 'Breche ab …')
              : t('evaluation.cancel.cancelAll', 'Alle abbrechen')}
          </Button>
        )}
      </div>
      <ul className="mt-2 space-y-1.5">
        {(latestFailed ? [latestFailed] : inflight).map(renderRow)}
      </ul>
      {shownFailures.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-amber-900 dark:text-amber-100">
          <span className="opacity-70">
            {t('evaluation.inflight.failuresLabel', 'Fehlschläge nach Grund:')}
          </span>
          {shownFailures.map(([reason, n]) => (
            <span
              key={reason}
              className="rounded bg-amber-200/70 px-1.5 py-0.5 font-mono dark:bg-amber-800/40"
              title={reason}
            >
              {reason}: {n}
            </span>
          ))}
          {hiddenFailureCount > 0 && (
            <span className="rounded bg-amber-300/70 px-1.5 py-0.5 dark:bg-amber-700/40">
              {t('evaluation.inflight.failuresMore', {
                count: hiddenFailureCount,
                defaultValue: `+${hiddenFailureCount} weitere`,
              } as any)}
            </span>
          )}
        </div>
      )}
    </div>
  )
}
