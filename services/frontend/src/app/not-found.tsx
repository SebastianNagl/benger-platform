'use client'

import { HeroPattern } from '@/components/shared'
import { Button } from '@/components/shared/Button'
import { useI18n } from '@/contexts/I18nContext'

export default function NotFound() {
  const { t } = useI18n()

  return (
    <>
      <HeroPattern />
      <div className="mx-auto flex h-full max-w-xl flex-col items-center justify-center py-16 text-center">
        <p className="text-sm font-semibold text-zinc-900 dark:text-white">
          {t('errors.404.code')}
        </p>
        <h1 className="mt-2 text-2xl font-bold text-zinc-900 dark:text-white">
          {t('errors.404.title')}
        </h1>
        <p className="mt-2 text-base text-zinc-600 dark:text-zinc-400">
          {t('errors.404.description')}
        </p>
        <Button href="/" arrow="right" className="mt-8">
          {t('errors.404.backButton')}
        </Button>
      </div>
    </>
  )
}
