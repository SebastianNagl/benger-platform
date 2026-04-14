'use client'

import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { useI18n } from '@/contexts/I18nContext'
import {
  Activity,
  AlertTriangle,
  BarChart3,
  CheckCircle,
  Clock,
  Mail,
  RefreshCw,
  Send,
  Trash2,
  Users,
  XCircle,
} from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

interface VerificationStatistics {
  total_users: number
  verified_users: number
  unverified_users: number
  verification_rate_percent: number
  recent_unverified: number
  pending_verification: number
  expired_tokens: number
  period_days: number
  generated_at: string
}

interface UnverifiedUser {
  id: string
  username: string
  email: string
  name: string
  created_at: string
  email_verification_sent_at: string | null
  has_verification_token: boolean
  days_since_registration: number
}

interface StatisticsReport {
  weekly_stats: VerificationStatistics
  monthly_stats: VerificationStatistics
  trends: {
    weekly_verification_rate: number
    monthly_verification_rate: number
    rate_trend: string
  }
  alerts: Array<{
    level: string
    message: string
  }>
}

export default function EmailVerificationManagement() {
  const { t } = useI18n()
  const [statistics, setStatistics] = useState<VerificationStatistics | null>(
    null
  )
  const [unverifiedUsers, setUnverifiedUsers] = useState<UnverifiedUser[]>([])
  const [statisticsReport, setStatisticsReport] =
    useState<StatisticsReport | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<
    'overview' | 'users' | 'analytics' | 'maintenance'
  >('overview')

  const apiBase =
    process.env.NODE_ENV === 'production' ? '/api' : 'http://localhost:8000'

  const loadInitialData = useCallback(async () => {
    setLoading(true)
    setError(null)

    try {
      await Promise.all([
        loadStatistics(),
        loadUnverifiedUsers(),
        loadStatisticsReport(),
      ])
    } catch (err) {
      setError(t('emailVerification.admin.alerts.loadFailed'))
      console.error('Error loading data:', err)
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- loadStatistics, loadUnverifiedUsers, loadStatisticsReport are stable functions defined in component
  }, [t])

  useEffect(() => {
    loadInitialData()
  }, [loadInitialData])

  const loadStatistics = async () => {
    const response = await fetch(
      `${apiBase}/monitoring/email-verification/statistics`,
      {
        credentials: 'include',
      }
    )

    if (!response.ok) {
      throw new Error(`Failed to load statistics: ${response.status}`)
    }

    const data = await response.json()
    setStatistics(data)
  }

  const loadUnverifiedUsers = async () => {
    const response = await fetch(
      `${apiBase}/monitoring/email-verification/unverified-users?limit=20`,
      {
        credentials: 'include',
      }
    )

    if (!response.ok) {
      throw new Error(`Failed to load unverified users: ${response.status}`)
    }

    const data = await response.json()
    setUnverifiedUsers(data.users || [])
  }

  const loadStatisticsReport = async () => {
    const response = await fetch(
      `${apiBase}/monitoring/email-verification/statistics-report`,
      {
        credentials: 'include',
      }
    )

    if (!response.ok) {
      throw new Error(`Failed to load statistics report: ${response.status}`)
    }

    const data = await response.json()
    setStatisticsReport(data.report)
  }

  const handleCleanupTokens = async () => {
    setLoading(true)
    setError(null)
    setSuccess(null)

    try {
      const response = await fetch(
        `${apiBase}/monitoring/email-verification/run-cleanup`,
        {
          method: 'POST',
          credentials: 'include',
        }
      )

      if (!response.ok) {
        throw new Error(`Cleanup failed: ${response.status}`)
      }

      const result = await response.json()
      setSuccess(
        t('emailVerification.admin.alerts.cleanupSuccess').replace(
          '{{count}}',
          String(result.tokens_cleaned || 0)
        )
      )

      // Refresh data
      await loadInitialData()
    } catch (err) {
      setError(t('emailVerification.admin.alerts.cleanupFailed'))
      console.error('Cleanup error:', err)
    } finally {
      setLoading(false)
    }
  }

  const handleSendReminders = async () => {
    setLoading(true)
    setError(null)
    setSuccess(null)

    try {
      const response = await fetch(
        `${apiBase}/monitoring/email-verification/send-reminders`,
        {
          method: 'POST',
          credentials: 'include',
        }
      )

      if (!response.ok) {
        throw new Error(`Send reminders failed: ${response.status}`)
      }

      const result = await response.json()
      setSuccess(
        t('emailVerification.admin.alerts.remindersSuccess').replace(
          '{{count}}',
          String(result.reminders_sent || 0)
        )
      )

      // Refresh data
      await loadInitialData()
    } catch (err) {
      setError(t('emailVerification.admin.alerts.remindersFailed'))
      console.error('Reminder error:', err)
    } finally {
      setLoading(false)
    }
  }

  const handleResendVerification = async (userId: string) => {
    setLoading(true)
    setError(null)
    setSuccess(null)

    try {
      const response = await fetch(
        `${apiBase}/monitoring/email-verification/resend-verification/${userId}`,
        {
          method: 'POST',
          credentials: 'include',
        }
      )

      if (!response.ok) {
        throw new Error(`Resend failed: ${response.status}`)
      }

      const result = await response.json()
      if (result.success) {
        setSuccess(
          t('emailVerification.admin.alerts.resendSuccess').replace(
            '{{email}}',
            result.user_email
          )
        )
      } else {
        setError(
          result.message || t('emailVerification.admin.alerts.resendFailed')
        )
      }

      // Refresh unverified users
      await loadUnverifiedUsers()
    } catch (err) {
      setError(t('emailVerification.admin.alerts.resendFailed'))
      console.error('Resend error:', err)
    } finally {
      setLoading(false)
    }
  }

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'Never'
    return new Date(dateString).toLocaleDateString()
  }

  const getVerificationRateColor = (rate: number) => {
    if (rate >= 90) return 'text-green-600'
    if (rate >= 75) return 'text-yellow-600'
    return 'text-red-600'
  }

  const renderOverviewTab = () => (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-4">
      {/* Key Metrics Cards */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center text-sm font-medium">
            <Users className="mr-2 h-4 w-4" />
            {t('emailVerification.admin.metrics.totalUsers')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {statistics?.total_users || 0}
          </div>
          <p className="text-muted-foreground mt-1 text-xs">
            {t('emailVerification.admin.metrics.registeredUsers')}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center text-sm font-medium">
            <CheckCircle className="mr-2 h-4 w-4 text-green-600" />
            {t('emailVerification.admin.metrics.verifiedUsers')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold text-green-600">
            {statistics?.verified_users || 0}
          </div>
          <p className="text-muted-foreground mt-1 text-xs">
            {t('emailVerification.admin.metrics.emailVerified')}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center text-sm font-medium">
            <XCircle className="mr-2 h-4 w-4 text-red-600" />
            {t('emailVerification.admin.metrics.unverifiedUsers')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold text-red-600">
            {statistics?.unverified_users || 0}
          </div>
          <p className="text-muted-foreground mt-1 text-xs">
            {t('emailVerification.admin.metrics.needVerification')}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center text-sm font-medium">
            <Activity className="mr-2 h-4 w-4" />
            {t('emailVerification.admin.metrics.verificationRate')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div
            className={`text-2xl font-bold ${getVerificationRateColor(statistics?.verification_rate_percent || 0)}`}
          >
            {statistics?.verification_rate_percent || 0}%
          </div>
          <p className="text-muted-foreground mt-1 text-xs">
            {t('emailVerification.admin.metrics.overallRate')}
          </p>
        </CardContent>
      </Card>

      {/* Additional Status Cards */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center text-sm font-medium">
            <Clock className="mr-2 h-4 w-4 text-yellow-600" />
            {t('emailVerification.admin.metrics.pendingVerification')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold text-yellow-600">
            {statistics?.pending_verification || 0}
          </div>
          <p className="text-muted-foreground mt-1 text-xs">
            {t('emailVerification.admin.metrics.awaitingClick')}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center text-sm font-medium">
            <AlertTriangle className="mr-2 h-4 w-4 text-orange-600" />
            {t('emailVerification.admin.metrics.expiredTokens')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold text-orange-600">
            {statistics?.expired_tokens || 0}
          </div>
          <p className="text-muted-foreground mt-1 text-xs">
            {t('emailVerification.admin.metrics.needCleanup')}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center text-sm font-medium">
            <Users className="mr-2 h-4 w-4 text-blue-600" />
            {t('emailVerification.admin.metrics.recentUnverified')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold text-blue-600">
            {statistics?.recent_unverified || 0}
          </div>
          <p className="text-muted-foreground mt-1 text-xs">
            {t('emailVerification.admin.metrics.lastSevenDays')}
          </p>
        </CardContent>
      </Card>

      {/* Alerts */}
      {statisticsReport?.alerts && statisticsReport.alerts.length > 0 && (
        <Card className="md:col-span-2 lg:col-span-4">
          <CardHeader>
            <CardTitle className="flex items-center text-lg">
              <AlertTriangle className="mr-2 h-5 w-5 text-yellow-600" />
              {t('emailVerification.admin.alerts.systemAlerts')}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {statisticsReport.alerts.map((alert, index) => (
              <Alert
                key={index}
                variant={alert.level === 'warning' ? 'destructive' : 'default'}
              >
                <AlertDescription>{alert.message}</AlertDescription>
              </Alert>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  )

  const renderUsersTab = () => (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center">
            <Users className="mr-2 h-5 w-5" />
            {t('emailVerification.admin.users.unverifiedCount').replace(
              '{{count}}',
              String(unverifiedUsers.length)
            )}
          </CardTitle>
          <CardDescription>
            {t('emailVerification.admin.users.manageUnverified')}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {unverifiedUsers.length === 0 ? (
            <div className="text-muted-foreground py-8 text-center">
              <CheckCircle className="mx-auto mb-4 h-12 w-12 text-green-600" />
              <p>{t('emailVerification.admin.users.allVerified')}</p>
            </div>
          ) : (
            <div className="space-y-4">
              {unverifiedUsers.map((user) => (
                <div
                  key={user.id}
                  className="flex items-center justify-between rounded-lg border p-4"
                >
                  <div className="flex-1">
                    <div className="flex items-center space-x-2">
                      <h3 className="font-medium">{user.name}</h3>
                      <Badge
                        variant={
                          user.has_verification_token ? 'default' : 'secondary'
                        }
                      >
                        {user.has_verification_token
                          ? t('emailVerification.admin.users.tokenActive')
                          : t('emailVerification.admin.users.noToken')}
                      </Badge>
                    </div>
                    <p className="text-muted-foreground text-sm">
                      {user.email}
                    </p>
                    <div className="text-muted-foreground mt-2 flex items-center space-x-4 text-xs">
                      <span>
                        {t('emailVerification.admin.users.registered').replace(
                          '{{date}}',
                          formatDate(user.created_at)
                        )}
                      </span>
                      <span>
                        {t('emailVerification.admin.users.lastEmail').replace(
                          '{{date}}',
                          formatDate(user.email_verification_sent_at)
                        )}
                      </span>
                      <span>
                        {t('emailVerification.admin.users.daysAgo').replace(
                          '{{days}}',
                          String(user.days_since_registration)
                        )}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Button
                      variant="outline"
                      onClick={() => handleResendVerification(user.id)}
                      disabled={loading}
                    >
                      <Mail className="mr-1 h-4 w-4" />
                      {t('emailVerification.admin.users.resend')}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )

  const renderAnalyticsTab = () => (
    <div className="space-y-6">
      {statisticsReport && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center">
              <BarChart3 className="mr-2 h-5 w-5" />
              {t('emailVerification.admin.analytics.trends')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
              <div className="text-center">
                <div className="text-2xl font-bold text-blue-600">
                  {statisticsReport.trends.weekly_verification_rate}%
                </div>
                <p className="text-muted-foreground text-sm">
                  {t('emailVerification.admin.analytics.weeklyRate')}
                </p>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-green-600">
                  {statisticsReport.trends.monthly_verification_rate}%
                </div>
                <p className="text-muted-foreground text-sm">
                  {t('emailVerification.admin.analytics.monthlyRate')}
                </p>
              </div>
              <div className="text-center">
                <Badge
                  variant={
                    statisticsReport.trends.rate_trend === 'improving'
                      ? 'default'
                      : 'destructive'
                  }
                  className="text-sm"
                >
                  {statisticsReport.trends.rate_trend === 'improving'
                    ? `↗️ ${t('emailVerification.admin.analytics.improving')}`
                    : `↘️ ${t('emailVerification.admin.analytics.declining')}`}
                </Badge>
                <p className="text-muted-foreground mt-1 text-sm">
                  {t('emailVerification.admin.analytics.trend')}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )

  const renderMaintenanceTab = () => (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center">
            <RefreshCw className="mr-2 h-5 w-5" />
            {t('emailVerification.admin.maintenance.operations')}
          </CardTitle>
          <CardDescription>
            {t('emailVerification.admin.maintenance.adminTasks')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between rounded-lg border p-4">
            <div>
              <h3 className="font-medium">
                {t('emailVerification.admin.maintenance.cleanupExpired')}
              </h3>
              <p className="text-muted-foreground text-sm">
                {t('emailVerification.admin.maintenance.cleanupDesc')}
              </p>
            </div>
            <Button
              onClick={handleCleanupTokens}
              disabled={loading}
              variant="outline"
            >
              <Trash2 className="mr-2 h-4 w-4" />
              {t('emailVerification.admin.maintenance.runCleanup')}
            </Button>
          </div>

          <div className="flex items-center justify-between rounded-lg border p-4">
            <div>
              <h3 className="font-medium">
                {t('emailVerification.admin.maintenance.sendReminders')}
              </h3>
              <p className="text-muted-foreground text-sm">
                {t('emailVerification.admin.maintenance.remindersDesc')}
              </p>
            </div>
            <Button
              onClick={handleSendReminders}
              disabled={loading}
              variant="outline"
            >
              <Send className="mr-2 h-4 w-4" />
              {t('emailVerification.admin.maintenance.sendRemindersBtn')}
            </Button>
          </div>

          <div className="flex items-center justify-between rounded-lg border p-4">
            <div>
              <h3 className="font-medium">
                {t('emailVerification.admin.maintenance.refreshData')}
              </h3>
              <p className="text-muted-foreground text-sm">
                {t('emailVerification.admin.maintenance.refreshDesc')}
              </p>
            </div>
            <Button
              onClick={loadInitialData}
              disabled={loading}
              variant="outline"
            >
              <RefreshCw className="mr-2 h-4 w-4" />
              {t('emailVerification.admin.maintenance.refresh')}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="mx-auto max-w-7xl">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900">
            {t('emailVerification.admin.title')}
          </h1>
          <p className="mt-2 text-gray-600">
            {t('emailVerification.admin.description')}
          </p>
        </div>

        {/* Status Messages */}
        {error && (
          <Alert variant="destructive" className="mb-6">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {success && (
          <Alert className="mb-6">
            <CheckCircle className="h-4 w-4" />
            <AlertDescription>{success}</AlertDescription>
          </Alert>
        )}

        {/* Tab Navigation */}
        <div className="mb-6 flex space-x-1 rounded-lg bg-gray-100 p-1">
          {[
            {
              key: 'overview',
              label: t('emailVerification.admin.tabs.overview'),
              icon: Activity,
            },
            {
              key: 'users',
              label: t('emailVerification.admin.tabs.users'),
              icon: Users,
            },
            {
              key: 'analytics',
              label: t('emailVerification.admin.tabs.analytics'),
              icon: BarChart3,
            },
            {
              key: 'maintenance',
              label: t('emailVerification.admin.tabs.maintenance'),
              icon: RefreshCw,
            },
          ].map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setActiveTab(key as any)}
              className={`flex items-center rounded-md px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === key
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
              }`}
            >
              <Icon className="mr-2 h-4 w-4" />
              {label}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        {loading && (
          <div className="flex items-center justify-center py-12">
            <RefreshCw className="mr-2 h-6 w-6 animate-spin" />
            <span>{t('emailVerification.admin.maintenance.loading')}</span>
          </div>
        )}

        {!loading && (
          <>
            {activeTab === 'overview' && renderOverviewTab()}
            {activeTab === 'users' && renderUsersTab()}
            {activeTab === 'analytics' && renderAnalyticsTab()}
            {activeTab === 'maintenance' && renderMaintenanceTab()}
          </>
        )}
      </div>
    </div>
  )
}
