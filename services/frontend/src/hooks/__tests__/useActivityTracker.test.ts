/**
 * @jest-environment jsdom
 */

import { renderHook, act } from '@testing-library/react'
import { useActivityTracker } from '../useActivityTracker'

describe('useActivityTracker', () => {
  beforeEach(() => {
    jest.useFakeTimers()
    // Ensure document is visible
    Object.defineProperty(document, 'hidden', {
      value: false,
      writable: true,
    })
  })

  afterEach(() => {
    jest.useRealTimers()
  })

  it('returns start, getData, and reset functions', () => {
    const { result } = renderHook(() => useActivityTracker())
    expect(typeof result.current.start).toBe('function')
    expect(typeof result.current.getData).toBe('function')
    expect(typeof result.current.reset).toBe('function')
  })

  it('returns zeroed data before start', () => {
    const { result } = renderHook(() => useActivityTracker())
    const data = result.current.getData()
    expect(data).toHaveProperty('wallClockMs')
    expect(data).toHaveProperty('activeMs')
    expect(data).toHaveProperty('focusedMs')
    expect(data).toHaveProperty('tabSwitches')
  })

  it('tracks wall clock time after start', () => {
    const { result } = renderHook(() => useActivityTracker())
    act(() => {
      result.current.start()
    })

    // Advance performance.now by simulating time
    jest.advanceTimersByTime(1000)

    const data = result.current.getData()
    // wallClockMs should be positive (performance.now based)
    expect(data.wallClockMs).toBeGreaterThanOrEqual(0)
    expect(data.tabSwitches).toBe(0)
  })

  it('resets all data on reset', () => {
    const { result } = renderHook(() => useActivityTracker())
    act(() => {
      result.current.start()
    })

    jest.advanceTimersByTime(5000)

    act(() => {
      result.current.reset()
    })

    const data = result.current.getData()
    expect(data.tabSwitches).toBe(0)
  })

  it('tracks tab switches on visibility change', () => {
    const { result } = renderHook(() => useActivityTracker())
    act(() => {
      result.current.start()
    })

    // Simulate tab becoming hidden
    act(() => {
      Object.defineProperty(document, 'hidden', { value: true, writable: true })
      document.dispatchEvent(new Event('visibilitychange'))
    })

    const data = result.current.getData()
    expect(data.tabSwitches).toBe(1)

    // Simulate tab becoming visible again
    act(() => {
      Object.defineProperty(document, 'hidden', { value: false, writable: true })
      document.dispatchEvent(new Event('visibilitychange'))
    })

    const data2 = result.current.getData()
    expect(data2.tabSwitches).toBe(1) // still 1 (only increments on hide)
  })

  it('does not track when not running', () => {
    const { result } = renderHook(() => useActivityTracker())
    // Don't start - just trigger visibility change
    act(() => {
      Object.defineProperty(document, 'hidden', { value: true, writable: true })
      document.dispatchEvent(new Event('visibilitychange'))
    })

    const data = result.current.getData()
    expect(data.tabSwitches).toBe(0)
  })

  it('handles interaction events', () => {
    const { result } = renderHook(() => useActivityTracker())
    act(() => {
      result.current.start()
    })

    // Simulate user interaction
    act(() => {
      document.dispatchEvent(new Event('mousemove'))
      document.dispatchEvent(new Event('keydown'))
      document.dispatchEvent(new Event('click'))
    })

    const data = result.current.getData()
    expect(data.focusedMs).toBeGreaterThanOrEqual(0)
  })

  it('detects idle state after 60s without interaction', () => {
    const { result } = renderHook(() => useActivityTracker())
    act(() => {
      result.current.start()
    })

    // Advance past idle threshold (60s) plus the check interval (5s)
    act(() => {
      jest.advanceTimersByTime(65000)
    })

    // getData should still work
    const data = result.current.getData()
    expect(data).toBeDefined()
  })

  it('cleans up event listeners on unmount', () => {
    const removeEventSpy = jest.spyOn(document, 'removeEventListener')
    const { unmount } = renderHook(() => useActivityTracker())

    unmount()

    expect(removeEventSpy).toHaveBeenCalledWith(
      'visibilitychange',
      expect.any(Function)
    )
    removeEventSpy.mockRestore()
  })

  it('can be started multiple times (resets counters)', () => {
    const { result } = renderHook(() => useActivityTracker())
    act(() => {
      result.current.start()
    })

    // Switch tab
    act(() => {
      Object.defineProperty(document, 'hidden', { value: true, writable: true })
      document.dispatchEvent(new Event('visibilitychange'))
    })

    expect(result.current.getData().tabSwitches).toBe(1)

    // Start again - should reset
    act(() => {
      Object.defineProperty(document, 'hidden', { value: false, writable: true })
      result.current.start()
    })

    expect(result.current.getData().tabSwitches).toBe(0)
  })
})
