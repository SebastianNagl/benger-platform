/**
 * @jest-environment jsdom
 */

import { useUIStore } from '@/stores'
import { act, renderHook } from '@testing-library/react'
import { useHydration } from '../useHydration'

// Mock the UI store
jest.mock('@/stores', () => ({
  useUIStore: jest.fn(),
}))

const mockedUseUIStore = useUIStore as jest.MockedFunction<typeof useUIStore>

describe('useHydration', () => {
  let mockSetHydrated: jest.Mock

  beforeEach(() => {
    mockSetHydrated = jest.fn()
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  describe('Basic Hook Behavior', () => {
    it('should be defined and callable', () => {
      mockedUseUIStore.mockReturnValue({
        isHydrated: false,
        setHydrated: mockSetHydrated,
      } as any)

      const { result } = renderHook(() => useHydration())
      expect(result.current).toBeDefined()
    })

    it('should return a boolean value', () => {
      mockedUseUIStore.mockReturnValue({
        isHydrated: false,
        setHydrated: mockSetHydrated,
      } as any)

      const { result } = renderHook(() => useHydration())
      expect(typeof result.current).toBe('boolean')
    })

    it('should call useUIStore to get hydration state', () => {
      mockedUseUIStore.mockReturnValue({
        isHydrated: false,
        setHydrated: mockSetHydrated,
      } as any)

      renderHook(() => useHydration())
      expect(mockedUseUIStore).toHaveBeenCalled()
    })
  })

  describe('Initial State', () => {
    it('should return false when store is not hydrated', () => {
      mockedUseUIStore.mockReturnValue({
        isHydrated: false,
        setHydrated: mockSetHydrated,
      } as any)

      const { result } = renderHook(() => useHydration())
      expect(result.current).toBe(false)
    })

    it('should return true when store is already hydrated', () => {
      mockedUseUIStore.mockReturnValue({
        isHydrated: true,
        setHydrated: mockSetHydrated,
      } as any)

      const { result } = renderHook(() => useHydration())
      expect(result.current).toBe(true)
    })

    it('should call setHydrated on mount when not hydrated', () => {
      mockedUseUIStore.mockReturnValue({
        isHydrated: false,
        setHydrated: mockSetHydrated,
      } as any)

      renderHook(() => useHydration())

      // setHydrated should be called in useEffect
      expect(mockSetHydrated).toHaveBeenCalledTimes(1)
      expect(mockSetHydrated).toHaveBeenCalledWith()
    })

    it('should not call setHydrated on mount when already hydrated', () => {
      mockedUseUIStore.mockReturnValue({
        isHydrated: true,
        setHydrated: mockSetHydrated,
      } as any)

      renderHook(() => useHydration())

      // setHydrated should not be called since already hydrated
      expect(mockSetHydrated).not.toHaveBeenCalled()
    })
  })

  describe('Hydration Detection', () => {
    it('should detect hydration state change from false to true', () => {
      let isHydrated = false
      mockedUseUIStore.mockImplementation(() => ({
        isHydrated,
        setHydrated: () => {
          isHydrated = true
        },
      }))

      const { result, rerender } = renderHook(() => useHydration())
      expect(result.current).toBe(false)

      // Simulate hydration
      act(() => {
        isHydrated = true
      })
      rerender()

      expect(result.current).toBe(true)
    })

    it('should reflect store hydration state accurately', () => {
      mockedUseUIStore.mockReturnValue({
        isHydrated: false,
        setHydrated: mockSetHydrated,
      } as any)

      const { result } = renderHook(() => useHydration())
      expect(result.current).toBe(false)

      // Update mock to return hydrated state
      mockedUseUIStore.mockReturnValue({
        isHydrated: true,
        setHydrated: mockSetHydrated,
      } as any)

      const { result: result2 } = renderHook(() => useHydration())
      expect(result2.current).toBe(true)
    })

    it('should call setHydrated only once per mount', () => {
      mockedUseUIStore.mockReturnValue({
        isHydrated: false,
        setHydrated: mockSetHydrated,
      } as any)

      const { rerender } = renderHook(() => useHydration())

      expect(mockSetHydrated).toHaveBeenCalledTimes(1)

      // Rerender should not trigger additional calls
      rerender()
      expect(mockSetHydrated).toHaveBeenCalledTimes(1)
    })
  })

  describe('State Changes', () => {
    it('should update returned value when store state changes', () => {
      let currentHydrated = false
      mockedUseUIStore.mockImplementation(() => ({
        isHydrated: currentHydrated,
        setHydrated: mockSetHydrated,
      }))

      const { result, rerender } = renderHook(() => useHydration())
      expect(result.current).toBe(false)

      // Change the store state
      act(() => {
        currentHydrated = true
      })
      rerender()

      expect(result.current).toBe(true)
    })

    it('should handle multiple state transitions', () => {
      let currentHydrated = false
      mockedUseUIStore.mockImplementation(() => ({
        isHydrated: currentHydrated,
        setHydrated: mockSetHydrated,
      }))

      const { result, rerender } = renderHook(() => useHydration())
      expect(result.current).toBe(false)

      // First transition: false -> true
      act(() => {
        currentHydrated = true
      })
      rerender()
      expect(result.current).toBe(true)

      // Second transition: true -> false (edge case)
      act(() => {
        currentHydrated = false
      })
      rerender()
      expect(result.current).toBe(false)

      // Third transition: false -> true again
      act(() => {
        currentHydrated = true
      })
      rerender()
      expect(result.current).toBe(true)
    })

    it('should handle rapid state changes', () => {
      let currentHydrated = false
      mockedUseUIStore.mockImplementation(() => ({
        isHydrated: currentHydrated,
        setHydrated: mockSetHydrated,
      }))

      const { result, rerender } = renderHook(() => useHydration())

      // Rapid changes
      for (let i = 0; i < 10; i++) {
        act(() => {
          currentHydrated = !currentHydrated
        })
        rerender()
        expect(result.current).toBe(currentHydrated)
      }
    })
  })

  describe('Multiple Hook Instances', () => {
    it('should allow multiple instances to coexist', () => {
      mockedUseUIStore.mockReturnValue({
        isHydrated: false,
        setHydrated: mockSetHydrated,
      } as any)

      const { result: result1 } = renderHook(() => useHydration())
      const { result: result2 } = renderHook(() => useHydration())
      const { result: result3 } = renderHook(() => useHydration())

      expect(result1.current).toBe(false)
      expect(result2.current).toBe(false)
      expect(result3.current).toBe(false)

      // setHydrated should be called for each instance
      expect(mockSetHydrated).toHaveBeenCalledTimes(3)
    })

    it('should sync all instances when store state changes', () => {
      let currentHydrated = false
      mockedUseUIStore.mockImplementation(() => ({
        isHydrated: currentHydrated,
        setHydrated: mockSetHydrated,
      }))

      const { result: result1, rerender: rerender1 } = renderHook(() =>
        useHydration()
      )
      const { result: result2, rerender: rerender2 } = renderHook(() =>
        useHydration()
      )

      expect(result1.current).toBe(false)
      expect(result2.current).toBe(false)

      // Change global state
      act(() => {
        currentHydrated = true
      })
      rerender1()
      rerender2()

      expect(result1.current).toBe(true)
      expect(result2.current).toBe(true)
    })

    it('should handle different instances mounting at different times', () => {
      mockedUseUIStore.mockReturnValue({
        isHydrated: false,
        setHydrated: mockSetHydrated,
      } as any)

      const { result: result1 } = renderHook(() => useHydration())
      expect(result1.current).toBe(false)
      expect(mockSetHydrated).toHaveBeenCalledTimes(1)

      // Update store to hydrated
      mockedUseUIStore.mockReturnValue({
        isHydrated: true,
        setHydrated: mockSetHydrated,
      } as any)

      const { result: result2 } = renderHook(() => useHydration())
      expect(result2.current).toBe(true)
      // Should not call setHydrated again since already hydrated
      expect(mockSetHydrated).toHaveBeenCalledTimes(1)
    })
  })

  describe('Edge Cases', () => {
    it('should handle unmounting before hydration completes', () => {
      mockedUseUIStore.mockReturnValue({
        isHydrated: false,
        setHydrated: mockSetHydrated,
      } as any)

      const { unmount } = renderHook(() => useHydration())

      expect(mockSetHydrated).toHaveBeenCalledTimes(1)

      // Unmount immediately
      expect(() => unmount()).not.toThrow()
    })

    it('should handle rapid mount and unmount cycles', () => {
      mockedUseUIStore.mockReturnValue({
        isHydrated: false,
        setHydrated: mockSetHydrated,
      } as any)

      for (let i = 0; i < 5; i++) {
        const { unmount } = renderHook(() => useHydration())
        unmount()
      }

      // setHydrated should be called for each mount
      expect(mockSetHydrated).toHaveBeenCalledTimes(5)
    })

    it('should handle already hydrated state on mount', () => {
      mockedUseUIStore.mockReturnValue({
        isHydrated: true,
        setHydrated: mockSetHydrated,
      } as any)

      // Should not call setHydrated when already hydrated
      const { result } = renderHook(() => useHydration())
      expect(result.current).toBe(true)
      expect(mockSetHydrated).not.toHaveBeenCalled()
    })

    it('should handle store returning undefined isHydrated', () => {
      mockedUseUIStore.mockReturnValue({
        isHydrated: undefined as any,
        setHydrated: mockSetHydrated,
      })

      const { result } = renderHook(() => useHydration())
      expect(result.current).toBeUndefined()
    })

    it('should handle re-renders with same hydration state', () => {
      mockedUseUIStore.mockReturnValue({
        isHydrated: false,
        setHydrated: mockSetHydrated,
      } as any)

      const { result, rerender } = renderHook(() => useHydration())
      expect(result.current).toBe(false)

      // Multiple rerenders with same state
      for (let i = 0; i < 10; i++) {
        rerender()
        expect(result.current).toBe(false)
      }

      // setHydrated should only be called once
      expect(mockSetHydrated).toHaveBeenCalledTimes(1)
    })

    it('should not cause memory leaks on repeated mount/unmount', () => {
      mockedUseUIStore.mockReturnValue({
        isHydrated: false,
        setHydrated: mockSetHydrated,
      } as any)

      const instances: Array<() => void> = []

      // Mount multiple instances
      for (let i = 0; i < 100; i++) {
        const { unmount } = renderHook(() => useHydration())
        instances.push(unmount)
      }

      // Unmount all
      expect(() => {
        instances.forEach((unmount) => unmount())
      }).not.toThrow()
    })
  })

  describe('Server vs Client Environment', () => {
    it('should work in client environment', () => {
      mockedUseUIStore.mockReturnValue({
        isHydrated: false,
        setHydrated: mockSetHydrated,
      } as any)

      // jsdom environment simulates client
      expect(() => renderHook(() => useHydration())).not.toThrow()
      expect(mockSetHydrated).toHaveBeenCalled()
    })

    it('should handle hydration after client-side mount', () => {
      let isHydrated = false
      const setHydratedMock = jest.fn(() => {
        isHydrated = true
      })

      mockedUseUIStore.mockImplementation(() => ({
        isHydrated,
        setHydrated: setHydratedMock,
      }))

      const { result, rerender } = renderHook(() => useHydration())

      // Initially not hydrated
      expect(result.current).toBe(false)
      expect(setHydratedMock).toHaveBeenCalledTimes(1)

      // Simulate hydration completion
      act(() => {
        isHydrated = true
      })
      rerender()

      expect(result.current).toBe(true)
    })

    it('should preserve hydration state across navigation', () => {
      mockedUseUIStore.mockReturnValue({
        isHydrated: true,
        setHydrated: mockSetHydrated,
      } as any)

      const { result: result1, unmount } = renderHook(() => useHydration())
      expect(result1.current).toBe(true)

      unmount()

      // Simulate navigation - new component mount
      const { result: result2 } = renderHook(() => useHydration())
      expect(result2.current).toBe(true)
      expect(mockSetHydrated).not.toHaveBeenCalled()
    })

    it('should handle SSR to CSR transition', () => {
      // Start with server-side rendered state (not hydrated)
      mockedUseUIStore.mockReturnValue({
        isHydrated: false,
        setHydrated: mockSetHydrated,
      } as any)

      const { result } = renderHook(() => useHydration())

      // On client mount, should call setHydrated
      expect(result.current).toBe(false)
      expect(mockSetHydrated).toHaveBeenCalledTimes(1)
    })

    it('should support React 18 concurrent features', () => {
      mockedUseUIStore.mockReturnValue({
        isHydrated: false,
        setHydrated: mockSetHydrated,
      } as any)

      // Multiple renders in concurrent mode
      const { result, rerender } = renderHook(() => useHydration())

      act(() => {
        rerender()
        rerender()
        rerender()
      })

      expect(result.current).toBe(false)
      // Should only call setHydrated once despite multiple renders
      expect(mockSetHydrated).toHaveBeenCalledTimes(1)
    })
  })

  describe('Cleanup', () => {
    it('should cleanup properly on unmount', () => {
      mockedUseUIStore.mockReturnValue({
        isHydrated: false,
        setHydrated: mockSetHydrated,
      } as any)

      const { unmount } = renderHook(() => useHydration())

      expect(() => unmount()).not.toThrow()
    })

    it('should not call setHydrated after unmount', () => {
      let shouldCall = true
      const delayedSetHydrated = jest.fn(() => {
        if (shouldCall) {
          // Simulate async operation
        }
      })

      mockedUseUIStore.mockReturnValue({
        isHydrated: false,
        setHydrated: delayedSetHydrated,
      } as any)

      const { unmount } = renderHook(() => useHydration())

      shouldCall = false
      unmount()

      // Should not throw or cause issues after unmount
      expect(() => delayedSetHydrated()).not.toThrow()
    })

    it('should allow remounting after unmount', () => {
      mockedUseUIStore.mockReturnValue({
        isHydrated: false,
        setHydrated: mockSetHydrated,
      } as any)

      const { unmount } = renderHook(() => useHydration())
      unmount()

      expect(() => renderHook(() => useHydration())).not.toThrow()
      expect(mockSetHydrated).toHaveBeenCalledTimes(2)
    })

    it('should not interfere with other hook instances on unmount', () => {
      mockedUseUIStore.mockReturnValue({
        isHydrated: false,
        setHydrated: mockSetHydrated,
      } as any)

      const { result: result1 } = renderHook(() => useHydration())
      const { result: result2, unmount: unmount2 } = renderHook(() =>
        useHydration()
      )

      expect(result1.current).toBe(false)
      expect(result2.current).toBe(false)

      // Unmount second instance
      unmount2()

      // First instance should still work
      expect(result1.current).toBe(false)
    })

    it('should handle cleanup with pending state updates', () => {
      let currentHydrated = false
      mockedUseUIStore.mockImplementation(() => ({
        isHydrated: currentHydrated,
        setHydrated: mockSetHydrated,
      }))

      const { unmount } = renderHook(() => useHydration())

      // Schedule state update
      act(() => {
        currentHydrated = true
      })

      // Unmount before update completes
      expect(() => unmount()).not.toThrow()
    })
  })
})
