'use client'

import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'

import apiSingleton from '@/lib/api'
import { useOptionalApiClient } from '@/contexts/ApiClientContext'
import { useAuth } from '@/contexts/AuthContext'
import { useHydration } from '@/contexts/HydrationContext'
import { isExtendedEdition, useResolvedUiMode } from '@/hooks/useResolvedUiMode'
import { useUIStore } from '@/stores'

export type UiMode = 'student' | 'expert'

/**
 * Shared student⇄expert view-switch logic (issue #35).
 *
 * Centralizes the gating + the switch action so multiple surfaces can offer it
 * without duplicating the optimistic-switch / persist / navigate dance:
 *  - the account dropdown in the classic expert header (a menu item)
 *  - the student shell's sidebar control
 *
 * ``status``:
 *  - ``'unavailable'`` — community edition, OR the closed-beta lock: the student
 *    shell renders only on student-locked hosts (vertretbar.net), so the switch
 *    is never offered on the benchmark platform. Render nothing.
 *  - ``'loading'`` — extended edition but auth/hydration not settled yet
 *    (role-flicker guard; render a neutral skeleton where one fits).
 *  - ``'ready'`` — offer the switch. (Unreachable while the beta lock is in
 *    place; retained for when opt-in switching is reopened — see below.)
 */
export function useViewModeSwitch() {
  const router = useRouter()
  const { isLoading, updateUser } = useAuth()
  const apiClient = useOptionalApiClient() ?? apiSingleton
  const setUiMode = useUIStore((s) => s.setUiMode)
  const resolved = useResolvedUiMode()
  const mounted = useHydration()
  const [pending, setPending] = useState(false)

  // Declared as the full union (incl. 'ready') via an annotated IIFE so TS does
  // NOT narrow 'ready' away while the beta lock always resolves to
  // 'unavailable' — that keeps the retained switch code below (and the account
  // menu item in AuthButton, which reads this `status`) type-valid instead of
  // erroring as an impossible comparison.
  const status = ((): 'unavailable' | 'loading' | 'ready' => {
    if (!isExtendedEdition()) return 'unavailable'
    if (!mounted || isLoading) return 'loading'
    // Closed beta: the student shell renders ONLY on student-locked hosts
    // (vertretbar.net), and even there the expert⇄student toggle is not offered
    // (student-only surface). So the switch is never available while the lock is
    // in place — this matches useResolvedUiMode's hard lock and keeps the toggle
    // out of every org admin's / contributor's menu on the benchmark platform.
    // To reopen opt-in switching there, restore the isStudentLockedHost() guard +
    // `canUseExpertView(user, organizations, parseSubdomain())` gate here and
    // return 'ready'.
    return 'unavailable'
  })()

  // Warm both interface homes so the switch transition is fast — otherwise the
  // destination dashboard pays a first-load cost on click (especially under the
  // dev server's on-demand route compilation). Prefetch is idempotent/cached.
  useEffect(() => {
    if (status === 'ready') {
      router.prefetch('/student')
      router.prefetch('/dashboard')
    }
  }, [status, router])

  const switchTo = async (target: UiMode) => {
    if (target === resolved || pending) return
    // Optimistic local switch — the resolved mode is the source of truth for
    // which shell renders, so flip it first for an instant response.
    setUiMode(target)
    // Navigate to the target mode's home so the correct interface renders:
    // the /student routes always mount the student shell, the classic routes
    // the expert shell.
    router.push(target === 'student' ? '/student' : '/dashboard')
    setPending(true)
    try {
      const updated = await apiClient.setUiMode(target)
      updateUser({ preferred_ui_mode: updated?.preferred_ui_mode ?? target })
    } catch {
      // Persistence failed — keep the local override so the session still
      // honours the choice; the server just won't remember it.
    } finally {
      setPending(false)
    }
  }

  return { status, resolved, pending, switchTo }
}
