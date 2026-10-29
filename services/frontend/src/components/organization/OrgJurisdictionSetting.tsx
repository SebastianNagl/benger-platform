'use client'

import { Dialog } from '@headlessui/react'
import { XMarkIcon } from '@heroicons/react/24/outline'
import { useState } from 'react'

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shared/Select'
import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import { organizationsAPI } from '@/lib/api/organizations'
import {
  JURISDICTIONS,
  orgJurisdiction,
  type Jurisdiction,
} from '@/lib/jurisdiction'

/**
 * The organization's jurisdiction (Rechtsordnung): which legal system its
 * members teach and examine in. Decides the jurisdiction-specific project
 * types the project wizard offers. Rarely changed, so org admins reach it
 * from the organization's "Mehr" menu; it saves on selection.
 */
export function OrgJurisdictionSetting({
  organization,
  open,
  onOpenChange,
  onSaved,
}: {
  organization: { id: string; jurisdiction?: unknown }
  open: boolean
  onOpenChange: (open: boolean) => void
  onSaved?: (jurisdiction: Jurisdiction) => void | Promise<void>
}) {
  const { t } = useI18n()
  const { addToast } = useToast()
  const [saving, setSaving] = useState(false)
  const current = orgJurisdiction(organization)

  const save = async (next: Jurisdiction) => {
    if (next === current) return
    setSaving(true)
    try {
      await organizationsAPI.updateOrganizationJurisdiction(
        organization.id,
        next,
      )
      await onSaved?.(next)
      addToast(t('admin.organizations.jurisdiction.saved'), 'success')
    } catch (error) {
      console.error('Failed to update the jurisdiction:', error)
      addToast(t('admin.organizations.jurisdiction.failed'), 'error')
    } finally {
      setSaving(false)
    }
  }

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
          className="mx-auto w-full max-w-md rounded-2xl bg-white shadow-xl dark:bg-zinc-800"
          data-testid="org-jurisdiction"
        >
          <div className="flex items-center justify-between border-b border-zinc-200 px-6 py-4 dark:border-zinc-700">
            <Dialog.Title className="text-lg font-semibold text-zinc-900 dark:text-white">
              {t('admin.organizations.jurisdiction.label')}
            </Dialog.Title>
            <button
              onClick={() => onOpenChange(false)}
              className="rounded-md p-2 text-zinc-400 transition-colors hover:text-zinc-500 dark:text-zinc-500 dark:hover:text-zinc-400"
              aria-label={t('common.close')}
            >
              <XMarkIcon className="h-5 w-5" />
            </button>
          </div>

          <div className="space-y-2 px-6 py-4">
            <Select
              value={current}
              disabled={saving}
              onValueChange={(v) => void save(v as Jurisdiction)}
              displayValue={t(
                `admin.organizations.jurisdiction.options.${current}`,
              )}
            >
              <SelectTrigger
                aria-label={t('admin.organizations.jurisdiction.label')}
                data-testid="org-jurisdiction-select"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {JURISDICTIONS.map((j) => (
                  <SelectItem key={j} value={j}>
                    {t(`admin.organizations.jurisdiction.options.${j}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              {t('admin.organizations.jurisdiction.help')}
            </p>
          </div>

          <div className="flex items-center justify-end border-t border-zinc-200 px-6 py-4 dark:border-zinc-700">
            <button
              onClick={() => onOpenChange(false)}
              className="h-8 rounded-full bg-zinc-900 px-4 text-sm font-medium text-white transition-colors hover:bg-zinc-700 dark:bg-emerald-500 dark:hover:bg-emerald-400"
            >
              {t('common.done')}
            </button>
          </div>
        </Dialog.Panel>
      </div>
    </Dialog>
  )
}
