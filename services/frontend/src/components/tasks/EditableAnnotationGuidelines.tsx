'use client'

import { AnnotationGuidelinesModal } from '@/components/modals/AnnotationGuidelinesModal'
import { useToast } from '@/components/shared/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { api, Task } from '@/lib/api'
import { DocumentTextIcon, PencilIcon } from '@heroicons/react/24/outline'
import { useState } from 'react'

interface EditableAnnotationGuidelinesProps {
  task: Task
  onTaskUpdated?: (updatedTask: Task) => void
  className?: string
}

export function EditableAnnotationGuidelines({
  task,
  onTaskUpdated,
  className = '',
}: EditableAnnotationGuidelinesProps) {
  const { user } = useAuth()
  const { t } = useI18n()
  const { addToast } = useToast()
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)

  // Only show edit capability to superadmins or task creators
  const canEdit = user && (user.is_superadmin || user.id === task.created_by)

  const handleOpenModal = () => {
    if (!canEdit) return
    setIsModalOpen(true)
  }

  const handleSaveGuidelines = async (guidelines: string) => {
    const trimmedGuidelines = guidelines.trim()

    // Allow empty guidelines (optional field)
    if (trimmedGuidelines === (task.annotation_guidelines || '').trim()) {
      setIsModalOpen(false)
      return
    }

    setIsSubmitting(true)
    try {
      const updatedTask = await api.updateTask(task.id, {
        annotation_guidelines: trimmedGuidelines || undefined,
      })
      setIsModalOpen(false)
      addToast(t('tasks.guidelines.updateSuccess'), 'success')

      if (onTaskUpdated) {
        onTaskUpdated(updatedTask)
      }
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : t('tasks.guidelines.updateFailed')
      addToast(t('tasks.guidelines.updateFailedWithMessage', { message }), 'error')
      console.error('Error updating annotation guidelines:', error)
    } finally {
      setIsSubmitting(false)
    }
  }

  const hasGuidelines =
    task.annotation_guidelines && task.annotation_guidelines.trim().length > 0

  return (
    <>
      <div className={`group mt-2 ${className}`}>
        <div className="mb-2 flex items-center gap-2">
          <DocumentTextIcon className="h-4 w-4 text-zinc-500 dark:text-zinc-400" />
          <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
            {t('tasks.guidelines.title')}
          </span>
          {canEdit && (
            <button
              onClick={handleOpenModal}
              className="p-1 text-zinc-500 opacity-0 transition-all hover:text-zinc-600 group-hover:opacity-100 dark:text-zinc-400 dark:hover:text-zinc-300"
              title={t('tasks.guidelines.editTooltip')}
            >
              <PencilIcon className="h-4 w-4" />
            </button>
          )}
        </div>

        <div
          className={`${canEdit ? 'cursor-pointer transition-colors hover:text-zinc-800 dark:hover:text-zinc-200' : ''} relative`}
          onClick={handleOpenModal}
          title={canEdit ? t('tasks.guidelines.clickToEdit') : undefined}
        >
          {hasGuidelines ? (
            <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-800 dark:bg-blue-900/20">
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
                {task.annotation_guidelines}
              </p>
            </div>
          ) : (
            <div
              className={`rounded-lg border-2 border-dashed border-zinc-300 p-4 text-center dark:border-zinc-600 ${
                canEdit
                  ? 'hover:border-zinc-400 dark:hover:border-zinc-500'
                  : ''
              } transition-colors`}
            >
              <DocumentTextIcon className="mx-auto mb-2 h-8 w-8 text-zinc-400 dark:text-zinc-500" />
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                {canEdit
                  ? t('tasks.guidelines.clickToAdd')
                  : t('tasks.guidelines.noGuidelines')}
              </p>
              {canEdit && (
                <p className="mt-1 text-xs text-zinc-400 dark:text-zinc-500">
                  {t('tasks.guidelines.helpText')}
                </p>
              )}
            </div>
          )}
        </div>
      </div>

      <AnnotationGuidelinesModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSave={handleSaveGuidelines}
        initialValue={task.annotation_guidelines || ''}
      />
    </>
  )
}
