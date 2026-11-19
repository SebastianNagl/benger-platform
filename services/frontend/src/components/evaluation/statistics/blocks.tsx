'use client'

/**
 * Layout primitives of the statistics panel's blocks (Inference, Fit,
 * Agreement and validity): a titled block, a titled sub-block holding a
 * scrollable table, and the table itself with its cell classes.
 */

import type { ReactNode } from 'react'

export const th =
  'px-3 py-2 text-left text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400'
export const td = 'px-3 py-2 text-zinc-800 dark:text-zinc-200'
export const num =
  'px-3 py-2 text-right font-mono text-xs whitespace-nowrap text-zinc-800 dark:text-zinc-200'

export function Block({
  title,
  description,
  children,
  testId,
}: {
  title: string
  description?: string
  children: ReactNode
  testId?: string
}) {
  return (
    <section
      className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-900"
      data-testid={testId}
    >
      <h3 className="text-lg font-semibold text-zinc-900 dark:text-white">
        {title}
      </h3>
      {description && (
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          {description}
        </p>
      )}
      <div className="mt-4 space-y-5">{children}</div>
    </section>
  )
}

export function SubBlock({
  title,
  description,
  children,
  testId,
}: {
  title: string
  description?: string
  children: ReactNode
  testId?: string
}) {
  return (
    <div data-testid={testId}>
      <h4 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
        {title}
      </h4>
      {description && (
        <p className="-mt-1 mb-2 text-xs text-zinc-500 dark:text-zinc-400">
          {description}
        </p>
      )}
      <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
        {children}
      </div>
    </div>
  )
}

export function Table({
  head,
  children,
}: {
  head: ReactNode
  children: ReactNode
}) {
  return (
    <table className="min-w-full divide-y divide-zinc-200 text-sm dark:divide-zinc-800">
      <thead className="bg-zinc-50 dark:bg-zinc-900/40">
        <tr>{head}</tr>
      </thead>
      <tbody className="divide-y divide-zinc-100 bg-white dark:divide-zinc-800 dark:bg-zinc-950">
        {children}
      </tbody>
    </table>
  )
}
