/**
 * Column Selector component for the Project Data Manager
 *
 * Allows users to show/hide table columns
 */

import { Button } from '@/components/shared/Button'
import { useI18n } from '@/contexts/I18nContext'
import { Menu } from '@headlessui/react'
import {
  DragDropContext,
  Draggable,
  Droppable,
  DropResult,
} from '@hello-pangea/dnd'
import {
  Bars3Icon,
  ChevronDownIcon,
  ViewColumnsIcon,
} from '@heroicons/react/24/outline'

interface TableColumn {
  id: string
  label: string
  visible: boolean
  sortable: boolean
  width?: string
  type?: 'metadata' | 'data' | 'system'
}

interface ColumnSelectorProps {
  columns: TableColumn[]
  onToggle: (columnId: string) => void
  onReorder?: (sourceIndex: number, destinationIndex: number) => void
  onReset?: () => void
}

export function ColumnSelector({
  columns,
  onToggle,
  onReorder,
  onReset,
}: ColumnSelectorProps) {
  const { t } = useI18n()
  // Don't allow hiding the select column
  const toggleableColumns = columns.filter((col) => col.id !== 'select')

  // Handle drag end
  const handleDragEnd = (result: DropResult) => {
    if (!result.destination || !onReorder) {
      return
    }

    // The source and destination indices are from the toggleableColumns array
    const sourceIndex = result.source.index
    const destinationIndex = result.destination.index

    // Map these to the actual column indices in the full columns array
    // We need to account for the 'select' column which is filtered out
    const sourceColumn = toggleableColumns[sourceIndex]
    const destColumn = toggleableColumns[destinationIndex]

    if (sourceColumn && destColumn) {
      const realSourceIndex = columns.findIndex(
        (col) => col.id === sourceColumn.id
      )
      const realDestIndex = columns.findIndex((col) => col.id === destColumn.id)

      if (realSourceIndex !== -1 && realDestIndex !== -1) {
        onReorder(realSourceIndex, realDestIndex)
      }
    }
  }

  return (
    <Menu as="div" className="relative inline-block text-left">
      <div>
        <Menu.Button as={Button} variant="outline" className="gap-2">
          <ViewColumnsIcon className="h-4 w-4" />
          {t('projects.columns.label')}
          <ChevronDownIcon className="h-4 w-4" />
        </Menu.Button>
      </div>

      <Menu.Items className="absolute left-0 z-50 mt-2 w-72 origin-top-left rounded-lg bg-white shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none dark:bg-zinc-900">
        <div className="py-2">
          <div className="flex items-center justify-between border-b border-zinc-200 px-4 py-2 text-xs font-medium text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
            <span>{t('projects.columns.showHideReorder')}</span>
            <Bars3Icon className="h-4 w-4" />
          </div>
          <DragDropContext onDragEnd={handleDragEnd}>
            <Droppable droppableId="columns-list">
              {(provided) => (
                <div
                  className="scrollbar-thin scrollbar-thumb-zinc-400 dark:scrollbar-thumb-zinc-600 scrollbar-track-zinc-100 dark:scrollbar-track-zinc-800 max-h-96 overflow-y-auto"
                  {...provided.droppableProps}
                  ref={provided.innerRef}
                >
                  <div className="py-1">
                    {toggleableColumns.map((column, index) => (
                      <Draggable
                        key={column.id}
                        draggableId={column.id}
                        index={index}
                      >
                        {(provided, snapshot) => (
                          <div
                            ref={provided.innerRef}
                            {...provided.draggableProps}
                            className={`${
                              snapshot.isDragging
                                ? 'bg-zinc-100 shadow-lg dark:bg-zinc-800'
                                : ''
                            }`}
                          >
                            <div className="group flex w-full items-center px-2 py-1 text-sm text-zinc-900 transition-colors hover:bg-zinc-50 dark:text-white dark:hover:bg-zinc-800">
                              <div
                                {...provided.dragHandleProps}
                                className="mr-1 cursor-move rounded p-1 hover:bg-zinc-200 dark:hover:bg-zinc-700"
                              >
                                <Bars3Icon className="h-4 w-4 text-zinc-400" />
                              </div>
                              <button
                                className="flex flex-1 items-center"
                                onClick={(e) => {
                                  e.preventDefault()
                                  e.stopPropagation()
                                  onToggle(column.id)
                                }}
                              >
                                <input
                                  type="checkbox"
                                  checked={column.visible}
                                  readOnly
                                  className="pointer-events-none mr-3 h-4 w-4 flex-shrink-0 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                                />
                                <span className="flex-1 truncate text-left">
                                  {column.label}
                                  {column.type && (
                                    <span className="ml-2 text-xs text-zinc-500 dark:text-zinc-400">
                                      ({column.type})
                                    </span>
                                  )}
                                </span>
                              </button>
                            </div>
                          </div>
                        )}
                      </Draggable>
                    ))}
                    {provided.placeholder}
                  </div>
                </div>
              )}
            </Droppable>
          </DragDropContext>
          {onReset && (
            <div className="border-t border-zinc-200 px-4 py-2 dark:border-zinc-700">
              <button
                onClick={onReset}
                className="w-full rounded px-3 py-1.5 text-sm text-zinc-600 transition-colors hover:bg-zinc-50 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-white"
              >
                {t('projects.columns.resetToDefault')}
              </button>
            </div>
          )}
        </div>
      </Menu.Items>
    </Menu>
  )
}
