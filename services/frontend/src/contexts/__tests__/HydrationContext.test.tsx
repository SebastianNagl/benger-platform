/**
 * @jest-environment jsdom
 */

import { renderHook } from '@testing-library/react'
import { HydrationProvider, useHydration } from '../HydrationContext'

describe('HydrationProvider', () => {
  it('should eventually report hydrated state', () => {
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <HydrationProvider>{children}</HydrationProvider>
    )

    const { result } = renderHook(() => useHydration(), { wrapper })
    // After rendering, the useEffect should fire and set isHydrated to true
    expect(result.current).toBe(true)
  })
})

describe('useHydration', () => {
  it('should return true when used outside provider in browser (jsdom)', () => {
    const { result } = renderHook(() => useHydration())
    // Outside provider, returns typeof window !== 'undefined' which is true in jsdom
    expect(result.current).toBe(true)
  })
})
