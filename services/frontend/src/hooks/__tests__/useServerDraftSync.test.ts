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

  it('never writes when disabled (read-only views), on tick or tab-hide', () => {
    renderHook(() => useServerDraftSync('p1', 't1', A, { enabled: false }))
    act(() => jest.advanceTimersByTime(60_000))
    Object.defineProperty(document, 'visibilityState', {
      value: 'hidden',
      configurable: true,
    })
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })
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

  it('reports saved status with a timestamp after a successful save', async () => {
    const { result } = renderHook(() => useServerDraftSync('p1', 't1', A))
    expect(result.current.status).toBe('idle')
    await act(async () => {
      jest.advanceTimersByTime(30_000)
    })
    expect(result.current.status).toBe('saved')
    expect(result.current.lastSavedAt).toBeInstanceOf(Date)
    expect(result.current.failures).toBe(0)
  })

  it('reports errors and retries with backoff instead of failing silently', async () => {
    mockSaveDraft.mockRejectedValue(new Error('network'))
    const { result } = renderHook(() => useServerDraftSync('p1', 't1', A))
    await act(async () => {
      jest.advanceTimersByTime(30_000)
    })
    expect(mockSaveDraft).toHaveBeenCalledTimes(1)
    expect(result.current.status).toBe('error')
    expect(result.current.failures).toBe(1)

    // First retry after 5s, second after a further 10s.
    await act(async () => {
      jest.advanceTimersByTime(5_000)
    })
    expect(mockSaveDraft).toHaveBeenCalledTimes(2)
    expect(result.current.failures).toBe(2)
    await act(async () => {
      jest.advanceTimersByTime(10_000)
    })
    expect(mockSaveDraft).toHaveBeenCalledTimes(3)

    // Connection comes back: the next retry succeeds and clears the error.
    mockSaveDraft.mockResolvedValue(undefined)
    await act(async () => {
      jest.advanceTimersByTime(20_000)
    })
    expect(result.current.status).toBe('saved')
    expect(result.current.failures).toBe(0)
  })

  it('saves immediately when the browser comes back online', async () => {
    mockSaveDraft.mockRejectedValueOnce(new Error('offline'))
    const { result } = renderHook(() => useServerDraftSync('p1', 't1', A))
    await act(async () => {
      jest.advanceTimersByTime(30_000)
    })
    expect(result.current.status).toBe('error')
    await act(async () => {
      window.dispatchEvent(new Event('online'))
    })
    expect(mockSaveDraft).toHaveBeenCalledTimes(2)
    expect(result.current.status).toBe('saved')
  })

  it('reports idle when disabled, even after an earlier error', async () => {
    mockSaveDraft.mockRejectedValue(new Error('network'))
    const { result, rerender } = renderHook(
      ({ enabled }) => useServerDraftSync('p1', 't1', A, { enabled }),
      { initialProps: { enabled: true } },
    )
    await act(async () => {
      jest.advanceTimersByTime(30_000)
    })
    expect(result.current.status).toBe('error')
    rerender({ enabled: false })
    expect(result.current.status).toBe('idle')
  })

  // Restorable checkpoints moved to the extended DraftCheckpointPanel; this
  // hook now only owns the generic 30s draft sync.
})
