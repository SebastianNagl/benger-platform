/**
 * "Zeitfenster für den Zugriff" sub-section of the project page's settings
 * card, next to the project visibility: both decide who sees the project
 * when. It saves on its own (like the other settings sub-sections), but only
 * a finished edit: on leaving or pressing Enter in a time field, or on
 * switching the window on or off. A time still being typed is never saved,
 * since a partial date (year 0002) could open the window to students. The
 * badge shows the saved window, the one the server enforces.
 */

'use client'

import { SubSection } from '@/components/projects/SubSection'
import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import { computeWindowState, windowStateLabel } from '@/utils/projectWindow'
import { useRef, useState } from 'react'
import {
  AccessWindowFields,
  isAccessWindowValid,
  type AccessWindowValue,
} from './AccessWindowFields'

interface ProjectAccessWindowSectionProps {
  windowStartAt: string | null | undefined
  windowEndAt: string | null | undefined
  /** Persists the window (PATCH of the project); rejects on failure. */
  onSave: (value: AccessWindowValue) => Promise<void>
}

const instant = (iso: string | null) => (iso ? new Date(iso).getTime() : null)

const sameWindow = (a: AccessWindowValue, b: AccessWindowValue) =>
  instant(a.window_start_at) === instant(b.window_start_at) &&
  instant(a.window_end_at) === instant(b.window_end_at)

/** No window, or both bounds set and the window closes after it opens. */
const isComplete = (value: AccessWindowValue) =>
  (!value.window_start_at && !value.window_end_at) ||
  (!!value.window_start_at &&
    !!value.window_end_at &&
    isAccessWindowValid(value))

export function ProjectAccessWindowSection({
  windowStartAt,
  windowEndAt,
  onSave,
}: ProjectAccessWindowSectionProps) {
  const { t, locale } = useI18n()
  const { addToast } = useToast()
  // The edit not saved yet; null shows the stored window. Kept until its
  // save went through, so a refetch of the project in between never
  // overwrites what the user is typing, and kept after a failed save.
  const [edit, setEdit] = useState<AccessWindowValue | null>(null)
  const stored: AccessWindowValue = {
    window_start_at: windowStartAt ?? null,
    window_end_at: windowEndAt ?? null,
  }
  const draft = edit ?? stored
  // The value whose save is in flight, so Enter followed by blur saves once.
  const saving = useRef<AccessWindowValue | null>(null)

  const clearEdit = (value: AccessWindowValue) =>
    setEdit((current) => (current === value ? null : current))

  const commit = (value: AccessWindowValue) => {
    if (!isComplete(value)) return
    if (saving.current && sameWindow(value, saving.current)) return
    if (sameWindow(value, stored)) {
      clearEdit(value)
      return
    }
    saving.current = value
    onSave(value)
      // A newer edit made during the save stays pending.
      .then(
        () => clearEdit(value),
        (error: unknown) => {
          addToast(
            t('toasts.project.settingsSaveFailed', {
              error: error instanceof Error ? error.message : '',
            }),
            'error',
          )
        },
      )
      .finally(() => {
        if (saving.current === value) saving.current = null
      })
  }

  const state = computeWindowState(stored.window_start_at, stored.window_end_at)

  return (
    <div data-testid="project-access-window">
      <SubSection
        title={t('project.settings.accessWindow.title')}
        badge={windowStateLabel(state, stored.window_start_at, t, locale)}
      >
        <AccessWindowFields
          value={draft}
          showTitle={false}
          onChange={setEdit}
          onCommit={commit}
        />
      </SubSection>
    </div>
  )
}
