/**
 * Additional function coverage for MobileNavigation.tsx
 * Covers: useMobileNavigationStore (open, close, toggle), useIsInsideMobileNavigation
 */

import {
  useMobileNavigationStore,
  useIsInsideMobileNavigation,
} from '../MobileNavigation'
import { renderHook, act } from '@testing-library/react'

describe('MobileNavigation - store and hooks', () => {
  beforeEach(() => {
    // Reset store state
    act(() => {
      useMobileNavigationStore.setState({ isOpen: false })
    })
  })

  describe('useMobileNavigationStore', () => {
    it('starts with isOpen false', () => {
      const { result } = renderHook(() => useMobileNavigationStore())
      expect(result.current.isOpen).toBe(false)
    })

    it('open() sets isOpen to true', () => {
      const { result } = renderHook(() => useMobileNavigationStore())
      act(() => {
        result.current.open()
      })
      expect(result.current.isOpen).toBe(true)
    })

    it('close() sets isOpen to false', () => {
      const { result } = renderHook(() => useMobileNavigationStore())
      act(() => {
        result.current.open()
      })
      expect(result.current.isOpen).toBe(true)
      act(() => {
        result.current.close()
      })
      expect(result.current.isOpen).toBe(false)
    })

    it('toggle() flips isOpen state', () => {
      const { result } = renderHook(() => useMobileNavigationStore())
      expect(result.current.isOpen).toBe(false)
      act(() => {
        result.current.toggle()
      })
      expect(result.current.isOpen).toBe(true)
      act(() => {
        result.current.toggle()
      })
      expect(result.current.isOpen).toBe(false)
    })
  })

  describe('useIsInsideMobileNavigation', () => {
    it('returns false by default (outside context)', () => {
      const { result } = renderHook(() => useIsInsideMobileNavigation())
      expect(result.current).toBe(false)
    })
  })
})
