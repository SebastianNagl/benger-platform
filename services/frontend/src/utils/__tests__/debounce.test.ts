/**
 * Comprehensive tests for debounce utility function
 * Tests timing behavior, argument passing, and edge cases
 */

import { debounce } from '../debounce'

describe('debounce utility', () => {
  beforeEach(() => {
    jest.useFakeTimers()
  })

  afterEach(() => {
    jest.useRealTimers()
  })

  describe('Basic Functionality', () => {
    it('should delay function execution by specified wait time', () => {
      const mockFn = jest.fn()
      const debouncedFn = debounce(mockFn, 100)

      debouncedFn()
      expect(mockFn).not.toHaveBeenCalled()

      jest.advanceTimersByTime(99)
      expect(mockFn).not.toHaveBeenCalled()

      jest.advanceTimersByTime(1)
      expect(mockFn).toHaveBeenCalledTimes(1)
    })

    it('should pass arguments correctly to the debounced function', () => {
      const mockFn = jest.fn()
      const debouncedFn = debounce(mockFn, 100)

      debouncedFn('arg1', 'arg2', 123)
      jest.advanceTimersByTime(100)

      expect(mockFn).toHaveBeenCalledWith('arg1', 'arg2', 123)
    })

    it('should work with functions that have no arguments', () => {
      const mockFn = jest.fn()
      const debouncedFn = debounce(mockFn, 50)

      debouncedFn()
      jest.advanceTimersByTime(50)

      expect(mockFn).toHaveBeenCalledWith()
      expect(mockFn).toHaveBeenCalledTimes(1)
    })
  })

  describe('Debouncing Behavior', () => {
    it('should cancel previous timeout when called multiple times rapidly', () => {
      const mockFn = jest.fn()
      const debouncedFn = debounce(mockFn, 100)

      // Call multiple times rapidly
      debouncedFn('first')
      debouncedFn('second')
      debouncedFn('third')

      // Advance time but not enough for any execution
      jest.advanceTimersByTime(99)
      expect(mockFn).not.toHaveBeenCalled()

      // Complete the timeout - only last call should execute
      jest.advanceTimersByTime(1)
      expect(mockFn).toHaveBeenCalledTimes(1)
      expect(mockFn).toHaveBeenCalledWith('third')
    })

    it('should reset timer on each new call', () => {
      const mockFn = jest.fn()
      const debouncedFn = debounce(mockFn, 100)

      debouncedFn('first')
      jest.advanceTimersByTime(50)

      debouncedFn('second')
      jest.advanceTimersByTime(50)

      // First call should be cancelled, second not yet executed
      expect(mockFn).not.toHaveBeenCalled()

      jest.advanceTimersByTime(50)
      expect(mockFn).toHaveBeenCalledTimes(1)
      expect(mockFn).toHaveBeenCalledWith('second')
    })

    it('should allow execution after wait period if no new calls', () => {
      const mockFn = jest.fn()
      const debouncedFn = debounce(mockFn, 100)

      debouncedFn('first')
      jest.advanceTimersByTime(100)
      expect(mockFn).toHaveBeenCalledWith('first')

      // New call after completion should work independently
      debouncedFn('second')
      jest.advanceTimersByTime(100)
      expect(mockFn).toHaveBeenCalledTimes(2)
      expect(mockFn).toHaveBeenLastCalledWith('second')
    })
  })

  describe('Type Safety and Generics', () => {
    it('should preserve function signature for string arguments', () => {
      const stringFn = (str: string, num: number): string => `${str}:${num}`
      const debouncedStringFn = debounce(stringFn, 100)

      // TypeScript should enforce correct arguments
      debouncedStringFn('test', 42)
      jest.advanceTimersByTime(100)

      // The original function should have been called
      expect(stringFn).toBeDefined()
    })

    it('should work with complex object arguments', () => {
      interface TestObject {
        id: number
        name: string
        nested: { value: boolean }
      }

      const mockFn = jest.fn<void, [TestObject]>()
      const debouncedFn = debounce(mockFn, 100)

      const testObj: TestObject = {
        id: 1,
        name: 'test',
        nested: { value: true },
      }

      debouncedFn(testObj)
      jest.advanceTimersByTime(100)

      expect(mockFn).toHaveBeenCalledWith(testObj)
    })

    it('should work with variadic arguments', () => {
      const variadicFn = jest.fn<void, string[]>()
      const debouncedFn = debounce(variadicFn, 100)

      debouncedFn('a', 'b', 'c', 'd')
      jest.advanceTimersByTime(100)

      expect(variadicFn).toHaveBeenCalledWith('a', 'b', 'c', 'd')
    })
  })

  describe('Timing Edge Cases', () => {
    it('should handle zero wait time', () => {
      const mockFn = jest.fn()
      const debouncedFn = debounce(mockFn, 0)

      debouncedFn()
      expect(mockFn).not.toHaveBeenCalled()

      jest.advanceTimersByTime(0)
      expect(mockFn).toHaveBeenCalledTimes(1)
    })

    it('should handle very small wait times', () => {
      const mockFn = jest.fn()
      const debouncedFn = debounce(mockFn, 1)

      debouncedFn()
      jest.advanceTimersByTime(1)

      expect(mockFn).toHaveBeenCalledTimes(1)
    })

    it('should handle very large wait times', () => {
      const mockFn = jest.fn()
      const debouncedFn = debounce(mockFn, 10000)

      debouncedFn()
      jest.advanceTimersByTime(9999)
      expect(mockFn).not.toHaveBeenCalled()

      jest.advanceTimersByTime(1)
      expect(mockFn).toHaveBeenCalledTimes(1)
    })
  })

  describe('Multiple Debounced Functions', () => {
    it('should handle multiple independent debounced functions', () => {
      const mockFn1 = jest.fn()
      const mockFn2 = jest.fn()
      const debouncedFn1 = debounce(mockFn1, 100)
      const debouncedFn2 = debounce(mockFn2, 200)

      debouncedFn1('fn1')
      debouncedFn2('fn2')

      jest.advanceTimersByTime(100)
      expect(mockFn1).toHaveBeenCalledWith('fn1')
      expect(mockFn2).not.toHaveBeenCalled()

      jest.advanceTimersByTime(100)
      expect(mockFn2).toHaveBeenCalledWith('fn2')
    })

    it('should not interfere between different debounced instances', () => {
      const originalFn = jest.fn()
      const debouncedFn1 = debounce(originalFn, 100)
      const debouncedFn2 = debounce(originalFn, 100)

      debouncedFn1('call1')
      debouncedFn2('call2')

      jest.advanceTimersByTime(100)

      // Both should execute independently
      expect(originalFn).toHaveBeenCalledTimes(2)
      expect(originalFn).toHaveBeenCalledWith('call1')
      expect(originalFn).toHaveBeenCalledWith('call2')
    })
  })

  describe('Memory and Cleanup', () => {
    it('should clear timeout reference after execution', () => {
      const mockFn = jest.fn()
      const debouncedFn = debounce(mockFn, 100)

      debouncedFn()
      jest.advanceTimersByTime(100)

      // After execution, should be able to call again cleanly
      debouncedFn()
      jest.advanceTimersByTime(100)

      expect(mockFn).toHaveBeenCalledTimes(2)
    })

    it('should handle rapid successive calls without memory leaks', () => {
      const mockFn = jest.fn()
      const debouncedFn = debounce(mockFn, 100)

      // Make many rapid calls
      for (let i = 0; i < 1000; i++) {
        debouncedFn(`call-${i}`)
      }

      jest.advanceTimersByTime(100)

      // Only the last call should execute
      expect(mockFn).toHaveBeenCalledTimes(1)
      expect(mockFn).toHaveBeenCalledWith('call-999')
    })
  })

  describe('Real-world Usage Scenarios', () => {
    it('should work with search input simulation', () => {
      const searchFn = jest.fn()
      const debouncedSearch = debounce(searchFn, 300)

      // Simulate typing "hello"
      debouncedSearch('h')
      jest.advanceTimersByTime(50)
      debouncedSearch('he')
      jest.advanceTimersByTime(50)
      debouncedSearch('hel')
      jest.advanceTimersByTime(50)
      debouncedSearch('hell')
      jest.advanceTimersByTime(50)
      debouncedSearch('hello')

      // No search should have executed yet
      expect(searchFn).not.toHaveBeenCalled()

      // Wait for debounce to complete
      jest.advanceTimersByTime(300)
      expect(searchFn).toHaveBeenCalledTimes(1)
      expect(searchFn).toHaveBeenCalledWith('hello')
    })

    it('should work with resize event simulation', () => {
      const resizeHandler = jest.fn()
      const debouncedResize = debounce(resizeHandler, 250)

      // Simulate multiple resize events
      for (let i = 0; i < 10; i++) {
        debouncedResize(`resize-${i}`)
        jest.advanceTimersByTime(20)
      }

      // Handler should not have been called during rapid events
      expect(resizeHandler).not.toHaveBeenCalled()

      // Wait for debounce period after last call
      jest.advanceTimersByTime(250)
      expect(resizeHandler).toHaveBeenCalledTimes(1)
      expect(resizeHandler).toHaveBeenCalledWith('resize-9')
    })

    it('should work with API request debouncing', () => {
      interface ApiRequest {
        endpoint: string
        params: Record<string, any>
      }

      const apiCall = jest.fn<void, [ApiRequest]>()
      const debouncedApiCall = debounce(apiCall, 500)

      const request: ApiRequest = {
        endpoint: '/api/search',
        params: { query: 'test', limit: 10 },
      }

      debouncedApiCall(request)
      jest.advanceTimersByTime(500)

      expect(apiCall).toHaveBeenCalledWith(request)
    })
  })
})
