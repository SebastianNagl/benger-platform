'use client'

import { Button } from '@/components/shared/Button'
import { Input } from '@/components/shared/Input'
import { useI18n } from '@/contexts/I18nContext'

import type { ProfileFormData, SetProfileForm, UserProfile } from './types'

interface ProfilePersonalSectionProps {
  profile: UserProfile | null
  profileForm: ProfileFormData
  setProfileForm: SetProfileForm
  /** Mail a new link to the pending address (shown while one is pending). */
  onResendEmailChange?: () => void
  /** Drop the pending address. */
  onCancelEmailChange?: () => void
  /** A resend or cancel request is running. */
  emailChangeBusy?: boolean
}

export function ProfilePersonalSection({
  profile,
  profileForm,
  setProfileForm,
  onResendEmailChange,
  onCancelEmailChange,
  emailChangeBusy = false,
}: ProfilePersonalSectionProps) {
  const { t } = useI18n()
  const pendingEmail = profile?.pending_email || null
  const pendingSent = Boolean(profile?.pending_email_sent_at)

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
            aria-describedby="email-change-hint"
            required
          />
          <p
            id="email-change-hint"
            className="mt-1 text-xs text-zinc-500 dark:text-zinc-400"
          >
            {t('profile.emailChangeHint')}
          </p>
          {pendingEmail && (
            <div
              className={`mt-3 rounded-md border p-3 text-sm ${
                pendingSent
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-100'
                  : 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-100'
              }`}
              role="status"
              data-testid="profile-email-change-pending"
            >
              <p>
                {pendingSent
                  ? t('profile.emailChangeSent', {
                      email: pendingEmail,
                      current: profile?.email ?? '',
                    })
                  : t('profile.emailChangeNotSent', { email: pendingEmail })}
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={onResendEmailChange}
                  disabled={emailChangeBusy || !onResendEmailChange}
                  data-testid="profile-email-change-resend"
                >
                  {t('profile.emailChangeResend')}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={onCancelEmailChange}
                  disabled={emailChangeBusy || !onCancelEmailChange}
                  data-testid="profile-email-change-cancel"
                >
                  {t('profile.emailChangeCancel')}
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default ProfilePersonalSection
