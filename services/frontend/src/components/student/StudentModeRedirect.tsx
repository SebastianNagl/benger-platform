'use client'

import { useAuth } from '@/contexts/AuthContext'
import { useHydration } from '@/hooks/useHydration'
import {
  isExtendedEdition,
  useResolvedUiMode,
  type UiMode,
} from '@/hooks/useResolvedUiMode'
import { useSlot } from '@/lib/extensions/slots'
import { isStudentLockedHost } from '@/lib/utils/subdomain'
import { useUIStore } from '@/stores'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect } from 'react'

/** One-shot UI mode an LMS (LTI) launch asks for. */
export const LTI_UI_PARAM = 'lti_ui'
/** Query params only LMS launch redirects carry. */
const LTI_LANDING_PARAMS = ['lti_u', 'rl']

/**
 * The UI mode an LMS launch asks for on this page load, or null.
 *
 * Only honoured together with an LMS landing param (`lti_u` or `rl`), so a
 * stray `?lti_ui=` on any other link does nothing.
 */
function readLtiUiMode(): UiMode | null {
  if (typeof window === 'undefined') return null
  const params = new URLSearchParams(window.location.search)
  const mode = params.get(LTI_UI_PARAM)
  if (mode !== 'student' && mode !== 'expert') return null
  if (!LTI_LANDING_PARAMS.some((key) => params.has(key))) return null
  return mode
}

/** Drop `lti_ui` from the address bar, keeping every other param. */
function stripLtiUiParam(): void {
  const params = new URLSearchParams(window.location.search)
  params.delete(LTI_UI_PARAM)
  const search = params.toString()
  window.history.replaceState(
    null,
    '',
    window.location.pathname +
      (search ? `?${search}` : '') +
      window.location.hash,
  )
}

/**
 * Keeps each user on the surface that matches their resolved UI mode (Issue #35).
 *
 * - student mode → the expert landing surfaces (`/`, `/dashboard`) are pulled
 *   into the student home (`/student`).
 * - expert mode → the `/student/*` surface is a CLOSED BETA and unreachable
 *   here (it only renders on student-locked hosts like vertretbar.net). Any
 *   navigation onto a `/student` route is bounced back to `/dashboard`, so an
 *   org admin/contributor can't land on the student pages via the view toggle
 *   or a direct URL.
 *
 * LMS launches: the redirect after an LTI launch carries a one-shot
 * `lti_ui=student|expert` next to `lti_u`/`rl`. It sets the local view mode
 * (like the view switch, never saved to the server) and decides this run's
 * bounce, so an LMS student is not sent from `/student/exams/…` to the
 * dashboard by a stale expert choice and an LMS teacher on the main host
 * lands in the expert shell. Student-locked hosts honour only `student`:
 * everyone there uses the student UI. The param is removed from the address
 * bar once handled; while the extended package (the student shell) is still
 * loading it stays, so the choice is not lost.
 *
 * It keys exclusively on the resolved UI mode — there is intentionally NO
 * profile-completion gate. Renders nothing.
 */
export function StudentModeRedirect() {
  const pathname = usePathname()
  const router = useRouter()
  const { user, isLoading } = useAuth()
  const isHydrated = useHydration()
  const resolvedUiMode = useResolvedUiMode()
  const studentShellReady = Boolean(useSlot('StudentShell'))
  const setUiMode = useUIStore((s) => s.setUiMode)
  // Only presence matters here — a logged-out visitor has no view mode to
  // honour and must not be bounced off the public landing page.
  const isAuthenticated = !!user

  useEffect(() => {
    if (!isHydrated || isLoading) return
    if (!isAuthenticated) return
    if (!pathname) return

    let effectiveMode = resolvedUiMode
    const ltiMode = readLtiUiMode()
    if (ltiMode) {
      if (isExtendedEdition() && !studentShellReady) {
        // The extended package is still loading: decide once the student
        // shell is registered (this effect runs again then).
        return
      }
      // The student shell exists only in the extended edition; elsewhere
      // there is nothing to switch to. On a student-locked host everyone
      // uses the student UI, so only `student` counts there.
      const canSwitch =
        isExtendedEdition() && (!isStudentLockedHost() || ltiMode === 'student')
      if (canSwitch) {
        effectiveMode = ltiMode
        if (useUIStore.getState().uiMode !== ltiMode) setUiMode(ltiMode)
      }
      stripLtiUiParam()
    }

    const onStudentRoute =
      pathname === '/student' || pathname.startsWith('/student/')

    if (effectiveMode === 'student') {
      if (pathname === '/' || pathname === '/dashboard') {
        router.replace('/student')
      }
    } else if (onStudentRoute) {
      // Closed beta: expert-mode users (i.e. everyone off a student-locked host)
      // must never sit on the student surface. Bounce back to the classic home.
      router.replace('/dashboard')
    }
  }, [
    isHydrated,
    isLoading,
    isAuthenticated,
    resolvedUiMode,
    studentShellReady,
    pathname,
    router,
    setUiMode,
  ])

  return null
}
