/**
 * Task Detail/Annotation page - Label Studio aligned task annotation interface
 *
 * This page provides the interface for annotating a specific task
 */

'use client'

import { ProtectedRoute } from '@/components/auth/ProtectedRoute'
import { logger } from '@/lib/utils/logger'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Button } from '@/components/shared/Button'
import { Textarea } from '@/components/shared/Textarea'
import { useToast } from '@/components/shared/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { projectsAPI } from '@/lib/api/projects'
import { useProjectStore } from '@/stores/projectStore'
import { Task } from '@/types/labelStudio'
import { CheckIcon, PencilIcon, XMarkIcon } from '@heroicons/react/24/outline'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'

interface TaskDetailPageProps {
  params: Promise<{
    id: string
    taskId: string
  }>
}

export default function TaskDetailPage({ params }: TaskDetailPageProps) {
  const router = useRouter()
  const [resolvedParams, setResolvedParams] = useState<{
    id: string
    taskId: string
  } | null>(null)
  const { addToast } = useToast()
  const { user } = useAuth()
  const { t } = useI18n()

  // Resolve params in useEffect to avoid potential issues with use() hook
  useEffect(() => {
    const resolveParams = async () => {
      try {
        const resolved = await params
        logger.debug('Resolved params:', resolved)
        setResolvedParams(resolved)
      } catch (error) {
        console.error('Error resolving params:', error)
      }
    }
    resolveParams()
  }, [params])

  const projectId = resolvedParams?.id
  const taskId = resolvedParams?.taskId

  // Debug logging
  logger.debug('TaskDetailPage - taskId:', taskId, 'type:', typeof taskId)
  logger.debug(
    'TaskDetailPage - projectId:',
    projectId,
    'type:',
    typeof projectId
  )

  const { currentProject, fetchProject } = useProjectStore()
  const [task, setTask] = useState<Task | null>(null)
  const [loading, setLoading] = useState(true)
  const [showAnnotations, setShowAnnotations] = useState(false)
  const [annotations, setAnnotations] = useState<any[]>([])
  const [loadingAnnotations, setLoadingAnnotations] = useState(false)

  // Editing state
  const [isEditing, setIsEditing] = useState(false)
  const [editedData, setEditedData] = useState('')
  const [isSaving, setIsSaving] = useState(false)

  // Load project if not already loaded
  useEffect(() => {
    if (projectId && (!currentProject || currentProject.id !== projectId)) {
      fetchProject(projectId)
    }
  }, [projectId, currentProject, fetchProject])

  // Load task details
  useEffect(() => {
    const loadTask = async () => {
      if (!taskId) {
        console.error('taskId is required but not provided')
        setLoading(false)
        return
      }

      logger.debug(
        'loadTask called with taskId:',
        taskId,
        'type:',
        typeof taskId
      )
      setLoading(true)
      try {
        logger.debug('About to call projectsAPI.getTask with:', taskId)
        const taskData = await projectsAPI.getTask(taskId)
        logger.debug('Task data received:', taskData)
        setTask(taskData)
      } catch (error) {
        console.error('Failed to load task:', error)
        addToast(t('tasks.detail.loadFailed'), 'error')
      } finally {
        setLoading(false)
      }
    }

    logger.debug(
      'useEffect [taskId] - taskId value:',
      taskId,
      'truthy:',
      !!taskId,
      'resolvedParams:',
      resolvedParams
    )
    if (taskId && resolvedParams) {
      loadTask()
    } else if (!taskId && resolvedParams) {
      console.warn('taskId is falsy but resolvedParams exist:', resolvedParams)
      setLoading(false)
    }
  }, [taskId, resolvedParams, addToast])

  // Load annotations for the task
  const loadAnnotations = async () => {
    if (!task || task.total_annotations === 0) {
      addToast(t('tasks.detail.noAnnotationsAvailable'), 'info')
      return
    }

    if (!taskId) {
      addToast(t('tasks.detail.taskIdNotAvailable'), 'error')
      return
    }

    setLoadingAnnotations(true)
    try {
      const annotationData = await projectsAPI.getTaskAnnotations(taskId)
      setAnnotations(annotationData)
      setShowAnnotations(true)
    } catch (error) {
      console.error('Failed to load annotations:', error)
      addToast(t('tasks.detail.loadAnnotationsFailed'), 'error')
    } finally {
      setLoadingAnnotations(false)
    }
  }

  // Handle starting edit mode
  const handleStartEdit = () => {
    if (task) {
      setEditedData(JSON.stringify((task as any).data, null, 2))
      setIsEditing(true)
    }
  }

  // Handle canceling edit
  const handleCancelEdit = () => {
    setIsEditing(false)
    setEditedData('')
  }

  // Handle saving edited data
  const handleSaveEdit = async () => {
    if (!task) return

    if (!projectId || !taskId) {
      addToast(t('tasks.detail.projectOrTaskIdNotAvailable'), 'error')
      return
    }

    try {
      // Parse the edited JSON
      const parsedData = JSON.parse(editedData)

      setIsSaving(true)

      // Update task data via API
      const updatedTask = await projectsAPI.updateTaskData(
        projectId,
        taskId,
        parsedData
      )

      // Update local state
      setTask({
        ...task,
        data: parsedData,
      })

      setIsEditing(false)
      addToast(t('tasks.detail.dataUpdated'), 'success')
    } catch (error: any) {
      if (error instanceof SyntaxError) {
        addToast(t('tasks.detail.invalidJson'), 'error')
      } else {
        console.error('Failed to update task data:', error)
        addToast(error.message || t('tasks.detail.dataUpdateFailed'), 'error')
      }
    } finally {
      setIsSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-center">
          <div className="mx-auto h-12 w-12 animate-spin rounded-full border-b-2 border-emerald-500"></div>
          <p className="mt-4 text-zinc-600 dark:text-zinc-400">
            {t('tasks.detail.loading')}
          </p>
        </div>
      </div>
    )
  }

  if (!task) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-center">
          <h2 className="mb-2 text-xl font-semibold text-zinc-900 dark:text-white">
            {t('tasks.detail.notFound')}
          </h2>
          <p className="mb-4 text-zinc-600 dark:text-zinc-400">
            {t('tasks.detail.notFoundDescription')}
          </p>
          <Button onClick={() => router.push(`/projects/${projectId}/data`)}>
            {t('tasks.detail.backToDataManager')}
          </Button>
        </div>
      </div>
    )
  }

  return (
    <ProtectedRoute>
      <div className="min-h-screen bg-zinc-50 dark:bg-zinc-900">
        {/* Header */}
        <div className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
          <div className="px-6 py-4">
            {/* Breadcrumb */}
            <Breadcrumb
              items={[
                { label: t('navigation.projects'), href: '/projects' },
                {
                  label: currentProject?.title || 'Project',
                  href: `/projects/${projectId}`,
                },
                { label: t('tasks.detail.backToDataManager'), href: `/projects/${projectId}/data` },
                {
                  label: t('tasks.detail.taskBreadcrumb', { id: task.id }),
                  href: `/projects/${projectId}/tasks/${task.id}`,
                },
              ]}
            />
          </div>
        </div>

        {/* Task Content */}
        <div className="p-6">
          <div className="mx-auto max-w-4xl">
            <div className="rounded-lg bg-white p-6 shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-900 dark:ring-white/10">
              <h2 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
                {t('tasks.detail.taskHeading', { id: task.id })}
              </h2>

              {/* Task Data Display */}
              <div className="mb-6">
                <div className="mb-2 flex items-center justify-between">
                  <h3 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    {t('tasks.detail.taskData')}
                  </h3>
                  {user?.is_superadmin && !isEditing && (
                    <Button
                      variant="outline"
                      onClick={handleStartEdit}
                      className="flex items-center gap-1"
                    >
                      <PencilIcon className="h-4 w-4" />
                      {t('tasks.detail.edit')}
                    </Button>
                  )}
                  {isEditing && (
                    <div className="flex items-center gap-2">
                      <Button
                        variant="primary"
                        onClick={handleSaveEdit}
                        disabled={isSaving}
                        className="flex items-center gap-1"
                      >
                        <CheckIcon className="h-4 w-4" />
                        {isSaving
                          ? t('tasks.detail.saving')
                          : t('tasks.detail.save')}
                      </Button>
                      <Button
                        variant="outline"
                        onClick={handleCancelEdit}
                        disabled={isSaving}
                        className="flex items-center gap-1"
                      >
                        <XMarkIcon className="h-4 w-4" />
                        {t('tasks.detail.cancel')}
                      </Button>
                    </div>
                  )}
                </div>
                {isEditing ? (
                  <div>
                    <Textarea
                      value={editedData}
                      onChange={(e) => setEditedData(e.target.value)}
                      rows={10}
                      className="w-full bg-zinc-50 font-mono text-sm text-zinc-900 dark:bg-zinc-800 dark:text-white"
                      placeholder={t('tasks.detail.editDataPlaceholder')}
                    />
                    <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                      {t('tasks.detail.editHelpText')}
                    </p>
                  </div>
                ) : (
                  <div className="rounded-lg bg-zinc-50 p-4 dark:bg-zinc-800">
                    <pre className="whitespace-pre-wrap text-sm text-zinc-900 dark:text-white">
                      {JSON.stringify((task as any).data, null, 2)}
                    </pre>
                  </div>
                )}
              </div>

              {/* Task Status */}
              <div className="mb-6 flex items-center justify-between">
                <div>
                  <span className="text-sm text-zinc-600 dark:text-zinc-400">
                    {t('tasks.detail.status')}:{' '}
                  </span>
                  <span
                    className={`inline-flex items-center rounded-md px-2 py-1 text-xs font-medium ${
                      task.is_labeled
                        ? 'bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-600/20 dark:bg-emerald-400/10 dark:text-emerald-400 dark:ring-emerald-400/30'
                        : 'bg-yellow-50 text-yellow-700 ring-1 ring-inset ring-yellow-600/20 dark:bg-yellow-400/10 dark:text-yellow-400 dark:ring-yellow-400/30'
                    }`}
                  >
                    {task.is_labeled
                      ? t('tasks.detail.labeled')
                      : t('tasks.detail.unlabeled')}
                  </span>
                </div>

                <div className="text-sm text-zinc-600 dark:text-zinc-400">
                  <span>
                    {t('tasks.detail.annotations')}: {task.total_annotations}
                  </span>
                  <span className="mx-2">•</span>
                  <span>
                    {t('tasks.detail.generations')}: {task.total_generations}
                  </span>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center justify-between">
                <Button
                  variant="primary"
                  onClick={() => router.push(`/projects/${projectId}/label`)}
                >
                  {t('tasks.detail.startLabeling')}
                </Button>

                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    onClick={loadAnnotations}
                    disabled={
                      loadingAnnotations ||
                      !task ||
                      task.total_annotations === 0
                    }
                  >
                    {loadingAnnotations
                      ? t('tasks.detail.loading')
                      : t('tasks.detail.viewAnnotations')}
                  </Button>
                  {currentProject?.show_skip_button !== false && (
                    <Button variant="outline">
                      {t('tasks.detail.skipTask')}
                    </Button>
                  )}
                </div>
              </div>
            </div>

            {/* Annotations Section (if any) */}
            {task.total_annotations > 0 && (
              <div className="mt-6 rounded-lg bg-white p-6 shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-900 dark:ring-white/10">
                <h3 className="mb-4 text-lg font-semibold text-zinc-900 dark:text-white">
                  {t('tasks.detail.existingAnnotations')}
                </h3>
                <p className="text-sm text-zinc-600 dark:text-zinc-400">
                  {t('tasks.detail.annotationCount', { count: task.total_annotations })}
                </p>
                {/* TODO: Load and display actual annotations */}
              </div>
            )}
          </div>
        </div>
      </div>
    </ProtectedRoute>
  )
}
