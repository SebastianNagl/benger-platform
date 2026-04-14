/**
 * Pagination component following Label Studio patterns
 *
 * Displays traditional pagination controls with page numbers,
 * previous/next buttons, and page size selector
 */

import { useI18n } from '@/contexts/I18nContext'
import { cn } from '@/lib/utils'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/shared/Select'
import { ChevronLeftIcon, ChevronRightIcon } from '@heroicons/react/24/outline'

interface PaginationProps {
  currentPage: number
  totalPages: number
  totalItems: number
  pageSize: number
  onPageChange: (page: number) => void
  onPageSizeChange: (size: number) => void
  pageSizeOptions?: number[]
  className?: string
}

export function Pagination({
  currentPage,
  totalPages,
  totalItems,
  pageSize,
  onPageChange,
  onPageSizeChange,
  pageSizeOptions = [25, 50, 100],
  className,
}: PaginationProps) {
  const { t } = useI18n()

  // Calculate page range to display
  const getPageNumbers = () => {
    const delta = 2 // Pages to show on each side of current
    const range: (number | string)[] = []
    const rangeWithDots: (number | string)[] = []
    let l: number | undefined

    for (let i = 1; i <= totalPages; i++) {
      if (
        i === 1 ||
        i === totalPages ||
        (i >= currentPage - delta && i <= currentPage + delta)
      ) {
        range.push(i)
      }
    }

    range.forEach((i) => {
      if (l !== undefined && typeof i === 'number') {
        if (i - l === 2) {
          rangeWithDots.push(l + 1)
        } else if (i - l !== 1) {
          rangeWithDots.push('...')
        }
      }
      rangeWithDots.push(i)
      if (typeof i === 'number') {
        l = i
      }
    })

    return rangeWithDots
  }

  const startItem =
    totalItems === 0 ? 0 : ((currentPage || 1) - 1) * (pageSize || 10) + 1
  const endItem = Math.min(
    (currentPage || 1) * (pageSize || 10),
    totalItems || 0
  )

  return (
    <div className={cn('flex items-center justify-between', className)}>
      {/* Results info */}
      <div className="text-sm text-zinc-600 dark:text-zinc-400">
        {t('common.pagination.showingResults', { start: String(startItem), end: String(endItem), total: String(totalItems) })}
      </div>

      <div className="flex items-center gap-4">
        {/* Page size selector */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-zinc-600 dark:text-zinc-400">
            {t('common.pagination.perPage')}
          </span>
          <Select
            value={pageSize.toString()}
            onValueChange={(v) => onPageSizeChange(Number(v))}
          >
            <SelectTrigger className="w-20" aria-label={t('common.pagination.perPage')}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {pageSizeOptions.map((size) => (
                <SelectItem key={size} value={size.toString()}>
                  {size}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Navigation controls */}
        <nav className="flex items-center gap-1" aria-label="Pagination">
          {/* Previous button */}
          <button
            onClick={() => onPageChange(currentPage - 1)}
            disabled={currentPage === 1}
            className={cn(
              'inline-flex items-center rounded-md px-2 py-2 text-sm font-medium',
              currentPage === 1
                ? 'cursor-not-allowed text-zinc-400 dark:text-zinc-600'
                : 'text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800'
            )}
            aria-label={t('common.pagination.previousPage')}
          >
            <ChevronLeftIcon className="h-4 w-4" />
          </button>

          {/* Page numbers */}
          {getPageNumbers().map((page, index) => {
            if (page === '...') {
              return (
                <span
                  key={`dots-${index}`}
                  className="px-3 py-2 text-sm text-zinc-500 dark:text-zinc-400"
                >
                  …
                </span>
              )
            }

            const pageNumber = page as number
            const isActive = pageNumber === currentPage

            return (
              <button
                key={pageNumber}
                onClick={() => onPageChange(pageNumber)}
                className={cn(
                  'inline-flex items-center rounded-md px-3 py-2 text-sm font-medium',
                  isActive
                    ? 'bg-emerald-600 text-white'
                    : 'text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800'
                )}
                aria-label={t('shared.pagination.goToPage', { page: String(pageNumber) })}
                aria-current={isActive ? 'page' : undefined}
              >
                {pageNumber}
              </button>
            )
          })}

          {/* Next button */}
          <button
            onClick={() => onPageChange(currentPage + 1)}
            disabled={currentPage === totalPages}
            className={cn(
              'inline-flex items-center rounded-md px-2 py-2 text-sm font-medium',
              currentPage === totalPages
                ? 'cursor-not-allowed text-zinc-400 dark:text-zinc-600'
                : 'text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800'
            )}
            aria-label={t('common.pagination.nextPage')}
          >
            <ChevronRightIcon className="h-4 w-4" />
          </button>
        </nav>
      </div>
    </div>
  )
}
