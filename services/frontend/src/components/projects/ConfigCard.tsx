/**
 * Top-level collapsible card for the project detail page.
 *
 * Each card groups related sub-sections (Annotation, Generation, Evaluation,
 * Project Settings). The card owns a single edit/save lifecycle so all
 * sub-sections inside flush as one atomic Speichern action.
 */

'use client'

import { useState, type ReactNode } from 'react'
import { Button } from '@/components/shared/Button'

interface ConfigCardProps {
  title: string
  /**
   * Short summary shown next to the title when the card is collapsed
   * (e.g. "10 Konfigurationen", "manual-Modus, 1 min. Annotation").
   */
  badge?: ReactNode
  defaultExpanded?: boolean
  /**
   * When the consumer wires `editing` + `onEdit` + `onSave`, the card
   * renders a single Bearbeiten / Speichern / Abbrechen button group at
   * its header. Sub-sections inside should treat `editing` as the source
   * of truth so the one Save flushes everything.
   */
  editing?: boolean
  onEdit?: () => void
  onSave?: () => Promise<void> | void
  onCancel?: () => void
  saving?: boolean
  canEdit?: boolean
  children: ReactNode
}

export function ConfigCard({
  title,
  badge,
  defaultExpanded = true,
  editing,
  onEdit,
  onSave,
  onCancel,
  saving,
  canEdit,
  children,
}: ConfigCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded)
  const showEditControls = !!onEdit && !!onSave && canEdit !== false

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
        {expanded && showEditControls && (
          <div className="ml-3 flex items-center gap-2">
            {editing ? (
              <>
                <Button
                  variant="outline"
                  className="text-sm"
                  onClick={onCancel}
                  disabled={saving}
                >
                  Abbrechen
                </Button>
                <Button
                  className="text-sm"
                  onClick={() => void onSave?.()}
                  disabled={saving}
                >
                  {saving ? 'Speichert…' : 'Speichern'}
                </Button>
              </>
            ) : (
              <Button
                variant="outline"
                className="text-sm"
                onClick={onEdit}
              >
                Bearbeiten
              </Button>
            )}
          </div>
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
