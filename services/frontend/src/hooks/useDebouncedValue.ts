import { useEffect, useState } from 'react'

/**
 * Lag a fast-changing value by `delayMs` so downstream effects (typically
 * a fetch) fire only after the user pauses. Returns the most recent value
 * once `delayMs` ms have elapsed without a change.
 */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(id)
  }, [value, delayMs])
  return debounced
}
