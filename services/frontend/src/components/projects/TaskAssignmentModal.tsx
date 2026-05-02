/**
 * Task Assignment Modal - Allows managers to assign tasks to annotators.
 *
 * Refactored to consume the shared AssignmentFormBody so the Korrektur item
 * assignment modal stays in sync without duplicating fields.
 */

import {
  AssignmentFormBody,
  EMPTY_ASSIGNMENT_FORM,
  type AssignmentFormValue,
} from '@/components/projects/AssignmentFormBody'
import { Button } from '@/components/shared/Button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/shared/Dialog'
import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import apiClient from '@/lib/api'
import { AssignTasksRequest } from '@/types/labelStudio'
import { useState } from 'react'

interface TaskAssignmentModalProps {
  isOpen: boolean
  onClose: () => void
  projectId: string
  selectedTaskIds: string[]
  projectMembers: Array<{
    id: string
    user_id: string
    name: string
    email: string
    role: string
  }>
  onAssignmentComplete: () => Promise<void>
}

export function TaskAssignmentModal({
  isOpen,
  onClose,
  projectId,
  selectedTaskIds,
  projectMembers,
  onAssignmentComplete,
}: TaskAssignmentModalProps) {
  const { t } = useI18n()
  const { addToast } = useToast()
  const [form, setForm] = useState<AssignmentFormValue>(EMPTY_ASSIGNMENT_FORM)
  const [isAssigning, setIsAssigning] = useState(false)

  const handleAssign = async () => {
    if (form.user_ids.length === 0) {
      addToast(t('tasks.assignment.noUsers'), 'error')
      return
    }

    setIsAssigning(true)
    try {
      const response = await fetch(`/api/projects/${projectId}/tasks/assign`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('access_token')}`,
        },
        body: JSON.stringify({
          task_ids: selectedTaskIds,
          user_ids: form.user_ids,
          distribution: form.distribution,
          priority: form.priority,
          due_date: form.due_date || undefined,
          notes: form.notes || undefined,
        } as AssignTasksRequest),
      })

      if (!response.ok) {
        throw new Error('Failed to assign tasks')
      }

      const result = await response.json()

      if (result.assignments_created > 0) {
        addToast(t('tasks.assignment.assigned'), 'success')
      } else if (result.assignments_skipped > 0) {
        addToast(t('tasks.assignment.assigned'), 'info')
      } else if (result.assignments_updated > 0) {
        addToast(t('tasks.assignment.assigned'), 'success')
      } else {
        addToast(result.message || t('tasks.assignment.assigned'), 'info')
      }

      apiClient.clearCache()
      await onAssignmentComplete()
      onClose()
    } catch (error) {
      console.error('Error assigning tasks:', error)
      addToast(t('tasks.assignment.assignFailed'), 'error')
    } finally {
      setIsAssigning(false)
    }
  }

  return (
    <Dialog open={isOpen} onClose={onClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t('tasks.assignment.title')}</DialogTitle>
        </DialogHeader>

        <div className="space-y-6 py-4">
          <div className="rounded-lg bg-zinc-50 p-4 dark:bg-zinc-800">
            <p className="text-sm text-zinc-600 dark:text-zinc-400">
              {t('projects.taskAssignment.assigningTasks', { count: selectedTaskIds.length })}
            </p>
          </div>

          <AssignmentFormBody
            members={projectMembers}
            value={form}
            onChange={setForm}
          />
        </div>

        <div className="flex items-center justify-end gap-3 border-t pt-4">
          <Button variant="outline" onClick={onClose} disabled={isAssigning}>
            {t('tasks.assignment.cancel')}
          </Button>
          <Button
            onClick={handleAssign}
            disabled={isAssigning || form.user_ids.length === 0}
            className="bg-emerald-600 hover:bg-emerald-700"
          >
            {isAssigning
              ? `${t('tasks.assignment.assign')}...`
              : t('tasks.assignment.assign')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
