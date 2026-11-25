/**
 * "Zeitfenster für den Zugriff" sub-section of the project page's settings
 * card, next to the project visibility: both decide who sees the project
 * when. It saves on its own through the shared auto-save, but only a
 * finished edit: on leaving or pressing Enter in a time field, or on
 * switching the window on or off. A time still being typed is never saved,
 * since a partial date (year 0002) could open the window to students.
 * Opening or closing access is high-impact (risk registry key
 * `access_window`): the change is confirmed first, and cancelling puts the
 * fields back to the saved window. Only a confirmed window reaches the
 * auto-save, so nothing unconfirmed is saved when the section unmounts.
 * The badge shows the saved window, the one the server enforces.
 */

'use client'

import { SubSection } from '@/components/projects/SubSection'
import { useAutoSave } from '@/components/shared/AutoSave'
import { useGatedSettingChange } from '@/components/shared/settingRisk'
import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import { computeWindowState, windowStateLabel } from '@/utils/projectWindow'
import { useEffect, useState } from 'react'
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

export function ProjectAccessWindowSection({
  windowStartAt,
  windowEndAt,
  onSave,
}: ProjectAccessWindowSectionProps) {
  const { t, locale } = useI18n()
  const { addToast } = useToast()
  const gateChange = useGatedSettingChange()
  // The window being typed, not confirmed yet; null shows the pending one.
  const [edit, setEdit] = useState<AccessWindowValue | null>(null)
  // The confirmed window not saved yet; null is the stored window. Kept
  // until its save went through, so a refetch of the project in between
  // never overwrites it, and kept after a failed save.
  const [confirmed, setConfirmed] = useState<AccessWindowValue | null>(null)
  const stored: AccessWindowValue = {
    window_start_at: windowStartAt ?? null,
    window_end_at: windowEndAt ?? null,
  }
  const pending = confirmed ?? stored
  const draft = edit ?? pending

  const autoSave = useAutoSave({
    value: pending,
    savedValue: stored,
    saveOn: 'commit',
    isValid: isAccessWindowValid,
    save: async (value) => {
      try {
        await onSave(value)
      } catch (error) {
        addToast(
          t('toasts.project.settingsSaveFailed', {
            error: error instanceof Error ? error.message : '',
          }),
          'error',
        )
        throw error
      }
    },
    onUndo: (previous) => {
      setEdit(null)
      setConfirmed(previous)
    },
    riskChanges: (from, to) => [{ key: 'access_window', from, to }],
  })

  // The confirmed window is done once the stored window (refetched
  // project) shows it; dropping it earlier would show the old window until
  // the refetch lands.
  if (confirmed && sameWindow(confirmed, stored) && !autoSave.saving)
    setConfirmed(null)

  // Save once the committed window has rendered (the auto-save reads the
  // rendered value).
  const [commitRequest, setCommitRequest] = useState(0)
  const commitNow = autoSave.commit
  useEffect(() => {
    if (commitRequest > 0) void commitNow()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [commitRequest])

  const commit = (value: AccessWindowValue) => {
    if (!isAccessWindowValid(value)) return
    if (sameWindow(value, stored)) {
      setEdit(null)
      setConfirmed(null)
      return
    }
    gateChange(
      [{ key: 'access_window', from: stored, to: value }],
      () => {
        setEdit(null)
        setConfirmed(value)
        setCommitRequest((n) => n + 1)
      },
      // Cancelled: back to the window before this edit.
      () => setEdit(null),
    )
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
