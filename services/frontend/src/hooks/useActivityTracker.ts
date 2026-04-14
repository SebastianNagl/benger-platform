import { useCallback, useEffect, useRef } from 'react'

const IDLE_THRESHOLD_MS = 60_000 // 60 seconds

interface ActivityData {
  wallClockMs: number
  activeMs: number
  focusedMs: number
  tabSwitches: number
}

/**
 * Tracks research-grade timing data for annotation tasks (Issue #1208).
 *
 * - wallClockMs: total elapsed time (performance.now based, monotonic)
 * - activeMs: time when browser tab was visible (Page Visibility API)
 * - focusedMs: time when tab was visible AND user was interacting (not idle for >60s)
 * - tabSwitches: number of times the tab lost/regained visibility
 */
export function useActivityTracker() {
  const startTimeRef = useRef<number>(0)
  const isRunningRef = useRef(false)

  // Active time tracking (Page Visibility API)
  const activeAccumRef = useRef(0)
  const lastVisibleTimeRef = useRef(0)

  // Focused time tracking (idle detection)
  const focusedAccumRef = useRef(0)
  const lastInteractionTimeRef = useRef(0)
  const idleStartRef = useRef<number | null>(null)

  // Tab switch counter
  const tabSwitchesRef = useRef(0)

  const handleVisibilityChange = useCallback(() => {
    if (!isRunningRef.current) return

    const now = performance.now()
    if (document.hidden) {
      // Tab became hidden — accumulate active time
      const activeChunk = now - lastVisibleTimeRef.current
      activeAccumRef.current += activeChunk
      // Also accumulate focused time for non-idle portion
      if (idleStartRef.current === null) {
        focusedAccumRef.current += activeChunk
      } else {
        // Was idle — only count up to when idle started
        const focusedChunk = idleStartRef.current - lastVisibleTimeRef.current
        if (focusedChunk > 0) {
          focusedAccumRef.current += focusedChunk
        }
      }
      tabSwitchesRef.current += 1
    } else {
      // Tab became visible again
      lastVisibleTimeRef.current = now
      lastInteractionTimeRef.current = now
      idleStartRef.current = null
    }
  }, [])

  const handleInteraction = useCallback(() => {
    if (!isRunningRef.current) return
    const now = performance.now()

    if (idleStartRef.current !== null) {
      // Was idle, now active again — the idle gap is already excluded
      idleStartRef.current = null
    }

    lastInteractionTimeRef.current = now
  }, [])

  // Idle detection via interval
  useEffect(() => {
    const interval = setInterval(() => {
      if (!isRunningRef.current || document.hidden) return

      const now = performance.now()
      const timeSinceInteraction = now - lastInteractionTimeRef.current

      if (timeSinceInteraction >= IDLE_THRESHOLD_MS && idleStartRef.current === null) {
        // User went idle — mark when idle started (at the threshold boundary)
        idleStartRef.current = lastInteractionTimeRef.current + IDLE_THRESHOLD_MS
      }
    }, 5000)

    return () => clearInterval(interval)
  }, [])

  // Register event listeners
  useEffect(() => {
    document.addEventListener('visibilitychange', handleVisibilityChange)

    const interactionEvents = ['mousemove', 'keydown', 'scroll', 'click', 'touchstart']
    interactionEvents.forEach((event) => {
      document.addEventListener(event, handleInteraction, { passive: true })
    })

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      interactionEvents.forEach((event) => {
        document.removeEventListener(event, handleInteraction)
      })
    }
  }, [handleVisibilityChange, handleInteraction])

  const start = useCallback(() => {
    const now = performance.now()
    startTimeRef.current = now
    isRunningRef.current = true
    activeAccumRef.current = 0
    focusedAccumRef.current = 0
    lastVisibleTimeRef.current = now
    lastInteractionTimeRef.current = now
    idleStartRef.current = null
    tabSwitchesRef.current = 0
  }, [])

  const getData = useCallback((): ActivityData => {
    const now = performance.now()
    const wallClockMs = now - startTimeRef.current

    let activeMs = activeAccumRef.current
    let focusedMs = focusedAccumRef.current

    // If tab is currently visible, add the current active chunk
    if (!document.hidden && isRunningRef.current) {
      activeMs += now - lastVisibleTimeRef.current

      if (idleStartRef.current === null) {
        focusedMs += now - lastVisibleTimeRef.current
      } else {
        const focusedChunk = idleStartRef.current - lastVisibleTimeRef.current
        if (focusedChunk > 0) {
          focusedMs += focusedChunk
        }
      }
    }

    return {
      wallClockMs: Math.round(wallClockMs),
      activeMs: Math.round(activeMs),
      focusedMs: Math.round(focusedMs),
      tabSwitches: tabSwitchesRef.current,
    }
  }, [])

  const reset = useCallback(() => {
    isRunningRef.current = false
    startTimeRef.current = 0
    activeAccumRef.current = 0
    focusedAccumRef.current = 0
    lastVisibleTimeRef.current = 0
    lastInteractionTimeRef.current = 0
    idleStartRef.current = null
    tabSwitchesRef.current = 0
  }, [])

  return { start, getData, reset }
}
