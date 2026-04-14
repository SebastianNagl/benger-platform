'use client'

import { useI18n } from '@/contexts/I18nContext'
import Link from 'next/link'

interface ModelProviderStatusProps {
  provider: string
  hasApiKey: boolean
  modelCount: number
  className?: string
}

export function ModelProviderStatus({
  provider,
  hasApiKey,
  modelCount,
  className = '',
}: ModelProviderStatusProps) {
  const { t } = useI18n()

  if (hasApiKey) {
    return (
      <div
        className={`rounded-md border border-emerald-200 bg-emerald-50 p-3 dark:border-emerald-800 dark:bg-emerald-950/50 ${className}`}
      >
        <div className="flex items-center space-x-2">
          <div className="h-2 w-2 rounded-full bg-emerald-500" />
          <span className="text-sm font-medium text-emerald-700 dark:text-emerald-400">
            {provider}
          </span>
          <span className="text-xs text-emerald-600 dark:text-emerald-500">
            {modelCount === 1
              ? t('tasks.modelProvider.modelAvailableSingular', { count: modelCount })
              : t('tasks.modelProvider.modelAvailablePlural', { count: modelCount })}
          </span>
        </div>
      </div>
    )
  }

  return (
    <div
      className={`rounded-md border border-amber-200 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-950/50 ${className}`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <svg
            className="h-4 w-4 text-amber-600 dark:text-amber-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"
            />
          </svg>
          <span className="text-sm text-amber-700 dark:text-amber-400">
            {t('tasks.modelProvider.configureKey', { provider })}
          </span>
        </div>
        <Link
          href="/profile"
          className="text-sm font-medium text-amber-600 transition-colors hover:text-amber-800 dark:text-amber-400 dark:hover:text-amber-300"
        >
          {t('tasks.modelProvider.configure')}
        </Link>
      </div>
    </div>
  )
}

export default ModelProviderStatus
