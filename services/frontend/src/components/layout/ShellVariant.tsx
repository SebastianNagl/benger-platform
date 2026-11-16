'use client'

import { useHydration } from '@/hooks/useHydration'
import { useUIStore } from '@/stores'
import { createContext, useContext } from 'react'
import { create } from 'zustand'

/**
 * Which flavour of the app shell (Layout: Header + sidebar) is rendering.
 *
 * - `app`: the signed-in workspace. The sidebar shows the workspace entries
 *   and its open/closed state is the user's persisted preference.
 * - `public`: the same shell for visitors (the landing page). The sidebar
 *   holds only what a visitor may open, starts collapsed on every visit and
 *   the header drops the parts that need a session (search, notifications).
 */
export type ShellVariant = 'app' | 'public'

const ShellVariantContext = createContext<ShellVariant>('app')

export const ShellVariantProvider = ShellVariantContext.Provider

export function useShellVariant(): ShellVariant {
  return useContext(ShellVariantContext)
}

export function useIsPublicShell(): boolean {
  return useShellVariant() === 'public'
}

/**
 * Open/closed state of the visitor sidebar. Deliberately not persisted and
 * separate from the signed-in preference (uiStore.isSidebarHidden): a
 * visitor always lands on the collapsed shell, and opening it here never
 * changes how the workspace sidebar looks after signing in.
 */
export const usePublicSidebarStore = create<{
  isOpen: boolean
  toggle: () => void
}>()((set) => ({
  isOpen: false,
  toggle: () => set((state) => ({ isOpen: !state.isOpen })),
}))

/**
 * Whether the desktop sidebar is shown, and how to toggle it, for the shell
 * variant in context. Before hydration the workspace sidebar is shown (to
 * avoid a layout shift for the common case) and the visitor sidebar is
 * collapsed, matching what each renders after hydration by default.
 */
export function useShellSidebar(): {
  showSidebar: boolean
  toggle: () => void
} {
  const isPublic = useIsPublicShell()
  const { isSidebarHidden, toggleSidebar } = useUIStore()
  const publicSidebar = usePublicSidebarStore()
  const isHydrated = useHydration()

  if (isPublic) {
    return { showSidebar: publicSidebar.isOpen, toggle: publicSidebar.toggle }
  }
  return {
    showSidebar: isHydrated ? !isSidebarHidden : true,
    toggle: toggleSidebar,
  }
}
