'use client'

/**
 * "Start analysis" dialog: the spec form (`NewAnalysisRunForm`) in a modal,
 * optionally prefilled with the spec and name of an earlier run of the same
 * project (`fromRunId`, the `newRunFrom` URL parameter of the evaluations
 * page). Hosts decide who may open it (edit rights on the project).
 */

import { NewAnalysisRunForm } from '@/components/analysis/NewAnalysisRunForm'
import { Dialog } from '@/components/shared/Dialog'
import { useI18n } from '@/contexts/I18nContext'
import { analysisAPI, type AnalysisRun } from '@/lib/api/analysis'
import { useEffect, useState } from 'react'

export interface StartAnalysisDialogProps {
  isOpen: boolean
  onClose: () => void
  projectId: string
  /** Prefill from this run's spec (must belong to `projectId`). */
  fromRunId?: string | null
  onStarted: (run: AnalysisRun) => void
}

export function StartAnalysisDialog({
  isOpen,
  onClose,
  projectId,
  fromRunId = null,
  onStarted,
}: StartAnalysisDialogProps) {
  const { t } = useI18n()
  const [designKeys, setDesignKeys] = useState<string[]>([])
  const [prefill, setPrefill] = useState<{ spec: string; name: string } | null>(
    null,
  )
  const [prefillError, setPrefillError] = useState<string | null>(null)

  useEffect(() => {
    if (!isOpen || !projectId) return
    let cancelled = false
    analysisAPI
      .listDesignKeys(projectId)
      .then((keys) => {
        if (!cancelled) setDesignKeys(keys)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [isOpen, projectId])

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

  const waitingForPrefill = Boolean(fromRunId) && !prefill && !prefillError

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
        {prefillError && (
          <p
            className="mb-3 text-sm text-red-600 dark:text-red-400"
            role="alert"
          >
            {prefillError}
          </p>
        )}
        {waitingForPrefill ? (
          <p className="text-sm text-zinc-500" role="status">
            {t('analysis.run.loading')}
          </p>
        ) : (
          <NewAnalysisRunForm
            key={prefill ? 'prefilled' : 'blank'}
            projectId={projectId}
            initialSpec={prefill?.spec}
            initialName={prefill?.name}
            designKeys={designKeys}
            onStarted={onStarted}
          />
        )}
      </div>
    </Dialog>
  )
}
