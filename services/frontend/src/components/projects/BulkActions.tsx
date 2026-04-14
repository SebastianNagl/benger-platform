/**
 * Bulk Actions component for the Project Data Manager
 *
 * Provides bulk operations for selected tasks
 */

import { Button } from '@/components/shared/Button'
import { BulkMetadataEditor } from '@/components/shared/MetadataField'
import { useI18n } from '@/contexts/I18nContext'
import {
  ArchiveBoxIcon,
  ArrowDownTrayIcon,
  ChevronDownIcon,
  DocumentDuplicateIcon,
  EllipsisHorizontalIcon,
  PencilSquareIcon,
  TrashIcon,
  UserGroupIcon,
} from '@heroicons/react/24/outline'
import { useEffect, useRef, useState } from 'react'

interface BulkActionsProps {
  selectedCount: number
  selectedTaskIds?: string[]
  projectId?: string
  onDelete: () => void
  onExport: () => void
  onArchive: () => void
  onAssign?: () => void
  canAssign?: boolean
  onTagsUpdated?: () => void
}

export function BulkActions({
  selectedCount,
  selectedTaskIds = [],
  projectId = '',
  onDelete,
  onExport,
  onArchive,
  onAssign,
  canAssign = false,
  onTagsUpdated,
}: BulkActionsProps) {
  const { t } = useI18n()
  const [showMetadataEditor, setShowMetadataEditor] = useState(false)
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const isDisabled = selectedCount === 0

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setDropdownOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  return (
    <div className="relative inline-block text-left" ref={dropdownRef}>
      <Button
        variant="outline"
        className="gap-2"
        disabled={isDisabled}
        onClick={() => setDropdownOpen(!dropdownOpen)}
      >
        <EllipsisHorizontalIcon className="h-4 w-4" />
        {t('projects.bulkActions.actions')}
        {selectedCount > 0 && (
          <span className="ml-1 inline-flex h-5 w-5 items-center justify-center rounded-full bg-emerald-100 text-xs font-medium text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200">
            {selectedCount}
          </span>
        )}
        <ChevronDownIcon className="h-4 w-4" />
      </Button>

      {dropdownOpen && (
        <div className="absolute left-0 z-10 mt-2 w-56 origin-top-left rounded-lg bg-white shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none dark:bg-zinc-900">
          <div className="p-1">
            {selectedCount > 0 ? (
              <>
                <div className="px-3 py-2 text-xs font-medium text-zinc-500 dark:text-zinc-400">
                  {t('projects.bulkActions.tasksSelected', { count: selectedCount })}
                </div>

                {canAssign && onAssign && (
                  <button
                    className="group flex w-full items-center rounded-md px-3 py-2 text-sm text-zinc-900 hover:bg-zinc-100 dark:text-white dark:hover:bg-zinc-800"
                    onClick={() => {
                      onAssign()
                      setDropdownOpen(false)
                    }}
                  >
                    <UserGroupIcon className="mr-3 h-4 w-4" />
                    {t('projects.bulkActions.assignToAnnotators')}
                  </button>
                )}

                <button
                  className="group flex w-full items-center rounded-md px-3 py-2 text-sm text-zinc-900 hover:bg-zinc-100 dark:text-white dark:hover:bg-zinc-800"
                  onClick={() => {
                    onExport()
                    setDropdownOpen(false)
                  }}
                >
                  <ArrowDownTrayIcon className="mr-3 h-4 w-4" />
                  {t('projects.bulkActions.exportSelected')}
                </button>

                <button
                  className="group flex w-full items-center rounded-md px-3 py-2 text-sm text-zinc-900 hover:bg-zinc-100 dark:text-white dark:hover:bg-zinc-800"
                  onClick={() => {
                    alert(t('projects.bulkActions.duplicateComingSoon'))
                    setDropdownOpen(false)
                  }}
                >
                  <DocumentDuplicateIcon className="mr-3 h-4 w-4" />
                  {t('projects.bulkActions.duplicateSelected')}
                </button>

                <button
                  className="group flex w-full items-center rounded-md px-3 py-2 text-sm text-zinc-900 hover:bg-zinc-100 dark:text-white dark:hover:bg-zinc-800"
                  onClick={() => {
                    setShowMetadataEditor(true)
                    setDropdownOpen(false)
                  }}
                >
                  <PencilSquareIcon className="mr-3 h-4 w-4" />
                  {t('projects.bulkActions.editMetadata')}
                </button>

                <div className="my-1 border-t border-zinc-200 dark:border-zinc-700" />

                <button
                  className="group flex w-full items-center rounded-md px-3 py-2 text-sm text-zinc-900 hover:bg-zinc-100 dark:text-white dark:hover:bg-zinc-800"
                  onClick={() => {
                    onArchive()
                    setDropdownOpen(false)
                  }}
                >
                  <ArchiveBoxIcon className="mr-3 h-4 w-4" />
                  {t('projects.bulkActions.archiveSelected')}
                </button>

                <button
                  className="group flex w-full items-center rounded-md px-3 py-2 text-sm text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20"
                  onClick={() => {
                    onDelete()
                    setDropdownOpen(false)
                  }}
                >
                  <TrashIcon className="mr-3 h-4 w-4" />
                  {t('projects.bulkActions.deleteSelected')}
                </button>
              </>
            ) : (
              <div className="px-3 py-2 text-sm text-zinc-500 dark:text-zinc-400">
                {t('projects.bulkActions.selectTasksPrompt')}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Metadata Editor Modal */}
      {showMetadataEditor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
          <BulkMetadataEditor
            taskIds={selectedTaskIds.map((id) => parseInt(id))}
            onClose={() => setShowMetadataEditor(false)}
            onSuccess={async () => {
              setShowMetadataEditor(false)
              await onTagsUpdated?.() // Keep the same callback for now
            }}
          />
        </div>
      )}
    </div>
  )
}
