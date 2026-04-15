'use client'

import { Button } from '@/components/shared/Button'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useI18n } from '@/contexts/I18nContext'
import { useRouter } from 'next/navigation'

interface ComingSoonProps {
  title?: string
  description?: string
  showBackButton?: boolean
}

export function ComingSoon({
  title,
  description,
  showBackButton = true,
}: ComingSoonProps) {
  const router = useRouter()
  const { t } = useI18n()

  const displayTitle = title ?? t('common.comingSoon')
  const displayDescription = description ?? t('common.comingSoonMessage')

  return (
    <ResponsiveContainer size="xl" className="pb-10 pt-8">
      <div className="flex min-h-[60vh] flex-col items-center justify-center text-center">
        {/* Icon */}
        <div className="mb-8">
          <svg
            className="h-24 w-24 text-zinc-300 dark:text-zinc-600"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
        </div>

        {/* Title */}
        <h1 className="mb-4 text-3xl font-bold text-zinc-900 dark:text-zinc-100">
          {displayTitle}
        </h1>

        {/* Description */}
        <p className="mb-8 max-w-md text-lg text-zinc-600 dark:text-zinc-400">
          {displayDescription}
        </p>

        {/* Back button */}
        {showBackButton && (
          <Button
            onClick={() => router.back()}
            className="bg-emerald-600 text-white hover:bg-emerald-700"
          >
            {t('common.goBack')}
          </Button>
        )}
      </div>
    </ResponsiveContainer>
  )
}
