'use client'

import { Badge } from '@/components/ui/badge'
import { useI18n } from '@/contexts/I18nContext'
import type { InvitationDetails } from '@/lib/api/invitations'

/**
 * The delivery state of an invitation mail, as one badge.
 *
 * Admins used to see "invite sent" the moment the Celery task was queued,
 * with no way to tell that apart from a mail the worker never sent. The
 * server now records the outcome per invitation and derives `email_status`;
 * this renders it, and puts the timestamps and the provider error into the
 * tooltip so a failure is diagnosable without digging through worker logs.
 *
 * Shared by the org-admin members page and the superadmin organizations tab
 * so the two surfaces cannot drift on what a state means.
 */
export function InvitationDeliveryBadge({
  invitation,
}: {
  invitation: Pick<
    InvitationDetails,
    | 'email_status'
    | 'email_sent_at'
    | 'email_last_attempt_at'
    | 'email_attempts'
    | 'email_last_error'
  >
}) {
  const { t } = useI18n()
  const status = invitation.email_status || 'unknown'

  const variant =
    status === 'sent'
      ? 'default'
      : status === 'failed'
        ? 'destructive'
        : 'secondary'

  const label = t(`admin.invitationDelivery.status.${status}`)

  // Tooltip: the stamp that explains the badge, plus the error when there is
  // one. Kept in the title attribute so neither list layout has to grow a
  // popover.
  const details: string[] = [t(`admin.invitationDelivery.hint.${status}`)]
  if (invitation.email_sent_at) {
    details.push(
      `${t('admin.invitationDelivery.sentAt')}: ${new Date(
        invitation.email_sent_at,
      ).toLocaleString()}`,
    )
  } else if (invitation.email_last_attempt_at) {
    details.push(
      `${t('admin.invitationDelivery.lastAttemptAt')}: ${new Date(
        invitation.email_last_attempt_at,
      ).toLocaleString()}`,
    )
  }
  if (invitation.email_attempts) {
    details.push(
      `${t('admin.invitationDelivery.attempts')}: ${invitation.email_attempts}`,
    )
  }
  if (invitation.email_last_error) {
    details.push(
      `${t('admin.invitationDelivery.lastError')}: ${invitation.email_last_error}`,
    )
  }

  return (
    <Badge
      variant={variant}
      title={details.join('\n')}
      data-testid={`invitation-delivery-${status}`}
    >
      {label}
    </Badge>
  )
}
