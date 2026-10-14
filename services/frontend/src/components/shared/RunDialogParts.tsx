/**
 * Shared look of the run dialogs ("Generierung starten" and "Evaluierung
 * starten"). The class strings follow the conventions used across the app's
 * forms (zinc palette, emerald accents, rounded-lg option cards as in the
 * permission panels, the collapsible card of the project wizard), so both
 * dialogs read as one family without each spelling them out.
 */

import { Button } from '@/components/shared/Button'
import { ReactNode } from 'react'

export const RUN_DIALOG = {
  overlay: 'fixed inset-0 bg-black/30 transition-opacity dark:bg-black/50',
  panel:
    'relative transform overflow-hidden rounded-lg bg-white px-4 pt-5 pb-4 text-left shadow-xl transition-all sm:my-8 sm:w-full sm:max-w-4xl sm:p-6 dark:bg-zinc-800',
  closeButton:
    'rounded-md text-zinc-400 hover:text-zinc-500 focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 focus:outline-none dark:text-zinc-500 dark:hover:text-zinc-300 dark:focus:ring-offset-zinc-800',
  title: 'text-lg leading-6 font-semibold text-zinc-900 dark:text-white',
  sectionLabel: 'mb-2 block text-sm font-medium text-zinc-900 dark:text-white',
  fieldLabel: 'block text-sm font-medium text-zinc-700 dark:text-zinc-300',
  hint: 'text-xs text-zinc-500 dark:text-zinc-400',
  optionCard:
    'flex items-start gap-3 rounded-lg border border-zinc-200 p-3 transition-colors hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-700/40',
  optionTitle:
    'cursor-pointer text-sm font-medium text-zinc-900 dark:text-white',
  optionDescription: 'mt-0.5 text-sm text-zinc-600 dark:text-zinc-400',
  radio:
    'mt-1 h-4 w-4 shrink-0 border-zinc-300 text-emerald-600 accent-emerald-600 focus:ring-emerald-500 dark:border-zinc-600 dark:accent-emerald-500',
  checkbox:
    'h-4 w-4 shrink-0 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600',
  checkList:
    'max-h-48 divide-y divide-zinc-100 overflow-y-auto rounded-lg border border-zinc-200 dark:divide-zinc-700/60 dark:border-zinc-700',
  checkRow:
    'flex cursor-pointer items-center gap-3 px-3 py-2 text-sm text-zinc-900 transition-colors hover:bg-zinc-50 dark:text-zinc-100 dark:hover:bg-zinc-700/40',
  groupLabel:
    'flex items-center gap-2 bg-zinc-50 px-3 py-1.5 text-xs font-medium text-zinc-500 dark:bg-zinc-900/40 dark:text-zinc-400',
  summaryBox: 'rounded-lg border border-zinc-200 p-4 dark:border-zinc-700',
  summaryLabel: 'text-sm text-zinc-600 dark:text-zinc-400',
  summaryValue: 'mt-1 text-lg font-semibold text-zinc-900 dark:text-white',
  inlineLink:
    'font-medium text-emerald-600 hover:text-emerald-700 dark:text-emerald-400 dark:hover:text-emerald-300',
  emptyState:
    'rounded-lg border border-dashed border-zinc-300 px-3 py-2 text-xs text-zinc-500 dark:border-zinc-700 dark:text-zinc-400',
  warningText: 'text-xs text-amber-700 dark:text-amber-400',
} as const

/** Count of picked entries plus "select all" / "clear all" under a list. */
export function SelectionFooter({
  summary,
  selectAllLabel,
  clearAllLabel,
  onSelectAll,
  onClearAll,
}: {
  summary: ReactNode
  selectAllLabel: ReactNode
  clearAllLabel: ReactNode
  onSelectAll: () => void
  onClearAll: () => void
}) {
  return (
    <div className="mt-2 flex items-center justify-between gap-4">
      <span className="text-sm text-zinc-600 dark:text-zinc-400">
        {summary}
      </span>
      <div className="flex items-center gap-4">
        <Button variant="text" onClick={onSelectAll}>
          {selectAllLabel}
        </Button>
        <Button variant="text" onClick={onClearAll}>
          {clearAllLabel}
        </Button>
      </div>
    </div>
  )
}
