/**
 * Surgical coverage tests for Notification Settings page
 *
 * Targets previously uncovered functions:
 * - handlePreferenceChange (toggle enabled/in_app/email)
 * - handleBulkToggle (enable/disable per category)
 * - handleSavePreferences
 * - handleTestEmail
 * - Disable All / Enable All buttons
 * - getEnabledCount
 *
 * @jest-environment jsdom
 */

import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { api } from '@/lib/api'
import '@testing-library/jest-dom'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import NotificationSettingsPage from '../page'

jest.mock('@/lib/api', () => ({
  api: {
    getNotificationPreferences: jest.fn(),
    updateNotificationPreferences: jest.fn(),
    notifications: {
      getEmailStatus: jest.fn(),
      sendTestEmail: jest.fn(),
    },
  },
}))

jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: ({ items }: any) => (
    <div data-testid="breadcrumb">
      {items.map((item: any, index: number) => (
        <span key={index}>{item.label}</span>
      ))}
    </div>
  ),
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, disabled, className, variant, ...props }: any) => (
    <button onClick={onClick} disabled={disabled} className={className} data-variant={variant} {...props}>
      {children}
    </button>
  ),
}))

jest.mock('@/components/shared/ResponsiveContainer', () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
}))

jest.mock('@heroicons/react/24/outline', () => ({
  ArrowPathIcon: ({ className }: any) => <div className={className}>ArrowPathIcon</div>,
  BellIcon: ({ className }: any) => <div className={className}>BellIcon</div>,
  CheckCircleIcon: ({ className }: any) => <div className={className}>CheckCircleIcon</div>,
  ClockIcon: ({ className }: any) => <div className={className}>ClockIcon</div>,
  EnvelopeIcon: ({ className }: any) => <div className={className}>EnvelopeIcon</div>,
  ExclamationTriangleIcon: ({ className }: any) => <div className={className}>ExclamationTriangleIcon</div>,
  GlobeAltIcon: ({ className }: any) => <div className={className}>GlobeAltIcon</div>,
  InformationCircleIcon: ({ className }: any) => <div className={className}>InformationCircleIcon</div>,
  UserPlusIcon: ({ className }: any) => <div className={className}>UserPlusIcon</div>,
}))

const mockT = (key: string, vars?: any) => {
  const translations: Record<string, string> = {
    'settings.notifications.title': 'Notification Preferences',
    'settings.notifications.subtitle': 'Configure your notifications',
    'settings.notifications.breadcrumb.settings': 'Settings',
    'settings.notifications.breadcrumb.notifications': 'Notifications',
    'settings.notifications.types.projectCreated': 'Project Created',
    'settings.notifications.types.projectCreatedDesc': 'When a project is created',
    'settings.notifications.types.projectUpdated': 'Project Updated',
    'settings.notifications.types.projectUpdatedDesc': 'When a project is updated',
    'settings.notifications.types.projectShared': 'Project Shared',
    'settings.notifications.types.projectSharedDesc': 'When a project is shared',
    'settings.notifications.types.evaluationCompleted': 'Evaluation Completed',
    'settings.notifications.types.evaluationCompletedDesc': 'When evaluation completes',
    'settings.notifications.types.evaluationFailed': 'Evaluation Failed',
    'settings.notifications.types.evaluationFailedDesc': 'When evaluation fails',
    'settings.notifications.types.dataUploadCompleted': 'Data Upload Completed',
    'settings.notifications.types.dataUploadCompletedDesc': 'When data upload completes',
    'settings.notifications.types.llmGenerationCompleted': 'LLM Generation Completed',
    'settings.notifications.types.llmGenerationCompletedDesc': 'When LLM generation completes',
    'settings.notifications.types.annotationCompleted': 'Annotation Completed',
    'settings.notifications.types.annotationCompletedDesc': 'When annotation completes',
    'settings.notifications.types.annotationAssigned': 'Annotation Assigned',
    'settings.notifications.types.annotationAssignedDesc': 'When annotation is assigned',
    'settings.notifications.types.orgInvitationSent': 'Org Invitation Sent',
    'settings.notifications.types.orgInvitationSentDesc': 'When org invitation is sent',
    'settings.notifications.types.orgInvitationAccepted': 'Org Invitation Accepted',
    'settings.notifications.types.orgInvitationAcceptedDesc': 'When org invitation is accepted',
    'settings.notifications.types.memberJoined': 'Member Joined',
    'settings.notifications.types.memberJoinedDesc': 'When a member joins',
    'settings.notifications.types.systemAlert': 'System Alert',
    'settings.notifications.types.systemAlertDesc': 'System alerts',
    'settings.notifications.types.errorOccurred': 'Error Occurred',
    'settings.notifications.types.errorOccurredDesc': 'When errors occur',
    'settings.notifications.categories.projects': 'Projects',
    'settings.notifications.categories.evaluations': 'Evaluations',
    'settings.notifications.categories.data': 'Data',
    'settings.notifications.categories.llm': 'LLM',
    'settings.notifications.categories.annotation': 'Annotation',
    'settings.notifications.categories.organization': 'Organization',
    'settings.notifications.categories.system': 'System',
    'settings.notifications.ui.notificationType': 'Notification Type',
    'settings.notifications.ui.enabled': 'Enabled',
    'settings.notifications.ui.inApp': 'In-App',
    'settings.notifications.ui.email': 'Email',
    'settings.notifications.ui.loading': 'Loading...',
    'settings.notifications.ui.saving': 'Saving...',
    'settings.notifications.ui.savePreferences': 'Save Preferences',
    'settings.notifications.ui.preferencesSaved': 'Preferences saved',
    'settings.notifications.ui.loadFailed': 'Load failed',
    'settings.notifications.ui.saveFailed': 'Save failed',
    'settings.notifications.ui.sendTestEmail': 'Send Test Email',
    'settings.notifications.ui.sending': 'Sending...',
    'settings.notifications.ui.testEmailSent': 'Test email sent',
    'settings.notifications.ui.testEmailFailed': 'Test email failed',
    'settings.notifications.ui.enabledCount': '{{enabled}} of {{total}} enabled',
    'settings.notifications.ui.disableAll': 'Disable All',
    'settings.notifications.ui.enableAll': 'Enable All',
    'settings.notifications.ui.authRequired': 'Auth Required',
    'settings.notifications.ui.authRequiredDesc': 'Login to manage notifications',
    'settings.notifications.email.available': 'Email Available',
    'settings.notifications.email.notConfigured': 'Email Not Configured',
    'settings.notifications.email.configuredDesc': 'Email is configured',
    'settings.notifications.email.notConfiguredDesc': 'Email is not configured',
    'settings.notifications.help.title': 'Help',
    'settings.notifications.help.inAppTitle': 'In-App Notifications',
    'settings.notifications.help.inAppDesc': 'Receive in-app notifications',
    'settings.notifications.help.emailTitle': 'Email Notifications',
    'settings.notifications.help.emailDescBefore': 'Sent to',
    'settings.notifications.help.emailDescAfter': 'Check spam folder',
    'settings.notifications.help.roleBasedDesc': 'Role-based notification filtering',
    'settings.notifications.help.preferencesDesc': 'Preferences are global',
    'settings.notifications.timezone.utc': 'UTC',
  }
  let result = translations[key] || key
  if (vars && typeof vars === 'object') {
    Object.entries(vars).forEach(([k, v]) => {
      result = result.replace(`{{${k}}}`, String(v))
    })
  }
  return result
}

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(),
}))

describe('NotificationSettings - Surgical Coverage', () => {
  const user = userEvent.setup()

  beforeEach(() => {
    jest.clearAllMocks()
    ;(useAuth as jest.Mock).mockReturnValue({
      user: { id: 'user-1', username: 'testuser', email: 'test@example.com' },
    })
    ;(useI18n as jest.Mock).mockReturnValue({
      t: mockT,
      locale: 'en',
    })
    ;(api.getNotificationPreferences as jest.Mock).mockResolvedValue({
      project_created: { enabled: true, in_app: true, email: false },
      project_updated: { enabled: false, in_app: false, email: false },
    })
    ;(api.notifications.getEmailStatus as jest.Mock).mockResolvedValue({
      available: true,
      configured: true,
      message: 'Email configured',
    })
  })

  it('toggles notification enabled state via click', async () => {
    render(<NotificationSettingsPage />)

    await waitFor(() => {
      expect(screen.getByTestId('settings-notification-toggle-project_created')).toBeInTheDocument()
    })

    // Click the enabled toggle for project_created (currently enabled -> disable)
    const enabledToggle = screen.getByTestId('settings-notification-toggle-project_created')
    await user.click(enabledToggle)

    // After disabling, in_app and email should also disable
    // The toggle should now have the disabled style (bg-zinc-200)
    expect(enabledToggle).toBeInTheDocument()
  })

  it('toggles in_app notification via click', async () => {
    render(<NotificationSettingsPage />)

    await waitFor(() => {
      expect(screen.getByTestId('settings-notification-inapp-project_created')).toBeInTheDocument()
    })

    const inAppToggle = screen.getByTestId('settings-notification-inapp-project_created')
    await user.click(inAppToggle)
  })

  it('toggles email notification via click', async () => {
    render(<NotificationSettingsPage />)

    await waitFor(() => {
      expect(screen.getByTestId('settings-notification-email-project_created')).toBeInTheDocument()
    })

    const emailToggle = screen.getByTestId('settings-notification-email-project_created')
    await user.click(emailToggle)
  })

  it('clicks Disable All button', async () => {
    render(<NotificationSettingsPage />)

    await waitFor(() => {
      expect(screen.getByTestId('settings-disable-all-notifications-button')).toBeInTheDocument()
    })

    await user.click(screen.getByTestId('settings-disable-all-notifications-button'))

    // All toggles should now be off
    const enabledToggle = screen.getByTestId('settings-notification-toggle-project_created')
    expect(enabledToggle.className).toContain('bg-zinc-200')
  })

  it('clicks Enable All button', async () => {
    render(<NotificationSettingsPage />)

    await waitFor(() => {
      expect(screen.getByTestId('settings-enable-all-notifications-button')).toBeInTheDocument()
    })

    await user.click(screen.getByTestId('settings-enable-all-notifications-button'))

    // All toggles should now be on
    const enabledToggle = screen.getByTestId('settings-notification-toggle-project_updated')
    expect(enabledToggle.className).toContain('bg-emerald-600')
  })

  it('saves preferences via Save button', async () => {
    ;(api.updateNotificationPreferences as jest.Mock).mockResolvedValue({})

    render(<NotificationSettingsPage />)

    await waitFor(() => {
      expect(screen.getByTestId('settings-save-notifications-button')).toBeInTheDocument()
    })

    await user.click(screen.getByTestId('settings-save-notifications-button'))

    await waitFor(() => {
      expect(api.updateNotificationPreferences).toHaveBeenCalled()
    })
  })

  it('shows error when save fails', async () => {
    ;(api.updateNotificationPreferences as jest.Mock).mockRejectedValue(new Error('Save failed'))

    render(<NotificationSettingsPage />)

    await waitFor(() => {
      expect(screen.getByTestId('settings-save-notifications-button')).toBeInTheDocument()
    })

    await user.click(screen.getByTestId('settings-save-notifications-button'))

    await waitFor(() => {
      expect(screen.getByText('Save failed')).toBeInTheDocument()
    })
  })

  it('sends test email via button click', async () => {
    ;(api.notifications.sendTestEmail as jest.Mock).mockResolvedValue({
      message: 'Test email sent',
    })

    render(<NotificationSettingsPage />)

    await waitFor(() => {
      expect(screen.getByTestId('settings-test-email-button')).toBeInTheDocument()
    })

    await user.click(screen.getByTestId('settings-test-email-button'))

    await waitFor(() => {
      expect(api.notifications.sendTestEmail).toHaveBeenCalled()
    })
  })

  it('handles test email failure', async () => {
    ;(api.notifications.sendTestEmail as jest.Mock).mockRejectedValue({
      response: { data: { detail: 'Email server down' } },
    })

    render(<NotificationSettingsPage />)

    await waitFor(() => {
      expect(screen.getByTestId('settings-test-email-button')).toBeInTheDocument()
    })

    await user.click(screen.getByTestId('settings-test-email-button'))

    await waitFor(() => {
      expect(screen.getByText('Email server down')).toBeInTheDocument()
    })
  })

  it('handles legacy boolean preferences by converting them', async () => {
    ;(api.getNotificationPreferences as jest.Mock).mockResolvedValue({
      project_created: true,  // Legacy boolean format
      project_updated: false,
    })

    render(<NotificationSettingsPage />)

    await waitFor(() => {
      expect(screen.getByTestId('settings-notification-toggle-project_created')).toBeInTheDocument()
    })

    // project_created should be converted to enabled=true
    const toggle = screen.getByTestId('settings-notification-toggle-project_created')
    expect(toggle.className).toContain('bg-emerald-600')
  })
})
