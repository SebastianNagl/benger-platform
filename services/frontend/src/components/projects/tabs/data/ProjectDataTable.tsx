/**
 * ProjectDataTable - the presentational `<table>` block for ProjectDataTab.
 *
 * Pure presentation: receives the already-fetched current-page rows, the
 * resolved column spec, sort/selection state, and the dynamic
 * metadata/data-column descriptors, plus the row/cell event handlers as
 * props. It owns NO data-fetching and NO business logic — the orchestrator
 * keeps all of that.
 *
 * Bespoke (not the shared `@/components/shared/DataTable`) on purpose: this
 * table renders dynamic `meta_`/`data_` columns with their own amber/blue
 * cell backgrounds, uses `TableCheckbox` + `data-testid="header-checkbox"`,
 * and embeds AnnotatorBadges / UserAvatar cells. Swapping in the generic
 * primitive would change the rendered DOM, classNames, and test-ids — which
 * existing Jest tests assert on. Extract-only; the markup below is verbatim
 * from the original inline table.
 */

'use client'

import { AnnotatorBadges } from '@/components/projects/AnnotatorBadges'
import { TableCheckbox } from '@/components/projects/TableCheckbox'
import { UserAvatar } from '@/components/projects/UserAvatar'
import { useI18n } from '@/contexts/I18nContext'
import { Task as LabelStudioTask } from '@/types/labelStudio'
import { formatCellValue } from '@/utils/dataColumnHelpers'
import {
  formatNestedCellValue,
  getTaskNestedValue,
} from '@/utils/nestedDataColumnHelpers'
import {
  CheckIcon,
  EyeIcon,
  PencilSquareIcon,
} from '@heroicons/react/24/outline'
import { formatDistanceToNow } from 'date-fns'

// Define table columns
export interface TableColumn {
  id: string
  label: string
  visible: boolean
  sortable: boolean
  width?: string
  type?: 'metadata' | 'data' | 'system'
}

// Shape of the dynamic data columns derived from nested JSON fields.
interface DataColumnDescriptor {
  id: string
  label: string
  type: any
}

// Shape of the dynamic metadata columns.
interface MetadataColumnDescriptor {
  key: string
  label: string
  type: any
}

interface ProjectDataTableProps {
  rows: LabelStudioTask[]
  columns: TableColumn[]
  canEditTasks: boolean
  dataColumns: DataColumnDescriptor[]
  metadataColumns: MetadataColumnDescriptor[]
  useDataColumns: boolean

  // Sort
  sortBy: string
  sortOrder: 'asc' | 'desc'
  onSort: (columnId: string) => void

  // Selection
  selectedTasks: Set<string>
  headerCheckboxState: { allSelected: boolean; isIndeterminate: boolean }
  onSelectAll: (checked: boolean) => void
  onSelectTask: (taskId: string) => void

  // Assignment
  canUnassign: boolean
  onUnassign: (assignmentId: string) => void
  onAssignTask: (taskId: string) => void

  // Row / cell interactions
  onRowClick: (task: LabelStudioTask) => void
  onOpenGenerations: (task: LabelStudioTask) => void
  onViewTaskData: (task: LabelStudioTask) => void
  onEditTaskData: (task: LabelStudioTask) => void
  onViewTaskMetadata: (task: LabelStudioTask) => void
  getTaskDisplayValue: (task: LabelStudioTask) => string
}

export function ProjectDataTable({
  rows,
  columns,
  canEditTasks,
  dataColumns,
  metadataColumns,
  useDataColumns,
  sortBy,
  sortOrder,
  onSort,
  selectedTasks,
  headerCheckboxState,
  onSelectAll,
  onSelectTask,
  canUnassign,
  onUnassign,
  onAssignTask,
  onRowClick,
  onOpenGenerations,
  onViewTaskData,
  onEditTaskData,
  onViewTaskMetadata,
  getTaskDisplayValue,
}: ProjectDataTableProps) {
  const { t } = useI18n()

  return (
    <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[800px]">
          <thead className="border-b border-zinc-200 bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800">
            <tr>
              {columns
                .filter(
                  (col) =>
                    col.visible &&
                    (col.id !== 'edit_data' || canEditTasks)
                )
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
                          onSort(column.id)
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
                          onSort(column.id)
                        }
                      }}
                    >
                      {column.id === 'select' ? (
                        <TableCheckbox
                          checked={headerCheckboxState.allSelected}
                          indeterminate={
                            headerCheckboxState.isIndeterminate
                          }
                          onChange={onSelectAll}
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
            {rows.map((task) => {
              // People who actually did work on the task (from the
              // serializer), kept separate from assignments.
              const annotators = task.annotators || []
              const reviewers = task.reviewers || []
              // Assignment list split by target_type: annotator
              // assignments ('task') vs Korrektur grader assignments.
              const allAssignments = (task as any).assignments || []
              const annotatorAssignments = allAssignments.filter(
                (a: any) => !a.target_type || a.target_type === 'task'
              )
              const graderAssignments = allAssignments.filter(
                (a: any) =>
                  a.target_type === 'annotation' ||
                  a.target_type === 'generation'
              )

              return (
                <tr
                  key={task.id}
                  className="h-12 cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-800/50"
                  onClick={() => {
                    onRowClick(task)
                  }}
                >
                  {columns
                    .filter(
                      (col) =>
                        col.visible &&
                        (col.id !== 'edit_data' || canEditTasks)
                    )
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
                                onViewTaskMetadata(task)
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
                                onChange={() => onSelectTask(task.id)}
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
                                assignments={annotatorAssignments}
                                maxVisible={3}
                                size="sm"
                                showStatus={true}
                                onUnassign={onUnassign}
                                canUnassign={canUnassign}
                                onAssign={() => onAssignTask(task.id)}
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
                              onClick={(e) => {
                                e.stopPropagation()
                                if (task.total_generations > 0) {
                                  onOpenGenerations(task)
                                }
                              }}
                            >
                              <span
                                className={`text-sm ${
                                  task.total_generations > 0
                                    ? 'cursor-pointer font-medium text-blue-600 hover:underline dark:text-blue-400'
                                    : 'text-zinc-500 dark:text-zinc-400'
                                }`}
                                title={
                                  task.total_generations > 0
                                    ? t('generation.comparison.modal.viewAll')
                                    : undefined
                                }
                              >
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
                                  {annotators.map((person) => (
                                    <UserAvatar
                                      key={person.id}
                                      name={person.name}
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
                        case 'graders':
                          // Korrektur grader assignments (item-level,
                          // target_type annotation/generation). Read-only
                          // here — grading is managed on the /korrektur
                          // page.
                          return (
                            <td
                              key={column.id}
                              className="border-r border-zinc-200 px-3 py-2 dark:border-zinc-700"
                              onClick={(e) => e.stopPropagation()}
                            >
                              {graderAssignments.length > 0 ? (
                                <AnnotatorBadges
                                  assignments={graderAssignments}
                                  maxVisible={3}
                                  size="sm"
                                  showStatus={true}
                                  canUnassign={false}
                                  canAssign={false}
                                />
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
                                onClick={() => onViewTaskData(task)}
                                className="rounded p-1 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
                                title={t('annotation.viewTaskData')}
                              >
                                <EyeIcon className="h-4 w-4" />
                              </button>
                            </td>
                          )
                        case 'edit_data':
                          return (
                            <td
                              key={column.id}
                              className="border-r border-zinc-200 px-3 py-2 dark:border-zinc-700"
                              onClick={(e) => e.stopPropagation()}
                            >
                              {canEditTasks && (
                                <button
                                  onClick={() => onEditTaskData(task)}
                                  className="rounded p-1 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
                                  title={t('annotation.editTaskData')}
                                >
                                  <PencilSquareIcon className="h-4 w-4" />
                                </button>
                              )}
                            </td>
                          )
                        case 'reviewers':
                          // Who actually reviewed an annotation on this
                          // task (Annotation.reviewed_by) — distinct from
                          // graders above.
                          return (
                            <td
                              key={column.id}
                              className="border-r border-zinc-200 px-3 py-2 dark:border-zinc-700"
                            >
                              {reviewers.length > 0 ? (
                                <div className="flex -space-x-2">
                                  {reviewers.map((person) => (
                                    <UserAvatar
                                      key={person.id}
                                      name={person.name}
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
  )
}

export default ProjectDataTable
