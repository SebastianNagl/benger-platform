'use client'

import { useI18n } from '@/contexts/I18nContext'
import api from '@/lib/api'
import {
  NotificationGroupsResponse,
  NotificationSummaryResponse,
} from '@/lib/api/notifications'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/shared/Select'
import {
  BellIcon,
  ChartBarIcon,
  CheckCircleIcon,
  ClockIcon,
  ExclamationTriangleIcon,
  InformationCircleIcon,
} from '@heroicons/react/24/outline'
import { useCallback, useEffect, useState } from 'react'

const timeRangeValues = [7, 14, 30, 90] as const
const groupByValues = ['type', 'date', 'organization'] as const

interface ChartData {
  name: string
  value: number
  color: string
}

const typeIcons: Record<string, any> = {
  task_created: InformationCircleIcon,
  evaluation_completed: CheckCircleIcon,
  evaluation_failed: ExclamationTriangleIcon,
  data_upload_completed: CheckCircleIcon,
  llm_generation_completed: CheckCircleIcon,
  organization_invitation_sent: BellIcon,
  organization_invitation_accepted: CheckCircleIcon,
  system_alert: ExclamationTriangleIcon,
  error_occurred: ExclamationTriangleIcon,
}

const typeColors: Record<string, string> = {
  task_created: '#3b82f6',
  evaluation_completed: '#10b981',
  evaluation_failed: '#ef4444',
  data_upload_completed: '#10b981',
  llm_generation_completed: '#8b5cf6',
  organization_invitation_sent: '#f59e0b',
  organization_invitation_accepted: '#10b981',
  system_alert: '#ef4444',
  error_occurred: '#ef4444',
}

function SimpleBarChart({ data, title, noDataText }: { data: ChartData[]; title: string; noDataText: string }) {
  const maxValue = Math.max(...data.map((item) => item.value))

  return (
    <div className="rounded-lg bg-white p-6 shadow-md">
      <h3 className="mb-4 text-lg font-medium text-gray-900">{title}</h3>
      <div className="space-y-3">
        {data.map((item, index) => (
          <div key={index} className="flex items-center">
            <div
              className="w-24 truncate text-sm text-gray-600"
              title={item.name}
            >
              {item.name}
            </div>
            <div className="mx-3 flex-1">
              <div className="relative h-4 rounded-full bg-gray-200">
                <div
                  className="h-4 rounded-full"
                  style={{
                    width: `${(item.value / maxValue) * 100}%`,
                    backgroundColor: item.color,
                  }}
                />
              </div>
            </div>
            <div className="w-12 text-right text-sm font-medium text-gray-900">
              {item.value}
            </div>
          </div>
        ))}
        {data.length === 0 && (
          <div className="py-4 text-center text-gray-500">
            {noDataText}
          </div>
        )}
      </div>
    </div>
  )
}

function StatCard({
  title,
  value,
  subtitle,
  icon: Icon,
  color,
}: {
  title: string
  value: number | string
  subtitle?: string
  icon: any
  color: string
}) {
  return (
    <div className="rounded-lg bg-white p-6 shadow-md">
      <div className="flex items-center">
        <div className={`rounded-lg p-2 ${color}`}>
          <Icon className="h-6 w-6 text-white" />
        </div>
        <div className="ml-4">
          <h3 className="text-sm font-medium text-gray-500">{title}</h3>
          <p className="text-2xl font-bold text-gray-900">{value}</p>
          {subtitle && <p className="text-sm text-gray-600">{subtitle}</p>}
        </div>
      </div>
    </div>
  )
}

export default function NotificationAnalyticsPage() {
  const { t } = useI18n()

  const timeRangeOptions = [
    { value: 7, label: t('notifications.analytics.timeRange.last7Days') },
    { value: 14, label: t('notifications.analytics.timeRange.last2Weeks') },
    { value: 30, label: t('notifications.analytics.timeRange.last30Days') },
    { value: 90, label: t('notifications.analytics.timeRange.last3Months') },
  ]

  const groupByOptions = [
    { value: 'type' as const, label: t('notifications.analytics.groupBy.byType') },
    { value: 'date' as const, label: t('notifications.analytics.groupBy.byDate') },
    { value: 'organization' as const, label: t('notifications.analytics.groupBy.byOrganization') },
  ]

  const [summary, setSummary] = useState<NotificationSummaryResponse | null>(
    null
  )
  const [groups, setGroups] = useState<NotificationGroupsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [timeRange, setTimeRange] = useState(7)
  const [groupBy, setGroupBy] = useState<'type' | 'date' | 'organization'>(
    'type'
  )

  const loadAnalytics = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)

      const [summaryData, groupsData] = await Promise.all([
        api.getNotificationSummary(timeRange),
        api.getNotificationGroups(groupBy, 50),
      ])

      setSummary(summaryData)
      setGroups(groupsData)
    } catch (err) {
      console.error('Error loading notification analytics:', err)
      setError(t('notifications.analytics.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [timeRange, groupBy])

  useEffect(() => {
    loadAnalytics()
  }, [loadAnalytics])

  const formatTypeLabel = (type: string): string => {
    return type
      .split('_')
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
      .join(' ')
  }

  const getTypeChartData = (): ChartData[] => {
    if (!summary?.notifications_by_type) return []

    return Object.entries(summary.notifications_by_type)
      .map(([type, count]) => ({
        name: formatTypeLabel(type),
        value: count,
        color: typeColors[type] || '#6b7280',
      }))
      .sort((a, b) => b.value - a.value)
  }

  const getGroupChartData = (): ChartData[] => {
    if (!groups?.groups) return []

    return Object.entries(groups.groups)
      .map(([key, notifications]) => ({
        name: groupBy === 'type' ? formatTypeLabel(key) : key,
        value: notifications.length,
        color: groupBy === 'type' ? typeColors[key] || '#6b7280' : '#3b82f6',
      }))
      .sort((a, b) => b.value - a.value)
  }

  const getReadRate = (): number => {
    if (!summary || summary.total_notifications === 0) return 0
    return Math.round(
      (summary.read_notifications / summary.total_notifications) * 100
    )
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-7xl p-6">
        <div className="animate-pulse">
          <div className="mb-6 h-8 w-1/3 rounded bg-gray-200"></div>
          <div className="mb-8 grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-32 rounded bg-gray-200"></div>
            ))}
          </div>
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {[1, 2].map((i) => (
              <div key={i} className="h-64 rounded bg-gray-200"></div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-7xl p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            {t('notifications.analyticsTitle')}
          </h1>
          <p className="mt-1 text-gray-600">
            {t('notifications.analytics.subtitle')}
          </p>
        </div>

        <div className="flex space-x-4">
          <Select value={timeRange.toString()} onValueChange={(v) => setTimeRange(Number(v))} displayValue={timeRangeOptions.find(o => o.value === timeRange)?.label}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {timeRangeOptions.map((option) => (
                <SelectItem key={option.value} value={option.value.toString()}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select value={groupBy} onValueChange={(v) => setGroupBy(v as 'type' | 'date' | 'organization')} displayValue={groupByOptions.find(o => o.value === groupBy)?.label}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {groupByOptions.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {error && (
        <div className="mb-6 rounded-md border border-red-200 bg-red-50 p-4">
          <div className="flex">
            <ExclamationTriangleIcon className="mr-2 h-5 w-5 text-red-400" />
            <p className="text-red-700">{error}</p>
          </div>
        </div>
      )}

      {summary && (
        <>
          {/* Statistics Cards */}
          <div className="mb-8 grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-4">
            <StatCard
              title={t('notifications.totalNotifications')}
              value={summary.total_notifications}
              subtitle={t('notifications.analytics.lastNDays', { days: summary.period_days })}
              icon={BellIcon}
              color="bg-blue-500"
            />

            <StatCard
              title={t('notifications.unreadCount')}
              value={summary.unread_notifications}
              subtitle={t('notifications.analytics.percentOfTotal', { percent: summary.total_notifications > 0 ? Math.round((summary.unread_notifications / summary.total_notifications) * 100) : 0 })}
              icon={ExclamationTriangleIcon}
              color="bg-orange-500"
            />

            <StatCard
              title={t('notifications.readCount')}
              value={summary.read_notifications}
              subtitle={t('notifications.analytics.readRate', { percent: getReadRate() })}
              icon={CheckCircleIcon}
              color="bg-green-500"
            />

            <StatCard
              title={t('notifications.analytics.typesTitle')}
              value={Object.keys(summary.notifications_by_type).length}
              subtitle={t('notifications.analytics.typesSubtitle')}
              icon={ChartBarIcon}
              color="bg-purple-500"
            />
          </div>

          {/* Charts */}
          <div className="mb-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
            <SimpleBarChart
              data={getTypeChartData()}
              title={t('notifications.byType')}
              noDataText={t('notifications.analytics.noData')}
            />

            <SimpleBarChart
              data={getGroupChartData()}
              title={t('notifications.analytics.chartTitle', { groupBy: groupByOptions.find((opt) => opt.value === groupBy)?.label })}
              noDataText={t('notifications.analytics.noData')}
            />
          </div>

          {/* Recent Activity by Type */}
          <div className="rounded-lg bg-white p-6 shadow-md">
            <h3 className="mb-4 text-lg font-medium text-gray-900">
              {t('notifications.analytics.recentActivityDetails')}
            </h3>

            {Object.keys(summary.notifications_by_type).length === 0 ? (
              <div className="py-8 text-center text-gray-500">
                <BellIcon className="mx-auto mb-3 h-12 w-12 text-gray-400" />
                <p>{t('notifications.analytics.noNotifications')}</p>
                <p className="text-sm">{t('notifications.analytics.tryLongerRange')}</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
                {Object.entries(summary.notifications_by_type)
                  .sort(([, a], [, b]) => b - a)
                  .map(([type, count]) => {
                    const IconComponent = typeIcons[type] || BellIcon
                    return (
                      <div
                        key={type}
                        className="flex items-center rounded-lg border border-gray-200 p-3"
                      >
                        <div
                          className="mr-3 rounded-lg p-2"
                          style={{
                            backgroundColor: typeColors[type] || '#6b7280',
                          }}
                        >
                          <IconComponent className="h-5 w-5 text-white" />
                        </div>
                        <div>
                          <p className="font-medium text-gray-900">
                            {formatTypeLabel(type)}
                          </p>
                          <p className="text-sm text-gray-600">
                            {t('notifications.analytics.notificationCount', { count })}
                          </p>
                        </div>
                      </div>
                    )
                  })}
              </div>
            )}
          </div>

          {/* Summary Information */}
          <div className="mt-6 rounded-lg bg-gray-50 p-4">
            <div className="flex items-center text-sm text-gray-600">
              <ClockIcon className="mr-2 h-4 w-4" />
              <span>
                {t('notifications.analytics.generatedAt', { date: new Date(summary.summary_generated_at).toLocaleString(), days: summary.period_days })}
              </span>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
