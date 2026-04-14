/**
 * @jest-environment jsdom
 *
 * useAutoSave branch coverage extension tests.
 * Targets: localStorage error paths (save/load/clear failure),
 * clearDraft with null taskId, empty annotations save skipping,
 * and saveToLocal with no data.
 */

import { renderHook, act } from '@testing-library/react'
import { useAutoSave } from '../useAutoSave'

describe('useAutoSave - branch coverage extensions', () => {
  beforeEach(() => {
    jest.useFakeTimers()
    localStorage.clear()
    jest.clearAllMocks()
  })

  afterEach(() => {
    jest.useRealTimers()
    jest.restoreAllMocks()
  })

  const startTime = Date.now()
  const emptyAnnotations = new Map()
  const emptyValues = new Map()

  describe('localStorage error handling', () => {
    it('should handle localStorage.setItem throwing during save', () => {
      const annotations = new Map([['comp1', { id: 'a1', value: 'test', from_name: 'a', to_name: 'b', type: 'text' }]])
      const consoleSpy = jest.spyOn(console, 'warn').mockImplementation()
      const originalSetItem = Storage.prototype.setItem

      const { result } = renderHook(() =>
        useAutoSave('task-err-1', annotations, emptyValues, startTime)
      )

      // Let the auto-trigger fire, then mock setItem to throw
      Storage.prototype.setItem = jest.fn(() => {
        throw new Error('QuotaExceeded')
      })

      act(() => {
        jest.advanceTimersByTime(1500)
      })

      // Should handle error gracefully
      expect(consoleSpy).toHaveBeenCalledWith(
        'Failed to save draft to localStorage:',
        expect.any(Error)
      )

      Storage.prototype.setItem = originalSetItem
      consoleSpy.mockRestore()
    })

    it('should handle localStorage.getItem throwing during load', () => {
      const consoleSpy = jest.spyOn(console, 'warn').mockImplementation()

      // Set up valid data first
      localStorage.setItem('benger_draft_task-err-2', JSON.stringify({
        taskId: 'task-err-2',
        annotations: [{ id: 'a1', value: 'test' }],
        componentValues: {},
        savedAt: Date.now(),
        leadTime: 0,
      }))

      // Mock getItem to throw
      const originalGetItem = Storage.prototype.getItem
      Storage.prototype.getItem = jest.fn(() => {
        throw new Error('SecurityError')
      })

      const { result } = renderHook(() =>
        useAutoSave('task-err-2', emptyAnnotations, emptyValues, startTime)
      )

      // loadDraft should return null and not throw
      const loaded = result.current.loadDraft()
      expect(loaded).toBeNull()

      Storage.prototype.getItem = originalGetItem
      consoleSpy.mockRestore()
    })

    it('should handle localStorage.removeItem throwing during clear', async () => {
      const consoleSpy = jest.spyOn(console, 'warn').mockImplementation()

      localStorage.setItem('benger_draft_task-err-3', JSON.stringify({
        taskId: 'task-err-3',
        annotations: [{ id: 'a1' }],
        componentValues: {},
        savedAt: Date.now(),
        leadTime: 0,
      }))

      const { result } = renderHook(() =>
        useAutoSave('task-err-3', emptyAnnotations, emptyValues, startTime)
      )

      // Mock removeItem to throw
      const originalRemoveItem = Storage.prototype.removeItem
      Storage.prototype.removeItem = jest.fn(() => {
        throw new Error('SecurityError')
      })

      // clearDraft should handle the error
      await act(async () => {
        await result.current.clearDraft()
      })

      expect(consoleSpy).toHaveBeenCalledWith(
        'Failed to clear draft from localStorage:',
        expect.any(Error)
      )

      Storage.prototype.removeItem = originalRemoveItem
      consoleSpy.mockRestore()
    })
  })

  describe('null/empty edge cases', () => {
    it('should not save when serializeData returns null (no taskId)', async () => {
      const annotations = new Map([['comp1', { id: 'a1', value: 'test', from_name: 'a', to_name: 'b', type: 'text' }]])

      const { result } = renderHook(() =>
        useAutoSave(null, annotations, emptyValues, startTime)
      )

      // Force save should be a no-op
      await act(async () => {
        await result.current.forceSave()
      })

      // No draft should exist
      expect(result.current.hasDraft).toBe(false)
    })

    it('should not save when annotations array is empty', () => {
      // serializeData will produce empty annotations array
      const { result } = renderHook(() =>
        useAutoSave('task-empty', emptyAnnotations, emptyValues, startTime)
      )

      act(() => {
        result.current.triggerSave()
        jest.advanceTimersByTime(1500)
      })

      // Should not save because annotations.length === 0
      expect(localStorage.getItem('benger_draft_task-empty')).toBeNull()
    })

    it('should not clear draft when taskId is null', async () => {
      const { result } = renderHook(() =>
        useAutoSave(null, emptyAnnotations, emptyValues, startTime)
      )

      await act(async () => {
        await result.current.clearDraft()
      })

      // Should be a no-op, not crash
      expect(result.current.hasDraft).toBe(false)
    })

    it('should initialize with hasDraft=false when taskId is null', () => {
      const { result } = renderHook(() =>
        useAutoSave(null, emptyAnnotations, emptyValues, startTime)
      )

      expect(result.current.hasDraft).toBe(false)
      expect(result.current.lastSaved).toBeNull()
    })
  })

  describe('saveNow with directValues', () => {
    it('should merge directValues into componentValues before saving', async () => {
      const annotations = new Map([['comp1', { id: 'a1', value: 'test', from_name: 'a', to_name: 'b', type: 'text' }]])
      const values = new Map<string, unknown>([['existingField', 'existingValue']])

      const { result } = renderHook(() =>
        useAutoSave('task-direct', annotations, values, startTime)
      )

      await act(async () => {
        await result.current.saveNow({
          fieldName: 'newField',
          value: 'newValue',
        })
      })

      const saved = JSON.parse(localStorage.getItem('benger_draft_task-direct')!)
      expect(saved.componentValues.newField).toBe('newValue')
      expect(saved.componentValues.existingField).toBe('existingValue')
    })

    it('should save without directValues when not provided', async () => {
      const annotations = new Map([['comp1', { id: 'a1', value: 'test', from_name: 'a', to_name: 'b', type: 'text' }]])

      const { result } = renderHook(() =>
        useAutoSave('task-no-direct', annotations, emptyValues, startTime)
      )

      await act(async () => {
        await result.current.saveNow()
      })

      expect(localStorage.getItem('benger_draft_task-no-direct')).not.toBeNull()
    })
  })

  describe('triggerSave debouncing', () => {
    it('should reset debounce timer on subsequent calls', () => {
      const annotations = new Map([['comp1', { id: 'a1', value: 'test', from_name: 'a', to_name: 'b', type: 'text' }]])

      const { result } = renderHook(() =>
        useAutoSave('task-debounce', annotations, emptyValues, startTime)
      )

      // Trigger first save
      act(() => {
        result.current.triggerSave()
      })

      // Advance 500ms (less than debounce time)
      act(() => {
        jest.advanceTimersByTime(500)
      })

      // Trigger again to reset the timer
      act(() => {
        result.current.triggerSave()
      })

      // Advance 500ms more - total 1000ms but should not have saved yet
      // because the timer was reset
      act(() => {
        jest.advanceTimersByTime(500)
      })

      // Not saved yet since debounce reset
      expect(localStorage.getItem('benger_draft_task-debounce')).toBeNull()

      // Advance past debounce threshold
      act(() => {
        jest.advanceTimersByTime(600)
      })

      // Now it should be saved
      expect(localStorage.getItem('benger_draft_task-debounce')).not.toBeNull()
    })
  })
})
