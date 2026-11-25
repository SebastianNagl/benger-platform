/**
 * Inner collapsible sub-section inside a ConfigCard. Collapsed by default
 * so the parent card stays scannable when expanded.
 *
 * Optional `actions` slot for an "Edit" button etc. shown to the right of
 * the title only when the sub-section is open, and an optional
 * `description` shown as the first line of the open sub-section.
 *
 * Uncontrolled by default; pass `expanded` with `onExpandedChange` when the
 * parent has to open or close it (e.g. collapse after a save).
 */

'use client'

import { useState, type ReactNode } from 'react'

interface SubSectionProps {
  title: string
  badge?: ReactNode
  description?: ReactNode
  defaultExpanded?: boolean
  expanded?: boolean
  onExpandedChange?: (expanded: boolean) => void
  actions?: ReactNode
  children: ReactNode
  'data-testid'?: string
}

export function SubSection({
  title,
  badge,
  description,
  defaultExpanded = false,
  expanded: expandedProp,
  onExpandedChange,
  actions,
  children,
  'data-testid': testId,
}: SubSectionProps) {
  const [expandedState, setExpandedState] = useState(defaultExpanded)
  const expanded = expandedProp ?? expandedState
  const toggle = () => {
    const next = !expanded
    if (expandedProp === undefined) setExpandedState(next)
    onExpandedChange?.(next)
  }

  return (
    <div className="bg-white dark:bg-zinc-900" data-testid={testId}>
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <button
          type="button"
          onClick={toggle}
          aria-expanded={expanded}
          className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-left"
        >
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
            {title}
          </h2>
          {badge && (
            <span className="rounded-md bg-zinc-100 px-2 py-1 text-sm leading-tight text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
              {badge}
            </span>
          )}
          <svg
            className={`h-5 w-5 shrink-0 text-zinc-400 transition-transform ${
              expanded ? 'rotate-90 transform' : ''
            }`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 5l7 7-7 7"
            />
          </svg>
        </button>
        {expanded && actions ? <div>{actions}</div> : null}
      </div>
      {expanded && (
        <div className="mt-4">
          {description ? (
            <p className="mb-4 text-xs text-zinc-500 dark:text-zinc-400">
              {description}
            </p>
          ) : null}
          {children}
        </div>
      )}
    </div>
  )
}
