/**
 * ProjectListTable component - Table-based project list following BenGer styling
 */

import { ProjectBulkActions } from '@/components/projects/ProjectBulkActions'
import { TableCheckbox } from '@/components/projects/TableCheckbox'
import { Button } from '@/components/shared/Button'
import { FilterToolbar } from '@/components/shared/FilterToolbar'
import { Pagination } from '@/components/shared/Pagination'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/shared/Select'
import { useToast } from '@/components/shared/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { useConfirm } from '@/hooks/useDialogs'
import { projectsAPI } from '@/lib/api/projects'
import { useProjectStore } from '@/stores/projectStore'
import { Project } from '@/types/labelStudio'
import { parseSubdomain } from '@/lib/utils/subdomain'
import { canCreateProjects } from '@/utils/permissions'
import {
  ArchiveBoxIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  CloudArrowUpIcon,
  FolderIcon,
  PlusIcon,
} from '@heroicons/react/24/outline'
import { formatDistanceToNow } from 'date-fns'
import { de } from 'date-fns/locale'
import { useRouter } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'

type SortField = 'title' | 'created_at' | 'task_count' | 'progress'
type SortOrder = 'asc' | 'desc'

interface ProjectListTableProps {
  /** Show only archived projects and enable unarchive functionality */
  showArchivedOnly?: boolean
}

export function ProjectListTable({
  showArchivedOnly = false,
}: ProjectListTableProps) {
  const router = useRouter()
  const { addToast, removeToast } = useToast()
  const confirm = useConfirm()
  const { t } = useI18n()
  const { user } = useAuth()
  const {
    projects,
    loading,
    fetchProjects,
    setSearchQuery,
    searchQuery,
    currentPage,
    pageSize,
    totalProjects,
    totalPages,
    setCurrentPage,
    setPageSize,
  } = useProjectStore()

  const [sortField, setSortField] = useState<SortField>('created_at')
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc')
  const [localSearchQuery, setLocalSearchQuery] = useState('')
  const [selectedProjects, setSelectedProjects] = useState<Set<string>>(
    new Set()
  )
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Check if user has permissions to create/modify projects
  const { isPrivateMode } = typeof window !== 'undefined' ? parseSubdomain() : { isPrivateMode: true }
  const userCanCreateProjects = canCreateProjects(user, { isPrivateMode })

  useEffect(() => {
    fetchProjects(undefined, undefined, showArchivedOnly)
  }, [fetchProjects, showArchivedOnly])

  // Clear selections when page changes
  useEffect(() => {
    setSelectedProjects(new Set())
  }, [currentPage])

  // Update search query in store with debounce
  useEffect(() => {
    const delayDebounceFn = setTimeout(() => {
      setSearchQuery(localSearchQuery)
    }, 300)

    return () => clearTimeout(delayDebounceFn)
  }, [localSearchQuery, setSearchQuery])

  // Fetch projects when search query changes in the store
  useEffect(() => {
    fetchProjects(undefined, undefined, showArchivedOnly)
  }, [searchQuery, fetchProjects, showArchivedOnly])

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortOrder('asc')
    }
  }

  const getProgress = (project: Project) => {
    // Use server-calculated progress_percentage if available (Issue #257)
    if (project.progress_percentage !== undefined) {
      return Math.round(project.progress_percentage)
    }
    // Fallback to old calculation for backward compatibility, capped at 100%
    const taskCount = project.task_count ?? 0
    const annotationCount = project.annotation_count ?? 0
    return taskCount > 0
      ? Math.min(100, Math.round((annotationCount / taskCount) * 100))
      : 0
  }

  // Handle project selection
  const handleSelectProject = (projectId: string) => {
    setSelectedProjects((prev) => {
      const newSet = new Set(prev)
      if (newSet.has(projectId)) {
        newSet.delete(projectId)
      } else {
        newSet.add(projectId)
      }
      return newSet
    })
  }

  const handleSelectAll = (checked: boolean) => {
    const currentPageProjectIds = sortedProjects.map((p) => p.id)

    if (checked) {
      // Select all projects on the current page
      setSelectedProjects((prev) => {
        const newSet = new Set(prev)
        currentPageProjectIds.forEach((id) => newSet.add(id))
        return newSet
      })
    } else {
      // Deselect all projects on the current page
      setSelectedProjects((prev) => {
        const newSet = new Set(prev)
        currentPageProjectIds.forEach((id) => newSet.delete(id))
        return newSet
      })
    }
  }

  // Bulk operation handlers
  const handleBulkDelete = async () => {
    if (selectedProjects.size === 0) return

    const confirmed = await confirm({
      title: t('projects.list.deleteProjectsTitle'),
      message: t('projects.list.deleteProjectsMessage', { count: selectedProjects.size }),
      confirmText: t('projects.list.delete'),
      variant: 'danger',
    })
    if (!confirmed) return

    try {
      const projectIds = Array.from(selectedProjects)
      const result = await projectsAPI.bulkDeleteProjects(projectIds)

      if (result.deleted === 0) {
        addToast(
          t('projects.list.noProjectsDeleted'),
          'warning'
        )
      } else if (result.deleted < projectIds.length) {
        addToast(
          t('projects.list.partialDeleteWarning', { deleted: result.deleted, total: projectIds.length }),
          'warning'
        )
      } else {
        addToast(t('toasts.projects.deleted', { count: result.deleted }), 'success')
      }

      setSelectedProjects(new Set())
      // Refresh projects list immediately after deletion completes with correct filter
      await fetchProjects(undefined, undefined, showArchivedOnly)
    } catch (error) {
      console.error('Failed to delete projects:', error)
      addToast(t('toasts.projects.deleteFailed'), 'error')
    }
  }

  const handleBulkExport = async (fullExport: boolean = false) => {
    if (selectedProjects.size === 0) return

    // Create a loading toast message
    const loadingMessage = fullExport
      ? t('projects.list.exportingFullProjects', { count: selectedProjects.size })
      : t('projects.list.exportingProjectData', { count: selectedProjects.size })
    let toastId: string | undefined

    try {
      const projectIds = Array.from(selectedProjects)
      // Show loading toast (now auto-removes duplicates with same message)
      toastId = addToast(
        loadingMessage,
        'info',
        0 // Keep toast until we update it
      )

      const startTime = Date.now()
      const blob = fullExport
        ? await projectsAPI.bulkExportFullProjects(projectIds)
        : await projectsAPI.bulkExportProjects(projectIds, 'json', true)

      const exportTime = ((Date.now() - startTime) / 1000).toFixed(1)

      // Validate that we received a proper Blob
      if (!blob || !(blob instanceof Blob)) {
        throw new Error(
          `Invalid response from server: expected Blob, got ${typeof blob}. ${
            blob ? `Response: ${JSON.stringify(blob).substring(0, 100)}...` : ''
          }`
        )
      }

      // Check if the blob has a reasonable size (not just an error message)
      if (blob.size === 0) {
        throw new Error('Received empty file from server')
      }

      // Download the exported file
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.style.display = 'none'
      a.href = url
      const dateStr = new Date().toISOString().split('T')[0]
      a.download = fullExport
        ? `benger-projects-full-${dateStr}.zip`
        : `projects-export-${dateStr}.json`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)

      // Remove the loading toast
      if (toastId) {
        removeToast(toastId)
      }

      // Success notification with timing (with normal duration)
      addToast(
        fullExport
          ? t('projects.list.exportFullSuccess', { count: selectedProjects.size, time: exportTime })
          : t('projects.list.exportSuccess', { count: selectedProjects.size, time: exportTime }),
        'success',
        5000 // Auto-dismiss after 5 seconds
      )
      setSelectedProjects(new Set())
    } catch (error) {
      console.error('Failed to export projects:', error)

      // Remove the loading toast on error
      if (toastId) {
        removeToast(toastId)
      }
      addToast(
        t('projects.list.exportFailed', { error: error instanceof Error ? error.message : t('projects.list.unknownError') }),
        'error'
      )
    }
  }

  const handleImportProject = async (
    event: React.ChangeEvent<HTMLInputElement>
  ) => {
    const file = event.target.files?.[0]
    if (!file) return

    if (!file.name.endsWith('.json') && !file.name.endsWith('.zip')) {
      addToast(t('toasts.projects.selectJsonOrZip'), 'error')
      return
    }

    // Show file size for user awareness
    const fileSizeMB = (file.size / (1024 * 1024)).toFixed(2)

    try {
      addToast(
        t('projects.list.importingProject', { filename: file.name, size: fileSizeMB }),
        'info'
      )

      const startTime = Date.now()
      const result = await projectsAPI.importProject(file)
      const importTime = ((Date.now() - startTime) / 1000).toFixed(1)

      // Show detailed success message with statistics
      const statsMessage = result.statistics
        ? t('projects.list.importStats', {
            tasks: result.statistics.tasks_imported || 0,
            annotations: result.statistics.annotations_imported || 0,
          })
        : ''

      addToast(
        t('projects.list.importSuccess', { title: result.project_title, stats: statsMessage, time: importTime }),
        'success'
      )

      // Clear file input
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }

      // Refresh projects list
      await fetchProjects(undefined, undefined, showArchivedOnly)

      // Navigate to the imported project
      router.push(result.project_url)
    } catch (error) {
      console.error('Failed to import project:', error)

      // Provide specific error message if available
      let errorMessage = t('projects.list.importFailed')
      if (error instanceof Error) {
        if (error.message.includes('JSON')) {
          errorMessage = t('projects.list.invalidJsonFormat')
        } else if (error.message.includes('format_version')) {
          errorMessage = t('projects.list.unsupportedFileFormat')
        } else if (error.message.includes('required')) {
          errorMessage = t('projects.list.missingRequiredFields')
        } else {
          errorMessage = error.message
        }
      }

      addToast(errorMessage, 'error')

      // Clear file input on error
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

  const handleBulkArchive = async () => {
    if (selectedProjects.size === 0) return

    const confirmed = await confirm({
      title: t('projects.bulkActions.archiveTitle'),
      message: t('projects.bulkActions.archiveMessage').replace(
        '{count}',
        selectedProjects.size.toString()
      ),
      confirmText: t('projects.bulkActions.archive'),
      variant: 'warning',
    })
    if (!confirmed) return

    try {
      const projectIds = Array.from(selectedProjects)
      const result = await projectsAPI.bulkArchiveProjects(projectIds)
      addToast(
        t('projects.bulkActions.archiveSuccess').replace(
          '{count}',
          result.archived.toString()
        ),
        'success'
      )
      setSelectedProjects(new Set())
      // Refresh projects list immediately after operation completes with correct filter
      await fetchProjects(undefined, undefined, showArchivedOnly)
    } catch (error) {
      console.error('Failed to archive projects:', error)
      addToast(t('toasts.projects.archiveFailed'), 'error')
    }
  }

  const handleBulkUnarchive = async () => {
    if (selectedProjects.size === 0) return

    const confirmed = await confirm({
      title: t('projects.bulkActions.unarchiveTitle'),
      message: t('projects.bulkActions.unarchiveMessage').replace(
        '{count}',
        selectedProjects.size.toString()
      ),
      confirmText: t('projects.bulkActions.unarchive'),
      variant: 'info',
    })
    if (!confirmed) return

    try {
      const projectIds = Array.from(selectedProjects)
      const result = await projectsAPI.bulkUnarchiveProjects(projectIds)
      addToast(
        t('projects.bulkActions.unarchiveSuccess').replace(
          '{count}',
          result.unarchived.toString()
        ),
        'success'
      )
      setSelectedProjects(new Set())
      // Refresh projects list immediately after operation completes with correct filter
      await fetchProjects(undefined, undefined, showArchivedOnly)
    } catch (error) {
      console.error('Failed to unarchive projects:', error)
      addToast(t('toasts.projects.unarchiveFailed'), 'error')
    }
  }

  // Projects are already filtered by search and archive status on the backend
  const sortedProjects = [...(projects || [])].sort((a, b) => {
    let aValue: any
    let bValue: any

    switch (sortField) {
      case 'title':
        aValue = a.title.toLowerCase()
        bValue = b.title.toLowerCase()
        break
      case 'created_at':
        aValue = new Date(a.created_at).getTime()
        bValue = new Date(b.created_at).getTime()
        break
      case 'task_count':
        aValue = a.task_count
        bValue = b.task_count
        break
      case 'progress':
        aValue = getProgress(a)
        bValue = getProgress(b)
        break
    }

    if (sortOrder === 'asc') {
      return aValue > bValue ? 1 : -1
    } else {
      return aValue < bValue ? 1 : -1
    }
  })

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) {
      return <div className="h-4 w-4" />
    }
    return sortOrder === 'asc' ? (
      <ChevronUpIcon className="h-4 w-4" />
    ) : (
      <ChevronDownIcon className="h-4 w-4" />
    )
  }

  if (loading && (!projects || projects.length === 0)) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <div className="border-primary h-8 w-8 animate-spin rounded-full border-b-2"></div>
      </div>
    )
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-zinc-900 dark:text-white sm:text-3xl">
              {showArchivedOnly
                ? `${t('projects.archived')} ${t('projects.title')}`
                : t('projects.title')}
            </h1>
          </div>
          <div className="flex items-center gap-3">
            {!showArchivedOnly && userCanCreateProjects && (
              <Button
                onClick={() => router.push('/projects/archived')}
                variant="outline"
                data-testid="projects-archived-button"
              >
                <ArchiveBoxIcon className="h-4 w-4" />
                {t('projects.archived')}
              </Button>
            )}
            {showArchivedOnly && userCanCreateProjects && (
              <Button
                onClick={() => router.push('/projects')}
                variant="outline"
                data-testid="projects-active-button"
              >
                <FolderIcon className="h-4 w-4" />
                {t('projects.activeProjects')}
              </Button>
            )}
            {!showArchivedOnly && userCanCreateProjects && (
              <>
                <Button
                  onClick={() => fileInputRef.current?.click()}
                  variant="outline"
                  data-testid="projects-import-button"
                >
                  <CloudArrowUpIcon className="h-4 w-4" />
                  {t('projects.importProject')}
                </Button>
                <Button
                  onClick={() => router.push('/projects/create')}
                  variant="filled"
                  data-testid="projects-create-button"
                >
                  <PlusIcon className="h-4 w-4" />
                  {t('projects.newProject')}
                </Button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Search and Bulk Actions */}
      <div className="space-y-4">
        <FilterToolbar
          searchValue={localSearchQuery}
          onSearchChange={setLocalSearchQuery}
          searchPlaceholder={t('projects.searchPlaceholder')}
          searchLabel={t('common.filters.search')}
          filtersLabel={t('common.filters.filters')}
          hasActiveFilters={
            sortField !== 'created_at' ||
            sortOrder !== 'desc' ||
            localSearchQuery.trim() !== ''
          }
          onClearFilters={() => {
            setSortField('created_at')
            setSortOrder('desc')
            setLocalSearchQuery('')
          }}
          clearLabel={t('common.filters.clearAll')}
          rightExtras={
            <span className="text-sm text-zinc-600 dark:text-zinc-400">
              {selectedProjects.size > 0 ? (
                <span
                  className="font-medium text-zinc-900 dark:text-white"
                  data-testid="projects-selection-count"
                >
                  {t('projects.list.projectsSelected', { count: selectedProjects.size })}
                </span>
              ) : (
                t('projects.list.showingResults', { shown: sortedProjects.length, total: totalProjects })
              )}
            </span>
          }
        >
          <FilterToolbar.Field label={t('common.filters.sortBy')}>
            <Select
              value={sortField}
              onValueChange={(v) => setSortField(v as SortField)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="title">{t('projects.list.sortTitle')}</SelectItem>
                <SelectItem value="created_at">{t('projects.list.sortCreated')}</SelectItem>
                <SelectItem value="task_count">{t('projects.list.sortTaskCount')}</SelectItem>
                <SelectItem value="progress">{t('projects.list.sortProgress')}</SelectItem>
              </SelectContent>
            </Select>
          </FilterToolbar.Field>
          <FilterToolbar.Field label={t('common.filters.order')}>
            <Select
              value={sortOrder}
              onValueChange={(v) => setSortOrder(v as SortOrder)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="asc">{t('common.filters.asc')}</SelectItem>
                <SelectItem value="desc">{t('common.filters.desc')}</SelectItem>
              </SelectContent>
            </Select>
          </FilterToolbar.Field>
        </FilterToolbar>

        {/* Bulk Actions */}
        {selectedProjects.size > 0 && userCanCreateProjects && (
          <div className="flex items-center justify-end space-x-3">
            <ProjectBulkActions
              selectedCount={selectedProjects.size}
              onDelete={handleBulkDelete}
              onFullExport={() => handleBulkExport(true)}
              onArchive={showArchivedOnly ? undefined : handleBulkArchive}
              onUnarchive={showArchivedOnly ? handleBulkUnarchive : undefined}
              isArchivedContext={showArchivedOnly}
            />
          </div>
        )}
      </div>

      {/* Table */}
      <div className="mt-6 overflow-hidden rounded-lg bg-white shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-900 dark:ring-white/10">
        <div className="overflow-x-auto">
          <table
            className="min-w-full divide-y divide-zinc-200 dark:divide-zinc-700"
            data-testid="projects-table"
          >
            <thead className="bg-zinc-50 dark:bg-zinc-800">
              <tr>
                {userCanCreateProjects && (
                  <th scope="col" className="w-12 px-6 py-3">
                    <TableCheckbox
                      checked={
                        sortedProjects.length > 0 &&
                        sortedProjects.every((p) => selectedProjects.has(p.id))
                      }
                      indeterminate={
                        sortedProjects.length > 0 &&
                        sortedProjects.some((p) =>
                          selectedProjects.has(p.id)
                        ) &&
                        !sortedProjects.every((p) => selectedProjects.has(p.id))
                      }
                      onChange={(checked) => handleSelectAll(checked)}
                      data-testid="projects-table-header-checkbox"
                    />
                  </th>
                )}
                <th
                  scope="col"
                  className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400"
                >
                  <button
                    onClick={() => handleSort('title')}
                    className="group inline-flex items-center space-x-1 hover:text-zinc-900 dark:hover:text-zinc-100"
                  >
                    <span>{t('projects.table.project')}</span>
                    <SortIcon field="title" />
                  </button>
                </th>
                <th
                  scope="col"
                  className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400"
                >
                  <button
                    onClick={() => handleSort('task_count')}
                    className="group inline-flex items-center space-x-1 hover:text-zinc-900 dark:hover:text-zinc-100"
                  >
                    <span>{t('projects.table.tasks')}</span>
                    <SortIcon field="task_count" />
                  </button>
                </th>
                <th
                  scope="col"
                  className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400"
                >
                  {t('projects.table.annotations')}
                </th>
                <th
                  scope="col"
                  className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400"
                >
                  <button
                    onClick={() => handleSort('progress')}
                    className="group inline-flex items-center space-x-1 hover:text-zinc-900 dark:hover:text-zinc-100"
                  >
                    <span>{t('projects.table.progress')}</span>
                    <SortIcon field="progress" />
                  </button>
                </th>
                <th
                  scope="col"
                  className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400"
                >
                  <button
                    onClick={() => handleSort('created_at')}
                    className="group inline-flex items-center space-x-1 hover:text-zinc-900 dark:hover:text-zinc-100"
                  >
                    <span>{t('projects.list.created')}</span>
                    <SortIcon field="created_at" />
                  </button>
                </th>
                <th scope="col" className="relative px-6 py-3">
                  <span className="sr-only">{t('projects.list.actions')}</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-200 bg-white dark:divide-zinc-700 dark:bg-zinc-900">
              {sortedProjects.length === 0 ? (
                <tr>
                  <td
                    colSpan={userCanCreateProjects ? 7 : 6}
                    className="px-6 py-12 text-center"
                  >
                    <div
                      className="text-zinc-500 dark:text-zinc-400"
                      data-testid="projects-empty-state"
                    >
                      {searchQuery ? (
                        <>
                          <p className="text-sm">
                            {t('projects.noProjectsMatchFilters')}
                          </p>
                          <p className="mt-1 text-xs">
                            {t('projects.adjustFilters')}
                          </p>
                        </>
                      ) : (
                        <>
                          <p className="text-sm">{t('projects.noProjects')}</p>
                          {userCanCreateProjects && (
                            <button
                              onClick={() => router.push('/projects/create')}
                              className="mt-2 text-sm text-emerald-600 hover:text-emerald-500 dark:text-emerald-400 dark:hover:text-emerald-300"
                            >
                              {t('projects.noProjectsDescription')}
                            </button>
                          )}
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ) : (
                sortedProjects.map((project) => {
                  const progress = getProgress(project)

                  return (
                    <tr
                      key={project.id}
                      className="transition-colors hover:bg-zinc-50 dark:hover:bg-zinc-800/50"
                      data-testid={`projects-table-row-${project.id}`}
                    >
                      {userCanCreateProjects && (
                        <td
                          className="px-6 py-4"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <TableCheckbox
                            checked={selectedProjects.has(project.id)}
                            onChange={() => handleSelectProject(project.id)}
                            data-testid={`projects-table-checkbox-${project.id}`}
                          />
                        </td>
                      )}
                      <td
                        className="cursor-pointer px-6 py-4"
                        onClick={() => router.push(`/projects/${project.id}`)}
                      >
                        <div>
                          <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                            {project.title}
                          </div>
                          {project.description && (
                            <div className="max-w-md truncate text-sm text-zinc-500 dark:text-zinc-400">
                              {project.description}
                            </div>
                          )}
                        </div>
                      </td>
                      <td
                        className="cursor-pointer whitespace-nowrap px-6 py-4 text-sm text-zinc-900 dark:text-zinc-100"
                        onClick={() => router.push(`/projects/${project.id}`)}
                      >
                        {project.task_count}
                      </td>
                      <td
                        className="cursor-pointer whitespace-nowrap px-6 py-4 text-sm text-zinc-900 dark:text-zinc-100"
                        onClick={() => router.push(`/projects/${project.id}`)}
                      >
                        {project.annotation_count}
                      </td>
                      <td
                        className="cursor-pointer whitespace-nowrap px-6 py-4"
                        onClick={() => router.push(`/projects/${project.id}`)}
                      >
                        <div className="flex items-center">
                          <div className="max-w-[100px] flex-1">
                            <div className="mb-1 text-sm text-zinc-900 dark:text-zinc-100">
                              {progress}%
                            </div>
                            <div className="h-1.5 w-full rounded-full bg-zinc-200 dark:bg-zinc-700">
                              <div
                                className="h-1.5 rounded-full bg-emerald-600 transition-all dark:bg-emerald-500"
                                style={{ width: `${Math.min(100, progress)}%` }}
                              />
                            </div>
                          </div>
                        </div>
                      </td>
                      <td
                        className="cursor-pointer whitespace-nowrap px-6 py-4 text-sm text-zinc-500 dark:text-zinc-400"
                        onClick={() => router.push(`/projects/${project.id}`)}
                      >
                        {formatDistanceToNow(new Date(project.created_at), {
                          addSuffix: true,
                          locale: de,
                        })}
                      </td>
                      <td className="whitespace-nowrap px-6 py-4 text-right text-sm font-medium">
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            router.push(`/projects/${project.id}/label`)
                          }}
                          className="mr-4 text-emerald-600 hover:text-emerald-500 dark:text-emerald-400 dark:hover:text-emerald-300"
                        >
                          {t('projects.list.label')}
                        </button>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      <div className="mt-6">
        <Pagination
          currentPage={currentPage}
          totalPages={totalPages}
          totalItems={totalProjects}
          pageSize={pageSize}
          onPageChange={setCurrentPage}
          onPageSizeChange={setPageSize}
          pageSizeOptions={[25, 50, 100, 200]}
        />
      </div>

      {/* Hidden file input for project import */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".json,.zip"
        onChange={handleImportProject}
        style={{ display: 'none' }}
        data-testid="project-import-file-input"
      />
    </div>
  )
}
