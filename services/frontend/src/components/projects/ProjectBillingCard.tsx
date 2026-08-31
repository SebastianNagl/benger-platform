'use client'

import { useEffect, useState } from 'react'

import { useI18n } from '@/contexts/I18nContext'
import { organizationsAPI } from '@/lib/api/organizations'
import { useSlot } from '@/lib/extensions/slots'

interface Props {
  // Loosely typed so the card works with the page's ProjectResponse shape
  // without importing it: only id + linked orgs are read.
  project: {
    id: string
    organizations?: { id: string; name: string }[]
  }
}

type BillingMessage =
  | { kind: 'orgPays'; orgName: string }
  | { kind: 'personalKey' }
  | { kind: 'dependsOnAccess' }

/**
 * "Abrechnung" sidebar card on the project detail page: says whose API key
 * pays for AI evaluations in this project. Community-edition-safe — it only
 * reads the generic org api-key settings endpoint; the extended edition adds
 * the authoritative per-user line via the `project-billing-extended` slot.
 *
 * Fail-closed: when the org settings request fails (e.g. a non-member 403),
 * the card quietly says the answer depends on the viewer's access.
 */
export function ProjectBillingCard({ project }: Props) {
  const { t } = useI18n()
  const Extra = useSlot('project-billing-extended')
  const [message, setMessage] = useState<BillingMessage | null>(null)

  const org = project?.organizations?.[0] ?? null
  const orgId = org?.id ?? null
  const orgName = org?.name ?? ''

  useEffect(() => {
    if (!orgId) {
      setMessage({ kind: 'personalKey' })
      return
    }
    let cancelled = false
    organizationsAPI
      .getOrgApiKeySettings(orgId)
      .then((settings) => {
        if (cancelled) return
        if (settings.require_private_keys === false) {
          setMessage({ kind: 'orgPays', orgName })
        } else {
          setMessage({ kind: 'personalKey' })
        }
      })
      .catch(() => {
        // Non-members can't read org settings — don't guess, don't toast.
        if (!cancelled) setMessage({ kind: 'dependsOnAccess' })
      })
    return () => {
      cancelled = true
    }
  }, [orgId, orgName])

  let line: string | null = null
  if (message?.kind === 'orgPays') {
    line = t('project.billing.orgPays', { org: message.orgName })
  } else if (message?.kind === 'personalKey') {
    line = t('project.billing.personalKey')
  } else if (message?.kind === 'dependsOnAccess') {
    line = t('project.billing.dependsOnAccess')
  }

  return (
    <div
      className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm ring-1 ring-zinc-900/5 dark:border-zinc-700 dark:bg-zinc-900 dark:ring-white/10"
      data-testid="project-billing-card"
    >
      <h3 className="mb-6 text-lg font-semibold text-zinc-900 dark:text-white">
        {t('project.billing.title')}
      </h3>
      {line && (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">{line}</p>
      )}
      {Extra && <Extra project={project} />}
    </div>
  )
}
