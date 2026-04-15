'use client'

import { createContext, ReactNode, useContext, useEffect, useState } from 'react'

/**
 * HydrationContext provides a centralized way to detect when the app has
 * completed client-side hydration. This is essential for preventing
 * SSR/hydration mismatches when using client-only features like:
 * - localStorage/sessionStorage
 * - window.matchMedia
 * - Browser-specific APIs
 *
 * Usage:
 *   const isHydrated = useHydration()
 *   if (!isHydrated) return <ServerFallback />
 *   return <ClientOnlyContent />
 */

// Use a symbol to detect if we're inside a provider
const NOT_PROVIDED = Symbol('not-provided')
const HydrationContext = createContext<boolean | typeof NOT_PROVIDED>(NOT_PROVIDED)

export function HydrationProvider({ children }: { children: ReactNode }) {
  const [isHydrated, setIsHydrated] = useState(false)

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- Intentional: tracking hydration completion
    setIsHydrated(true)
  }, [])

  return (
    <HydrationContext.Provider value={isHydrated}>
      {children}
    </HydrationContext.Provider>
  )
}

/**
 * Hook to check if the app has completed client-side hydration.
 * Returns false during SSR and initial hydration, true after hydration completes.
 * When used outside a HydrationProvider (e.g., in tests), returns true in browser.
 */
export function useHydration(): boolean {
  const value = useContext(HydrationContext)

  // If used outside provider, assume hydrated in browser environment (tests, etc.)
  if (value === NOT_PROVIDED) {
    return typeof window !== 'undefined'
  }

  return value
}
