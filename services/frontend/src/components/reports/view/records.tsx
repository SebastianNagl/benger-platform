/**
 * Small building blocks for the record-like report sections (data
 * provenance, generation details, human evaluation, reproducibility): one
 * table look, a hash value that wraps instead of overflowing, and an
 * expandable JSON document.
 */

import { CopyValueButton } from '@/components/analysis/RunProvenance'
import clsx from 'clsx'
import type { ReactNode } from 'react'
import type { TranslateFn } from './chartTheme'

/** Placeholder for a missing value, the same glyph the metric formatters use. */
export const MISSING = '–'

export const TH =
  'px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400'
export const TD = 'px-3 py-2 text-sm text-zinc-800 dark:text-zinc-200'
export const NUM = 'text-right tabular-nums'

/** A bordered, horizontally scrollable table with the report's header style. */
export function RecordTable({
  head,
  children,
  testId,
}: {
  head: ReactNode
  children: ReactNode
  testId?: string
}) {
  return (
    <div
      className="overflow-x-auto rounded-md border border-zinc-200 dark:border-zinc-800 print:overflow-visible"
      data-testid={testId}
    >
      <table className="min-w-full divide-y divide-zinc-200 dark:divide-zinc-800">
        <thead className="bg-zinc-50 dark:bg-zinc-900/60">
          <tr>{head}</tr>
        </thead>
        <tbody className="divide-y divide-zinc-100 bg-white dark:divide-zinc-800 dark:bg-zinc-900">
          {children}
        </tbody>
      </table>
    </div>
  )
}

/** A full hash in monospace that breaks anywhere, with a copy button. */
export function HashValue({
  value,
  label,
  className,
}: {
  value: string | null | undefined
  /** Accessible name of the copy button. */
  label: string
  className?: string
}) {
  if (!value) return <span className="text-zinc-400">{MISSING}</span>
  return (
    <span
      className={clsx('inline-flex max-w-full items-start gap-1', className)}
    >
      <code className="min-w-0 font-mono text-xs break-all text-zinc-700 dark:text-zinc-300">
        {value}
      </code>
      <span className="shrink-0 print:hidden">
        <CopyValueButton value={value} label={label} />
      </span>
    </span>
  )
}

/** A JSON document behind a disclosure, for manifests and parameters. */
export function JsonDetails({
  summary,
  value,
}: {
  summary: string
  value: unknown
}) {
  return (
    <details className="group mt-1 text-xs">
      <summary className="cursor-pointer text-emerald-700 hover:underline dark:text-emerald-400">
        {summary}
      </summary>
      <pre className="mt-1 max-h-64 overflow-auto rounded bg-zinc-50 p-2 font-mono text-xs break-all whitespace-pre-wrap text-zinc-700 dark:bg-zinc-800/60 dark:text-zinc-300">
        {JSON.stringify(value, null, 2)}
      </pre>
    </details>
  )
}

/** A label/value list (definition list) for the appendix. */
export function FactList({
  items,
}: {
  items: Array<{ label: string; value: ReactNode; testId?: string }>
}) {
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-[minmax(0,14rem)_minmax(0,1fr)]">
      {items.map((item) => (
        <div key={item.label} className="contents" data-testid={item.testId}>
          <dt className="text-xs font-medium tracking-wide text-zinc-500 uppercase sm:pt-0.5 dark:text-zinc-400">
            {item.label}
          </dt>
          <dd className="min-w-0 text-sm text-zinc-800 dark:text-zinc-200">
            {item.value}
          </dd>
        </div>
      ))}
    </dl>
  )
}

export type { TranslateFn }
