'use client'

import { useI18n } from '@/contexts/I18nContext'

import { NewsCard, useNewsItems } from './NewsCard'

export function NewsSection() {
  const { t } = useI18n()

  const newsItems = useNewsItems()

  return (
    <section
      id="news"
      className="flex min-h-screen items-center bg-zinc-50 py-16 sm:py-24 dark:bg-zinc-800/50"
    >
      <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="text-center">
          <h2 className="text-3xl font-bold tracking-tight text-zinc-900 sm:text-4xl dark:text-white">
            {t('landing.news.title')}
          </h2>
          <p className="mx-auto mt-4 max-w-2xl text-lg text-zinc-600 dark:text-zinc-400">
            {t('landing.news.subtitle')}
          </p>
        </div>

        <div className="mt-12 grid gap-8 md:grid-cols-2 lg:grid-cols-3">
          {newsItems.map((item, i) => (
            <NewsCard key={i} item={item} />
          ))}
        </div>
      </div>
    </section>
  )
}
