/**
 * UI State Store
 *
 * Manages global UI state including modals, notifications, loading states,
 * sidebar collapse, and other interface-related state.
 */

import { create } from 'zustand'
import { devtools, persist } from 'zustand/middleware'

export interface UIState {
  // Sidebar state
  isSidebarHidden: boolean
  isHydrated: boolean

  // Modal states
  isLoginModalOpen: boolean
  isSignupModalOpen: boolean
  isTaskCreationModalOpen: boolean

  // Loading states
  isGlobalLoading: boolean
  loadingMessage: string | null

  // Notification state
  notifications: Notification[]

  // Theme state
  theme: 'light' | 'dark' | 'system'

  // Mobile navigation
  isMobileMenuOpen: boolean
}

export interface UIActions {
  // Sidebar actions
  toggleSidebar: () => void
  hideSidebar: () => void
  showSidebar: () => void

  // Hydration action
  setHydrated: () => void

  // Modal actions
  openLoginModal: () => void
  closeLoginModal: () => void
  openSignupModal: () => void
  closeSignupModal: () => void
  openTaskCreationModal: () => void
  closeTaskCreationModal: () => void

  // Loading actions
  setGlobalLoading: (loading: boolean, message?: string) => void

  // Notification actions
  addNotification: (notification: Omit<Notification, 'id'>) => void
  removeNotification: (id: string) => void
  clearNotifications: () => void

  // Theme actions
  setTheme: (theme: 'light' | 'dark' | 'system') => void

  // Mobile navigation actions
  toggleMobileMenu: () => void
  closeMobileMenu: () => void
}

export interface Notification {
  id: string
  type: 'success' | 'error' | 'warning' | 'info'
  title: string
  message?: string
  duration?: number
  action?: {
    label: string
    onClick: () => void
  }
}

type UIStore = UIState & UIActions

const initialState: UIState = {
  isSidebarHidden: false,
  isHydrated: false,
  isLoginModalOpen: false,
  isSignupModalOpen: false,
  isTaskCreationModalOpen: false,
  isGlobalLoading: false,
  loadingMessage: null,
  notifications: [],
  theme: 'system',
  isMobileMenuOpen: false,
}

export const useUIStore = create<UIStore>()(
  devtools(
    persist(
      (set, get) => ({
        ...initialState,

        // Sidebar actions
        toggleSidebar: () =>
          set(
            (state) => ({ isSidebarHidden: !state.isSidebarHidden }),
            false,
            'toggleSidebar'
          ),

        hideSidebar: () => set({ isSidebarHidden: true }, false, 'hideSidebar'),

        showSidebar: () =>
          set({ isSidebarHidden: false }, false, 'showSidebar'),

        setHydrated: () => set({ isHydrated: true }, false, 'setHydrated'),

        // Modal actions
        openLoginModal: () =>
          set(
            { isLoginModalOpen: true, isSignupModalOpen: false },
            false,
            'openLoginModal'
          ),

        closeLoginModal: () =>
          set({ isLoginModalOpen: false }, false, 'closeLoginModal'),

        openSignupModal: () =>
          set(
            { isSignupModalOpen: true, isLoginModalOpen: false },
            false,
            'openSignupModal'
          ),

        closeSignupModal: () =>
          set({ isSignupModalOpen: false }, false, 'closeSignupModal'),

        openTaskCreationModal: () =>
          set(
            { isTaskCreationModalOpen: true },
            false,
            'openTaskCreationModal'
          ),

        closeTaskCreationModal: () =>
          set(
            { isTaskCreationModalOpen: false },
            false,
            'closeTaskCreationModal'
          ),

        // Loading actions
        setGlobalLoading: (loading: boolean, message?: string) =>
          set(
            {
              isGlobalLoading: loading,
              loadingMessage: loading ? message || null : null,
            },
            false,
            'setGlobalLoading'
          ),

        // Notification actions
        addNotification: (notification: Omit<Notification, 'id'>) => {
          const id = Math.random().toString(36).substring(2, 9)
          const newNotification: Notification = { id, ...notification }

          set(
            (state) => ({
              notifications: [...state.notifications, newNotification],
            }),
            false,
            'addNotification'
          )

          // Auto-remove notification after duration
          if (notification.duration !== 0) {
            setTimeout(() => {
              get().removeNotification(id)
            }, notification.duration || 5000)
          }
        },

        removeNotification: (id: string) =>
          set(
            (state) => ({
              notifications: state.notifications.filter((n) => n.id !== id),
            }),
            false,
            'removeNotification'
          ),

        clearNotifications: () =>
          set({ notifications: [] }, false, 'clearNotifications'),

        // Theme actions
        setTheme: (theme: 'light' | 'dark' | 'system') =>
          set({ theme }, false, 'setTheme'),

        // Mobile navigation actions
        toggleMobileMenu: () =>
          set(
            (state) => ({ isMobileMenuOpen: !state.isMobileMenuOpen }),
            false,
            'toggleMobileMenu'
          ),

        closeMobileMenu: () =>
          set({ isMobileMenuOpen: false }, false, 'closeMobileMenu'),
      }),
      {
        name: 'ui-store',
        partialize: (state) => ({
          // Persist only theme and sidebar preferences, not hydration flag
          theme: state.theme,
          isSidebarHidden: state.isSidebarHidden,
        }),
      }
    ),
    {
      name: 'ui-store',
    }
  )
)
