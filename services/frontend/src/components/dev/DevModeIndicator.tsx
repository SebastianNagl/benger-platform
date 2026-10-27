'use client'

import { useAuth } from '@/contexts/AuthContext'
import { useHydration } from '@/contexts/HydrationContext'
import { useI18n } from '@/contexts/I18nContext'
import { XMarkIcon } from '@heroicons/react/24/outline'
import { useMemo, useState } from 'react'

export function DevModeIndicator() {
  const { user } = useAuth()
  const { t } = useI18n()
  const isHydrated = useHydration()
  const [showDetails, setShowDetails] = useState(false)

  // Derive visibility from environment and user state
  const isVisible = useMemo(() => {
    if (!isHydrated) return false
    const isDevAutoAuth =
      process.env.NODE_ENV === 'development' &&
      process.env.NEXT_PUBLIC_DISABLE_AUTO_LOGIN !== 'true'
    const isLocalhost =
      typeof window !== 'undefined' &&
      (window.location.hostname === 'localhost' ||
        window.location.hostname === '127.0.0.1' ||
        window.location.hostname === 'benger.localhost')
    return isDevAutoAuth && isLocalhost && !!user
  }, [isHydrated, user])

  if (!isVisible) {
    return null
  }

  return (
    <>
      {/* Small badge indicator */}
      <div className="fixed right-4 bottom-4 z-50">
        <button
          onClick={() => setShowDetails(!showDetails)}
          className="flex items-center gap-2 rounded-full border border-amber-300 bg-amber-100 px-3 py-1.5 text-xs font-medium text-amber-800 shadow-sm transition-colors duration-200 hover:bg-amber-200 dark:border-amber-700 dark:bg-amber-900/80 dark:text-amber-200 dark:hover:bg-amber-800"
          title={t('dev.modeIndicator.tooltip')}
        >
          <span className="h-2 w-2 animate-pulse rounded-full bg-amber-500 dark:bg-amber-400"></span>
          {t('dev.modeIndicator.badge')}
        </button>
      </div>

      {/* Details popup (only when clicked) */}
      {showDetails && (
        <div className="fixed right-4 bottom-16 z-50 transition-opacity duration-200">
          <div className="max-w-sm rounded-lg border border-zinc-200 bg-white p-4 shadow-lg dark:border-zinc-700 dark:bg-zinc-800">
            <div className="mb-2 flex items-start justify-between">
              <h3 className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                {t('dev.modeIndicator.title')}
              </h3>
              <button
                onClick={() => setShowDetails(false)}
                className="text-zinc-400 hover:text-zinc-500 dark:text-zinc-500 dark:hover:text-zinc-400"
                aria-label={t('common.close')}
              >
                <XMarkIcon className="h-4 w-4" />
              </button>
            </div>
            <div className="space-y-1 text-xs text-zinc-600 dark:text-zinc-400">
              <p>
                {t('dev.modeIndicator.authenticatedAs')}{' '}
                <strong className="text-zinc-800 dark:text-zinc-200">
                  {user?.username}
                </strong>
              </p>
              <p>
                {t('dev.modeIndicator.emailLabel')} {user?.email}
              </p>
              <p>
                {t('dev.modeIndicator.hostLabel')} {window.location.hostname}
              </p>
              <p>
                {t('dev.modeIndicator.superadminLabel')}{' '}
                {user?.is_superadmin ? t('common.yes') : t('common.no')}
              </p>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
