/**
 * Project Bulk Actions component for the Projects List
 *
 * Provides bulk operations for selected projects, through the shared
 * SelectionActions menu every table with row selection uses.
 */

import {
  SelectionActions,
  type SelectionAction,
} from '@/components/shared/SelectionActions'
import { useI18n } from '@/contexts/I18nContext'
import {
  ArchiveBoxIcon,
  ArrowDownTrayIcon,
  ArrowUpTrayIcon,
  DocumentDuplicateIcon,
  TrashIcon,
} from '@heroicons/react/24/outline'

interface ProjectBulkActionsProps {
  selectedCount: number
  onDelete: () => void
  onFullExport?: () => void
  /** Full export through the async job flow, one file per project. */
  onAsyncExport?: (format: 'ndjson_gz' | 'comprehensive') => void
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
  onAsyncExport,
  onArchive,
  onUnarchive,
  onDuplicate,
  isArchivedContext = false,
}: ProjectBulkActionsProps) {
  const { t } = useI18n()

  const actions: SelectionAction[] = []
  if (onFullExport) {
    actions.push({
      id: 'export',
      label: t('projects.projectBulkActions.exportSelected'),
      icon: ArrowDownTrayIcon,
      onSelect: onFullExport,
      testId: 'projects-bulk-export-option',
    })
  }
  if (onAsyncExport) {
    for (const format of ['ndjson_gz', 'comprehensive'] as const) {
      actions.push({
        id: `export-${format}`,
        label:
          format === 'ndjson_gz'
            ? t('projects.projectBulkActions.exportNdjsonGz')
            : t('projects.projectBulkActions.exportComprehensive'),
        icon: ArrowDownTrayIcon,
        onSelect: () => onAsyncExport(format),
        testId: `projects-bulk-export-${format}-option`,
      })
    }
  }
  if (onDuplicate) {
    actions.push({
      id: 'duplicate',
      label: t('projects.projectBulkActions.duplicateSelected'),
      icon: DocumentDuplicateIcon,
      onSelect: onDuplicate,
    })
  }
  // Archive or unarchive, depending on the list being shown.
  const archiveAction = isArchivedContext ? onUnarchive : onArchive
  if (archiveAction) {
    actions.push({
      id: isArchivedContext ? 'unarchive' : 'archive',
      label: isArchivedContext
        ? t('projects.projectBulkActions.unarchiveSelected')
        : t('projects.projectBulkActions.archiveSelected'),
      icon: isArchivedContext ? ArrowUpTrayIcon : ArchiveBoxIcon,
      onSelect: archiveAction,
      separatorBefore: true,
      testId: isArchivedContext
        ? 'projects-bulk-unarchive-option'
        : 'projects-bulk-archive-option',
    })
  }
  actions.push({
    id: 'delete',
    label: t('projects.projectBulkActions.deleteSelected'),
    icon: TrashIcon,
    onSelect: onDelete,
    danger: true,
    separatorBefore: !archiveAction,
    testId: 'projects-bulk-delete-option',
  })

  return (
    <SelectionActions
      selectedCount={selectedCount}
      selectedLabel={t('projects.projectBulkActions.projectsSelected', {
        count: selectedCount,
      })}
      label={t('projects.projectBulkActions.actions')}
      actions={actions}
      testId="projects-bulk-actions"
    />
  )
}
