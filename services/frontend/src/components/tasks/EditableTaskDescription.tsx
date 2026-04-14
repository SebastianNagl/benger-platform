'use client'

import { useToast } from '@/components/shared/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { api, Task } from '@/lib/api'
import { PencilIcon } from '@heroicons/react/24/outline'
import { useEffect, useRef, useState } from 'react'

interface EditableTaskDescriptionProps {
  task: Task
  onTaskUpdated?: (updatedTask: Task) => void
  className?: string
}

export function EditableTaskDescription({
  task,
  onTaskUpdated,
  className = '',
}: EditableTaskDescriptionProps) {
  const { user } = useAuth()
  const { addToast } = useToast()
  const { t } = useI18n()
  const [isEditing, setIsEditing] = useState(false)
  const [editedDescription, setEditedDescription] = useState(task.description)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Only show edit capability to superadmins or task creators
  const canEdit = user && (user.is_superadmin || user.id === task.created_by)

  useEffect(() => {
    if (isEditing && textareaRef.current) {
      textareaRef.current.focus()
      // Position cursor at end
      const length = textareaRef.current.value.length
      textareaRef.current.setSelectionRange(length, length)

      // Auto-resize textarea to fit content
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = textareaRef.current.scrollHeight + 'px'
    }
  }, [isEditing])

  const handleStartEdit = () => {
    if (!canEdit) return
    setEditedDescription(task.description)
    setIsEditing(true)
  }

  const handleCancel = () => {
    setEditedDescription(task.description)
    setIsEditing(false)
  }

  const handleSave = async () => {
    const trimmedDescription = editedDescription.trim()

    if (!trimmedDescription) {
      addToast(t('tasks.description.cannotBeEmpty'), 'error')
      return
    }

    if (trimmedDescription === task.description) {
      setIsEditing(false)
      return
    }

    setIsSubmitting(true)
    try {
      const updatedTask = await api.updateTask(task.id, {
        description: trimmedDescription,
      })
      setIsEditing(false)
      addToast(t('tasks.description.updated'), 'success')

      if (onTaskUpdated) {
        onTaskUpdated(updatedTask)
      }
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : t('tasks.description.saveFailed')
      addToast(t('tasks.description.updateFailed', { message }), 'error')
      console.error('Error updating description:', error)
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      // Ctrl/Cmd + Enter to save
      e.preventDefault()
      handleSave()
    } else if (e.key === 'Escape') {
      e.preventDefault()
      handleCancel()
    }
  }

  const handleBlur = () => {
    if (!isSubmitting) {
      handleSave()
    }
  }

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setEditedDescription(e.target.value)

    // Auto-resize textarea
    e.target.style.height = 'auto'
    e.target.style.height = e.target.scrollHeight + 'px'
  }

  if (isEditing) {
    return (
      <div className={`mt-2 ${className}`}>
        <textarea
          ref={textareaRef}
          value={editedDescription}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          onBlur={handleBlur}
          disabled={isSubmitting}
          className="min-h-[80px] w-full resize-none rounded-lg border-2 border-emerald-500 bg-transparent px-3 py-2 text-zinc-600 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 dark:text-zinc-400"
          placeholder={t('tasks.description.placeholder')}
          rows={3}
          data-testid="description-textarea"
        />
        <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
          {t('tasks.description.editInstructions')}
        </p>
      </div>
    )
  }

  return (
    <div className={`group mt-2 ${className}`}>
      <div
        className={`text-zinc-600 dark:text-zinc-400 ${canEdit ? 'cursor-pointer transition-colors hover:text-zinc-800 dark:hover:text-zinc-200' : ''} relative`}
        onClick={handleStartEdit}
        title={canEdit ? t('tasks.description.clickToEdit') : undefined}
      >
        <p className="whitespace-pre-wrap">{task.description}</p>
        {canEdit && (
          <button
            onClick={(e) => {
              e.stopPropagation()
              handleStartEdit()
            }}
            className="absolute right-0 top-0 p-1 text-zinc-500 opacity-0 transition-all hover:text-zinc-600 group-hover:opacity-100 dark:text-zinc-400 dark:hover:text-zinc-300"
            title={t('tasks.description.editDescription')}
            aria-label={t('tasks.description.editDescription')}
          >
            <PencilIcon className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  )
}
