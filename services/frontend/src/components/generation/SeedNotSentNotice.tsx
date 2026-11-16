'use client'

import { useI18n } from '@/contexts/I18nContext'

/**
 * Notice for a generation run whose requested seed did not reach the model.
 *
 * The worker stores the seed that was actually sent in the run's parameters
 * (`seed`, null when none went out) and, when a requested seed was left out
 * because the model does not take one, `seed_not_sent: {requested, reason}`.
 * Without this notice the parameters only show `"seed": null`, and a reader
 * comparing runs could miss that the run was unseeded although its project
 * configuration names a seed.
 */

interface SeedNotSent {
  requested?: unknown
  reason?: unknown
}

export function seedNotSentOf(
  parameters: Record<string, unknown> | null | undefined,
): SeedNotSent | null {
  const value = parameters?.seed_not_sent
  return value && typeof value === 'object' ? (value as SeedNotSent) : null
}

export function SeedNotSentNotice({
  parameters,
  className = '',
}: {
  parameters: Record<string, unknown> | null | undefined
  className?: string
}) {
  const { t } = useI18n()
  const info = seedNotSentOf(parameters)
  if (!info) return null
  const key =
    info.reason === 'declared_unsupported'
      ? 'generation.seedNotSent.declaredUnsupported'
      : 'generation.seedNotSent.unsupportedByModel'
  return (
    <div
      role="status"
      data-testid="seed-not-sent-notice"
      className={`rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300 ${className}`}
    >
      {t(key, { seed: String(info.requested ?? '') })}
    </div>
  )
}
