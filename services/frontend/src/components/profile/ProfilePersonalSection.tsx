'use client'

import { useI18n } from '@/contexts/I18nContext'

import type { ProfileFormData, SetProfileForm, UserProfile } from './types'

interface ProfilePersonalSectionProps {
  profile: UserProfile | null
  profileForm: ProfileFormData
  setProfileForm: SetProfileForm
}

export function ProfilePersonalSection({
  profile,
  profileForm,
  setProfileForm,
}: ProfilePersonalSectionProps) {
  const { t } = useI18n()

  return (
    <div>
      <h2 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
        {t('profile.personalInfo')}
      </h2>
      <div className="space-y-4">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div>
            <label
              htmlFor="username"
              className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
            >
              {t('profile.username')}
            </label>
            <input
              type="text"
              id="username"
              name="username"
              value={profile?.username || ''}
              disabled
              autoComplete="username"
              title={t('profile.usernameNote')}
              className="w-full cursor-not-allowed rounded-full bg-zinc-100 px-4 py-2 text-sm text-zinc-500 ring-1 ring-zinc-900/5 dark:bg-white/5 dark:text-zinc-400 dark:ring-inset dark:ring-white/5"
            />
          </div>
          <div>
            <label
              htmlFor="role"
              className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
            >
              {t('profile.role')}
            </label>
            <input
              type="text"
              id="role"
              name="role"
              value={
                profile?.is_superadmin
                  ? t('profile.roles.superadmin')
                  : t('profile.roles.user')
              }
              disabled
              autoComplete="organization-title"
              title={t('profile.roleNote')}
              className="w-full cursor-not-allowed rounded-full bg-zinc-100 px-4 py-2 text-sm text-zinc-500 ring-1 ring-zinc-900/5 dark:bg-white/5 dark:text-zinc-400 dark:ring-inset dark:ring-white/5"
            />
          </div>
        </div>

        <div>
          <label
            htmlFor="name"
            className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
          >
            {t('profile.fullName')}
          </label>
          <input
            type="text"
            id="name"
            name="name"
            value={profileForm.name}
            onChange={(e) =>
              setProfileForm({
                ...profileForm,
                name: e.target.value,
              })
            }
            autoComplete="name"
            className="w-full rounded-full bg-white px-4 py-2 text-sm text-zinc-900 ring-1 ring-zinc-900/10 transition placeholder:text-zinc-500 hover:ring-zinc-900/20 focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:bg-white/5 dark:text-white dark:ring-inset dark:ring-white/10 dark:placeholder:text-zinc-400 dark:hover:ring-white/20 dark:focus:ring-emerald-400"
            required
          />
        </div>

        <div>
          <label
            htmlFor="email"
            className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
          >
            {t('profile.emailAddress')}
          </label>
          <input
            type="email"
            id="email"
            name="email"
            value={profileForm.email}
            onChange={(e) =>
              setProfileForm({
                ...profileForm,
                email: e.target.value,
              })
            }
            autoComplete="email"
            className="w-full rounded-full bg-white px-4 py-2 text-sm text-zinc-900 ring-1 ring-zinc-900/10 transition placeholder:text-zinc-500 hover:ring-zinc-900/20 focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:bg-white/5 dark:text-white dark:ring-inset dark:ring-white/10 dark:placeholder:text-zinc-400 dark:hover:ring-white/20 dark:focus:ring-emerald-400"
            required
          />
        </div>
      </div>
    </div>
  )
}

export default ProfilePersonalSection
