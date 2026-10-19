'use client'

import { BeakerIcon } from '@heroicons/react/24/outline'
import Link from 'next/link'

import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'

interface Props {
  /** Called when the link is followed so the host can close its dropdown. */
  onNavigate?: () => void
}

/**
 * "Feature Flags" row of the account dropdown (AuthButton), superadmins
 * only. Links to /admin/feature-flags.
 */
export function FeatureFlagsMenuEntry({ onNavigate }: Props) {
  const { user } = useAuth()
  const { t } = useI18n()
  if (!user?.is_superadmin) return null
  return (
    <Link
      href="/admin/feature-flags"
      onClick={onNavigate}
      data-testid="auth-menu-feature-flags"
      className="flex items-center px-4 py-2 text-sm text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-700"
    >
      <BeakerIcon className="mr-3 h-4 w-4" />
      {t('admin.featureFlagsConsole.menu')}
    </Link>
  )
}

export default FeatureFlagsMenuEntry
