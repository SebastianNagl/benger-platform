/**
 * Bulk Actions component for the Project Data Manager
 *
 * Provides bulk operations for selected tasks, through the shared
 * SelectionActions menu every table with row selection uses.
 */

import { BulkMetadataEditor } from '@/components/shared/MetadataField'
import {
  SelectionActions,
  type SelectionAction,
} from '@/components/shared/SelectionActions'
import { useI18n } from '@/contexts/I18nContext'
import {
  ArchiveBoxIcon,
  ArrowDownTrayIcon,
  DocumentDuplicateIcon,
  PencilSquareIcon,
  TrashIcon,
  UserGroupIcon,
} from '@heroicons/react/24/outline'
import { useState } from 'react'

interface BulkActionsProps {
  selectedCount: number
  selectedTaskIds?: string[]
  projectId?: string
  onDelete: () => void
  onExport: () => void
  onArchive: () => void
  onAssign?: () => void
  canAssign?: boolean
  /**
   * Whether the caller may change the project's tasks (metadata, archive,
   * delete, duplicate): real project members only, the API's
   * check_user_can_edit_project. Export stays available either way.
   */
  canModify?: boolean
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
  canModify = true,
  onTagsUpdated,
}: BulkActionsProps) {
  const { t } = useI18n()
  const [showMetadataEditor, setShowMetadataEditor] = useState(false)
  const actions: SelectionAction[] = []
  if (canAssign && onAssign) {
    actions.push({
      id: 'assign',
      label: t('projects.bulkActions.assignToAnnotators'),
      icon: UserGroupIcon,
      onSelect: onAssign,
    })
  }
  actions.push({
    id: 'export',
    label: t('projects.bulkActions.exportSelected'),
    icon: ArrowDownTrayIcon,
    onSelect: onExport,
  })
  if (canModify) {
    actions.push(
      {
        id: 'duplicate',
        label: t('projects.bulkActions.duplicateSelected'),
        icon: DocumentDuplicateIcon,
        onSelect: () => alert(t('projects.bulkActions.duplicateComingSoon')),
      },
      {
        id: 'metadata',
        label: t('projects.bulkActions.editMetadata'),
        icon: PencilSquareIcon,
        onSelect: () => setShowMetadataEditor(true),
      },
      {
        id: 'archive',
        label: t('projects.bulkActions.archiveSelected'),
        icon: ArchiveBoxIcon,
        onSelect: onArchive,
        separatorBefore: true,
      },
      {
        id: 'delete',
        label: t('projects.bulkActions.deleteSelected'),
        icon: TrashIcon,
        onSelect: onDelete,
        danger: true,
      },
    )
  }

  return (
    <>
      <SelectionActions
        selectedCount={selectedCount}
        selectedLabel={t('projects.bulkActions.tasksSelected', {
          count: selectedCount,
        })}
        label={t('projects.bulkActions.actions')}
        actions={actions}
        testId="task-bulk-actions"
      />

      {/* Metadata Editor Modal */}
      {showMetadataEditor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 dark:bg-black/50">
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
    </>
  )
}
