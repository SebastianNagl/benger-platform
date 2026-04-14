'use client'

import { useToast } from '@/components/shared/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { api, Task } from '@/lib/api'
import { PencilIcon } from '@heroicons/react/24/outline'
import { useEffect, useRef, useState } from 'react'

interface EditableTaskTitleProps {
  task: Task
  onTaskUpdated?: (updatedTask: Task) => void
  className?: string
}

export function EditableTaskTitle({
  task,
  onTaskUpdated,
  className = '',
}: EditableTaskTitleProps) {
  const { t } = useI18n()
  const { user } = useAuth()
  const { addToast } = useToast()
  const [isEditing, setIsEditing] = useState(false)
  const [editedName, setEditedName] = useState(task.name)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  // Only show edit capability to admins or task creators
  const canEdit = user && (user.is_superadmin || user.id === task.created_by)

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus()
      inputRef.current.select()
    }
  }, [isEditing])

  const handleStartEdit = () => {
    if (!canEdit) return
    setEditedName(task.name)
    setIsEditing(true)
  }

  const handleCancel = () => {
    setEditedName(task.name)
    setIsEditing(false)
  }

  const handleSave = async () => {
    const trimmedName = editedName.trim()

    if (!trimmedName) {
      addToast(t('tasks.editTitle.taskNameEmpty'), 'error')
      return
    }

    if (trimmedName === task.name) {
      setIsEditing(false)
      return
    }

    setIsSubmitting(true)
    try {
      const updatedTask = await api.updateTask(task.id, { name: trimmedName })
      setIsEditing(false)
      addToast(t('tasks.editTitle.taskRenamed'), 'success')

      if (onTaskUpdated) {
        onTaskUpdated(updatedTask)
      }
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : t('tasks.editTitle.taskRenameFailed')
      addToast(`${t('tasks.editTitle.taskRenameFailed')}: ${message}`, 'error')
      console.error('Error renaming task:', error)
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
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

  if (isEditing) {
    return (
      <div className={`group flex items-center gap-3 ${className}`}>
        <input
          ref={inputRef}
          type="text"
          value={editedName}
          onChange={(e) => setEditedName(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={handleBlur}
          disabled={isSubmitting}
          className="w-full min-w-0 rounded-lg border-2 border-emerald-500 bg-transparent px-2 py-1 text-3xl font-bold tracking-tight text-zinc-900 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 dark:text-white"
          placeholder={t('tasks.editTitle.enterTaskName')}
        />
      </div>
    )
  }

  return (
    <div className={`group flex items-center gap-3 ${className}`}>
      <h1
        className={`text-3xl font-bold tracking-tight text-zinc-900 dark:text-white ${canEdit ? 'cursor-pointer transition-colors hover:text-emerald-600 dark:hover:text-emerald-400' : ''}`}
        onClick={handleStartEdit}
        title={canEdit ? t('tasks.editTitle.clickToEdit') : undefined}
      >
        {task.name}
      </h1>
      {canEdit && (
        <button
          onClick={handleStartEdit}
          className="p-1 text-zinc-500 opacity-0 transition-all hover:text-zinc-600 group-hover:opacity-100 dark:text-zinc-400 dark:hover:text-zinc-300"
          title={t('tasks.editTitle.editTaskName')}
          aria-label={t('tasks.editTitle.editTaskName')}
        >
          <PencilIcon className="h-5 w-5" />
        </button>
      )}
    </div>
  )
}
