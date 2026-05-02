/**
 * Inner collapsible sub-section inside a ConfigCard. Collapsed by default
 * so the parent card stays scannable when expanded.
 *
 * Optional `actions` slot for an "Edit" button etc. shown to the right of
 * the title only when the sub-section is open.
 */

'use client'

import { useState, type ReactNode } from 'react'

interface SubSectionProps {
  title: string
  badge?: ReactNode
  defaultExpanded?: boolean
  actions?: ReactNode
  children: ReactNode
}

export function SubSection({
  title,
  badge,
  defaultExpanded = false,
  actions,
  children,
}: SubSectionProps) {
  const [expanded, setExpanded] = useState(defaultExpanded)

  return (
    <div className="bg-white dark:bg-zinc-900">
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex items-center space-x-3 text-left"
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
            className={`h-5 w-5 flex-shrink-0 text-zinc-400 transition-transform ${
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
      {expanded && <div className="mt-4">{children}</div>}
    </div>
  )
}
