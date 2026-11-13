'use client'

/**
 * Explicit confirmation before a project is opened to every signed-in
 * account with the public CONTRIBUTOR role. That role is broad (full export
 * including reference solutions, generation and evaluation runs), so the
 * choice is never made by a single stray click: the radio only switches
 * after the dialog is confirmed.
 */

import { ConfirmationDialog } from '@/components/shared/ConfirmationDialog'
import { useI18n } from '@/contexts/I18nContext'

interface PublicContributorConfirmDialogProps {
  isOpen: boolean
  onClose: () => void
  onConfirm: () => void
}

export function PublicContributorConfirmDialog({
  isOpen,
  onClose,
  onConfirm,
}: PublicContributorConfirmDialogProps) {
  const { t } = useI18n()
  return (
    <ConfirmationDialog
      isOpen={isOpen}
      onClose={onClose}
      onConfirm={onConfirm}
      title={t('project.permissions.publicContributorConfirm.title')}
      message={t('project.permissions.publicContributorConfirm.message')}
      confirmText={t('project.permissions.publicContributorConfirm.confirm')}
      variant="warning"
    />
  )
}
