import Link from 'next/link'
import { Badge } from '@/components/shared/Badge'
import { formatDate, formatDateTime } from '@/lib/reports/format'
import type { TranslateFn } from './chartTheme'

interface ReportHeaderProps {
  title: string
  description?: string | null
  publishedAt?: string | null
  generatedAt?: string | null
  isDraft: boolean
  /** Shown only when the viewer may edit (superadmin); anonymous readers get nothing. */
  editHref?: string | null
  locale: string
  t: TranslateFn
}

export function ReportHeader({
  title,
  description,
  publishedAt,
  generatedAt,
  isDraft,
  editHref,
  locale,
  t,
}: ReportHeaderProps) {
  const published = formatDate(publishedAt, locale)
  const generated = formatDateTime(generatedAt, locale)
  return (
    <header className="mb-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
              {title}
            </h1>
            {isDraft && (
              <Badge variant="outline" data-testid="draft-badge">
                {t('reports.view.draft', 'Entwurf')}
              </Badge>
            )}
          </div>
          {description && (
            <p className="mt-3 max-w-3xl whitespace-pre-line text-base leading-7 text-zinc-600 dark:text-zinc-300">
              {description}
            </p>
          )}
        </div>
        {editHref && (
          <Link
            href={editHref}
            className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm font-medium text-zinc-700 transition hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800"
          >
            {t('reports.view.edit', 'Bearbeiten')}
          </Link>
        )}
      </div>
      <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-sm text-zinc-500 dark:text-zinc-400">
        {published && (
          <span>{t('reports.view.publishedOn', 'Veröffentlicht am {date}', { date: published })}</span>
        )}
        {generated && (
          <span data-testid="data-as-of">
            {t('reports.view.dataAsOf', 'Datenstand: {date}', { date: generated })}
          </span>
        )}
      </div>
    </header>
  )
}
