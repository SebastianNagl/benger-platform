'use client'

import { useHydration } from '@/hooks/useHydration'
import { useUIStore } from '@/stores'
import { createContext, useContext } from 'react'
import { create } from 'zustand'

/**
 * Which flavour of the app shell (Layout with its Header) is rendering.
 *
 * - `app`: the signed-in workspace. The sidebar holds the navigation, the
 *   hamburger in the top bar collapses and expands it (the user's persisted
 *   preference) and the search sits in the top bar.
 * - `public`: the same top bar for visitors (the landing page and the public
 *   pages). There is no sidebar and no hamburger: the landing sections and
 *   the public pages are items of the top bar itself, and the parts that need
 *   a session (search, notifications) are left out.
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
 * Whether the desktop sidebar is pinned open, and how to toggle it. Before
 * hydration the workspace sidebar is shown (to avoid a layout shift for the
 * common case). The visitor shell has no sidebar.
 */
export function useShellSidebar(): {
  showSidebar: boolean
  toggle: () => void
} {
  const isPublic = useIsPublicShell()
  const { isSidebarHidden, toggleSidebar } = useUIStore()
  const isHydrated = useHydration()

  if (isPublic) {
    return { showSidebar: false, toggle: () => {} }
  }
  return {
    showSidebar: isHydrated ? !isSidebarHidden : true,
    toggle: toggleSidebar,
  }
}

/** Ids that tie the hamburger and the sidebar it controls together. */
export const SIDEBAR_ID = 'app-sidebar'
export const SIDEBAR_TOGGLE_ID = 'app-sidebar-toggle'

/** How long the peeked sidebar stays after the pointer or focus left it. */
export const SIDEBAR_PEEK_HIDE_DELAY_MS = 300

let peekHideTimer: ReturnType<typeof setTimeout> | undefined

function clearPeekHideTimer() {
  if (peekHideTimer !== undefined) {
    clearTimeout(peekHideTimer)
    peekHideTimer = undefined
  }
}

/**
 * The collapsed sidebar shown as an overlay ("peek"), the way Notion does it:
 * pointing at the hamburger, or moving keyboard focus into the sidebar,
 * slides it in above the page without moving the content; it hides again
 * shortly after the pointer or focus leaves both. It never changes the
 * persisted open/closed preference; clicking the hamburger still pins it.
 */
export const useSidebarPeekStore = create<{
  isPeeking: boolean
  /** Show the overlay now (cancels a pending hide). */
  show: () => void
  /** Hide the overlay after SIDEBAR_PEEK_HIDE_DELAY_MS unless shown again. */
  hideSoon: () => void
  /** Hide the overlay now. */
  hide: () => void
}>()((set) => ({
  isPeeking: false,
  show: () => {
    clearPeekHideTimer()
    set({ isPeeking: true })
  },
  hideSoon: () => {
    clearPeekHideTimer()
    peekHideTimer = setTimeout(() => {
      peekHideTimer = undefined
      set({ isPeeking: false })
    }, SIDEBAR_PEEK_HIDE_DELAY_MS)
  },
  hide: () => {
    clearPeekHideTimer()
    set({ isPeeking: false })
  },
}))

/**
 * Pointer events that may peek the sidebar: a mouse or pen hovering. A touch
 * has no hover; a tap on the hamburger pins the sidebar instead.
 */
export function isHoverPointer(event: { pointerType?: string }): boolean {
  return event.pointerType === 'mouse' || event.pointerType === 'pen'
}
