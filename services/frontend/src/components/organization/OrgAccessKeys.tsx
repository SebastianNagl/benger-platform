'use client'

/**
 * "API-Zugänge" dialog of an organization: access keys (`bgr_...`) that
 * scripts and benchmark runners use on the public /api/v1. Opened from the
 * organization tab next to the provider-key dialog. Org admins manage every
 * key of the org, group admins the keys of the groups they administer.
 */

import { AccessKeyManager } from '@/components/accessKeys/AccessKeyManager'
import { useI18n } from '@/contexts/I18nContext'
import { Dialog } from '@headlessui/react'
import { XMarkIcon } from '@heroicons/react/24/outline'

export interface OrgAccessKeysProps {
  organizationId: string
  /** Org-wide admin (or superadmin). */
  isAdmin: boolean
  /** Group admin of at least one group of the org. */
  canManageGroups?: boolean
  /** Active groups the caller administers. */
  adminGroupIds?: string[]
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function OrgAccessKeys({
  organizationId,
  isAdmin,
  canManageGroups = false,
  adminGroupIds = [],
  open,
  onOpenChange,
}: OrgAccessKeysProps) {
  const { t } = useI18n()
  if (!isAdmin && !canManageGroups) return null

  return (
    <Dialog
      open={open}
      onClose={() => onOpenChange(false)}
      className="relative z-50"
    >
      <div
        className="fixed inset-0 bg-black/30 dark:bg-black/50"
        aria-hidden="true"
      />
      <div className="fixed inset-0 flex items-center justify-center p-4">
        <Dialog.Panel
          className="mx-auto w-full max-w-3xl rounded-2xl bg-white shadow-xl dark:bg-zinc-800"
          data-testid="org-access-keys-dialog"
        >
          <div className="flex items-center justify-between border-b border-zinc-200 px-6 py-4 dark:border-zinc-700">
            <div>
              <Dialog.Title className="text-lg font-semibold text-zinc-900 dark:text-white">
                {t('accessKeys.title')}
              </Dialog.Title>
              <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                {t('accessKeys.orgDescription')}
              </p>
            </div>
            <button
              type="button"
              onClick={() => onOpenChange(false)}
              className="rounded-md p-2 text-zinc-400 transition-colors hover:text-zinc-500 dark:text-zinc-500 dark:hover:text-zinc-400"
              aria-label={t('accessKeys.close')}
            >
              <XMarkIcon className="h-5 w-5" />
            </button>
          </div>
          <div className="max-h-[75vh] overflow-y-auto px-6 py-4">
            {open && (
              <AccessKeyManager
                mode="org"
                organizationId={organizationId}
                isAdmin={isAdmin}
                adminGroupIds={adminGroupIds}
                active={open}
              />
            )}
          </div>
        </Dialog.Panel>
      </div>
    </Dialog>
  )
}

export default OrgAccessKeys
