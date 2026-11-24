/**
 * The fields of a project's timed access window: a switch that sets or
 * clears the window, and the opening and closing time. Only the switch turns
 * the window off; emptying the time fields keeps them shown. Controlled; the
 * creation wizard (StepSettings) and the project page's settings card
 * (ProjectAccessWindowSection) render the same fields and each saves them
 * its own way. The backend (shared/project_window.py) enforces the window.
 */

'use client'

import { Input } from '@/components/shared/Input'
import { Label } from '@/components/shared/Label'
import { useI18n } from '@/contexts/I18nContext'
import { isoToLocalInput, localInputToIso } from '@/utils/projectWindow'
import { useRef, useState, type KeyboardEvent } from 'react'

export interface AccessWindowValue {
  window_start_at: string | null
  window_end_at: string | null
}

/** False when both bounds are set and the window closes before it opens. */
export function isAccessWindowValid(value: AccessWindowValue): boolean {
  if (!value.window_start_at || !value.window_end_at) return true
  return new Date(value.window_end_at) > new Date(value.window_start_at)
}

/** The window the switch proposes: now (to the minute) for two hours. */
function proposedWindow(): AccessWindowValue {
  const start = new Date()
  start.setSeconds(0, 0)
  const end = new Date(start.getTime() + 2 * 3600 * 1000)
  return {
    window_start_at: start.toISOString(),
    window_end_at: end.toISOString(),
  }
}

interface AccessWindowFieldsProps {
  value: AccessWindowValue
  onChange: (value: AccessWindowValue) => void
  /**
   * Called with the value the user finished: on leaving or pressing Enter in
   * a time field while at least one time is set (a single time is an
   * open-ended window), and on switching the window on or off. Unlike
   * onChange it never fires for a time that is still being typed (also not
   * while either field is only partly filled), and only the switch commits
   * an empty window.
   */
  onCommit?: (value: AccessWindowValue) => void
  disabled?: boolean
  /** Show the title above the hint; off where a section header names it. */
  showTitle?: boolean
}

export function AccessWindowFields({
  value,
  onChange,
  onCommit,
  disabled = false,
  showTitle = true,
}: AccessWindowFieldsProps) {
  const { t } = useI18n()
  const hasBounds = !!(value.window_start_at || value.window_end_at)
  const [enabled, setEnabled] = useState(hasBounds)
  if (hasBounds && !enabled) setEnabled(true)
  const toggle = (on: boolean, next: AccessWindowValue) => {
    setEnabled(on)
    onChange(next)
    onCommit?.(next)
  }
  const opensRef = useRef<HTMLInputElement>(null)
  const closesRef = useRef<HTMLInputElement>(null)
  const commitTimes = () => {
    const partlyTyped = [opensRef, closesRef].some(
      (ref) => ref.current?.validity.badInput,
    )
    if (partlyTyped) return
    if (value.window_start_at || value.window_end_at) onCommit?.(value)
  }
  const commitOnEnter = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') commitTimes()
  }

  return (
    <div className="space-y-3" data-testid="access-window-fields">
      <div className="flex items-center justify-between gap-4">
        <div>
          {showTitle && (
            <Label>{t('project.settings.accessWindow.title')}</Label>
          )}
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            {t('project.settings.accessWindow.hint')}
          </p>
        </div>
        <input
          type="checkbox"
          aria-label={t('project.settings.accessWindow.title')}
          data-testid="access-window-toggle"
          checked={enabled}
          onChange={(e) => {
            if (!e.target.checked) {
              toggle(false, { window_start_at: null, window_end_at: null })
            } else {
              toggle(true, proposedWindow())
            }
          }}
          disabled={disabled}
          className="h-4 w-4 shrink-0 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
        />
      </div>

      {enabled && (
        <div className="ml-4 space-y-2">
          <div className="flex items-center gap-2">
            <Label htmlFor="access-window-opens" className="w-16 text-sm">
              {t('project.settings.accessWindow.opens')}
            </Label>
            <Input
              id="access-window-opens"
              ref={opensRef}
              type="datetime-local"
              value={isoToLocalInput(value.window_start_at)}
              onChange={(e) =>
                onChange({
                  ...value,
                  window_start_at: localInputToIso(e.target.value),
                })
              }
              onBlur={commitTimes}
              onKeyDown={commitOnEnter}
              disabled={disabled}
              className="text-sm"
            />
          </div>
          <div className="flex items-center gap-2">
            <Label htmlFor="access-window-closes" className="w-16 text-sm">
              {t('project.settings.accessWindow.closes')}
            </Label>
            <Input
              id="access-window-closes"
              ref={closesRef}
              type="datetime-local"
              value={isoToLocalInput(value.window_end_at)}
              onChange={(e) =>
                onChange({
                  ...value,
                  window_end_at: localInputToIso(e.target.value),
                })
              }
              onBlur={commitTimes}
              onKeyDown={commitOnEnter}
              disabled={disabled}
              className="text-sm"
            />
          </div>
          {!isAccessWindowValid(value) && (
            <p className="text-xs text-red-500" role="alert">
              {t('project.settings.accessWindow.invalid')}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
