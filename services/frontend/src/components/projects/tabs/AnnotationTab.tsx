/**
 * AnnotationTab - Display project annotation data with filtering, sorting, and bulk operations
 * This component contains the original content from the project data page
 */

'use client'

import { logger } from '@/lib/utils/logger'
import { AnnotatorBadges } from '@/components/projects/AnnotatorBadges'
import { BulkActions } from '@/components/projects/BulkActions'
import { ColumnSelector } from '@/components/projects/ColumnSelector'
import { FilterDropdown } from '@/components/projects/FilterDropdown'
import { ImportDataModal } from '@/components/projects/ImportDataModal'
import { TableCheckbox } from '@/components/projects/TableCheckbox'
import { TaskAssignmentModal } from '@/components/projects/TaskAssignmentModal'
import { UserAvatar } from '@/components/projects/UserAvatar'
import { Button } from '@/components/shared/Button'
import { Input } from '@/components/shared/Input'
import { useToast } from '@/components/shared/Toast'
import { TaskAnnotationComparisonModal } from '@/components/tasks/TaskAnnotationComparisonModal'
import { TaskDataViewModal } from '@/components/tasks/TaskDataViewModal'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { useProgress } from '@/contexts/ProgressContext'
import {
  useColumnSettings,
  useTablePreferences,
} from '@/hooks/useColumnSettings'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { projectsAPI } from '@/lib/api/projects'
import { TruncatedExportError } from '@/lib/api/streamingExport'
import { Task } from '@/lib/api/types'
import { useProjectStore } from '@/stores/projectStore'
import { Task as LabelStudioTask } from '@/types/labelStudio'
import {
  extractMetadataColumns,
  formatCellValue,
  hasConsistentMetadataStructure,
} from '@/utils/dataColumnHelpers'
import {
  extractNestedDataColumns,
  formatNestedCellValue,
  getTaskNestedValue,
} from '@/utils/nestedDataColumnHelpers'
import { canAccessProjectData } from '@/utils/permissions'
import { labelStudioTaskToApi } from '@/utils/taskTypeAdapter'
import {
  CheckIcon,
  ChevronDownIcon,
  DocumentMagnifyingGlassIcon,
  EyeIcon,
  MagnifyingGlassIcon,
  PlayIcon,
} from '@heroicons/react/24/outline'
import { formatDistanceToNow } from 'date-fns'
import { useCallback, useEffect, useMemo, useState } from 'react'

interface AnnotationTabProps {
  projectId: string
}

// Define table columns
interface TableColumn {
  id: string
  label: string
  visible: boolean
  sortable: boolean
  width?: string
  type?: 'metadata' | 'data' | 'system'
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
    id: 'agreement',
    label: 'annotationTab.columns.agreement',
    visible: true,
    sortable: true,
    width: 'w-28',
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
]

export function AnnotationTab({ projectId }: AnnotationTabProps) {
  const { user } = useAuth()
  const { t } = useI18n()
  const { addToast } = useToast()
  const { startProgress, updateProgress, completeProgress } = useProgress()

  const { currentProject, loading } = useProjectStore()

  // Use persistent column settings
  const { columns, toggleColumn, resetColumns, updateColumns, reorderColumns } =
    useColumnSettings(projectId, user?.id, defaultColumns)

  // Use persistent table preferences
  const { preferences, updatePreference } = useTablePreferences(
    projectId,
    user?.id
  )

  // State - using LabelStudio Task type internally for compatibility.
  // `tasks` holds the CURRENT PAGE only; the projects-list page is driven
  // by server-side pagination + filters now. `filteredTasks` keeps the
  // (small) client-side filter pass for fields the API doesn't yet expose
  // (annotator, metadata) on top of the current page.
  const [tasks, setTasks] = useState<LabelStudioTask[]>([])
  const [filteredTasks, setFilteredTasks] = useState<LabelStudioTask[]>([])
  const [selectedTasks, setSelectedTasks] = useState<Set<string>>(new Set())
  const [searchQuery, setSearchQuery] = useState('')
  const [showSearch, setShowSearch] = useState(preferences.showSearch)
  const [sortBy, setSortBy] = useState<string>(preferences.sortBy)
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>(
    preferences.sortOrder
  )
  const [filterStatus, setFilterStatus] = useState<
    'all' | 'completed' | 'incomplete'
  >(preferences.filterStatus)
  const [filterDateRange, setFilterDateRange] = useState<{
    start: string
    end: string
  }>({ start: '', end: '' })
  const [showImportModal, setShowImportModal] = useState(false)
  const [filterAnnotator, setFilterAnnotator] = useState('')
  const [isLoading, setIsLoading] = useState(true)

  // Server-driven pagination state. The API endpoint returns `total` /
  // `pages` from the new Phase 1c filter shape; this lets us drive
  // Previous/Next without ever loading the entire project into memory.
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize] = useState(50)
  const [totalTasks, setTotalTasks] = useState(0)
  const [totalPages, setTotalPages] = useState(0)

  // Metadata filtering state (Label Studio aligned)
  const [metadataFilters, setMetadataFilters] = useState<Record<string, any>>(
    {}
  )

  // Task Assignment Modal state
  const [showAssignmentModal, setShowAssignmentModal] = useState(false)
  const [projectMembers, setProjectMembers] = useState<any[]>([])

  // Lag the search input so per-keystroke typing doesn't refire the page
  // fetch.
  const debouncedSearch = useDebouncedValue(searchQuery, 300)

  // Reset to page 1 whenever a filter changes — otherwise the current page
  // index may exceed the new totalPages and the UI shows an empty page.
  useEffect(() => {
    setCurrentPage(1)
  }, [debouncedSearch, filterStatus, filterDateRange.start, filterDateRange.end, sortBy, sortOrder])

  // Map UI sort key to the backend sort columns. `agreement` isn't a
  // server-sortable concept yet (it's derived from per-task annotation
  // distribution), so we fall back to created and let the client-side
  // pass at lines below handle the in-page ordering.
  const serverSortBy = useMemo<
    'id' | 'created' | 'completed' | 'annotations' | 'generations' | undefined
  >(() => {
    if (sortBy === 'id' || sortBy === 'created' || sortBy === 'completed') return sortBy
    if (sortBy === 'annotations' || sortBy === 'generations') return sortBy
    return undefined
  }, [sortBy])

  // Load the current page from the server with the active filters in one
  // round-trip. Pre-refactor the store walked every page of the project
  // and concatenated them into memory — for 50k-task projects that was
  // tens of MB streamed across the wire on every filter change.
  const reloadCurrentPage = useCallback(async () => {
    setIsLoading(true)
    try {
      const page = await projectsAPI.getTasksPage(projectId, {
        page: currentPage,
        pageSize,
        search: debouncedSearch || undefined,
        dateFrom: filterDateRange.start || undefined,
        dateTo: filterDateRange.end || undefined,
        onlyLabeled: filterStatus === 'completed' ? true : undefined,
        onlyUnlabeled: filterStatus === 'incomplete' ? true : undefined,
        sortBy: serverSortBy,
        sortOrder,
      })
      // `getTasksPage` returns the raw task shape from the API; cast to
      // the LabelStudio task type used by the rest of this component.
      setTasks(page.items as unknown as LabelStudioTask[])
      setFilteredTasks(page.items as unknown as LabelStudioTask[])
      setTotalTasks(page.total)
      setTotalPages(page.pages)
    } finally {
      setIsLoading(false)
    }
  }, [
    projectId,
    currentPage,
    pageSize,
    debouncedSearch,
    filterStatus,
    filterDateRange.start,
    filterDateRange.end,
    serverSortBy,
    sortOrder,
  ])

  useEffect(() => {
    if (!projectId) return
    reloadCurrentPage()
  }, [projectId, reloadCurrentPage])

  // Client-side fallback pass for fields the API doesn't filter yet:
  // - filterAnnotator: requires reading annotation rows; no server endpoint exists yet
  // - metadataFilters: arbitrary JSONB path equality, kept client-side
  // status/date/search/sort all went server-side in Phase 6.4 and operate
  // on the full project before pagination — no need to re-apply them here.
  useEffect(() => {
    let filtered = tasks

    if (filterAnnotator) {
      // TODO(perf): expose annotator filter on /projects/{id}/tasks; today
      // this is a no-op because annotation rows aren't included in the
      // task payload. Kept as a guarded branch so the prop wiring stays
      // valid when the backend filter lands.
      filtered = filtered
    }

    if (Object.keys(metadataFilters).length > 0) {
      filtered = filtered.filter((task) => {
        const taskMeta = (task as any).meta || {}

        return Object.entries(metadataFilters).every(
          ([field, filterValues]) => {
            const taskValue = taskMeta[field]

            if (Array.isArray(filterValues)) {
              if (Array.isArray(taskValue)) {
                return filterValues.some((fv) => taskValue.includes(fv))
              } else {
                return filterValues.includes(taskValue)
              }
            } else {
              if (Array.isArray(taskValue)) {
                return taskValue.includes(filterValues)
              } else {
                return taskValue === filterValues
              }
            }
          }
        )
      })
    }

    setFilteredTasks(filtered)
  }, [tasks, filterAnnotator, metadataFilters])

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

  // Handle export
  const handleExport = async (format: 'json' | 'csv' | 'tsv' = 'json') => {
    const progressId = `export-${Date.now()}`

    try {
      let blob: Blob
      const taskCount =
        selectedTasks.size > 0 ? selectedTasks.size : tasks.length

      startProgress(progressId, t('annotationTab.messages.exporting'), {
        sublabel: t('annotationTab.messages.preparingTasks', {
          count: taskCount,
        }),
        indeterminate: false,
      })

      updateProgress(progressId, 20, t('annotationTab.messages.fetchingData'))

      if (selectedTasks.size > 0) {
        updateProgress(
          progressId,
          40,
          t('annotationTab.messages.processingSelected', {
            count: selectedTasks.size,
          })
        )
        blob = await projectsAPI.bulkExportTasks(
          projectId,
          Array.from(selectedTasks),
          format
        )
      } else {
        updateProgress(
          progressId,
          40,
          t('annotationTab.messages.processingSelected', {
            count: tasks.length,
          })
        )
        blob = await projectsAPI.export(projectId, format)
      }

      updateProgress(progressId, 80, `Formatting as ${format.toUpperCase()}...`)

      // Create download link
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${currentProject?.title || 'project'}_export.${format}`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)

      updateProgress(
        progressId,
        100,
        t('annotationTab.messages.exportComplete')
      )
      completeProgress(progressId, 'success')

      addToast(
        selectedTasks.size > 0
          ? t('annotationTab.messages.exportedTasks', {
              count: selectedTasks.size,
            })
          : t('annotationTab.messages.exportedTasks', {
              count: tasks.length,
            }),
        'success'
      )
    } catch (error: any) {
      completeProgress(progressId, 'error')
      addToast(
        t('annotationTab.messages.exportFailed', {
          error: error.message || 'Unknown error',
        }),
        'error'
      )
    }
  }

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
    const suggestedName = `tasks-export-${new Date().toISOString().split('T')[0]}.json`

    try {
      // Streams the body straight to disk (File System Access API) and
      // validates the server's completeness sentinel, so a severed multi-GB
      // download surfaces as an error rather than a silently-truncated file.
      // The backend streams a single response with no per-row progress
      // signal, so the bar stays indeterminate.
      await projectsAPI.streamExportTasks(projectId, taskIds, suggestedName, {
        onStart: () =>
          startProgress(progressId, t('annotationTab.buttons.bulkExport'), {
            sublabel: t('annotationTab.messages.exportingSelected', {
              count: selectedTasks.size,
            }),
            indeterminate: true,
          }),
      })

      completeProgress(progressId, 'success')
      addToast(
        t('annotationTab.messages.exportedTasks', {
          count: selectedTasks.size,
        }),
        'success'
      )
    } catch (error) {
      // User dismissed the save dialog before any work started — not an error.
      if (error instanceof DOMException && error.name === 'AbortError') {
        return
      }
      logger.error('Failed to export tasks:', error)
      completeProgress(progressId, 'error')
      addToast(
        t('annotationTab.messages.exportFailed', {
          error:
            error instanceof TruncatedExportError
              ? error.message
              : 'Unknown error',
        }),
        'error'
      )
    }
  }

  // Export all filtered tasks — "all" means all rows that match the current
  // filters, not just the visible page. Fetches the full ID list via the
  // `ids_only=true` short-circuit, then drives the existing bulk-export
  // endpoint with that set. Pre-Phase-7.5 this used `filteredTasks.map(...)`
  // which after the server-side pagination shift meant just 50 rows.
  const handleExportTasks = async () => {
    if (totalTasks === 0) {
      addToast(t('annotationTab.empty.noExport'), 'warning')
      return
    }

    const progressId = `export-tasks-${Date.now()}`

    try {
      const { ids: taskIds, truncated } = await projectsAPI.getTaskIds(
        projectId,
        {
          search: debouncedSearch || undefined,
          dateFrom: filterDateRange.start || undefined,
          dateTo: filterDateRange.end || undefined,
          onlyLabeled: filterStatus === 'completed' ? true : undefined,
          onlyUnlabeled: filterStatus === 'incomplete' ? true : undefined,
        }
      )

      if (truncated) {
        addToast(
          `Export capped at ${taskIds.length} tasks; refine filters to export the rest.`,
          'warning'
        )
      }

      const suggestedName = `${currentProject?.title || 'project'}-tasks-${new Date().toISOString().split('T')[0]}.json`

      // Stream straight to disk with completeness validation rather than
      // buffering the whole body via blob(); for the 4.5 GB ZJS project the
      // old path was severed mid-stream and saved a truncated, invalid file.
      await projectsAPI.streamExportTasks(projectId, taskIds, suggestedName, {
        onStart: () =>
          // Indeterminate — no real per-row progress signal from the backend
          // stream; the previous fake 30%→70%→100% was misleading.
          startProgress(progressId, t('annotationTab.buttons.export'), {
            sublabel: t('annotationTab.messages.exportingSelected', {
              count: taskIds.length,
            }),
            indeterminate: true,
          }),
      })

      completeProgress(progressId, 'success')
      addToast(
        t('annotationTab.messages.exportedTasks', {
          count: taskIds.length,
        }),
        'success'
      )
    } catch (error) {
      // User dismissed the save dialog before any work started — not an error.
      if (error instanceof DOMException && error.name === 'AbortError') {
        return
      }
      logger.error('Failed to export tasks:', error)
      completeProgress(progressId, 'error')
      addToast(
        t('annotationTab.messages.exportFailed', {
          error:
            error instanceof TruncatedExportError
              ? error.message
              : 'Unknown error',
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

  // State for annotation comparison modal
  const [selectedTaskForComparison, setSelectedTaskForComparison] =
    useState<LabelStudioTask | null>(null)
  const [showComparisonModal, setShowComparisonModal] = useState(false)

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

        // Add view_data button at the end
        if (viewDataIndex > -1) {
          newColumns = [...newColumns, baseColumns[viewDataIndex]]
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

  // Get annotators for a task
  const getTaskAnnotators = (task: LabelStudioTask) => {
    return []
  }

  // Calculate inter-annotator agreement
  const getAgreement = (task: LabelStudioTask) => {
    return null
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
  const canUnassign = canAccessProjectData(user, { project: currentProject })

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
                canAssign={canAccessProjectData(user, { project: currentProject })}
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

              <div className="relative hidden sm:block">
                <Button variant="outline" className="gap-2">
                  {t('annotationTab.buttons.orderBy')}
                  <ChevronDownIcon className="h-4 w-4" />
                </Button>
              </div>

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
          <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[800px]">
                <thead className="border-b border-zinc-200 bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800">
                  <tr>
                    {columns
                      .filter((col) => col.visible)
                      .map((column) => {
                        // Handle dynamic data columns
                        if (column.id.startsWith('data_')) {
                          // Find the corresponding data column
                          const dataColumnKey = column.id.replace('data_', '')
                          const dataColumn = dataColumns.find(
                            (dc) => dc.id === dataColumnKey
                          )
                          if (dataColumn) {
                            return (
                              <th
                                key={column.id}
                                className={`min-w-[120px] whitespace-nowrap border-r border-zinc-200 px-3 py-2.5 text-left text-xs font-medium uppercase tracking-wider text-zinc-600 dark:border-zinc-700 dark:text-zinc-400 ${column.width || ''} bg-amber-50/50 dark:bg-amber-900/10`}
                              >
                                {t(column.label)}
                              </th>
                            )
                          }
                          return null
                        }

                        // Skip the single 'data' column if we're using dynamic columns
                        if (column.id === 'data' && useDataColumns) {
                          return null
                        }

                        return (
                          <th
                            key={column.id}
                            className={`whitespace-nowrap border-r border-zinc-200 px-3 py-2.5 text-left text-xs font-medium uppercase tracking-wider text-zinc-600 dark:border-zinc-700 dark:text-zinc-400 ${column.width || ''} ${
                              column.sortable
                                ? 'cursor-pointer select-none transition-colors duration-150 hover:text-zinc-900 dark:hover:text-white'
                                : ''
                            } ${
                              column.type === 'metadata'
                                ? 'bg-blue-50/50 dark:bg-blue-900/10'
                                : column.type === 'data'
                                  ? 'bg-amber-50/50 dark:bg-amber-900/10'
                                  : ''
                            }`}
                            onClick={(e) => {
                              e.preventDefault()
                              if (column.sortable) {
                                handleSort(column.id)
                              }
                            }}
                            role={column.sortable ? 'button' : undefined}
                            tabIndex={column.sortable ? 0 : undefined}
                            onKeyDown={(e) => {
                              if (
                                column.sortable &&
                                (e.key === 'Enter' || e.key === ' ')
                              ) {
                                e.preventDefault()
                                handleSort(column.id)
                              }
                            }}
                          >
                            {column.id === 'select' ? (
                              <TableCheckbox
                                checked={headerCheckboxState.allSelected}
                                indeterminate={
                                  headerCheckboxState.isIndeterminate
                                }
                                onChange={handleSelectAll}
                                data-testid="header-checkbox"
                              />
                            ) : (
                              <div className="flex items-center space-x-1">
                                <span>{t(column.label)}</span>
                                {column.sortable && sortBy === column.id && (
                                  <span className="text-emerald-600">
                                    {sortOrder === 'asc' ? '↑' : '↓'}
                                  </span>
                                )}
                              </div>
                            )}
                          </th>
                        )
                      })}
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-200 dark:divide-zinc-700">
                  {filteredTasks.map((task) => {
                    const annotators = getTaskAnnotators(task)
                    const agreement = getAgreement(task)

                    return (
                      <tr
                        key={task.id}
                        className="h-12 cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-800/50"
                        onClick={() => {
                          setSelectedTaskForComparison(task)
                          setShowComparisonModal(true)
                        }}
                      >
                        {columns
                          .filter((col) => col.visible)
                          .map((column) => {
                            // Handle dynamic metadata columns
                            if (column.id.startsWith('meta_')) {
                              const metaColumnKey = column.id.replace(
                                'meta_',
                                ''
                              )
                              const metaColumn = metadataColumns.find(
                                (mc) => mc.key === metaColumnKey
                              )
                              if (metaColumn) {
                                const value = task.meta?.[metaColumn.key]
                                const formatted = formatCellValue(
                                  value,
                                  metaColumn.type,
                                  50
                                )
                                return (
                                  <td
                                    key={column.id}
                                    className="min-w-[120px] cursor-pointer whitespace-nowrap border-r border-zinc-200 bg-blue-50/30 px-3 py-2 hover:bg-blue-100/30 dark:border-zinc-700 dark:bg-blue-900/5 dark:hover:bg-blue-800/10"
                                    onClick={(e) => {
                                      e.stopPropagation()
                                      handleViewTaskMetadata(task)
                                    }}
                                    title={t(
                                      'annotationTab.display.viewMetadata'
                                    )}
                                  >
                                    {formatted.truncated ? (
                                      <span
                                        className="text-sm text-zinc-900 hover:text-zinc-700 dark:text-white dark:hover:text-zinc-300"
                                        title={formatted.full}
                                      >
                                        {formatted.display}
                                      </span>
                                    ) : (
                                      <span className="text-sm text-zinc-900 dark:text-white">
                                        {formatted.display}
                                      </span>
                                    )}
                                  </td>
                                )
                              }
                              return null
                            }

                            // Handle dynamic data columns
                            if (column.id.startsWith('data_')) {
                              const dataColumnKey = column.id.replace(
                                'data_',
                                ''
                              )
                              const dataColumn = dataColumns.find(
                                (dc) => dc.id === dataColumnKey
                              )
                              if (dataColumn) {
                                // Use nested value getter to support dot notation paths
                                const value = getTaskNestedValue(
                                  task as any,
                                  dataColumn.id
                                )
                                const formatted = formatNestedCellValue(
                                  value,
                                  dataColumn.type,
                                  50
                                )
                                return (
                                  <td
                                    key={column.id}
                                    className="min-w-[120px] whitespace-nowrap border-r border-zinc-200 bg-amber-50/30 px-3 py-2 dark:border-zinc-700 dark:bg-amber-900/5"
                                  >
                                    {formatted.truncated ? (
                                      <span
                                        className="cursor-help text-sm text-zinc-900 hover:text-zinc-700 dark:text-white dark:hover:text-zinc-300"
                                        title={formatted.full}
                                      >
                                        {formatted.display}
                                      </span>
                                    ) : (
                                      <span className="text-sm text-zinc-900 dark:text-white">
                                        {formatted.display}
                                      </span>
                                    )}
                                  </td>
                                )
                              }
                              return null
                            }

                            switch (column.id) {
                              case 'select':
                                return (
                                  <td
                                    key={column.id}
                                    className="border-r border-zinc-200 px-3 py-2 dark:border-zinc-700"
                                    onClick={(e) => e.stopPropagation()}
                                  >
                                    <TableCheckbox
                                      checked={selectedTasks.has(task.id)}
                                      onChange={() => handleSelectTask(task.id)}
                                    />
                                  </td>
                                )
                              case 'id':
                                return (
                                  <td
                                    key={column.id}
                                    className="border-r border-zinc-200 px-3 py-2 font-mono text-sm text-zinc-900 dark:border-zinc-700 dark:text-white"
                                  >
                                    {task.id}
                                  </td>
                                )
                              case 'completed':
                                return (
                                  <td
                                    key={column.id}
                                    className="border-r border-zinc-200 px-3 py-2 dark:border-zinc-700"
                                  >
                                    <div className="flex items-center">
                                      {task.is_labeled ? (
                                        <CheckIcon className="h-4 w-4 text-emerald-500" />
                                      ) : (
                                        <div className="h-4 w-4 rounded border-2 border-zinc-300 dark:border-zinc-600" />
                                      )}
                                    </div>
                                  </td>
                                )
                              case 'assigned':
                                return (
                                  <td
                                    key={column.id}
                                    className="border-r border-zinc-200 px-3 py-2 dark:border-zinc-700"
                                    onClick={(e) => e.stopPropagation()}
                                  >
                                    <AnnotatorBadges
                                      assignments={
                                        (task as any).assignments || []
                                      }
                                      maxVisible={3}
                                      size="sm"
                                      showStatus={true}
                                      onUnassign={handleUnassign}
                                      canUnassign={canUnassign}
                                      onAssign={() => handleAssignTask(task.id)}
                                      canAssign={canUnassign}
                                    />
                                  </td>
                                )
                              // Tags case removed - handled by dynamic metadata columns now
                              case 'data':
                                // Skip the 'data' column if we're using dynamic columns
                                if (useDataColumns) {
                                  return null
                                }
                                return (
                                  <td
                                    key={column.id}
                                    className="border-r border-zinc-200 px-3 py-2 dark:border-zinc-700"
                                  >
                                    <p className="truncate text-sm text-zinc-900 dark:text-white">
                                      {getTaskDisplayValue(task)}
                                    </p>
                                  </td>
                                )
                              case 'annotations':
                                return (
                                  <td
                                    key={column.id}
                                    className="border-r border-zinc-200 px-3 py-2 dark:border-zinc-700"
                                  >
                                    <span className="text-sm font-medium text-zinc-900 dark:text-white">
                                      {Math.max(
                                        0,
                                        task.total_annotations -
                                          task.cancelled_annotations
                                      )}
                                    </span>
                                  </td>
                                )
                              case 'generations':
                                return (
                                  <td
                                    key={column.id}
                                    className="border-r border-zinc-200 px-3 py-2 dark:border-zinc-700"
                                  >
                                    <span className="text-sm text-zinc-900 dark:text-white">
                                      {task.total_generations}
                                    </span>
                                  </td>
                                )
                              case 'annotators':
                                return (
                                  <td
                                    key={column.id}
                                    className="border-r border-zinc-200 px-3 py-2 dark:border-zinc-700"
                                  >
                                    {annotators.length > 0 ? (
                                      <div className="flex -space-x-2">
                                        {annotators.map((name, idx) => (
                                          <UserAvatar
                                            key={idx}
                                            name={name}
                                            size="sm"
                                          />
                                        ))}
                                      </div>
                                    ) : (
                                      <span className="text-sm text-zinc-500 dark:text-zinc-400">
                                        —
                                      </span>
                                    )}
                                  </td>
                                )
                              case 'agreement':
                                return (
                                  <td
                                    key={column.id}
                                    className="border-r border-zinc-200 px-3 py-2 dark:border-zinc-700"
                                  >
                                    {agreement !== null ? (
                                      <div className="flex items-center space-x-2">
                                        <span
                                          className={`text-sm font-medium ${
                                            agreement >= 80
                                              ? 'text-emerald-600'
                                              : agreement >= 60
                                                ? 'text-amber-600'
                                                : 'text-red-600'
                                          }`}
                                        >
                                          {agreement}%
                                        </span>
                                      </div>
                                    ) : (
                                      <span className="text-sm text-zinc-500 dark:text-zinc-400">
                                        —
                                      </span>
                                    )}
                                  </td>
                                )
                              case 'view_data':
                                return (
                                  <td
                                    key={column.id}
                                    className="border-r border-zinc-200 px-3 py-2 dark:border-zinc-700"
                                    onClick={(e) => e.stopPropagation()}
                                  >
                                    <button
                                      onClick={() => handleViewTaskData(task)}
                                      className="rounded p-1 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
                                      title={t('annotation.viewTaskData')}
                                    >
                                      <EyeIcon className="h-4 w-4" />
                                    </button>
                                  </td>
                                )
                              case 'reviewers':
                                return (
                                  <td
                                    key={column.id}
                                    className="border-r border-zinc-200 px-3 py-2 dark:border-zinc-700"
                                  >
                                    <span className="text-sm text-zinc-500">
                                      —
                                    </span>
                                  </td>
                                )
                              case 'created':
                                return (
                                  <td
                                    key={column.id}
                                    className="border-r border-zinc-200 px-3 py-2 dark:border-zinc-700"
                                  >
                                    <span className="whitespace-nowrap text-sm text-zinc-600 dark:text-zinc-400">
                                      {formatDistanceToNow(
                                        new Date(task.created_at),
                                        {
                                          addSuffix: true,
                                        }
                                      ).replace(/\s+/g, ' ')}
                                    </span>
                                  </td>
                                )
                              default:
                                return null
                            }
                          })}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
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

        {/* Pagination — server-driven now that AnnotationTab loads one page
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

      {/* Task Data View Modal */}
      <TaskDataViewModal
        task={viewDataTask}
        isOpen={showDataModal}
        onClose={() => {
          setShowDataModal(false)
          setViewDataTask(null)
        }}
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

      {/* Task Metadata View Modal - removed, now using page navigation */}
    </>
  )
}
