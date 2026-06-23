'use client'

import { Button } from '@/components/shared/Button'
import { useI18n } from '@/contexts/I18nContext'
import type { MandatoryProfileStatus } from '@/lib/api/types'

interface ProfileMandatoryBannersProps {
  mandatoryStatus: MandatoryProfileStatus | null
  confirmingProfile: boolean
  onConfirm: () => void
}

export function ProfileMandatoryBanners({
  mandatoryStatus,
  confirmingProfile,
  onConfirm,
}: ProfileMandatoryBannersProps) {
  return (
    <>
      {/* Mandatory profile confirmation banner (Issue #1206) */}
      {mandatoryStatus?.confirmation_due && (
        <ConfirmationDueBanner
          mandatoryStatus={mandatoryStatus}
          confirmingProfile={confirmingProfile}
          onConfirm={onConfirm}
        />
      )}

      {/* Mandatory profile incomplete banner (Issue #1206) */}
      {mandatoryStatus && !mandatoryStatus.mandatory_profile_completed && !mandatoryStatus.confirmation_due && (
        <IncompleteBanner mandatoryStatus={mandatoryStatus} />
      )}
    </>
  )
}

function ConfirmationDueBanner({
  mandatoryStatus,
  confirmingProfile,
  onConfirm,
}: {
  mandatoryStatus: MandatoryProfileStatus
  confirmingProfile: boolean
  onConfirm: () => void
}) {
  const { t } = useI18n()

  return (
    <div className="mb-6 rounded-lg border border-amber-300 bg-amber-50 p-4 dark:border-amber-600 dark:bg-amber-900/20">
      <h3 className="font-medium text-amber-800 dark:text-amber-300">
        {t('profile.confirmationDue')}
      </h3>
      <p className="mt-1 text-sm text-amber-700 dark:text-amber-400">
        {t('profile.confirmationDueDescription')}
      </p>
      {mandatoryStatus.missing_fields.length > 0 && (
        <p className="mt-2 text-sm text-amber-700 dark:text-amber-400">
          {t('profile.missingFields')}:{' '}
          {mandatoryStatus.missing_fields.join(', ')}
        </p>
      )}
      <Button
        variant="filled"
        className="mt-3"
        disabled={
          confirmingProfile || mandatoryStatus.missing_fields.length > 0
        }
        onClick={onConfirm}
      >
        {confirmingProfile
          ? t('profile.confirming')
          : t('profile.confirmProfile')}
      </Button>
    </div>
  )
}

function IncompleteBanner({
  mandatoryStatus,
}: {
  mandatoryStatus: MandatoryProfileStatus
}) {
  const { t } = useI18n()

  return (
    <div className="mb-6 rounded-lg border border-red-300 bg-red-50 p-4 dark:border-red-600 dark:bg-red-900/20">
      <h3 className="font-medium text-red-800 dark:text-red-300">
        {t('profile.mandatoryIncomplete')}
      </h3>
      <p className="mt-1 text-sm text-red-700 dark:text-red-400">
        {t('profile.mandatoryIncompleteDescription')}
      </p>
      {mandatoryStatus.missing_fields.length > 0 && (
        <p className="mt-2 text-sm text-red-700 dark:text-red-400">
          {t('profile.missingFields')}:{' '}
          {mandatoryStatus.missing_fields.join(', ')}
        </p>
      )}
    </div>
  )
}

export default ProfileMandatoryBanners
