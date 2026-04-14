/**
 * @jest-environment jsdom
 *
 * useActivityTracker branch coverage extension tests.
 * Targets idle detection, visibility changes, focusedMs calculation branches,
 * and edge cases (idle start, not running, hidden tab).
 */

import { renderHook, act } from '@testing-library/react'
import { useActivityTracker } from '../useActivityTracker'

describe('useActivityTracker - branch coverage', () => {
  let originalHidden: boolean
  let visibilityChangeHandlers: (() => void)[] = []
  let originalPerformanceNow: typeof performance.now

  beforeEach(() => {
    jest.useFakeTimers()
    originalHidden = document.hidden
    originalPerformanceNow = performance.now

    visibilityChangeHandlers = []

    // Capture visibility change handlers
    const originalAddEventListener = document.addEventListener
    jest.spyOn(document, 'addEventListener').mockImplementation((event, handler, options) => {
      if (event === 'visibilitychange') {
        visibilityChangeHandlers.push(handler as () => void)
      }
      return originalAddEventListener.call(document, event, handler as any, options)
    })

    // Mock performance.now with controllable time
    let mockTime = 0
    jest.spyOn(performance, 'now').mockImplementation(() => mockTime)

    // Helper to advance performance.now
    ;(global as any).__setMockPerformanceNow = (t: number) => {
      mockTime = t
      jest.spyOn(performance, 'now').mockImplementation(() => t)
    }
  })

  afterEach(() => {
    jest.useRealTimers()
    jest.restoreAllMocks()
    Object.defineProperty(document, 'hidden', {
      value: originalHidden,
      configurable: true,
      writable: true,
    })
    delete (global as any).__setMockPerformanceNow
  })

  const setHidden = (hidden: boolean) => {
    Object.defineProperty(document, 'hidden', {
      value: hidden,
      configurable: true,
      writable: true,
    })
  }

  const setTime = (t: number) => {
    ;(global as any).__setMockPerformanceNow(t)
  }

  it('should return start, getData, reset functions', () => {
    const { result } = renderHook(() => useActivityTracker())

    expect(result.current.start).toBeDefined()
    expect(result.current.getData).toBeDefined()
    expect(result.current.reset).toBeDefined()
  })

  it('should track wall clock time', () => {
    setHidden(false)
    setTime(0)

    const { result } = renderHook(() => useActivityTracker())

    act(() => {
      result.current.start()
    })

    setTime(5000)

    const data = result.current.getData()
    expect(data.wallClockMs).toBe(5000)
  })

  it('should track active time when tab is visible', () => {
    setHidden(false)
    setTime(0)

    const { result } = renderHook(() => useActivityTracker())

    act(() => {
      result.current.start()
    })

    setTime(3000)

    const data = result.current.getData()
    expect(data.activeMs).toBe(3000)
  })

  it('should track tab switches', () => {
    setHidden(false)
    setTime(0)

    const { result } = renderHook(() => useActivityTracker())

    act(() => {
      result.current.start()
    })

    // Tab goes hidden
    setTime(2000)
    setHidden(true)
    act(() => {
      visibilityChangeHandlers.forEach(h => h())
    })

    const data = result.current.getData()
    expect(data.tabSwitches).toBe(1)
  })

  it('should reset all counters', () => {
    setHidden(false)
    setTime(0)

    const { result } = renderHook(() => useActivityTracker())

    act(() => {
      result.current.start()
    })

    setTime(5000)

    act(() => {
      result.current.reset()
    })

    const data = result.current.getData()
    // After reset, wallClockMs should be large negative (since startTimeRef is 0)
    // but tabSwitches should be 0
    expect(data.tabSwitches).toBe(0)
  })

  it('should not count active time when tab becomes hidden', () => {
    setHidden(false)
    setTime(0)

    const { result } = renderHook(() => useActivityTracker())

    act(() => {
      result.current.start()
    })

    // Active for 2 seconds
    setTime(2000)
    setHidden(true)
    act(() => {
      visibilityChangeHandlers.forEach(h => h())
    })

    // Time passes while hidden
    setTime(10000)

    // Tab visible again
    setHidden(false)
    act(() => {
      visibilityChangeHandlers.forEach(h => h())
    })

    // Active for 1 more second
    setTime(11000)

    const data = result.current.getData()
    // Active: 2000 (before hidden) + 1000 (after visible again) = 3000
    expect(data.activeMs).toBe(3000)
  })

  it('should handle visibility changes when not running', () => {
    setHidden(false)
    setTime(0)

    const { result } = renderHook(() => useActivityTracker())

    // Don't call start(), just trigger visibility change
    setHidden(true)
    act(() => {
      visibilityChangeHandlers.forEach(h => h())
    })

    // Should not crash and tabSwitches should stay 0
    const data = result.current.getData()
    expect(data.tabSwitches).toBe(0)
  })

  it('should handle interaction events when not running', () => {
    setHidden(false)
    setTime(0)

    const { result } = renderHook(() => useActivityTracker())

    // Simulate interaction without starting - should not throw
    act(() => {
      document.dispatchEvent(new MouseEvent('mousemove'))
      document.dispatchEvent(new KeyboardEvent('keydown'))
    })

    // Should not crash
    const data = result.current.getData()
    expect(data.tabSwitches).toBe(0)
  })

  it('should handle getData when tab is hidden and tracker is running', () => {
    setHidden(false)
    setTime(0)

    const { result } = renderHook(() => useActivityTracker())

    act(() => {
      result.current.start()
    })

    setTime(3000)
    setHidden(true)
    act(() => {
      visibilityChangeHandlers.forEach(h => h())
    })

    setTime(5000)
    // getData while tab is hidden - should NOT add current chunk
    const data = result.current.getData()
    expect(data.activeMs).toBe(3000)
    expect(data.wallClockMs).toBe(5000)
  })

  it('should handle multiple tab switches', () => {
    setHidden(false)
    setTime(0)

    const { result } = renderHook(() => useActivityTracker())

    act(() => {
      result.current.start()
    })

    // First switch away
    setTime(1000)
    setHidden(true)
    act(() => { visibilityChangeHandlers.forEach(h => h()) })

    // Come back
    setTime(2000)
    setHidden(false)
    act(() => { visibilityChangeHandlers.forEach(h => h()) })

    // Second switch away
    setTime(3000)
    setHidden(true)
    act(() => { visibilityChangeHandlers.forEach(h => h()) })

    // Come back
    setTime(4000)
    setHidden(false)
    act(() => { visibilityChangeHandlers.forEach(h => h()) })

    setTime(5000)

    const data = result.current.getData()
    expect(data.tabSwitches).toBe(2)
    // Active: 1000 (0-1000) + 1000 (2000-3000) + 1000 (4000-5000) = 3000
    expect(data.activeMs).toBe(3000)
  })
})
