/**
 * @jest-environment jsdom
 */

import { renderHook } from '@testing-library/react'
import { act } from 'react'

import { registerWritingPresenceReporter } from '@/lib/extensions/writingPresence'

import { useServerDraftSync } from '../useServerDraftSync'

const mockSaveDraft = jest.fn()
const mockTouchPresence = jest.fn()
jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    saveDraft: (...args: any[]) => mockSaveDraft(...args),
  },
}))

const setVisibility = (value: 'visible' | 'hidden') =>
  Object.defineProperty(document, 'visibilityState', {
    value,
    configurable: true,
  })

const A = [{ from_name: 'loesung', value: { markdown: 'x' } }]

describe('useServerDraftSync', () => {
  beforeEach(() => {
    jest.useFakeTimers()
    mockSaveDraft.mockReset().mockResolvedValue(undefined)
    mockTouchPresence.mockReset().mockResolvedValue(undefined)
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

  describe('presence reporter (extension point)', () => {
    beforeEach(() => {
      setVisibility('visible')
      registerWritingPresenceReporter((...args) => mockTouchPresence(...args))
    })
    afterEach(() => registerWritingPresenceReporter(null))

    it('sends nothing without a registered reporter (community edition)', async () => {
      registerWritingPresenceReporter(null)
      renderHook(() => useServerDraftSync('p1', 't1', []))
      await act(async () => {
        jest.advanceTimersByTime(60_000)
      })
      expect(mockTouchPresence).not.toHaveBeenCalled()
    })

    it('touches on mount and on every tick without a change', async () => {
      renderHook(() => useServerDraftSync('p1', 't1', []))
      await act(async () => {})
      expect(mockTouchPresence).toHaveBeenCalledWith('p1', 't1', true)
      await act(async () => {
        jest.advanceTimersByTime(30_000)
      })
      expect(mockTouchPresence).toHaveBeenCalledTimes(2)
      expect(mockSaveDraft).not.toHaveBeenCalled()
    })

    it('a tick that saves the draft sends no extra presence report', async () => {
      renderHook(() => useServerDraftSync('p1', 't1', A))
      await act(async () => {})
      mockTouchPresence.mockClear()
      await act(async () => {
        jest.advanceTimersByTime(30_000)
      })
      expect(mockSaveDraft).toHaveBeenCalledTimes(1)
      expect(mockTouchPresence).not.toHaveBeenCalled()
    })

    it('reports a hidden tab, also after the flush on hide', async () => {
      renderHook(() => useServerDraftSync('p1', 't1', A))
      await act(async () => {})
      setVisibility('hidden')
      await act(async () => {
        document.dispatchEvent(new Event('visibilitychange'))
      })
      expect(mockSaveDraft).toHaveBeenCalledTimes(1)
      expect(mockTouchPresence).toHaveBeenLastCalledWith('p1', 't1', false)
    })

    it('spreads the first tick over the period, then keeps a 30s rhythm', async () => {
      const random = jest.spyOn(Math, 'random').mockReturnValue(0.5)
      try {
        renderHook(() => useServerDraftSync('p1', 't1', A))
        await act(async () => {
          jest.advanceTimersByTime(14_999)
        })
        expect(mockSaveDraft).not.toHaveBeenCalled()
        await act(async () => {
          jest.advanceTimersByTime(1)
        })
        expect(mockSaveDraft).toHaveBeenCalledTimes(1)
        mockTouchPresence.mockClear()
        await act(async () => {
          jest.advanceTimersByTime(30_000)
        })
        // Unchanged text on the next tick: a presence report instead of a save.
        expect(mockSaveDraft).toHaveBeenCalledTimes(1)
        expect(mockTouchPresence).toHaveBeenCalledTimes(1)
      } finally {
        random.mockRestore()
      }
    })

    it('never touches when disabled', async () => {
      renderHook(() => useServerDraftSync('p1', 't1', A, { enabled: false }))
      await act(async () => {
        jest.advanceTimersByTime(60_000)
      })
      expect(mockTouchPresence).not.toHaveBeenCalled()
    })

    it('a failing presence report stays invisible to the writer', async () => {
      mockTouchPresence.mockRejectedValue(new Error('offline'))
      const { result } = renderHook(() => useServerDraftSync('p1', 't1', []))
      await act(async () => {
        jest.advanceTimersByTime(30_000)
      })
      expect(result.current.status).toBe('idle')
    })
  })
})
