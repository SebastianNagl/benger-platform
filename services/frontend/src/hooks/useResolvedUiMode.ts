'use client'

import { useAuth } from '@/contexts/AuthContext'
import { hasSlot, useSlot } from '@/lib/extensions/slots'
import { isStudentLockedHost } from '@/lib/utils/subdomain'
import { useUIStore } from '@/stores'

export type UiMode = 'student' | 'expert'

/**
 * Whether the running build is the extended edition. The student shell only
 * exists in extended; community always renders the expert (default) shell.
 */
export function isExtendedEdition(): boolean {
  return process.env.NEXT_PUBLIC_BENGER_EDITION === 'extended'
}

/**
 * Resolve the EFFECTIVE UI mode (the single source of truth for which shell
 * renders).
 *
 * Precedence:
 *
 *   1. Community edition (NEXT_PUBLIC_BENGER_EDITION !== 'extended') → 'expert'.
 *      There is no student experience to render.
 *   2. Extended edition but the StudentShell slot is not registered yet (the
 *      extended package hasn't loaded, or this build doesn't ship it) →
 *      'expert'. Never show a broken/empty student shell.
 *   3. Authenticated user → their switch choice wins over the host default:
 *      the local (session) toggle first, then the server-saved preference,
 *      then the host default. Open to EVERY user since 2026-08-25
 *      (previously a superadmin exception during the closed beta) — this
 *      powers the vertretbar⇄benger switch in the student sidebar and the
 *      expert account dropdown (useViewModeSwitch, kept in lockstep).
 *   4. Anonymous visitors: student-locked host (vertretbar.net & co) →
 *      'student'; every other host → 'expert'.
 *
 * Branding note: legal/changelog pages brand by HOST, not by mode — a
 * student switching to the expert shell on vertretbar.net keeps vertretbar
 * branding there.
 *
 * The hook subscribes to slot registrations via useSlot so a late-loading
 * extended package flips locked-host users from the expert fallback into the
 * student shell once StudentShell registers.
 */
export function useResolvedUiMode(): UiMode {
  // Subscribe to StudentShell registration so this re-resolves when the
  // extended package finishes loading (async loadExtended()).
  const studentShell = useSlot('StudentShell')
  const { user } = useAuth()
  const localMode = useUIStore((s) => s.uiMode)

  if (!isExtendedEdition()) return 'expert'
  if (!studentShell && !hasSlot('StudentShell')) return 'expert'

  const hostDefault: UiMode = isStudentLockedHost() ? 'student' : 'expert'

  // Any authenticated user's explicit switch choice (or persisted
  // preference) picks the shell on any host.
  if (user) {
    return localMode ?? user.preferred_ui_mode ?? hostDefault
  }

  return hostDefault
}
