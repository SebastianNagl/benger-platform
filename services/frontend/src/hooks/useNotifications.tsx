'use client'

import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { getTranslatedNotification } from '@/lib/notificationTranslation'
import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from '@/components/shared/Toast'

export interface Notification {
  id: string
  type: string
  title: string
  message: string
  data?: Record<string, any>
  is_read: boolean
  created_at: string
  organization_id?: string
}

export interface NotificationPreferences {
  [key: string]: boolean
}

// Mirrors the cap used by the three project-progress WS clients.
const MAX_RECONNECT_ATTEMPTS = 5

export function useNotifications() {
  const { apiClient, user } = useAuth()
  const { t } = useI18n()
  // Keep the latest `t` in a ref so the memoized callbacks below (whose deps
  // intentionally omit `t` to avoid churn — the SSE effect never re-runs) always
  // translate toasts with the current locale instead of the locale captured when
  // the callback was created. Fixes German toasts leaking under an English UI
  // (and vice-versa) after a live language switch without a page reload.
  const tRef = useRef(t)
  useEffect(() => {
    tRef.current = t
  }, [t])
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [isLoading, setIsLoading] = useState(false)
  const [preferences, setPreferences] = useState<NotificationPreferences>({})

  // SSE connection management
  const eventSourceRef = useRef<EventSource | null>(null)
  const isConnectedRef = useRef(false)
  const reconnectAttemptsRef = useRef(0)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  // Fetch notifications from API
  const fetchNotifications = useCallback(
    async (limit = 20, offset = 0, unreadOnly = false) => {
      if (!apiClient || !user) {
        return []
      }

      try {
        const params = new URLSearchParams({
          limit: limit.toString(),
          offset: offset.toString(),
        })

        if (unreadOnly) {
          params.append('read_status', 'false')
        }

        const response = await apiClient.getNotifications(params.toString())
        return response || []
      } catch (error) {
        console.error('Error fetching notifications:', error)
        return []
      }
    },
    [apiClient, user]
  )

  // Fetch unread count
  const fetchUnreadCount = useCallback(async () => {
    if (!apiClient || !user) {
      return 0
    }

    try {
      const response = await apiClient.getUnreadNotificationCount()
      return response.count || 0
    } catch (error) {
      console.error('Error fetching unread count:', error)
      return 0
    }
  }, [apiClient, user])

  // Mark notification as read
  const markAsRead = useCallback(
    async (notificationId: string) => {
      if (!apiClient || !user) return

      try {
        await apiClient.markNotificationAsRead(notificationId)

        // Update local state
        setNotifications((prev) =>
          prev.map((notification) =>
            notification.id === notificationId
              ? { ...notification, is_read: true }
              : notification
          )
        )

        // Update unread count
        setUnreadCount((prev) => Math.max(0, prev - 1))
      } catch (error) {
        console.error('Error marking notification as read:', error)
        toast(tRef.current('notifications.markReadError'), 'error')
      }
    },
    [apiClient, user]
  )

  // Mark all notifications as read
  const markAllAsRead = useCallback(async () => {
    if (!apiClient || !user) return

    try {
      const response = await apiClient.markAllNotificationsAsRead()

      // Update local state optimistically
      setNotifications((prev) =>
        prev.map((notification) => ({ ...notification, is_read: true }))
      )
      setUnreadCount(0)

      const markedCount = response?.count ?? 0
      const messageKey =
        markedCount === 1
          ? 'notifications.markAllReadSuccessOne'
          : 'notifications.markAllReadSuccess'
      toast(tRef.current(messageKey, { count: markedCount }), 'success')

      // Refetch to sync with server and prevent SSE race conditions
      const [fetchedNotifications, count] = await Promise.all([
        fetchNotifications(),
        fetchUnreadCount(),
      ])
      setNotifications(fetchedNotifications)
      setUnreadCount(count)
    } catch (error) {
      console.error('Error marking all notifications as read:', error)
      toast(tRef.current('notifications.markAllReadError'), 'error')
    }
  }, [apiClient, user, fetchNotifications, fetchUnreadCount])

  // Fetch notification preferences
  const fetchPreferences = useCallback(async () => {
    if (!apiClient || !user) return {}

    try {
      return await apiClient.getNotificationPreferences()
    } catch (error) {
      console.error('Error fetching notification preferences:', error)
      return {}
    }
  }, [apiClient, user])

  // Update notification preferences
  const updatePreferences = useCallback(
    async (newPreferences: NotificationPreferences) => {
      if (!apiClient || !user) return false

      try {
        await apiClient.updateNotificationPreferences(newPreferences)

        setPreferences(newPreferences)
        toast(tRef.current('notifications.preferencesUpdated'), 'success')
        return true
      } catch (error) {
        console.error('Error updating notification preferences:', error)
        toast(tRef.current('notifications.preferencesUpdateFailed'), 'error')
        return false
      }
    },
    [apiClient, user]
  )

  // Refresh all notification data
  const refreshNotifications = useCallback(async () => {
    if (!user) return

    setIsLoading(true)
    try {
      const [fetchedNotifications, count] = await Promise.all([
        fetchNotifications(),
        fetchUnreadCount(),
      ])

      setNotifications(fetchedNotifications)
      setUnreadCount(count)
    } catch (error) {
      console.error('Error refreshing notifications:', error)
    } finally {
      setIsLoading(false)
    }
  }, [user, fetchNotifications, fetchUnreadCount])

  // Create SSE connection helper
  const createSSEConnection = useCallback(() => {
    if (
      !apiClient ||
      !user ||
      isConnectedRef.current ||
      eventSourceRef.current
    ) {
      return null
    }

    try {
      const eventSource = apiClient.createNotificationStream()

      eventSource.onopen = () => {
        isConnectedRef.current = true
        reconnectAttemptsRef.current = 0
      }

      eventSource.onmessage = (event: any) => {
        try {
          const data = JSON.parse(event.data)

          switch (data.type) {
            case 'connected':
            case 'proxy_connected':
              break

            case 'new_notification':
              const newNotification = data.notification
              setNotifications((prev) => [newNotification, ...prev])
              setUnreadCount((prev) => prev + 1)
              const { title: translatedToastTitle } =
                getTranslatedNotification(tRef.current, newNotification)
              toast(translatedToastTitle, 'success')
              break

            case 'unread_count':
              setUnreadCount(data.count)
              break

            case 'error':
              if (data.message?.includes('Authentication required')) {
                if (eventSourceRef.current) {
                  eventSourceRef.current.close()
                  eventSourceRef.current = null
                }
                isConnectedRef.current = false
                reconnectAttemptsRef.current = 0
                if (reconnectTimeoutRef.current) {
                  clearTimeout(reconnectTimeoutRef.current)
                  reconnectTimeoutRef.current = null
                }
              } else {
                console.error('Notification stream error:', data.message)
              }
              break
          }
        } catch (error) {
          console.error('Error parsing SSE data:', error)
        }
      }

      eventSource.onerror = () => {
        isConnectedRef.current = false

        if (eventSourceRef.current?.readyState === 2) {
          eventSourceRef.current.close()
          eventSourceRef.current = null

          // Cap reconnect attempts. The three project-progress WS clients
          // (EvaluationResults, GenerationTaskList, GenerationProgress)
          // cap at 5; this SSE used to retry forever — once the user's
          // session expired the browser hammered /api/notifications/stream
          // every ~5 s indefinitely with no auth cookie.
          if (reconnectAttemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
            console.warn(
              `Notification SSE: giving up after ${MAX_RECONNECT_ATTEMPTS} reconnect attempts`
            )
            return
          }

          // Reconnect after brief delay
          if (user && apiClient && !reconnectTimeoutRef.current) {
            reconnectAttemptsRef.current++
            const delay = Math.min(1000 * reconnectAttemptsRef.current, 5000)

            reconnectTimeoutRef.current = setTimeout(() => {
              const newConnection = createSSEConnection()
              if (newConnection) {
                eventSourceRef.current = newConnection
              }
              reconnectTimeoutRef.current = null
            }, delay)
          }
        }
      }

      return eventSource
    } catch (error) {
      console.error('Error creating SSE connection:', error)
      return null
    }
  }, [apiClient, user])

  // Cleanup SSE connection
  const cleanupSSEConnection = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
      isConnectedRef.current = false
    }

    // Clear any pending reconnect timeout
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }

    // Reset reconnect attempts
    reconnectAttemptsRef.current = 0
  }, [])

  // Initialize notifications on component mount
  useEffect(() => {
    if (user && apiClient) {
      // Always fetch fresh notification data on mount to avoid stale state issues
      // This prevents the cycling bug where cached values conflict with API data
      refreshNotifications()

      // Load preferences
      fetchPreferences().then(setPreferences)

      // Setup SSE connection for real-time updates
      if (!reconnectTimeoutRef.current) {
        const connection = createSSEConnection()
        if (connection) {
          eventSourceRef.current = connection
        }
      }
    }

    return () => {
      cleanupSSEConnection()
    }
    // Only depend on user and apiClient to prevent re-runs from callback recreations
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, apiClient])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      cleanupSSEConnection()
    }
  }, [cleanupSSEConnection])

  return {
    notifications,
    unreadCount,
    isLoading,
    preferences,
    markAsRead,
    markAllAsRead,
    refreshNotifications,
    updatePreferences,
    fetchNotifications,
    fetchUnreadCount,
  }
}
