/**
 * AnnotationCreator Component
 *
 * Annotation interface for task labeling.
 * Drafts are saved locally only (localStorage) for privacy.
 * Server saves only occur on final submission.
 */

'use client'

import { DynamicAnnotationInterface } from '@/components/labeling/DynamicAnnotationInterface'
import { useI18n } from '@/contexts/I18nContext'
import { useActivityTracker } from '@/hooks/useActivityTracker'
import { projectsAPI } from '@/lib/api/projects'
import type { AnnotationResult } from '@/lib/labelConfig/dataBinding'
import type { Annotation, Task } from '@/types/labelStudio'
import { useEffect, useRef, useState } from 'react'
import { buildSubmissionPayload } from './submissionPayload'

interface AnnotationCreatorProps {
  task: Task
  projectId: string
  labelConfig: string
  onSubmit: (annotation: Annotation) => void
  onCancel?: () => void
  initialAnnotation?: Annotation | null
}

export function AnnotationCreator({
  task,
  projectId,
  labelConfig,
  onSubmit,
  onCancel,
  initialAnnotation,
}: AnnotationCreatorProps) {
  const { t } = useI18n()
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Timing of a new submission, as on the labeling page.
  const activityTracker = useActivityTracker()
  const startTimeRef = useRef(Date.now())
  useEffect(() => {
    startTimeRef.current = Date.now()
    activityTracker.start()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [task.id])

  // Handle final submission
  const handleSubmit = async (results: AnnotationResult[]) => {
    setIsSaving(true)
    setError(null)

    try {
      let finalAnnotation: Annotation

      if (initialAnnotation && !initialAnnotation.was_cancelled) {
        // Update existing annotation to be a final submission. A withdrawn
        // (cancelled) one is a closed record the API refuses to edit, so
        // handing in again creates a new submission below.
        finalAnnotation = await projectsAPI.updateAnnotation(
          initialAnnotation.id,
          {
            result: results,
            was_cancelled: false, // Mark as submitted
          },
        )
      } else {
        // Create new annotation as submitted
        finalAnnotation = await projectsAPI.createAnnotation(
          task.id,
          buildSubmissionPayload({
            result: results,
            leadTimeSeconds: Math.round(
              (Date.now() - startTimeRef.current) / 1000,
            ),
            timing: activityTracker.getData(),
          }),
        )
      }

      onSubmit(finalAnnotation)
    } catch (err) {
      console.error('Error submitting annotation:', err)
      setError(t('labeling.annotationCreator.submitFailed'))
    } finally {
      setIsSaving(false)
    }
  }

  // Handle skip/cancel
  const handleSkip = () => {
    if (onCancel) {
      onCancel()
    }
  }

  return (
    <div className="annotation-creator">
      {/* Status Bar */}
      <div className="mb-4 flex items-center justify-between rounded-lg bg-zinc-50 px-4 py-2 text-sm dark:bg-zinc-800">
        <div className="flex items-center gap-4">
          <span className="text-zinc-600 dark:text-zinc-400">
            {t('labeling.annotationCreator.taskLabel')} #{task.id}
          </span>
          {isSaving && (
            <span className="text-zinc-500">
              {t('labeling.annotationCreator.saving')}
            </span>
          )}
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="mb-4 rounded-lg bg-red-50 p-4 text-red-800 dark:bg-red-900/20 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Annotation Interface */}
      <div className="annotation-interface-wrapper">
        <DynamicAnnotationInterface
          labelConfig={labelConfig}
          taskData={task.data || {}}
          taskId={task.id}
          initialValues={initialAnnotation?.result}
          onSubmit={handleSubmit}
          onSkip={handleSkip}
        />
      </div>

      {/* Info text */}
      <div className="mt-4 text-xs text-zinc-500 dark:text-zinc-400">
        <p>{t('labeling.annotationCreator.autoSaveInfo')}</p>
      </div>
    </div>
  )
}
