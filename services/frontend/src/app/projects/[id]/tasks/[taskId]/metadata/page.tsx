/**
 * Task Metadata Page - View and edit all metadata fields for a task
 *
 * Matches the design and feel of the task data page
 */

'use client'

import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Button } from '@/components/shared/Button'
import { Textarea } from '@/components/shared/Textarea'
import { useToast } from '@/components/shared/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import apiClient from '@/lib/api'
import { useProjectStore } from '@/stores/projectStore'
import { CheckIcon, PencilIcon, XMarkIcon } from '@heroicons/react/24/outline'
import { useRouter } from 'next/navigation'
import { use, useEffect, useState } from 'react'

interface TaskMetadataPageProps {
  params: Promise<{
    id: string
    taskId: string
  }>
}

export default function TaskMetadataPage({ params }: TaskMetadataPageProps) {
  const router = useRouter()
  const resolvedParams = use(params)
  const projectId = resolvedParams.id
  const taskId = resolvedParams.taskId

  const { t } = useI18n()
  const { addToast } = useToast()
  const { user } = useAuth()
  const { currentProject, fetchProject } = useProjectStore()

  const [task, setTask] = useState<any>(null)
  const [metadata, setMetadata] = useState<Record<string, any>>({})
  const [isEditing, setIsEditing] = useState(false)
  const [editedMetadata, setEditedMetadata] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [loading, setLoading] = useState(true)

  // Load project if not already loaded
  useEffect(() => {
    if (!currentProject || currentProject.id !== projectId) {
      fetchProject(projectId)
    }
  }, [projectId, currentProject, fetchProject])

  // Fetch task data
  useEffect(() => {
    const fetchTask = async () => {
      try {
        const response = await apiClient.get(`/api/projects/tasks/${taskId}`)
        setTask(response)
        setMetadata(response.meta || {})
      } catch (error) {
        console.error('Failed to fetch task:', error)
        addToast(t('tasks.metadata.loadFailed'), 'error')
      } finally {
        setLoading(false)
      }
    }

    fetchTask()
  }, [taskId, addToast, t])

  // Handle starting edit
  const handleStartEdit = () => {
    setEditedMetadata(JSON.stringify(metadata, null, 2))
    setIsEditing(true)
  }

  // Handle canceling edit
  const handleCancelEdit = () => {
    setIsEditing(false)
    setEditedMetadata('')
  }

  // Handle saving edited metadata
  const handleSaveEdit = async () => {
    if (!task) return

    try {
      // Parse the edited JSON
      const parsedMetadata = JSON.parse(editedMetadata)

      setIsSaving(true)

      // Update metadata via API - send the entire metadata object
      await apiClient.patch(
        `/api/projects/tasks/${taskId}/metadata`,
        parsedMetadata
      )

      // Update local state
      setTask({
        ...task,
        meta: parsedMetadata,
      })
      setMetadata(parsedMetadata)

      setIsEditing(false)
      addToast(t('tasks.metadata.updated'), 'success')
    } catch (error: any) {
      if (error instanceof SyntaxError) {
        addToast(t('tasks.metadata.invalidJson'), 'error')
      } else {
        console.error('Failed to update metadata:', error)
        addToast(error.message || t('tasks.metadata.updateFailed'), 'error')
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
            {t('tasks.metadata.loading')}
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
            {t('tasks.metadata.notFound')}
          </h2>
          <p className="mb-4 text-zinc-600 dark:text-zinc-400">
            {t('tasks.metadata.notFoundDescription')}
          </p>
          <Button onClick={() => router.push(`/projects/${projectId}/data`)}>
            {t('tasks.metadata.backToDataManager')}
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-900">
      {/* Header */}
      <div className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="px-6 py-4">
          {/* Breadcrumb */}
          <Breadcrumb
            items={[
              {
                label: t('navigation.dashboard') || 'Dashboard',
                href: '/dashboard',
              },
              {
                label: t('navigation.projects') || 'Projects',
                href: '/projects',
              },
              {
                label: currentProject?.title || 'Project',
                href: `/projects/${projectId}`,
              },
              {
                label: t('navigation.projectData') || 'Data',
                href: `/projects/${projectId}/data`,
              },
              {
                label: `${t('navigation.task')} ${task.id}`,
                href: `/projects/${projectId}/tasks/${task.id}`,
              },
              {
                label: t('navigation.metadata') || 'Metadata',
                href: `/projects/${projectId}/tasks/${task.id}/metadata`,
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
              {t('tasks.metadata.heading', { id: task.id })}
            </h2>

            {/* Metadata Display */}
            <div className="mb-6">
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                  {t('tasks.metadata.title')}
                </h3>
                {!isEditing && (
                  <Button
                    variant="outline"
                    onClick={handleStartEdit}
                    className="flex items-center gap-1"
                  >
                    <PencilIcon className="h-4 w-4" />
                    {t('tasks.metadata.edit')}
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
                      {isSaving ? t('tasks.metadata.saving') : t('tasks.metadata.save')}
                    </Button>
                    <Button
                      variant="outline"
                      onClick={handleCancelEdit}
                      disabled={isSaving}
                      className="flex items-center gap-1"
                    >
                      <XMarkIcon className="h-4 w-4" />
                      {t('tasks.metadata.cancel')}
                    </Button>
                  </div>
                )}
              </div>
              {isEditing ? (
                <div>
                  <Textarea
                    value={editedMetadata}
                    onChange={(e) => setEditedMetadata(e.target.value)}
                    rows={10}
                    className="w-full bg-zinc-50 font-mono text-sm text-zinc-900 dark:bg-zinc-800 dark:text-white"
                    placeholder={t('tasks.metadata.jsonPlaceholder')}
                  />
                  <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
                    {t('tasks.metadata.jsonHelpText')}
                  </p>
                </div>
              ) : (
                <pre className="overflow-auto rounded-lg bg-zinc-50 p-4 font-mono text-sm text-zinc-900 dark:bg-zinc-800 dark:text-white">
                  {JSON.stringify(metadata, null, 2)}
                </pre>
              )}
            </div>

            {/* Status Info */}
            <div className="flex items-center justify-between text-sm text-zinc-600 dark:text-zinc-400">
              <div className="flex items-center gap-4">
                <span>
                  {t('tasks.metadata.status')}{' '}
                  {task.is_labeled ? (
                    <span className="font-medium text-emerald-600 dark:text-emerald-400">
                      {t('tasks.metadata.completed')}
                    </span>
                  ) : (
                    <span className="font-medium text-amber-600 dark:text-amber-400">
                      {t('tasks.metadata.unlabeled')}
                    </span>
                  )}
                </span>
                <span>{t('tasks.metadata.annotations', { count: task.total_annotations || 0 })}</span>
                <span>{t('tasks.metadata.generations', { count: task.total_generations || 0 })}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
