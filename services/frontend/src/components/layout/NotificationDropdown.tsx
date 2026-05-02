'use client'

import { useI18n } from '@/contexts/I18nContext'
import { getTranslatedNotification } from '@/lib/notificationTranslation'
import { cn } from '@/lib/utils'
import {
  ArrowPathIcon,
  CheckCircleIcon,
  CheckIcon,
  ExclamationTriangleIcon,
  InformationCircleIcon,
  UserPlusIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'
import { formatDistanceToNow } from 'date-fns'
import { de } from 'date-fns/locale'

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

interface NotificationDropdownProps {
  isOpen: boolean
  notifications: Notification[]
  unreadCount: number
  onClose: () => void
  onMarkAsRead: (id: string) => void
  onMarkAllAsRead: () => void
  onRefresh: () => void
}

const notificationIcons = {
  task_created: InformationCircleIcon,
  task_completed: CheckCircleIcon,
  task_assigned: UserPlusIcon,
  korrektur_assigned: UserPlusIcon,
  llm_generation_completed: CheckCircleIcon,
  evaluation_completed: CheckCircleIcon,
  evaluation_failed: ExclamationTriangleIcon,
  annotation_completed: CheckCircleIcon,
  annotation_assigned: UserPlusIcon,
  data_upload_completed: CheckCircleIcon,
  organization_invitation_sent: UserPlusIcon,
  organization_invitation_accepted: UserPlusIcon,
  member_joined: UserPlusIcon,
  system_alert: ExclamationTriangleIcon,
  error_occurred: ExclamationTriangleIcon,
}

const notificationColors = {
  task_created: 'text-blue-600 bg-blue-100 dark:text-blue-400 dark:bg-blue-900',
  task_completed:
    'text-green-600 bg-green-100 dark:text-green-400 dark:bg-green-900',
  task_assigned:
    'text-amber-600 bg-amber-100 dark:text-amber-400 dark:bg-amber-900',
  korrektur_assigned:
    'text-indigo-600 bg-indigo-100 dark:text-indigo-400 dark:bg-indigo-900',
  annotation_assigned:
    'text-amber-600 bg-amber-100 dark:text-amber-400 dark:bg-amber-900',
  llm_generation_completed:
    'text-green-600 bg-green-100 dark:text-green-400 dark:bg-green-900',
  evaluation_completed:
    'text-green-600 bg-green-100 dark:text-green-400 dark:bg-green-900',
  evaluation_failed:
    'text-red-600 bg-red-100 dark:text-red-400 dark:bg-red-900',
  annotation_completed:
    'text-green-600 bg-green-100 dark:text-green-400 dark:bg-green-900',
  data_upload_completed:
    'text-blue-600 bg-blue-100 dark:text-blue-400 dark:bg-blue-900',
  organization_invitation_sent:
    'text-purple-600 bg-purple-100 dark:text-purple-400 dark:bg-purple-900',
  organization_invitation_accepted:
    'text-green-600 bg-green-100 dark:text-green-400 dark:bg-green-900',
  member_joined:
    'text-purple-600 bg-purple-100 dark:text-purple-400 dark:bg-purple-900',
  system_alert:
    'text-yellow-600 bg-yellow-100 dark:text-yellow-400 dark:bg-yellow-900',
  error_occurred: 'text-red-600 bg-red-100 dark:text-red-400 dark:bg-red-900',
}

export function NotificationDropdown({
  isOpen,
  notifications,
  unreadCount,
  onClose,
  onMarkAsRead,
  onMarkAllAsRead,
  onRefresh,
}: NotificationDropdownProps) {
  const { t, locale } = useI18n()

  if (!isOpen) return null

  const handleNotificationClick = (notification: Notification) => {
    if (!notification.is_read) {
      onMarkAsRead(notification.id)
    }

    // Navigate to relevant page if data contains task_id
    if (notification.data?.task_id) {
      // TODO: Update to use project-based routing when project_id is available
      // window.location.href = `/projects/${notification.data.project_id}/tasks/${notification.data.task_id}`
    }
  }

  return (
    <div className="w-96 max-w-sm rounded-lg bg-white shadow-lg ring-1 ring-black ring-opacity-5 dark:bg-zinc-900 dark:ring-zinc-700">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-zinc-200 px-4 py-3 dark:border-zinc-700">
        <h3 className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
          {t('notifications.title')}
          {unreadCount > 0 && (
            <span className="ml-2 text-xs text-zinc-500 dark:text-zinc-400">
              ({unreadCount} {t('notifications.unread')})
            </span>
          )}
        </h3>

        <div className="flex items-center space-x-2">
          {/* Refresh Button */}
          <button
            type="button"
            className="rounded-full p-1 text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-600 dark:hover:bg-zinc-700 dark:hover:text-zinc-300"
            onClick={onRefresh}
            title={t('notifications.refresh')}
          >
            <ArrowPathIcon className="h-4 w-4" />
          </button>

          {/* Mark All Read Button */}
          {unreadCount > 0 && (
            <button
              type="button"
              className="rounded-full p-1 text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-600 dark:hover:bg-zinc-700 dark:hover:text-zinc-300"
              onClick={onMarkAllAsRead}
              title={t('notifications.markAllRead')}
            >
              <CheckIcon className="h-4 w-4" />
            </button>
          )}

          {/* Close Button */}
          <button
            type="button"
            className="rounded-full p-1 text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-600 dark:hover:bg-zinc-700 dark:hover:text-zinc-300"
            onClick={onClose}
            title={t('notifications.close')}
          >
            <XMarkIcon className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Notifications List */}
      <div className="max-h-96 overflow-y-auto">
        {notifications.length === 0 ? (
          <div className="px-4 py-8 text-center text-zinc-500 dark:text-zinc-400">
            <InformationCircleIcon className="mx-auto mb-2 h-8 w-8 text-zinc-300 dark:text-zinc-600" />
            <p className="text-sm">{t('notifications.empty')}</p>
          </div>
        ) : (
          <div className="divide-y divide-zinc-200 dark:divide-zinc-700">
            {notifications.map((notification) => {
              const IconComponent =
                notificationIcons[
                  notification.type as keyof typeof notificationIcons
                ] || InformationCircleIcon
              const iconColorClass =
                notificationColors[
                  notification.type as keyof typeof notificationColors
                ] || notificationColors.system_alert
              const timeAgo = formatDistanceToNow(
                new Date(notification.created_at),
                { addSuffix: true, locale: locale === 'de' ? de : undefined }
              )
              const { title: translatedTitle, message: translatedMessage } =
                getTranslatedNotification(t, notification)

              return (
                <div
                  key={notification.id}
                  className={cn(
                    'cursor-pointer px-4 py-3 transition-colors',
                    'hover:bg-zinc-50 dark:hover:bg-zinc-700',
                    !notification.is_read && 'bg-zinc-50 dark:bg-zinc-800'
                  )}
                  onClick={() => handleNotificationClick(notification)}
                >
                  <div className="flex items-start space-x-3">
                    {/* Icon */}
                    <div
                      className={cn(
                        'flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full',
                        iconColorClass
                      )}
                    >
                      <IconComponent className="h-4 w-4" />
                    </div>

                    {/* Content */}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between">
                        <p
                          className={cn(
                            'truncate text-sm font-medium',
                            notification.is_read
                              ? 'text-zinc-700 dark:text-zinc-300'
                              : 'text-zinc-900 dark:text-zinc-100'
                          )}
                        >
                          {translatedTitle}
                        </p>

                        {/* Unread indicator */}
                        {!notification.is_read && (
                          <div className="ml-2 h-2 w-2 flex-shrink-0 rounded-full bg-emerald-600" />
                        )}
                      </div>

                      <p
                        className={cn(
                          'mt-1 text-sm',
                          notification.is_read
                            ? 'text-zinc-500 dark:text-zinc-400'
                            : 'text-zinc-600 dark:text-zinc-300'
                        )}
                      >
                        {translatedMessage}
                      </p>

                      <p className="mt-1 text-xs text-zinc-400 dark:text-zinc-500">
                        {timeAgo}
                      </p>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Footer */}
      {notifications.length > 0 && (
        <div className="border-t border-zinc-200 px-4 py-3 dark:border-zinc-700">
          <button
            type="button"
            className="w-full text-center text-sm font-medium text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300"
            onClick={() => {
              onClose()
              window.location.href = '/notifications'
            }}
          >
            {t('notifications.viewAll')}
          </button>
        </div>
      )}
    </div>
  )
}
