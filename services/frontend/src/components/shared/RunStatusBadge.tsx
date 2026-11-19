'use client'

import { Badge } from '@/components/shared/Badge'
import { useI18n } from '@/contexts/I18nContext'

/** Statuses with a translated label (`evaluations.detail.statusLabels`). */
const LABELLED = new Set([
  'completed',
  'failed',
  'running',
  'pending',
  'queued',
  'cancelled',
  'paused',
])

function toneOf(status: string) {
  if (status === 'completed') return 'success' as const
  if (status === 'failed') return 'destructive' as const
  if (status === 'running' || status === 'pending' || status === 'queued') {
    return 'warning' as const
  }
  return 'secondary' as const
}

/**
 * Status of a generation, evaluation or analysis run as a coloured badge
 * with a translated label (unknown statuses show as given, in grey).
 */
export function RunStatusBadge({
  status,
  className,
}: {
  status?: string | null
  className?: string
}) {
  const { t } = useI18n()
  if (!status) return <span className="text-zinc-400">—</span>
  const label = LABELLED.has(status)
    ? t(`evaluations.detail.statusLabels.${status}`)
    : status
  return (
    <Badge
      variant={toneOf(status)}
      className={className}
      data-testid="run-status-badge"
      data-status={status}
    >
      {label}
    </Badge>
  )
}
