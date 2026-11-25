/**
 * Top-level collapsible card for the project detail page.
 *
 * Each card groups related sub-sections (Annotation, Generation, Evaluation,
 * Project Settings). Sub-sections are always editable for users with edit
 * permission; changes save automatically (the page debounces a flush through
 * the card's save handler). The header shows a small status chip while a
 * card has unsaved changes or a save in flight — there is no edit mode and
 * no manual save button. Sections that save themselves (`useAutoSave`)
 * report into the same chip through the card's AutoSaveStatusProvider.
 */

'use client'

import { AutoSaveStatusProvider } from '@/components/shared/AutoSave'
import { useI18n } from '@/contexts/I18nContext'
import { useState, type ReactNode } from 'react'

interface ConfigCardProps {
  title: string
  /**
   * Short summary shown next to the title when the card is collapsed
   * (e.g. "10 Konfigurationen", "manual-Modus, 1 min. Annotation").
   */
  badge?: ReactNode
  /** One line about the whole card, shown under the title while open. */
  description?: ReactNode
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
  description,
  defaultExpanded = true,
  dirty,
  saving,
  children,
}: ConfigCardProps) {
  const { t } = useI18n()
  const [expanded, setExpanded] = useState(defaultExpanded)

  return (
    <AutoSaveStatusProvider>
      {(sections) => (
        <ConfigCardFrame
          title={title}
          badge={badge}
          description={description}
          expanded={expanded}
          onToggle={() => setExpanded((v) => !v)}
          dirty={!!dirty || sections.dirty}
          saving={!!saving || sections.saving}
          savingLabel={t('project.configCard.saving')}
          dirtyLabel={t('project.configCard.unsavedChanges')}
        >
          {children}
        </ConfigCardFrame>
      )}
    </AutoSaveStatusProvider>
  )
}

function ConfigCardFrame({
  title,
  badge,
  description,
  expanded,
  onToggle,
  dirty,
  saving,
  savingLabel,
  dirtyLabel,
  children,
}: {
  title: string
  badge?: ReactNode
  description?: ReactNode
  expanded: boolean
  onToggle: () => void
  dirty: boolean
  saving: boolean
  savingLabel: string
  dirtyLabel: string
  children: ReactNode
}) {
  return (
    <div className="mb-8 rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex w-full items-center">
        <button
          type="button"
          onClick={onToggle}
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
            className={`ml-auto h-5 w-5 shrink-0 text-zinc-400 transition-transform ${
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
            className="ml-3 flex items-center gap-1.5 text-xs whitespace-nowrap text-zinc-500 dark:text-zinc-400"
            role="status"
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                saving ? 'animate-pulse bg-emerald-500' : 'bg-amber-500'
              }`}
            />
            {saving ? savingLabel : dirtyLabel}
          </span>
        )}
      </div>
      {expanded && description ? (
        <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
          {description}
        </p>
      ) : null}
      {expanded && (
        <div className="mt-6 *:py-6 *:pl-6 [&>*+*]:border-t [&>*+*]:border-zinc-200 dark:[&>*+*]:border-zinc-700 [&>*:first-child]:pt-6 [&>*:last-child]:pb-2">
          {children}
        </div>
      )}
    </div>
  )
}
