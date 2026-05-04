'use client'

import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Button } from '@/components/shared/Button'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { api } from '@/lib/api'
import {
  ArrowPathIcon,
  BellIcon,
  CheckCircleIcon,
  ClockIcon,
  EnvelopeIcon,
  ExclamationTriangleIcon,
  GlobeAltIcon,
  InformationCircleIcon,
  UserPlusIcon,
} from '@heroicons/react/24/outline'
import { useEffect, useState } from 'react'

// Get notification types dynamically from translation system
const getNotificationTypes = (t: any) => [
  {
    key: 'project_created',
    name: t('settings.notifications.types.projectCreated'),
    description: t('settings.notifications.types.projectCreatedDesc'),
    icon: InformationCircleIcon,
    category: t('settings.notifications.categories.projects'),
  },
  {
    key: 'project_updated',
    name: t('settings.notifications.types.projectUpdated'),
    description: t('settings.notifications.types.projectUpdatedDesc'),
    icon: InformationCircleIcon,
    category: t('settings.notifications.categories.projects'),
  },
  {
    key: 'project_shared',
    name: t('settings.notifications.types.projectShared'),
    description: t('settings.notifications.types.projectSharedDesc'),
    icon: UserPlusIcon,
    category: t('settings.notifications.categories.projects'),
  },
  {
    key: 'evaluation_completed',
    name: t('settings.notifications.types.evaluationCompleted'),
    description: t('settings.notifications.types.evaluationCompletedDesc'),
    icon: CheckCircleIcon,
    category: t('settings.notifications.categories.evaluations'),
  },
  {
    key: 'evaluation_failed',
    name: t('settings.notifications.types.evaluationFailed'),
    description: t('settings.notifications.types.evaluationFailedDesc'),
    icon: ExclamationTriangleIcon,
    category: t('settings.notifications.categories.evaluations'),
  },
  {
    key: 'data_upload_completed',
    name: t('settings.notifications.types.dataUploadCompleted'),
    description: t('settings.notifications.types.dataUploadCompletedDesc'),
    icon: CheckCircleIcon,
    category: t('settings.notifications.categories.data'),
  },
  {
    key: 'llm_generation_completed',
    name: t('settings.notifications.types.llmGenerationCompleted'),
    description: t('settings.notifications.types.llmGenerationCompletedDesc'),
    icon: CheckCircleIcon,
    category: t('settings.notifications.categories.llm'),
  },
  {
    key: 'annotation_completed',
    name: t('settings.notifications.types.annotationCompleted'),
    description: t('settings.notifications.types.annotationCompletedDesc'),
    icon: CheckCircleIcon,
    category: t('settings.notifications.categories.annotation'),
  },
  {
    key: 'annotation_assigned',
    name: t('settings.notifications.types.annotationAssigned'),
    description: t('settings.notifications.types.annotationAssignedDesc'),
    icon: UserPlusIcon,
    category: t('settings.notifications.categories.annotation'),
  },
  {
    key: 'task_assigned',
    name: t('settings.notifications.types.taskAssigned', { defaultValue: 'Aufgabe zugewiesen' }),
    description: t('settings.notifications.types.taskAssignedDesc', {
      defaultValue: 'Sie wurden einer oder mehreren Annotationsaufgaben zugewiesen',
    }),
    icon: UserPlusIcon,
    category: t('settings.notifications.categories.annotation'),
  },
  {
    key: 'korrektur_assigned',
    name: t('settings.notifications.types.korrekturAssigned', {
      defaultValue: 'Korrektur zugewiesen',
    }),
    description: t('settings.notifications.types.korrekturAssignedDesc', {
      defaultValue: 'Sie wurden einer Korrekturaufgabe (Classic oder Falllösung) zugewiesen',
    }),
    icon: UserPlusIcon,
    category: t('settings.notifications.categories.annotation'),
  },
  {
    key: 'organization_invitation_sent',
    name: t('settings.notifications.types.orgInvitationSent'),
    description: t('settings.notifications.types.orgInvitationSentDesc'),
    icon: UserPlusIcon,
    category: t('settings.notifications.categories.organization'),
  },
  {
    key: 'organization_invitation_accepted',
    name: t('settings.notifications.types.orgInvitationAccepted'),
    description: t('settings.notifications.types.orgInvitationAcceptedDesc'),
    icon: UserPlusIcon,
    category: t('settings.notifications.categories.organization'),
  },
  {
    key: 'member_joined',
    name: t('settings.notifications.types.memberJoined'),
    description: t('settings.notifications.types.memberJoinedDesc'),
    icon: UserPlusIcon,
    category: t('settings.notifications.categories.organization'),
  },
  {
    key: 'system_alert',
    name: t('settings.notifications.types.systemAlert'),
    description: t('settings.notifications.types.systemAlertDesc'),
    icon: ExclamationTriangleIcon,
    category: t('settings.notifications.categories.system'),
  },
  {
    key: 'error_occurred',
    name: t('settings.notifications.types.errorOccurred'),
    description: t('settings.notifications.types.errorOccurredDesc'),
    icon: ExclamationTriangleIcon,
    category: t('settings.notifications.categories.system'),
  },
]

// Categories will be calculated dynamically within the component

// Timezone options with translation support
const getTimezoneOptions = (t: any) => [
  { value: 'UTC', label: t('settings.notifications.timezone.utc') },
  { value: 'UTC-12', label: t('settings.notifications.timezone.utcMinus12') },
  { value: 'UTC-11', label: t('settings.notifications.timezone.utcMinus11') },
  { value: 'UTC-10', label: t('settings.notifications.timezone.utcMinus10') },
  { value: 'UTC-9', label: t('settings.notifications.timezone.utcMinus9') },
  { value: 'UTC-8', label: t('settings.notifications.timezone.utcMinus8') },
  { value: 'UTC-7', label: t('settings.notifications.timezone.utcMinus7') },
  { value: 'UTC-6', label: t('settings.notifications.timezone.utcMinus6') },
  { value: 'UTC-5', label: t('settings.notifications.timezone.utcMinus5') },
  { value: 'UTC-4', label: t('settings.notifications.timezone.utcMinus4') },
  { value: 'UTC-3', label: t('settings.notifications.timezone.utcMinus3') },
  { value: 'UTC-2', label: t('settings.notifications.timezone.utcMinus2') },
  { value: 'UTC-1', label: t('settings.notifications.timezone.utcMinus1') },
  { value: 'UTC+1', label: t('settings.notifications.timezone.utcPlus1') },
  { value: 'UTC+2', label: t('settings.notifications.timezone.utcPlus2') },
  { value: 'UTC+3', label: t('settings.notifications.timezone.utcPlus3') },
  { value: 'UTC+4', label: t('settings.notifications.timezone.utcPlus4') },
  { value: 'UTC+5', label: t('settings.notifications.timezone.utcPlus5') },
  { value: 'UTC+6', label: t('settings.notifications.timezone.utcPlus6') },
  { value: 'UTC+7', label: t('settings.notifications.timezone.utcPlus7') },
  { value: 'UTC+8', label: t('settings.notifications.timezone.utcPlus8') },
  { value: 'UTC+9', label: t('settings.notifications.timezone.utcPlus9') },
  { value: 'UTC+10', label: t('settings.notifications.timezone.utcPlus10') },
  { value: 'UTC+11', label: t('settings.notifications.timezone.utcPlus11') },
  { value: 'UTC+12', label: t('settings.notifications.timezone.utcPlus12') },
]

interface NotificationPreferences {
  [key: string]: {
    enabled: boolean
    in_app: boolean
    email: boolean
  }
}

interface EmailStatus {
  available: boolean
  configured: boolean
  message: string
}

function NotificationSettingsContent() {
  const { user } = useAuth()
  const { t } = useI18n()
  // All hooks must be called before any early returns (rules-of-hooks)
  const [preferences, setPreferences] = useState<NotificationPreferences>({})
  const [emailStatus, setEmailStatus] = useState<EmailStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testingEmail, setTestingEmail] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [configError, setConfigError] = useState<string | null>(null)

  // Compute notification types, timezone options, and categories
  const { notificationTypes, timezoneOptions, categories } = (() => {
    if (!t) {
      return { notificationTypes: [], timezoneOptions: [], categories: [] }
    }
    try {
      const allNotificationTypes = getNotificationTypes(t)
      return {
        notificationTypes: allNotificationTypes,
        timezoneOptions: getTimezoneOptions(t),
        categories: Array.from(new Set(allNotificationTypes.map((type: any) => type.category))),
      }
    } catch (err) {
      console.error('Error loading notification configuration:', err)
      return { notificationTypes: [], timezoneOptions: [], categories: [] }
    }
  })()

  useEffect(() => {
    const initializeSettings = async () => {
      try {
        if (user) {
          await Promise.allSettled([loadPreferences(), loadEmailStatus()])
        }
      } catch (err) {
        console.error('Error initializing notification settings:', err)
        try {
          if (typeof t === 'function') {
            setError(t('settings.notifications.ui.initFailed'))
          } else {
            setError('Failed to initialize notification settings') // fallback when t() unavailable
          }
        } catch {
          setError('Failed to initialize notification settings') // fallback when t() throws
        }
      }
    }

    initializeSettings()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- loadPreferences and loadEmailStatus are defined inside component
  }, [user])

  // Add safety checks to prevent runtime errors (Fix for Issue #423)
  if (!t) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-center">
          <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-b-2 border-emerald-600"></div>
          <p>Loading translations...</p>
        </div>
      </div>
    )
  }

  // Show error state if configuration failed to load
  if (notificationTypes.length === 0 && categories.length === 0) {
    // Use try-catch for t() since this error state may be triggered by t() itself failing
    let loadingErrorText = 'Error loading notification settings'
    let reloadPageText = 'Reload Page'
    try {
      loadingErrorText = t('settings.notifications.ui.loadingError')
      reloadPageText = t('common.reloadPage')
    } catch {
      // Keep fallback strings if t() fails
    }
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-center">
          <p className="mb-4 text-red-600">
            {loadingErrorText}
          </p>
          <button
            onClick={() => window.location.reload()}
            className="rounded bg-emerald-600 px-4 py-2 text-white hover:bg-emerald-700"
          >
            {reloadPageText}
          </button>
        </div>
      </div>
    )
  }

  const loadPreferences = async () => {
    try {
      setLoading(true)
      const data = await api.getNotificationPreferences()

      // Convert legacy boolean preferences to new structure
      const convertedPreferences: NotificationPreferences = {}
      if (data) {
        Object.entries(data).forEach(([key, value]) => {
          if (typeof value === 'boolean') {
            // Legacy format - convert to new structure
            convertedPreferences[key] = {
              enabled: value,
              in_app: value,
              email: (value && emailStatus?.configured) || false,
            }
          } else if (typeof value === 'object' && value !== null) {
            // New format - use as is
            convertedPreferences[key] = value as {
              enabled: boolean
              in_app: boolean
              email: boolean
            }
          }
        })
      }

      setPreferences(convertedPreferences)
    } catch (err) {
      console.error('Failed to load notification preferences:', err)
      setError(t('settings.notifications.ui.loadFailed'))
    } finally {
      setLoading(false)
    }
  }

  const loadEmailStatus = async () => {
    try {
      const status = await api.notifications.getEmailStatus()
      setEmailStatus(status)
    } catch (err) {
      console.error('Failed to load email status:', err)
      // Don't show error for email status - it's optional
    }
  }

  const handlePreferenceChange = (
    notificationType: string,
    field: 'enabled' | 'in_app' | 'email',
    value: boolean
  ) => {
    setPreferences((prev) => ({
      ...prev,
      [notificationType]: {
        ...prev[notificationType],
        enabled: prev[notificationType]?.enabled || false,
        in_app: prev[notificationType]?.in_app || false,
        email: prev[notificationType]?.email || false,
        [field]: value,
        // If disabling main toggle, disable both delivery methods
        ...(field === 'enabled' && !value
          ? { in_app: false, email: false }
          : {}),
        // If enabling delivery method, ensure main toggle is enabled
        ...(field !== 'enabled' && value ? { enabled: true } : {}),
      },
    }))
  }

  const handleBulkToggle = (category: string, enabled: boolean) => {
    const categoryTypes = notificationTypes.filter(
      (type) => type.category === category
    )
    const updates = Object.fromEntries(
      categoryTypes.map((type) => [
        type.key,
        {
          enabled,
          in_app: enabled,
          email: (enabled && emailStatus?.configured) || false,
        },
      ])
    )
    setPreferences((prev) => ({ ...prev, ...updates }))
  }

  const handleSavePreferences = async () => {
    try {
      setSaving(true)
      setError(null)
      setSuccess(null)

      // Convert new format back to legacy format for API compatibility
      const legacyPreferences = Object.fromEntries(
        Object.entries(preferences).map(([key, value]) => [key, value.enabled])
      )

      await api.updateNotificationPreferences(legacyPreferences)
      setSuccess(t('settings.notifications.ui.preferencesSaved'))

      // Clear success message after 3 seconds
      setTimeout(() => setSuccess(null), 3000)
    } catch (err) {
      console.error('Failed to save notification preferences:', err)
      setError(t('settings.notifications.ui.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const handleTestEmail = async () => {
    try {
      setTestingEmail(true)
      setError(null)
      setSuccess(null)

      const result = await api.notifications.sendTestEmail()
      setSuccess(result.message || t('settings.notifications.ui.testEmailSent'))

      // Clear success message after 5 seconds
      setTimeout(() => setSuccess(null), 5000)
    } catch (err: any) {
      console.error('Failed to send test email:', err)
      setError(err.response?.data?.detail || t('settings.notifications.ui.testEmailFailed'))
    } finally {
      setTestingEmail(false)
    }
  }

  const getEnabledCount = (category: string): number => {
    const categoryTypes = notificationTypes.filter(
      (type) => type.category === category
    )
    return categoryTypes.filter((type) => preferences[type.key]?.enabled).length
  }

  if (!user) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <div className="text-center">
          <h2 className="mb-4 text-2xl font-bold text-zinc-900 dark:text-white">
            {t('settings.notifications.ui.authRequired')}
          </h2>
          <p className="text-zinc-600 dark:text-zinc-400">
            {t('settings.notifications.ui.authRequiredDesc')}
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
            { label: t('settings.notifications.breadcrumb.settings'), href: '/settings' },
            { label: t('settings.notifications.breadcrumb.notifications'), href: '/settings/notifications' },
          ]}
        />
      </div>

      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
          {t('settings.notifications.title')}
        </h1>
        <p className="mt-2 text-lg text-zinc-600 dark:text-zinc-400">
          {t('settings.notifications.subtitle')}
        </p>
      </div>

      {/* Error/Success Messages */}
      {error && (
        <div className="mb-6 rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-900/20">
          <div className="flex">
            <ExclamationTriangleIcon className="mr-2 mt-0.5 h-5 w-5 flex-shrink-0 text-red-400" />
            <div className="text-red-800 dark:text-red-200">{error}</div>
          </div>
        </div>
      )}

      {success && (
        <div className="mb-6 rounded-lg border border-green-200 bg-green-50 p-4 dark:border-green-800 dark:bg-green-900/20">
          <div className="flex">
            <CheckCircleIcon className="mr-2 mt-0.5 h-5 w-5 flex-shrink-0 text-green-400" />
            <div className="text-green-800 dark:text-green-200">{success}</div>
          </div>
        </div>
      )}

      {/* Email Service Status */}
      {emailStatus && (
        <div
          className={`mb-6 rounded-lg border p-4 ${
            emailStatus.configured
              ? 'border-green-200 bg-green-50 dark:border-green-800 dark:bg-green-900/20'
              : 'border-yellow-200 bg-yellow-50 dark:border-yellow-800 dark:bg-yellow-900/20'
          }`}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <EnvelopeIcon
                className={`mr-2 h-5 w-5 ${
                  emailStatus.configured ? 'text-green-500' : 'text-yellow-500'
                }`}
              />
              <div>
                <div
                  className={`font-medium ${
                    emailStatus.configured
                      ? 'text-green-800 dark:text-green-200'
                      : 'text-yellow-800 dark:text-yellow-200'
                  }`}
                >
                  {emailStatus.configured
                    ? t('settings.notifications.email.available')
                    : t('settings.notifications.email.notConfigured')}
                </div>
                <div
                  className={`text-sm ${
                    emailStatus.configured
                      ? 'text-green-600 dark:text-green-300'
                      : 'text-yellow-600 dark:text-yellow-300'
                  }`}
                >
                  {emailStatus.configured
                    ? t('settings.notifications.email.configuredDesc')
                    : t('settings.notifications.email.notConfiguredDesc')}
                </div>
              </div>
            </div>

            {emailStatus.configured && (
              <Button
                onClick={handleTestEmail}
                variant="outline"
                className="text-sm"
                disabled={testingEmail}
                data-testid="settings-test-email-button"
              >
                {testingEmail ? (
                  <>
                    <ArrowPathIcon className="mr-1 h-4 w-4 animate-spin" />
                    {t('settings.notifications.ui.sending')}
                  </>
                ) : (
                  t('settings.notifications.ui.sendTestEmail')
                )}
              </Button>
            )}
          </div>
        </div>
      )}

      {loading ? (
        <div className="rounded-lg bg-white p-8 shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-900 dark:ring-white/10">
          <div className="flex items-center justify-center">
            <ArrowPathIcon className="h-8 w-8 animate-spin text-zinc-400" />
            <span className="ml-2 text-zinc-600 dark:text-zinc-400">
              {t('settings.notifications.ui.loading')}
            </span>
          </div>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Notification Preferences Table */}
          <div className="overflow-hidden rounded-lg bg-white shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-900 dark:ring-white/10">
            <div className="border-b border-zinc-200 bg-zinc-50 px-6 py-4 dark:border-zinc-700 dark:bg-zinc-800/50">
              <h3 className="text-lg font-medium text-zinc-900 dark:text-white">
                {t('settings.notifications.title')}
              </h3>
              <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                {t('settings.notifications.subtitle')}
              </p>
            </div>

            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-zinc-200 dark:divide-zinc-700">
                <thead className="bg-zinc-50 dark:bg-zinc-800/30">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                      {t('settings.notifications.ui.notificationType')}
                    </th>
                    <th className="px-6 py-3 text-center text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                      {t('settings.notifications.ui.enabled')}
                    </th>
                    <th className="px-6 py-3 text-center text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                      <div className="flex items-center justify-center space-x-1">
                        <BellIcon className="h-3 w-3" />
                        <span>{t('settings.notifications.ui.inApp')}</span>
                      </div>
                    </th>
                    <th className="px-6 py-3 text-center text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                      <div className="flex items-center justify-center space-x-1">
                        <EnvelopeIcon className="h-3 w-3" />
                        <span>{t('settings.notifications.ui.email')}</span>
                      </div>
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-200 bg-white dark:divide-zinc-700 dark:bg-zinc-900">
                  {notificationTypes.map((notificationType, index) => {
                    const IconComponent = notificationType.icon
                    const pref = preferences[notificationType.key] || {
                      enabled: true,
                      in_app: true,
                      email: false,
                    }

                    return (
                      <tr
                        key={`notification-${notificationType.key}-${index}`}
                        className="hover:bg-zinc-50 dark:hover:bg-zinc-800/50"
                      >
                        <td className="whitespace-nowrap px-6 py-4">
                          <div className="flex items-center space-x-3">
                            <div className="flex-shrink-0">
                              <IconComponent className="h-5 w-5 text-zinc-400" />
                            </div>
                            <div>
                              <div className="flex items-center space-x-2">
                                <div className="text-sm font-medium text-zinc-900 dark:text-white">
                                  {notificationType.name}
                                </div>
                                <span className="inline-flex items-center rounded bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-800 dark:bg-zinc-700 dark:text-zinc-200">
                                  {notificationType.category}
                                </span>
                              </div>
                              <div className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                                {notificationType.description}
                              </div>
                            </div>
                          </div>
                        </td>
                        <td className="whitespace-nowrap px-6 py-4 text-center">
                          <button
                            type="button"
                            className={`relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-emerald-600 focus:ring-offset-2 ${
                              pref.enabled
                                ? 'bg-emerald-600'
                                : 'bg-zinc-200 dark:bg-zinc-700'
                            }`}
                            onClick={() =>
                              handlePreferenceChange(
                                notificationType.key,
                                'enabled',
                                !pref.enabled
                              )
                            }
                            data-testid={`settings-notification-toggle-${notificationType.key}`}
                          >
                            <span
                              className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                                pref.enabled ? 'translate-x-4' : 'translate-x-0'
                              }`}
                            />
                          </button>
                        </td>
                        <td className="whitespace-nowrap px-6 py-4 text-center">
                          <button
                            type="button"
                            className={`relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-emerald-600 focus:ring-offset-2 ${
                              pref.in_app
                                ? 'bg-emerald-600'
                                : 'bg-zinc-200 dark:bg-zinc-700'
                            } ${!pref.enabled ? 'cursor-not-allowed opacity-50' : ''}`}
                            disabled={!pref.enabled}
                            onClick={() =>
                              handlePreferenceChange(
                                notificationType.key,
                                'in_app',
                                !pref.in_app
                              )
                            }
                            data-testid={`settings-notification-inapp-${notificationType.key}`}
                          >
                            <span
                              className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                                pref.in_app ? 'translate-x-4' : 'translate-x-0'
                              }`}
                            />
                          </button>
                        </td>
                        <td className="whitespace-nowrap px-6 py-4 text-center">
                          <button
                            type="button"
                            className={`relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-emerald-600 focus:ring-offset-2 ${
                              pref.email && emailStatus?.configured
                                ? 'bg-emerald-600'
                                : 'bg-zinc-200 dark:bg-zinc-700'
                            } ${!pref.enabled || !emailStatus?.configured ? 'cursor-not-allowed opacity-50' : ''}`}
                            disabled={!pref.enabled || !emailStatus?.configured}
                            onClick={() =>
                              handlePreferenceChange(
                                notificationType.key,
                                'email',
                                !pref.email
                              )
                            }
                            data-testid={`settings-notification-email-${notificationType.key}`}
                          >
                            <span
                              className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                                pref.email && emailStatus?.configured
                                  ? 'translate-x-4'
                                  : 'translate-x-0'
                              }`}
                            />
                          </button>
                          {!emailStatus?.configured && (
                            <div className="mt-1 text-xs text-zinc-400">
                              {t('settings.notifications.email.notConfigured')}
                            </div>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            {/* Bulk Actions */}
            <div className="border-t border-zinc-200 bg-zinc-50 px-6 py-3 dark:border-zinc-700 dark:bg-zinc-800/50">
              <div className="flex items-center justify-between">
                <div className="text-sm text-zinc-600 dark:text-zinc-400">
                  {t('settings.notifications.ui.enabledCount', {
                    enabled: Object.values(preferences).filter((p) => p?.enabled).length,
                    total: notificationTypes.length,
                  })}
                </div>
                <div className="flex space-x-2">
                  <Button
                    onClick={() => {
                      const updates = Object.fromEntries(
                        notificationTypes.map((type) => [
                          type.key,
                          { enabled: false, in_app: false, email: false },
                        ])
                      )
                      setPreferences(updates)
                    }}
                    variant="outline"
                    className="text-xs"
                    data-testid="settings-disable-all-notifications-button"
                  >
                    {t('settings.notifications.ui.disableAll')}
                  </Button>
                  <Button
                    onClick={() => {
                      const updates = Object.fromEntries(
                        notificationTypes.map((type) => [
                          type.key,
                          {
                            enabled: true,
                            in_app: true,
                            email: emailStatus?.configured || false,
                          },
                        ])
                      )
                      setPreferences(updates)
                    }}
                    variant="outline"
                    className="text-xs"
                    data-testid="settings-enable-all-notifications-button"
                  >
                    {t('settings.notifications.ui.enableAll')}
                  </Button>
                </div>
              </div>
            </div>
          </div>

          {/* Save Button */}
          <div className="flex justify-end pt-6">
            <Button
              onClick={handleSavePreferences}
              disabled={saving}
              className="px-6"
              data-testid="settings-save-notifications-button"
            >
              {saving ? (
                <>
                  <ArrowPathIcon className="mr-2 h-4 w-4 animate-spin" />
                  {t('settings.notifications.ui.saving')}
                </>
              ) : (
                t('settings.notifications.ui.savePreferences')
              )}
            </Button>
          </div>

          {/* Help Section */}
          <div className="mt-8 rounded-lg bg-zinc-50 p-6 dark:bg-zinc-800/50">
            <h3 className="mb-4 text-lg font-medium text-zinc-900 dark:text-white">
              {t('settings.notifications.help.title')}
            </h3>
            <div className="space-y-3 text-sm text-zinc-600 dark:text-zinc-400">
              <div className="flex items-start space-x-2">
                <BellIcon className="mt-0.5 h-4 w-4 flex-shrink-0 text-zinc-400" />
                <div>
                  <strong>{t('settings.notifications.help.inAppTitle')}</strong>{' '}
                  {t('settings.notifications.help.inAppDesc')}
                </div>
              </div>

              {emailStatus?.configured && (
                <div className="flex items-start space-x-2">
                  <EnvelopeIcon className="mt-0.5 h-4 w-4 flex-shrink-0 text-zinc-400" />
                  <div>
                    <strong>{t('settings.notifications.help.emailTitle')}</strong>{' '}
                    {t('settings.notifications.help.emailDescBefore')}{' '}
                    <strong>{user?.email}</strong>.{' '}
                    {t('settings.notifications.help.emailDescAfter')}
                  </div>
                </div>
              )}

              <div className="flex items-start space-x-2">
                <ClockIcon className="mt-0.5 h-4 w-4 flex-shrink-0 text-zinc-400" />
                <div>
                  {t('settings.notifications.help.roleBasedDesc')}
                </div>
              </div>

              <div className="flex items-start space-x-2">
                <GlobeAltIcon className="mt-0.5 h-4 w-4 flex-shrink-0 text-zinc-400" />
                <div>
                  {t('settings.notifications.help.preferencesDesc')}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default function NotificationSettingsPage() {
  return (
    <ResponsiveContainer size="xl" className="pb-10 pt-8">
      <NotificationSettingsContent />
    </ResponsiveContainer>
  )
}
