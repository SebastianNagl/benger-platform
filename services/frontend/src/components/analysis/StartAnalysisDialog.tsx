'use client'

/**
 * "Start analysis" dialog, shared by the project page's Evaluation card and
 * the evaluations page's Analyses view: the spec form
 * (`NewAnalysisRunForm`) in a modal, filled from one of three sources the
 * picker offers:
 *
 * - a saved analysis plan of the project (`planId` preselects one); a run
 *   started from it unchanged records the plan's `spec_hash`;
 * - an earlier run of the same project (`fromRunId`, the `newRunFrom` URL
 *   parameter of the evaluations page);
 * - a blank spec to paste.
 *
 * Hosts decide who may open it (the CONTRIBUTOR or ORG_ADMIN role).
 */

import { NewAnalysisRunForm } from '@/components/analysis/NewAnalysisRunForm'
import { Dialog } from '@/components/shared/Dialog'
import { useI18n } from '@/contexts/I18nContext'
import { shortHash } from '@/lib/analysis/results'
import {
  analysisAPI,
  type AnalysisPlan,
  type AnalysisRun,
} from '@/lib/api/analysis'
import { formatDateTime } from '@/lib/reports/format'
import { useEffect, useId, useState } from 'react'

export interface StartAnalysisDialogProps {
  isOpen: boolean
  onClose: () => void
  projectId: string
  /** Prefill from this run's spec (must belong to `projectId`). */
  fromRunId?: string | null
  /** Preselect this saved plan. */
  planId?: string | null
  onStarted: (run: AnalysisRun) => void
}

type Source =
  { kind: 'blank' } | { kind: 'run' } | { kind: 'plan'; planId: string }

const sourceValue = (source: Source) =>
  source.kind === 'plan' ? `plan:${source.planId}` : source.kind

export function StartAnalysisDialog({
  isOpen,
  onClose,
  projectId,
  fromRunId = null,
  planId = null,
  onStarted,
}: StartAnalysisDialogProps) {
  const { t, locale } = useI18n()
  const pickerId = useId()
  const [designKeys, setDesignKeys] = useState<string[]>([])
  const [plans, setPlans] = useState<AnalysisPlan[] | null>(null)
  const [source, setSource] = useState<Source>({ kind: 'blank' })
  const [prefill, setPrefill] = useState<{ spec: string; name: string } | null>(
    null,
  )
  const [prefillError, setPrefillError] = useState<string | null>(null)

  useEffect(() => {
    if (!isOpen || !projectId) return
    let cancelled = false
    setPlans(null)
    analysisAPI
      .listDesignKeys(projectId)
      .then((keys) => {
        if (!cancelled) setDesignKeys(keys)
      })
      .catch(() => undefined)
    analysisAPI
      .listPlans(projectId)
      .then((saved) => {
        if (!cancelled) setPlans(saved)
      })
      .catch(() => {
        if (!cancelled) setPlans([])
      })
    return () => {
      cancelled = true
    }
  }, [isOpen, projectId])

  // The source the dialog opens with: the run to reuse, else the plan asked
  // for, else a blank spec.
  useEffect(() => {
    if (!isOpen) return
    setSource(
      fromRunId
        ? { kind: 'run' }
        : planId
          ? { kind: 'plan', planId }
          : { kind: 'blank' },
    )
  }, [isOpen, fromRunId, planId])

  useEffect(() => {
    setPrefill(null)
    setPrefillError(null)
    if (!isOpen || !fromRunId) return
    let cancelled = false
    analysisAPI
      .getRun(fromRunId)
      .then((run) => {
        if (cancelled) return
        if (run.project_id !== projectId) {
          setPrefillError(t('analysis.list.prefillFailed'))
          return
        }
        setPrefill({ spec: JSON.stringify(run.spec, null, 2), name: run.name })
      })
      .catch(() => {
        if (!cancelled) setPrefillError(t('analysis.list.prefillFailed'))
      })
    return () => {
      cancelled = true
    }
    // t is stable per locale; a locale switch need not refetch the run.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, fromRunId, projectId])

  const plan =
    source.kind === 'plan'
      ? (plans?.find((p) => p.id === source.planId) ?? null)
      : null
  const planMissing = source.kind === 'plan' && plans !== null && !plan
  const waiting =
    (source.kind === 'run' && !prefill && !prefillError) ||
    (source.kind === 'plan' && plans === null)
  const showPicker = Boolean(fromRunId) || (plans?.length ?? 0) > 0

  const form =
    source.kind === 'plan' && plan ? (
      <NewAnalysisRunForm
        key={`plan:${plan.id}:${plan.spec_hash}`}
        projectId={projectId}
        initialSpec={JSON.stringify(plan.spec, null, 2)}
        initialName={plan.name}
        designKeys={designKeys}
        planHash={plan.spec_hash}
        onStarted={onStarted}
      />
    ) : (
      <NewAnalysisRunForm
        key={source.kind === 'run' && prefill ? 'prefilled' : 'blank'}
        projectId={projectId}
        initialSpec={source.kind === 'run' ? prefill?.spec : undefined}
        initialName={source.kind === 'run' ? prefill?.name : undefined}
        designKeys={designKeys}
        onStarted={onStarted}
      />
    )

  return (
    <Dialog
      isOpen={isOpen}
      onClose={onClose}
      title={t('analysis.list.newRun')}
      className="max-w-2xl"
    >
      <div data-testid="start-analysis-dialog">
        <p className="mb-4 text-sm text-zinc-500 dark:text-zinc-400">
          {t('analysis.list.newRunDescription')}
        </p>
        {showPicker && (
          <div className="mb-4">
            <label
              htmlFor={pickerId}
              className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
            >
              {t('analysis.plans.source')}
            </label>
            <select
              id={pickerId}
              value={sourceValue(source)}
              onChange={(e) => {
                const value = e.target.value
                setSource(
                  value.startsWith('plan:')
                    ? { kind: 'plan', planId: value.slice(5) }
                    : value === 'run'
                      ? { kind: 'run' }
                      : { kind: 'blank' },
                )
              }}
              className="block w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 focus:border-emerald-500 focus:ring-emerald-500 focus:outline-none dark:border-zinc-600 dark:bg-zinc-800 dark:text-white"
              data-testid="start-analysis-source"
            >
              {(plans ?? []).map((p) => (
                <option key={p.id} value={`plan:${p.id}`}>
                  {t('analysis.plans.sourcePlan', { name: p.name })}
                </option>
              ))}
              {planMissing && source.kind === 'plan' && (
                <option value={sourceValue(source)} disabled>
                  {t('analysis.plans.missing')}
                </option>
              )}
              {fromRunId && (
                <option value="run">{t('analysis.plans.sourceRun')}</option>
              )}
              <option value="blank">{t('analysis.plans.sourceBlank')}</option>
            </select>
            {plan && (
              <p
                className="mt-1 text-xs text-zinc-500 dark:text-zinc-400"
                data-testid="start-analysis-plan-hash"
              >
                {plan.saved_at
                  ? t('analysis.plans.planHashSaved', {
                      hash: shortHash(plan.spec_hash),
                      date: formatDateTime(plan.saved_at, locale),
                    })
                  : t('analysis.plans.planHash', {
                      hash: shortHash(plan.spec_hash),
                    })}
              </p>
            )}
          </div>
        )}
        {source.kind === 'run' && prefillError && (
          <p
            className="mb-3 text-sm text-red-600 dark:text-red-400"
            role="alert"
          >
            {prefillError}
          </p>
        )}
        {planMissing && (
          <p
            className="mb-3 text-sm text-red-600 dark:text-red-400"
            role="alert"
          >
            {t('analysis.plans.missing')}
          </p>
        )}
        {waiting ? (
          <p className="text-sm text-zinc-500" role="status">
            {t('analysis.run.loading')}
          </p>
        ) : planMissing ? null : (
          form
        )}
      </div>
    </Dialog>
  )
}
