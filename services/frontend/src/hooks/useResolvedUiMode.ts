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
 * The student shell is a CLOSED BETA — it renders ONLY on student-locked hosts
 * (vertretbar.net, behind the beta password), with a SUPERADMIN exception.
 * Precedence:
 *
 *   1. Community edition (NEXT_PUBLIC_BENGER_EDITION !== 'extended') → 'expert'.
 *      There is no student experience to render.
 *   2. Extended edition but the StudentShell slot is not registered yet (the
 *      extended package hasn't loaded, or this build doesn't ship it) →
 *      'expert'. Never show a broken/empty student shell.
 *   3. Superadmin → their switch choice wins over the host lock: the local
 *      (session) toggle first, then the server-saved preference, then the
 *      host default. This powers the vertretbar⇄benger switch offered in the
 *      student sidebar and the expert account dropdown (useViewModeSwitch
 *      gates the switch surfaces to superadmins).
 *   4. Everyone else: student-locked host (vertretbar.net & co) → 'student';
 *      EVERY other host — the benger benchmark platform (what-a-benger.net) —
 *      → ALWAYS 'expert'. No org admin, contributor, local toggle, or
 *      server-saved preference can surface the student shell there. This is a
 *      deliberate hard lock for the closed beta.
 *
 * To later re-open opt-in switching for non-superadmins, widen the gate in
 * useViewModeSwitch and the `is_superadmin` check below in lockstep.
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

  // Superadmin exception to the closed-beta lock: their explicit switch
  // choice (or persisted preference) picks the shell on any host.
  if (user?.is_superadmin) {
    return localMode ?? user.preferred_ui_mode ?? hostDefault
  }

  // Closed beta: for everyone else the student shell exists ONLY on
  // student-locked hosts. Every other host gets the expert shell — full stop.
  return hostDefault
}
