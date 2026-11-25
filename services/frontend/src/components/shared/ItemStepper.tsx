'use client'

/**
 * Previous / next through a list of items, with an "x of y" counter between
 * the two buttons. The buttons are icon buttons with accessible names and
 * are disabled at the ends of the list (and while `disabled` is set).
 *
 * The default variant uses outlined buttons, for a page's detail pane; the
 * compact variant uses bare chevrons, for a dense header such as a full
 * screen dialog's. `children` replace the counter between the buttons (a
 * dialog title, say), and `labels` replace the generic names with ones that
 * say what is being stepped through.
 */

import { ChevronLeftIcon, ChevronRightIcon } from '@heroicons/react/24/outline'
import clsx from 'clsx'
import { ReactNode } from 'react'

import { Button } from '@/components/shared/Button'
import { useI18n } from '@/contexts/I18nContext'

export interface ItemStepperProps {
  /** Zero-based position of the current item; below 0 when none is shown. */
  index: number
  total: number
  onPrevious: () => void
  onNext: () => void
  /** Disables both buttons, such as while the current item loads. */
  disabled?: boolean
  variant?: 'default' | 'compact'
  /** Accessible names of the buttons; generic ones by default. */
  labels?: { previous?: string; next?: string }
  /** Shown between the buttons instead of the counter. */
  children?: ReactNode
  className?: string
  /** Prefix of the test ids: `<prefix>-previous`, `-position`, `-next`. */
  testId?: string
}

export function ItemStepper({
  index,
  total,
  onPrevious,
  onNext,
  disabled = false,
  variant = 'default',
  labels,
  children,
  className,
  testId = 'item-stepper',
}: ItemStepperProps) {
  const { t } = useI18n()
  const known = index >= 0 && index < total
  const previousDisabled = disabled || !known || index <= 0
  const nextDisabled = disabled || !known || index >= total - 1
  const previousLabel = labels?.previous || t('shared.itemStepper.previous')
  const nextLabel = labels?.next || t('shared.itemStepper.next')
  const compact = variant === 'compact'

  const middle =
    children !== undefined ? (
      children
    ) : (
      <span
        className={clsx(
          'text-zinc-600 tabular-nums dark:text-zinc-400',
          compact ? 'text-xs' : 'text-sm',
        )}
        aria-live="polite"
        data-testid={`${testId}-position`}
      >
        {known
          ? t('shared.itemStepper.position', {
              current: index + 1,
              total,
            })
          : ''}
      </span>
    )

  if (compact) {
    const bare =
      'rounded p-1 text-zinc-400 transition-colors hover:text-zinc-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 disabled:cursor-not-allowed disabled:opacity-30 dark:hover:text-zinc-300'
    return (
      <div
        className={clsx('flex items-center gap-4', className)}
        data-testid={testId}
      >
        <button
          type="button"
          onClick={onPrevious}
          disabled={previousDisabled}
          aria-label={previousLabel}
          title={previousLabel}
          className={bare}
          data-testid={`${testId}-previous`}
        >
          <ChevronLeftIcon className="h-5 w-5" aria-hidden="true" />
        </button>
        {middle}
        <button
          type="button"
          onClick={onNext}
          disabled={nextDisabled}
          aria-label={nextLabel}
          title={nextLabel}
          className={bare}
          data-testid={`${testId}-next`}
        >
          <ChevronRightIcon className="h-5 w-5" aria-hidden="true" />
        </button>
      </div>
    )
  }

  return (
    <div
      className={clsx('flex items-center gap-2', className)}
      data-testid={testId}
    >
      <Button
        type="button"
        variant="outline"
        onClick={onPrevious}
        disabled={previousDisabled}
        aria-label={previousLabel}
        title={previousLabel}
        data-testid={`${testId}-previous`}
      >
        <ChevronLeftIcon className="h-4 w-4" aria-hidden="true" />
      </Button>
      {middle}
      <Button
        type="button"
        variant="outline"
        onClick={onNext}
        disabled={nextDisabled}
        aria-label={nextLabel}
        title={nextLabel}
        data-testid={`${testId}-next`}
      >
        <ChevronRightIcon className="h-4 w-4" aria-hidden="true" />
      </Button>
    </div>
  )
}

export default ItemStepper
