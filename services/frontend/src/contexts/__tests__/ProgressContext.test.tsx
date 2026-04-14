/**
 * @jest-environment jsdom
 */

import { act, renderHook } from '@testing-library/react'
import React from 'react'
import { ProgressProvider, useProgress } from '../ProgressContext'

describe('ProgressContext', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    jest.useFakeTimers()
  })

  afterEach(() => {
    jest.runOnlyPendingTimers()
    jest.useRealTimers()
  })

  describe('useProgress hook', () => {
    it('throws error when used outside provider', () => {
      const consoleErrorSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})

      try {
        renderHook(() => useProgress())
      } catch (error) {
        expect(error).toEqual(
          new Error('useProgress must be used within a ProgressProvider')
        )
      }

      consoleErrorSpy.mockRestore()
    })

    it('returns context when used inside provider', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      expect(result.current).toBeDefined()
      expect(result.current.progressItems).toBeDefined()
      expect(result.current.startProgress).toBeDefined()
      expect(result.current.updateProgress).toBeDefined()
      expect(result.current.completeProgress).toBeDefined()
      expect(result.current.removeProgress).toBeDefined()
    })
  })

  describe('ProgressProvider initialization', () => {
    it('initializes with empty progress items', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      expect(result.current.progressItems).toEqual([])
    })

    it('renders children correctly', () => {
      const testChild = <div data-testid="test-child">Test</div>
      const { container } = require('@testing-library/react').render(
        <ProgressProvider>{testChild}</ProgressProvider>
      )

      expect(container.querySelector('[data-testid="test-child"]')).toBeTruthy()
    })
  })

  describe('startProgress function', () => {
    it('starts progress with basic options', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-1', 'Test Operation')
      })

      expect(result.current.progressItems).toHaveLength(1)
      expect(result.current.progressItems[0]).toMatchObject({
        id: 'test-1',
        label: 'Test Operation',
        progress: 0,
        status: 'running',
      })
    })

    it('starts progress with sublabel', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-1', 'Test Operation', {
          sublabel: 'Processing file 1 of 10',
        })
      })

      expect(result.current.progressItems[0].sublabel).toBe(
        'Processing file 1 of 10'
      )
    })

    it('starts progress with indeterminate flag', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-1', 'Test Operation', {
          indeterminate: true,
        })
      })

      expect(result.current.progressItems[0].indeterminate).toBe(true)
    })

    it('starts progress with cancel handler', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })
      const cancelHandler = jest.fn()

      act(() => {
        result.current.startProgress('test-1', 'Test Operation', {
          onCancel: cancelHandler,
        })
      })

      expect(result.current.progressItems[0].onCancel).toBe(cancelHandler)
    })

    it('replaces existing progress with same id', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-1', 'First Operation')
      })

      act(() => {
        result.current.startProgress('test-1', 'Second Operation')
      })

      expect(result.current.progressItems).toHaveLength(1)
      expect(result.current.progressItems[0].label).toBe('Second Operation')
    })

    it('supports multiple concurrent progress items', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-1', 'Operation 1')
        result.current.startProgress('test-2', 'Operation 2')
        result.current.startProgress('test-3', 'Operation 3')
      })

      expect(result.current.progressItems).toHaveLength(3)
    })

    it('starts progress with all options', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })
      const cancelHandler = jest.fn()

      act(() => {
        result.current.startProgress('test-1', 'Full Options Test', {
          sublabel: 'Step 1',
          indeterminate: false,
          onCancel: cancelHandler,
        })
      })

      expect(result.current.progressItems[0]).toMatchObject({
        id: 'test-1',
        label: 'Full Options Test',
        sublabel: 'Step 1',
        progress: 0,
        status: 'running',
        indeterminate: false,
      })
      expect(result.current.progressItems[0].onCancel).toBe(cancelHandler)
    })
  })

  describe('updateProgress function', () => {
    it('updates progress value', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-1', 'Test Operation')
      })

      act(() => {
        result.current.updateProgress('test-1', 50)
      })

      expect(result.current.progressItems[0].progress).toBe(50)
    })

    it('updates sublabel', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-1', 'Test Operation', {
          sublabel: 'Initial',
        })
      })

      act(() => {
        result.current.updateProgress('test-1', 50, 'Updated')
      })

      expect(result.current.progressItems[0].sublabel).toBe('Updated')
    })

    it('clamps progress to 0-100 range (below 0)', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-1', 'Test Operation')
      })

      act(() => {
        result.current.updateProgress('test-1', -10)
      })

      expect(result.current.progressItems[0].progress).toBe(0)
    })

    it('clamps progress to 0-100 range (above 100)', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-1', 'Test Operation')
      })

      act(() => {
        result.current.updateProgress('test-1', 150)
      })

      expect(result.current.progressItems[0].progress).toBe(100)
    })

    it('preserves sublabel when not provided', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-1', 'Test Operation', {
          sublabel: 'Original',
        })
      })

      act(() => {
        result.current.updateProgress('test-1', 50)
      })

      expect(result.current.progressItems[0].sublabel).toBe('Original')
    })

    it('does not affect other progress items', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-1', 'Operation 1')
        result.current.startProgress('test-2', 'Operation 2')
      })

      act(() => {
        result.current.updateProgress('test-1', 75)
      })

      expect(result.current.progressItems[0].progress).toBe(75)
      expect(result.current.progressItems[1].progress).toBe(0)
    })

    it('handles updates to non-existent items gracefully', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.updateProgress('non-existent', 50)
      })

      expect(result.current.progressItems).toHaveLength(0)
    })

    it('updates progress with both value and sublabel', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-1', 'Test Operation')
      })

      act(() => {
        result.current.updateProgress('test-1', 33, 'Step 1 of 3')
      })

      expect(result.current.progressItems[0].progress).toBe(33)
      expect(result.current.progressItems[0].sublabel).toBe('Step 1 of 3')
    })
  })

  describe('completeProgress function', () => {
    it('completes progress with success status', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-1', 'Test Operation')
      })

      act(() => {
        result.current.completeProgress('test-1', 'success')
      })

      expect(result.current.progressItems[0].progress).toBe(100)
      expect(result.current.progressItems[0].status).toBe('success')
    })

    it('completes progress with error status', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-1', 'Test Operation')
      })

      act(() => {
        result.current.completeProgress('test-1', 'error')
      })

      expect(result.current.progressItems[0].progress).toBe(100)
      expect(result.current.progressItems[0].status).toBe('error')
    })

    it('defaults to success status when not specified', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-1', 'Test Operation')
      })

      act(() => {
        result.current.completeProgress('test-1')
      })

      expect(result.current.progressItems[0].status).toBe('success')
    })

    it('auto-removes success items after delay', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-1', 'Test Operation')
      })

      act(() => {
        result.current.completeProgress('test-1', 'success')
      })

      expect(result.current.progressItems).toHaveLength(1)

      act(() => {
        jest.advanceTimersByTime(3000)
      })

      expect(result.current.progressItems).toHaveLength(0)
    })

    it('does not auto-remove error items', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-1', 'Test Operation')
      })

      act(() => {
        result.current.completeProgress('test-1', 'error')
      })

      act(() => {
        jest.advanceTimersByTime(5000)
      })

      expect(result.current.progressItems).toHaveLength(1)
    })

    it('handles completion of non-existent items', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.completeProgress('non-existent', 'success')
      })

      expect(result.current.progressItems).toHaveLength(0)
    })

    it('does not affect other progress items', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-1', 'Operation 1')
        result.current.startProgress('test-2', 'Operation 2')
      })

      act(() => {
        result.current.completeProgress('test-1', 'success')
      })

      expect(result.current.progressItems[0].status).toBe('success')
      expect(result.current.progressItems[1].status).toBe('running')
    })
  })

  describe('removeProgress function', () => {
    it('removes progress item', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-1', 'Test Operation')
      })

      expect(result.current.progressItems).toHaveLength(1)

      act(() => {
        result.current.removeProgress('test-1')
      })

      expect(result.current.progressItems).toHaveLength(0)
    })

    it('handles removal of non-existent items', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.removeProgress('non-existent')
      })

      expect(result.current.progressItems).toHaveLength(0)
    })

    it('only removes specified item', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-1', 'Operation 1')
        result.current.startProgress('test-2', 'Operation 2')
        result.current.startProgress('test-3', 'Operation 3')
      })

      act(() => {
        result.current.removeProgress('test-2')
      })

      expect(result.current.progressItems).toHaveLength(2)
      expect(
        result.current.progressItems.find((p) => p.id === 'test-1')
      ).toBeTruthy()
      expect(
        result.current.progressItems.find((p) => p.id === 'test-3')
      ).toBeTruthy()
      expect(
        result.current.progressItems.find((p) => p.id === 'test-2')
      ).toBeFalsy()
    })

    it('can remove completed items', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-1', 'Test Operation')
        result.current.completeProgress('test-1', 'success')
      })

      act(() => {
        result.current.removeProgress('test-1')
      })

      expect(result.current.progressItems).toHaveLength(0)
    })
  })

  describe('complex workflows', () => {
    it('handles full progress lifecycle', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-1', 'Processing')
      })

      act(() => {
        result.current.updateProgress('test-1', 25, 'Step 1')
      })

      act(() => {
        result.current.updateProgress('test-1', 50, 'Step 2')
      })

      act(() => {
        result.current.updateProgress('test-1', 75, 'Step 3')
      })

      act(() => {
        result.current.completeProgress('test-1', 'success')
      })

      expect(result.current.progressItems[0]).toMatchObject({
        progress: 100,
        status: 'success',
        sublabel: 'Step 3',
      })

      act(() => {
        jest.advanceTimersByTime(3000)
      })

      expect(result.current.progressItems).toHaveLength(0)
    })

    it('handles multiple concurrent operations', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('upload', 'Uploading file')
        result.current.startProgress('process', 'Processing data')
        result.current.startProgress('analyze', 'Analyzing results')
      })

      act(() => {
        result.current.updateProgress('upload', 100)
        result.current.completeProgress('upload', 'success')
      })

      act(() => {
        result.current.updateProgress('process', 50)
      })

      expect(result.current.progressItems).toHaveLength(3)
      expect(
        result.current.progressItems.find((p) => p.id === 'upload')?.status
      ).toBe('success')
      expect(
        result.current.progressItems.find((p) => p.id === 'process')?.progress
      ).toBe(50)
      expect(
        result.current.progressItems.find((p) => p.id === 'analyze')?.status
      ).toBe('running')
    })

    it('handles error scenarios', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-1', 'Risky Operation')
        result.current.updateProgress('test-1', 30)
      })

      act(() => {
        result.current.completeProgress('test-1', 'error')
      })

      expect(result.current.progressItems[0]).toMatchObject({
        progress: 100,
        status: 'error',
      })

      act(() => {
        jest.advanceTimersByTime(5000)
      })

      expect(result.current.progressItems).toHaveLength(1)
    })

    it('handles restart of same operation', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-1', 'Operation')
        result.current.updateProgress('test-1', 50)
      })

      act(() => {
        result.current.startProgress('test-1', 'Operation Restarted')
      })

      expect(result.current.progressItems[0]).toMatchObject({
        id: 'test-1',
        label: 'Operation Restarted',
        progress: 0,
        status: 'running',
      })
    })

    it('handles rapid updates', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-1', 'Fast Operation')
      })

      act(() => {
        for (let i = 0; i <= 100; i += 10) {
          result.current.updateProgress('test-1', i)
        }
      })

      expect(result.current.progressItems[0].progress).toBe(100)
    })
  })

  describe('edge cases', () => {
    it('handles empty string ids', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('', 'Empty ID Test')
      })

      expect(result.current.progressItems).toHaveLength(1)
    })

    it('handles empty string labels', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-1', '')
      })

      expect(result.current.progressItems[0].label).toBe('')
    })

    it('handles special characters in ids', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-@#$%', 'Special ID')
      })

      expect(result.current.progressItems[0].id).toBe('test-@#$%')
    })

    it('handles very long labels', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })
      const longLabel = 'A'.repeat(1000)

      act(() => {
        result.current.startProgress('test-1', longLabel)
      })

      expect(result.current.progressItems[0].label).toBe(longLabel)
    })

    it('handles fractional progress values', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-1', 'Test')
        result.current.updateProgress('test-1', 33.333)
      })

      expect(result.current.progressItems[0].progress).toBe(33.333)
    })

    it('handles NaN progress values', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-1', 'Test')
        result.current.updateProgress('test-1', NaN)
      })

      expect(isNaN(result.current.progressItems[0].progress)).toBe(true)
    })

    it('handles cancel handler invocation', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })
      const cancelHandler = jest.fn()

      act(() => {
        result.current.startProgress('test-1', 'Cancellable Operation', {
          onCancel: cancelHandler,
        })
      })

      const onCancel = result.current.progressItems[0].onCancel
      expect(onCancel).toBeDefined()

      if (onCancel) {
        onCancel()
        expect(cancelHandler).toHaveBeenCalled()
      }
    })

    it('handles undefined options', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-1', 'Test', undefined)
      })

      expect(result.current.progressItems[0]).toMatchObject({
        id: 'test-1',
        label: 'Test',
        progress: 0,
        status: 'running',
      })
    })

    it('preserves other properties when updating', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })
      const cancelHandler = jest.fn()

      act(() => {
        result.current.startProgress('test-1', 'Test', {
          indeterminate: true,
          onCancel: cancelHandler,
        })
      })

      act(() => {
        result.current.updateProgress('test-1', 50)
      })

      expect(result.current.progressItems[0].indeterminate).toBe(true)
      expect(result.current.progressItems[0].onCancel).toBe(cancelHandler)
    })
  })

  describe('auto-removal timing', () => {
    it('does not remove item before timeout', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-1', 'Test')
        result.current.completeProgress('test-1', 'success')
      })

      act(() => {
        jest.advanceTimersByTime(2999)
      })

      expect(result.current.progressItems).toHaveLength(1)
    })

    it('removes item exactly at timeout', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-1', 'Test')
        result.current.completeProgress('test-1', 'success')
      })

      act(() => {
        jest.advanceTimersByTime(3000)
      })

      expect(result.current.progressItems).toHaveLength(0)
    })

    it('handles multiple success completions with staggered timeouts', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <ProgressProvider>{children}</ProgressProvider>
      )

      const { result } = renderHook(() => useProgress(), { wrapper })

      act(() => {
        result.current.startProgress('test-1', 'Test 1')
        result.current.completeProgress('test-1', 'success')
      })

      act(() => {
        jest.advanceTimersByTime(1000)
      })

      act(() => {
        result.current.startProgress('test-2', 'Test 2')
        result.current.completeProgress('test-2', 'success')
      })

      act(() => {
        jest.advanceTimersByTime(2000)
      })

      expect(result.current.progressItems).toHaveLength(1)
      expect(result.current.progressItems[0].id).toBe('test-2')

      act(() => {
        jest.advanceTimersByTime(1000)
      })

      expect(result.current.progressItems).toHaveLength(0)
    })
  })
})
