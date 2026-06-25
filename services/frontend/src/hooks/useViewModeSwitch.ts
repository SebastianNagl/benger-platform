'use client'

import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'

import apiSingleton from '@/lib/api'
import { useOptionalApiClient } from '@/contexts/ApiClientContext'
import { useAuth } from '@/contexts/AuthContext'
import { useHydration } from '@/contexts/HydrationContext'
import { isExtendedEdition, useResolvedUiMode } from '@/hooks/useResolvedUiMode'
import { useUIStore } from '@/stores'
import { parseSubdomain } from '@/lib/utils/subdomain'
import { canUseExpertView } from '@/utils/permissions'

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
 *  - ``'unavailable'`` — community edition, or the user can't use expert view
 *    (gating recomputed every render via canUseExpertView, never from the
 *    persisted preference). Render nothing.
 *  - ``'loading'`` — extended edition but auth/hydration not settled yet
 *    (role-flicker guard; render a neutral skeleton where one fits).
 *  - ``'ready'`` — offer the switch.
 */
export function useViewModeSwitch() {
  const router = useRouter()
  const { user, organizations, isLoading, updateUser } = useAuth()
  const apiClient = useOptionalApiClient() ?? apiSingleton
  const setUiMode = useUIStore((s) => s.setUiMode)
  const resolved = useResolvedUiMode()
  const mounted = useHydration()
  const [pending, setPending] = useState(false)

  let status: 'unavailable' | 'loading' | 'ready'
  if (!isExtendedEdition()) {
    status = 'unavailable'
  } else if (!mounted || isLoading) {
    status = 'loading'
  } else {
    const { isPrivateMode, orgSlug } = parseSubdomain()
    status = canUseExpertView(user, organizations, { isPrivateMode, orgSlug })
      ? 'ready'
      : 'unavailable'
  }

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
