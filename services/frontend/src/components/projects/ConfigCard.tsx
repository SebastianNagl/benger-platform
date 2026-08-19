/**
 * Top-level collapsible card for the project detail page.
 *
 * Each card groups related sub-sections (Annotation, Generation, Evaluation,
 * Project Settings). Sub-sections are always editable for users with edit
 * permission; changes save automatically (the page debounces a flush through
 * the card's save handler). The header shows a small status chip while a
 * card has unsaved changes or a save in flight — there is no edit mode and
 * no manual save button.
 */

'use client'

import { useState, type ReactNode } from 'react'

interface ConfigCardProps {
  title: string
  /**
   * Short summary shown next to the title when the card is collapsed
   * (e.g. "10 Konfigurationen", "manual-Modus, 1 min. Annotation").
   */
  badge?: ReactNode
  defaultExpanded?: boolean
  /** Unsaved changes pending an auto-save flush. */
  dirty?: boolean
  /** A save flush is in flight. */
  saving?: boolean
  children: ReactNode
}

export function ConfigCard({
  title,
  badge,
  defaultExpanded = true,
  dirty,
  saving,
  children,
}: ConfigCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded)

  return (
    <div className="mb-8 rounded-lg bg-white p-6 shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-900 dark:ring-white/10">
      <div className="flex w-full items-center">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex flex-1 items-center space-x-3 text-left"
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
            className={`ml-auto h-5 w-5 flex-shrink-0 text-zinc-400 transition-transform ${
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
        {(saving || dirty) && (
          <span
            className="ml-3 flex items-center gap-1.5 whitespace-nowrap text-xs text-zinc-500 dark:text-zinc-400"
            role="status"
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                saving ? 'animate-pulse bg-emerald-500' : 'bg-amber-500'
              }`}
            />
            {saving ? 'Speichert…' : 'Ungespeicherte Änderungen'}
          </span>
        )}
      </div>
      {expanded && (
        <div className="mt-6 [&>*]:py-6 [&>*]:pl-6 [&>*:first-child]:pt-6 [&>*:last-child]:pb-2 [&>*+*]:border-t [&>*+*]:border-zinc-200 dark:[&>*+*]:border-zinc-700">
          {children}
        </div>
      )}
    </div>
  )
}
