'use client'

import { useSyncExternalStore } from 'react'

const subscribeNoop = () => () => {}

import { VertretbarMarkIcon } from '@/components/brand/VertretbarMark'
import { Button } from '@/components/shared/Button'
import { useI18n } from '@/contexts/I18nContext'
import { isStudentLockedHost } from '@/lib/utils/subdomain'
import { logger } from '@/lib/utils/logger'

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  // Inline German defaults on every t(): when the crash originates inside the
  // provider tree this segment renders WITHOUT I18nProvider, and the bare-key
  // fallback would otherwise show raw `errors.global.*` keys.
  const { t } = useI18n()
  // Host resolved on the client only: the server snapshot stays neutral so
  // the first paint never hydration-mismatches (no state, no effect needed).
  const isVtr = useSyncExternalStore(subscribeNoop, isStudentLockedHost, () => false)
  // Safely log error to prevent any undefined access
  if (error) {
    try {
      console.error('Global error:', error)
    } catch (e) {
      // Fallback if console.error fails
      logger.debug('Error occurred but could not be logged properly')
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-50 p-4 dark:bg-zinc-900">
      <div className="w-full max-w-2xl rounded-lg border border-zinc-200 bg-white p-6 shadow-lg dark:border-zinc-700 dark:bg-zinc-800">
        {isVtr && (
          <div className="mb-4 flex items-center gap-2" data-testid="error-brand-vertretbar">
            <VertretbarMarkIcon className="h-6 w-6 text-emerald-500" />
            <span className="text-lg font-semibold text-zinc-900 dark:text-white">
              Vertretbar
            </span>
          </div>
        )}
        <div className="mb-4 flex items-center">
          <div className="mr-4 flex h-12 w-12 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/20">
            <svg
              className="h-6 w-6 text-red-600 dark:text-red-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.962-.833-2.732 0L3.732 16.5c-.77.833-.208 2.5 1.732 2.5z"
              />
            </svg>
          </div>
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
            {t('errors.global.title', 'Etwas ist schiefgelaufen')}
          </h2>
        </div>

        <p className="mb-4 text-zinc-600 dark:text-zinc-300">
          {t(
            'errors.global.description',
            'Beim Laden dieses Inhalts ist ein unerwarteter Fehler aufgetreten.'
          )}
        </p>

        <div className="flex gap-3">
          <Button variant="primary" onClick={reset}>
            {t('errors.global.tryAgain', 'Erneut versuchen')}
          </Button>
          <Button variant="secondary" onClick={() => window.location.reload()}>
            {t('errors.global.reloadPage', 'Seite neu laden')}
          </Button>
        </div>

        {/* Technical details in development */}
        {process.env.NODE_ENV === 'development' && (
          <details className="mt-4">
            <summary className="cursor-pointer text-sm text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300">
              {t('errors.global.technicalDetails', 'Technische Details')}
            </summary>
            <pre className="mt-2 max-h-96 overflow-auto rounded bg-zinc-100 p-3 text-xs text-zinc-600 dark:bg-zinc-900 dark:text-zinc-400">
              {error?.message || 'Unknown error'}
              {error?.stack && (
                <>
                  {'\n\nStack trace:\n'}
                  {error.stack}
                </>
              )}
            </pre>
          </details>
        )}
      </div>
    </div>
  )
}
