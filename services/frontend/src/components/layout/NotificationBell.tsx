'use client'

import { useI18n } from '@/contexts/I18nContext'
import { useNotifications } from '@/hooks/useNotifications'
import { BellIcon } from '@heroicons/react/24/outline'
import { useEffect, useState } from 'react'
import { NotificationDropdown } from './NotificationDropdown'

export function NotificationBell() {
  const { t } = useI18n()
  const [isOpen, setIsOpen] = useState(false)
  const {
    unreadCount,
    notifications,
    markAsRead,
    markAllAsRead,
    refreshNotifications,
  } = useNotifications()

  // Auto-refresh notifications periodically
  useEffect(() => {
    const interval = setInterval(() => {
      refreshNotifications()
    }, 30000) // Refresh every 30 seconds

    return () => clearInterval(interval)
  }, [refreshNotifications])

  const hasUnread = unreadCount > 0

  return (
    <div className="relative">
      {/* Bell Icon Button */}
      <button
        type="button"
        className="relative flex size-6 items-center justify-center rounded-md transition hover:bg-zinc-900/5 dark:hover:bg-white/5"
        onClick={() => setIsOpen(!isOpen)}
        aria-label={hasUnread ? t('notifications.bellAriaLabelUnread', { count: unreadCount }) : t('notifications.bellAriaLabel')}
      >
        <span className="pointer-fine:hidden absolute size-12" />
        <BellIcon className="h-4 w-4 stroke-zinc-900 dark:stroke-white" />

        {/* Unread Count Badge */}
        {hasUnread && (
          <span className="absolute -right-1 -top-1 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-red-500 px-1 text-xs font-medium text-white">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {/* Notification Dropdown */}
      {isOpen && (
        <>
          {/* Backdrop for mobile */}
          <div
            className="fixed inset-0 z-40 lg:hidden"
            onClick={() => setIsOpen(false)}
            aria-hidden="true"
          />

          {/* Dropdown Panel */}
          <div className="absolute right-0 z-50 mt-2">
            <NotificationDropdown
              isOpen={isOpen}
              notifications={notifications}
              unreadCount={unreadCount}
              onClose={() => setIsOpen(false)}
              onMarkAsRead={markAsRead}
              onMarkAllAsRead={markAllAsRead}
              onRefresh={refreshNotifications}
            />
          </div>
        </>
      )}
    </div>
  )
}
