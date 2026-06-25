'use client'

import { useI18n } from '@/contexts/I18nContext'

/**
 * Community-edition fallback for the student host routes (Issue #35).
 *
 * Mirrors the tone of the existing review-page fallback: the student
 * experience ships in the proprietary extended package, so the open-core
 * platform renders a neutral "not available" notice when no slot is
 * registered. Never crashes the route.
 */
export function StudentSlotFallback() {
  const { t } = useI18n()
  return (
    <div className="flex min-h-[400px] items-center justify-center">
      <p className="text-zinc-500 dark:text-zinc-400">
        {t('student.community.unavailable')}
      </p>
    </div>
  )
}
