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
 * renders). Precedence:
 *
 *   1. Community edition (NEXT_PUBLIC_BENGER_EDITION !== 'extended') → always
 *      'expert'. There is no student experience to render.
 *   2. Extended edition but the StudentShell slot is not registered (the
 *      extended package hasn't loaded yet, or this build doesn't ship it) →
 *      'expert'. Never show a broken/empty student shell.
 *   3. Otherwise → the local store override (uiMode), falling back to the
 *      server-persisted user preference (user.preferred_ui_mode), falling back
 *      to the extended default of 'student'.
 *
 * This deliberately does NOT consult permissions: the toggle's VISIBILITY is
 * gated by canUseExpertView, but once a user has chosen expert (or a server
 * default says so) we honour it. A pure student simply never sees the toggle.
 *
 * The hook subscribes to slot registrations via useSlot so a late-loading
 * extended package flips student-mode users from the expert fallback into the
 * student shell once StudentShell registers.
 */
export function useResolvedUiMode(): UiMode {
  const { user } = useAuth()
  const localMode = useUIStore((s) => s.uiMode)
  // Subscribe to StudentShell registration so this re-resolves when the
  // extended package finishes loading (async loadExtended()).
  const studentShell = useSlot('StudentShell')

  if (!isExtendedEdition()) return 'expert'
  if (!studentShell && !hasSlot('StudentShell')) return 'expert'

  // A student-locked host (e.g. vertretbar.net) only ever renders the student
  // shell — the local override / saved preference cannot escape to expert.
  if (isStudentLockedHost()) return 'student'

  return localMode ?? user?.preferred_ui_mode ?? 'student'
}
