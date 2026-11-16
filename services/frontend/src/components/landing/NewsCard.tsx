'use client'

import { Badge } from '@/components/shared/Badge'
import { Card } from '@/components/shared/Card'
import { useI18n } from '@/contexts/I18nContext'

/** One entry of `landing.news.items` in the locale catalogs. */
export interface NewsItem {
  title: string
  description: string
  date: string
  type: 'news' | 'publication'
  url?: string
}

/**
 * The news and publications list of the catalog (`landing.news.items`), the
 * one source for the landing page and the /publications page.
 */
export function useNewsItems(): NewsItem[] {
  const { t } = useI18n()
  const items = t('landing.news.items') as unknown as NewsItem[]
  return Array.isArray(items) ? items : []
}

/**
 * A news or publication card as the landing page shows it; the whole card
 * links to the entry's article when it has one.
 */
export function NewsCard({ item }: { item: NewsItem }) {
  const { t } = useI18n()

  const content = (
    <Card
      className={`flex h-full flex-col p-6 ${item.url ? 'transition-shadow hover:shadow-lg' : ''}`}
    >
      <div className="mb-3">
        <Badge variant={item.type === 'publication' ? 'default' : 'secondary'}>
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
        {item.url && (
          <span className="text-sm font-medium text-emerald-600 dark:text-emerald-400">
            {t('landing.news.readMore')} &rarr;
          </span>
        )}
      </div>
    </Card>
  )

  if (!item.url) return content

  return (
    <a
      href={item.url}
      target="_blank"
      rel="noopener noreferrer"
      className="block h-full"
    >
      {content}
    </a>
  )
}
