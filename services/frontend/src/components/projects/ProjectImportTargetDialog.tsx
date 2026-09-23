'use client'

import { Button } from '@/components/shared/Button'
import { Dialog } from '@/components/shared/Dialog'
import { useI18n } from '@/contexts/I18nContext'

export interface ImportTargetOrganization {
  id: string
  name: string
}

/** The radio value for a private import (no organization owns the copy). */
export const PRIVATE_IMPORT_TARGET = 'private'

interface ProjectImportTargetDialogProps {
  isOpen: boolean
  /** Organizations the user may create projects in (ORG_ADMIN/CONTRIBUTOR). */
  organizations: ImportTargetOrganization[]
  /** An organization id, PRIVATE_IMPORT_TARGET, or null while nothing is chosen. */
  value: string | null
  onChange: (value: string) => void
  onConfirm: () => void
  onClose: () => void
}

/**
 * Asks where a create-new project import should land before the file picker
 * opens, the way the creation wizard names its target. "Private" is always
 * offered; the caller preselects the only organization a user may create in.
 */
export function ProjectImportTargetDialog({
  isOpen,
  organizations,
  value,
  onChange,
  onConfirm,
  onClose,
}: ProjectImportTargetDialogProps) {
  const { t } = useI18n()
  const options = [
    ...organizations.map((o) => ({ value: o.id, label: o.name })),
    {
      value: PRIVATE_IMPORT_TARGET,
      label: t('projects.list.importTargetPrivate'),
    },
  ]

  return (
    <Dialog
      isOpen={isOpen}
      onClose={onClose}
      title={t('projects.list.importTargetTitle')}
    >
      <p className="mb-4 text-sm text-zinc-600 dark:text-zinc-400">
        {t('projects.list.importTargetDescription')}
      </p>
      <fieldset className="space-y-2" data-testid="project-import-target">
        {options.map((option) => (
          <label
            key={option.value}
            className="flex cursor-pointer items-center gap-3 rounded-md px-2 py-1.5 text-sm text-zinc-900 hover:bg-zinc-50 dark:text-white dark:hover:bg-zinc-800"
          >
            <input
              type="radio"
              name="project-import-target"
              value={option.value}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
              data-testid={`project-import-target-${option.value}`}
            />
            <span className="truncate">{option.label}</span>
          </label>
        ))}
      </fieldset>
      <div className="mt-6 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>
          {t('projects.list.importTargetCancel')}
        </Button>
        <Button
          variant="primary"
          onClick={onConfirm}
          disabled={value === null}
          data-testid="project-import-target-confirm"
        >
          {t('projects.list.importTargetChooseFile')}
        </Button>
      </div>
    </Dialog>
  )
}
