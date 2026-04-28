/**
 * My Tasks page - Shows tasks assigned to the current user
 *
 * This page allows annotators to see and work on their assigned tasks
 * with priority sorting and status filtering
 */

'use client'

import { Badge } from '@/components/shared/Badge'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Button } from '@/components/shared/Button'
import { Card } from '@/components/shared/Card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shared/Select'
import { useToast } from '@/components/shared/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { useProjectStore } from '@/stores/projectStore'
import { Task, TaskAssignment } from '@/types/labelStudio'
import {
  CalendarIcon,
  ChatBubbleLeftRightIcon,
  CheckCircleIcon,
  ChevronRightIcon,
  ClockIcon,
  DocumentTextIcon,
  FlagIcon,
} from '@heroicons/react/24/outline'
import { formatDistanceToNow } from 'date-fns'
import { useParams, useRouter } from 'next/navigation'
import { useCallback, useEffect, useState } from 'react'

interface MyTask extends Task {
  assignment?: TaskAssignment
  has_feedback?: boolean
}

interface MyTasksResponse {
  tasks: MyTask[]
  total: number
  page: number
  page_size: number
  pages: number
}

export default function MyTasksPage() {
  const router = useRouter()
  const params = useParams()
  const projectId = params?.id as string
  const { user } = useAuth()
  const { addToast } = useToast()
  const { t } = useI18n()
  const {
    currentProject,
    fetchProject,
    loading: projectLoading,
  } = useProjectStore()

  // State
  const [tasks, setTasks] = useState<MyTask[]>([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [totalTasks, setTotalTasks] = useState(0)

  // Load project if not already loaded
  useEffect(() => {
    if (!currentProject || currentProject.id !== projectId) {
      fetchProject(projectId)
    }
  }, [projectId, currentProject, fetchProject])

  const loadMyTasks = useCallback(async () => {
    try {
      setLoading(true)
      const response = await fetch(
        `/api/projects/${projectId}/my-tasks?page=${page}&page_size=20${
          statusFilter !== 'all' ? `&status=${statusFilter}` : ''
        }`,
        {
          credentials: 'include',
        }
      )

      if (!response.ok) {
        throw new Error(t('tasks.myTasks.loadFailed'))
      }

      const data: MyTasksResponse = await response.json()
      setTasks(data.tasks)
      setTotalPages(data.pages)
      setTotalTasks(data.total)
    } catch (error) {
      console.error('Error loading tasks:', error)
      addToast(t('tasks.myTasks.loadFailed'), 'error')
    } finally {
      setLoading(false)
    }
  }, [projectId, statusFilter, page, addToast])

  // Load assigned tasks
  useEffect(() => {
    loadMyTasks()
  }, [loadMyTasks])

  const startAnnotating = (task: MyTask) => {
    if (task.has_feedback) {
      router.push(`/projects/${projectId}/my-korrektur/${task.id}`)
      return
    }
    // Save task ID so the labeling interface loads this specific task
    if (typeof window !== 'undefined') {
      localStorage.setItem(`benger_task_id_${projectId}`, task.id)
    }
    router.push(`/projects/${projectId}/label`)
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'assigned':
        return <Badge variant="default">{t('tasks.myTasks.assigned')}</Badge>
      case 'in_progress':
        return <Badge variant="secondary">{t('tasks.myTasks.inProgress')}</Badge>
      case 'completed':
        return <Badge variant="default">{t('tasks.myTasks.completed')}</Badge>
      case 'skipped':
        return <Badge variant="secondary">{t('tasks.myTasks.skipped')}</Badge>
      default:
        return <Badge>{status}</Badge>
    }
  }

  const getPriorityIcon = (priority: number) => {
    if (priority >= 3) {
      return <FlagIcon className="h-4 w-4 text-red-500" />
    } else if (priority >= 2) {
      return <FlagIcon className="h-4 w-4 text-orange-500" />
    } else if (priority >= 1) {
      return <FlagIcon className="h-4 w-4 text-yellow-500" />
    }
    return null
  }


  if (projectLoading || !currentProject) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-center">
          <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-b-2 border-emerald-600"></div>
          <p className="text-sm text-zinc-500">{t('common.loadingProject')}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="container mx-auto max-w-7xl px-4 py-8">
      {/* Breadcrumb */}
      <Breadcrumb
        items={[
          {
            label: t('navigation.dashboard'),
            href: '/dashboard',
          },
          { label: t('navigation.projects'), href: '/projects' },
          { label: currentProject.title, href: `/projects/${projectId}` },
          {
            label: t('navigation.myTasks'),
            href: `/projects/${projectId}/my-tasks`,
          },
        ]}
      />

      {/* Header */}
      <div className="mb-8">
        <h1 className="mb-2 text-3xl font-bold text-zinc-900 dark:text-white">
          {t('tasks.myTasks.title')}
        </h1>
        <p className="text-zinc-600 dark:text-zinc-400">
          {t('tasks.myTasks.description')} {currentProject.title}
        </p>
      </div>

      {/* Filters and Stats */}
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('tasks.myTasks.allTasks')}</SelectItem>
              <SelectItem value="assigned">{t('tasks.myTasks.assigned')}</SelectItem>
              <SelectItem value="in_progress">{t('tasks.myTasks.inProgress')}</SelectItem>
              <SelectItem value="completed">{t('tasks.myTasks.completed')}</SelectItem>
              <SelectItem value="skipped">{t('tasks.myTasks.skipped')}</SelectItem>
            </SelectContent>
          </Select>

          <div className="text-sm text-zinc-500">
            {totalTasks} {t('tasks.myTasks.tasksAssigned')}
          </div>
        </div>

        <Button
          onClick={() => router.push(`/projects/${projectId}/annotate`)}
          className="bg-emerald-600 hover:bg-emerald-700"
        >
          {t('tasks.myTasks.startAnnotating')}
        </Button>
      </div>

      {/* Tasks List */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="text-center">
            <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-b-2 border-emerald-600"></div>
            <p className="text-sm text-zinc-500">{t('tasks.myTasks.loadingTasks')}</p>
          </div>
        </div>
      ) : tasks.length === 0 ? (
        <Card className="p-12 text-center" data-testid="my-tasks-empty">
          <DocumentTextIcon className="mx-auto mb-4 h-12 w-12 text-zinc-400" />
          <h3 className="mb-2 text-lg font-semibold text-zinc-900 dark:text-white">
            {t('tasks.myTasks.noTasks')}
          </h3>
          <p className="text-zinc-600 dark:text-zinc-400">
            {statusFilter === 'all'
              ? t('tasks.myTasks.noTasks')
              : t('tasks.myTasks.noTasksWithStatus', { status: statusFilter })}
          </p>
        </Card>
      ) : (
        <div className="space-y-4" data-testid="my-tasks-list">
          {tasks.map((task) => (
            <Card
              key={task.id}
              data-testid="my-task-item"
              className="cursor-pointer p-6 transition-shadow hover:shadow-lg"
              onClick={() => startAnnotating(task)}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="mb-2 flex items-center gap-3">
                    <span className="text-sm font-medium text-zinc-500">
                      {t('tasks.myTasks.taskPrefix')} #{task.inner_id || task.id}
                    </span>
                    {task.assignment &&
                      getPriorityIcon(task.assignment.priority)}
                    {task.assignment && getStatusBadge(task.assignment.status)}
                    {task.is_labeled && (
                      <Badge variant="default">
                        <CheckCircleIcon className="mr-1 h-3 w-3" />
                        {t('tasks.myTasks.labeled')}
                      </Badge>
                    )}
                    {task.has_feedback && (
                      <Badge className="bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300">
                        <ChatBubbleLeftRightIcon className="mr-1 h-3 w-3" />
                        {t('tasks.myTasks.feedbackAvailable')}
                      </Badge>
                    )}
                  </div>

                  {task.assignment && (
                    <div className="flex items-center gap-4 text-sm text-zinc-500">
                      <div className="flex items-center gap-1">
                        <ClockIcon className="h-4 w-4" />
                        {t('tasks.myTasks.assigned')}{' '}
                        {formatDistanceToNow(
                          new Date(task.assignment.assigned_at),
                          { addSuffix: true }
                        )}
                      </div>

                      {task.assignment.due_date && (
                        <div className="flex items-center gap-1">
                          <CalendarIcon className="h-4 w-4" />
                          {t('tasks.myTasks.due')}{' '}
                          {formatDistanceToNow(
                            new Date(task.assignment.due_date),
                            { addSuffix: true }
                          )}
                        </div>
                      )}

                      {task.assignment.notes && (
                        <div className="flex items-center gap-1">
                          <DocumentTextIcon className="h-4 w-4" />
                          {task.assignment.notes}
                        </div>
                      )}
                    </div>
                  )}
                </div>

                <ChevronRightIcon className="ml-4 h-5 w-5 text-zinc-400" />
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="mt-8 flex items-center justify-center gap-2">
          <Button
            variant="outline"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
          >
            {t('common.previous')}
          </Button>

          <span className="px-4 text-sm text-zinc-600">
            {t('common.pageOf', { page, totalPages })}
          </span>

          <Button
            variant="outline"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
          >
            {t('common.next')}
          </Button>
        </div>
      )}
    </div>
  )
}
