'use client'

import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Button } from '@/components/shared/Button'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { api } from '@/lib/api'
import {
  BellIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  InformationCircleIcon,
  UserPlusIcon,
} from '@heroicons/react/24/outline'
import { useState } from 'react'
import { toast } from 'react-hot-toast'

interface TestNotificationType {
  type: string
  title: string
  message: string
  description: string
  icon: React.ComponentType<any>
  color: string
  category: string
}

export default function TestNotificationsPage() {
  const { user } = useAuth()
  const { t } = useI18n()
  const [loading, setLoading] = useState<string | null>(null)

  if (!user?.is_superadmin) {
    return (
      <ResponsiveContainer size="xl" className="pb-10 pt-8">
        <div className="mb-4">
          <Breadcrumb
            items={[
              { label: t('navigation.dashboard'), href: '/dashboard' },
              {
                label: t('admin.testNotifications.breadcrumb'),
                href: '/admin/test-notifications',
              },
            ]}
          />
        </div>

        <div className="text-center">
          <h1 className="text-2xl font-bold text-red-600">
            {t('admin.accessDenied')}
          </h1>
          <p className="mt-2 text-zinc-600 dark:text-zinc-400">
            {t('admin.accessDeniedDesc')}
          </p>
        </div>
      </ResponsiveContainer>
    )
  }

  const testNotificationTypes: TestNotificationType[] = [
    {
      type: 'project_created',
      title: t('admin.testNotifications.types.projectCreated.title'),
      message: t('admin.testNotifications.types.projectCreated.message'),
      description: t('admin.testNotifications.types.projectCreated.description'),
      icon: InformationCircleIcon,
      color: 'text-blue-600 bg-blue-100 dark:text-blue-400 dark:bg-blue-900',
      category: t('admin.testNotifications.types.projectCreated.category'),
    },
    {
      type: 'project_completed',
      title: t('admin.testNotifications.types.projectCompleted.title'),
      message: t('admin.testNotifications.types.projectCompleted.message'),
      description: t('admin.testNotifications.types.projectCompleted.description'),
      icon: CheckCircleIcon,
      color:
        'text-green-600 bg-green-100 dark:text-green-400 dark:bg-green-900',
      category: t('admin.testNotifications.types.projectCompleted.category'),
    },
    {
      type: 'llm_generation_completed',
      title: t('admin.testNotifications.types.generationCompleted.title'),
      message: t('admin.testNotifications.types.generationCompleted.message'),
      description: t('admin.testNotifications.types.generationCompleted.description'),
      icon: CheckCircleIcon,
      color:
        'text-green-600 bg-green-100 dark:text-green-400 dark:bg-green-900',
      category: t('admin.testNotifications.types.generationCompleted.category'),
    },
    {
      type: 'evaluation_completed',
      title: t('admin.testNotifications.types.evaluationCompleted.title'),
      message: t('admin.testNotifications.types.evaluationCompleted.message'),
      description: t('admin.testNotifications.types.evaluationCompleted.description'),
      icon: CheckCircleIcon,
      color:
        'text-green-600 bg-green-100 dark:text-green-400 dark:bg-green-900',
      category: t('admin.testNotifications.types.evaluationCompleted.category'),
    },
    {
      type: 'evaluation_failed',
      title: t('admin.testNotifications.types.evaluationFailed.title'),
      message: t('admin.testNotifications.types.evaluationFailed.message'),
      description: t('admin.testNotifications.types.evaluationFailed.description'),
      icon: ExclamationTriangleIcon,
      color: 'text-red-600 bg-red-100 dark:text-red-400 dark:bg-red-900',
      category: t('admin.testNotifications.types.evaluationFailed.category'),
    },
    {
      type: 'annotation_completed',
      title: t('admin.testNotifications.types.annotationCompleted.title'),
      message: t('admin.testNotifications.types.annotationCompleted.message'),
      description: t('admin.testNotifications.types.annotationCompleted.description'),
      icon: CheckCircleIcon,
      color:
        'text-green-600 bg-green-100 dark:text-green-400 dark:bg-green-900',
      category: t('admin.testNotifications.types.annotationCompleted.category'),
    },
    {
      type: 'member_joined',
      title: t('admin.testNotifications.types.memberJoined.title'),
      message: t('admin.testNotifications.types.memberJoined.message'),
      description: t('admin.testNotifications.types.memberJoined.description'),
      icon: UserPlusIcon,
      color:
        'text-purple-600 bg-purple-100 dark:text-purple-400 dark:bg-purple-900',
      category: t('admin.testNotifications.types.memberJoined.category'),
    },
    {
      type: 'system_alert',
      title: t('admin.testNotifications.types.systemAlert.title'),
      message: t('admin.testNotifications.types.systemAlert.message'),
      description: t('admin.testNotifications.types.systemAlert.description'),
      icon: ExclamationTriangleIcon,
      color:
        'text-yellow-600 bg-yellow-100 dark:text-yellow-400 dark:bg-yellow-900',
      category: t('admin.testNotifications.types.systemAlert.category'),
    },
    {
      type: 'error_occurred',
      title: t('admin.testNotifications.types.errorOccurred.title'),
      message: t('admin.testNotifications.types.errorOccurred.message'),
      description: t('admin.testNotifications.types.errorOccurred.description'),
      icon: ExclamationTriangleIcon,
      color: 'text-red-600 bg-red-100 dark:text-red-400 dark:bg-red-900',
      category: t('admin.testNotifications.types.errorOccurred.category'),
    },
  ]

  const handleGenerateTestNotification = async (
    notificationType: TestNotificationType
  ) => {
    setLoading(notificationType.type)
    try {
      await api.notifications.createTestNotification({
        type: notificationType.type,
        title: notificationType.title,
        message: notificationType.message,
        data: {
          test: true,
          generated_at: new Date().toISOString(),
          category: notificationType.category,
        },
      })

      toast.success(t('admin.testNotifications.sent'))
    } catch (error) {
      console.error('Failed to generate test notification:', error)
      toast.error(t('admin.testNotifications.sendFailed'))
    } finally {
      setLoading(null)
    }
  }

  const handleGenerateAllTypes = async () => {
    setLoading('all')
    try {
      // Try using the bulk endpoint first, fallback to individual calls if not available
      try {
        const result = await api.notifications.generateTestNotifications()
        toast.success(
          result.message || `Generated ${result.count} test notifications!`
        )
      } catch (bulkError) {
        // Fallback: Generate one of each type with a small delay between them
        let successCount = 0
        for (const notificationType of testNotificationTypes) {
          try {
            await api.notifications.createTestNotification({
              type: notificationType.type,
              title: notificationType.title,
              message: notificationType.message,
              data: {
                test: true,
                generated_at: new Date().toISOString(),
                category: notificationType.category,
              },
            })
            successCount++
            await new Promise((resolve) => setTimeout(resolve, 200)) // Small delay
          } catch (individualError) {
            console.warn(
              `Failed to create ${notificationType.type}:`,
              individualError
            )
          }
        }

        if (successCount > 0) {
          toast.success(t('admin.testNotifications.sent'))
        } else {
          throw new Error('All individual requests failed')
        }
      }
    } catch (error) {
      console.error('Failed to generate all test notifications:', error)
      toast.error(t('admin.testNotifications.sendFailed'))
    } finally {
      setLoading(null)
    }
  }

  const handleClearAllNotifications = async () => {
    if (!confirm(t('admin.testNotifications.clearConfirm'))) {
      return
    }

    setLoading('clear')
    try {
      await api.markAllNotificationsAsRead()
      toast.success(t('admin.testNotifications.cleared'))
    } catch (error) {
      console.error('Failed to clear notifications:', error)
      toast.error(t('admin.testNotifications.clearFailed'))
    } finally {
      setLoading(null)
    }
  }

  // Group notifications by category
  const groupedNotifications = testNotificationTypes.reduce(
    (acc, notification) => {
      if (!acc[notification.category]) {
        acc[notification.category] = []
      }
      acc[notification.category].push(notification)
      return acc
    },
    {} as Record<string, TestNotificationType[]>
  )

  return (
    <ResponsiveContainer size="xl" className="pb-10 pt-8">
      <div className="mb-4">
        <Breadcrumb
          items={[
            { label: t('navigation.dashboard'), href: '/dashboard' },
            { label: t('admin.testNotifications.breadcrumb'), href: '/admin/test-notifications' },
          ]}
        />
      </div>

      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
          {t('admin.testNotifications.title')}
        </h1>
        <p className="mt-2 text-lg text-zinc-600 dark:text-zinc-400">
          {t('admin.testNotifications.description')}
        </p>
      </div>

      {/* Bulk Actions */}
      <div className="mb-8 rounded-lg bg-white p-6 shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-900 dark:ring-white/10">
        <h2 className="mb-4 text-lg font-medium text-zinc-900 dark:text-white">
          {t('admin.testNotifications.bulkActions')}
        </h2>
        <div className="flex flex-wrap gap-4">
          <Button
            onClick={handleGenerateAllTypes}
            disabled={loading !== null}
            className="bg-emerald-600 hover:bg-emerald-700"
          >
            {loading === 'all' ? (
              <>
                <div className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                {t('admin.testNotifications.generating')}
              </>
            ) : (
              <>
                <BellIcon className="mr-2 h-4 w-4" />
                {t('admin.testNotifications.generateAll')}
              </>
            )}
          </Button>

          <Button
            onClick={handleClearAllNotifications}
            disabled={loading !== null}
            variant="outline"
          >
            {loading === 'clear' ? (
              <>
                <div className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-zinc-400 border-t-transparent" />
                {t('admin.testNotifications.clearing')}
              </>
            ) : (
              t('admin.testNotifications.clearAll')
            )}
          </Button>
        </div>
      </div>

      {/* Test Notification Types */}
      <div className="space-y-8">
        {Object.entries(groupedNotifications).map(
          ([category, notifications]) => (
            <div
              key={category}
              className="rounded-lg bg-white p-6 shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-900 dark:ring-white/10"
            >
              <h2 className="mb-4 text-lg font-medium text-zinc-900 dark:text-white">
                {t('admin.testNotifications.categoryHeader', { category })}
              </h2>
              <div className="grid grid-cols-1 gap-4">
                {notifications.map((notification) => {
                  const IconComponent = notification.icon
                  const isLoading = loading === notification.type

                  return (
                    <div
                      key={notification.type}
                      className="flex items-start gap-4 rounded-lg border border-zinc-200 p-4 dark:border-zinc-700"
                    >
                      <div
                        className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full ${notification.color}`}
                      >
                        <IconComponent className="h-5 w-5" />
                      </div>

                      <div className="min-w-0 flex-1">
                        <h3 className="text-sm font-medium text-zinc-900 dark:text-white">
                          {notification.title}
                        </h3>
                        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                          {notification.message}
                        </p>
                        <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-500">
                          {notification.description}
                        </p>
                      </div>

                      <Button
                        onClick={() =>
                          handleGenerateTestNotification(notification)
                        }
                        disabled={loading !== null}
                        variant="outline"
                        className="text-sm"
                      >
                        {isLoading ? (
                          <>
                            <div className="mr-1 h-3 w-3 animate-spin rounded-full border border-zinc-400 border-t-transparent" />
                            {t('admin.testNotifications.generating')}
                          </>
                        ) : (
                          t('admin.testNotifications.generate')
                        )}
                      </Button>
                    </div>
                  )
                })}
              </div>
            </div>
          )
        )}
      </div>

      {/* Implementation Status */}
      <div className="mt-8 rounded-lg bg-blue-50 p-6 ring-1 ring-blue-200 dark:bg-blue-900/20 dark:ring-blue-700">
        <h3 className="text-sm font-medium text-blue-800 dark:text-blue-200">
          {t('admin.testNotifications.status.title')}
        </h3>
        <div className="mt-2 text-sm text-blue-700 dark:text-blue-300">
          <p className="mb-2">
            {t('admin.testNotifications.status.description')}
          </p>
          <ul className="list-inside list-disc space-y-1">
            <li className="text-green-600 dark:text-green-400">
              {t('admin.testNotifications.status.item1')}
            </li>
            <li className="text-green-600 dark:text-green-400">
              {t('admin.testNotifications.status.item2')}
            </li>
            <li className="text-green-600 dark:text-green-400">
              {t('admin.testNotifications.status.item3')}
            </li>
            <li>{t('admin.testNotifications.status.item4')}</li>
            <li>{t('admin.testNotifications.status.item5')}</li>
            <li>{t('admin.testNotifications.status.item6')}</li>
          </ul>
          <p className="mt-2 text-xs">
            {t('admin.testNotifications.status.note')}
          </p>
        </div>
      </div>
    </ResponsiveContainer>
  )
}
