/**
 * Notification State Store
 *
 * Manages application-wide notifications, toasts, and alert states.
 * Provides a centralized system for user feedback and status updates.
 */

import { create } from 'zustand'
import { devtools, subscribeWithSelector } from 'zustand/middleware'

export interface NotificationItem {
  id: string
  type: 'success' | 'error' | 'warning' | 'info'
  title: string
  message?: string
  duration?: number // 0 for persistent, undefined for default (5s)
  timestamp: Date
  read: boolean
  action?: {
    label: string
    onClick: () => void
  }
  // Optional metadata for different notification sources
  source?: 'system' | 'task' | 'annotation' | 'evaluation' | 'user'
  taskId?: string
  userId?: string
}

export interface ToastItem {
  id: string
  type: 'success' | 'error' | 'warning' | 'info'
  title: string
  message?: string
  duration?: number
  action?: {
    label: string
    onClick: () => void
  }
}

export interface NotificationState {
  // Persistent notifications (for notification center)
  notifications: NotificationItem[]

  // Temporary toasts (for immediate feedback)
  toasts: ToastItem[]

  // Notification settings
  settings: {
    enableToasts: boolean
    enablePersistentNotifications: boolean
    defaultToastDuration: number
    maxToasts: number
    maxNotifications: number
  }

  // Counters
  unreadCount: number

  // Loading states
  isLoadingNotifications: boolean
}

export interface NotificationActions {
  // Toast management
  addToast: (toast: Omit<ToastItem, 'id'>) => string
  removeToast: (id: string) => void
  clearToasts: () => void

  // Notification management
  addNotification: (
    notification: Omit<NotificationItem, 'id' | 'timestamp' | 'read'>
  ) => string
  markAsRead: (id: string) => void
  markAllAsRead: () => void
  removeNotification: (id: string) => void
  clearNotifications: () => void
  clearOldNotifications: (olderThanDays: number) => void

  // Convenience methods for common notification types
  notifySuccess: (
    title: string,
    message?: string,
    options?: Partial<NotificationItem>
  ) => string
  notifyError: (
    title: string,
    message?: string,
    options?: Partial<NotificationItem>
  ) => string
  notifyWarning: (
    title: string,
    message?: string,
    options?: Partial<NotificationItem>
  ) => string
  notifyInfo: (
    title: string,
    message?: string,
    options?: Partial<NotificationItem>
  ) => string

  // Toast convenience methods
  toastSuccess: (title: string, message?: string, duration?: number) => string
  toastError: (title: string, message?: string, duration?: number) => string
  toastWarning: (title: string, message?: string, duration?: number) => string
  toastInfo: (title: string, message?: string, duration?: number) => string

  // Settings
  updateSettings: (settings: Partial<NotificationState['settings']>) => void

  // Bulk operations
  markMultipleAsRead: (ids: string[]) => void
  removeMultiple: (ids: string[]) => void

  // Loading
  setLoadingNotifications: (loading: boolean) => void
}

type NotificationStore = NotificationState & NotificationActions

const defaultSettings: NotificationState['settings'] = {
  enableToasts: true,
  enablePersistentNotifications: true,
  defaultToastDuration: 5000,
  maxToasts: 5,
  maxNotifications: 100,
}

const initialState: NotificationState = {
  notifications: [],
  toasts: [],
  settings: defaultSettings,
  unreadCount: 0,
  isLoadingNotifications: false,
}

export const useNotificationStore = create<NotificationStore>()(
  devtools(
    subscribeWithSelector((set, get) => ({
      ...initialState,

      // Toast management
      addToast: (toast: Omit<ToastItem, 'id'>) => {
        const { settings } = get()
        if (!settings.enableToasts) return ''

        const id = Math.random().toString(36).substring(2, 9)
        const newToast: ToastItem = {
          id,
          duration: toast.duration ?? settings.defaultToastDuration,
          ...toast,
        }

        set(
          (state) => {
            const newToasts = [...state.toasts, newToast]

            // Limit number of toasts
            if (newToasts.length > settings.maxToasts) {
              newToasts.splice(0, newToasts.length - settings.maxToasts)
            }

            return { toasts: newToasts }
          },
          false,
          'addToast'
        )

        // Auto-remove toast after duration
        if (newToast.duration && newToast.duration > 0) {
          setTimeout(() => {
            get().removeToast(id)
          }, newToast.duration)
        }

        return id
      },

      removeToast: (id: string) => {
        set(
          (state) => ({
            toasts: state.toasts.filter((toast) => toast.id !== id),
          }),
          false,
          'removeToast'
        )
      },

      clearToasts: () => {
        set({ toasts: [] }, false, 'clearToasts')
      },

      // Notification management
      addNotification: (
        notification: Omit<NotificationItem, 'id' | 'timestamp' | 'read'>
      ) => {
        const { settings } = get()
        if (!settings.enablePersistentNotifications) return ''

        const id = Math.random().toString(36).substring(2, 9)
        const newNotification: NotificationItem = {
          id,
          timestamp: new Date(),
          read: false,
          ...notification,
        }

        set(
          (state) => {
            const newNotifications = [newNotification, ...state.notifications]

            // Limit number of notifications
            if (newNotifications.length > settings.maxNotifications) {
              newNotifications.splice(settings.maxNotifications)
            }

            return {
              notifications: newNotifications,
              unreadCount: state.unreadCount + 1,
            }
          },
          false,
          'addNotification'
        )

        return id
      },

      markAsRead: (id: string) => {
        set(
          (state) => ({
            notifications: state.notifications.map((notification) =>
              notification.id === id && !notification.read
                ? { ...notification, read: true }
                : notification
            ),
            unreadCount: Math.max(0, state.unreadCount - 1),
          }),
          false,
          'markAsRead'
        )
      },

      markAllAsRead: () => {
        set(
          (state) => ({
            notifications: state.notifications.map((notification) => ({
              ...notification,
              read: true,
            })),
            unreadCount: 0,
          }),
          false,
          'markAllAsRead'
        )
      },

      removeNotification: (id: string) => {
        set(
          (state) => {
            const notification = state.notifications.find((n) => n.id === id)
            return {
              notifications: state.notifications.filter((n) => n.id !== id),
              unreadCount:
                notification && !notification.read
                  ? Math.max(0, state.unreadCount - 1)
                  : state.unreadCount,
            }
          },
          false,
          'removeNotification'
        )
      },

      clearNotifications: () => {
        set(
          {
            notifications: [],
            unreadCount: 0,
          },
          false,
          'clearNotifications'
        )
      },

      clearOldNotifications: (olderThanDays: number) => {
        const cutoffDate = new Date()
        cutoffDate.setDate(cutoffDate.getDate() - olderThanDays)

        set(
          (state) => {
            const filteredNotifications = state.notifications.filter(
              (notification) => notification.timestamp > cutoffDate
            )

            const removedUnreadCount = state.notifications.filter(
              (n) => n.timestamp <= cutoffDate && !n.read
            ).length

            return {
              notifications: filteredNotifications,
              unreadCount: Math.max(0, state.unreadCount - removedUnreadCount),
            }
          },
          false,
          'clearOldNotifications'
        )
      },

      // Convenience methods for notifications
      notifySuccess: (
        title: string,
        message?: string,
        options?: Partial<NotificationItem>
      ) => {
        return get().addNotification({
          type: 'success',
          title,
          message,
          ...options,
        })
      },

      notifyError: (
        title: string,
        message?: string,
        options?: Partial<NotificationItem>
      ) => {
        return get().addNotification({
          type: 'error',
          title,
          message,
          duration: 0, // Errors are persistent by default
          ...options,
        })
      },

      notifyWarning: (
        title: string,
        message?: string,
        options?: Partial<NotificationItem>
      ) => {
        return get().addNotification({
          type: 'warning',
          title,
          message,
          ...options,
        })
      },

      notifyInfo: (
        title: string,
        message?: string,
        options?: Partial<NotificationItem>
      ) => {
        return get().addNotification({
          type: 'info',
          title,
          message,
          ...options,
        })
      },

      // Convenience methods for toasts
      toastSuccess: (title: string, message?: string, duration?: number) => {
        return get().addToast({
          type: 'success',
          title,
          message,
          duration,
        })
      },

      toastError: (title: string, message?: string, duration?: number) => {
        return get().addToast({
          type: 'error',
          title,
          message,
          duration: duration ?? 8000, // Longer duration for errors
        })
      },

      toastWarning: (title: string, message?: string, duration?: number) => {
        return get().addToast({
          type: 'warning',
          title,
          message,
          duration,
        })
      },

      toastInfo: (title: string, message?: string, duration?: number) => {
        return get().addToast({
          type: 'info',
          title,
          message,
          duration,
        })
      },

      // Settings
      updateSettings: (newSettings: Partial<NotificationState['settings']>) => {
        set(
          (state) => ({
            settings: { ...state.settings, ...newSettings },
          }),
          false,
          'updateSettings'
        )
      },

      // Bulk operations
      markMultipleAsRead: (ids: string[]) => {
        set(
          (state) => {
            let unreadReduction = 0
            const updatedNotifications = state.notifications.map(
              (notification) => {
                if (ids.includes(notification.id) && !notification.read) {
                  unreadReduction++
                  return { ...notification, read: true }
                }
                return notification
              }
            )

            return {
              notifications: updatedNotifications,
              unreadCount: Math.max(0, state.unreadCount - unreadReduction),
            }
          },
          false,
          'markMultipleAsRead'
        )
      },

      removeMultiple: (ids: string[]) => {
        set(
          (state) => {
            let unreadReduction = 0
            const filteredNotifications = state.notifications.filter(
              (notification) => {
                if (ids.includes(notification.id)) {
                  if (!notification.read) unreadReduction++
                  return false
                }
                return true
              }
            )

            return {
              notifications: filteredNotifications,
              unreadCount: Math.max(0, state.unreadCount - unreadReduction),
            }
          },
          false,
          'removeMultiple'
        )
      },

      // Loading
      setLoadingNotifications: (loading: boolean) => {
        set(
          { isLoadingNotifications: loading },
          false,
          'setLoadingNotifications'
        )
      },
    })),
    {
      name: 'notification-store',
      partialize: (state: any) => ({
        // Persist notifications and settings
        notifications: state.notifications,
        settings: state.settings,
        unreadCount: state.unreadCount,
      }),
    }
  )
)
