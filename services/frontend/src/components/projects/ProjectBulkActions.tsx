/**
 * Project Bulk Actions component for the Projects List
 *
 * Provides bulk operations for selected projects
 */

import { Button } from '@/components/shared/Button'
import { useI18n } from '@/contexts/I18nContext'
import { Menu } from '@headlessui/react'
import {
  ArchiveBoxIcon,
  ArrowDownTrayIcon,
  ArrowUpTrayIcon,
  ChevronDownIcon,
  DocumentDuplicateIcon,
  EllipsisHorizontalIcon,
  TrashIcon,
} from '@heroicons/react/24/outline'

interface ProjectBulkActionsProps {
  selectedCount: number
  onDelete: () => void
  onFullExport?: () => void
  onArchive?: () => void
  onUnarchive?: () => void
  onDuplicate?: () => void
  /** Whether we're in archived projects context (shows unarchive instead of archive) */
  isArchivedContext?: boolean
}

export function ProjectBulkActions({
  selectedCount,
  onDelete,
  onFullExport,
  onArchive,
  onUnarchive,
  onDuplicate,
  isArchivedContext = false,
}: ProjectBulkActionsProps) {
  const { t } = useI18n()
  const isDisabled = selectedCount === 0

  return (
    <Menu as="div" className="relative inline-block text-left">
      <div>
        <Menu.Button
          as={Button}
          variant="outline"
          className="gap-2"
          disabled={isDisabled}
          data-testid="projects-bulk-actions-button"
        >
          <EllipsisHorizontalIcon className="h-4 w-4" />
          {t('projects.projectBulkActions.actions')}
          {selectedCount > 0 && (
            <span className="ml-1 inline-flex items-center rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium leading-none text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200">
              {selectedCount}
            </span>
          )}
          <ChevronDownIcon className="h-4 w-4" />
        </Menu.Button>
      </div>

      <Menu.Items
        anchor="bottom end"
        className="z-10 w-64 rounded-lg bg-white shadow-lg ring-1 ring-black ring-opacity-5 transition duration-100 ease-out focus:outline-none data-[closed]:scale-95 data-[closed]:transform data-[closed]:opacity-0 dark:bg-zinc-900"
        data-testid="projects-bulk-actions-menu"
      >
        <div className="p-1">
          {selectedCount > 0 ? (
            <>
              <div className="px-3 py-2 text-xs font-medium text-zinc-500 dark:text-zinc-400">
                {t('projects.projectBulkActions.projectsSelected', { count: selectedCount })}
              </div>

              {onFullExport && (
                <Menu.Item>
                  {({ active }) => (
                    <button
                      className={`${
                        active ? 'bg-zinc-100 dark:bg-zinc-800' : ''
                      } group flex w-full items-center rounded-md px-3 py-2 text-sm text-zinc-900 dark:text-white`}
                      onClick={onFullExport}
                      data-testid="projects-bulk-export-option"
                    >
                      <ArrowDownTrayIcon className="mr-3 h-4 w-4 text-emerald-600 dark:text-emerald-400" />
                      {t('projects.projectBulkActions.exportSelected')}
                    </button>
                  )}
                </Menu.Item>
              )}

              {onDuplicate && (
                <Menu.Item>
                  {({ active }) => (
                    <button
                      className={`${
                        active ? 'bg-zinc-100 dark:bg-zinc-800' : ''
                      } group flex w-full items-center rounded-md px-3 py-2 text-sm text-zinc-900 dark:text-white`}
                      onClick={onDuplicate}
                    >
                      <DocumentDuplicateIcon className="mr-3 h-4 w-4" />
                      {t('projects.projectBulkActions.duplicateSelected')}
                    </button>
                  )}
                </Menu.Item>
              )}

              <div className="my-1 border-t border-zinc-200 dark:border-zinc-700" />

              {/* Archive/Unarchive based on context */}
              {isArchivedContext ? (
                <Menu.Item>
                  {({ active }) => (
                    <button
                      className={`${
                        active ? 'bg-zinc-100 dark:bg-zinc-800' : ''
                      } group flex w-full items-center rounded-md px-3 py-2 text-sm text-zinc-900 dark:text-white`}
                      onClick={onUnarchive}
                      data-testid="projects-bulk-unarchive-option"
                    >
                      <ArrowUpTrayIcon className="mr-3 h-4 w-4" />
                      {t('projects.projectBulkActions.unarchiveSelected')}
                    </button>
                  )}
                </Menu.Item>
              ) : (
                <Menu.Item>
                  {({ active }) => (
                    <button
                      className={`${
                        active ? 'bg-zinc-100 dark:bg-zinc-800' : ''
                      } group flex w-full items-center rounded-md px-3 py-2 text-sm text-zinc-900 dark:text-white`}
                      onClick={onArchive}
                      data-testid="projects-bulk-archive-option"
                    >
                      <ArchiveBoxIcon className="mr-3 h-4 w-4" />
                      {t('projects.projectBulkActions.archiveSelected')}
                    </button>
                  )}
                </Menu.Item>
              )}

              <Menu.Item>
                {({ active }) => (
                  <button
                    className={`${
                      active ? 'bg-red-50 dark:bg-red-900/20' : ''
                    } group flex w-full items-center rounded-md px-3 py-2 text-sm text-red-600 dark:text-red-400`}
                    onClick={onDelete}
                    data-testid="projects-bulk-delete-option"
                  >
                    <TrashIcon className="mr-3 h-4 w-4" />
                    {t('projects.projectBulkActions.deleteSelected')}
                  </button>
                )}
              </Menu.Item>
            </>
          ) : (
            <div className="px-3 py-2 text-sm text-zinc-500 dark:text-zinc-400">
              {t('projects.projectBulkActions.selectProjectsPrompt')}
            </div>
          )}
        </div>
      </Menu.Items>
    </Menu>
  )
}
