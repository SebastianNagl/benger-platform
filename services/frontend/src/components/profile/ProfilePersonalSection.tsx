'use client'

import { Input } from '@/components/shared/Input'
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
            <Input
              type="text"
              id="username"
              name="username"
              value={profile?.username || ''}
              disabled
              autoComplete="username"
              title={t('profile.usernameNote')}
            />
          </div>
          <div>
            <label
              htmlFor="role"
              className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
            >
              {t('profile.role')}
            </label>
            <Input
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
          <Input
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
          <Input
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
            required
          />
        </div>
      </div>
    </div>
  )
}

export default ProfilePersonalSection
