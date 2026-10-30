'use client'

/**
 * Personal access keys on the profile page: keys that act as the user on
 * the whole API (never more than the user may see). Same list, create
 * form, show-once panel, test, renewal and revocation as the organization
 * dialog, without role, group and project allowlist.
 */

import { AccessKeyManager } from '@/components/accessKeys/AccessKeyManager'
import { useOptionalAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'

export function ProfileAccessKeysSection() {
  const { t } = useI18n()
  // Only a superadmin's personal keys may carry admin:platform.
  const isSuperadmin = useOptionalAuth()?.user?.is_superadmin === true
  return (
    <section
      className="mt-8 border-t border-zinc-200 pt-8 dark:border-zinc-700"
      data-testid="profile-access-keys"
    >
      <h2 className="mb-1 text-xl font-semibold text-zinc-900 dark:text-white">
        {t('profile.accessKeys')}
      </h2>
      <p className="mb-4 text-sm text-zinc-600 dark:text-zinc-400">
        {t('accessKeys.personalDescription')}
      </p>
      <AccessKeyManager mode="personal" isSuperadmin={isSuperadmin} />
    </section>
  )
}

export default ProfileAccessKeysSection
