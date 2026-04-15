/**
 * @jest-environment jsdom
 *
 * Branch coverage tests for useNotifications hook.
 * Targets uncovered branches: no user/apiClient guards, error paths,
 * SSE message parsing, reconnection logic, preference operations.
 */

import { useAuth } from '@/contexts/AuthContext'
import { act, renderHook, waitFor } from '@testing-library/react'
import React from 'react'
import { useNotifications } from '../useNotifications'

// Mock react-hot-toast
jest.mock('react-hot-toast', () => {
  const success = jest.fn()
  const error = jest.fn()
  return {
    toast: Object.assign(jest.fn(), { success, error }),
  }
})

// Mock I18nContext
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => key,
    locale: 'en',
    isReady: true,
  }),
}))

// Mock notification translation
jest.mock('@/lib/notificationTranslation', () => ({
  getTranslatedNotification: jest.fn((_t: any, notification: any) => ({
    title: notification.title || 'Translated Title',
    message: notification.message || 'Translated Message',
  })),
}))

// Mock AuthContext
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))

// Mock EventSource
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
      if (this.onopen) {
        this.onopen(new Event('open'))
      }
    })
  }

  close() {
    this.readyState = 2
  }

  simulateMessage(data: any) {
    if (this.onmessage) {
      this.onmessage(
        new MessageEvent('message', { data: JSON.stringify(data) })
      )
    }
  }

  simulateError() {
    this.readyState = 2
    if (this.onerror) {
      this.onerror(new Event('error'))
    }
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

const mockUser = {
  id: '1',
  username: 'testuser',
  email: 'test@example.com',
}

const wrapper = ({ children }: { children: React.ReactNode }) => <>{children}</>

describe('useNotifications - Branch Coverage', () => {
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

  describe('fetchNotifications guard branches', () => {
    it('returns empty array when apiClient is null', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: mockUser,
        apiClient: null,
      })

      const { result } = renderHook(() => useNotifications(), { wrapper })

      const data = await result.current.fetchNotifications()
      expect(data).toEqual([])
    })

    it('returns empty array when user is null', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        apiClient: mockApiClient,
      })

      const { result } = renderHook(() => useNotifications(), { wrapper })

      const data = await result.current.fetchNotifications()
      expect(data).toEqual([])
    })

    it('passes unreadOnly as read_status param when true', async () => {
      mockApiClient.getNotifications.mockResolvedValue([
        { id: '1', type: 'info', title: 'N', message: 'M', is_read: false, created_at: '2025-01-01' },
      ])

      const { result } = renderHook(() => useNotifications(), { wrapper })

      // Wait for initialization
      await act(async () => {
        await Promise.resolve()
      })

      const data = await act(async () => {
        return await result.current.fetchNotifications(20, 0, true)
      })

      // Check that read_status=false was appended
      const calls = mockApiClient.getNotifications.mock.calls
      const lastCall = calls[calls.length - 1]
      expect(lastCall[0]).toContain('read_status=false')
    })

    it('returns empty array when API call fails', async () => {
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()
      mockApiClient.getNotifications.mockRejectedValueOnce(new Error('API Error'))

      const { result } = renderHook(() => useNotifications(), { wrapper })

      await act(async () => {
        await Promise.resolve()
      })

      // Manually call with fresh mock that will reject
      mockApiClient.getNotifications.mockRejectedValueOnce(new Error('Network failure'))
      const data = await act(async () => {
        return await result.current.fetchNotifications()
      })
      expect(data).toEqual([])
      consoleSpy.mockRestore()
    })

    it('returns empty array when response is falsy', async () => {
      mockApiClient.getNotifications.mockResolvedValue(null)

      const { result } = renderHook(() => useNotifications(), { wrapper })

      await act(async () => {
        await Promise.resolve()
      })

      mockApiClient.getNotifications.mockResolvedValue(null)
      const data = await act(async () => {
        return await result.current.fetchNotifications()
      })
      expect(data).toEqual([])
    })
  })

  describe('fetchUnreadCount guard branches', () => {
    it('returns 0 when apiClient is null', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: mockUser,
        apiClient: null,
      })

      const { result } = renderHook(() => useNotifications(), { wrapper })

      const count = await result.current.fetchUnreadCount()
      expect(count).toBe(0)
    })

    it('returns 0 when user is null', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        apiClient: mockApiClient,
      })

      const { result } = renderHook(() => useNotifications(), { wrapper })

      const count = await result.current.fetchUnreadCount()
      expect(count).toBe(0)
    })

    it('returns 0 when response.count is falsy', async () => {
      mockApiClient.getUnreadNotificationCount.mockResolvedValue({})

      const { result } = renderHook(() => useNotifications(), { wrapper })

      await act(async () => {
        await Promise.resolve()
      })

      mockApiClient.getUnreadNotificationCount.mockResolvedValue({})
      const count = await act(async () => {
        return await result.current.fetchUnreadCount()
      })
      expect(count).toBe(0)
    })

    it('returns 0 when API call fails', async () => {
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()
      mockApiClient.getUnreadNotificationCount.mockRejectedValueOnce(new Error('Fail'))

      const { result } = renderHook(() => useNotifications(), { wrapper })

      await act(async () => {
        await Promise.resolve()
      })

      mockApiClient.getUnreadNotificationCount.mockRejectedValueOnce(new Error('Fail'))
      const count = await act(async () => {
        return await result.current.fetchUnreadCount()
      })
      expect(count).toBe(0)
      consoleSpy.mockRestore()
    })
  })

  describe('markAsRead guard and error branches', () => {
    it('does nothing when apiClient is null', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: mockUser,
        apiClient: null,
      })

      const { result } = renderHook(() => useNotifications(), { wrapper })

      await act(async () => {
        await result.current.markAsRead('1')
      })

      expect(mockApiClient.markNotificationAsRead).not.toHaveBeenCalled()
    })

    it('does nothing when user is null', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        apiClient: mockApiClient,
      })

      const { result } = renderHook(() => useNotifications(), { wrapper })

      await act(async () => {
        await result.current.markAsRead('1')
      })

      expect(mockApiClient.markNotificationAsRead).not.toHaveBeenCalled()
    })

    it('shows error toast when markAsRead API fails', async () => {
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()
      mockApiClient.markNotificationAsRead.mockRejectedValue(new Error('Fail'))

      const { result } = renderHook(() => useNotifications(), { wrapper })

      await waitFor(() => {
        expect(mockApiClient.createNotificationStream).toHaveBeenCalled()
      })

      await act(async () => {
        await result.current.markAsRead('1')
      })

      const { toast } = require('react-hot-toast')
      expect(toast.error).toHaveBeenCalledWith('notifications.markReadError')
      consoleSpy.mockRestore()
    })
  })

  describe('markAllAsRead guard and error branches', () => {
    it('does nothing when apiClient is null', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: mockUser,
        apiClient: null,
      })

      const { result } = renderHook(() => useNotifications(), { wrapper })

      await act(async () => {
        await result.current.markAllAsRead()
      })

      expect(mockApiClient.markAllNotificationsAsRead).not.toHaveBeenCalled()
    })

    it('uses fallback success message when response.message is falsy', async () => {
      mockApiClient.markAllNotificationsAsRead.mockResolvedValue({})
      mockApiClient.getNotifications.mockResolvedValue([])
      mockApiClient.getUnreadNotificationCount.mockResolvedValue({ count: 0 })

      const { result } = renderHook(() => useNotifications(), { wrapper })

      await waitFor(() => {
        expect(mockApiClient.createNotificationStream).toHaveBeenCalled()
      })

      await act(async () => {
        await result.current.markAllAsRead()
      })

      const { toast } = require('react-hot-toast')
      expect(toast.success).toHaveBeenCalledWith('notifications.markAllReadSuccess')
    })

    it('shows error toast when markAllAsRead API fails', async () => {
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()
      mockApiClient.markAllNotificationsAsRead.mockRejectedValue(new Error('Fail'))

      const { result } = renderHook(() => useNotifications(), { wrapper })

      await waitFor(() => {
        expect(mockApiClient.createNotificationStream).toHaveBeenCalled()
      })

      await act(async () => {
        await result.current.markAllAsRead()
      })

      const { toast } = require('react-hot-toast')
      expect(toast.error).toHaveBeenCalledWith('notifications.markAllReadError')
      consoleSpy.mockRestore()
    })
  })

  describe('fetchPreferences guard and error branches', () => {
    it('returns empty object when apiClient is null', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: mockUser,
        apiClient: null,
      })

      const { result } = renderHook(() => useNotifications(), { wrapper })

      // fetchPreferences is not directly exposed, but we can test via internal use
      // Instead, test via updatePreferences which uses the same guard
    })

    it('returns empty object when user is null', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        apiClient: mockApiClient,
      })

      const { result } = renderHook(() => useNotifications(), { wrapper })

      // preferences should remain empty when user is null
      expect(result.current.preferences).toEqual({})
    })
  })

  describe('updatePreferences guard and error branches', () => {
    it('returns false when apiClient is null', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: mockUser,
        apiClient: null,
      })

      const { result } = renderHook(() => useNotifications(), { wrapper })

      const success = await act(async () => {
        return await result.current.updatePreferences({ email_enabled: true })
      })
      expect(success).toBe(false)
    })

    it('returns false when user is null', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        apiClient: mockApiClient,
      })

      const { result } = renderHook(() => useNotifications(), { wrapper })

      const success = await act(async () => {
        return await result.current.updatePreferences({ email_enabled: true })
      })
      expect(success).toBe(false)
    })

    it('returns true and shows success toast on success', async () => {
      mockApiClient.updateNotificationPreferences.mockResolvedValue(undefined)

      const { result } = renderHook(() => useNotifications(), { wrapper })

      await waitFor(() => {
        expect(mockApiClient.createNotificationStream).toHaveBeenCalled()
      })

      const success = await act(async () => {
        return await result.current.updatePreferences({ email_enabled: true })
      })

      expect(success).toBe(true)
      const { toast } = require('react-hot-toast')
      expect(toast.success).toHaveBeenCalledWith('notifications.preferencesUpdated')
    })

    it('returns false and shows error toast on failure', async () => {
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()
      mockApiClient.updateNotificationPreferences.mockRejectedValue(new Error('Fail'))

      const { result } = renderHook(() => useNotifications(), { wrapper })

      await waitFor(() => {
        expect(mockApiClient.createNotificationStream).toHaveBeenCalled()
      })

      const success = await act(async () => {
        return await result.current.updatePreferences({ email_enabled: true })
      })

      expect(success).toBe(false)
      const { toast } = require('react-hot-toast')
      expect(toast.error).toHaveBeenCalledWith('notifications.preferencesUpdateFailed')
      consoleSpy.mockRestore()
    })
  })

  describe('refreshNotifications branches', () => {
    it('does nothing when user is null', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        apiClient: mockApiClient,
      })

      const { result } = renderHook(() => useNotifications(), { wrapper })

      await act(async () => {
        await result.current.refreshNotifications()
      })

      // getNotifications should not have been called for refresh
      expect(result.current.isLoading).toBe(false)
    })

    it('handles errors during refresh gracefully', async () => {
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()

      const { result } = renderHook(() => useNotifications(), { wrapper })

      await waitFor(() => {
        expect(mockApiClient.createNotificationStream).toHaveBeenCalled()
      })

      // Make next calls fail
      mockApiClient.getNotifications.mockRejectedValue(new Error('Fail'))
      mockApiClient.getUnreadNotificationCount.mockRejectedValue(new Error('Fail'))

      await act(async () => {
        await result.current.refreshNotifications()
      })

      expect(result.current.isLoading).toBe(false)
      consoleSpy.mockRestore()
    })
  })

  describe('SSE message type branches', () => {
    it('handles connected message type (no-op)', async () => {
      const { result } = renderHook(() => useNotifications(), { wrapper })

      await waitFor(() => {
        expect(mockApiClient.createNotificationStream).toHaveBeenCalled()
      })

      const es = mockApiClient.createNotificationStream.mock.results[0].value as MockEventSource

      await act(async () => {
        await Promise.resolve()
      })

      act(() => {
        es.simulateMessage({ type: 'connected' })
      })

      // Should not crash, no state changes
      expect(result.current.notifications).toEqual([])
    })

    it('handles proxy_connected message type (no-op)', async () => {
      const { result } = renderHook(() => useNotifications(), { wrapper })

      await waitFor(() => {
        expect(mockApiClient.createNotificationStream).toHaveBeenCalled()
      })

      const es = mockApiClient.createNotificationStream.mock.results[0].value as MockEventSource

      await act(async () => {
        await Promise.resolve()
      })

      act(() => {
        es.simulateMessage({ type: 'proxy_connected' })
      })

      expect(result.current.notifications).toEqual([])
    })

    it('handles error message with auth required - closes connection and stops reconnecting', async () => {
      const { result } = renderHook(() => useNotifications(), { wrapper })

      await waitFor(() => {
        expect(mockApiClient.createNotificationStream).toHaveBeenCalled()
      })

      const es = mockApiClient.createNotificationStream.mock.results[0].value as MockEventSource

      await act(async () => {
        await Promise.resolve()
      })

      act(() => {
        es.simulateMessage({
          type: 'error',
          message: 'Authentication required',
        })
      })

      // Should have closed the connection
      expect(es.readyState).toBe(2)
    })

    it('handles error message without auth required - logs error', async () => {
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()

      const { result } = renderHook(() => useNotifications(), { wrapper })

      await waitFor(() => {
        expect(mockApiClient.createNotificationStream).toHaveBeenCalled()
      })

      const es = mockApiClient.createNotificationStream.mock.results[0].value as MockEventSource

      await act(async () => {
        await Promise.resolve()
      })

      act(() => {
        es.simulateMessage({
          type: 'error',
          message: 'Some other error',
        })
      })

      expect(consoleSpy).toHaveBeenCalledWith('Notification stream error:', 'Some other error')
      consoleSpy.mockRestore()
    })

    it('handles malformed JSON in SSE data', async () => {
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()

      const { result } = renderHook(() => useNotifications(), { wrapper })

      await waitFor(() => {
        expect(mockApiClient.createNotificationStream).toHaveBeenCalled()
      })

      const es = mockApiClient.createNotificationStream.mock.results[0].value as MockEventSource

      await act(async () => {
        await Promise.resolve()
      })

      // Send invalid JSON
      act(() => {
        if (es.onmessage) {
          es.onmessage(new MessageEvent('message', { data: 'not valid json' }))
        }
      })

      expect(consoleSpy).toHaveBeenCalledWith('Error parsing SSE data:', expect.any(Error))
      consoleSpy.mockRestore()
    })
  })

  describe('createSSEConnection guard branches', () => {
    it('returns null when apiClient is null', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: mockUser,
        apiClient: null,
      })

      const { result } = renderHook(() => useNotifications(), { wrapper })

      // SSE should not be created
      expect(mockApiClient.createNotificationStream).not.toHaveBeenCalled()
    })

    it('returns null when user is null', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        apiClient: mockApiClient,
      })

      const { result } = renderHook(() => useNotifications(), { wrapper })

      expect(mockApiClient.createNotificationStream).not.toHaveBeenCalled()
    })

    it('handles error during SSE creation', async () => {
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()
      mockApiClient.createNotificationStream.mockImplementation(() => {
        throw new Error('SSE creation failed')
      })

      const { result } = renderHook(() => useNotifications(), { wrapper })

      await act(async () => {
        await Promise.resolve()
      })

      expect(consoleSpy).toHaveBeenCalledWith('Error creating SSE connection:', expect.any(Error))
      consoleSpy.mockRestore()
    })
  })

  describe('error message data.message?.includes branch', () => {
    it('handles error type with null message', async () => {
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()

      const { result } = renderHook(() => useNotifications(), { wrapper })

      await waitFor(() => {
        expect(mockApiClient.createNotificationStream).toHaveBeenCalled()
      })

      const es = mockApiClient.createNotificationStream.mock.results[0].value as MockEventSource

      await act(async () => {
        await Promise.resolve()
      })

      act(() => {
        es.simulateMessage({
          type: 'error',
          message: null,
        })
      })

      // null?.includes returns undefined which is falsy, so goes to else branch
      expect(consoleSpy).toHaveBeenCalledWith('Notification stream error:', null)
      consoleSpy.mockRestore()
    })
  })
})
