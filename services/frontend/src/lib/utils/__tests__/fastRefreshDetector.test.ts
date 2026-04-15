/**
 * @jest-environment jsdom
 *
 * FastRefreshDetector Comprehensive Test Suite
 * Tests Fast Refresh detection, webpack HMR integration, and component tracking
 */

import { fastRefreshDetector } from '@/lib/utils/fastRefreshDetector'

describe('FastRefreshDetector', () => {
  const originalEnv = process.env

  beforeEach(() => {
    sessionStorage.clear()
    jest.clearAllMocks()
    process.env = { ...originalEnv, NODE_ENV: 'development' }

    // Clean up window globals
    delete (window as any).__REACT_REFRESH_RUNTIME__
    delete (window as any).__webpack_hot_middleware_client__
  })

  afterEach(() => {
    process.env = originalEnv
    sessionStorage.clear()
    delete (window as any).__REACT_REFRESH_RUNTIME__
    delete (window as any).__webpack_hot_middleware_client__
  })

  describe('Constructor initialization', () => {
    it('should not initialize hooks in production', () => {
      process.env.NODE_ENV = 'production'
      const mockPerformRefresh = jest.fn()

      ;(window as any).__REACT_REFRESH_RUNTIME__ = {
        performReactRefresh: mockPerformRefresh,
      }

      jest.isolateModules(() => {
        require('@/lib/utils/fastRefreshDetector')
      })

      expect(
        (window as any).__REACT_REFRESH_RUNTIME__.performReactRefresh
      ).toBe(mockPerformRefresh)
    })

    it('should hook into React Refresh runtime in development', () => {
      process.env.NODE_ENV = 'development'
      const mockPerformRefresh = jest.fn((arg: any) => arg)

      ;(window as any).__REACT_REFRESH_RUNTIME__ = {
        performReactRefresh: mockPerformRefresh,
      }

      jest.isolateModules(() => {
        require('@/lib/utils/fastRefreshDetector')
      })

      expect(
        (window as any).__REACT_REFRESH_RUNTIME__.performReactRefresh
      ).not.toBe(mockPerformRefresh)
      expect(
        typeof (window as any).__REACT_REFRESH_RUNTIME__.performReactRefresh
      ).toBe('function')
    })

    it('should hook into webpack HMR in development', () => {
      process.env.NODE_ENV = 'development'
      const subscribeMock = jest.fn()

      ;(window as any).__webpack_hot_middleware_client__ = {
        subscribe: subscribeMock,
      }

      jest.isolateModules(() => {
        require('@/lib/utils/fastRefreshDetector')
      })

      expect(subscribeMock).toHaveBeenCalledWith(expect.any(Function))
    })

    it('should not throw if no refresh runtime exists', () => {
      process.env.NODE_ENV = 'development'

      expect(() => {
        jest.isolateModules(() => {
          require('@/lib/utils/fastRefreshDetector')
        })
      }).not.toThrow()
    })
  })

  describe('isActive', () => {
    it('should return false in production environment', () => {
      process.env.NODE_ENV = 'production'
      expect(fastRefreshDetector.isActive()).toBe(false)
    })

    it('should return false on server-side', () => {
      const originalWindow = global.window
      delete (global as any).window

      expect(fastRefreshDetector.isActive()).toBe(false)

      global.window = originalWindow
    })

    it('should return false when no refresh is active', () => {
      process.env.NODE_ENV = 'development'
      expect(fastRefreshDetector.isActive()).toBe(false)
    })

    it('should return true when fast_refresh_active flag is set', () => {
      process.env.NODE_ENV = 'development'
      sessionStorage.setItem('fast_refresh_active', 'true')

      expect(fastRefreshDetector.isActive()).toBe(true)
    })

    it('should return false when fast_refresh_active is not "true"', () => {
      process.env.NODE_ENV = 'development'
      sessionStorage.setItem('fast_refresh_active', 'false')

      expect(fastRefreshDetector.isActive()).toBe(false)
    })

    it('should return true when refresh occurred within 2 seconds', () => {
      process.env.NODE_ENV = 'development'
      const recentTime = Date.now() - 1000
      sessionStorage.setItem('fast_refresh_time', String(recentTime))

      expect(fastRefreshDetector.isActive()).toBe(true)
    })

    it('should return false when refresh occurred more than 2 seconds ago', () => {
      process.env.NODE_ENV = 'development'
      const oldTime = Date.now() - 3000
      sessionStorage.setItem('fast_refresh_time', String(oldTime))

      expect(fastRefreshDetector.isActive()).toBe(false)
    })

    it('should prioritize fast_refresh_active flag', () => {
      process.env.NODE_ENV = 'development'
      const oldTime = Date.now() - 3000
      sessionStorage.setItem('fast_refresh_time', String(oldTime))
      sessionStorage.setItem('fast_refresh_active', 'true')

      expect(fastRefreshDetector.isActive()).toBe(true)
    })
  })

  describe('getTimeSinceLastRefresh', () => {
    it('should return Infinity on server-side', () => {
      const originalWindow = global.window
      delete (global as any).window

      expect(fastRefreshDetector.getTimeSinceLastRefresh()).toBe(Infinity)

      global.window = originalWindow
    })

    it('should return Infinity when no refresh has occurred', () => {
      expect(fastRefreshDetector.getTimeSinceLastRefresh()).toBe(Infinity)
    })

    it('should calculate time since refresh from session storage', () => {
      const refreshTime = Date.now() - 5000
      sessionStorage.setItem('fast_refresh_time', String(refreshTime))

      const timeSince = fastRefreshDetector.getTimeSinceLastRefresh()

      expect(timeSince).toBeGreaterThanOrEqual(5000)
      expect(timeSince).toBeLessThan(6000)
    })

    it('should handle invalid timestamp in session storage', () => {
      sessionStorage.setItem('fast_refresh_time', 'invalid')

      const timeSince = fastRefreshDetector.getTimeSinceLastRefresh()

      expect(isNaN(timeSince)).toBe(true)
    })
  })

  describe('markHandled', () => {
    it('should store component handling timestamp', () => {
      const beforeTime = Date.now()
      fastRefreshDetector.markHandled('TestComponent')
      const afterTime = Date.now()

      const handledTime = sessionStorage.getItem(
        'fast_refresh_handled_TestComponent'
      )
      expect(handledTime).toBeTruthy()

      const timestamp = parseInt(handledTime!)
      expect(timestamp).toBeGreaterThanOrEqual(beforeTime)
      expect(timestamp).toBeLessThanOrEqual(afterTime)
    })

    it('should handle different component names', () => {
      fastRefreshDetector.markHandled('Component1')
      fastRefreshDetector.markHandled('Component2')

      expect(
        sessionStorage.getItem('fast_refresh_handled_Component1')
      ).toBeTruthy()
      expect(
        sessionStorage.getItem('fast_refresh_handled_Component2')
      ).toBeTruthy()
    })

    it('should handle server-side gracefully', () => {
      const originalWindow = global.window
      delete (global as any).window

      expect(() =>
        fastRefreshDetector.markHandled('TestComponent')
      ).not.toThrow()

      global.window = originalWindow
    })
  })

  describe('hasBeenHandled', () => {
    it('should return false on server-side', () => {
      const originalWindow = global.window
      delete (global as any).window

      expect(fastRefreshDetector.hasBeenHandled('TestComponent')).toBe(false)

      global.window = originalWindow
    })

    it('should return false when component has not been handled', () => {
      expect(fastRefreshDetector.hasBeenHandled('TestComponent')).toBe(false)
    })

    it('should return true when component was handled recently (< 2s)', () => {
      const recentTime = Date.now() - 1000
      sessionStorage.setItem(
        'fast_refresh_handled_TestComponent',
        String(recentTime)
      )

      expect(fastRefreshDetector.hasBeenHandled('TestComponent')).toBe(true)
    })

    it('should return false when component was handled long ago (>= 2s)', () => {
      const oldTime = Date.now() - 3000
      sessionStorage.setItem(
        'fast_refresh_handled_TestComponent',
        String(oldTime)
      )

      expect(fastRefreshDetector.hasBeenHandled('TestComponent')).toBe(false)
    })

    it('should handle different component names independently', () => {
      const recentTime = Date.now() - 1000
      sessionStorage.setItem(
        'fast_refresh_handled_Component1',
        String(recentTime)
      )

      expect(fastRefreshDetector.hasBeenHandled('Component1')).toBe(true)
      expect(fastRefreshDetector.hasBeenHandled('Component2')).toBe(false)
    })

    it('should handle invalid timestamp', () => {
      sessionStorage.setItem('fast_refresh_handled_TestComponent', 'invalid')

      expect(fastRefreshDetector.hasBeenHandled('TestComponent')).toBe(false)
    })
  })

  describe('getRefreshCount', () => {
    it('should return 0 initially', () => {
      expect(fastRefreshDetector.getRefreshCount()).toBe(0)
    })
  })

  describe('React Refresh integration', () => {
    beforeEach(() => {
      process.env.NODE_ENV = 'development'
      jest.useFakeTimers()
    })

    afterEach(() => {
      jest.useRealTimers()
    })

    it('should track refresh when performReactRefresh is called', () => {
      const mockPerformRefresh = jest.fn()
      ;(window as any).__REACT_REFRESH_RUNTIME__ = {
        performReactRefresh: mockPerformRefresh,
      }

      jest.isolateModules(() => {
        require('@/lib/utils/fastRefreshDetector')
      })

      const hookedFunction = (window as any).__REACT_REFRESH_RUNTIME__
        .performReactRefresh

      hookedFunction()

      expect(sessionStorage.getItem('fast_refresh_active')).toBe('true')
      expect(sessionStorage.getItem('fast_refresh_time')).toBeTruthy()

      jest.advanceTimersByTime(150)

      expect(sessionStorage.getItem('fast_refresh_active')).toBeNull()
    })

    it('should call original performReactRefresh function', () => {
      const mockPerformRefresh = jest.fn((arg: any) => `result_${arg}`)
      ;(window as any).__REACT_REFRESH_RUNTIME__ = {
        performReactRefresh: mockPerformRefresh,
      }

      jest.isolateModules(() => {
        require('@/lib/utils/fastRefreshDetector')
      })

      const hookedFunction = (window as any).__REACT_REFRESH_RUNTIME__
        .performReactRefresh

      const result = hookedFunction('test_arg')

      expect(mockPerformRefresh).toHaveBeenCalledWith('test_arg')
      expect(result).toBe('result_test_arg')
    })

    it('should preserve this context in hooked function', () => {
      let capturedThis: any
      const mockPerformRefresh = function (this: any) {
        capturedThis = this
        return 'result'
      }

      ;(window as any).__REACT_REFRESH_RUNTIME__ = {
        performReactRefresh: mockPerformRefresh,
      }

      jest.isolateModules(() => {
        require('@/lib/utils/fastRefreshDetector')
      })

      const hookedFunction = (window as any).__REACT_REFRESH_RUNTIME__
        .performReactRefresh

      hookedFunction.call('custom_context')

      expect(capturedThis).toBe((window as any).__REACT_REFRESH_RUNTIME__)
    })
  })

  describe('Webpack HMR integration', () => {
    beforeEach(() => {
      process.env.NODE_ENV = 'development'
      jest.useFakeTimers()
    })

    afterEach(() => {
      jest.useRealTimers()
    })

    it('should track refresh on webpack building event', () => {
      let subscribedCallback: ((event: any) => void) | null = null
      const subscribeMock = jest.fn((cb: (event: any) => void) => {
        subscribedCallback = cb
      })

      ;(window as any).__webpack_hot_middleware_client__ = {
        subscribe: subscribeMock,
      }

      jest.isolateModules(() => {
        require('@/lib/utils/fastRefreshDetector')
      })

      expect(subscribedCallback).toBeTruthy()

      subscribedCallback!({ action: 'building' })

      expect(sessionStorage.getItem('fast_refresh_active')).toBe('true')
    })

    it('should clear refresh flag on webpack built event', () => {
      let subscribedCallback: ((event: any) => void) | null = null
      const subscribeMock = jest.fn((cb: (event: any) => void) => {
        subscribedCallback = cb
      })

      ;(window as any).__webpack_hot_middleware_client__ = {
        subscribe: subscribeMock,
      }

      jest.isolateModules(() => {
        require('@/lib/utils/fastRefreshDetector')
      })

      subscribedCallback!({ action: 'building' })
      expect(sessionStorage.getItem('fast_refresh_active')).toBe('true')

      subscribedCallback!({ action: 'built' })
      jest.advanceTimersByTime(150)

      expect(sessionStorage.getItem('fast_refresh_active')).toBeNull()
    })

    it('should ignore unknown webpack events', () => {
      let subscribedCallback: ((event: any) => void) | null = null
      const subscribeMock = jest.fn((cb: (event: any) => void) => {
        subscribedCallback = cb
      })

      ;(window as any).__webpack_hot_middleware_client__ = {
        subscribe: subscribeMock,
      }

      jest.isolateModules(() => {
        require('@/lib/utils/fastRefreshDetector')
      })

      subscribedCallback!({ action: 'unknown' })

      expect(sessionStorage.getItem('fast_refresh_active')).toBeNull()
    })
  })

  describe('Integration scenarios', () => {
    beforeEach(() => {
      process.env.NODE_ENV = 'development'
    })

    it('should handle complete refresh lifecycle', () => {
      jest.useFakeTimers()

      sessionStorage.setItem('fast_refresh_time', String(Date.now()))
      sessionStorage.setItem('fast_refresh_active', 'true')

      expect(fastRefreshDetector.isActive()).toBe(true)
      expect(fastRefreshDetector.hasBeenHandled('TestComponent')).toBe(false)

      fastRefreshDetector.markHandled('TestComponent')
      expect(fastRefreshDetector.hasBeenHandled('TestComponent')).toBe(true)

      jest.advanceTimersByTime(2500)

      expect(fastRefreshDetector.hasBeenHandled('TestComponent')).toBe(false)

      jest.useRealTimers()
    })

    it('should handle multiple components tracking refresh', () => {
      fastRefreshDetector.markHandled('Component1')
      fastRefreshDetector.markHandled('Component2')
      fastRefreshDetector.markHandled('Component3')

      expect(fastRefreshDetector.hasBeenHandled('Component1')).toBe(true)
      expect(fastRefreshDetector.hasBeenHandled('Component2')).toBe(true)
      expect(fastRefreshDetector.hasBeenHandled('Component3')).toBe(true)
    })

    it('should correctly report time since refresh', () => {
      jest.useFakeTimers()
      const startTime = Date.now()

      sessionStorage.setItem('fast_refresh_time', String(startTime))

      jest.advanceTimersByTime(3000)

      const timeSince = fastRefreshDetector.getTimeSinceLastRefresh()
      expect(timeSince).toBeGreaterThanOrEqual(3000)

      jest.useRealTimers()
    })
  })

  describe('Edge cases', () => {
    it('should handle session storage being cleared externally', () => {
      process.env.NODE_ENV = 'development'

      fastRefreshDetector.markHandled('TestComponent')
      expect(fastRefreshDetector.hasBeenHandled('TestComponent')).toBe(true)

      sessionStorage.clear()

      expect(fastRefreshDetector.hasBeenHandled('TestComponent')).toBe(false)
      expect(fastRefreshDetector.isActive()).toBe(false)
    })

    it('should handle rapid successive refreshes', () => {
      jest.useFakeTimers()

      const mockPerformRefresh = jest.fn()
      ;(window as any).__REACT_REFRESH_RUNTIME__ = {
        performReactRefresh: mockPerformRefresh,
      }

      jest.isolateModules(() => {
        require('@/lib/utils/fastRefreshDetector')
      })

      const hookedFunction = (window as any).__REACT_REFRESH_RUNTIME__
        .performReactRefresh

      hookedFunction()
      jest.advanceTimersByTime(50)
      hookedFunction()
      jest.advanceTimersByTime(50)
      hookedFunction()

      expect(sessionStorage.getItem('fast_refresh_active')).toBe('true')

      jest.advanceTimersByTime(150)

      expect(sessionStorage.getItem('fast_refresh_active')).toBeNull()

      jest.useRealTimers()
    })

    it('should handle component name with special characters', () => {
      const specialNames = [
        'Component-With-Dashes',
        'Component.With.Dots',
        'Component_With_Underscores',
        'Component123',
      ]

      specialNames.forEach((name) => {
        fastRefreshDetector.markHandled(name)
        expect(fastRefreshDetector.hasBeenHandled(name)).toBe(true)
      })
    })
  })
})
