'use client'

import { Badge } from '@/components/shared/Badge'
import { Card } from '@/components/shared/Card'
import { useI18n } from '@/contexts/I18nContext'

interface NewsItem {
  title: string
  description: string
  date: string
  type: 'news' | 'publication'
  url?: string
}

export function NewsSection() {
  const { t } = useI18n()

  const items = t('landing.news.items') as unknown as NewsItem[]
  const newsItems = Array.isArray(items) ? items : []

  return (
    <section
      id="news"
      className="flex min-h-screen items-center bg-zinc-50 py-16 dark:bg-zinc-800/50 sm:py-24"
    >
      <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="text-center">
          <h2 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white sm:text-4xl">
            {t('landing.news.title')}
          </h2>
          <p className="mx-auto mt-4 max-w-2xl text-lg text-zinc-600 dark:text-zinc-400">
            {t('landing.news.subtitle')}
          </p>
        </div>

        <div className="mt-12 grid gap-8 md:grid-cols-2 lg:grid-cols-3">
          {newsItems.map((item, i) => {
            const content = (
              <Card
                key={i}
                className={`flex flex-col p-6${item.url ? ' transition-shadow hover:shadow-lg' : ''}`}
              >
                <div className="mb-3">
                  <Badge
                    variant={
                      item.type === 'publication' ? 'default' : 'secondary'
                    }
                  >
                    {item.type === 'publication'
                      ? t('landing.news.publicationLabel')
                      : t('landing.news.newsLabel')}
                  </Badge>
                </div>
                <h3 className="text-lg font-semibold text-zinc-900 dark:text-white">
                  {item.title}
                </h3>
                <p className="mt-2 flex-1 text-sm text-zinc-600 dark:text-zinc-400">
                  {item.description}
                </p>
                <div className="mt-4 flex items-center justify-between">
                  <span className="text-xs text-zinc-500 dark:text-zinc-500">
                    {item.date}
                  </span>
                  <span className="text-sm font-medium text-emerald-600 dark:text-emerald-400">
                    {t('landing.news.readMore')} &rarr;
                  </span>
                </div>
              </Card>
            )

            if (item.url) {
              return (
                <a
                  key={i}
                  href={item.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block"
                >
                  {content}
                </a>
              )
            }

            return content
          })}
        </div>
      </div>
    </section>
  )
}
