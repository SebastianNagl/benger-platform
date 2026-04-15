'use client'

import { useUIStore } from '@/stores'
import { useEffect } from 'react'

/**
 * Hook to handle hydration for persisted UI state
 * This ensures the UI is properly synchronized with localStorage after hydration
 */
export function useHydration() {
  const { isHydrated, setHydrated } = useUIStore()

  useEffect(() => {
    // Mark as hydrated after client-side mount
    if (!isHydrated) {
      setHydrated()
    }
  }, [isHydrated, setHydrated])

  return isHydrated
}
