'use client'

import { hasSlot, useSlot } from '@/lib/extensions/slots'
import { isStudentLockedHost } from '@/lib/utils/subdomain'

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
 * (vertretbar.net, behind the beta password). Precedence:
 *
 *   1. Community edition (NEXT_PUBLIC_BENGER_EDITION !== 'extended') → 'expert'.
 *      There is no student experience to render.
 *   2. Extended edition but the StudentShell slot is not registered yet (the
 *      extended package hasn't loaded, or this build doesn't ship it) →
 *      'expert'. Never show a broken/empty student shell.
 *   3. Student-locked host (vertretbar.net & co) → 'student'.
 *   4. EVERY other host — the benger benchmark platform (what-a-benger.net) —
 *      → ALWAYS 'expert'. No user, org admin, contributor, local toggle, or
 *      server-saved preference can surface the student shell there. This is a
 *      deliberate hard lock for the closed beta.
 *
 * To later re-open opt-in student mode on non-locked hosts, restore the old
 * precedence `localMode ?? user?.preferred_ui_mode ?? 'expert'` here (and the
 * useAuth()/useUIStore() reads it needs).
 *
 * The hook subscribes to slot registrations via useSlot so a late-loading
 * extended package flips locked-host users from the expert fallback into the
 * student shell once StudentShell registers.
 */
export function useResolvedUiMode(): UiMode {
  // Subscribe to StudentShell registration so this re-resolves when the
  // extended package finishes loading (async loadExtended()).
  const studentShell = useSlot('StudentShell')

  if (!isExtendedEdition()) return 'expert'
  if (!studentShell && !hasSlot('StudentShell')) return 'expert'

  // Closed beta: the student shell exists ONLY on student-locked hosts. Every
  // other host always gets the expert shell — full stop.
  if (isStudentLockedHost()) return 'student'
  return 'expert'
}
