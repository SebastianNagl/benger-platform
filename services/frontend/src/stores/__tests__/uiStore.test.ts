/**
 * @jest-environment jsdom
 */

import { act, renderHook } from '@testing-library/react'
import type { Notification } from '../uiStore'
import { useUIStore } from '../uiStore'

describe('UIStore', () => {
  beforeEach(() => {
    // Reset store to initial state before each test
    useUIStore.setState({
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
    })

    // Clear localStorage
    localStorage.clear()

    // Clear all timers
    jest.clearAllTimers()
  })

  afterEach(() => {
    jest.clearAllTimers()
  })

  describe('Store Initialization', () => {
    it('should initialize with default state', () => {
      const { result } = renderHook(() => useUIStore())

      expect(result.current.isSidebarHidden).toBe(false)
      expect(result.current.isHydrated).toBe(false)
      expect(result.current.isLoginModalOpen).toBe(false)
      expect(result.current.isSignupModalOpen).toBe(false)
      expect(result.current.isTaskCreationModalOpen).toBe(false)
      expect(result.current.isGlobalLoading).toBe(false)
      expect(result.current.loadingMessage).toBe(null)
      expect(result.current.notifications).toEqual([])
      expect(result.current.theme).toBe('system')
      expect(result.current.isMobileMenuOpen).toBe(false)
    })

    it('should have all required actions available', () => {
      const { result } = renderHook(() => useUIStore())

      // Sidebar actions
      expect(typeof result.current.toggleSidebar).toBe('function')
      expect(typeof result.current.hideSidebar).toBe('function')
      expect(typeof result.current.showSidebar).toBe('function')

      // Hydration action
      expect(typeof result.current.setHydrated).toBe('function')

      // Modal actions
      expect(typeof result.current.openLoginModal).toBe('function')
      expect(typeof result.current.closeLoginModal).toBe('function')
      expect(typeof result.current.openSignupModal).toBe('function')
      expect(typeof result.current.closeSignupModal).toBe('function')
      expect(typeof result.current.openTaskCreationModal).toBe('function')
      expect(typeof result.current.closeTaskCreationModal).toBe('function')

      // Loading actions
      expect(typeof result.current.setGlobalLoading).toBe('function')

      // Notification actions
      expect(typeof result.current.addNotification).toBe('function')
      expect(typeof result.current.removeNotification).toBe('function')
      expect(typeof result.current.clearNotifications).toBe('function')

      // Theme actions
      expect(typeof result.current.setTheme).toBe('function')

      // Mobile navigation actions
      expect(typeof result.current.toggleMobileMenu).toBe('function')
      expect(typeof result.current.closeMobileMenu).toBe('function')
    })
  })

  describe('Sidebar State Management', () => {
    it('should toggle sidebar visibility', () => {
      const { result } = renderHook(() => useUIStore())

      expect(result.current.isSidebarHidden).toBe(false)

      act(() => {
        result.current.toggleSidebar()
      })

      expect(result.current.isSidebarHidden).toBe(true)

      act(() => {
        result.current.toggleSidebar()
      })

      expect(result.current.isSidebarHidden).toBe(false)
    })

    it('should hide sidebar', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.hideSidebar()
      })

      expect(result.current.isSidebarHidden).toBe(true)

      // Should remain hidden when called again
      act(() => {
        result.current.hideSidebar()
      })

      expect(result.current.isSidebarHidden).toBe(true)
    })

    it('should show sidebar', () => {
      const { result } = renderHook(() => useUIStore())

      // First hide it
      act(() => {
        result.current.hideSidebar()
      })

      expect(result.current.isSidebarHidden).toBe(true)

      // Then show it
      act(() => {
        result.current.showSidebar()
      })

      expect(result.current.isSidebarHidden).toBe(false)

      // Should remain shown when called again
      act(() => {
        result.current.showSidebar()
      })

      expect(result.current.isSidebarHidden).toBe(false)
    })
  })

  describe('Hydration State Management', () => {
    it('should set hydration state', () => {
      const { result } = renderHook(() => useUIStore())

      expect(result.current.isHydrated).toBe(false)

      act(() => {
        result.current.setHydrated()
      })

      expect(result.current.isHydrated).toBe(true)
    })

    it('should remain hydrated after multiple calls', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.setHydrated()
        result.current.setHydrated()
        result.current.setHydrated()
      })

      expect(result.current.isHydrated).toBe(true)
    })
  })

  describe('Modal State Management', () => {
    describe('Login Modal', () => {
      it('should open login modal', () => {
        const { result } = renderHook(() => useUIStore())

        act(() => {
          result.current.openLoginModal()
        })

        expect(result.current.isLoginModalOpen).toBe(true)
      })

      it('should close login modal', () => {
        const { result } = renderHook(() => useUIStore())

        act(() => {
          result.current.openLoginModal()
        })

        expect(result.current.isLoginModalOpen).toBe(true)

        act(() => {
          result.current.closeLoginModal()
        })

        expect(result.current.isLoginModalOpen).toBe(false)
      })

      it('should close signup modal when opening login modal', () => {
        const { result } = renderHook(() => useUIStore())

        act(() => {
          result.current.openSignupModal()
        })

        expect(result.current.isSignupModalOpen).toBe(true)

        act(() => {
          result.current.openLoginModal()
        })

        expect(result.current.isLoginModalOpen).toBe(true)
        expect(result.current.isSignupModalOpen).toBe(false)
      })
    })

    describe('Signup Modal', () => {
      it('should open signup modal', () => {
        const { result } = renderHook(() => useUIStore())

        act(() => {
          result.current.openSignupModal()
        })

        expect(result.current.isSignupModalOpen).toBe(true)
      })

      it('should close signup modal', () => {
        const { result } = renderHook(() => useUIStore())

        act(() => {
          result.current.openSignupModal()
        })

        expect(result.current.isSignupModalOpen).toBe(true)

        act(() => {
          result.current.closeSignupModal()
        })

        expect(result.current.isSignupModalOpen).toBe(false)
      })

      it('should close login modal when opening signup modal', () => {
        const { result } = renderHook(() => useUIStore())

        act(() => {
          result.current.openLoginModal()
        })

        expect(result.current.isLoginModalOpen).toBe(true)

        act(() => {
          result.current.openSignupModal()
        })

        expect(result.current.isSignupModalOpen).toBe(true)
        expect(result.current.isLoginModalOpen).toBe(false)
      })
    })

    describe('Task Creation Modal', () => {
      it('should open task creation modal', () => {
        const { result } = renderHook(() => useUIStore())

        act(() => {
          result.current.openTaskCreationModal()
        })

        expect(result.current.isTaskCreationModalOpen).toBe(true)
      })

      it('should close task creation modal', () => {
        const { result } = renderHook(() => useUIStore())

        act(() => {
          result.current.openTaskCreationModal()
        })

        expect(result.current.isTaskCreationModalOpen).toBe(true)

        act(() => {
          result.current.closeTaskCreationModal()
        })

        expect(result.current.isTaskCreationModalOpen).toBe(false)
      })
    })

    describe('Modal Independence', () => {
      it('should allow task creation modal to be open alongside login/signup modals', () => {
        const { result } = renderHook(() => useUIStore())

        act(() => {
          result.current.openLoginModal()
          result.current.openTaskCreationModal()
        })

        expect(result.current.isLoginModalOpen).toBe(true)
        expect(result.current.isTaskCreationModalOpen).toBe(true)
      })
    })
  })

  describe('Loading State Management', () => {
    it('should set global loading state to true', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.setGlobalLoading(true)
      })

      expect(result.current.isGlobalLoading).toBe(true)
      expect(result.current.loadingMessage).toBe(null)
    })

    it('should set global loading state to false', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.setGlobalLoading(true, 'Loading...')
        result.current.setGlobalLoading(false)
      })

      expect(result.current.isGlobalLoading).toBe(false)
      expect(result.current.loadingMessage).toBe(null)
    })

    it('should set loading state with custom message', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.setGlobalLoading(true, 'Processing your request...')
      })

      expect(result.current.isGlobalLoading).toBe(true)
      expect(result.current.loadingMessage).toBe('Processing your request...')
    })

    it('should clear loading message when setting loading to false', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.setGlobalLoading(true, 'Loading data...')
      })

      expect(result.current.loadingMessage).toBe('Loading data...')

      act(() => {
        result.current.setGlobalLoading(false)
      })

      expect(result.current.isGlobalLoading).toBe(false)
      expect(result.current.loadingMessage).toBe(null)
    })

    it('should clear loading message when setting loading to false with a message', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.setGlobalLoading(true, 'Loading...')
        result.current.setGlobalLoading(false, 'This should be ignored')
      })

      expect(result.current.isGlobalLoading).toBe(false)
      expect(result.current.loadingMessage).toBe(null)
    })
  })

  describe('Notification Management', () => {
    beforeEach(() => {
      jest.useFakeTimers()
    })

    afterEach(() => {
      jest.useRealTimers()
    })

    it('should add a notification with auto-generated id', () => {
      const { result } = renderHook(() => useUIStore())

      const notification: Omit<Notification, 'id'> = {
        type: 'success',
        title: 'Success',
        message: 'Operation completed successfully',
      }

      act(() => {
        result.current.addNotification(notification)
      })

      expect(result.current.notifications).toHaveLength(1)
      expect(result.current.notifications[0]).toMatchObject({
        type: 'success',
        title: 'Success',
        message: 'Operation completed successfully',
      })
      expect(result.current.notifications[0].id).toBeDefined()
      expect(typeof result.current.notifications[0].id).toBe('string')
    })

    it('should add multiple notifications', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.addNotification({
          type: 'success',
          title: 'Success 1',
        })
        result.current.addNotification({
          type: 'error',
          title: 'Error 1',
        })
        result.current.addNotification({
          type: 'warning',
          title: 'Warning 1',
        })
      })

      expect(result.current.notifications).toHaveLength(3)
    })

    it('should add notification with action', () => {
      const { result } = renderHook(() => useUIStore())
      const mockAction = jest.fn()

      const notification: Omit<Notification, 'id'> = {
        type: 'info',
        title: 'Info',
        message: 'Click to learn more',
        action: {
          label: 'Learn More',
          onClick: mockAction,
        },
      }

      act(() => {
        result.current.addNotification(notification)
      })

      expect(result.current.notifications[0].action).toBeDefined()
      expect(result.current.notifications[0].action?.label).toBe('Learn More')
      expect(result.current.notifications[0].action?.onClick).toBe(mockAction)
    })

    it('should remove notification by id', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.addNotification({
          type: 'success',
          title: 'Success 1',
        })
        result.current.addNotification({
          type: 'error',
          title: 'Error 1',
        })
      })

      const notificationId = result.current.notifications[0].id

      act(() => {
        result.current.removeNotification(notificationId)
      })

      expect(result.current.notifications).toHaveLength(1)
      expect(result.current.notifications[0].title).toBe('Error 1')
    })

    it('should handle removing non-existent notification gracefully', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.addNotification({
          type: 'success',
          title: 'Success 1',
        })
      })

      expect(result.current.notifications).toHaveLength(1)

      act(() => {
        result.current.removeNotification('non-existent-id')
      })

      expect(result.current.notifications).toHaveLength(1)
    })

    it('should clear all notifications', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.addNotification({
          type: 'success',
          title: 'Success 1',
        })
        result.current.addNotification({
          type: 'error',
          title: 'Error 1',
        })
        result.current.addNotification({
          type: 'warning',
          title: 'Warning 1',
        })
      })

      expect(result.current.notifications).toHaveLength(3)

      act(() => {
        result.current.clearNotifications()
      })

      expect(result.current.notifications).toHaveLength(0)
    })

    it('should auto-remove notification after default duration (5000ms)', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.addNotification({
          type: 'success',
          title: 'Auto-remove',
        })
      })

      expect(result.current.notifications).toHaveLength(1)

      // Fast-forward time by 5000ms
      act(() => {
        jest.advanceTimersByTime(5000)
      })

      expect(result.current.notifications).toHaveLength(0)
    })

    it('should auto-remove notification after custom duration', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.addNotification({
          type: 'success',
          title: 'Custom duration',
          duration: 3000,
        })
      })

      expect(result.current.notifications).toHaveLength(1)

      // Fast-forward time by 2999ms (should still be there)
      act(() => {
        jest.advanceTimersByTime(2999)
      })

      expect(result.current.notifications).toHaveLength(1)

      // Fast-forward time by 1ms more (should be removed)
      act(() => {
        jest.advanceTimersByTime(1)
      })

      expect(result.current.notifications).toHaveLength(0)
    })

    it('should not auto-remove notification when duration is 0', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.addNotification({
          type: 'error',
          title: 'Persistent notification',
          duration: 0,
        })
      })

      expect(result.current.notifications).toHaveLength(1)

      // Fast-forward time by a lot
      act(() => {
        jest.advanceTimersByTime(10000)
      })

      // Should still be there
      expect(result.current.notifications).toHaveLength(1)
    })

    it('should handle multiple notifications with different durations', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.addNotification({
          type: 'success',
          title: 'Short',
          duration: 1000,
        })
        result.current.addNotification({
          type: 'warning',
          title: 'Medium',
          duration: 3000,
        })
        result.current.addNotification({
          type: 'error',
          title: 'Long',
          duration: 5000,
        })
      })

      expect(result.current.notifications).toHaveLength(3)

      // After 1000ms, first notification should be removed
      act(() => {
        jest.advanceTimersByTime(1000)
      })
      expect(result.current.notifications).toHaveLength(2)
      expect(
        result.current.notifications.find((n) => n.title === 'Short')
      ).toBeUndefined()

      // After 2000ms more (3000ms total), second notification should be removed
      act(() => {
        jest.advanceTimersByTime(2000)
      })
      expect(result.current.notifications).toHaveLength(1)
      expect(
        result.current.notifications.find((n) => n.title === 'Medium')
      ).toBeUndefined()

      // After 2000ms more (5000ms total), third notification should be removed
      act(() => {
        jest.advanceTimersByTime(2000)
      })
      expect(result.current.notifications).toHaveLength(0)
    })

    it('should generate unique ids for notifications', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.addNotification({
          type: 'success',
          title: 'Notification 1',
        })
        result.current.addNotification({
          type: 'success',
          title: 'Notification 2',
        })
        result.current.addNotification({
          type: 'success',
          title: 'Notification 3',
        })
      })

      const ids = result.current.notifications.map((n) => n.id)
      const uniqueIds = new Set(ids)

      expect(uniqueIds.size).toBe(3)
    })
  })

  describe('Theme Management', () => {
    it('should set theme to light', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.setTheme('light')
      })

      expect(result.current.theme).toBe('light')
    })

    it('should set theme to dark', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.setTheme('dark')
      })

      expect(result.current.theme).toBe('dark')
    })

    it('should set theme to system', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.setTheme('system')
      })

      expect(result.current.theme).toBe('system')
    })

    it('should switch between themes', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.setTheme('light')
      })
      expect(result.current.theme).toBe('light')

      act(() => {
        result.current.setTheme('dark')
      })
      expect(result.current.theme).toBe('dark')

      act(() => {
        result.current.setTheme('system')
      })
      expect(result.current.theme).toBe('system')
    })
  })

  describe('Mobile Navigation Management', () => {
    it('should toggle mobile menu', () => {
      const { result } = renderHook(() => useUIStore())

      expect(result.current.isMobileMenuOpen).toBe(false)

      act(() => {
        result.current.toggleMobileMenu()
      })

      expect(result.current.isMobileMenuOpen).toBe(true)

      act(() => {
        result.current.toggleMobileMenu()
      })

      expect(result.current.isMobileMenuOpen).toBe(false)
    })

    it('should close mobile menu', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.toggleMobileMenu()
      })

      expect(result.current.isMobileMenuOpen).toBe(true)

      act(() => {
        result.current.closeMobileMenu()
      })

      expect(result.current.isMobileMenuOpen).toBe(false)

      // Should remain closed when called again
      act(() => {
        result.current.closeMobileMenu()
      })

      expect(result.current.isMobileMenuOpen).toBe(false)
    })
  })

  describe('State Persistence', () => {
    it('should persist theme to localStorage', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.setTheme('dark')
      })

      // Check if localStorage was updated
      const storedData = localStorage.getItem('ui-store')
      expect(storedData).toBeDefined()

      if (storedData) {
        const parsedData = JSON.parse(storedData)
        expect(parsedData.state.theme).toBe('dark')
      }
    })

    it('should persist sidebar state to localStorage', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.hideSidebar()
      })

      // Check if localStorage was updated
      const storedData = localStorage.getItem('ui-store')
      expect(storedData).toBeDefined()

      if (storedData) {
        const parsedData = JSON.parse(storedData)
        expect(parsedData.state.isSidebarHidden).toBe(true)
      }
    })

    it('should not persist modal states', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.openLoginModal()
      })

      const storedData = localStorage.getItem('ui-store')
      if (storedData) {
        const parsedData = JSON.parse(storedData)
        expect(parsedData.state.isLoginModalOpen).toBeUndefined()
      }
    })

    it('should not persist notifications', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.addNotification({
          type: 'success',
          title: 'Test',
        })
      })

      const storedData = localStorage.getItem('ui-store')
      if (storedData) {
        const parsedData = JSON.parse(storedData)
        expect(parsedData.state.notifications).toBeUndefined()
      }
    })

    it('should not persist loading state', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.setGlobalLoading(true, 'Loading...')
      })

      const storedData = localStorage.getItem('ui-store')
      if (storedData) {
        const parsedData = JSON.parse(storedData)
        expect(parsedData.state.isGlobalLoading).toBeUndefined()
        expect(parsedData.state.loadingMessage).toBeUndefined()
      }
    })

    it('should not persist hydration flag', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.setHydrated()
      })

      const storedData = localStorage.getItem('ui-store')
      if (storedData) {
        const parsedData = JSON.parse(storedData)
        expect(parsedData.state.isHydrated).toBeUndefined()
      }
    })
  })

  describe('Edge Cases', () => {
    it('should handle rapid notification additions', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        for (let i = 0; i < 10; i++) {
          result.current.addNotification({
            type: 'info',
            title: `Notification ${i}`,
          })
        }
      })

      expect(result.current.notifications).toHaveLength(10)
    })

    it('should handle rapid sidebar toggles', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        for (let i = 0; i < 10; i++) {
          result.current.toggleSidebar()
        }
      })

      expect(result.current.isSidebarHidden).toBe(false) // Even number of toggles
    })

    it('should handle rapid modal switches', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.openLoginModal()
        result.current.openSignupModal()
        result.current.openLoginModal()
        result.current.openSignupModal()
      })

      expect(result.current.isSignupModalOpen).toBe(true)
      expect(result.current.isLoginModalOpen).toBe(false)
    })

    it('should handle rapid theme changes', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.setTheme('light')
        result.current.setTheme('dark')
        result.current.setTheme('system')
        result.current.setTheme('light')
      })

      expect(result.current.theme).toBe('light')
    })

    it('should handle notification removal during auto-removal timer', () => {
      jest.useFakeTimers()
      const { result } = renderHook(() => useUIStore())

      let notificationId: string

      act(() => {
        result.current.addNotification({
          type: 'success',
          title: 'Test',
          duration: 5000,
        })
      })

      notificationId = result.current.notifications[0].id

      // Manually remove before timer expires
      act(() => {
        result.current.removeNotification(notificationId)
      })

      expect(result.current.notifications).toHaveLength(0)

      // Advance timer to when auto-removal would have happened
      act(() => {
        jest.advanceTimersByTime(5000)
      })

      // Should still be 0, not cause any errors
      expect(result.current.notifications).toHaveLength(0)

      jest.useRealTimers()
    })

    it('should handle empty notification title', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.addNotification({
          type: 'info',
          title: '',
        })
      })

      expect(result.current.notifications).toHaveLength(1)
      expect(result.current.notifications[0].title).toBe('')
    })

    it('should handle clearing empty notification list', () => {
      const { result } = renderHook(() => useUIStore())

      expect(result.current.notifications).toHaveLength(0)

      act(() => {
        result.current.clearNotifications()
      })

      expect(result.current.notifications).toHaveLength(0)
    })
  })

  describe('Concurrent Operations', () => {
    it('should handle concurrent sidebar and modal operations', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.toggleSidebar()
        result.current.openLoginModal()
        result.current.hideSidebar()
        result.current.openSignupModal()
      })

      expect(result.current.isSidebarHidden).toBe(true)
      expect(result.current.isSignupModalOpen).toBe(true)
      expect(result.current.isLoginModalOpen).toBe(false)
    })

    it('should handle concurrent loading and notification operations', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.setGlobalLoading(true, 'Loading...')
        result.current.addNotification({
          type: 'info',
          title: 'Processing',
        })
      })

      expect(result.current.isGlobalLoading).toBe(true)
      expect(result.current.loadingMessage).toBe('Loading...')
      expect(result.current.notifications).toHaveLength(1)
    })

    it('should handle concurrent theme and mobile menu operations', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.setTheme('dark')
        result.current.toggleMobileMenu()
        result.current.setTheme('light')
        result.current.toggleMobileMenu()
      })

      expect(result.current.theme).toBe('light')
      expect(result.current.isMobileMenuOpen).toBe(false)
    })

    it('should handle all state changes simultaneously', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.toggleSidebar()
        result.current.openLoginModal()
        result.current.setGlobalLoading(true, 'Processing...')
        result.current.addNotification({
          type: 'success',
          title: 'Success',
        })
        result.current.setTheme('dark')
        result.current.toggleMobileMenu()
        result.current.setHydrated()
        result.current.openTaskCreationModal()
      })

      expect(result.current.isSidebarHidden).toBe(true)
      expect(result.current.isLoginModalOpen).toBe(true)
      expect(result.current.isGlobalLoading).toBe(true)
      expect(result.current.loadingMessage).toBe('Processing...')
      expect(result.current.notifications).toHaveLength(1)
      expect(result.current.theme).toBe('dark')
      expect(result.current.isMobileMenuOpen).toBe(true)
      expect(result.current.isHydrated).toBe(true)
      expect(result.current.isTaskCreationModalOpen).toBe(true)
    })
  })

  describe('Notification Types', () => {
    it('should handle success notification', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.addNotification({
          type: 'success',
          title: 'Success',
          message: 'Operation completed',
        })
      })

      expect(result.current.notifications[0].type).toBe('success')
    })

    it('should handle error notification', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.addNotification({
          type: 'error',
          title: 'Error',
          message: 'Something went wrong',
        })
      })

      expect(result.current.notifications[0].type).toBe('error')
    })

    it('should handle warning notification', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.addNotification({
          type: 'warning',
          title: 'Warning',
          message: 'Please be careful',
        })
      })

      expect(result.current.notifications[0].type).toBe('warning')
    })

    it('should handle info notification', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.addNotification({
          type: 'info',
          title: 'Info',
          message: 'Here is some information',
        })
      })

      expect(result.current.notifications[0].type).toBe('info')
    })
  })

  describe('State Isolation', () => {
    it('should not affect other state when changing sidebar', () => {
      const { result } = renderHook(() => useUIStore())

      act(() => {
        result.current.setHydrated()
        result.current.openLoginModal()
        result.current.setTheme('dark')
        result.current.toggleSidebar()
      })

      expect(result.current.isHydrated).toBe(true)
      expect(result.current.isLoginModalOpen).toBe(true)
      expect(result.current.theme).toBe('dark')
    })

    it('should not affect other state when managing notifications', () => {
      const { result } = renderHook(() => useUIStore())

      const initialState = {
        isSidebarHidden: result.current.isSidebarHidden,
        theme: result.current.theme,
        isLoginModalOpen: result.current.isLoginModalOpen,
      }

      act(() => {
        result.current.addNotification({
          type: 'success',
          title: 'Test',
        })
      })

      expect(result.current.isSidebarHidden).toBe(initialState.isSidebarHidden)
      expect(result.current.theme).toBe(initialState.theme)
      expect(result.current.isLoginModalOpen).toBe(
        initialState.isLoginModalOpen
      )
    })
  })
})
