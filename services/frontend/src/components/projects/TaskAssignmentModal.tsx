/**
 * Task Assignment Modal - Allows managers to assign tasks to annotators
 */

import { TableCheckbox } from '@/components/projects/TableCheckbox'
import { UserAvatar } from '@/components/projects/UserAvatar'
import { Button } from '@/components/shared/Button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/shared/Dialog'
import { Input } from '@/components/shared/Input'
import { Label } from '@/components/shared/Label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shared/Select'
import { Textarea } from '@/components/shared/Textarea'
import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import apiClient from '@/lib/api'
import { AssignTasksRequest } from '@/types/labelStudio'
import {
  ArrowPathRoundedSquareIcon,
  ChartBarIcon,
  SparklesIcon,
  UserGroupIcon,
} from '@heroicons/react/24/outline'
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
  const [selectedUsers, setSelectedUsers] = useState<string[]>([])
  const [distribution, setDistribution] =
    useState<AssignTasksRequest['distribution']>('manual')
  const [priority, setPriority] = useState(0)
  const [dueDate, setDueDate] = useState('')
  const [notes, setNotes] = useState('')
  const [isAssigning, setIsAssigning] = useState(false)

  // Deduplicate members by user_id (a user in multiple orgs could appear twice)
  const uniqueMembers = Array.from(
    new Map(projectMembers.map((m) => [m.user_id, m])).values()
  )

  // Filter to only show annotators, reviewers, contributors, and org admins
  const annotators = uniqueMembers.filter(
    (m) =>
      m.role === 'ANNOTATOR' ||
      m.role === 'REVIEWER' ||
      m.role === 'CONTRIBUTOR' ||
      m.role === 'ORG_ADMIN' ||
      m.role === 'annotator' ||
      m.role === 'reviewer' ||
      m.role === 'contributor' ||
      m.role === 'org_admin'
  )

  const handleUserToggle = (userId: string) => {
    setSelectedUsers((prev) =>
      prev.includes(userId)
        ? prev.filter((id) => id !== userId)
        : [...prev, userId]
    )
  }

  const handleSelectAll = () => {
    if (selectedUsers.length === annotators.length) {
      setSelectedUsers([])
    } else {
      setSelectedUsers(annotators.map((a) => a.user_id))
    }
  }

  const handleAssign = async () => {
    if (selectedUsers.length === 0) {
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
          user_ids: selectedUsers,
          distribution,
          priority,
          due_date: dueDate || undefined,
          notes: notes || undefined,
        } as AssignTasksRequest),
      })

      if (!response.ok) {
        throw new Error('Failed to assign tasks')
      }

      const result = await response.json()

      // Handle different assignment outcomes
      if (result.assignments_created > 0) {
        addToast(t('tasks.assignment.assigned'), 'success')
      } else if (result.assignments_skipped > 0) {
        addToast(t('tasks.assignment.assigned'), 'info')
      } else if (result.assignments_updated > 0) {
        addToast(t('tasks.assignment.assigned'), 'success')
      } else {
        addToast(result.message || t('tasks.assignment.assigned'), 'info')
      }

      // Clear API cache so task list refetch gets fresh data
      apiClient.clearCache()
      // Await the completion callback to ensure state updates before closing
      await onAssignmentComplete()
      onClose()
    } catch (error) {
      console.error('Error assigning tasks:', error)
      addToast(t('tasks.assignment.assignFailed'), 'error')
    } finally {
      setIsAssigning(false)
    }
  }

  const getDistributionIcon = () => {
    switch (distribution) {
      case 'manual':
        return <UserGroupIcon className="h-5 w-5" />
      case 'round_robin':
        return <ArrowPathRoundedSquareIcon className="h-5 w-5" />
      case 'random':
        return <SparklesIcon className="h-5 w-5" />
      case 'load_balanced':
        return <ChartBarIcon className="h-5 w-5" />
    }
  }

  const getDistributionDescription = () => {
    switch (distribution) {
      case 'manual':
        return t('projects.taskAssignment.manualDescription')
      case 'round_robin':
        return t('projects.taskAssignment.roundRobinDescription')
      case 'random':
        return t('projects.taskAssignment.randomDescription')
      case 'load_balanced':
        return t('projects.taskAssignment.loadBalancedDescription')
    }
  }

  return (
    <Dialog open={isOpen} onClose={onClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t('tasks.assignment.title')}</DialogTitle>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Task Summary */}
          <div className="rounded-lg bg-zinc-50 p-4 dark:bg-zinc-800">
            <p className="text-sm text-zinc-600 dark:text-zinc-400">
              {t('projects.taskAssignment.assigningTasks', { count: selectedTaskIds.length })}
            </p>
          </div>

          {/* Distribution Method */}
          <div>
            <Label>{t('projects.taskAssignment.distributionMethod')}</Label>
            <Select
              value={distribution}
              onValueChange={(value) => setDistribution(value as any)}
            >
              <SelectTrigger>
                <div className="flex items-center gap-2">
                  {getDistributionIcon()}
                  <SelectValue />
                </div>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="manual">{t('projects.taskAssignment.manual')}</SelectItem>
                <SelectItem value="round_robin">{t('projects.taskAssignment.roundRobin')}</SelectItem>
                <SelectItem value="random">{t('projects.taskAssignment.random')}</SelectItem>
                <SelectItem value="load_balanced">{t('projects.taskAssignment.loadBalanced')}</SelectItem>
              </SelectContent>
            </Select>
            <p className="mt-1 text-xs text-zinc-500">
              {getDistributionDescription()}
            </p>
          </div>

          {/* User Selection */}
          <div>
            <div className="mb-2 flex items-center justify-between">
              <Label>{t('projects.taskAssignment.selectAnnotators')}</Label>
              <Button variant="text" onClick={handleSelectAll}>
                {selectedUsers.length === annotators.length
                  ? t('projects.taskAssignment.deselectAll')
                  : t('projects.taskAssignment.selectAll')}
              </Button>
            </div>

            <div className="max-h-48 divide-y overflow-y-auto rounded-lg border">
              {annotators.length === 0 ? (
                <div className="p-4 text-center text-sm text-zinc-500">
                  {t('tasks.assignment.noUsers')}
                </div>
              ) : (
                annotators.map((member) => (
                  <div
                    key={member.user_id}
                    className="flex cursor-pointer items-center gap-3 p-3 hover:bg-zinc-50 dark:hover:bg-zinc-800"
                    onClick={() => handleUserToggle(member.user_id)}
                  >
                    <TableCheckbox
                      checked={selectedUsers.includes(member.user_id)}
                      onChange={() => {}}
                    />
                    <UserAvatar
                      name={member.name}
                      email={member.email}
                      size="sm"
                    />
                    <div className="flex-1">
                      <div className="text-sm font-medium">{member.name}</div>
                      <div className="text-xs text-zinc-500">
                        {member.email}
                      </div>
                    </div>
                    <div className="text-xs text-zinc-500">{member.role}</div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Priority */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label htmlFor="priority">{t('projects.taskAssignment.priority')}</Label>
              <Select
                value={priority.toString()}
                onValueChange={(value) => setPriority(parseInt(value))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="0">{t('projects.taskAssignment.priorityNormal')}</SelectItem>
                  <SelectItem value="1">{t('projects.taskAssignment.priorityLow')}</SelectItem>
                  <SelectItem value="2">{t('projects.taskAssignment.priorityMedium')}</SelectItem>
                  <SelectItem value="3">{t('projects.taskAssignment.priorityHigh')}</SelectItem>
                  <SelectItem value="4">{t('projects.taskAssignment.priorityUrgent')}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label htmlFor="due_date">
                {t('tasks.assignment.dueDate')} (
                {t('tasks.assignment.optional')})
              </Label>
              <Input
                id="due_date"
                type="datetime-local"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
              />
            </div>
          </div>

          {/* Notes */}
          <div>
            <Label htmlFor="notes">
              {t('common.notes')} ({t('tasks.assignment.optional')})
            </Label>
            <Textarea
              id="notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder={t('projects.taskAssignment.notesPlaceholder')}
              rows={3}
            />
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center justify-end gap-3 border-t pt-4">
          <Button variant="outline" onClick={onClose} disabled={isAssigning}>
            {t('tasks.assignment.cancel')}
          </Button>
          <Button
            onClick={handleAssign}
            disabled={isAssigning || selectedUsers.length === 0}
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
