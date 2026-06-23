/**
 * DataRecordModal - view/edit a single task's complete data record.
 *
 * Thin wrapper around {@link TaskDataViewModal} extracted from ProjectDataTab.
 * It carries the same prop surface the orchestrator wired inline (open/close,
 * the resolved API task, view-vs-edit mode, edit gate, and the save callback)
 * so the orchestrator no longer has to reach into the underlying modal
 * directly. Behaviour and rendered output are unchanged — this is a rename of
 * the inline `<TaskDataViewModal …>` block.
 */

'use client'

import { TaskDataViewModal } from '@/components/tasks/TaskDataViewModal'
import { Task } from '@/lib/api/types'

interface DataRecordModalProps {
  task: Task | null
  isOpen: boolean
  onClose: () => void
  projectId: string
  mode: 'view' | 'edit'
  canEdit: boolean
  onSaved: () => void
}

export function DataRecordModal({
  task,
  isOpen,
  onClose,
  projectId,
  mode,
  canEdit,
  onSaved,
}: DataRecordModalProps) {
  return (
    <TaskDataViewModal
      task={task}
      isOpen={isOpen}
      onClose={onClose}
      projectId={projectId}
      taskId={task?.id ? String(task.id) : undefined}
      initialMode={mode}
      canEdit={canEdit}
      onSaved={onSaved}
    />
  )
}

export default DataRecordModal
