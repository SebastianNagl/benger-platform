/**
 * @jest-environment jsdom
 *
 * Branch coverage for the SSE reconnection / error-recovery logic in
 * useNotifications, plus a few remaining guard branches the existing suites
 * leave uncovered:
 *
 *  - onerror with readyState===2: schedules a reconnect (lines 254-285),
 *    the reconnect timeout firing and creating a fresh EventSource,
 *    and the give-up-after-MAX_RECONNECT_ATTEMPTS path (lines 266-271).
 *  - onerror with readyState!==2: no reconnect scheduled (branch 257 false).
 *  - markAsRead's map keeps non-matching notifications untouched (ternary
 *    false branch, line 94).
 *  - fetchPreferences error path returns {} (lines 146-147).
 *
 * Mirrors the MockEventSource / mockApiClient idiom from
 * useNotifications.branch.test.tsx.
 */

import { useAuth } from '@/contexts/AuthContext'
import { act, renderHook, waitFor } from '@testing-library/react'
import React from 'react'
import { useNotifications } from '../useNotifications'

// Toast mocking is handled by setupTests.ts.

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => key,
    locale: 'en',
    isReady: true,
  }),
}))

jest.mock('@/lib/notificationTranslation', () => ({
  getTranslatedNotification: jest.fn((_t: any, notification: any) => ({
    title: notification.title || 'Translated Title',
    message: notification.message || 'Translated Message',
  })),
}))

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))

class MockEventSource {
  url: string
  withCredentials: boolean
  readyState: number = 0
  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null

  constructor(url: string, options?: { withCredentials?: boolean }) {
    this.url = url
    this.withCredentials = options?.withCredentials || false
    Promise.resolve().then(() => {
      this.readyState = 1
      if (this.onopen) this.onopen(new Event('open'))
    })
  }

  close() {
    this.readyState = 2
  }

  simulateMessage(data: any) {
    if (this.onmessage) {
      this.onmessage(new MessageEvent('message', { data: JSON.stringify(data) }))
    }
  }

  // Simulate the browser closing the stream then firing onerror.
  simulateClosedError() {
    this.readyState = 2
    if (this.onerror) this.onerror(new Event('error'))
  }

  // Simulate a transient error where the stream is NOT closed.
  simulateTransientError() {
    this.readyState = 1
    if (this.onerror) this.onerror(new Event('error'))
  }
}

// @ts-ignore
global.EventSource = MockEventSource

const mockApiClient = {
  getNotifications: jest.fn(),
  getUnreadNotificationCount: jest.fn(),
  markNotificationAsRead: jest.fn(),
  markAllNotificationsAsRead: jest.fn(),
  getNotificationPreferences: jest.fn(),
  updateNotificationPreferences: jest.fn(),
  createNotificationStream: jest.fn(),
}

const mockUser = { id: '1', username: 'testuser', email: 'test@example.com' }

const wrapper = ({ children }: { children: React.ReactNode }) => <>{children}</>

const flushMicrotasks = async () => {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}

beforeEach(() => {
  jest.clearAllMocks()
  jest.useFakeTimers()
  ;(useAuth as jest.Mock).mockReturnValue({
    user: mockUser,
    apiClient: mockApiClient as any,
  })
  mockApiClient.getNotifications.mockResolvedValue([])
  mockApiClient.getUnreadNotificationCount.mockResolvedValue({ count: 0 })
  mockApiClient.getNotificationPreferences.mockResolvedValue({})
  mockApiClient.createNotificationStream.mockImplementation(
    () => new MockEventSource('/api/notifications/stream')
  )
})

afterEach(() => {
  jest.useRealTimers()
})

describe('useNotifications - SSE reconnection branches', () => {
  it('schedules a reconnect when the stream errors after closing (readyState 2)', async () => {
    renderHook(() => useNotifications(), { wrapper })

    await waitFor(() => {
      expect(mockApiClient.createNotificationStream).toHaveBeenCalledTimes(1)
    })
    const first = mockApiClient.createNotificationStream.mock.results[0]
      .value as MockEventSource
    await flushMicrotasks()

    act(() => {
      first.simulateClosedError()
    })

    // First backoff delay is 1000ms (1000 * attempt 1). Fire it.
    await act(async () => {
      jest.advanceTimersByTime(1000)
      await Promise.resolve()
    })

    // A brand new EventSource was created by the reconnect timeout.
    expect(mockApiClient.createNotificationStream).toHaveBeenCalledTimes(2)
  })

  it('does NOT reconnect when the error leaves the stream open (readyState 1)', async () => {
    renderHook(() => useNotifications(), { wrapper })

    await waitFor(() => {
      expect(mockApiClient.createNotificationStream).toHaveBeenCalledTimes(1)
    })
    const first = mockApiClient.createNotificationStream.mock.results[0]
      .value as MockEventSource
    await flushMicrotasks()

    act(() => {
      first.simulateTransientError()
    })

    await act(async () => {
      jest.advanceTimersByTime(5000)
      await Promise.resolve()
    })

    // readyState !== 2 -> the whole reconnect block is skipped.
    expect(mockApiClient.createNotificationStream).toHaveBeenCalledTimes(1)
  })

  it('gives up after MAX_RECONNECT_ATTEMPTS (5) consecutive failures', async () => {
    const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {})

    // Reconnected streams must error BEFORE their async onopen fires, otherwise
    // onopen resets reconnectAttemptsRef to 0 (line 207) and the cap is never
    // reached. We error each new stream synchronously inside the same tick the
    // reconnect timer creates it, before any microtask flush runs its onopen.
    renderHook(() => useNotifications(), { wrapper })
    await waitFor(() => {
      expect(mockApiClient.createNotificationStream).toHaveBeenCalledTimes(1)
    })
    await flushMicrotasks()

    // Cycle: error current stream (closed) -> backoff timer fires -> new stream
    // created -> error it synchronously (no await => its onopen never runs =>
    // attempts keeps climbing). After 5 increments the 6th error bails.
    const errorLatest = () => {
      const idx = mockApiClient.createNotificationStream.mock.results.length - 1
      const es = mockApiClient.createNotificationStream.mock.results[idx]
        .value as MockEventSource
      es.simulateClosedError()
    }

    act(() => {
      // Initial stream error -> attempts 0->1, schedules reconnect (delay 1000).
      errorLatest()
    })

    for (let attempt = 1; attempt <= 5; attempt++) {
      const delay = Math.min(1000 * attempt, 5000)
      act(() => {
        // Fire the backoff timer: creates a new stream synchronously...
        jest.advanceTimersByTime(delay)
        // ...and error it immediately, before its onopen microtask can run.
        errorLatest()
      })
    }

    // 1 initial + 5 reconnect streams = 6 createNotificationStream calls.
    // The final error saw attempts===5 (>= MAX) and bailed: no 7th stream.
    expect(mockApiClient.createNotificationStream).toHaveBeenCalledTimes(6)
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('giving up'))
    warnSpy.mockRestore()
  })
})

describe('useNotifications - remaining guard branches', () => {
  it('markAsRead leaves non-matching notifications untouched', async () => {
    mockApiClient.getNotifications.mockResolvedValue([
      {
        id: 'a',
        type: 't',
        title: 'A',
        message: 'm',
        is_read: false,
        created_at: 'now',
      },
      {
        id: 'b',
        type: 't',
        title: 'B',
        message: 'm',
        is_read: false,
        created_at: 'now',
      },
    ])
    mockApiClient.getUnreadNotificationCount.mockResolvedValue({ count: 2 })
    mockApiClient.markNotificationAsRead.mockResolvedValue({})

    const { result } = renderHook(() => useNotifications(), { wrapper })

    await waitFor(() => {
      expect(result.current.notifications).toHaveLength(2)
    })

    await act(async () => {
      await result.current.markAsRead('a')
    })

    const a = result.current.notifications.find((n) => n.id === 'a')
    const b = result.current.notifications.find((n) => n.id === 'b')
    // The matched one flips to read...
    expect(a?.is_read).toBe(true)
    // ...the non-matching one (ternary false branch) is unchanged.
    expect(b?.is_read).toBe(false)
    expect(result.current.unreadCount).toBe(1)
  })

  it('fetchPreferences returns {} when the API rejects', async () => {
    const errSpy = jest.spyOn(console, 'error').mockImplementation(() => {})
    mockApiClient.getNotificationPreferences.mockRejectedValue(
      new Error('prefs boom')
    )

    const { result } = renderHook(() => useNotifications(), { wrapper })

    // The mount effect calls fetchPreferences().then(setPreferences); the
    // rejection is swallowed by the hook's catch (lines 146-147) and {} is
    // returned, so preferences never become undefined and nothing throws.
    await waitFor(() => {
      expect(mockApiClient.getNotificationPreferences).toHaveBeenCalled()
    })
    await flushMicrotasks()

    expect(result.current.preferences).toEqual({})
    expect(errSpy).toHaveBeenCalledWith(
      'Error fetching notification preferences:',
      expect.any(Error)
    )
    errSpy.mockRestore()
  })

  it('fetchPreferences early-returns {} when there is no user', async () => {
    ;(useAuth as jest.Mock).mockReturnValue({
      user: null,
      apiClient: mockApiClient as any,
    })

    const { result } = renderHook(() => useNotifications(), { wrapper })

    // No user -> the mount effect never fetches; preferences stay {}.
    expect(result.current.preferences).toEqual({})
    expect(mockApiClient.getNotificationPreferences).not.toHaveBeenCalled()
  })
})
