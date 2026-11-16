import { useI18n } from '@/contexts/I18nContext'
import { HomeIcon } from '@heroicons/react/24/outline'
import Link from 'next/link'

interface BreadcrumbItem {
  label: string
  href?: string
}

interface BreadcrumbProps {
  items: BreadcrumbItem[]
}

export function Breadcrumb({ items }: BreadcrumbProps) {
  const { t } = useI18n()
  const allItems = items

  return (
    <nav className="flex min-w-0" aria-label={t('shared.breadcrumb.ariaLabel')}>
      {/* Wraps onto more lines on a narrow screen, and a long label (a task
          UUID) breaks anywhere, so the trail never widens the page (rubric
          e2e D02). */}
      <ol className="flex min-w-0 flex-wrap items-center gap-x-1 gap-y-1 text-sm">
        {allItems.map((item, index) => (
          <li
            key={item.href || `breadcrumb-${index}`}
            className="flex min-w-0 items-center wrap-anywhere"
          >
            {index > 0 && (
              <span className="mx-2 text-zinc-400 dark:text-zinc-600">/</span>
            )}
            {index === 0 &&
            (item.href === '/' || item.href === '/dashboard') ? (
              <Link
                href={item.href}
                className="text-zinc-600 transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
              >
                <HomeIcon className="h-4 w-4" />
              </Link>
            ) : index === allItems.length - 1 ? (
              <span className="font-medium text-zinc-900 dark:text-white">
                {item.label}
              </span>
            ) : (
              <Link
                href={item.href || '#'}
                className="text-zinc-600 transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
              >
                {item.label}
              </Link>
            )}
          </li>
        ))}
      </ol>
    </nav>
  )
}
