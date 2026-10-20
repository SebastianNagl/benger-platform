'use client'

import { useState } from 'react'

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
 * types the project wizard offers. Org admins change it inline; everyone
 * else sees the value.
 */
export function OrgJurisdictionSetting({
  organization,
  canManage,
  onSaved,
}: {
  organization: { id: string; jurisdiction?: unknown }
  canManage: boolean
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
    <div
      className="mt-3 flex flex-wrap items-center gap-2 text-sm"
      data-testid="org-jurisdiction"
    >
      <label
        htmlFor={`org-jurisdiction-${organization.id}`}
        className="text-zinc-500 dark:text-zinc-400"
      >
        {t('admin.organizations.jurisdiction.label')}
      </label>
      {canManage ? (
        <select
          id={`org-jurisdiction-${organization.id}`}
          value={current}
          disabled={saving}
          onChange={(e) => void save(e.target.value as Jurisdiction)}
          className="rounded-md border border-zinc-300 bg-white px-2 py-1 text-zinc-900 dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-100"
          data-testid="org-jurisdiction-select"
        >
          {JURISDICTIONS.map((j) => (
            <option key={j} value={j}>
              {t(`admin.organizations.jurisdiction.options.${j}`)}
            </option>
          ))}
        </select>
      ) : (
        <span className="text-zinc-900 dark:text-zinc-100">
          {t(`admin.organizations.jurisdiction.options.${current}`)}
        </span>
      )}
      <span className="w-full text-xs text-zinc-500 dark:text-zinc-400">
        {t('admin.organizations.jurisdiction.help')}
      </span>
    </div>
  )
}
