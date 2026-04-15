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
import { projectsAPI } from '@/lib/api/projects'
import type { AnnotationResult } from '@/lib/labelConfig/dataBinding'
import type { Annotation, Task } from '@/types/labelStudio'
import { useState } from 'react'

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

  // Handle final submission
  const handleSubmit = async (results: AnnotationResult[]) => {
    setIsSaving(true)
    setError(null)

    try {
      let finalAnnotation: Annotation

      if (initialAnnotation) {
        // Update existing annotation to be a final submission
        finalAnnotation = await projectsAPI.updateAnnotation(
          initialAnnotation.id,
          {
            result: results,
            was_cancelled: false, // Mark as submitted
          }
        )
      } else {
        // Create new annotation as submitted
        finalAnnotation = await projectsAPI.createAnnotation(task.id, {
          result: results,
          was_cancelled: false,
        })
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
      <div className="mb-4 flex items-center justify-between rounded-lg bg-gray-50 px-4 py-2 text-sm dark:bg-gray-800">
        <div className="flex items-center gap-4">
          <span className="text-gray-600 dark:text-gray-400">
            {t('labeling.annotationCreator.taskLabel')} #{task.id}
          </span>
          {isSaving && (
            <span className="text-gray-500">{t('labeling.annotationCreator.saving')}</span>
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
      <div className="mt-4 text-xs text-gray-500 dark:text-gray-400">
        <p>{t('labeling.annotationCreator.autoSaveInfo')}</p>
      </div>
    </div>
  )
}
