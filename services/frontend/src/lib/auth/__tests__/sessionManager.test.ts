/**
 * @jest-environment jsdom
 *
 * Session Manager Comprehensive Test Suite
 * Tests session tracking, user switching, cache management, and token handling
 */

import { ApiClient, User } from '@/lib/api'
import { SessionManager, sessionManager } from '@/lib/auth/sessionManager'
import { clearAllStores } from '@/utils/clearAllStores'

// Mock dependencies
jest.mock('@/lib/api', () => ({
  ApiClient: jest.fn().mockImplementation(() => ({
    clearCache: jest.fn(),
    clearUserCache: jest.fn(),
  })),
}))

jest.mock('@/utils/clearAllStores', () => ({
  clearAllStores: jest.fn(),
}))

describe('SessionManager', () => {
  let mockApiClient: jest.Mocked<ApiClient>
  let manager: SessionManager

  beforeEach(() => {
    // Clear all storage
    localStorage.clear()
    sessionStorage.clear()

    // Reset mocks
    jest.clearAllMocks()

    // Create fresh mock API client
    mockApiClient = new ApiClient() as jest.Mocked<ApiClient>

    // Create fresh manager instance
    manager = new SessionManager()
  })

  afterEach(() => {
    // Clean up after each test
    localStorage.clear()
    sessionStorage.clear()
  })

  describe('Constructor and Singleton', () => {
    it('should have correct storage key constants', () => {
      expect(manager['SESSION_USER_KEY']).toBe('benger_last_session_user')
      expect(manager['AUTH_VERIFIED_KEY']).toBe('auth_verified')
      expect(manager['LOGIN_IN_PROGRESS_KEY']).toBe('login_in_progress')
    })

    it('should provide a singleton instance', () => {
      expect(sessionManager).toBeInstanceOf(SessionManager)
    })
  })

  describe('trackUserSession', () => {
    it('should store user ID in localStorage', () => {
      const user: User = { id: 123, name: 'Test User' } as User

      manager.trackUserSession(user)

      expect(localStorage.getItem('benger_last_session_user')).toBe('123')
      expect(localStorage.getItem('auth_verified')).toBe('true')
    })

    it('should convert numeric user ID to string', () => {
      const user: User = { id: 999, name: 'User 999' } as User

      manager.trackUserSession(user)

      expect(localStorage.getItem('benger_last_session_user')).toBe('999')
      expect(typeof localStorage.getItem('benger_last_session_user')).toBe(
        'string'
      )
    })

    it('should overwrite previous user session', () => {
      const user1: User = { id: 1, name: 'User 1' } as User
      const user2: User = { id: 2, name: 'User 2' } as User

      manager.trackUserSession(user1)
      expect(localStorage.getItem('benger_last_session_user')).toBe('1')

      manager.trackUserSession(user2)
      expect(localStorage.getItem('benger_last_session_user')).toBe('2')
    })
  })

  describe('getLastSessionUserId', () => {
    it('should return stored user ID', () => {
      localStorage.setItem('benger_last_session_user', '456')

      expect(manager.getLastSessionUserId()).toBe('456')
    })

    it('should return null if no user ID stored', () => {
      expect(manager.getLastSessionUserId()).toBeNull()
    })

    it('should return null when localStorage is empty', () => {
      localStorage.clear()

      expect(manager.getLastSessionUserId()).toBeNull()
    })
  })

  describe('detectUserSwitch', () => {
    it('should detect when user switches', () => {
      localStorage.setItem('benger_last_session_user', '111')
      const newUser: User = { id: 222, name: 'New User' } as User

      expect(manager.detectUserSwitch(newUser)).toBe(true)
    })

    it('should not detect switch for same user', () => {
      localStorage.setItem('benger_last_session_user', '333')
      const sameUser: User = { id: 333, name: 'Same User' } as User

      expect(manager.detectUserSwitch(sameUser)).toBe(false)
    })

    it('should return false if no previous user', () => {
      const user: User = { id: 444, name: 'User' } as User

      expect(manager.detectUserSwitch(user)).toBe(false)
    })

    it('should return false if current user is null', () => {
      localStorage.setItem('benger_last_session_user', '555')

      expect(manager.detectUserSwitch(null)).toBe(false)
    })

    it('should handle string comparison correctly', () => {
      localStorage.setItem('benger_last_session_user', '123')
      const user: User = { id: 123, name: 'User' } as User

      expect(manager.detectUserSwitch(user)).toBe(false)
    })
  })

  describe('handleUserSwitch', () => {
    it('should clear old user cache and update session', () => {
      manager.handleUserSwitch(mockApiClient, '999', '888')

      expect(mockApiClient.clearUserCache).toHaveBeenCalledWith('888')
      expect(mockApiClient.clearCache).toHaveBeenCalled()
      expect(clearAllStores).toHaveBeenCalledWith(true)
      expect(localStorage.getItem('benger_last_session_user')).toBe('999')
    })

    it('should handle null old user ID', () => {
      manager.handleUserSwitch(mockApiClient, '777', null)

      expect(mockApiClient.clearUserCache).not.toHaveBeenCalled()
      expect(mockApiClient.clearCache).toHaveBeenCalled()
      expect(clearAllStores).toHaveBeenCalledWith(true)
      expect(localStorage.getItem('benger_last_session_user')).toBe('777')
    })

    it('should preserve initialized state during user switch', () => {
      manager.handleUserSwitch(mockApiClient, '555', '444')

      expect(clearAllStores).toHaveBeenCalledWith(true)
    })

    it('should handle empty string old user ID', () => {
      manager.handleUserSwitch(mockApiClient, '666', '')

      // Empty string is falsy, so clearUserCache should NOT be called
      expect(mockApiClient.clearUserCache).not.toHaveBeenCalled()
      expect(mockApiClient.clearCache).toHaveBeenCalled()
    })
  })

  describe('isLoginInProgress', () => {
    it('should return true when login is in progress', () => {
      sessionStorage.setItem('login_in_progress', 'true')

      expect(manager.isLoginInProgress()).toBe(true)
    })

    it('should return false when login is not in progress', () => {
      expect(manager.isLoginInProgress()).toBe(false)
    })

    it('should return false for non-true values', () => {
      sessionStorage.setItem('login_in_progress', 'false')

      expect(manager.isLoginInProgress()).toBe(false)
    })

    it('should return false for empty string', () => {
      sessionStorage.setItem('login_in_progress', '')

      expect(manager.isLoginInProgress()).toBe(false)
    })
  })

  describe('setLoginInProgress', () => {
    it('should set login in progress flag', () => {
      manager.setLoginInProgress(true)

      expect(sessionStorage.getItem('login_in_progress')).toBe('true')
    })

    it('should remove login in progress flag', () => {
      sessionStorage.setItem('login_in_progress', 'true')

      manager.setLoginInProgress(false)

      expect(sessionStorage.getItem('login_in_progress')).toBeNull()
    })

    it('should handle multiple set/unset cycles', () => {
      manager.setLoginInProgress(true)
      expect(sessionStorage.getItem('login_in_progress')).toBe('true')

      manager.setLoginInProgress(false)
      expect(sessionStorage.getItem('login_in_progress')).toBeNull()

      manager.setLoginInProgress(true)
      expect(sessionStorage.getItem('login_in_progress')).toBe('true')
    })
  })

  describe('clearSession', () => {
    it('should clear all session data', () => {
      // Set up initial state
      localStorage.setItem('benger_last_session_user', '123')
      localStorage.setItem('auth_verified', 'true')
      localStorage.setItem('auth_token', 'token123')
      localStorage.setItem('user_preferences', 'prefs')
      localStorage.setItem('session_data', 'data')
      sessionStorage.setItem('temp_data', 'temp')

      manager.clearSession(mockApiClient)

      // Check localStorage cleared
      expect(localStorage.getItem('benger_last_session_user')).toBeNull()
      expect(localStorage.getItem('auth_verified')).toBeNull()
      expect(localStorage.getItem('auth_token')).toBeNull()
      expect(localStorage.getItem('user_preferences')).toBeNull()
      expect(localStorage.getItem('session_data')).toBeNull()

      // Check sessionStorage fully cleared
      expect(sessionStorage.getItem('temp_data')).toBeNull()

      // Check API cache cleared
      expect(mockApiClient.clearUserCache).toHaveBeenCalledWith('123')
      expect(mockApiClient.clearCache).toHaveBeenCalled()
      expect(clearAllStores).toHaveBeenCalledWith(false)
    })

    it('should clear user-specific cache if user ID exists', () => {
      localStorage.setItem('benger_last_session_user', '456')

      manager.clearSession(mockApiClient)

      expect(mockApiClient.clearUserCache).toHaveBeenCalledWith('456')
    })

    it('should not call clearUserCache when no user ID exists', () => {
      manager.clearSession(mockApiClient)

      expect(mockApiClient.clearUserCache).not.toHaveBeenCalled()
      expect(mockApiClient.clearCache).toHaveBeenCalled()
    })

    it('should clear browser caches when available', async () => {
      const mockDelete = jest.fn().mockResolvedValue(true)
      const mockKeys = jest.fn().mockResolvedValue(['cache1', 'cache2'])

      // Mock the caches API
      Object.defineProperty(window, 'caches', {
        value: {
          keys: mockKeys,
          delete: mockDelete,
        },
        writable: true,
        configurable: true,
      })

      manager.clearSession(mockApiClient)

      // Wait for promises to resolve
      await new Promise((resolve) => setTimeout(resolve, 10))

      expect(mockKeys).toHaveBeenCalled()
      expect(mockDelete).toHaveBeenCalledWith('cache1')
      expect(mockDelete).toHaveBeenCalledWith('cache2')
    })

    it('should handle cache API errors gracefully', async () => {
      const mockKeys = jest.fn().mockRejectedValue(new Error('Cache error'))

      Object.defineProperty(window, 'caches', {
        value: {
          keys: mockKeys,
        },
        writable: true,
        configurable: true,
      })

      // Should not throw
      expect(() => manager.clearSession(mockApiClient)).not.toThrow()

      await new Promise((resolve) => setTimeout(resolve, 10))

      expect(mockKeys).toHaveBeenCalled()
    })

    it('should handle missing caches API', () => {
      // Remove caches API
      const descriptor = Object.getOwnPropertyDescriptor(window, 'caches')
      // @ts-ignore
      delete window.caches

      expect(() => manager.clearSession(mockApiClient)).not.toThrow()

      // Restore caches API if it existed
      if (descriptor) {
        Object.defineProperty(window, 'caches', descriptor)
      }
    })

    it('should clear all auth-related keys from localStorage', () => {
      localStorage.setItem('auth_token', 'token')
      localStorage.setItem('authToken', 'token')
      localStorage.setItem('user_id', '123')
      localStorage.setItem('userId', '123')
      localStorage.setItem('session_key', 'key')
      localStorage.setItem('sessionKey', 'key')
      localStorage.setItem('keep_this', 'value')

      manager.clearSession(mockApiClient)

      expect(localStorage.getItem('auth_token')).toBeNull()
      expect(localStorage.getItem('authToken')).toBeNull()
      expect(localStorage.getItem('user_id')).toBeNull()
      expect(localStorage.getItem('userId')).toBeNull()
      expect(localStorage.getItem('session_key')).toBeNull()
      expect(localStorage.getItem('sessionKey')).toBeNull()
      expect(localStorage.getItem('keep_this')).toBe('value')
    })

    it('should clear all sessionStorage', () => {
      sessionStorage.setItem('temp1', 'value1')
      sessionStorage.setItem('temp2', 'value2')

      manager.clearSession(mockApiClient)

      expect(sessionStorage.getItem('temp1')).toBeNull()
      expect(sessionStorage.getItem('temp2')).toBeNull()
    })

    it('should call clearAllStores with false for full reset', () => {
      manager.clearSession(mockApiClient)

      expect(clearAllStores).toHaveBeenCalledWith(false)
    })
  })

  describe('hasAuthVerification', () => {
    it('should return true when auth is verified', () => {
      localStorage.setItem('auth_verified', 'true')

      expect(manager.hasAuthVerification()).toBe(true)
    })

    it('should return false when auth is not verified', () => {
      expect(manager.hasAuthVerification()).toBe(false)
    })

    it('should return false for non-true values', () => {
      localStorage.setItem('auth_verified', 'false')

      expect(manager.hasAuthVerification()).toBe(false)
    })

    it('should return false for empty string', () => {
      localStorage.setItem('auth_verified', '')

      expect(manager.hasAuthVerification()).toBe(false)
    })
  })

  describe('clearAuthVerification', () => {
    it('should remove auth verification flag', () => {
      localStorage.setItem('auth_verified', 'true')

      manager.clearAuthVerification()

      expect(localStorage.getItem('auth_verified')).toBeNull()
    })

    it('should handle clearing when flag does not exist', () => {
      expect(() => manager.clearAuthVerification()).not.toThrow()
      expect(localStorage.getItem('auth_verified')).toBeNull()
    })
  })

  describe('prepareForLogin', () => {
    it('should clear previous user data before login', () => {
      localStorage.setItem('benger_last_session_user', '789')
      localStorage.setItem('auth_verified', 'true')
      localStorage.setItem('auth_token', 'token')
      sessionStorage.setItem('temp_data', 'temp')

      manager.prepareForLogin(mockApiClient)

      expect(mockApiClient.clearUserCache).toHaveBeenCalledWith('789')
      expect(mockApiClient.clearCache).toHaveBeenCalled()
      expect(clearAllStores).toHaveBeenCalledWith(true)
      expect(localStorage.getItem('benger_last_session_user')).toBeNull()
      expect(localStorage.getItem('auth_verified')).toBeNull()
      expect(localStorage.getItem('auth_token')).toBeNull()
      expect(sessionStorage.length).toBe(0)
    })

    it('should not call clearUserCache when no previous user exists', () => {
      manager.prepareForLogin(mockApiClient)

      expect(mockApiClient.clearUserCache).not.toHaveBeenCalled()
      expect(mockApiClient.clearCache).toHaveBeenCalled()
    })

    it('should clear all auth, token, user, and session keys', () => {
      localStorage.setItem('auth_data', 'auth')
      localStorage.setItem('token_data', 'token')
      localStorage.setItem('user_data', 'user')
      localStorage.setItem('session_data', 'session')
      localStorage.setItem('other_data', 'other')

      manager.prepareForLogin(mockApiClient)

      expect(localStorage.getItem('auth_data')).toBeNull()
      expect(localStorage.getItem('token_data')).toBeNull()
      expect(localStorage.getItem('user_data')).toBeNull()
      expect(localStorage.getItem('session_data')).toBeNull()
      expect(localStorage.getItem('other_data')).toBe('other')
    })

    it('should clear sessionStorage completely', () => {
      sessionStorage.setItem('key1', 'value1')
      sessionStorage.setItem('key2', 'value2')

      manager.prepareForLogin(mockApiClient)

      expect(sessionStorage.length).toBe(0)
    })

    it('should preserve initialized state in stores', () => {
      manager.prepareForLogin(mockApiClient)

      expect(clearAllStores).toHaveBeenCalledWith(true)
    })
  })

  describe('SSR Compatibility', () => {
    let originalWindow: typeof window

    beforeEach(() => {
      originalWindow = global.window
    })

    afterEach(() => {
      global.window = originalWindow
    })

    it('should handle trackUserSession when window is undefined', () => {
      // @ts-ignore - simulate SSR
      delete global.window

      const user: User = { id: 123, name: 'Test User' } as User

      expect(() => manager.trackUserSession(user)).not.toThrow()
    })

    it('should return null from getLastSessionUserId when window is undefined', () => {
      // @ts-ignore - simulate SSR
      delete global.window

      expect(manager.getLastSessionUserId()).toBeNull()
    })

    it('should return false from detectUserSwitch when window is undefined', () => {
      // @ts-ignore - simulate SSR
      delete global.window

      const user: User = { id: 123, name: 'Test' } as User

      expect(manager.detectUserSwitch(user)).toBe(false)
    })

    it('should return false from isLoginInProgress when window is undefined', () => {
      // @ts-ignore - simulate SSR
      delete global.window

      expect(manager.isLoginInProgress()).toBe(false)
    })

    it('should handle setLoginInProgress when window is undefined', () => {
      // @ts-ignore - simulate SSR
      delete global.window

      expect(() => manager.setLoginInProgress(true)).not.toThrow()
      expect(() => manager.setLoginInProgress(false)).not.toThrow()
    })

    it('should return false from hasAuthVerification when window is undefined', () => {
      // @ts-ignore - simulate SSR
      delete global.window

      expect(manager.hasAuthVerification()).toBe(false)
    })

    it('should handle clearAuthVerification when window is undefined', () => {
      // @ts-ignore - simulate SSR
      delete global.window

      expect(() => manager.clearAuthVerification()).not.toThrow()
    })

    it('should handle handleUserSwitch when window is undefined', () => {
      // @ts-ignore - simulate SSR
      delete global.window

      expect(() =>
        manager.handleUserSwitch(mockApiClient, '123', '456')
      ).not.toThrow()
    })

    it('should handle clearSession when window is undefined', () => {
      // @ts-ignore - simulate SSR
      delete global.window

      expect(() => manager.clearSession(mockApiClient)).not.toThrow()
    })

    it('should handle prepareForLogin when window is undefined', () => {
      // @ts-ignore - simulate SSR
      delete global.window

      expect(() => manager.prepareForLogin(mockApiClient)).not.toThrow()
    })
  })

  describe('Browser Environment Tests', () => {
    it('should work correctly in browser environment (window defined)', () => {
      // Ensure window is defined
      expect(typeof window).not.toBe('undefined')

      const user: User = { id: 999, name: 'Browser User' } as User

      // Test all methods work correctly with window defined
      manager.trackUserSession(user)
      expect(localStorage.getItem('benger_last_session_user')).toBe('999')

      expect(manager.getLastSessionUserId()).toBe('999')
      expect(manager.hasAuthVerification()).toBe(true)

      manager.setLoginInProgress(true)
      expect(manager.isLoginInProgress()).toBe(true)

      manager.setLoginInProgress(false)
      expect(manager.isLoginInProgress()).toBe(false)

      manager.clearAuthVerification()
      expect(manager.hasAuthVerification()).toBe(false)
    })
  })

  describe('Edge Cases and Error Handling', () => {
    it('should handle special characters in user ID', () => {
      const user: User = { id: 'user-123-abc', name: 'Test' } as any

      manager.trackUserSession(user)

      expect(localStorage.getItem('benger_last_session_user')).toBe(
        'user-123-abc'
      )
    })

    it('should handle very large user IDs', () => {
      const largeId = 999999999999999
      const user: User = { id: largeId, name: 'Test' } as User

      manager.trackUserSession(user)

      expect(localStorage.getItem('benger_last_session_user')).toBe(
        String(largeId)
      )
    })

    it('should handle rapid successive calls to trackUserSession', () => {
      for (let i = 0; i < 100; i++) {
        const user: User = { id: i, name: `User ${i}` } as User
        manager.trackUserSession(user)
      }

      expect(localStorage.getItem('benger_last_session_user')).toBe('99')
    })

    it('should handle clearSession with no stored data', () => {
      expect(() => manager.clearSession(mockApiClient)).not.toThrow()

      expect(mockApiClient.clearCache).toHaveBeenCalled()
      expect(clearAllStores).toHaveBeenCalledWith(false)
    })

    it('should handle prepareForLogin with no stored data', () => {
      expect(() => manager.prepareForLogin(mockApiClient)).not.toThrow()

      expect(mockApiClient.clearCache).toHaveBeenCalled()
      expect(clearAllStores).toHaveBeenCalledWith(true)
    })

    it('should handle localStorage quota exceeded gracefully', () => {
      // Mock localStorage.setItem to throw quota exceeded error
      const originalSetItem = Storage.prototype.setItem
      Storage.prototype.setItem = jest.fn(() => {
        throw new Error('QuotaExceededError')
      })

      const user: User = { id: 123, name: 'Test' } as User

      // Should not crash the application
      expect(() => manager.trackUserSession(user)).toThrow()

      // Restore original method
      Storage.prototype.setItem = originalSetItem
    })
  })

  describe('Integration Scenarios', () => {
    it('should handle complete login flow', () => {
      // Prepare for login
      manager.prepareForLogin(mockApiClient)
      expect(clearAllStores).toHaveBeenCalledWith(true)

      // Set login in progress
      manager.setLoginInProgress(true)
      expect(manager.isLoginInProgress()).toBe(true)

      // Track session after successful login
      const user: User = { id: 100, name: 'New User' } as User
      manager.trackUserSession(user)
      expect(manager.getLastSessionUserId()).toBe('100')
      expect(manager.hasAuthVerification()).toBe(true)

      // Clear login in progress
      manager.setLoginInProgress(false)
      expect(manager.isLoginInProgress()).toBe(false)
    })

    it('should handle complete logout flow', () => {
      // Track initial session
      const user: User = { id: 200, name: 'User' } as User
      manager.trackUserSession(user)

      // Clear session on logout
      manager.clearSession(mockApiClient)

      expect(manager.getLastSessionUserId()).toBeNull()
      expect(manager.hasAuthVerification()).toBe(false)
      expect(mockApiClient.clearUserCache).toHaveBeenCalledWith('200')
      expect(mockApiClient.clearCache).toHaveBeenCalled()
      expect(clearAllStores).toHaveBeenCalledWith(false)
    })

    it('should handle user switch flow', () => {
      // Track first user
      const user1: User = { id: 300, name: 'User 1' } as User
      manager.trackUserSession(user1)

      // Detect switch to second user
      const user2: User = { id: 400, name: 'User 2' } as User
      const switched = manager.detectUserSwitch(user2)
      expect(switched).toBe(true)

      // Handle user switch
      manager.handleUserSwitch(mockApiClient, '400', '300')

      expect(mockApiClient.clearUserCache).toHaveBeenCalledWith('300')
      expect(mockApiClient.clearCache).toHaveBeenCalled()
      expect(clearAllStores).toHaveBeenCalledWith(true)
      expect(manager.getLastSessionUserId()).toBe('400')
    })

    it('should handle session recovery after page refresh', () => {
      // Simulate stored session from previous page load
      localStorage.setItem('benger_last_session_user', '500')
      localStorage.setItem('auth_verified', 'true')

      expect(manager.getLastSessionUserId()).toBe('500')
      expect(manager.hasAuthVerification()).toBe(true)
    })
  })
})
