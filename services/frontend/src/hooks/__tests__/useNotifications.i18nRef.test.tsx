/**
 * Regression test: toasts fired from useNotifications callbacks must translate
 * with the CURRENT locale, even after a live language switch without a page
 * reload. The callbacks are memoized with deps that intentionally omit `t`
 * (to avoid SSE reconnect churn), so a naive closure over `t` would keep the
 * language captured when the callback was first created. The hook guards
 * against this by reading the latest `t` from a ref.
 *
 * The mock below mirrors the real I18nContext: each render produces a fresh
 * `t` bound to the then-current locale. Without the ref fix this test fails —
 * the second (post-switch) toast comes back in the original language.
 */

import { useAuth } from '@/contexts/AuthContext'
import { act, renderHook, waitFor } from '@testing-library/react'
import React from 'react'
import { useNotifications } from '../useNotifications'
import { mockToast } from '@/test-utils/setupTests'

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))

// Locale-aware i18n mock. `t` is recreated per useI18n() call (i.e. per render)
// and bound to the locale at that moment — exactly like the real context, whose
// `t` closes over the render's `locale` state.
jest.mock('@/contexts/I18nContext', () => {
  let locale: 'de' | 'en' = 'de'
  const dict: Record<string, Record<string, string>> = {
    de: {
      'notifications.markAllReadSuccess':
        '{count} Benachrichtigungen als gelesen markiert',
      'notifications.markAllReadSuccessOne':
        '{count} Benachrichtigung als gelesen markiert',
    },
    en: {
      'notifications.markAllReadSuccess': '{count} notifications marked as read',
      'notifications.markAllReadSuccessOne':
        '{count} notification marked as read',
    },
  }
  return {
    useI18n: () => {
      const bound = locale
      const t = (key: string, vars?: Record<string, any>) => {
        let s = (dict[bound] && dict[bound][key]) || key
        if (vars) {
          s = s.replace(/\{(\w+)\}/g, (m, n) =>
            vars[n] !== undefined ? String(vars[n]) : m
          )
        }
        return s
      }
      return { t, locale: bound, changeLocale: jest.fn(), isReady: true }
    },
    I18nProvider: ({ children }: { children: React.ReactNode }) => children,
    __setLocale: (l: 'de' | 'en') => {
      locale = l
    },
  }
})

const { __setLocale } = jest.requireMock('@/contexts/I18nContext') as {
  __setLocale: (l: 'de' | 'en') => void
}

class MockEventSource {
  readyState = 0
  onopen: ((e: Event) => void) | null = null
  onmessage: ((e: MessageEvent) => void) | null = null
  onerror: ((e: Event) => void) | null = null
  constructor() {
    Promise.resolve().then(() => {
      this.readyState = 1
      this.onopen?.(new Event('open'))
    })
  }
  close() {
    this.readyState = 2
  }
}
// @ts-ignore
global.EventSource = MockEventSource

const mockApiClient = {
  getNotifications: jest.fn(),
  getUnreadNotificationCount: jest.fn(),
  markAllNotificationsAsRead: jest.fn(),
  getNotificationPreferences: jest.fn(),
  createNotificationStream: jest.fn(),
}

const mockUser = { id: '1', username: 'testuser', email: 'test@example.com' }
const wrapper = ({ children }: { children: React.ReactNode }) => <>{children}</>

describe('useNotifications - toast follows current locale after live switch', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    __setLocale('de')
    ;(useAuth as jest.Mock).mockReturnValue({
      user: mockUser,
      apiClient: mockApiClient as any,
    })
    mockApiClient.getNotifications.mockResolvedValue([])
    mockApiClient.getUnreadNotificationCount.mockResolvedValue({ count: 0 })
    mockApiClient.getNotificationPreferences.mockResolvedValue({})
    mockApiClient.markAllNotificationsAsRead.mockResolvedValue({
      message: 'Marked 2 notifications as read',
      count: 2,
    })
    mockApiClient.createNotificationStream.mockImplementation(
      () => new MockEventSource()
    )
  })

  it('translates the mark-all toast with the new locale after a rerender', async () => {
    const { result, rerender } = renderHook(() => useNotifications(), {
      wrapper,
    })

    await waitFor(() => {
      expect(mockApiClient.createNotificationStream).toHaveBeenCalled()
    })

    // German locale → German toast
    await act(async () => {
      await result.current.markAllAsRead()
    })
    expect(mockToast.success).toHaveBeenLastCalledWith(
      '2 Benachrichtigungen als gelesen markiert'
    )

    // Switch language live (no remount) and rerender the hook, as happens when
    // the user flips the language toggle.
    __setLocale('en')
    rerender()

    await act(async () => {
      await result.current.markAllAsRead()
    })
    expect(mockToast.success).toHaveBeenLastCalledWith(
      '2 notifications marked as read'
    )
  })
})
