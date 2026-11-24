/**
 * Client-side mirror of the backend project access-window state
 * (services/shared/project_window.py). The backend is authoritative (endpoints
 * return 403 outside the window); this only drives UX — gating the labeling
 * page, badging the project list, and folding into the permission helpers so we
 * don't render data views that would 403.
 */

import { intlTag, readStoredLocale } from '@/lib/i18n/locales'

export type WindowState = 'none' | 'upcoming' | 'open' | 'closed'

export function computeWindowState(
  startAt?: string | null,
  endAt?: string | null,
  now: Date = new Date(),
): WindowState {
  if (!startAt && !endAt) return 'none'
  const t = now.getTime()
  if (startAt && t < new Date(startAt).getTime()) return 'upcoming'
  if (endAt && t > new Date(endAt).getTime()) return 'closed'
  return 'open'
}

// A datetime-local <input> holds a LOCAL wall-clock string ("YYYY-MM-DDTHH:mm",
// no timezone); we store/transport the window bounds as ISO-8601 UTC.
export function isoToLocalInput(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16)
}
export function localInputToIso(local: string): string | null {
  if (!local) return null
  const d = new Date(local) // parsed as local time
  return isNaN(d.getTime()) ? null : d.toISOString()
}

/** The bound relevant to the current state (start when upcoming, end when closed). */
export function windowBoundLabel(
  state: WindowState,
  startAt?: string | null,
  endAt?: string | null,
): string | null {
  if (state === 'upcoming' && startAt)
    return new Date(startAt).toLocaleString(intlTag(readStoredLocale()))
  if (state === 'closed' && endAt)
    return new Date(endAt).toLocaleString(intlTag(readStoredLocale()))
  return null
}

/**
 * Short label of a window state ("Öffnet 24.11.2026" / "Offen" /
 * "Beendet"), or null without a window. The project list badges and the
 * settings card's access window section share it.
 */
export function windowStateLabel(
  state: WindowState,
  startAt: string | null | undefined,
  t: (key: string, vars?: Record<string, unknown>) => string,
  locale: string,
): string | null {
  if (state === 'none') return null
  if (state === 'upcoming')
    return t('projects.list.windowUpcoming', {
      date: startAt
        ? new Date(startAt).toLocaleDateString(intlTag(locale))
        : '',
    })
  if (state === 'closed') return t('projects.list.windowClosed')
  return t('projects.list.windowOpen')
}
