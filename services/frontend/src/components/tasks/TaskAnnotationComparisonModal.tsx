'use client'

import { AnnotationCreator } from '@/components/labeling/AnnotationCreator'
import { logger } from '@/lib/utils/logger'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { projectsAPI } from '@/lib/api/projects'
import { User } from '@/lib/api/types'
import { UsersClient } from '@/lib/api/users'
import type {
  Annotation,
  AnnotationResult,
  Project,
  Task,
} from '@/types/labelStudio'
import { Dialog, DialogPanel, DialogTitle, Tab } from '@headlessui/react'
import {
  CheckCircleIcon,
  ClockIcon,
  DocumentTextIcon,
  ExclamationTriangleIcon,
  PencilIcon,
  PlusCircleIcon,
  UserCircleIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

interface TaskAnnotationComparisonModalProps {
  task: Task | null
  isOpen: boolean
  onClose: () => void
  onAnnotationAdded?: () => void
  onViewRawData?: () => void
  projectId: string
}

interface AnnotatorTab {
  userId: string
  username: string
  email: string
  annotations: Annotation[]
  status: 'draft' | 'submitted' | 'approved' | 'rejected'
  lastUpdated: string
  displayedAnnotations?: number // For lazy loading
}

export function TaskAnnotationComparisonModal({
  task,
  isOpen,
  onClose,
  onAnnotationAdded,
  onViewRawData,
  projectId,
}: TaskAnnotationComparisonModalProps) {
  const [annotations, setAnnotations] = useState<Annotation[]>([])
  const [annotatorTabs, setAnnotatorTabs] = useState<AnnotatorTab[]>([])
  const [selectedTab, setSelectedTab] = useState(0)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [users, setUsers] = useState<Map<string, User>>(new Map())
  const [mode, setMode] = useState<'view' | 'create'>('view')
  const [showAddAnnotation, setShowAddAnnotation] = useState(false)
  const [editingAnnotation, setEditingAnnotation] = useState<Annotation | null>(
    null
  )
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [justCreated, setJustCreated] = useState(false)
  const justCreatedRef = useRef(justCreated)
  justCreatedRef.current = justCreated
  const [project, setProject] = useState<Project | null>(null)
  // Track how many annotations to display per annotator (userId -> count)
  const [displayedAnnotations, setDisplayedAnnotations] = useState<
    Map<string, number>
  >(new Map())
  const { user } = useAuth()
  const { t } = useI18n()

  // Create users client instance
  const usersClient = useMemo(() => new UsersClient(), [])

  const fetchAnnotations = useCallback(async () => {
    if (!task) return

    setIsLoading(true)
    setError(null)

    try {
      // Fetch all annotations for this task
      const allAnnotations = await projectsAPI.getTaskAnnotations(task.id)

      if (allAnnotations.length === 0) {
        setAnnotations([])
        setAnnotatorTabs([])
        // Automatically switch to create mode for empty tasks
        // This follows LabelStudio's pattern of immediate annotation interface
        if (!justCreatedRef.current) {
          setMode('create')
        }
        setIsLoading(false)
        return
      }

      // We have annotations, stay in view mode
      setMode('view')
      setJustCreated(false) // Clear the flag since we have annotations now

      setAnnotations(allAnnotations)

      // Try to fetch all users for mapping (this might fail if not admin)
      let userMap = new Map<string, User>()
      try {
        const allUsers = await usersClient.getAllUsers()
        userMap = new Map(allUsers.map((u) => [u.id, u]))
        setUsers(userMap)
      } catch (err) {
        logger.debug('Could not fetch users list (might not be admin)')
      }

      // Group annotations by completed_by (user)
      const annotationsByUser = new Map<string, Annotation[]>()

      for (const annotation of allAnnotations) {
        const userId = annotation.completed_by
        if (!userId) continue // Skip if no user ID
        if (!annotationsByUser.has(userId)) {
          annotationsByUser.set(userId, [])
        }
        annotationsByUser.get(userId)!.push(annotation)
      }

      // Create tabs for each annotator
      const tabs: AnnotatorTab[] = []

      for (const [userId, userAnnotations] of annotationsByUser) {
        // Get the most recent annotation
        const latestAnnotation = userAnnotations.reduce((latest, current) => {
          const latestDate = new Date(latest.updated_at || latest.created_at)
          const currentDate = new Date(current.updated_at || current.created_at)
          return currentDate > latestDate ? current : latest
        })

        // Get user info from map or use fallback
        const userInfo = userMap.get(userId)
        const username =
          userInfo?.username ||
          userInfo?.full_name ||
          `Annotator ${userId ? userId.substring(0, 8) : 'Unknown'}`
        const email = userInfo?.email || ''

        // Determine status based on annotation properties
        const status = latestAnnotation.was_cancelled
          ? 'draft'
          : latestAnnotation.ground_truth
            ? 'approved'
            : 'submitted'

        tabs.push({
          userId,
          username,
          email,
          annotations: userAnnotations.sort((a, b) => {
            const dateA = new Date(a.updated_at || a.created_at).getTime()
            const dateB = new Date(b.updated_at || b.created_at).getTime()
            return dateB - dateA
          }),
          status: status as 'draft' | 'submitted' | 'approved' | 'rejected',
          lastUpdated:
            latestAnnotation.updated_at || latestAnnotation.created_at,
        })
      }

      // Sort tabs by last updated
      tabs.sort(
        (a, b) =>
          new Date(b.lastUpdated).getTime() - new Date(a.lastUpdated).getTime()
      )

      // Set current user's tab as selected if they have annotations
      const currentUserTabIndex = tabs.findIndex(
        (tab) => tab.userId === user?.id
      )
      if (currentUserTabIndex !== -1) {
        setSelectedTab(currentUserTabIndex)
      }

      setAnnotatorTabs(tabs)

      // Initialize displayed annotation counts (show 5 per annotator by default)
      const initialCounts = new Map<string, number>()
      tabs.forEach((tab) => {
        initialCounts.set(tab.userId, 5)
      })
      setDisplayedAnnotations(initialCounts)
    } catch (err) {
      console.error('Error fetching annotations:', err)
      setError(t('annotation.comparison.messages.loadFailed'))
    } finally {
      setIsLoading(false)
    }
  }, [task, t, usersClient, user?.id])

  const fetchProjectAndAnnotations = useCallback(async () => {
    try {
      // Fetch project details to get label_config
      const projectData = await projectsAPI.get(projectId)
      setProject(projectData)
      // Then fetch annotations
      await fetchAnnotations()
    } catch (err) {
      console.error('Error fetching project:', err)
      setError(t('annotation.comparison.messages.projectLoadFailed'))
    }
  }, [projectId, t, fetchAnnotations])

  // Fetch project and annotations when modal opens
  useEffect(() => {
    if (isOpen && task && projectId) {
      fetchProjectAndAnnotations()
    } else if (!isOpen) {
      // Clear editing state when modal closes
      setEditingAnnotation(null)
      setShowAddAnnotation(false)
      setJustCreated(false)
    }
  }, [isOpen, task, projectId, fetchProjectAndAnnotations])

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'submitted':
        return <CheckCircleIcon className="h-4 w-4 text-green-600" />
      case 'approved':
        return <CheckCircleIcon className="h-4 w-4 text-blue-600" />
      case 'rejected':
        return <ExclamationTriangleIcon className="h-4 w-4 text-red-600" />
      case 'draft':
      default:
        return <ClockIcon className="h-4 w-4 text-gray-500" />
    }
  }

  const getStatusBadgeClass = (status: string) => {
    switch (status) {
      case 'submitted':
        return 'bg-green-100 text-green-800 dark:bg-green-900/20 dark:text-green-400'
      case 'approved':
        return 'bg-blue-100 text-blue-800 dark:bg-blue-900/20 dark:text-blue-400'
      case 'rejected':
        return 'bg-red-100 text-red-800 dark:bg-red-900/20 dark:text-red-400'
      case 'draft':
      default:
        return 'bg-gray-100 text-gray-800 dark:bg-gray-900/20 dark:text-gray-400'
    }
  }

  const renderAnnotationResult = (result: AnnotationResult[]) => {
    if (!result || result.length === 0) {
      return (
        <div className="py-8 text-center text-gray-500">
          {t('annotation.comparison.messages.noData')}
        </div>
      )
    }

    return (
      <div className="space-y-4">
        {result.map((item, index) => (
          <div
            key={index}
            className="rounded-lg border border-gray-200 p-4 dark:border-gray-700"
          >
            <div className="mb-2">
              <label className="font-medium text-gray-900 dark:text-white">
                {item.from_name}
              </label>
              <span className="ml-2 text-sm text-gray-500">({item.type})</span>
            </div>
            <div className="text-gray-700 dark:text-gray-300">
              {renderAnnotationValue(item.value, item.from_name)}
            </div>
          </div>
        ))}
      </div>
    )
  }

  const renderAnnotationValue = (
    value: any,
    fieldName: string
  ): React.ReactNode => {
    if (value === null || value === undefined) {
      return (
        <span className="italic text-gray-500">
          {t('annotation.comparison.result.notAnswered')}
        </span>
      )
    }

    if (typeof value === 'boolean') {
      return (
        <span className={value ? 'text-green-600' : 'text-red-600'}>
          {value
            ? t('annotation.comparison.result.yes')
            : t('annotation.comparison.result.no')}
        </span>
      )
    }

    if (Array.isArray(value)) {
      return (
        <ul className="list-disc space-y-1 pl-5">
          {value.map((item, index) => (
            <li key={index} className="text-sm">
              {String(item)}
            </li>
          ))}
        </ul>
      )
    }

    if (typeof value === 'object') {
      return (
        <div className="mt-1 rounded bg-gray-50 p-2 dark:bg-gray-800">
          <pre className="overflow-x-auto text-xs">
            {JSON.stringify(value, null, 2)}
          </pre>
        </div>
      )
    }

    if (typeof value === 'number') {
      return <span className="font-mono">{value}</span>
    }

    // String or other primitive values
    const stringValue = String(value)
    if (stringValue.length > 200) {
      return (
        <div className="space-y-2">
          <p className="whitespace-pre-wrap break-words">
            {stringValue.substring(0, 200)}...
          </p>
          <details className="cursor-pointer">
            <summary className="text-sm text-blue-600 hover:text-blue-800">
              {t('annotation.comparison.result.showFullText')}
            </summary>
            <p className="mt-2 whitespace-pre-wrap break-words">
              {stringValue}
            </p>
          </details>
        </div>
      )
    }

    return <p className="whitespace-pre-wrap break-words">{stringValue}</p>
  }

  const renderAnnotationFields = (annotation: Annotation) => {
    return renderAnnotationResult(annotation.result || [])
  }

  if (!task) return null

  return (
    <Dialog open={isOpen} onClose={onClose} className="relative z-50">
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/30" aria-hidden="true" />

      {/* Full-screen container - responsive padding */}
      <div className="fixed inset-0 flex w-screen items-center justify-center p-2 sm:p-4">
        <DialogPanel className="flex max-h-[95vh] w-full max-w-6xl flex-col rounded-lg bg-white shadow-xl dark:bg-zinc-900 sm:max-h-[90vh]">
          {/* Header - responsive padding and text size */}
          <div className="flex items-start justify-between border-b border-gray-200 p-4 dark:border-gray-700 sm:items-center sm:p-6">
            <div className="mr-2 min-w-0 flex-1">
              <DialogTitle className="truncate text-base font-semibold text-gray-900 dark:text-white sm:text-lg">
                {t('annotation.comparison.modal.title')}
                <span className="hidden sm:inline">
                  {' '}
                  -{' '}
                  {t('annotation.comparison.modal.taskId', { taskId: task.id })}
                </span>
              </DialogTitle>
              <p className="mt-1 text-xs text-gray-600 dark:text-gray-400 sm:text-sm">
                {t('annotation.comparison.description')}
              </p>
            </div>
            <button
              onClick={onClose}
              className="rounded-lg p-1.5 text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-white sm:p-2"
            >
              <XMarkIcon className="h-4 w-4 sm:h-5 sm:w-5" />
            </button>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-hidden">
            {isLoading ? (
              <div className="flex items-center justify-center py-12">
                <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-blue-600"></div>
              </div>
            ) : error ? (
              <div className="flex flex-col items-center justify-center py-12">
                <ExclamationTriangleIcon className="mb-4 h-12 w-12 text-red-500" />
                <p className="text-red-600">{error}</p>
                <button
                  onClick={fetchAnnotations}
                  className="mt-4 rounded bg-blue-600 px-4 py-2 text-white hover:bg-blue-700"
                >
                  {t('annotation.comparison.modal.retry')}
                </button>
              </div>
            ) : annotatorTabs.length === 0 ? (
              // Automatically show annotation creator interface for empty tasks
              mode === 'create' && project?.label_config ? (
                // Show annotation creator interface immediately - LabelStudio pattern
                <div className="p-6">
                  <div className="mb-4 rounded-lg bg-blue-50 p-4 dark:bg-blue-900/20">
                    <h3 className="flex items-center gap-2 text-sm font-medium text-blue-900 dark:text-blue-100">
                      <PencilIcon className="h-4 w-4" />
                      {t('annotation.comparison.tabs.createNew')}
                    </h3>
                    <p className="mt-1 text-xs text-blue-700 dark:text-blue-300">
                      {t('annotation.comparison.empty.noAnnotationsYet')}
                    </p>
                  </div>
                  <AnnotationCreator
                    task={task}
                    projectId={projectId}
                    labelConfig={project.label_config}
                    onSubmit={async (annotation) => {
                      setSuccessMessage(
                        t('annotation.comparison.messages.annotationSubmitted')
                      )
                      setJustCreated(true)

                      // Clear success message after 3 seconds
                      setTimeout(() => setSuccessMessage(null), 3000)

                      // Small delay to ensure backend has processed the annotation
                      await new Promise((resolve) => setTimeout(resolve, 500))

                      // Refresh annotations and switch to view mode
                      await fetchAnnotations()
                      // Force view mode even if no annotations returned yet
                      setMode('view')
                      if (onAnnotationAdded) {
                        onAnnotationAdded()
                      }
                    }}
                    onCancel={() => {
                      // Close the modal when cancelled on an empty task
                      onClose()
                    }}
                  />
                  {successMessage && (
                    <div className="mt-4 rounded-lg bg-green-50 p-4 text-green-800 dark:bg-green-900/20 dark:text-green-400">
                      {successMessage}
                    </div>
                  )}
                </div>
              ) : // Show loading state when just created
              justCreated ? (
                <div className="flex flex-col items-center justify-center py-12">
                  <div className="mb-4 h-8 w-8 animate-spin rounded-full border-b-2 border-blue-600"></div>
                  <p className="text-gray-600 dark:text-gray-400">
                    {t('annotation.comparison.messages.loadingUserAnnotation')}
                  </p>
                  <p className="mt-2 text-sm text-gray-500 dark:text-gray-500">
                    {t('annotation.comparison.messages.waitingForAnnotation')}
                  </p>
                </div>
              ) : (
                // Fallback empty state (should rarely be seen)
                <div className="flex flex-col items-center justify-center py-12">
                  <DocumentTextIcon className="mb-4 h-12 w-12 text-gray-400" />
                  <p className="text-gray-600 dark:text-gray-400">
                    {t('annotation.comparison.empty.noAnnotationsAvailable')}
                  </p>
                </div>
              )
            ) : showAddAnnotation && project?.label_config ? (
              // User is adding a new annotation or editing existing one
              <div className="p-6">
                <div className="mb-4 rounded-lg bg-blue-50 p-4 dark:bg-blue-900/20">
                  <h3 className="flex items-center gap-2 text-sm font-medium text-blue-900 dark:text-blue-100">
                    {editingAnnotation ? (
                      <>
                        <PencilIcon className="h-4 w-4" />
                        {t('annotation.comparison.tabs.editYourAnnotation')}
                      </>
                    ) : (
                      <>
                        <PlusCircleIcon className="h-4 w-4" />
                        {t('annotation.comparison.tabs.addYourAnnotation')}
                      </>
                    )}
                  </h3>
                  <p className="mt-1 text-xs text-blue-700 dark:text-blue-300">
                    {editingAnnotation
                      ? t('annotation.comparison.tabs.updateExisting')
                      : t('annotation.comparison.tabs.addNew')}
                  </p>
                </div>
                <AnnotationCreator
                  task={task}
                  projectId={projectId}
                  labelConfig={project.label_config}
                  initialAnnotation={editingAnnotation}
                  onSubmit={async (annotation) => {
                    setSuccessMessage(
                      editingAnnotation
                        ? t('annotation.comparison.messages.annotationUpdated')
                        : t(
                            'annotation.comparison.messages.annotationSubmitted'
                          )
                    )
                    setJustCreated(!editingAnnotation) // Only set if creating new, not editing

                    // Clear success message after 3 seconds
                    setTimeout(() => setSuccessMessage(null), 3000)

                    // Small delay to ensure backend has processed the annotation
                    await new Promise((resolve) => setTimeout(resolve, 500))

                    // Refresh and close
                    await fetchAnnotations()
                    setShowAddAnnotation(false)
                    setEditingAnnotation(null)
                    if (onAnnotationAdded) {
                      onAnnotationAdded()
                    }
                  }}
                  onCancel={() => {
                    setShowAddAnnotation(false)
                    setEditingAnnotation(null)
                  }}
                />
                {successMessage && (
                  <div className="mt-4 rounded-lg bg-green-50 p-4 text-green-800 dark:bg-green-900/20 dark:text-green-400">
                    {successMessage}
                  </div>
                )}
              </div>
            ) : (
              <Tab.Group selectedIndex={selectedTab} onChange={setSelectedTab}>
                {/* Tab List with horizontal scroll */}
                <div className="border-b border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800">
                  <Tab.List className="scrollbar-thin scrollbar-thumb-gray-400 scrollbar-track-gray-200 dark:scrollbar-thumb-gray-600 dark:scrollbar-track-gray-800 flex space-x-1 overflow-x-auto px-4 py-2 sm:px-6">
                    {annotatorTabs.map((tab) => (
                      <Tab
                        key={tab.userId}
                        className={({ selected }) =>
                          `flex flex-shrink-0 items-center gap-2 whitespace-nowrap rounded-t-lg px-3 py-2 text-xs font-medium transition-colors sm:px-4 sm:text-sm ${
                            selected
                              ? 'border-b-2 border-blue-600 bg-white text-blue-600 dark:bg-zinc-900 dark:text-blue-400'
                              : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-700 dark:hover:text-white'
                          }`
                        }
                      >
                        <UserCircleIcon className="h-3 w-3 flex-shrink-0 sm:h-4 sm:w-4" />
                        <span className="max-w-[150px] truncate sm:max-w-none">
                          {tab.username}
                        </span>
                        {getStatusIcon(tab.status)}
                        {tab.annotations.length > 1 && (
                          <span className="ml-1 rounded-full bg-gray-200 px-1.5 py-0.5 text-xs dark:bg-gray-700">
                            {tab.annotations.length}
                          </span>
                        )}
                      </Tab>
                    ))}
                  </Tab.List>
                </div>

                {/* Tab Panels */}
                <Tab.Panels className="flex-1 overflow-y-auto">
                  {annotatorTabs.map((tab) => (
                    <Tab.Panel key={tab.userId} className="p-4 sm:p-6">
                      {/* Annotator Info */}
                      <div className="mb-6 rounded-lg bg-gray-50 p-4 dark:bg-gray-800">
                        <div className="flex items-start justify-between">
                          <div>
                            <h3 className="font-medium text-gray-900 dark:text-white">
                              {tab.username}
                            </h3>
                            {tab.email && (
                              <p className="text-sm text-gray-600 dark:text-gray-400">
                                {tab.email}
                              </p>
                            )}
                          </div>
                          <span
                            className={`rounded-full px-3 py-1 text-xs font-medium ${getStatusBadgeClass(
                              tab.status
                            )}`}
                          >
                            {t(`annotation.comparison.status.${tab.status}`)}
                          </span>
                        </div>
                        <div className="mt-3 text-sm text-gray-600 dark:text-gray-400">
                          {t('annotation.comparison.info.lastUpdated', {
                            date: new Date(tab.lastUpdated).toLocaleString(),
                          })}
                        </div>
                        {tab.annotations[0]?.metadata?.time_spent && (
                          <div className="mt-1 text-sm text-gray-600 dark:text-gray-400">
                            {t('annotation.comparison.info.timeSpent', {
                              seconds: Math.round(
                                tab.annotations[0].metadata.time_spent / 1000
                              ),
                            })}
                          </div>
                        )}
                        {tab.annotations[0]?.metadata?.confidence !==
                          undefined && (
                          <div className="mt-1 text-sm text-gray-600 dark:text-gray-400">
                            {t('annotation.comparison.info.confidence', {
                              percent: Math.round(
                                tab.annotations[0].metadata.confidence * 100
                              ),
                            })}
                          </div>
                        )}
                      </div>

                      {/* Annotation Data with Lazy Loading */}
                      {tab.annotations.length > 1 ? (
                        <div className="space-y-6">
                          <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
                            {t('annotation.comparison.info.showingVersions', {
                              count: tab.annotations.length,
                            })}
                          </p>
                          {tab.annotations
                            .slice(0, displayedAnnotations.get(tab.userId) || 5)
                            .map((annotation, index) => (
                              <div
                                key={annotation.id}
                                className="border-l-4 border-blue-500 pl-4"
                              >
                                <div className="mb-2 text-sm text-gray-600 dark:text-gray-400">
                                  {t(
                                    'annotation.comparison.info.versionLabel',
                                    {
                                      version: tab.annotations.length - index,
                                      date: new Date(
                                        annotation.updated_at ||
                                          annotation.created_at
                                      ).toLocaleString(),
                                    }
                                  )}
                                </div>
                                {renderAnnotationFields(annotation)}
                              </div>
                            ))}
                          {tab.annotations.length >
                            (displayedAnnotations.get(tab.userId) || 5) && (
                            <div className="pt-4 text-center">
                              <button
                                className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
                                onClick={() => {
                                  // Load 5 more annotations for this annotator
                                  setDisplayedAnnotations((prev) => {
                                    const newMap = new Map(prev)
                                    const currentCount =
                                      newMap.get(tab.userId) || 5
                                    newMap.set(tab.userId, currentCount + 5)
                                    return newMap
                                  })
                                }}
                              >
                                {t('annotation.comparison.buttons.loadMore', {
                                  count:
                                    tab.annotations.length -
                                    (displayedAnnotations.get(tab.userId) || 5),
                                })}
                              </button>
                            </div>
                          )}
                        </div>
                      ) : (
                        renderAnnotationFields(tab.annotations[0])
                      )}

                      {/* Notes if available */}
                      {tab.annotations[0]?.metadata?.notes && (
                        <div className="mt-6 rounded-lg bg-yellow-50 p-4 dark:bg-yellow-900/20">
                          <h4 className="mb-2 font-medium text-gray-900 dark:text-white">
                            {t('annotation.comparison.info.annotatorNotes')}
                          </h4>
                          <p className="text-sm text-gray-700 dark:text-gray-300">
                            {tab.annotations[0].metadata.notes}
                          </p>
                        </div>
                      )}
                    </Tab.Panel>
                  ))}
                </Tab.Panels>
              </Tab.Group>
            )}
          </div>

          {/* Footer - responsive layout with enhanced button visibility */}
          {(annotatorTabs.length > 0 ||
            (mode === 'view' && !showAddAnnotation)) && (
            <div className="border-t border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-gray-800 sm:p-6">
              <div className="flex flex-col items-center justify-between gap-4 sm:flex-row">
                {/* Left side - statistics and primary action button */}
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-6">
                  {/* Statistics */}
                  <div className="text-center text-xs text-gray-600 dark:text-gray-400 sm:text-left sm:text-sm">
                    <span className="font-medium">
                      {t('annotation.comparison.info.annotatorCount', {
                        count: annotatorTabs.length,
                        plural: annotatorTabs.length !== 1 ? 's' : '',
                      })}
                    </span>
                    {' • '}
                    <span>
                      {t('annotation.comparison.info.totalAnnotations', {
                        count: annotations.length,
                        plural: annotations.length !== 1 ? 's' : '',
                      })}
                    </span>
                  </div>

                  {/* Primary action button - more prominent */}
                  {(() => {
                    // Check if current user has already annotated
                    const userHasAnnotated = annotatorTabs.some(
                      (tab) => tab.userId === user?.id
                    )

                    if (!user || mode !== 'view' || showAddAnnotation) {
                      return null
                    }

                    if (userHasAnnotated) {
                      // User has annotated - show edit button
                      return (
                        <button
                          onClick={() => {
                            // Find the user's most recent annotation to edit
                            const userTab = annotatorTabs.find(
                              (tab) => tab.userId === user?.id
                            )
                            if (userTab && userTab.annotations.length > 0) {
                              const latestAnnotation = userTab.annotations[0] // Already sorted by date
                              setEditingAnnotation(latestAnnotation)
                              setShowAddAnnotation(true)
                            }
                          }}
                          className="flex items-center gap-2 rounded-lg bg-amber-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-amber-700 hover:shadow-md"
                        >
                          <PencilIcon className="h-5 w-5" />
                          {t('annotation.comparison.buttons.editMyAnnotation')}
                        </button>
                      )
                    } else {
                      // User hasn't annotated - show add button with animation
                      return (
                        <button
                          onClick={() => {
                            if (annotatorTabs.length === 0) {
                              setMode('create')
                            } else {
                              setShowAddAnnotation(true)
                            }
                          }}
                          className="group relative flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:bg-blue-700 hover:shadow-md"
                        >
                          <PlusCircleIcon className="h-5 w-5 transition-transform group-hover:scale-110" />
                          {t('annotation.comparison.buttons.addMyAnnotation')}
                          {/* Subtle pulse animation to draw attention */}
                          <span className="absolute -right-1 -top-1 flex h-3 w-3">
                            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-400 opacity-75"></span>
                            <span className="relative inline-flex h-3 w-3 rounded-full bg-blue-500"></span>
                          </span>
                        </button>
                      )
                    }
                  })()}
                </div>

                {/* Right side - close button */}
                <button
                  onClick={onClose}
                  className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm transition-colors hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600 sm:w-auto"
                >
                  {t('annotation.comparison.modal.close')}
                </button>
              </div>
            </div>
          )}
        </DialogPanel>
      </div>
    </Dialog>
  )
}
