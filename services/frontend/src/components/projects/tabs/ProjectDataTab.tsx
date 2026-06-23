/**
 * ProjectDataTab - Display project annotation data with filtering, sorting, and bulk operations
 * This component contains the original content from the project data page
 */

'use client'

import { logger } from '@/lib/utils/logger'
import { BulkActions } from '@/components/projects/BulkActions'
import { ColumnSelector } from '@/components/projects/ColumnSelector'
import { FilterDropdown } from '@/components/projects/FilterDropdown'
import { ImportDataModal } from '@/components/projects/ImportDataModal'
import { TaskAssignmentModal } from '@/components/projects/TaskAssignmentModal'
import { Button } from '@/components/shared/Button'
import { Input } from '@/components/shared/Input'
import { useToast } from '@/components/shared/Toast'
import { TaskAnnotationComparisonModal } from '@/components/tasks/TaskAnnotationComparisonModal'
import { TaskGenerationComparisonModal } from '@/components/tasks/TaskGenerationComparisonModal'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { useProgress } from '@/contexts/ProgressContext'
import { useColumnSettings } from '@/hooks/useColumnSettings'
import { usePermissions } from '@/hooks/usePermissions'
import { projectsAPI } from '@/lib/api/projects'
import { Task } from '@/lib/api/types'
import { useProjectStore } from '@/stores/projectStore'
import { Task as LabelStudioTask } from '@/types/labelStudio'
import {
  extractMetadataColumns,
  hasConsistentMetadataStructure,
} from '@/utils/dataColumnHelpers'
import { extractNestedDataColumns } from '@/utils/nestedDataColumnHelpers'
import { labelStudioTaskToApi } from '@/utils/taskTypeAdapter'
import { Menu } from '@headlessui/react'
import {
  ChevronDownIcon,
  DocumentMagnifyingGlassIcon,
  MagnifyingGlassIcon,
  PlayIcon,
} from '@heroicons/react/24/outline'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { DataRecordModal } from './data/DataRecordModal'
import {
  ProjectDataTable,
  type TableColumn,
} from './data/ProjectDataTable'
import { useProjectData } from './data/useProjectData'

interface ProjectDataTabProps {
  projectId: string
}

const defaultColumns: TableColumn[] = [
  {
    id: 'select',
    label: '',
    visible: true,
    sortable: false,
    width: 'w-12',
    type: 'system',
  },
  {
    id: 'id',
    label: 'annotationTab.columns.id',
    visible: true,
    sortable: true,
    width: 'w-20',
    type: 'system',
  },
  {
    id: 'completed',
    label: 'annotationTab.columns.completed',
    visible: true,
    sortable: true,
    width: 'w-24',
    type: 'system',
  },
  {
    id: 'assigned',
    label: 'annotationTab.columns.assignedTo',
    visible: true,
    sortable: false,
    width: 'w-32',
    type: 'system',
  },
  // Metadata columns will be added dynamically
  {
    id: 'annotations',
    label: 'annotationTab.columns.annotations',
    visible: true,
    sortable: true,
    width: 'w-32',
    type: 'system',
  },
  {
    id: 'generations',
    label: 'annotationTab.columns.generations',
    visible: true,
    sortable: true,
    width: 'w-32',
    type: 'system',
  },
  {
    id: 'annotators',
    label: 'annotationTab.columns.annotators',
    visible: true,
    sortable: false,
    width: 'w-32',
    type: 'system',
  },
  {
    id: 'graders',
    label: 'annotationTab.columns.graders',
    visible: true,
    sortable: false,
    width: 'w-32',
    type: 'system',
  },
  {
    id: 'reviewers',
    label: 'annotationTab.columns.reviewers',
    visible: true,
    sortable: false,
    width: 'w-32',
    type: 'system',
  },
  {
    id: 'created',
    label: 'annotationTab.columns.created',
    visible: true,
    sortable: true,
    width: 'w-36',
    type: 'system',
  },
  // Data columns will be added dynamically
  {
    id: 'view_data',
    label: 'annotationTab.columns.view',
    visible: true,
    sortable: false,
    width: 'w-16',
    type: 'system',
  },
  {
    id: 'edit_data',
    label: 'annotationTab.columns.edit',
    visible: true,
    sortable: false,
    width: 'w-16',
    type: 'system',
  },
]

export function ProjectDataTab({ projectId }: ProjectDataTabProps) {
  const { user } = useAuth()
  const perms = usePermissions()
  const { t } = useI18n()
  const { addToast } = useToast()
  const { startProgress, updateProgress, completeProgress } = useProgress()

  const { currentProject, loading } = useProjectStore()

  // Use persistent column settings
  const { columns, toggleColumn, resetColumns, updateColumns, reorderColumns } =
    useColumnSettings(projectId, user?.id, defaultColumns)

  // Data-fetching + row/pagination/filter state lives in a dedicated hook so
  // this component can focus on layout and the modal/bulk wiring. The hook
  // owns the server-driven page fetch and the client-side metadata/annotator
  // filter pass; it also seeds + re-exposes `updatePreference` so the order-by
  // menu can keep persisting sort choices.
  const {
    updatePreference,
    tasks,
    filteredTasks,
    isLoading,
    searchQuery,
    setSearchQuery,
    showSearch,
    setShowSearch,
    debouncedSearch,
    sortBy,
    setSortBy,
    sortOrder,
    setSortOrder,
    filterStatus,
    setFilterStatus,
    filterDateRange,
    setFilterDateRange,
    setFilterAnnotator,
    metadataFilters,
    setMetadataFilters,
    currentPage,
    setCurrentPage,
    totalTasks,
    totalPages,
    reloadCurrentPage,
  } = useProjectData({ projectId, userId: user?.id })

  const [selectedTasks, setSelectedTasks] = useState<Set<string>>(new Set())
  const [showImportModal, setShowImportModal] = useState(false)

  // Task Assignment Modal state
  const [showAssignmentModal, setShowAssignmentModal] = useState(false)
  const [projectMembers, setProjectMembers] = useState<any[]>([])

  // Handle column visibility - now using the hook
  const handleColumnToggle = (columnId: string) => {
    toggleColumn(columnId)
  }

  // Calculate header checkbox state
  const headerCheckboxState = useMemo(() => {
    const filteredTaskIds = filteredTasks.map((t) => t.id)
    const allSelected =
      filteredTasks.length > 0 &&
      filteredTaskIds.every((id) => selectedTasks.has(id))
    const someSelected =
      filteredTasks.length > 0 &&
      filteredTaskIds.some((id) => selectedTasks.has(id))
    const isIndeterminate = someSelected && !allSelected

    // Debug logging removed - was causing error with undefined selectedTasksArray

    return { allSelected, isIndeterminate }
  }, [filteredTasks, selectedTasks])

  // Handle row selection
  const handleSelectTask = (taskId: string) => {
    setSelectedTasks((prev) => {
      const newSet = new Set(prev)
      if (newSet.has(taskId)) {
        newSet.delete(taskId)
      } else {
        newSet.add(taskId)
      }
      // Force React to recognize the change by creating a completely new Set
      return new Set(newSet)
    })
  }

  const handleSelectAll = (checked: boolean) => {
    // Use setTimeout to ensure state update happens in next tick
    setTimeout(() => {
      if (checked) {
        // Select all filtered tasks on the current page
        const currentPageTaskIds = filteredTasks.map((t) => t.id)
        setSelectedTasks(new Set(currentPageTaskIds))
      } else {
        // Clear all selections - completely reset state
        setSelectedTasks(new Set())
      }
    }, 0)
  }

  // True when the current-page select-all is fully checked AND there are
  // additional matching pages we *could* select if the user asked. Drives
  // the "Select all N matching" banner below the bulk-actions bar.
  const pageFullySelected =
    filteredTasks.length > 0 &&
    filteredTasks.every((t) => selectedTasks.has(t.id))
  const showSelectAllMatching =
    pageFullySelected && totalTasks > filteredTasks.length

  // Fetch every matching task id (across all pages) and select them all.
  // Used by the contextual banner. Backed by the `ids_only=true` short-circuit
  // on the list endpoint so we never page through 50-row windows client-side.
  const handleSelectAllMatching = useCallback(async () => {
    try {
      const { ids, truncated } = await projectsAPI.getTaskIds(projectId, {
        search: debouncedSearch || undefined,
        dateFrom: filterDateRange.start || undefined,
        dateTo: filterDateRange.end || undefined,
        onlyLabeled: filterStatus === 'completed' ? true : undefined,
        onlyUnlabeled: filterStatus === 'incomplete' ? true : undefined,
      })
      setSelectedTasks(new Set(ids))
      if (truncated) {
        addToast(
          `Selection capped at ${ids.length} tasks; refine filters to act on the rest.`,
          'warning'
        )
      }
    } catch (e) {
      console.error('select-all-matching failed', e)
      addToast(t('annotationTab.messages.selectAllFailed'), 'error')
    }
  }, [
    projectId,
    debouncedSearch,
    filterDateRange.start,
    filterDateRange.end,
    filterStatus,
    addToast,
    t,
  ])

  // Handle sorting - save preferences
  const handleSort = useCallback(
    (columnId: string) => {
      const column = columns.find((c) => c.id === columnId)
      if (!column?.sortable) return

      if (sortBy === columnId) {
        const newOrder = sortOrder === 'asc' ? 'desc' : 'asc'
        setSortOrder(newOrder)
        updatePreference('sortOrder', newOrder)
      } else {
        setSortBy(columnId)
        setSortOrder('desc')
        updatePreference('sortBy', columnId)
        updatePreference('sortOrder', 'desc')
      }
    },
    [columns, sortBy, sortOrder, updatePreference]
  )

  // Handle bulk actions
  const handleBulkDelete = async () => {
    if (selectedTasks.size === 0) return

    if (
      !confirm(
        t('annotationTab.confirmations.deleteTasks', {
          count: selectedTasks.size,
        })
      )
    ) {
      return
    }

    const progressId = `bulk-delete-${Date.now()}`

    try {
      const taskIds = Array.from(selectedTasks)

      startProgress(progressId, t('annotationTab.messages.deletingTasks'), {
        sublabel: t('annotationTab.messages.deletingTasks'),
        indeterminate: false,
      })

      updateProgress(progressId, 30, t('annotationTab.messages.deletingTasks'))

      const result = await projectsAPI.bulkDeleteTasks(projectId, taskIds)

      updateProgress(progressId, 70, t('annotationTab.messages.fetchingData'))

      addToast(
        t('annotationTab.messages.tasksDeleted', { count: result.deleted }),
        'success'
      )
      setSelectedTasks(new Set())

      // Refresh tasks
      await reloadCurrentPage()

      updateProgress(
        progressId,
        100,
        t('annotationTab.messages.exportComplete')
      )
      completeProgress(progressId, 'success')
    } catch (error) {
      console.error('Failed to delete tasks:', error)
      completeProgress(progressId, 'error')
      addToast(t('annotationTab.messages.deleteFailed'), 'error')
    }
  }

  const handleBulkExport = async () => {
    if (selectedTasks.size === 0) return

    const progressId = `bulk-export-${Date.now()}`
    const taskIds = Array.from(selectedTasks)

    try {
      // Selected-subset export goes through the async job flow: a worker streams
      // the export to object storage and the browser downloads it via a
      // presigned URL, keeping the bulk data plane off the request path. The
      // worker reports task-count progress (tasks streamed / total), which we
      // poll and reflect on the bar.
      startProgress(progressId, t('annotationTab.buttons.bulkExport'), {
        sublabel: t('annotationTab.messages.exportingSelected', {
          count: selectedTasks.size,
        }),
      })

      await projectsAPI.runProjectExportJob(
        projectId,
        'json',
        {
          onStatus: (status) => {
            if (status.status === 'running' || status.status === 'pending') {
              updateProgress(
                progressId,
                status.progress,
                t('annotationTab.messages.exporting')
              )
            }
          },
        },
        { taskIds }
      )

      completeProgress(progressId, 'success')
      addToast(
        t('annotationTab.messages.exportedTasks', {
          count: selectedTasks.size,
        }),
        'success'
      )
    } catch (error) {
      logger.error('Failed to export tasks:', error)
      completeProgress(progressId, 'error')
      addToast(
        t('annotationTab.messages.exportFailed', {
          error: (error as any)?.message || 'Unknown error',
        }),
        'error'
      )
    }
  }

  // Export tasks — "all" means all rows that match the current filters, not
  // just the visible page. Everything goes through the async job flow: a worker
  // streams the export to object storage and the browser downloads it via a
  // presigned URL, so the bulk data plane never touches the request path and
  // can't OOM the API or truncate a multi-GB download (e.g. the 4.5 GB ZJS
  // project). A whole-project export omits task_ids; a filtered export resolves
  // the matching id list first and passes it as the subset.
  const handleExportTasks = async () => {
    if (totalTasks === 0) {
      addToast(t('annotationTab.empty.noExport'), 'warning')
      return
    }

    const progressId = `export-tasks-${Date.now()}`

    const isFullExport =
      !debouncedSearch &&
      !filterDateRange.start &&
      !filterDateRange.end &&
      filterStatus === 'all'

    try {
      // For a filtered export, resolve the full set of matching ids (not just
      // the visible page) and pass it as the subset; a full export sends none.
      let taskIds: string[] | undefined
      let count = totalTasks
      if (!isFullExport) {
        const { ids, truncated } = await projectsAPI.getTaskIds(projectId, {
          search: debouncedSearch || undefined,
          dateFrom: filterDateRange.start || undefined,
          dateTo: filterDateRange.end || undefined,
          onlyLabeled: filterStatus === 'completed' ? true : undefined,
          onlyUnlabeled: filterStatus === 'incomplete' ? true : undefined,
        })
        if (truncated) {
          addToast(
            `Export capped at ${ids.length} tasks; refine filters to export the rest.`,
            'warning'
          )
        }
        taskIds = ids
        count = ids.length
      }

      startProgress(progressId, t('annotationTab.buttons.export'), {
        sublabel: t('annotationTab.messages.exportingSelected', { count }),
      })

      await projectsAPI.runProjectExportJob(
        projectId,
        'json',
        {
          onStatus: (status) => {
            // The worker reports task-count progress (tasks streamed / total);
            // reflect it on the bar as the export streams.
            if (status.status === 'running' || status.status === 'pending') {
              updateProgress(
                progressId,
                status.progress,
                t('annotationTab.messages.exporting')
              )
            }
          },
        },
        { taskIds }
      )

      completeProgress(progressId, 'success')
      addToast(
        t('annotationTab.messages.exportedTasks', { count }),
        'success'
      )
    } catch (error) {
      logger.error('Failed to export tasks:', error)
      completeProgress(progressId, 'error')
      addToast(
        t('annotationTab.messages.exportFailed', {
          error: (error as any)?.message || 'Unknown error',
        }),
        'error'
      )
    }
  }

  const handleBulkArchive = async () => {
    if (selectedTasks.size === 0) return

    if (
      !confirm(
        t('annotationTab.confirmations.archiveTasks', {
          count: selectedTasks.size,
        })
      )
    ) {
      return
    }

    const progressId = `bulk-archive-${Date.now()}`

    try {
      const taskIds = Array.from(selectedTasks)

      startProgress(progressId, t('annotationTab.buttons.archiveTasks'), {
        sublabel: t('annotationTab.messages.exportingSelected', {
          count: selectedTasks.size,
        }),
        indeterminate: false,
      })

      updateProgress(progressId, 30, t('annotationTab.messages.fetchingData'))

      const result = await projectsAPI.bulkArchiveTasks(projectId, taskIds)

      updateProgress(progressId, 70, t('annotationTab.messages.fetchingData'))

      addToast(
        t('annotationTab.messages.tasksArchived', { count: result.archived }),
        'success'
      )
      setSelectedTasks(new Set())

      // Refresh tasks
      await reloadCurrentPage()

      updateProgress(
        progressId,
        100,
        t('annotationTab.messages.exportComplete')
      )
      completeProgress(progressId, 'success')
    } catch (error) {
      console.error('Failed to archive tasks:', error)
      completeProgress(progressId, 'error')
      addToast(t('annotationTab.messages.archiveFailed'), 'error')
    }
  }

  // Modal state for viewing complete task data
  const [viewDataTask, setViewDataTask] = useState<Task | null>(null)
  const [showDataModal, setShowDataModal] = useState(false)
  const [dataModalMode, setDataModalMode] = useState<'view' | 'edit'>('view')

  // Per-project edit gate: superadmins, the project creator, and ORG_ADMINs of
  // the project's org. The backend re-checks and returns 403 if not allowed.
  const canEditTasks =
    perms.getEffectiveProjectRole(
      currentProject ?? null,
      user?.role ?? null
    ) === 'ORG_ADMIN'

  // State for annotation comparison modal
  const [selectedTaskForComparison, setSelectedTaskForComparison] =
    useState<LabelStudioTask | null>(null)
  const [showComparisonModal, setShowComparisonModal] = useState(false)

  // State for the all-generations modal (opened from the generations cell)
  const [selectedTaskForGenerations, setSelectedTaskForGenerations] =
    useState<LabelStudioTask | null>(null)
  const [showGenerationModal, setShowGenerationModal] = useState(false)

  // Modal state for viewing/editing metadata - removed (now using page navigation)

  // Extract dynamic data columns including nested JSON fields
  const dataColumns = useMemo(() => {
    // Use nested column extraction to support flattened JSON fields
    const nestedColumns = extractNestedDataColumns(tasks as any, 50, true)
    // Convert NestedDataColumn to the format expected by the rest of the component
    return nestedColumns.map((col) => ({
      id: col.key,
      label: col.label,
      type: col.type as any,
    }))
  }, [tasks])

  // Extract dynamic metadata columns
  const metadataColumns = useMemo(() => {
    return extractMetadataColumns(tasks as any, 8) // Limit columns for performance
  }, [tasks])

  // Check if tasks have consistent data structure for dynamic columns
  // Always use data columns when available to show nested JSON fields
  const useDataColumns = useMemo(() => {
    return tasks.length > 0 && dataColumns.length > 0
  }, [tasks, dataColumns])

  // Check if tasks have consistent metadata structure for dynamic columns
  const useMetadataColumns = useMemo(() => {
    return (
      tasks.length > 0 &&
      hasConsistentMetadataStructure(tasks as any) &&
      metadataColumns.length > 0
    )
  }, [tasks, metadataColumns])

  // Track if initial columns have been set
  const [columnsInitialized, setColumnsInitialized] = useState(false)

  // Update columns to include dynamic data and metadata columns for the column selector
  useEffect(() => {
    // Only update columns if they haven't been initialized or if structure changes
    const hasDataCols = columns.some((c) => c.id.startsWith('data_'))
    const hasMetaCols = columns.some((c) => c.id.startsWith('meta_'))
    const needsUpdate =
      !columnsInitialized ||
      useDataColumns !== hasDataCols ||
      useMetadataColumns !== hasMetaCols

    if (needsUpdate) {
      let baseColumns = defaultColumns.filter((c) => c.type === 'system')

      // Create metadata column definitions
      const metadataColumnDefs: TableColumn[] = metadataColumns.map((col) => ({
        id: `meta_${col.key}`,
        label: col.label,
        visible: true,
        sortable: false,
        width: 'w-32',
        type: 'metadata',
      }))

      // Create data column definitions - all visible by default to show nested JSON
      const dataColumnDefs: TableColumn[] = dataColumns.map((col) => ({
        id: `data_${col.id}`,
        label: col.label,
        visible: true, // Show all nested columns by default
        sortable: false,
        width: 'w-40', // Slightly wider for nested field names
        type: 'data',
      }))

      // Find insertion points
      const assignedIndex = baseColumns.findIndex((c) => c.id === 'assigned')
      const viewDataIndex = baseColumns.findIndex((c) => c.id === 'view_data')
      const editDataIndex = baseColumns.findIndex((c) => c.id === 'edit_data')

      let newColumns: TableColumn[] = []

      // Build column order: system columns, metadata columns, more system columns, data columns, view button
      if (assignedIndex > -1) {
        // Insert metadata columns after 'assigned'
        newColumns = [
          ...baseColumns.slice(0, assignedIndex + 1),
          ...metadataColumnDefs,
        ]

        // Add remaining system columns before view_data
        const remainingSystemCols = baseColumns.slice(
          assignedIndex + 1,
          viewDataIndex > -1 ? viewDataIndex : undefined
        )
        newColumns = [...newColumns, ...remainingSystemCols]

        // Add data columns
        newColumns = [...newColumns, ...dataColumnDefs]

        // Add view_data then edit_data buttons at the end
        if (viewDataIndex > -1) {
          newColumns = [...newColumns, baseColumns[viewDataIndex]]
        }
        if (editDataIndex > -1) {
          newColumns = [...newColumns, baseColumns[editDataIndex]]
        }
      } else {
        // Fallback: just append in order
        newColumns = [...baseColumns, ...metadataColumnDefs, ...dataColumnDefs]
      }

      updateColumns(newColumns)
      setColumnsInitialized(true)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- Intentional: columns and updateColumns excluded to prevent infinite loop
  }, [
    useDataColumns,
    useMetadataColumns,
    dataColumns.length,
    metadataColumns.length,
    columnsInitialized,
  ])

  // Handle viewing complete task data
  const handleViewTaskData = (task: LabelStudioTask) => {
    const apiTask = labelStudioTaskToApi(task)
    setViewDataTask(apiTask)
    setDataModalMode('view')
    setShowDataModal(true)
  }

  // Handle editing complete task data (opens the same modal in edit mode)
  const handleEditTaskData = (task: LabelStudioTask) => {
    const apiTask = labelStudioTaskToApi(task)
    setViewDataTask(apiTask)
    setDataModalMode('edit')
    setShowDataModal(true)
  }

  // Handle viewing/editing metadata
  const handleViewTaskMetadata = (task: LabelStudioTask) => {
    // This function can be removed or repurposed if needed
    logger.debug('Metadata view requested for task:', task.id)
  }

  // Get task display value (fallback for when dynamic columns are not used)
  const getTaskDisplayValue = (task: LabelStudioTask): string => {
    if ((task as any).data.text) return (task as any).data.text
    if ((task as any).data.question) return (task as any).data.question
    if ((task as any).data.prompt) return (task as any).data.prompt

    const firstStringValue = Object.values((task as any).data).find(
      (v) => typeof v === 'string'
    )
    if (firstStringValue) return firstStringValue as string

    return `Task ${task.id}`
  }

  // Fetch project members for assignment (including organization members)
  const fetchProjectMembers = async () => {
    try {
      logger.debug('fetchProjectMembers: Starting fetch for project', projectId)
      // Get both direct members and organization members
      const members = await projectsAPI.getMembers(projectId)
      logger.debug('fetchProjectMembers: Received members', members)
      setProjectMembers(members || [])
    } catch (error) {
      console.error('Error fetching project members:', error)
      setProjectMembers([])
    }
  }

  // Handle opening assignment modal
  const handleOpenAssignmentModal = () => {
    if (selectedTasks.size === 0) {
      addToast(t('annotationTab.confirmations.selectTasks'), 'warning')
      return
    }

    fetchProjectMembers()
    setShowAssignmentModal(true)
  }

  // Handle assignment completion
  const handleAssignmentComplete = async () => {
    await reloadCurrentPage()
    setSelectedTasks(new Set())
    addToast(t('annotationTab.messages.tasksAssigned'), 'success')
  }

  // Handle unassignment
  const handleUnassign = async (assignmentId: string) => {
    try {
      // Find the task that contains this assignment
      const task = tasks.find((t) =>
        (t as any).assignments?.some((a: any) => a.id === assignmentId)
      )

      if (!task) {
        addToast(t('errors.taskNotFound'), 'error')
        return
      }

      await projectsAPI.removeTaskAssignment(projectId, task.id, assignmentId)

      // Refresh tasks to show updated assignments
      await reloadCurrentPage()
      addToast(t('success.assignmentRemoved'), 'success')
    } catch (error) {
      console.error('Error removing assignment:', error)
      addToast(t('errors.assignmentRemoveFailed'), 'error')
    }
  }

  // Handle assigning a specific task
  const handleAssignTask = (taskId: string) => {
    setSelectedTasks(new Set([taskId]))
    fetchProjectMembers()
    setShowAssignmentModal(true)
  }

  // Check if current user can unassign tasks (admins/contributors, plus
  // public-tier CONTRIBUTORs when the project is public).
  const canUnassign = perms.canAccessProjectData({ project: currentProject })

  return (
    <>
      {/* Action Bar */}
      <div className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="px-4 py-3 sm:px-6">
          <div className="flex flex-col space-y-3 lg:flex-row lg:items-center lg:justify-between lg:space-y-0">
            {/* Primary Actions */}
            <div className="flex flex-wrap items-center gap-2 sm:gap-3">
              <Button
                variant="outline"
                onClick={() => {
                  const newShowSearch = !showSearch
                  setShowSearch(newShowSearch)
                  updatePreference('showSearch', newShowSearch)
                  if (!newShowSearch) {
                    setSearchQuery('') // Clear search when hiding
                  }
                }}
                className="flex items-center"
                title={
                  showSearch
                    ? t('annotationTab.filters.hideSearch')
                    : t('annotationTab.filters.showSearch')
                }
              >
                <MagnifyingGlassIcon className="h-4 w-4" />
                <span className="ml-2 hidden sm:inline">
                  {t('annotationTab.buttons.search')}
                </span>
              </Button>

              <BulkActions
                selectedCount={selectedTasks.size}
                selectedTaskIds={Array.from(selectedTasks).map((id) =>
                  String(id)
                )}
                projectId={projectId}
                onDelete={handleBulkDelete}
                onExport={handleBulkExport}
                onArchive={handleBulkArchive}
                onAssign={handleOpenAssignmentModal}
                canAssign={perms.canAccessProjectData({ project: currentProject })}
                onTagsUpdated={async () => {
                  await reloadCurrentPage()
                  addToast(t('success.tagsUpdated'), 'success')
                }}
              />

              <ColumnSelector
                columns={columns}
                onToggle={handleColumnToggle}
                onReorder={reorderColumns}
                onReset={resetColumns}
              />

              <FilterDropdown
                projectId={projectId}
                filterStatus={filterStatus}
                onStatusChange={(status) => {
                  setFilterStatus(status)
                  updatePreference('filterStatus', status)
                }}
                onDateRangeChange={(start, end) =>
                  setFilterDateRange({ start, end })
                }
                onAnnotatorChange={setFilterAnnotator}
                metadataFilters={metadataFilters}
                onMetadataChange={setMetadataFilters}
              />

              <Menu as="div" className="relative hidden sm:block">
                <Menu.Button as={Button} variant="outline" className="gap-2">
                  {t('annotationTab.buttons.orderBy')}
                  <ChevronDownIcon className="h-4 w-4" />
                </Menu.Button>
                <Menu.Items className="absolute right-0 z-50 mt-2 w-56 origin-top-right rounded-lg bg-white shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none dark:bg-zinc-900">
                  <div className="py-1">
                    <div className="px-4 py-2 text-xs font-medium text-zinc-500 dark:text-zinc-400">
                      {t('annotationTab.orderBy.sortBy')}
                    </div>
                    {columns
                      .filter((c) => c.sortable)
                      .map((column) => {
                        const isActive = sortBy === column.id
                        return (
                          <Menu.Item key={column.id}>
                            {({ active: focused }) => (
                              <button
                                onClick={() => {
                                  setSortBy(column.id)
                                  updatePreference('sortBy', column.id)
                                }}
                                className={`flex w-full items-center justify-between px-4 py-2 text-sm ${
                                  focused ? 'bg-zinc-100 dark:bg-zinc-800' : ''
                                } ${
                                  isActive
                                    ? 'font-medium text-emerald-600 dark:text-emerald-400'
                                    : 'text-zinc-700 dark:text-zinc-200'
                                }`}
                              >
                                <span>{t(column.label)}</span>
                                {isActive && (
                                  <span>{sortOrder === 'asc' ? '↑' : '↓'}</span>
                                )}
                              </button>
                            )}
                          </Menu.Item>
                        )
                      })}
                    <div className="my-1 border-t border-zinc-200 dark:border-zinc-700" />
                    {(['asc', 'desc'] as const).map((dir) => (
                      <Menu.Item key={dir}>
                        {({ active: focused }) => (
                          <button
                            onClick={() => {
                              setSortOrder(dir)
                              updatePreference('sortOrder', dir)
                            }}
                            className={`flex w-full items-center justify-between px-4 py-2 text-sm ${
                              focused ? 'bg-zinc-100 dark:bg-zinc-800' : ''
                            } ${
                              sortOrder === dir
                                ? 'font-medium text-emerald-600 dark:text-emerald-400'
                                : 'text-zinc-700 dark:text-zinc-200'
                            }`}
                          >
                            <span>
                              {dir === 'asc'
                                ? t('annotationTab.orderBy.ascending')
                                : t('annotationTab.orderBy.descending')}
                            </span>
                            {sortOrder === dir && <span>✓</span>}
                          </button>
                        )}
                      </Menu.Item>
                    ))}
                  </div>
                </Menu.Items>
              </Menu>

              <Button variant="outline" className="hidden md:flex">
                <DocumentMagnifyingGlassIcon className="mr-2 h-4 w-4" />
                <span className="hidden lg:inline">
                  {t('annotationTab.buttons.reviewAll')}
                </span>
                <span className="lg:hidden">
                  {t('annotationTab.buttons.reviewAll')}
                </span>
              </Button>

              <Button variant="primary" className="flex">
                <PlayIcon className="mr-2 h-4 w-4" />
                <span className="hidden sm:inline">
                  {t('annotationTab.buttons.labelAll')}
                </span>
                <span className="sm:hidden">
                  {t('annotationTab.buttons.labelAll')}
                </span>
              </Button>
            </div>

            {/* Secondary Actions - Import/Export buttons */}
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                onClick={() => setShowImportModal(true)}
                title={t('annotationTab.buttons.import')}
                data-testid="import-button"
              >
                <svg
                  className="h-4 w-4"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                  />
                </svg>
              </Button>

              <Button
                variant="outline"
                onClick={handleExportTasks}
                disabled={filteredTasks.length === 0}
                title={t('annotationTab.buttons.export')}
                data-testid="export-button"
              >
                <svg
                  className="h-4 w-4"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                  />
                </svg>
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="px-4 py-4 sm:px-6 sm:py-6">
        {/* Search Bar - Collapsible */}
        {showSearch && (
          <div className="animate-in slide-in-from-top-2 mb-4 duration-200 sm:mb-6">
            <div className="relative">
              <MagnifyingGlassIcon className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 transform text-zinc-400" />
              <Input
                placeholder={t('search.placeholder')}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-10"
                autoFocus
              />
            </div>
          </div>
        )}

        {/* Results count */}
        <div className="mb-4 flex flex-col text-sm text-zinc-600 dark:text-zinc-400 sm:flex-row sm:items-center sm:justify-between">
          <p>
            {selectedTasks.size > 0 && (
              <span className="font-medium text-zinc-900 dark:text-white">
                {t('annotationTab.display.selected', {
                  count: selectedTasks.size,
                })}{' '}
                ·
              </span>
            )}
            {t('annotationTab.display.showing', {
              current: filteredTasks.length,
              total: tasks.length,
            })}
          </p>
        </div>

        {/* Select-all-matching banner. Appears when the current-page
            checkbox is fully checked AND there are matching rows on other
            pages — gives the user a single click to extend the selection
            across the whole filtered set (Gmail's "Select all
            conversations" affordance). Without this, bulk delete/export
            would silently operate on only 50 rows even when the project
            has thousands of matching tasks. */}
        {showSelectAllMatching && (
          <div className="mb-3 flex items-center justify-between rounded-md border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-100">
            <span>
              {`All ${filteredTasks.length} tasks on this page are selected.`}
            </span>
            <button
              type="button"
              onClick={handleSelectAllMatching}
              className="ml-4 font-medium underline-offset-2 hover:underline"
            >
              {`Select all ${totalTasks} matching tasks`}
            </button>
          </div>
        )}

        {/* Data Table */}
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-emerald-500"></div>
          </div>
        ) : (
          <ProjectDataTable
            rows={filteredTasks}
            columns={columns}
            canEditTasks={canEditTasks}
            dataColumns={dataColumns}
            metadataColumns={metadataColumns}
            useDataColumns={useDataColumns}
            sortBy={sortBy}
            sortOrder={sortOrder}
            onSort={handleSort}
            selectedTasks={selectedTasks}
            headerCheckboxState={headerCheckboxState}
            onSelectAll={handleSelectAll}
            onSelectTask={handleSelectTask}
            canUnassign={canUnassign}
            onUnassign={handleUnassign}
            onAssignTask={handleAssignTask}
            onRowClick={(task) => {
              setSelectedTaskForComparison(task)
              setShowComparisonModal(true)
            }}
            onOpenGenerations={(task) => {
              setSelectedTaskForGenerations(task)
              setShowGenerationModal(true)
            }}
            onViewTaskData={handleViewTaskData}
            onEditTaskData={handleEditTaskData}
            onViewTaskMetadata={handleViewTaskMetadata}
            getTaskDisplayValue={getTaskDisplayValue}
          />
        )}

        {/* Empty state */}
        {filteredTasks.length === 0 && !isLoading && (
          <div className="py-12 text-center">
            <p className="text-zinc-600 dark:text-zinc-400">
              {searchQuery || filterStatus !== 'all'
                ? t('annotationTab.empty.noMatch')
                : t('annotationTab.empty.noTasks')}
            </p>
          </div>
        )}

        {/* Pagination — server-driven now that ProjectDataTab loads one page
            at a time. The Previous/Next buttons were stubbed (`disabled`)
            while everything lived in memory; they're real controls again. */}
        {totalTasks > 0 && (
          <div className="mt-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="order-2 text-sm text-zinc-600 dark:text-zinc-400 sm:order-1">
              <div className="flex flex-col gap-1 sm:flex-row sm:gap-0">
                <span>
                  {t('annotationTab.display.tasksCount', {
                    current: filteredTasks.length,
                    total: totalTasks,
                  })}
                </span>
                <span className="hidden sm:inline"> · </span>
                <span>
                  {`Page ${currentPage} of ${Math.max(totalPages, 1)}`}
                </span>
              </div>
            </div>
            <div className="order-1 flex items-center justify-center space-x-2 sm:order-2 sm:justify-end">
              <Button
                variant="outline"
                disabled={currentPage <= 1 || isLoading}
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              >
                {t('annotationTab.buttons.previous')}
              </Button>
              <Button
                variant="outline"
                disabled={currentPage >= totalPages || isLoading}
                onClick={() =>
                  setCurrentPage((p) => Math.min(totalPages, p + 1))
                }
              >
                {t('annotationTab.buttons.next')}
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Import Data Modal */}
      <ImportDataModal
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
        projectId={projectId}
        onImportComplete={async () => {
          // Imports may produce more pages — reset to page 1 so the user
          // lands on the freshest rows, then refresh.
          if (currentPage !== 1) {
            setCurrentPage(1)
          } else {
            await reloadCurrentPage()
          }
        }}
      />

      {/* Task Assignment Modal */}
      {showAssignmentModal && (
        <TaskAssignmentModal
          isOpen={showAssignmentModal}
          onClose={() => setShowAssignmentModal(false)}
          projectId={projectId}
          selectedTaskIds={Array.from(selectedTasks)}
          projectMembers={projectMembers}
          onAssignmentComplete={handleAssignmentComplete}
        />
      )}

      {/* Task Data View / Edit Modal */}
      <DataRecordModal
        task={viewDataTask}
        isOpen={showDataModal}
        onClose={() => {
          setShowDataModal(false)
          setViewDataTask(null)
        }}
        projectId={projectId}
        mode={dataModalMode}
        canEdit={canEditTasks}
        onSaved={() => reloadCurrentPage()}
      />

      {/* Task Annotation Comparison Modal */}
      <TaskAnnotationComparisonModal
        task={selectedTaskForComparison}
        isOpen={showComparisonModal}
        onClose={() => {
          setShowComparisonModal(false)
          setSelectedTaskForComparison(null)
        }}
        projectId={projectId}
      />

      {/* Task Generation Comparison Modal (all models for the task) */}
      <TaskGenerationComparisonModal
        task={selectedTaskForGenerations}
        isOpen={showGenerationModal}
        onClose={() => {
          setShowGenerationModal(false)
          setSelectedTaskForGenerations(null)
        }}
        projectId={projectId}
      />

      {/* Task Metadata View Modal - removed, now using page navigation */}
    </>
  )
}
