'use client'

import { Menu, MenuButton, MenuItem, MenuItems } from '@headlessui/react'
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

function ChevronIcon(props: React.ComponentPropsWithoutRef<'svg'>) {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true" {...props}>
      <path
        fillRule="evenodd"
        d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.17l3.71-3.94a.75.75 0 1 1 1.08 1.04l-4.25 4.5a.75.75 0 0 1-1.08 0l-4.25-4.5a.75.75 0 0 1 .02-1.06Z"
        clipRule="evenodd"
      />
    </svg>
  )
}

function CheckIcon(props: React.ComponentPropsWithoutRef<'svg'>) {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true" {...props}>
      <path
        fillRule="evenodd"
        d="M16.7 5.3a1 1 0 0 1 0 1.4l-7.5 7.5a1 1 0 0 1-1.4 0l-3.5-3.5a1 1 0 1 1 1.4-1.4l2.8 2.79 6.8-6.79a1 1 0 0 1 1.4 0Z"
        clipRule="evenodd"
      />
    </svg>
  )
}

type UiMode = 'student' | 'expert'

/**
 * Student⇄expert view-mode dropdown (Issue #35, platform shell).
 *
 * A nav-bar dropdown to switch between the new student interface and the
 * classic expert interface. Mounted in the expert Header AND in the student
 * shell's sidebar (so users can switch back), reusing one component.
 *
 * Renders nothing in the community edition or for users without expert-view
 * capability (gating recomputed every render via canUseExpertView — a
 * persisted preference can never grant expert access). Selecting a mode flips
 * the local store override immediately (the resolved mode drives which shell
 * the platform renders) and persists via PUT /api/auth/me/ui-mode.
 *
 * `variant="sidebar"` renders a full-width trigger for the student sidebar;
 * the default suits the compact header control row.
 */
export function ViewModeToggle({
  variant = 'header',
}: {
  variant?: 'header' | 'sidebar'
}) {
  const { t } = useI18n()
  const { user, organizations, isLoading, updateUser } = useAuth()
  const apiClient = useOptionalApiClient() ?? apiSingleton
  const setUiMode = useUIStore((s) => s.setUiMode)
  const resolved = useResolvedUiMode()
  const mounted = useHydration()
  const [pending, setPending] = useState(false)

  // Community edition never offers the student shell.
  if (!isExtendedEdition()) return null

  // Role-flicker guard: render nothing meaningful until hydrated + auth resolved.
  if (!mounted || isLoading) {
    return (
      <div
        className={variant === 'sidebar' ? 'h-9 w-full' : 'size-6'}
        aria-hidden="true"
        data-testid="view-mode-toggle-skeleton"
      />
    )
  }

  const { isPrivateMode, orgSlug } = parseSubdomain()
  if (!canUseExpertView(user, organizations, { isPrivateMode, orgSlug })) {
    return null
  }

  const select = async (target: UiMode) => {
    if (target === resolved || pending) return
    // Optimistic local switch — the resolved mode is the source of truth for
    // which shell renders, so flip it first for an instant response.
    setUiMode(target)
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

  const OPTIONS: { mode: UiMode; label: string; Icon: typeof ExpertIcon }[] = [
    { mode: 'student', label: t('student.view.student'), Icon: GraduationCapIcon },
    { mode: 'expert', label: t('student.view.expert'), Icon: ExpertIcon },
  ]
  const current = OPTIONS.find((o) => o.mode === resolved) ?? OPTIONS[0]

  const triggerClass =
    variant === 'sidebar'
      ? 'flex w-full items-center gap-2 rounded-lg border border-zinc-200 px-3 py-2 text-sm font-medium text-zinc-700 transition hover:bg-zinc-900/5 disabled:opacity-50 dark:border-white/10 dark:text-zinc-200 dark:hover:bg-white/5'
      : 'flex items-center gap-1.5 rounded-md px-2 py-1 text-sm font-medium text-zinc-700 transition hover:bg-zinc-900/5 disabled:opacity-50 dark:text-zinc-200 dark:hover:bg-white/5'

  return (
    <Menu as="div" className={`relative ${variant === 'sidebar' ? 'w-full' : ''}`}>
      <MenuButton
        type="button"
        disabled={pending}
        aria-label={t('student.toggle.label')}
        title={t('student.toggle.label')}
        data-testid="view-mode-toggle"
        data-ui-mode={resolved}
        className={triggerClass}
      >
        <current.Icon className="h-5 w-5 shrink-0 stroke-zinc-900 dark:stroke-white" />
        <span className={variant === 'sidebar' ? 'flex-1 text-left' : 'hidden sm:inline'}>
          {current.label}
        </span>
        <ChevronIcon className="h-4 w-4 shrink-0 opacity-60" />
      </MenuButton>
      <MenuItems
        anchor={variant === 'sidebar' ? 'top start' : 'bottom end'}
        className="z-50 mt-1 w-56 rounded-lg border border-zinc-200 bg-white p-1 shadow-lg focus:outline-none dark:border-white/10 dark:bg-zinc-800"
      >
        {OPTIONS.map(({ mode, label, Icon }) => (
          <MenuItem key={mode}>
            <button
              type="button"
              onClick={() => select(mode)}
              data-ui-mode-option={mode}
              className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm text-zinc-700 data-[focus]:bg-zinc-900/5 dark:text-zinc-200 dark:data-[focus]:bg-white/5"
            >
              <Icon className="h-5 w-5 shrink-0 stroke-zinc-900 dark:stroke-white" />
              <span className="flex-1 text-left">{label}</span>
              {resolved === mode && (
                <CheckIcon className="h-4 w-4 shrink-0 text-emerald-500" />
              )}
            </button>
          </MenuItem>
        ))}
      </MenuItems>
    </Menu>
  )
}
