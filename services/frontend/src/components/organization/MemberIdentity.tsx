'use client'

/**
 * Pieces of a member row for LMS (LTI) accounts.
 *
 * The API shows an LMS account by its pseudonym, with a null email, to
 * viewers who may not see its real name (`is_pseudonymized`). These helpers
 * render the "LMS" badge and the email line so such rows never print "null"
 * and explain why the address is missing.
 */

import { useI18n } from '@/contexts/I18nContext'
import type { MemberPrivacyFlags } from '@/lib/api/types'

const PSEUDONYM_TITLE = 'admin.organizations.memberPrivacy.pseudonymTitle'

interface LmsMemberBadgeProps extends MemberPrivacyFlags {
  'data-testid'?: string
}

/** "LMS" badge next to the name of an LMS account; nothing otherwise. */
export function LmsMemberBadge({
  is_lms_account,
  is_pseudonymized,
  'data-testid': testId,
}: LmsMemberBadgeProps) {
  const { t } = useI18n()
  if (!is_lms_account) return null
  return (
    <span
      data-testid={testId}
      title={
        is_pseudonymized
          ? t(PSEUDONYM_TITLE)
          : t('admin.organizations.memberPrivacy.lmsBadgeTitle')
      }
      className="ml-2 inline-flex items-center rounded-full bg-sky-100 px-2 py-0.5 text-xs font-medium text-sky-700 dark:bg-sky-900/30 dark:text-sky-300"
    >
      {t('admin.organizations.memberPrivacy.lmsBadge')}
    </span>
  )
}

interface MemberEmailProps {
  email?: string | null
  hidden?: boolean
}

/** The member's email, or a muted note when the viewer may not see it. */
export function MemberEmail({ email, hidden }: MemberEmailProps) {
  const { t } = useI18n()
  if (email) return <>{email}</>
  if (!hidden) return null
  return (
    <span className="italic" title={t(PSEUDONYM_TITLE)}>
      {t('admin.organizations.memberPrivacy.emailHidden')}
    </span>
  )
}

/** "Name (email)" for pickers; just the name when the email is withheld. */
export function memberOptionLabel(
  name: string | null | undefined,
  email: string | null | undefined,
): string {
  const label = name ?? ''
  if (!email) return label
  return label ? `${label} (${email})` : email
}
