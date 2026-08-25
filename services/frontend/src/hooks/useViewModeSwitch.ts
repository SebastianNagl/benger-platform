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
 *  - ``'unavailable'`` — community edition (no student shell to switch to),
 *    or no authenticated user.
 *  - ``'loading'`` — extended edition but auth/hydration not settled yet
 *    (role-flicker guard; render a neutral skeleton where one fits).
 *  - ``'ready'`` — offer the switch. Open to EVERY authenticated user since
 *    2026-08-25 (previously superadmin-only during the closed beta): anyone
 *    may move between the vertretbar (student) and benger (expert) shells on
 *    any host, backed by the choice branch in useResolvedUiMode (kept in
 *    lockstep with this gate).
 */
export function useViewModeSwitch() {
  const router = useRouter()
  const { isLoading, updateUser, user } = useAuth()
  const apiClient = useOptionalApiClient() ?? apiSingleton
  const setUiMode = useUIStore((s) => s.setUiMode)
  const resolved = useResolvedUiMode()
  const mounted = useHydration()
  const [pending, setPending] = useState(false)

  const status = ((): 'unavailable' | 'loading' | 'ready' => {
    if (!isExtendedEdition()) return 'unavailable'
    if (!mounted || isLoading) return 'loading'
    // Open switching (2026-08-25): every authenticated user may move between
    // the vertretbar (student) and benger (expert) shells — students who
    // want the expert interface included. Kept in lockstep with the
    // choice branch in useResolvedUiMode.
    return user ? 'ready' : 'unavailable'
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
