/**
 * Session Management Service
 *
 * Handles session tracking, user switching detection, and cache invalidation.
 * Extracted from AuthContext to separate concerns.
 */

import { ApiClient, User } from '@/lib/api'
import { logger } from '@/lib/utils/logger'
import { clearAllStores } from '@/utils/clearAllStores'

export class SessionManager {
  private readonly SESSION_USER_KEY = 'benger_last_session_user'
  private readonly AUTH_VERIFIED_KEY = 'auth_verified'
  private readonly LOGIN_IN_PROGRESS_KEY = 'login_in_progress'

  /**
   * Track the current user session
   */
  trackUserSession(user: User): void {
    if (typeof window !== 'undefined') {
      localStorage.setItem(this.SESSION_USER_KEY, String(user.id))
      localStorage.setItem(this.AUTH_VERIFIED_KEY, 'true')
    }
  }

  /**
   * Get the last session user ID
   */
  getLastSessionUserId(): string | null {
    if (typeof window === 'undefined') return null
    return localStorage.getItem(this.SESSION_USER_KEY)
  }

  /**
   * Check if we have a different user than last session
   */
  detectUserSwitch(currentUser: User | null): boolean {
    if (!currentUser || typeof window === 'undefined') return false

    const lastSessionUser = this.getLastSessionUserId()

    if (lastSessionUser && lastSessionUser !== String(currentUser.id)) {
      logger.debug(
        `User switch detected (was: ${lastSessionUser}, now: ${currentUser.id})`
      )
      return true
    }

    return false
  }

  /**
   * Handle user switch - clear old user data
   */
  handleUserSwitch(
    apiClient: ApiClient,
    newUserId: string,
    oldUserId: string | null
  ): void {
    // Clear the previous user's cached data
    if (oldUserId) {
      apiClient.clearUserCache(oldUserId)
    }

    // Clear all API cache
    apiClient.clearCache()

    // Clear all stores but preserve initialized state
    clearAllStores(true)

    // Update session tracking
    if (typeof window !== 'undefined') {
      localStorage.setItem(this.SESSION_USER_KEY, newUserId)
    }
  }

  /**
   * Check if login is in progress (prevents race conditions)
   */
  isLoginInProgress(): boolean {
    if (typeof window === 'undefined') return false
    return sessionStorage.getItem(this.LOGIN_IN_PROGRESS_KEY) === 'true'
  }

  /**
   * Set login in progress flag
   */
  setLoginInProgress(inProgress: boolean): void {
    if (typeof window !== 'undefined') {
      if (inProgress) {
        sessionStorage.setItem(this.LOGIN_IN_PROGRESS_KEY, 'true')
      } else {
        sessionStorage.removeItem(this.LOGIN_IN_PROGRESS_KEY)
      }
    }
  }

  /**
   * Clear session data on logout
   */
  clearSession(apiClient: ApiClient): void {
    const currentUserId = this.getLastSessionUserId()

    // Clear user-specific cache if we have a user ID
    if (currentUserId) {
      apiClient.clearUserCache(currentUserId)
    }

    // Clear all API response cache
    apiClient.clearCache()

    // Force clear any browser-level caches
    if (typeof window !== 'undefined' && 'caches' in window) {
      caches
        .keys()
        .then((names: string[]) => {
          names.forEach((name: string) => caches.delete(name))
        })
        .catch(() => {})
    }

    // Clear all Zustand stores (full reset on logout)
    clearAllStores(false)

    // Clear session tracking
    if (typeof window !== 'undefined') {
      localStorage.removeItem(this.SESSION_USER_KEY)
      localStorage.removeItem(this.AUTH_VERIFIED_KEY)

      // Clear any other auth-related keys
      const keysToRemove = Object.keys(localStorage).filter(
        (key) =>
          key.includes('auth') ||
          key.includes('user') ||
          key.includes('session')
      )
      keysToRemove.forEach((key) => localStorage.removeItem(key))

      sessionStorage.clear()
    }
  }

  /**
   * Check if we have auth verification
   */
  hasAuthVerification(): boolean {
    if (typeof window === 'undefined') return false
    return localStorage.getItem(this.AUTH_VERIFIED_KEY) === 'true'
  }

  /**
   * Clear auth verification
   */
  clearAuthVerification(): void {
    if (typeof window !== 'undefined') {
      localStorage.removeItem(this.AUTH_VERIFIED_KEY)
    }
  }

  /**
   * Prepare for login - clear old data
   */
  prepareForLogin(apiClient: ApiClient): void {
    const previousUserId = this.getLastSessionUserId()

    // Clear previous user's cache if exists
    if (previousUserId) {
      apiClient.clearUserCache(previousUserId)
    }

    // Clear all Zustand stores but preserve isInitialized
    clearAllStores(true)

    // Clear the session user key before login
    if (typeof window !== 'undefined') {
      localStorage.removeItem(this.SESSION_USER_KEY)

      // Clear all auth-related keys
      const keysToRemove = Object.keys(localStorage).filter(
        (key) =>
          key.includes('auth') ||
          key.includes('token') ||
          key.includes('user') ||
          key.includes('session')
      )
      keysToRemove.forEach((key) => localStorage.removeItem(key))
      sessionStorage.clear()
    }

    // Clear all API response cache
    apiClient.clearCache()
  }
}

// Export singleton instance
export const sessionManager = new SessionManager()
