'use client'

/**
 * "Billed to": picks which organization's API keys pay for generation and
 * evaluation runs on a project. Renders only when the caller may bill more
 * than one organization there; the pick is shared page-wide and remembered
 * per project (`useBillingOrganization`).
 */

import { useI18n } from '@/contexts/I18nContext'
import { useBillingOrganization } from '@/hooks/useBillingOrganization'

export function BillingOrgSelect({ projectId }: { projectId?: string | null }) {
  const { t } = useI18n()
  const {
    options,
    defaultOrganizationId,
    billingOrganizationId,
    setBillingOrganizationId,
  } = useBillingOrganization(projectId)

  if (options.length < 2) return null

  const defaultOption = options.find((o) => o.id === defaultOrganizationId)
  const describe = (name: string, providers: string[]) =>
    providers.length > 0 ? `${name} (${providers.join(', ')})` : name

  return (
    <div>
      <label
        htmlFor="billing-org-select"
        className="mb-2 block text-sm font-medium text-gray-700 dark:text-zinc-300"
      >
        {t('billingChoice.label')}
      </label>
      <select
        id="billing-org-select"
        data-testid="billing-org-select"
        value={billingOrganizationId ?? ''}
        onChange={(e) => setBillingOrganizationId(e.target.value || null)}
        className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-100"
      >
        <option value="">
          {t('billingChoice.default', {
            name: defaultOption
              ? describe(defaultOption.name, defaultOption.providers)
              : t('billingChoice.personalKeys'),
          })}
        </option>
        {options.map((o) => (
          <option key={o.id} value={o.id}>
            {describe(o.name, o.providers)}
          </option>
        ))}
      </select>
      <p className="mt-1 text-xs text-gray-500 dark:text-zinc-400">
        {t('billingChoice.hint')}
      </p>
    </div>
  )
}
