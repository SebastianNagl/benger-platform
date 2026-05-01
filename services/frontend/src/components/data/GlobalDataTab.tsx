/**
 * GlobalDataTab - Display all tasks across all projects with pagination and filtering
 * Similar to AnnotationTab but for global data management
 */

'use client'

import { Button } from '@/components/shared/Button'
import { FilterToolbar } from '@/components/shared/FilterToolbar'
import { Input } from '@/components/shared/Input'
import { Pagination } from '@/components/shared/Pagination'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/shared/Select'
import { useToast } from '@/components/shared/Toast'
import { TaskDataViewModal } from '@/components/tasks/TaskDataViewModal'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { apiClient } from '@/lib/api/client'
import { Task } from '@/lib/api/types'
import {
  ArrowDownTrayIcon,
  CheckIcon,
  ChevronDownIcon,
  DocumentMagnifyingGlassIcon,
  EllipsisHorizontalIcon,
  EyeIcon,
  FunnelIcon,
  MagnifyingGlassIcon,
  ViewColumnsIcon,
} from '@heroicons/react/24/outline'
import { formatDistanceToNow } from 'date-fns'
import { useRouter } from 'next/navigation'
import { useCallback, useEffect, useRef, useState } from 'react'

interface GlobalTask extends Task {
  project: {
    id: string
    title: string
    organization: string | null
  }
  project_id?: string // Alternative project reference
  annotations_count: number
  is_labeled?: boolean // Annotation status
  assigned_to?: string // User assignment
  meta?: Record<string, any> // Additional metadata
}

interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export function GlobalDataTab() {
  const { t } = useI18n()
  const { user } = useAuth()
  const { showToast } = useToast()
  const router = useRouter()

  // State
  const [tasks, setTasks] = useState<GlobalTask[]>([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [showSearch, setShowSearch] = useState(false)
  const [selectedTasks, setSelectedTasks] = useState<Set<string>>(new Set())
  const [viewModalTask, setViewModalTask] = useState<GlobalTask | null>(null)

  // Pagination state
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [totalPages, setTotalPages] = useState(0)
  const [totalTasks, setTotalTasks] = useState(0)

  // Filter state
  const [statusFilter, setStatusFilter] = useState<
    'all' | 'completed' | 'incomplete' | 'in_progress'
  >('all')
  const [projectFilter, setProjectFilter] = useState<string[]>([])
  const [assignedFilter, setAssignedFilter] = useState<string | null>(null)
  const [showFilters, setShowFilters] = useState(false)

  // Sort state
  const [sortBy, setSortBy] = useState('created_at')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')

  // Dropdown states
  const [showActionsDropdown, setShowActionsDropdown] = useState(false)
  const [showColumnsDropdown, setShowColumnsDropdown] = useState(false)
  const [showOrderDropdown, setShowOrderDropdown] = useState(false)
  const actionsRef = useRef<HTMLDivElement>(null)
  const columnsRef = useRef<HTMLDivElement>(null)
  const orderRef = useRef<HTMLDivElement>(null)

  // Column visibility state
  const [visibleColumns, setVisibleColumns] = useState({
    id: true,
    project: true,
    status: true,
    assigned: true,
    annotations: true,
    created: true,
    actions: true,
  })

  // Fetch tasks
  const fetchTasks = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({
        page: currentPage.toString(),
        page_size: pageSize.toString(),
        sort_by: sortBy,
        sort_order: sortOrder,
      })

      if (searchQuery) {
        params.append('search', searchQuery)
      }

      if (statusFilter !== 'all') {
        params.append('status', statusFilter)
      }

      if (projectFilter.length > 0) {
        projectFilter.forEach((id) => params.append('project_ids', id))
      }

      if (assignedFilter) {
        params.append('assigned_to', assignedFilter)
      }

      const response = (await apiClient.get(
        `/data/?${params.toString()}`
      )) as PaginatedResponse<GlobalTask>

      setTasks(response.items)
      setTotalPages(response.total_pages)
      setTotalTasks(response.total)
    } catch (error) {
      console.error('Failed to fetch tasks:', error)
      showToast('Failed to load tasks', 'error')
    } finally {
      setLoading(false)
    }
  }, [
    currentPage,
    pageSize,
    sortBy,
    sortOrder,
    searchQuery,
    statusFilter,
    projectFilter,
    assignedFilter,
    showToast,
  ])

  // Initial load
  useEffect(() => {
    fetchTasks()
  }, [fetchTasks])

  // Handle selection
  const toggleTaskSelection = (taskId: string) => {
    const newSelection = new Set(selectedTasks)
    if (newSelection.has(taskId)) {
      newSelection.delete(taskId)
    } else {
      newSelection.add(taskId)
    }
    setSelectedTasks(newSelection)
  }

  const toggleAllSelection = () => {
    if (selectedTasks.size === tasks.length) {
      setSelectedTasks(new Set())
    } else {
      setSelectedTasks(new Set(tasks.map((t) => t.id)))
    }
  }

  // Handle bulk actions
  const handleBulkComplete = async () => {
    if (selectedTasks.size === 0) return

    try {
      await apiClient.post('/data/bulk-update-status', {
        task_ids: Array.from(selectedTasks),
        is_labeled: true,
      })
      showToast('Tasks marked as completed', 'success')
      fetchTasks()
      setSelectedTasks(new Set())
    } catch (error) {
      showToast('Failed to update tasks', 'error')
    }
  }

  const handleBulkIncomplete = async () => {
    if (selectedTasks.size === 0) return

    try {
      await apiClient.post('/data/bulk-update-status', {
        task_ids: Array.from(selectedTasks),
        is_labeled: false,
      })
      showToast('Tasks marked as incomplete', 'success')
      fetchTasks()
      setSelectedTasks(new Set())
    } catch (error) {
      showToast('Failed to update tasks', 'error')
    }
  }

  const handleExport = async (format: 'json' | 'csv' = 'json') => {
    try {
      const params = new URLSearchParams({ format })
      if (selectedTasks.size > 0) {
        Array.from(selectedTasks).forEach((id) => params.append('task_ids', id))
      }

      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || ''}/api/data/export?${params.toString()}`,
        {
          headers: {
            Authorization: `Bearer ${localStorage.getItem('token')}`,
          },
        }
      )

      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `tasks_export_${new Date().toISOString()}.${format}`
      a.click()
      window.URL.revokeObjectURL(url)

      showToast('Export completed', 'success')
    } catch (error) {
      showToast('Failed to export tasks', 'error')
    }
  }

  // Handle column toggle
  const toggleColumn = (columnId: string) => {
    setVisibleColumns((prev) => ({
      ...prev,
      [columnId]: !prev[columnId as keyof typeof prev],
    }))
  }

  // Close dropdowns when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        actionsRef.current &&
        !actionsRef.current.contains(event.target as Node)
      ) {
        setShowActionsDropdown(false)
      }
      if (
        columnsRef.current &&
        !columnsRef.current.contains(event.target as Node)
      ) {
        setShowColumnsDropdown(false)
      }
      if (
        orderRef.current &&
        !orderRef.current.contains(event.target as Node)
      ) {
        setShowOrderDropdown(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Navigate to task
  const navigateToTask = (task: GlobalTask) => {
    router.push(`/projects/${task.project.id}/tasks/${task.id}`)
  }

  if (loading && tasks.length === 0) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <div className="text-center">
          <div className="mx-auto h-12 w-12 animate-spin rounded-full border-b-2 border-emerald-500"></div>
          <p className="mt-4 text-zinc-600 dark:text-zinc-400">
            {t('data.management.loadingTasks')}
          </p>
        </div>
      </div>
    )
  }

  const dataLeftExtras = (
    <>
      {/* Actions Dropdown */}
      <div className="relative inline-block text-left" ref={actionsRef}>
                <Button
                  variant="outline"
                  className="gap-2"
                  disabled={selectedTasks.size === 0}
                  onClick={() => setShowActionsDropdown(!showActionsDropdown)}
                >
                  <EllipsisHorizontalIcon className="h-4 w-4" />
                  {t('data.management.actions')}
                  {selectedTasks.size > 0 && (
                    <span className="ml-1 inline-flex items-center rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-medium text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200">
                      {selectedTasks.size}
                    </span>
                  )}
                  <ChevronDownIcon className="h-4 w-4" />
                </Button>

                {showActionsDropdown && (
                  <div className="absolute left-0 z-10 mt-2 w-56 origin-top-left rounded-lg bg-white shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none dark:bg-zinc-900">
                    <div className="p-1">
                      <div className="px-3 py-2 text-xs font-medium text-zinc-500 dark:text-zinc-400">
                        {t('data.management.tasksSelected', { count: selectedTasks.size })}
                      </div>

                      <button
                        className="group flex w-full items-center rounded-md px-3 py-2 text-sm text-zinc-900 hover:bg-zinc-100 dark:text-white dark:hover:bg-zinc-800"
                        onClick={() => {
                          handleBulkComplete()
                          setShowActionsDropdown(false)
                        }}
                      >
                        <CheckIcon className="mr-3 h-4 w-4 text-green-600" />
                        {t('data.management.markComplete')}
                      </button>

                      <button
                        className="group flex w-full items-center rounded-md px-3 py-2 text-sm text-zinc-900 hover:bg-zinc-100 dark:text-white dark:hover:bg-zinc-800"
                        onClick={() => {
                          handleBulkIncomplete()
                          setShowActionsDropdown(false)
                        }}
                      >
                        <MagnifyingGlassIcon className="mr-3 h-4 w-4 text-yellow-600" />
                        {t('data.management.markIncomplete')}
                      </button>

                      <div className="my-1 border-t border-zinc-200 dark:border-zinc-700" />

                      <button
                        className="group flex w-full items-center rounded-md px-3 py-2 text-sm text-zinc-900 hover:bg-zinc-100 dark:text-white dark:hover:bg-zinc-800"
                        onClick={() => {
                          handleExport('json')
                          setShowActionsDropdown(false)
                        }}
                      >
                        <ArrowDownTrayIcon className="mr-3 h-4 w-4" />
                        {t('data.management.exportJson')}
                      </button>

                      <button
                        className="group flex w-full items-center rounded-md px-3 py-2 text-sm text-zinc-900 hover:bg-zinc-100 dark:text-white dark:hover:bg-zinc-800"
                        onClick={() => {
                          handleExport('csv')
                          setShowActionsDropdown(false)
                        }}
                      >
                        <ArrowDownTrayIcon className="mr-3 h-4 w-4" />
                        {t('data.management.exportCsv')}
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* Columns Dropdown */}
              <div className="relative inline-block text-left" ref={columnsRef}>
                <Button
                  variant="outline"
                  className="gap-2"
                  onClick={() => setShowColumnsDropdown(!showColumnsDropdown)}
                >
                  <ViewColumnsIcon className="h-4 w-4" />
                  {t('data.management.columns')}
                  <ChevronDownIcon className="h-4 w-4" />
                </Button>

                {showColumnsDropdown && (
                  <div className="absolute left-0 z-10 mt-2 w-56 origin-top-left rounded-lg bg-white shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none dark:bg-zinc-900">
                    <div className="p-2">
                      <div className="px-2 py-1 text-xs font-medium text-zinc-500 dark:text-zinc-400">
                        {t('data.management.showHideColumns')}
                      </div>

                      {Object.entries(visibleColumns).map(([key, visible]) => (
                        <label
                          key={key}
                          className="flex items-center rounded px-2 py-1.5 hover:bg-zinc-100 dark:hover:bg-zinc-800"
                        >
                          <input
                            type="checkbox"
                            checked={visible}
                            onChange={() => toggleColumn(key)}
                            className="rounded border-zinc-300"
                          />
                          <span className="ml-2 text-sm capitalize">
                            {key === 'id' ? 'ID' : key}
                          </span>
                        </label>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Order By Dropdown */}
              <div className="relative inline-block text-left" ref={orderRef}>
                <Button
                  variant="outline"
                  className="gap-2"
                  onClick={() => setShowOrderDropdown(!showOrderDropdown)}
                >
                  <ChevronDownIcon className="h-4 w-4" />
                  {t('data.management.orderBy')}
                  <ChevronDownIcon className="h-4 w-4" />
                </Button>

                {showOrderDropdown && (
                  <div className="absolute left-0 z-10 mt-2 w-56 origin-top-left rounded-lg bg-white shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none dark:bg-zinc-900">
                    <div className="p-2">
                      <div className="px-2 py-1 text-xs font-medium text-zinc-500 dark:text-zinc-400">
                        {t('data.management.sortBy')}
                      </div>

                      {[
                        { value: 'created_at', label: t('data.management.createdDate') },
                        { value: 'updated_at', label: t('data.management.updatedDate') },
                        { value: 'is_labeled', label: t('data.management.status') },
                        { value: 'id', label: t('data.management.taskId') },
                      ].map((option) => (
                        <button
                          key={option.value}
                          className="flex w-full items-center justify-between rounded px-2 py-1.5 text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800"
                          onClick={() => {
                            if (sortBy === option.value) {
                              setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
                            } else {
                              setSortBy(option.value)
                              setSortOrder('desc')
                            }
                            setShowOrderDropdown(false)
                          }}
                        >
                          <span
                            className={
                              sortBy === option.value ? 'font-medium' : ''
                            }
                          >
                            {option.label}
                          </span>
                          {sortBy === option.value && (
                            <span className="text-xs text-zinc-500">
                              {sortOrder === 'asc' ? '↑' : '↓'}
                            </span>
                          )}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
    </>
  )

  const dataRightExtras = (
    <>
      <span className="text-sm text-zinc-600 dark:text-zinc-400">
        {t('data.management.totalTasks', { count: totalTasks })}
      </span>
      {selectedTasks.size > 0 && (
        <span className="text-sm font-medium text-emerald-600">
          {t('data.management.selected', { count: selectedTasks.size })}
        </span>
      )}
    </>
  )

  return (
    <div className="space-y-4">
      <FilterToolbar
        searchValue={searchQuery}
        onSearchChange={setSearchQuery}
        searchPlaceholder={t('data.management.searchPlaceholder')}
        searchLabel={t('data.management.search')}
        filtersLabel={t('data.management.filters')}
        hasActiveFilters={
          statusFilter !== 'all' ||
          projectFilter.length > 0 ||
          assignedFilter !== null ||
          searchQuery.trim() !== ''
        }
        onClearFilters={() => {
          setStatusFilter('all')
          setProjectFilter([])
          setAssignedFilter(null)
          setSearchQuery('')
        }}
        clearLabel={t('common.filters.clearAll')}
        leftExtras={dataLeftExtras}
        rightExtras={dataRightExtras}
      >
        <FilterToolbar.Field label={t('data.management.status')}>
          <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v as any)}>
            <SelectTrigger>
              <SelectValue placeholder={t('data.management.all')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('data.management.all')}</SelectItem>
              <SelectItem value="completed">{t('data.management.completed')}</SelectItem>
              <SelectItem value="incomplete">{t('data.management.incomplete')}</SelectItem>
              <SelectItem value="in_progress">{t('data.management.inProgress')}</SelectItem>
            </SelectContent>
          </Select>
        </FilterToolbar.Field>

        <FilterToolbar.Field label={t('data.management.sortBy')}>
          <Select value={sortBy} onValueChange={setSortBy}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="created_at">{t('data.management.created')}</SelectItem>
              <SelectItem value="updated_at">{t('data.management.updated')}</SelectItem>
              <SelectItem value="is_labeled">{t('data.management.status')}</SelectItem>
            </SelectContent>
          </Select>
        </FilterToolbar.Field>

        <FilterToolbar.Field label={t('data.management.order')}>
          <Select value={sortOrder} onValueChange={(v) => setSortOrder(v as 'asc' | 'desc')}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="desc">{t('data.management.newestFirst')}</SelectItem>
              <SelectItem value="asc">{t('data.management.oldestFirst')}</SelectItem>
            </SelectContent>
          </Select>
        </FilterToolbar.Field>
      </FilterToolbar>

      {/* Table */}
      <div className="scrollbar-thin scrollbar-thumb-zinc-300 scrollbar-track-transparent dark:scrollbar-thumb-zinc-600 overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-700">
        <table className="min-w-[1200px] divide-y divide-zinc-200 dark:divide-zinc-700">
          <thead className="bg-zinc-50 dark:bg-zinc-800">
            <tr>
              <th className="px-3 py-3">
                <input
                  type="checkbox"
                  checked={
                    selectedTasks.size === tasks.length && tasks.length > 0
                  }
                  onChange={toggleAllSelection}
                  className="rounded border-zinc-300"
                />
              </th>
              {visibleColumns.id && (
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500">
                  {t('data.management.columnId')}
                </th>
              )}
              {visibleColumns.project && (
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500">
                  {t('data.management.columnProject')}
                </th>
              )}
              {visibleColumns.status && (
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500">
                  {t('data.management.status')}
                </th>
              )}
              {visibleColumns.assigned && (
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500">
                  {t('data.management.columnAssignedTo')}
                </th>
              )}
              {visibleColumns.annotations && (
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500">
                  {t('data.management.columnAnnotations')}
                </th>
              )}
              {visibleColumns.created && (
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500">
                  {t('data.management.created')}
                </th>
              )}
              {visibleColumns.actions && (
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500">
                  {t('data.management.actions')}
                </th>
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-200 bg-white dark:divide-zinc-700 dark:bg-zinc-900">
            {tasks.map((task) => (
              <tr
                key={task.id}
                className="hover:bg-zinc-50 dark:hover:bg-zinc-800"
              >
                <td className="px-3 py-4">
                  <input
                    type="checkbox"
                    checked={selectedTasks.has(task.id)}
                    onChange={() => toggleTaskSelection(task.id)}
                    className="rounded border-zinc-300"
                  />
                </td>
                {visibleColumns.id && (
                  <td className="px-6 py-4 text-sm font-medium text-zinc-900 dark:text-white">
                    {task.id}
                  </td>
                )}
                {visibleColumns.project && (
                  <td className="px-6 py-4 text-sm text-zinc-500 dark:text-zinc-400">
                    <div>
                      <div className="font-medium">{task.project.title}</div>
                      {task.project.organization && (
                        <div className="text-xs text-zinc-400">
                          {task.project.organization}
                        </div>
                      )}
                    </div>
                  </td>
                )}
                {visibleColumns.status && (
                  <td className="px-6 py-4">
                    {task.is_labeled ? (
                      <span className="inline-flex items-center rounded-full bg-green-100 px-2 py-1 text-xs font-medium text-green-800">
                        <CheckIcon className="mr-1 h-3 w-3" />
                        {t('data.management.complete')}
                      </span>
                    ) : (
                      <span className="inline-flex items-center rounded-full bg-yellow-100 px-2 py-1 text-xs font-medium text-yellow-800">
                        {t('data.management.incomplete')}
                      </span>
                    )}
                  </td>
                )}
                {visibleColumns.assigned && (
                  <td className="px-6 py-4 text-sm text-zinc-500 dark:text-zinc-400">
                    {task.assigned_to || '-'}
                  </td>
                )}
                {visibleColumns.annotations && (
                  <td className="px-6 py-4 text-sm text-zinc-500 dark:text-zinc-400">
                    {task.annotations_count}
                  </td>
                )}
                {visibleColumns.created && (
                  <td className="px-6 py-4 text-sm text-zinc-500 dark:text-zinc-400">
                    {task.created_at
                      ? formatDistanceToNow(new Date(task.created_at), {
                          addSuffix: true,
                        })
                      : '-'}
                  </td>
                )}
                {visibleColumns.actions && (
                  <td className="px-6 py-4 text-sm">
                    <div className="flex items-center space-x-2">
                      <button
                        onClick={() => setViewModalTask(task)}
                        className="text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
                      >
                        <EyeIcon className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => navigateToTask(task)}
                        className="text-emerald-600 hover:text-emerald-700"
                      >
                        <DocumentMagnifyingGlassIcon className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalTasks > 0 && (
        <div className="mt-4">
          <Pagination
            currentPage={currentPage}
            totalPages={totalPages}
            totalItems={totalTasks}
            pageSize={pageSize}
            onPageChange={setCurrentPage}
            onPageSizeChange={(newPageSize) => {
              setPageSize(newPageSize)
              setCurrentPage(1) // Reset to first page when changing page size
            }}
            pageSizeOptions={[10, 25, 50, 100]}
          />
        </div>
      )}

      {/* View Modal */}
      {viewModalTask && (
        <TaskDataViewModal
          isOpen={!!viewModalTask}
          onClose={() => setViewModalTask(null)}
          task={viewModalTask}
        />
      )}
    </div>
  )
}
