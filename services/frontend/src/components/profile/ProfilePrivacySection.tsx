'use client'

import { ChevronDownIcon } from '@heroicons/react/24/outline'

import { useI18n } from '@/contexts/I18nContext'

import type { ProfileFormData, SetProfileForm, UserProfile } from './types'

interface ProfilePrivacySectionProps {
  profile: UserProfile | null
  profileForm: ProfileFormData
  setProfileForm: SetProfileForm
  expanded: boolean
  onToggle: (next: boolean) => void
}

export function ProfilePrivacySection({
  profile,
  profileForm,
  setProfileForm,
  expanded,
  onToggle,
}: ProfilePrivacySectionProps) {
  const { t } = useI18n()

  return (
    <div className="border-t border-zinc-200 pt-8 dark:border-zinc-700">
      <button
        type="button"
        onClick={() => onToggle(!expanded)}
        className="group flex w-full items-center justify-between text-left"
      >
        <h2 className="text-xl font-semibold text-zinc-900 dark:text-white">
          {t('profile.privacySettings')}
        </h2>
        <div className="inline-flex items-center gap-1.5">
          <span className="text-sm text-zinc-500 dark:text-zinc-400">
            {expanded
              ? t('profile.hidePrivacySettings')
              : t('profile.showPrivacySettings')}
          </span>
          <ChevronDownIcon
            className={`h-4 w-4 opacity-70 transition-transform ${
              expanded ? 'rotate-180' : ''
            }`}
          />
        </div>
      </button>

      {expanded && (
      <div className="mt-6 space-y-4 rounded-lg border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-700 dark:bg-zinc-800/50">
        <div>
          <label
            htmlFor="pseudonym"
            className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
          >
            {t('profile.yourPseudonym')}
          </label>
          <input
            type="text"
            id="pseudonym"
            name="pseudonym"
            value={profile?.pseudonym || ''}
            disabled
            className="w-full rounded-full bg-zinc-100 px-4 py-2 text-sm text-zinc-500 ring-1 ring-zinc-900/5 dark:bg-white/5 dark:text-zinc-400 dark:ring-inset dark:ring-white/5"
          />
          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
            {t('profile.pseudonymNote')}
          </p>
        </div>

        <div className="flex items-start">
          <div className="flex h-5 items-center">
            <input
              type="checkbox"
              id="use_pseudonym"
              name="use_pseudonym"
              checked={profileForm.use_pseudonym ?? true}
              onChange={(e) =>
                setProfileForm({
                  ...profileForm,
                  use_pseudonym: e.target.checked,
                })
              }
              className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600 dark:bg-zinc-700 dark:ring-offset-zinc-900"
            />
          </div>
          <div className="ml-3">
            <label
              htmlFor="use_pseudonym"
              className="text-sm font-medium text-zinc-700 dark:text-zinc-300"
            >
              {t('profile.usePseudonym')}
            </label>
            <p className="text-xs text-zinc-500 dark:text-zinc-400">
              {t('profile.usePseudonymDescription')}
            </p>
          </div>
        </div>
      </div>
      )}
    </div>
  )
}

export default ProfilePrivacySection
