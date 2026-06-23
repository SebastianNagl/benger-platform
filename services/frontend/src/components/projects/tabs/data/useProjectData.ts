/**
 * useProjectData - data-fetching + row/pagination/filter state for
 * ProjectDataTab.
 *
 * Encapsulates the server-driven page fetch (`projectsAPI.getTasksPage`) plus
 * the pagination/filter/sort state cluster that drives it. Pulled out of
 * ProjectDataTab verbatim so the orchestrator can stay focused on layout and
 * the modal/bulk wiring. Behaviour is unchanged:
 *
 * - `tasks` holds the CURRENT PAGE only; pagination/filters/sort all run
 *   server-side (Phase 6.4). A generic client-side table-state helper would
 *   not fit here, since that pattern sorts/paginates an already-loaded array
 *   in memory.
 * - `filteredTasks` keeps the small client-side filter pass for fields the API
 *   doesn't expose yet (annotator, metadata) on top of the current page.
 * - Sort/status/date/search preferences persist via `useTablePreferences`; the
 *   hook seeds its initial state from them and re-exposes `updatePreference`
 *   so the orchestrator's order-by menu can keep writing through.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'

import { useTablePreferences } from '@/hooks/useColumnSettings'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { projectsAPI } from '@/lib/api/projects'
import { Task as LabelStudioTask } from '@/types/labelStudio'

interface UseProjectDataOptions {
  projectId: string
  userId?: string
}

export function useProjectData({ projectId, userId }: UseProjectDataOptions) {
  // Use persistent table preferences
  const { preferences, updatePreference } = useTablePreferences(
    projectId,
    userId
  )

  // State - using LabelStudio Task type internally for compatibility.
  // `tasks` holds the CURRENT PAGE only; the projects-list page is driven
  // by server-side pagination + filters now. `filteredTasks` keeps the
  // (small) client-side filter pass for fields the API doesn't yet expose
  // (annotator, metadata) on top of the current page.
  const [tasks, setTasks] = useState<LabelStudioTask[]>([])
  const [filteredTasks, setFilteredTasks] = useState<LabelStudioTask[]>([])
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

  // Lag the search input so per-keystroke typing doesn't refire the page
  // fetch.
  const debouncedSearch = useDebouncedValue(searchQuery, 300)

  // Reset to page 1 whenever a filter changes — otherwise the current page
  // index may exceed the new totalPages and the UI shows an empty page.
  useEffect(() => {
    setCurrentPage(1)
  }, [debouncedSearch, filterStatus, filterDateRange.start, filterDateRange.end, sortBy, sortOrder])

  // Map UI sort key to the backend sort columns. Non-server-sortable keys
  // (e.g. people columns) map to undefined and fall back to the default
  // server ordering.
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
  // - metadataFilters: arbitrary JSONB path equality, kept client-side
  // status/date/search/sort all went server-side in Phase 6.4 and operate
  // on the full project before pagination — no need to re-apply them here.
  // (filterAnnotator can't be applied client-side: annotation rows aren't in
  // the task payload. It stays as exposed state for callers but has no effect
  // until a server-side annotator filter lands on /projects/{id}/tasks.)
  useEffect(() => {
    let filtered = tasks

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
  }, [tasks, metadataFilters])

  return {
    // Preferences passthrough
    preferences,
    updatePreference,

    // Rows
    tasks,
    filteredTasks,
    isLoading,

    // Search
    searchQuery,
    setSearchQuery,
    showSearch,
    setShowSearch,
    debouncedSearch,

    // Sort
    sortBy,
    setSortBy,
    sortOrder,
    setSortOrder,
    serverSortBy,

    // Filters
    filterStatus,
    setFilterStatus,
    filterDateRange,
    setFilterDateRange,
    filterAnnotator,
    setFilterAnnotator,
    metadataFilters,
    setMetadataFilters,

    // Pagination
    currentPage,
    setCurrentPage,
    pageSize,
    totalTasks,
    totalPages,

    // Actions
    reloadCurrentPage,
  }
}
