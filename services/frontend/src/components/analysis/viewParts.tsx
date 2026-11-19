'use client'

/**
 * Small building blocks of the variant and request views: a titled panel,
 * notices, definition fields, shortened hashes and system names. Styling
 * follows the analysis run page.
 */

import { systemParts } from '@/lib/analysis/labels'
import { MISSING } from '@/lib/analysis/results'
import clsx from 'clsx'
import type { ReactNode } from 'react'

/** A titled block inside a card or section. */
export function ViewPanel({
  title,
  description,
  actions,
  children,
  testId,
}: {
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  children: ReactNode
  testId?: string
}) {
  return (
    <div
      className="min-w-0 rounded-md border border-zinc-200 p-4 dark:border-zinc-800"
      data-testid={testId}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold break-words text-zinc-900 dark:text-white">
            {title}
          </h3>
          {description && (
            <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
              {description}
            </p>
          )}
        </div>
        {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
      </div>
      <div className="mt-3 min-w-0">{children}</div>
    </div>
  )
}

/** A system key shown as its model with the parameter profile beside it. */
export function SystemName({
  systemKey,
  className,
}: {
  systemKey: string | null | undefined
  className?: string
}) {
  const { model, profile } = systemParts(systemKey)
  return (
    <span
      className={clsx('inline-flex min-w-0 items-baseline gap-1', className)}
      title={systemKey ?? undefined}
    >
      <span className="truncate font-medium">{model || MISSING}</span>
      {profile && (
        <span className="shrink-0 font-mono text-[11px] text-zinc-500 dark:text-zinc-400">
          @{profile.slice(0, 6)}
        </span>
      )}
    </span>
  )
}

/** A hex digest shortened to 16 characters (the full one in its title). */
export function ShortHash({ value }: { value: string | null | undefined }) {
  if (!value) return <span className="text-zinc-400">{MISSING}</span>
  return (
    <span className="font-mono text-xs whitespace-nowrap" title={value}>
      {value.length > 16 ? `${value.slice(0, 16)}…` : value}
    </span>
  )
}

export function Notice({
  tone = 'info',
  children,
  testId,
}: {
  tone?: 'info' | 'warning' | 'error'
  children: ReactNode
  testId?: string
}) {
  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      data-testid={testId}
      className={clsx(
        'rounded-md border p-3 text-sm',
        tone === 'error' &&
          'border-red-300 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300',
        tone === 'warning' &&
          'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900/60 dark:bg-amber-900/20 dark:text-amber-300',
        tone === 'info' &&
          'border-zinc-200 bg-zinc-50 text-zinc-600 dark:border-zinc-800 dark:bg-zinc-800/40 dark:text-zinc-400',
      )}
    >
      {children}
    </div>
  )
}

/** A definition list row: label and value. */
export function Field({
  label,
  children,
}: {
  label: ReactNode
  children: ReactNode
}) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
        {label}
      </dt>
      <dd className="mt-0.5 min-w-0 text-sm break-words text-zinc-900 dark:text-zinc-100">
        {children}
      </dd>
    </div>
  )
}
