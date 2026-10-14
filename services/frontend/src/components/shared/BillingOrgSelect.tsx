'use client'

/**
 * "Billed to": picks which organization's API keys pay for generation and
 * evaluation runs on a project. Renders only when the caller may bill more
 * than one organization there; the pick is shared page-wide and remembered
 * per project (`useBillingOrganization`).
 */

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shared/Select'
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
  const defaultLabel = t('billingChoice.default', {
    name: defaultOption
      ? describe(defaultOption.name, defaultOption.providers)
      : t('billingChoice.personalKeys'),
  })
  const picked = options.find((o) => o.id === billingOrganizationId)
  const value = picked ? picked.id : ''

  return (
    <div>
      <label
        htmlFor="billing-org-select"
        className="mb-2 block text-sm font-medium text-zinc-900 dark:text-white"
      >
        {t('billingChoice.label')}
      </label>
      {/* The default entry has the empty value, which the shared Select
          cannot look up on its own, so the trigger text is passed in. */}
      <Select
        value={value}
        onValueChange={(next) => setBillingOrganizationId(next || null)}
        displayValue={
          picked ? describe(picked.name, picked.providers) : defaultLabel
        }
      >
        <SelectTrigger id="billing-org-select" data-testid="billing-org-select">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="">{defaultLabel}</SelectItem>
          {options.map((o) => (
            <SelectItem key={o.id} value={o.id}>
              {describe(o.name, o.providers)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
        {t('billingChoice.hint')}
      </p>
    </div>
  )
}
