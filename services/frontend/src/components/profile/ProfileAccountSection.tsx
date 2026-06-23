'use client'

import { useI18n } from '@/contexts/I18nContext'

import type { UserProfile } from './types'

interface ProfileAccountSectionProps {
  profile: UserProfile | null
}

export function ProfileAccountSection({ profile }: ProfileAccountSectionProps) {
  const { t } = useI18n()

  return (
    <div className="border-t border-zinc-200 pt-8 dark:border-zinc-700">
      <h2 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
        {t('profile.accountInfo')}
      </h2>
      <div className="space-y-3 text-sm text-zinc-600 dark:text-zinc-400">
        {profile?.created_at && (
          <div>
            <span className="font-medium">
              {t('profile.memberSince')}
            </span>{' '}
            {new Date(profile.created_at).toLocaleDateString()}
          </div>
        )}
        {profile?.updated_at && (
          <div>
            <span className="font-medium">
              {t('profile.lastUpdated')}
            </span>{' '}
            {new Date(profile.updated_at).toLocaleDateString()}
          </div>
        )}
        {profile?.profile_confirmed_at && (
          <div>
            <span className="font-medium">
              {t('profile.lastConfirmed')}
            </span>{' '}
            {new Date(
              profile.profile_confirmed_at
            ).toLocaleDateString()}
          </div>
        )}
      </div>
    </div>
  )
}

export default ProfileAccountSection
