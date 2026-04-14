/**
 * Fast Refresh Detection Utility
 * Helps components detect when they're being reloaded due to Fast Refresh
 * to prevent unnecessary API calls and re-initializations
 */

class FastRefreshDetector {
  private isRefreshing = false
  private lastRefreshTime = 0
  private refreshCount = 0

  constructor() {
    if (
      typeof window !== 'undefined' &&
      process.env.NODE_ENV === 'development'
    ) {
      // Hook into Fast Refresh runtime if available
      if (window.__REACT_REFRESH_RUNTIME__) {
        const originalPerformReactRefresh =
          window.__REACT_REFRESH_RUNTIME__.performReactRefresh

        window.__REACT_REFRESH_RUNTIME__.performReactRefresh = (
          ...args: any[]
        ) => {
          this.isRefreshing = true
          this.lastRefreshTime = Date.now()
          this.refreshCount++

          // Mark in session storage
          sessionStorage.setItem('fast_refresh_active', 'true')
          sessionStorage.setItem(
            'fast_refresh_time',
            this.lastRefreshTime.toString()
          )

          // Call original function
          const result = originalPerformReactRefresh.apply(
            window.__REACT_REFRESH_RUNTIME__,
            args
          )

          // Reset flag after a short delay
          setTimeout(() => {
            this.isRefreshing = false
            sessionStorage.removeItem('fast_refresh_active')
          }, 100)

          return result
        }
      }

      // Also detect webpack HMR
      if (window.__webpack_hot_middleware_client__) {
        window.__webpack_hot_middleware_client__.subscribe((event: any) => {
          if (event.action === 'building') {
            this.isRefreshing = true
            sessionStorage.setItem('fast_refresh_active', 'true')
          } else if (event.action === 'built') {
            setTimeout(() => {
              this.isRefreshing = false
              sessionStorage.removeItem('fast_refresh_active')
            }, 100)
          }
        })
      }
    }
  }

  /**
   * Check if Fast Refresh is currently active
   */
  isActive(): boolean {
    if (
      typeof window === 'undefined' ||
      process.env.NODE_ENV !== 'development'
    ) {
      return false
    }

    // Check internal state
    if (this.isRefreshing) {
      return true
    }

    // Check session storage as fallback
    const fastRefreshActive =
      sessionStorage.getItem('fast_refresh_active') === 'true'
    if (fastRefreshActive) {
      return true
    }

    // Check if we recently had a refresh (within 2 seconds)
    const lastRefreshStr = sessionStorage.getItem('fast_refresh_time')
    if (lastRefreshStr) {
      const lastRefresh = parseInt(lastRefreshStr)
      if (Date.now() - lastRefresh < 2000) {
        return true
      }
    }

    return false
  }

  /**
   * Get time since last Fast Refresh
   */
  getTimeSinceLastRefresh(): number {
    if (typeof window === 'undefined') {
      return Infinity
    }

    const lastRefreshStr = sessionStorage.getItem('fast_refresh_time')
    if (lastRefreshStr) {
      return Date.now() - parseInt(lastRefreshStr)
    }

    return this.lastRefreshTime ? Date.now() - this.lastRefreshTime : Infinity
  }

  /**
   * Mark that a component has handled Fast Refresh
   * Useful for preventing multiple components from reacting to the same refresh
   */
  markHandled(componentName: string) {
    if (typeof window !== 'undefined') {
      sessionStorage.setItem(
        `fast_refresh_handled_${componentName}`,
        Date.now().toString()
      )
    }
  }

  /**
   * Check if a component has already handled the current Fast Refresh
   */
  hasBeenHandled(componentName: string): boolean {
    if (typeof window === 'undefined') {
      return false
    }

    const handledTime = sessionStorage.getItem(
      `fast_refresh_handled_${componentName}`
    )
    if (!handledTime) {
      return false
    }

    // Consider it handled if it was marked within the last 2 seconds
    return Date.now() - parseInt(handledTime) < 2000
  }

  /**
   * Get the number of Fast Refreshes in this session
   */
  getRefreshCount(): number {
    return this.refreshCount
  }
}

// Export singleton instance
export const fastRefreshDetector = new FastRefreshDetector()

// Type declarations for global Fast Refresh objects
declare global {
  interface Window {
    __REACT_REFRESH_RUNTIME__?: {
      performReactRefresh: (...args: any[]) => any
    }
    __webpack_hot_middleware_client__?: {
      subscribe: (callback: (event: any) => void) => void
    }
  }
}
