/**
 * Utility to clear all Zustand stores and caches
 * Used during user switch to prevent data contamination
 */

import { logger } from '@/lib/utils/logger'
import { useNotificationStore } from '@/stores/notificationStore'
import { useProjectStore } from '@/stores/projectStore'
import { useUIStore } from '@/stores/uiStore'

export function clearAllStores(preserveInitialized = false) {
  logger.debug('Clearing all Zustand stores and localStorage...')

  // Note: Authentication state is managed by AuthContext and handles its own cleanup
  // This utility only clears other Zustand stores to prevent data contamination

  // Reset project store to initial state
  const projectStore = useProjectStore.getState()
  useProjectStore.setState({
    projects: [],
    currentProject: null,
    currentTask: null,
    currentTaskPosition: null,
    currentTaskTotal: null,
    loading: false,
    error: null,
    searchQuery: '',
  })

  // Clear persisted annotation store data from localStorage (legacy cleanup)
  if (typeof window !== 'undefined') {
    localStorage.removeItem('annotation-store')
  }

  // Reset notification store
  useNotificationStore.setState({
    toasts: [],
    pendingFlashes: [],
  })

  // Reset UI store (keep some UI preferences like sidebar state)
  const currentUIState = useUIStore.getState()
  useUIStore.setState({
    isSidebarHidden: currentUIState.isSidebarHidden,
    isHydrated: currentUIState.isHydrated,
    isLoginModalOpen: false,
    isSignupModalOpen: false,
    isTaskCreationModalOpen: false,
    isGlobalLoading: false,
    loadingMessage: null,
    notifications: [],
    theme: currentUIState.theme, // Keep theme preference
    isMobileMenuOpen: false,
  })

  // Clear persisted UI store data from localStorage (but preserve it since it has non-user-specific data)
  // The UI store persists theme and sidebar preferences which should remain

  // Clear any other user-specific localStorage keys
  if (typeof window !== 'undefined') {
    // Only clear session tracking keys during full logout, not during login
    if (!preserveInitialized) {
      localStorage.removeItem('benger_last_session_user')
    }

    // Clear any cached auth data
    const keysToRemove: string[] = []
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (
        key &&
        (key.includes('auth') ||
          key.includes('token') ||
          (key.includes('user') && !preserveInitialized) ||
          key.includes('session'))
      ) {
        // Skip benger_last_session_user during login to prevent loops
        if (preserveInitialized && key === 'benger_last_session_user') {
          continue
        }
        keysToRemove.push(key)
      }
    }
    keysToRemove.forEach((key) => localStorage.removeItem(key))

    // Only clear sessionStorage during full logout, not during login
    if (!preserveInitialized) {
      sessionStorage.clear()
    }
  }

  logger.debug('All stores and localStorage cleared')
}
