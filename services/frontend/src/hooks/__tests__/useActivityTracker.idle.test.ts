/**
 * @jest-environment jsdom
 *
 * Branch coverage for the IDLE paths of useActivityTracker that the existing
 * suites never reach. These all hinge on `idleStartRef` becoming non-null,
 * which only happens after the 5s idle-detection interval observes >= 60s
 * without interaction.
 *
 * Targets:
 *  - idle-detection interval sets idleStartRef (lines 83-85)
 *  - idle-detection interval early-returns while tab hidden (line 78)
 *  - handleVisibilityChange "was idle" branch (lines 45-52), both the
 *    focusedChunk > 0 and focusedChunk <= 0 sub-branches
 *  - handleInteraction resume-from-idle branch (lines 67-69)
 *  - getData "currently visible AND idle" branch (lines 132-138)
 *
 * Mirrors the controllable-time idiom from useActivityTracker.coverage.test.ts:
 * performance.now() is mocked and driven manually via setTime().
 */

import { renderHook, act } from '@testing-library/react'
import { useActivityTracker } from '../useActivityTracker'

const IDLE_THRESHOLD_MS = 60_000

describe('useActivityTracker - idle branch coverage', () => {
  let originalHidden: boolean
  let visibilityChangeHandlers: (() => void)[] = []

  beforeEach(() => {
    jest.useFakeTimers()
    originalHidden = document.hidden
    visibilityChangeHandlers = []

    const originalAddEventListener = document.addEventListener
    jest
      .spyOn(document, 'addEventListener')
      .mockImplementation((event, handler, options) => {
        if (event === 'visibilitychange') {
          visibilityChangeHandlers.push(handler as () => void)
        }
        return originalAddEventListener.call(
          document,
          event,
          handler as any,
          options
        )
      })

    let mockTime = 0
    jest.spyOn(performance, 'now').mockImplementation(() => mockTime)
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
  const setTime = (t: number) => (global as any).__setMockPerformanceNow(t)
  const fireVisibility = () =>
    act(() => {
      visibilityChangeHandlers.forEach((h) => h())
    })
  // Run one idle-detection tick (the hook's interval is 5000ms).
  const tickIdleInterval = () =>
    act(() => {
      jest.advanceTimersByTime(5000)
    })

  it('marks idle after 60s of no interaction and excludes idle time from focusedMs', () => {
    setHidden(false)
    setTime(0)
    const { result } = renderHook(() => useActivityTracker())

    act(() => result.current.start())

    // 65s pass with no interaction. Drive performance.now to 65000, then let
    // the 5s detection interval observe the idle gap.
    setTime(65_000)
    tickIdleInterval() // idleStartRef = lastInteraction(0) + 60000 = 60000

    // getData while visible + idle: activeMs counts full chunk, focusedMs only
    // up to the idle boundary (60000).
    const data = result.current.getData()
    expect(data.activeMs).toBe(65_000)
    expect(data.focusedMs).toBe(IDLE_THRESHOLD_MS) // 60000, not 65000
    expect(data.wallClockMs).toBe(65_000)
  })

  it('accumulates focused-up-to-idle when the tab is hidden while idle', () => {
    setHidden(false)
    setTime(0)
    const { result } = renderHook(() => useActivityTracker())

    act(() => result.current.start())

    // Go idle.
    setTime(65_000)
    tickIdleInterval() // idleStart = 60000

    // Now hide the tab at t=70000. handleVisibilityChange takes the "was idle"
    // branch: focusedChunk = idleStart(60000) - lastVisible(0) = 60000 (> 0).
    setTime(70_000)
    setHidden(true)
    fireVisibility()

    const data = result.current.getData()
    expect(data.tabSwitches).toBe(1)
    // active accumulated full 70000; focused only the pre-idle 60000.
    expect(data.activeMs).toBe(70_000)
    expect(data.focusedMs).toBe(IDLE_THRESHOLD_MS)
  })

  it('does not double-count focused time when idle started before the visible chunk', () => {
    setHidden(false)
    setTime(0)
    const { result } = renderHook(() => useActivityTracker())

    act(() => result.current.start())

    // Become idle.
    setTime(65_000)
    tickIdleInterval() // idleStart = 60000

    // Hide while idle (focusedChunk = 60000 > 0): focused freezes at 60000.
    setTime(66_000)
    setHidden(true)
    fireVisibility()

    // Become visible again -> resets lastVisible/lastInteraction, clears idle.
    setTime(67_000)
    setHidden(false)
    fireVisibility()

    // Immediately go idle again relative to the *new* lastInteraction (67000).
    setTime(67_000 + 65_000) // 132000
    tickIdleInterval() // idleStart = 67000 + 60000 = 127000

    const data = result.current.getData()
    // focused = 60000 (first window) + (127000 - 67000) = 60000 + 60000
    expect(data.focusedMs).toBe(120_000)
  })

  it('resumes focused tracking after an interaction clears the idle marker', () => {
    setHidden(false)
    setTime(0)
    const { result } = renderHook(() => useActivityTracker())

    act(() => result.current.start())

    // Go idle.
    setTime(65_000)
    tickIdleInterval() // idleStart = 60000

    // A user interaction at t=65000 clears idleStartRef (lines 67-69).
    setTime(65_000)
    act(() => {
      document.dispatchEvent(new Event('mousemove'))
    })

    // Now visible + NOT idle again: focusedMs tracks the full visible chunk.
    setTime(66_000)
    const data = result.current.getData()
    expect(data.focusedMs).toBe(66_000)
  })

  it('idle-detection interval early-returns while the tab is hidden', () => {
    setHidden(false)
    setTime(0)
    const { result } = renderHook(() => useActivityTracker())

    act(() => result.current.start())

    // Hide the tab, then let > 60s pass and run the interval. Because
    // document.hidden is true the interval returns before evaluating idle, so
    // no idle marker is set.
    setTime(1000)
    setHidden(true)
    fireVisibility() // tabSwitches -> 1, active accumulates to 1000

    setTime(70_000)
    tickIdleInterval() // early-returns: idleStart stays null

    // Becoming visible resets the timers; getData while visible counts the new
    // chunk fully as focused (no idle was recorded).
    setTime(70_000)
    setHidden(false)
    fireVisibility()

    setTime(71_000)
    const data = result.current.getData()
    expect(data.tabSwitches).toBe(1)
    // focused = pre-hide chunk (0..1000 => 1000) + post-visible 1000 = 2000
    expect(data.focusedMs).toBe(2000)
  })

  it('idle-detection interval is a no-op when the tracker is not running', () => {
    setHidden(false)
    setTime(0)
    const { result } = renderHook(() => useActivityTracker())

    // Never call start(). Advance well past the idle threshold and tick.
    setTime(70_000)
    tickIdleInterval()

    const data = result.current.getData()
    // Nothing tracked; getData short-circuits the visible-chunk add too.
    expect(data.focusedMs).toBe(0)
    expect(data.activeMs).toBe(0)
    expect(data.tabSwitches).toBe(0)
  })

  it('only sets the idle marker once, not on every interval tick', () => {
    setHidden(false)
    setTime(0)
    const { result } = renderHook(() => useActivityTracker())

    act(() => result.current.start())

    setTime(65_000)
    tickIdleInterval() // sets idleStart = 60000
    tickIdleInterval() // idleStart already non-null -> branch skipped
    tickIdleInterval()

    const data = result.current.getData()
    // focused frozen at the idle boundary regardless of extra ticks.
    expect(data.focusedMs).toBe(IDLE_THRESHOLD_MS)
  })
})
