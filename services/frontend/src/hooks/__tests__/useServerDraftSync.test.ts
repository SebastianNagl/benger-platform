/**
 * @jest-environment jsdom
 */

import { renderHook } from '@testing-library/react'
import { act } from 'react'

import { useServerDraftSync } from '../useServerDraftSync'

const mockSaveDraft = jest.fn()
jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    saveDraft: (...args: any[]) => mockSaveDraft(...args),
  },
}))

const A = [{ from_name: 'loesung', value: { markdown: 'x' } }]

describe('useServerDraftSync', () => {
  beforeEach(() => {
    jest.useFakeTimers()
    mockSaveDraft.mockReset().mockResolvedValue(undefined)
  })
  afterEach(() => {
    jest.useRealTimers()
  })

  it('PUTs the draft on the 30s interval when annotations are present', () => {
    renderHook(() => useServerDraftSync('p1', 't1', A))
    expect(mockSaveDraft).not.toHaveBeenCalled() // nothing before the first tick
    act(() => {
      jest.advanceTimersByTime(30_000)
    })
    expect(mockSaveDraft).toHaveBeenCalledWith('p1', 't1', A)
  })

  it('does not re-send an unchanged result (de-dup)', async () => {
    renderHook(() => useServerDraftSync('p1', 't1', A))
    // await each tick so the post-save ref update (after the await) flushes
    // before the next interval fires.
    await act(async () => {
      jest.advanceTimersByTime(30_000)
    })
    await act(async () => {
      jest.advanceTimersByTime(30_000)
    })
    expect(mockSaveDraft).toHaveBeenCalledTimes(1)
  })

  it('skips empty annotations', () => {
    renderHook(() => useServerDraftSync('p1', 't1', []))
    act(() => jest.advanceTimersByTime(30_000))
    expect(mockSaveDraft).not.toHaveBeenCalled()
  })

  it('is inert without a project/task id', () => {
    renderHook(() => useServerDraftSync(undefined, undefined, A))
    act(() => jest.advanceTimersByTime(60_000))
    expect(mockSaveDraft).not.toHaveBeenCalled()
  })

  it('saves immediately when the tab becomes hidden', () => {
    renderHook(() => useServerDraftSync('p1', 't1', A))
    Object.defineProperty(document, 'visibilityState', {
      value: 'hidden',
      configurable: true,
    })
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })
    expect(mockSaveDraft).toHaveBeenCalledWith('p1', 't1', A)
  })

  // Restorable checkpoints moved to the extended DraftCheckpointPanel; this
  // hook now only owns the generic 30s draft sync.
})
