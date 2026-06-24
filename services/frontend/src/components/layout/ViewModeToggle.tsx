'use client'

import apiSingleton from '@/lib/api'
import { useOptionalApiClient } from '@/contexts/ApiClientContext'
import { useAuth } from '@/contexts/AuthContext'
import { useHydration } from '@/contexts/HydrationContext'
import { useI18n } from '@/contexts/I18nContext'
import { isExtendedEdition, useResolvedUiMode } from '@/hooks/useResolvedUiMode'
import { useUIStore } from '@/stores'
import { parseSubdomain } from '@/lib/utils/subdomain'
import { canUseExpertView } from '@/utils/permissions'
import { useState } from 'react'

function GraduationCapIcon(props: React.ComponentPropsWithoutRef<'svg'>) {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" {...props}>
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        d="M10 4 2.5 7.5 10 11l7.5-3.5L10 4Z"
      />
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        d="M5.5 9v3.5c0 1 2 2 4.5 2s4.5-1 4.5-2V9M17.5 7.5v3.5"
      />
    </svg>
  )
}

function ExpertIcon(props: React.ComponentPropsWithoutRef<'svg'>) {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" {...props}>
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        d="M4 5h12M4 10h12M4 15h7"
      />
    </svg>
  )
}

/**
 * Student⇄expert view-mode toggle (Issue #35, platform shell).
 *
 * Renders nothing in the community edition or for users without expert-view
 * capability (the gating is recomputed every render via canUseExpertView).
 * Switching updates the local store override immediately and persists the
 * choice server-side via PUT /api/auth/me/ui-mode.
 *
 * The actual student PAGES are provided by the extended package; this toggle
 * only flips which shell the platform renders.
 */
export function ViewModeToggle() {
  const { t } = useI18n()
  const { user, organizations, isLoading, updateUser } = useAuth()
  // Prefer the org-wired client from context; fall back to the global singleton
  // (also org-aware via the global provider) so the toggle never throws when
  // rendered outside the authenticated tree.
  const apiClient = useOptionalApiClient() ?? apiSingleton
  const setUiMode = useUIStore((s) => s.setUiMode)
  const resolved = useResolvedUiMode()
  const mounted = useHydration()
  const [pending, setPending] = useState(false)

  // Community edition never offers the student shell.
  if (!isExtendedEdition()) return null

  // Avoid leaking expert UI to a student on first paint: render nothing until
  // hydrated and auth has resolved (role-flicker guard).
  if (!mounted || isLoading) {
    return (
      <div
        className="size-6"
        aria-hidden="true"
        data-testid="view-mode-toggle-skeleton"
      />
    )
  }

  const { isPrivateMode, orgSlug } = parseSubdomain()
  if (!canUseExpertView(user, organizations, { isPrivateMode, orgSlug })) {
    return null
  }

  const target = resolved === 'student' ? 'expert' : 'student'
  const label =
    target === 'student' ? t('student.toggle.toStudent') : t('student.toggle.toExpert')

  const handleToggle = async () => {
    // Optimistic local switch — the resolved mode is the source of truth for
    // which shell renders, so flip it first for an instant response.
    setUiMode(target)
    setPending(true)
    try {
      const updated = await apiClient.setUiMode(target)
      // Keep the in-memory user in sync so a later store reset still resolves
      // to the persisted preference.
      if (updated?.preferred_ui_mode) {
        updateUser({ preferred_ui_mode: updated.preferred_ui_mode })
      } else {
        updateUser({ preferred_ui_mode: target })
      }
    } catch {
      // Persistence failed — keep the local override so the session still
      // honours the user's choice; the server simply won't remember it.
    } finally {
      setPending(false)
    }
  }

  return (
    <button
      type="button"
      onClick={handleToggle}
      disabled={pending}
      aria-label={label}
      title={label}
      data-testid="view-mode-toggle"
      data-ui-mode={resolved}
      className="flex size-6 items-center justify-center rounded-md transition hover:bg-zinc-900/5 disabled:opacity-50 dark:hover:bg-white/5"
    >
      {resolved === 'student' ? (
        <GraduationCapIcon className="h-5 w-5 stroke-zinc-900 dark:stroke-white" />
      ) : (
        <ExpertIcon className="h-5 w-5 stroke-zinc-900 dark:stroke-white" />
      )}
    </button>
  )
}
