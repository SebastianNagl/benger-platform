'use client'

import { Notification } from '@/components/layout/NotificationDropdown'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Button } from '@/components/shared/Button'
import { FilterToolbar } from '@/components/shared/FilterToolbar'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shared/Select'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { useNotifications } from '@/hooks/useNotifications'
import { api } from '@/lib/api'
import { getTranslatedNotification } from '@/lib/notificationTranslation'
import {
  ArrowPathIcon,
  ChartBarIcon,
  CheckCircleIcon,
  CheckIcon,
  ExclamationTriangleIcon,
  InformationCircleIcon,
  TrashIcon,
  UserPlusIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'
import { formatDistanceToNow } from 'date-fns'
import { de } from 'date-fns/locale'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useCallback, useEffect, useState } from 'react'

const notificationIcons = {
  task_created: InformationCircleIcon,
  task_completed: CheckCircleIcon,
  llm_generation_completed: CheckCircleIcon,
  annotation_completed: CheckCircleIcon,
  member_joined: UserPlusIcon,
  system_alert: ExclamationTriangleIcon,
  error_occurred: ExclamationTriangleIcon,
}

const notificationColors = {
  task_created: 'text-blue-600 bg-blue-100 dark:text-blue-400 dark:bg-blue-900',
  task_completed:
    'text-green-600 bg-green-100 dark:text-green-400 dark:bg-green-900',
  llm_generation_completed:
    'text-green-600 bg-green-100 dark:text-green-400 dark:bg-green-900',
  annotation_completed:
    'text-green-600 bg-green-100 dark:text-green-400 dark:bg-green-900',
  member_joined:
    'text-indigo-600 bg-indigo-100 dark:text-indigo-400 dark:bg-indigo-900',
  system_alert:
    'text-amber-600 bg-amber-100 dark:text-amber-400 dark:bg-amber-900',
  error_occurred: 'text-red-600 bg-red-100 dark:text-red-400 dark:bg-red-900',
}

function NotificationsPageContent() {
  const { user } = useAuth()
  const router = useRouter()
  const { t, locale } = useI18n()

  const dateFnsLocale = locale === 'de' ? de : undefined

  // Use the notifications hook for real-time updates
  const {
    notifications: hookNotifications,
    unreadCount: hookUnreadCount,
    isLoading: hookLoading,
    markAsRead,
    markAllAsRead,
    refreshNotifications,
    fetchNotifications: fetchMoreNotifications,
  } = useNotifications()

  // Local state for additional notifications from pagination
  const [additionalNotifications, setAdditionalNotifications] = useState<
    Notification[]
  >([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Combine hook notifications with additional loaded notifications
  const allNotifications = [...hookNotifications, ...additionalNotifications]
  const unreadCount = hookUnreadCount

  // Enhanced filtering state (Fix for Issue #425: Filter dropdown limitations)
  const [filter, setFilter] = useState<'all' | 'unread' | 'read'>('all')
  const [typeFilter, setTypeFilter] = useState<string>('all')
  const [dateFilter, setDateFilter] = useState<
    'all' | 'today' | 'week' | 'month'
  >('all')
  const [searchTerm, setSearchTerm] = useState('')
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(true)
  const [markingAsRead, setMarkingAsRead] = useState<string | null>(null)
  const [availableTypes, setAvailableTypes] = useState<Set<string>>(new Set())
  const [markingAllAsRead, setMarkingAllAsRead] = useState(false)

  const [selectedNotifications, setSelectedNotifications] = useState<
    Set<string>
  >(new Set())
  const [showBulkActions, setShowBulkActions] = useState(false)

  // Client-side filtering of notifications
  const notifications = allNotifications.filter((n) => {
    if (filter === 'unread' && n.is_read) return false
    if (filter === 'read' && !n.is_read) return false
    if (typeFilter !== 'all' && n.type !== typeFilter) return false
    if (dateFilter !== 'all') {
      const now = new Date()
      const created = new Date(n.created_at)
      if (dateFilter === 'today') {
        const startOfDay = new Date(now.getFullYear(), now.getMonth(), now.getDate())
        if (created < startOfDay) return false
      } else if (dateFilter === 'week') {
        const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
        if (created < weekAgo) return false
      } else if (dateFilter === 'month') {
        const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1)
        if (created < startOfMonth) return false
      }
    }
    if (searchTerm.trim()) {
      const term = searchTerm.toLowerCase()
      return (
        (n.title?.toLowerCase().includes(term) ?? false) ||
        (n.message?.toLowerCase().includes(term) ?? false) ||
        (n.type?.toLowerCase().includes(term) ?? false)
      )
    }
    return true
  })

  const fetchNotifications = useCallback(
    async (pageNum: number = 1, reset: boolean = true) => {
      // For page 1, we already have data from the hook, so just refresh
      if (pageNum === 1 && reset) {
        await refreshNotifications()
        setAdditionalNotifications([])
        return
      }

      // For pagination, fetch additional notifications
      try {
        setLoading(true)

        const params = new URLSearchParams({
          page: pageNum.toString(),
          limit: '20',
          offset: ((pageNum - 1) * 20).toString(),
        })

        if (filter !== 'all') {
          params?.append('read_status', filter === 'read' ? 'true' : 'false')
        }

        if (typeFilter !== 'all') {
          params?.append('type', typeFilter)
        }

        if (dateFilter !== 'all') {
          const now = new Date()
          let fromDate: Date

          switch (dateFilter) {
            case 'today':
              fromDate = new Date(
                now.getFullYear(),
                now.getMonth(),
                now.getDate()
              )
              break
            case 'week':
              fromDate = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
              break
            case 'month':
              fromDate = new Date(now.getFullYear(), now.getMonth(), 1)
              break
            default:
              fromDate = new Date(0)
          }

          params?.append('from_date', fromDate.toISOString())
        }

        if (searchTerm.trim()) {
          params?.append('search', searchTerm.trim())
        }

        const data = await api.getNotifications(params?.toString())

        if (reset) {
          setAdditionalNotifications([])
          // Update available notification types for dynamic filtering
          const types = new Set<string>(data?.map((n: any) => n.type) || [])
          setAvailableTypes(types)
        } else {
          setAdditionalNotifications((prev) => [...prev, ...(data || [])])
        }

        setHasMore((data || []).length === 20)
      } catch (err) {
        console.error('Failed to fetch notifications:', err)
        setError(t('notifications.loadFailed'))
      } finally {
        setLoading(false)
      }
    },
    [filter, typeFilter, dateFilter, searchTerm, refreshNotifications]
  )

  useEffect(() => {
    if (user) {
      // Update available types from the hook notifications
      const types = new Set(hookNotifications.map((n: any) => n.type))
      setAvailableTypes(types)
    }
  }, [user, hookNotifications])

  const handleLoadMore = () => {
    const nextPage = page + 1
    setPage(nextPage)
    fetchNotifications(nextPage, false)
  }

  const handleMarkAsRead = async (id: string) => {
    setMarkingAsRead(id)
    try {
      // Use the hook's markAsRead function which handles state updates
      await markAsRead(id)
      // Update additional notifications if needed
      setAdditionalNotifications((prev) =>
        prev.map((n: any) => (n.id === id ? { ...n, is_read: true } : n))
      )
    } catch (err) {
      console.error('Failed to mark notification as read:', err)
    } finally {
      setMarkingAsRead(null)
    }
  }

  const handleMarkAllAsRead = async () => {
    setMarkingAllAsRead(true)
    try {
      // Use the hook's markAllAsRead function which handles state updates
      await markAllAsRead()
      // Update additional notifications if needed
      setAdditionalNotifications((prev) =>
        prev.map((n: any) => ({ ...n, is_read: true }))
      )
    } catch (err) {
      console.error('Failed to mark all notifications as read:', err)
    } finally {
      setMarkingAllAsRead(false)
    }
  }

  const handleNotificationClick = async (notification: Notification) => {
    // Mark as read if unread
    if (!notification.is_read) {
      await handleMarkAsRead(notification.id)
    }

    // Navigate to related project if project_id is available
    if (notification.data?.project_id) {
      router.push(`/projects/${notification.data.project_id}`)
    }
  }

  const handleRefresh = () => {
    refreshNotifications()
    setAdditionalNotifications([])
    setPage(1)
  }

  // New functions for advanced features

  const handleSelectNotification = (id: string, checked: boolean) => {
    const newSelected = new Set(selectedNotifications)
    if (checked) {
      newSelected.add(id)
    } else {
      newSelected.delete(id)
    }
    setSelectedNotifications(newSelected)
    setShowBulkActions(newSelected.size > 0)
  }

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      const allIds = new Set(notifications.map((n: any) => n.id))
      setSelectedNotifications(allIds)
      setShowBulkActions(true)
    } else {
      setSelectedNotifications(new Set())
      setShowBulkActions(false)
    }
  }

  const handleBulkMarkAsRead = async () => {
    try {
      await api.markNotificationsBulkAsRead(Array.from(selectedNotifications))
      // Mark notifications as read in the additional list
      setAdditionalNotifications((prev) =>
        prev.map((n: any) =>
          selectedNotifications.has(n.id) ? { ...n, is_read: true } : n
        )
      )
      // Refresh hook notifications to get updated read status
      await refreshNotifications()
      setSelectedNotifications(new Set())
      setShowBulkActions(false)
    } catch (err) {
      console.error('Failed to bulk mark as read:', err)
    }
  }

  const handleBulkDelete = async () => {
    if (!confirm(t('notifications.deleteConfirm'))) {
      return
    }

    try {
      await api.deleteNotificationsBulk(Array.from(selectedNotifications))
      // Remove deleted notifications from additional list
      setAdditionalNotifications((prev) =>
        prev.filter((n) => !selectedNotifications.has(n.id))
      )
      // Refresh hook notifications to reflect deletions
      await refreshNotifications()
      setSelectedNotifications(new Set())
      setShowBulkActions(false)
    } catch (err) {
      console.error('Failed to bulk delete:', err)
    }
  }

  // Function to clear all filters
  const clearAllFilters = () => {
    setFilter('all')
    setTypeFilter('all')
    setDateFilter('all')
    setSearchTerm('')
  }

  // Check if any filters are active
  const hasActiveFilters =
    filter !== 'all' ||
    typeFilter !== 'all' ||
    dateFilter !== 'all' ||
    searchTerm.trim() !== ''

  // Helper to translate notification type label for filter dropdown
  const getTypeLabel = (type: string) => {
    const translatedTitle = t(
      `notifications.content.${type}.title`,
      type
        .split('_')
        .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ')
    )
    // Strip variable placeholders for the label display
    return typeof translatedTitle === 'string'
      ? translatedTitle.replace(/[:{]\w+}/g, '').replace(/\s+/g, ' ').trim()
      : translatedTitle
  }

  if (!user) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <div className="text-center">
          <h2 className="mb-4 text-2xl font-bold text-zinc-900 dark:text-white">
            {t('notifications.authRequired')}
          </h2>
          <p className="text-zinc-600 dark:text-zinc-400">
            {t('notifications.authRequiredMessage')}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-7xl py-8">
      {/* Breadcrumb */}
      <div className="mb-4">
        <Breadcrumb
          items={[
            {
              label: t('navigation.dashboard') || 'Dashboard',
              href: '/dashboard',
            },
            {
              label: t('notifications.title') || 'Notifications',
              href: '/notifications',
            },
          ]}
        />
      </div>

      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
          {t('notifications.title')}
        </h1>
        <p className="mt-2 text-lg text-zinc-600 dark:text-zinc-400">
          {t('notifications.subtitle')}
        </p>
      </div>

      {/* Action Bar */}
      <FilterToolbar
        searchValue={searchTerm}
        onSearchChange={setSearchTerm}
        searchPlaceholder={t('notifications.searchPlaceholder')}
        searchLabel={t('common.filters.search')}
        filtersLabel={t('common.filters.filters')}
        hasActiveFilters={hasActiveFilters}
        onClearFilters={clearAllFilters}
        clearLabel={t('notifications.clearFilters')}
        rightExtras={
          <>
            <Link href="/notifications/analytics">
              <Button variant="outline" className="flex items-center">
                <ChartBarIcon className="h-4 w-4" />
                <span className="ml-2 hidden sm:inline">
                  {t('notifications.analyticsTitle')}
                </span>
              </Button>
            </Link>
            <Button
              onClick={handleRefresh}
              variant="outline"
              className="flex items-center"
              disabled={hookLoading || loading}
              title={t('notifications.refresh')}
            >
              <ArrowPathIcon className="h-4 w-4" />
            </Button>
            {unreadCount > 0 && (
              <Button
                onClick={handleMarkAllAsRead}
                variant="outline"
                disabled={markingAllAsRead}
              >
                <CheckIcon className="h-4 w-4" />
                <span className="ml-2">
                  {markingAllAsRead
                    ? '...'
                    : `${t('notifications.markAllRead')} (${unreadCount})`}
                </span>
              </Button>
            )}
          </>
        }
      >
        <FilterToolbar.Field label={t('notifications.all')}>
          <Select
            value={filter}
            onValueChange={(v) => setFilter(v as typeof filter)}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('notifications.all')}</SelectItem>
              <SelectItem value="unread">{t('notifications.unread')}</SelectItem>
              <SelectItem value="read">{t('notifications.read')}</SelectItem>
            </SelectContent>
          </Select>
        </FilterToolbar.Field>

        <FilterToolbar.Field label={t('notifications.allTypes')}>
          <Select value={typeFilter} onValueChange={setTypeFilter}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('notifications.allTypes')}</SelectItem>
              {Array.from(availableTypes).map((type) => (
                <SelectItem key={type} value={type}>
                  {type
                    .split('_')
                    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
                    .join(' ')}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FilterToolbar.Field>

        <FilterToolbar.Field label={t('notifications.allTime')}>
          <Select
            value={dateFilter}
            onValueChange={(v) => setDateFilter(v as typeof dateFilter)}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('notifications.allTime')}</SelectItem>
              <SelectItem value="today">{t('notifications.today')}</SelectItem>
              <SelectItem value="week">{t('notifications.pastWeek')}</SelectItem>
              <SelectItem value="month">{t('notifications.pastMonth')}</SelectItem>
            </SelectContent>
          </Select>
        </FilterToolbar.Field>
      </FilterToolbar>

      {/* Bulk Actions Bar */}
      {showBulkActions && (
        <div className="flex items-center gap-4 rounded-lg border border-zinc-200 bg-white px-4 py-3 dark:border-zinc-700 dark:bg-zinc-900">
          <span className="text-sm font-medium text-emerald-900 dark:text-emerald-100">
            {t('notifications.selected', { count: selectedNotifications.size })}
          </span>
          <div className="flex gap-2">
            <Button
              onClick={handleBulkMarkAsRead}
              variant="outline"
              className="text-sm"
            >
              <CheckIcon className="mr-1 h-4 w-4" />
              {t('notifications.markRead')}
            </Button>
            <Button
              onClick={handleBulkDelete}
              variant="outline"
              className="border-red-300 text-sm text-red-600 hover:border-red-400 hover:text-red-700"
            >
              <TrashIcon className="mr-1 h-4 w-4" />
              {t('notifications.delete')}
            </Button>
            <Button
              onClick={() => {
                setSelectedNotifications(new Set())
                setShowBulkActions(false)
              }}
              variant="outline"
              className="text-sm"
            >
              <XMarkIcon className="mr-1 h-4 w-4" />
              {t('notifications.cancel')}
            </Button>
          </div>
        </div>
      )}


      {/* Notifications Display */}
      {hookLoading || loading ? (
        <div className="flex min-h-[200px] items-center justify-center">
          <div className="mx-auto h-8 w-8 animate-spin rounded-full border-b-2 border-emerald-500"></div>
          <span className="ml-3 text-zinc-600 dark:text-zinc-400">
            {t('notifications.loading')}
          </span>
        </div>
      ) : error ? (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-950">
          <div className="flex">
            <ExclamationTriangleIcon className="h-5 w-5 flex-shrink-0 text-red-600 dark:text-red-400" />
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800 dark:text-red-200">
                {t('notifications.errorTitle')}
              </h3>
              <p className="mt-1 text-sm text-red-700 dark:text-red-300">{error}</p>
              <button
                onClick={handleRefresh}
                className="mt-2 text-sm font-medium text-red-800 underline hover:text-red-900 dark:text-red-200 dark:hover:text-red-100"
              >
                {t('notifications.tryAgain')}
              </button>
            </div>
          </div>
        </div>
      ) : notifications.length === 0 ? (
        <div className="rounded-lg border border-zinc-200 bg-white p-8 dark:border-zinc-700 dark:bg-zinc-900">
          <div className="text-center">
            <InformationCircleIcon className="mx-auto mb-4 h-12 w-12 text-zinc-400" />
            <h3 className="mb-2 text-lg font-medium text-zinc-900 dark:text-white">
              {t('notifications.noNotifications')}
            </h3>
            <p className="text-zinc-600 dark:text-zinc-400">
              {filter === 'unread'
                ? t('notifications.allCaughtUp')
                : searchTerm
                  ? t('notifications.noMatches')
                  : t('notifications.noNotificationsDescription')}
            </p>
          </div>
        </div>
      ) : (
        <>
          <div className="overflow-hidden rounded-lg border border-zinc-200 dark:border-zinc-700">
            <table className="min-w-full divide-y divide-zinc-200 dark:divide-zinc-700">
              <thead className="bg-zinc-50 dark:bg-zinc-800">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500">
                    {t('notifications.columnNotification', 'Notification')}
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500">
                    {t('notifications.columnTime', 'Time')}
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500">
                    {t('notifications.columnStatus', 'Status')}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-200 bg-white dark:divide-zinc-700 dark:bg-zinc-900">
                {notifications.map((notification) => {
                  const IconComponent =
                    notificationIcons[
                      notification.type as keyof typeof notificationIcons
                    ] || InformationCircleIcon
                  const colorClass =
                    notificationColors[
                      notification.type as keyof typeof notificationColors
                    ] ||
                    'text-zinc-600 bg-zinc-100 dark:text-zinc-400 dark:bg-zinc-800'
                  const { title: translatedTitle, message: translatedMessage } =
                    getTranslatedNotification(t, notification)

                  return (
                    <tr
                      key={notification.id}
                      className={`hover:bg-zinc-50 dark:hover:bg-zinc-800 ${notification.data?.project_id ? 'cursor-pointer' : ''}`}
                      onClick={() => handleNotificationClick(notification)}
                    >
                      <td className="px-6 py-4">
                        <div className="flex items-start gap-3">
                          <div
                            className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full ${colorClass}`}
                          >
                            <IconComponent className="h-4 w-4" />
                          </div>
                          <div className="min-w-0">
                            <div
                              className={`text-sm font-medium ${!notification.is_read ? 'text-zinc-900 dark:text-white' : 'text-zinc-700 dark:text-zinc-300'}`}
                            >
                              {translatedTitle}
                            </div>
                            <div
                              className={`mt-0.5 text-sm ${!notification.is_read ? 'text-zinc-600 dark:text-zinc-400' : 'text-zinc-500 dark:text-zinc-500'}`}
                            >
                              {translatedMessage}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td className="whitespace-nowrap px-6 py-4 text-sm text-zinc-500 dark:text-zinc-400">
                        {formatDistanceToNow(
                          new Date(notification.created_at),
                          { addSuffix: true, locale: dateFnsLocale }
                        )}
                      </td>
                      <td className="px-6 py-4">
                        {!notification.is_read ? (
                          <span className="inline-flex items-center rounded-full bg-emerald-100 px-2 py-1 text-xs font-medium text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-400">
                            {t('notifications.new')}
                          </span>
                        ) : (
                          <span className="inline-flex items-center rounded-full bg-zinc-100 px-2 py-1 text-xs font-medium text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
                            {t('notifications.read')}
                          </span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* Load More */}
          {hasMore && (
            <div className="pt-4 text-center">
              <Button
                onClick={handleLoadMore}
                variant="outline"
                disabled={hookLoading || loading}
                className="text-sm"
              >
                {loading ? (
                  <>
                    <ArrowPathIcon className="mr-2 h-4 w-4 animate-spin" />
                    {t('notifications.loadingMore')}
                  </>
                ) : (
                  t('notifications.loadMore')
                )}
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default function NotificationsPage() {
  return (
    <ResponsiveContainer
      size="full"
      className="px-4 pb-10 pt-8 sm:px-6 lg:px-8"
    >
      <NotificationsPageContent />
    </ResponsiveContainer>
  )
}
