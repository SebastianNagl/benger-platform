'use client'

/**
 * One questionnaire, rendered by the annotation interface itself (the same
 * label-config XML and components), with its own submit and, when the
 * questionnaire is optional, a skip. Required questions (`required="true"`)
 * block the submit and are named. A questionnaire never sees task data, so
 * nothing about the task or a person appears in it.
 */

import { useCallback, useState } from 'react'

import { DynamicAnnotationInterface } from '@/components/labeling/DynamicAnnotationInterface'
import { Button } from '@/components/shared/Button'
import { useI18n } from '@/contexts/I18nContext'
import type { AnnotationResult } from '@/lib/labelConfig/dataBinding'

// Stable reference: questionnaire items never reference task data.
const NO_TASK_DATA = {}

export interface QuestionnaireFormProps {
  config: string
  /** False shows a skip button. */
  required: boolean
  onSubmit: (result: AnnotationResult[]) => Promise<void>
  onSkip?: () => Promise<void>
  /** Remounts the form (fresh answers) when it changes. */
  formKey?: string
}

function errorMessage(err: any, fallback: string): string {
  return typeof err?.message === 'string' && err.message
    ? err.message
    : fallback
}

export function QuestionnaireForm({
  config,
  required,
  onSubmit,
  onSkip,
  formKey,
}: QuestionnaireFormProps) {
  const { t } = useI18n()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = useCallback(
    async (result: AnnotationResult[]) => {
      setBusy(true)
      setError(null)
      try {
        await onSubmit(result)
      } catch (err) {
        setError(errorMessage(err, t('questionnaires.answer.error')))
        // Rethrow so the form keeps the answers.
        throw err
      } finally {
        setBusy(false)
      }
    },
    [onSubmit, t],
  )

  const handleSkip = useCallback(async () => {
    if (!onSkip) return
    setBusy(true)
    setError(null)
    try {
      await onSkip()
    } catch (err) {
      setError(errorMessage(err, t('questionnaires.answer.error')))
    } finally {
      setBusy(false)
    }
  }, [onSkip, t])

  return (
    <div className="relative space-y-4" data-testid="questionnaire-form">
      {error && (
        <div
          role="alert"
          className="rounded-md bg-red-50 p-3 text-sm text-red-800 dark:bg-red-900/20 dark:text-red-300"
        >
          {error}
        </div>
      )}
      {busy && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/70 dark:bg-zinc-900/70">
          <div className="h-10 w-10 animate-spin rounded-full border-2 border-zinc-300 border-t-emerald-500 dark:border-zinc-600 dark:border-t-emerald-400" />
        </div>
      )}
      <DynamicAnnotationInterface
        key={formKey}
        labelConfig={config}
        taskData={NO_TASK_DATA}
        onSubmit={handleSubmit}
        showSubmitButton
        enableAutoSave={false}
        enforceRequired
      />
      {!required && onSkip && (
        <div className="flex justify-end">
          <Button
            variant="text"
            onClick={handleSkip}
            disabled={busy}
            data-testid="questionnaire-skip"
          >
            {t('questionnaires.answer.skip')}
          </Button>
        </div>
      )}
    </div>
  )
}
