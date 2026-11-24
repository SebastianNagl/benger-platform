/**
 * "Zeitfenster für den Zugriff" sub-section of the project page's settings
 * card, next to the project visibility: both decide who sees the project
 * when. It saves on its own (like the other settings sub-sections): a change
 * is written shortly after the last edit, as long as the window is valid.
 */

'use client'

import { SubSection } from '@/components/projects/SubSection'
import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import { computeWindowState, windowStateLabel } from '@/utils/projectWindow'
import { useEffect, useRef, useState } from 'react'
import {
  AccessWindowFields,
  isAccessWindowValid,
  type AccessWindowValue,
} from './AccessWindowFields'

/** Delay between the last edit and the save. */
export const ACCESS_WINDOW_SAVE_DELAY_MS = 800

interface ProjectAccessWindowSectionProps {
  windowStartAt: string | null | undefined
  windowEndAt: string | null | undefined
  /** Persists the window (PATCH of the project); rejects on failure. */
  onSave: (value: AccessWindowValue) => Promise<void>
}

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
  const draft: AccessWindowValue = edit ?? {
    window_start_at: windowStartAt ?? null,
    window_end_at: windowEndAt ?? null,
  }
  // The latest save callback (the page passes a new closure per render), so
  // a re-render of the page never restarts the save delay.
  const onSaveRef = useRef(onSave)
  useEffect(() => {
    onSaveRef.current = onSave
  }, [onSave])

  useEffect(() => {
    if (!edit || !isAccessWindowValid(edit)) return
    const timer = setTimeout(() => {
      onSaveRef.current(edit).then(
        // A newer edit made during the save stays pending.
        () => setEdit((current) => (current === edit ? null : current)),
        (error: unknown) => {
          addToast(
            t('toasts.project.settingsSaveFailed', {
              error: error instanceof Error ? error.message : '',
            }),
            'error',
          )
        },
      )
    }, ACCESS_WINDOW_SAVE_DELAY_MS)
    return () => clearTimeout(timer)
  }, [edit, addToast, t])

  const state = computeWindowState(draft.window_start_at, draft.window_end_at)

  return (
    <div data-testid="project-access-window">
      <SubSection
        title={t('project.settings.accessWindow.title')}
        badge={windowStateLabel(state, draft.window_start_at, t, locale)}
      >
        <AccessWindowFields
          value={draft}
          showTitle={false}
          onChange={setEdit}
        />
      </SubSection>
    </div>
  )
}
