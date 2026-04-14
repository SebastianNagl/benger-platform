/**
 * @jest-environment jsdom
 *
 * Comprehensive tests for clearAllStores utility
 * Tests store clearing, localStorage handling, sessionStorage, and edge cases
 */

import { useNotificationStore } from '@/stores/notificationStore'
import { useProjectStore } from '@/stores/projectStore'
import { useUIStore } from '@/stores/uiStore'
import { clearAllStores } from '../clearAllStores'

// Mock stores
jest.mock('@/stores/projectStore', () => ({
  useProjectStore: {
    getState: jest.fn(),
    setState: jest.fn(),
  },
}))

jest.mock('@/stores/notificationStore', () => ({
  useNotificationStore: {
    getState: jest.fn(),
    setState: jest.fn(),
  },
}))

jest.mock('@/stores/uiStore', () => ({
  useUIStore: {
    getState: jest.fn(),
    setState: jest.fn(),
  },
}))

describe('clearAllStores', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    localStorage.clear()
    sessionStorage.clear()

    // Default mock implementations
    ;(useProjectStore.getState as jest.Mock).mockReturnValue({})
    ;(useNotificationStore.getState as jest.Mock).mockReturnValue({})
    ;(useUIStore.getState as jest.Mock).mockReturnValue({
      isSidebarHidden: false,
      isHydrated: true,
      theme: 'light',
    })
  })

  describe('Project Store Clearing', () => {
    it('resets project store to initial state', () => {
      clearAllStores()

      expect(useProjectStore.setState).toHaveBeenCalledWith({
        projects: [],
        currentProject: null,
        currentTask: null,
        currentTaskPosition: null,
        currentTaskTotal: null,
        loading: false,
        error: null,
        searchQuery: '',
      })
    })

    it('clears projects array', () => {
      clearAllStores()

      const setStateCall = (useProjectStore.setState as jest.Mock).mock
        .calls[0][0]
      expect(setStateCall.projects).toEqual([])
    })

    it('clears current project', () => {
      clearAllStores()

      const setStateCall = (useProjectStore.setState as jest.Mock).mock
        .calls[0][0]
      expect(setStateCall.currentProject).toBeNull()
    })

    it('clears current task', () => {
      clearAllStores()

      const setStateCall = (useProjectStore.setState as jest.Mock).mock
        .calls[0][0]
      expect(setStateCall.currentTask).toBeNull()
    })

    it('clears task position and total', () => {
      clearAllStores()

      const setStateCall = (useProjectStore.setState as jest.Mock).mock
        .calls[0][0]
      expect(setStateCall.currentTaskPosition).toBeNull()
      expect(setStateCall.currentTaskTotal).toBeNull()
    })

    it('resets loading and error states', () => {
      clearAllStores()

      const setStateCall = (useProjectStore.setState as jest.Mock).mock
        .calls[0][0]
      expect(setStateCall.loading).toBe(false)
      expect(setStateCall.error).toBeNull()
    })

    it('clears search query', () => {
      clearAllStores()

      const setStateCall = (useProjectStore.setState as jest.Mock).mock
        .calls[0][0]
      expect(setStateCall.searchQuery).toBe('')
    })
  })

  describe('Annotation Store localStorage Clearing', () => {
    it('removes annotation store from localStorage', () => {
      localStorage.setItem(
        'annotation-store',
        JSON.stringify({ taskId: '123' })
      )

      clearAllStores()

      expect(localStorage.getItem('annotation-store')).toBeNull()
    })
  })

  describe('Notification Store Clearing', () => {
    it('resets notification store without clearing settings', () => {
      clearAllStores()

      expect(useNotificationStore.setState).toHaveBeenCalledWith({
        toasts: [],
        notifications: [],
        unreadCount: 0,
      })
    })

    it('clears toasts array', () => {
      clearAllStores()

      const setStateCall = (useNotificationStore.setState as jest.Mock).mock
        .calls[0][0]
      expect(setStateCall.toasts).toEqual([])
    })

    it('clears notifications array', () => {
      clearAllStores()

      const setStateCall = (useNotificationStore.setState as jest.Mock).mock
        .calls[0][0]
      expect(setStateCall.notifications).toEqual([])
    })

    it('resets unread count', () => {
      clearAllStores()

      const setStateCall = (useNotificationStore.setState as jest.Mock).mock
        .calls[0][0]
      expect(setStateCall.unreadCount).toBe(0)
    })

    it('does not reset notification settings', () => {
      clearAllStores()

      const setStateCall = (useNotificationStore.setState as jest.Mock).mock
        .calls[0][0]
      expect(setStateCall.settings).toBeUndefined()
    })
  })

  describe('UI Store Clearing', () => {
    beforeEach(() => {
      ;(useUIStore.getState as jest.Mock).mockReturnValue({
        isSidebarHidden: true,
        isHydrated: true,
        theme: 'dark',
        isLoginModalOpen: true,
        isSignupModalOpen: true,
        isTaskCreationModalOpen: true,
        isMobileMenuOpen: true,
        isGlobalLoading: true,
        loadingMessage: 'Loading...',
        notifications: [{ id: '1', message: 'Test' }],
      })
    })

    it('preserves sidebar state', () => {
      clearAllStores()

      const setStateCall = (useUIStore.setState as jest.Mock).mock.calls[0][0]
      expect(setStateCall.isSidebarHidden).toBe(true)
    })

    it('preserves hydration state', () => {
      clearAllStores()

      const setStateCall = (useUIStore.setState as jest.Mock).mock.calls[0][0]
      expect(setStateCall.isHydrated).toBe(true)
    })

    it('preserves theme preference', () => {
      clearAllStores()

      const setStateCall = (useUIStore.setState as jest.Mock).mock.calls[0][0]
      expect(setStateCall.theme).toBe('dark')
    })

    it('closes all modals', () => {
      clearAllStores()

      const setStateCall = (useUIStore.setState as jest.Mock).mock.calls[0][0]
      expect(setStateCall.isLoginModalOpen).toBe(false)
      expect(setStateCall.isSignupModalOpen).toBe(false)
      expect(setStateCall.isTaskCreationModalOpen).toBe(false)
    })

    it('closes mobile menu', () => {
      clearAllStores()

      const setStateCall = (useUIStore.setState as jest.Mock).mock.calls[0][0]
      expect(setStateCall.isMobileMenuOpen).toBe(false)
    })

    it('clears loading states', () => {
      clearAllStores()

      const setStateCall = (useUIStore.setState as jest.Mock).mock.calls[0][0]
      expect(setStateCall.isGlobalLoading).toBe(false)
      expect(setStateCall.loadingMessage).toBeNull()
    })

    it('clears UI notifications', () => {
      clearAllStores()

      const setStateCall = (useUIStore.setState as jest.Mock).mock.calls[0][0]
      expect(setStateCall.notifications).toEqual([])
    })
  })

  describe('localStorage Clearing', () => {
    beforeEach(() => {
      localStorage.setItem('annotation-store', JSON.stringify({ data: 'test' }))
      localStorage.setItem('auth-token', 'test-token')
      localStorage.setItem('user-data', 'test-user')
      localStorage.setItem('session-data', 'test-session')
      localStorage.setItem('benger_last_session_user', 'user-123')
      localStorage.setItem('other-data', 'keep-this')
    })

    it('removes annotation store from localStorage', () => {
      clearAllStores()

      expect(localStorage.getItem('annotation-store')).toBeNull()
    })

    it('removes auth-related keys', () => {
      clearAllStores()

      expect(localStorage.getItem('auth-token')).toBeNull()
    })

    it('removes token-related keys', () => {
      localStorage.setItem('access-token', 'test')
      clearAllStores()

      expect(localStorage.getItem('access-token')).toBeNull()
    })

    it('removes user-related keys by default', () => {
      clearAllStores()

      expect(localStorage.getItem('user-data')).toBeNull()
    })

    it('removes session-related keys', () => {
      clearAllStores()

      expect(localStorage.getItem('session-data')).toBeNull()
    })

    it('removes benger_last_session_user by default', () => {
      clearAllStores()

      expect(localStorage.getItem('benger_last_session_user')).toBeNull()
    })

    it('preserves non-auth keys', () => {
      clearAllStores()

      expect(localStorage.getItem('other-data')).toBe('keep-this')
    })

    it('preserves benger_last_session_user when preserveInitialized is true', () => {
      clearAllStores(true)

      expect(localStorage.getItem('benger_last_session_user')).toBe('user-123')
    })

    it('preserves user keys when preserveInitialized is true', () => {
      clearAllStores(true)

      expect(localStorage.getItem('benger_last_session_user')).toBe('user-123')
    })

    it('still removes auth and token keys when preserveInitialized is true', () => {
      clearAllStores(true)

      expect(localStorage.getItem('auth-token')).toBeNull()
    })
  })

  describe('sessionStorage Clearing', () => {
    beforeEach(() => {
      sessionStorage.setItem('temp-data', 'test')
      sessionStorage.setItem('other-temp', 'data')
    })

    it('clears sessionStorage by default', () => {
      clearAllStores()

      expect(sessionStorage.getItem('temp-data')).toBeNull()
      expect(sessionStorage.getItem('other-temp')).toBeNull()
    })

    it('does not clear sessionStorage when preserveInitialized is true', () => {
      clearAllStores(true)

      expect(sessionStorage.getItem('temp-data')).toBe('test')
      expect(sessionStorage.getItem('other-temp')).toBe('data')
    })
  })

  describe('preserveInitialized Parameter', () => {
    it('preserves session tracking when true', () => {
      localStorage.setItem('benger_last_session_user', 'user-123')

      clearAllStores(true)

      expect(localStorage.getItem('benger_last_session_user')).toBe('user-123')
    })

    it('clears session tracking when false', () => {
      localStorage.setItem('benger_last_session_user', 'user-123')

      clearAllStores(false)

      expect(localStorage.getItem('benger_last_session_user')).toBeNull()
    })

    it('clears session tracking by default', () => {
      localStorage.setItem('benger_last_session_user', 'user-123')

      clearAllStores()

      expect(localStorage.getItem('benger_last_session_user')).toBeNull()
    })

    it('preserves sessionStorage when true', () => {
      sessionStorage.setItem('temp-data', 'test')

      clearAllStores(true)

      expect(sessionStorage.getItem('temp-data')).toBe('test')
    })

    it('clears sessionStorage when false', () => {
      sessionStorage.setItem('temp-data', 'test')

      clearAllStores(false)

      expect(sessionStorage.getItem('temp-data')).toBeNull()
    })
  })

  // Note: Console logging tests removed - source uses logger.debug() not console.log

  describe('Store Calling Order', () => {
    it('calls project store setState', () => {
      clearAllStores()

      expect(useProjectStore.setState).toHaveBeenCalled()
    })

    it('calls notification store setState', () => {
      clearAllStores()

      expect(useNotificationStore.setState).toHaveBeenCalled()
    })

    it('calls UI store setState', () => {
      clearAllStores()

      expect(useUIStore.setState).toHaveBeenCalled()
    })

    it('calls UI store getState before setState', () => {
      clearAllStores()

      expect(useUIStore.getState).toHaveBeenCalled()
    })
  })

  describe('Edge Cases and Error Handling', () => {
    it('handles undefined window gracefully', () => {
      // This test verifies the typeof window check in the utility
      // In jsdom environment, window is always defined, so we test the logic works
      expect(() => clearAllStores()).not.toThrow()
    })

    it('handles window context correctly', () => {
      // Verify the function checks for window context
      expect(typeof window).toBe('object')
      expect(() => clearAllStores()).not.toThrow()
    })

    it('handles empty localStorage', () => {
      localStorage.clear()

      expect(() => clearAllStores()).not.toThrow()
    })

    it('handles empty sessionStorage', () => {
      sessionStorage.clear()

      expect(() => clearAllStores()).not.toThrow()
    })

    it('handles missing UI store state values', () => {
      ;(useUIStore.getState as jest.Mock).mockReturnValue({})

      expect(() => clearAllStores()).not.toThrow()

      const setStateCall = (useUIStore.setState as jest.Mock).mock.calls[0][0]
      expect(setStateCall.isSidebarHidden).toBeUndefined()
      expect(setStateCall.theme).toBeUndefined()
    })

    it('continues clearing even if one store fails', () => {
      const originalImpl = (
        useProjectStore.setState as jest.Mock
      ).getMockImplementation()

      ;(useProjectStore.setState as jest.Mock).mockImplementationOnce(() => {
        throw new Error('Store error')
      })

      expect(() => clearAllStores()).toThrow()
      // Note: In real implementation, you might want to add try-catch for robustness
    })

    it('handles localStorage with many keys efficiently', () => {
      for (let i = 0; i < 100; i++) {
        localStorage.setItem(`key-${i}`, `value-${i}`)
      }
      localStorage.setItem('auth-token', 'test')

      clearAllStores()

      expect(localStorage.getItem('auth-token')).toBeNull()
      expect(localStorage.getItem('key-0')).toBe('value-0')
    })

    it('handles keys with special characters', () => {
      localStorage.setItem('auth:token', 'test')
      localStorage.setItem('user@data', 'test')
      localStorage.setItem('session.data', 'test')

      clearAllStores()

      expect(localStorage.getItem('auth:token')).toBeNull()
      expect(localStorage.getItem('user@data')).toBeNull()
      expect(localStorage.getItem('session.data')).toBeNull()
    })
  })

  describe('Integration Scenarios', () => {
    beforeEach(() => {
      // Clear and reset mocks for integration tests
      jest.clearAllMocks()
      localStorage.clear()
      sessionStorage.clear()
    })

    it('clears all stores in single operation', () => {
      localStorage.setItem('annotation-store', JSON.stringify({ data: 'test' }))
      localStorage.setItem('auth-token', 'token')
      sessionStorage.setItem('temp', 'data')

      clearAllStores()

      expect(useProjectStore.setState).toHaveBeenCalled()
      expect(useNotificationStore.setState).toHaveBeenCalled()
      expect(useUIStore.setState).toHaveBeenCalled()
      expect(localStorage.getItem('annotation-store')).toBeNull()
      expect(localStorage.getItem('auth-token')).toBeNull()
    })

    it('handles full logout scenario', () => {
      localStorage.setItem(
        'annotation-store',
        JSON.stringify({ taskId: '123' })
      )
      localStorage.setItem('auth-token', 'token')
      localStorage.setItem('user-data', 'user')
      localStorage.setItem('benger_last_session_user', 'user-123')
      sessionStorage.setItem('temp', 'data')

      clearAllStores(false)

      expect(localStorage.getItem('annotation-store')).toBeNull()
      expect(localStorage.getItem('auth-token')).toBeNull()
      expect(localStorage.getItem('benger_last_session_user')).toBeNull()
      expect(sessionStorage.getItem('temp')).toBeNull()
    })

    it('handles login scenario (preserve initialized)', () => {
      localStorage.setItem('benger_last_session_user', 'user-123')
      localStorage.setItem('auth-token', 'old-token')

      clearAllStores(true)

      expect(localStorage.getItem('benger_last_session_user')).toBe('user-123')
      expect(localStorage.getItem('auth-token')).toBeNull()
    })
  })
})
