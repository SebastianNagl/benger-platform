/**
 * @jest-environment jsdom
 */

import { renderHook, act } from '@testing-library/react'
import { useAutoSave } from '../useAutoSave'

describe('useAutoSave', () => {
  beforeEach(() => {
    jest.useFakeTimers()
    localStorage.clear()
  })

  afterEach(() => {
    jest.useRealTimers()
  })

  const emptyAnnotations = new Map()
  const emptyValues = new Map()
  const startTime = Date.now()

  it('should initialize with no draft when localStorage is empty', () => {
    const { result } = renderHook(() =>
      useAutoSave('task-1', emptyAnnotations, emptyValues, startTime)
    )

    expect(result.current.hasDraft).toBe(false)
    expect(result.current.isSaving).toBe(false)
    expect(result.current.lastSaved).toBeNull()
    expect(result.current.error).toBeNull()
  })

  it('should initialize with draft when localStorage has data', () => {
    const draftData = {
      taskId: 'task-1',
      annotations: [{ id: 'a1', value: 'test' }],
      componentValues: { field1: 'value1' },
      savedAt: Date.now() - 5000,
      leadTime: 10,
    }
    localStorage.setItem('benger_draft_task-1', JSON.stringify(draftData))

    const { result } = renderHook(() =>
      useAutoSave('task-1', emptyAnnotations, emptyValues, startTime)
    )

    expect(result.current.hasDraft).toBe(true)
    expect(result.current.lastSaved).not.toBeNull()
  })

  it('should load draft from localStorage', () => {
    const draftData = {
      taskId: 'task-2',
      annotations: [{ id: 'a1', value: 'test' }],
      componentValues: { field1: 'value1' },
      savedAt: Date.now(),
      leadTime: 5,
    }
    localStorage.setItem('benger_draft_task-2', JSON.stringify(draftData))

    const { result } = renderHook(() =>
      useAutoSave('task-2', emptyAnnotations, emptyValues, startTime)
    )

    const loaded = result.current.loadDraft()
    expect(loaded).not.toBeNull()
    expect(loaded!.taskId).toBe('task-2')
    expect(loaded!.annotations).toHaveLength(1)
  })

  it('should return null when loading draft without taskId', () => {
    const { result } = renderHook(() =>
      useAutoSave(null, emptyAnnotations, emptyValues, startTime)
    )

    const loaded = result.current.loadDraft()
    expect(loaded).toBeNull()
  })

  it('should clear draft from localStorage', async () => {
    localStorage.setItem(
      'benger_draft_task-3',
      JSON.stringify({
        taskId: 'task-3',
        annotations: [],
        componentValues: {},
        savedAt: Date.now(),
        leadTime: 0,
      })
    )

    const { result } = renderHook(() =>
      useAutoSave('task-3', emptyAnnotations, emptyValues, startTime)
    )

    expect(result.current.hasDraft).toBe(true)

    await act(async () => {
      await result.current.clearDraft()
    })

    expect(result.current.hasDraft).toBe(false)
    expect(localStorage.getItem('benger_draft_task-3')).toBeNull()
  })

  it('should trigger save when annotations change', () => {
    const annotations = new Map([['comp1', { id: 'a1', value: 'test' }]])
    const values = new Map<string, unknown>()

    const { result } = renderHook(() =>
      useAutoSave('task-4', annotations, values, startTime)
    )

    // Advance timers to trigger debounced save
    act(() => {
      jest.advanceTimersByTime(1500)
    })

    expect(result.current.hasDraft).toBe(true)
    expect(localStorage.getItem('benger_draft_task-4')).not.toBeNull()
  })

  it('should debounce saves (not save immediately)', () => {
    const annotations = new Map([['comp1', { id: 'a1', value: 'test' }]])

    renderHook(() =>
      useAutoSave('task-5', annotations, emptyValues, startTime)
    )

    // Before debounce timeout
    act(() => {
      jest.advanceTimersByTime(500)
    })

    expect(localStorage.getItem('benger_draft_task-5')).toBeNull()

    // After debounce timeout
    act(() => {
      jest.advanceTimersByTime(600)
    })

    expect(localStorage.getItem('benger_draft_task-5')).not.toBeNull()
  })

  it('should not save when disabled', () => {
    const annotations = new Map([['comp1', { id: 'a1', value: 'test' }]])

    renderHook(() =>
      useAutoSave('task-6', annotations, emptyValues, startTime, {
        enabled: false,
      })
    )

    act(() => {
      jest.advanceTimersByTime(2000)
    })

    expect(localStorage.getItem('benger_draft_task-6')).toBeNull()
  })

  it('should not save when taskId is null', () => {
    const annotations = new Map([['comp1', { id: 'a1', value: 'test' }]])

    renderHook(() =>
      useAutoSave(null, annotations, emptyValues, startTime)
    )

    act(() => {
      jest.advanceTimersByTime(2000)
    })

    // No localStorage entries starting with benger_draft_null
    expect(localStorage.getItem('benger_draft_null')).toBeNull()
  })

  it('should force save immediately', async () => {
    const annotations = new Map([['comp1', { id: 'a1', value: 'test' }]])

    const { result } = renderHook(() =>
      useAutoSave('task-7', annotations, emptyValues, startTime)
    )

    await act(async () => {
      await result.current.forceSave()
    })

    expect(localStorage.getItem('benger_draft_task-7')).not.toBeNull()
  })

  it('should save immediately with saveNow', async () => {
    const annotations = new Map([['comp1', { id: 'a1', value: 'test' }]])
    const values = new Map<string, unknown>()

    const { result } = renderHook(() =>
      useAutoSave('task-8', annotations, values, startTime)
    )

    await act(async () => {
      await result.current.saveNow()
    })

    expect(localStorage.getItem('benger_draft_task-8')).not.toBeNull()
  })

  it('should save with direct values via saveNow', async () => {
    const annotations = new Map([['comp1', { id: 'a1', value: 'test' }]])
    const values = new Map<string, unknown>()

    const { result } = renderHook(() =>
      useAutoSave('task-9', annotations, values, startTime)
    )

    await act(async () => {
      await result.current.saveNow({
        fieldName: 'myField',
        value: 'directValue',
      })
    })

    const saved = JSON.parse(
      localStorage.getItem('benger_draft_task-9')!
    )
    expect(saved.componentValues.myField).toBe('directValue')
  })

  it('should return null from loadServerDraft', async () => {
    const { result } = renderHook(() =>
      useAutoSave('task-10', emptyAnnotations, emptyValues, startTime)
    )

    let serverDraft: any
    await act(async () => {
      serverDraft = await result.current.loadServerDraft()
    })

    expect(serverDraft).toBeNull()
  })

  it('should handle corrupted localStorage gracefully', () => {
    localStorage.setItem('benger_draft_task-11', 'not-valid-json')

    const { result } = renderHook(() =>
      useAutoSave('task-11', emptyAnnotations, emptyValues, startTime)
    )

    expect(result.current.hasDraft).toBe(false)
  })

  it('should cleanup timer on unmount', () => {
    const annotations = new Map([['comp1', { id: 'a1', value: 'test' }]])

    const { unmount } = renderHook(() =>
      useAutoSave('task-12', annotations, emptyValues, startTime)
    )

    unmount()

    // Advance time - should not throw
    act(() => {
      jest.advanceTimersByTime(2000)
    })
  })
})
