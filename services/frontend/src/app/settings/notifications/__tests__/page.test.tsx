/**
 * Unit tests for Notification Settings page
 * @jest-environment jsdom
 */

import { useAuth } from '@/contexts/AuthContext'
import { useFeatureFlags } from '@/contexts/FeatureFlagContext'
import { useI18n } from '@/contexts/I18nContext'
import { api } from '@/lib/api'
import '@testing-library/jest-dom'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import NotificationSettingsPage from '../page'

// Note: FeatureFlagContext is already globally mocked in jest.setup.js
// We just need to mock the specific contexts we need to override

// Mock API
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

// Mock shared components
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
  Button: ({
    children,
    onClick,
    disabled,
    className,
    variant,
    ...props
  }: any) => (
    <button
      onClick={onClick}
      disabled={disabled}
      className={className}
      data-variant={variant}
      {...props}
    >
      {children}
    </button>
  ),
}))

jest.mock('@/components/shared/ResponsiveContainer', () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
}))

// Mock icons
jest.mock('@heroicons/react/24/outline', () => ({
  ArrowPathIcon: ({ className }: any) => (
    <div className={className}>ArrowPathIcon</div>
  ),
  BellIcon: ({ className }: any) => <div className={className}>BellIcon</div>,
  CheckCircleIcon: ({ className }: any) => (
    <div className={className}>CheckCircleIcon</div>
  ),
  ClockIcon: ({ className }: any) => <div className={className}>ClockIcon</div>,
  EnvelopeIcon: ({ className }: any) => (
    <div className={className}>EnvelopeIcon</div>
  ),
  ExclamationTriangleIcon: ({ className }: any) => (
    <div className={className}>ExclamationTriangleIcon</div>
  ),
  GlobeAltIcon: ({ className }: any) => (
    <div className={className}>GlobeAltIcon</div>
  ),
  InformationCircleIcon: ({ className }: any) => (
    <div className={className}>InformationCircleIcon</div>
  ),
  UserPlusIcon: ({ className }: any) => (
    <div className={className}>UserPlusIcon</div>
  ),
}))

const mockUser = {
  id: '1',
  username: 'testuser',
  email: 'test@example.com',
  name: 'Test User',
  is_superadmin: false,
  is_active: true,
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T00:00:00Z',
}

const mockTranslations = {
  'settings.notifications.title': 'Notification Settings',
  'settings.notifications.subtitle': 'Manage your notification preferences',
  'settings.notifications.types.projectCreated': 'Project Created',
  'settings.notifications.types.projectCreatedDesc':
    'Receive notifications when new projects are created',
  'settings.notifications.types.projectUpdated': 'Project Updated',
  'settings.notifications.types.projectUpdatedDesc':
    'Receive notifications when projects are updated',
  'settings.notifications.types.projectShared': 'Project Shared',
  'settings.notifications.types.projectSharedDesc':
    'Receive notifications when projects are shared',
  'settings.notifications.types.evaluationCompleted': 'Evaluation Completed',
  'settings.notifications.types.evaluationCompletedDesc':
    'Receive notifications when evaluations complete',
  'settings.notifications.types.evaluationFailed': 'Evaluation Failed',
  'settings.notifications.types.evaluationFailedDesc':
    'Receive notifications when evaluations fail',
  'settings.notifications.types.dataUploadCompleted': 'Data Upload Completed',
  'settings.notifications.types.dataUploadCompletedDesc':
    'Receive notifications when data uploads complete',
  'settings.notifications.types.llmGenerationCompleted':
    'LLM Generation Completed',
  'settings.notifications.types.llmGenerationCompletedDesc':
    'Receive notifications when LLM generations complete',
  'settings.notifications.types.annotationCompleted': 'Annotation Completed',
  'settings.notifications.types.annotationCompletedDesc':
    'Receive notifications when annotations are completed',
  'settings.notifications.types.annotationAssigned': 'Annotation Assigned',
  'settings.notifications.types.annotationAssignedDesc':
    'Receive notifications when annotations are assigned',
  'settings.notifications.types.orgInvitationSent':
    'Organization Invitation Sent',
  'settings.notifications.types.orgInvitationSentDesc':
    'Receive notifications when invitations are sent',
  'settings.notifications.types.orgInvitationAccepted':
    'Organization Invitation Accepted',
  'settings.notifications.types.orgInvitationAcceptedDesc':
    'Receive notifications when invitations are accepted',
  'settings.notifications.types.memberJoined': 'Member Joined',
  'settings.notifications.types.memberJoinedDesc':
    'Receive notifications when members join',
  'settings.notifications.types.systemAlert': 'System Alert',
  'settings.notifications.types.systemAlertDesc': 'Receive system alerts',
  'settings.notifications.types.errorOccurred': 'Error Occurred',
  'settings.notifications.types.errorOccurredDesc':
    'Receive notifications when errors occur',
  'settings.notifications.categories.projects': 'Projects',
  'settings.notifications.categories.evaluations': 'Evaluations',
  'settings.notifications.categories.data': 'Data',
  'settings.notifications.categories.llm': 'LLM',
  'settings.notifications.categories.annotation': 'Annotation',
  'settings.notifications.categories.organization': 'Organization',
  'settings.notifications.categories.system': 'System',
  'settings.notifications.email.available': 'Email notifications available',
  'settings.notifications.email.configured': 'Email service is configured',
  'settings.notifications.email.configuredDesc':
    'You can enable email notifications',
  'settings.notifications.email.notConfigured': 'Email not configured',
  'settings.notifications.email.notConfiguredDesc':
    'Email service is not configured',
  'settings.notifications.ui.loading': 'Loading...',
  'settings.notifications.ui.saving': 'Saving...',
  'settings.notifications.ui.sending': 'Sending...',
  'settings.notifications.ui.notificationType': 'Notification Type',
  'settings.notifications.ui.enabled': 'Enabled',
  'settings.notifications.ui.inApp': 'In-App',
  'settings.notifications.ui.email': 'Email',
  'settings.notifications.ui.disableAll': 'Disable All',
  'settings.notifications.ui.enableAll': 'Enable All',
  'settings.notifications.ui.savePreferences': 'Save Preferences',
  'settings.notifications.ui.sendTestEmail': 'Send Test Email',
  'settings.notifications.ui.authRequired': 'Authentication Required',
  'settings.notifications.ui.authRequiredDesc':
    'Please log in to access notification settings',
  'settings.notifications.ui.enabledCount':
    '{enabled} of {total} notification types enabled',
  'settings.notifications.ui.preferencesSaved':
    'Notification preferences saved successfully!',
  'settings.notifications.ui.saveFailed':
    'Failed to save notification preferences',
  'settings.notifications.ui.loadFailed':
    'Failed to load notification preferences',
  'settings.notifications.ui.initFailed':
    'Failed to initialize notification settings',
  'settings.notifications.breadcrumb.settings': 'Settings',
  'settings.notifications.breadcrumb.notifications': 'Notifications',
  'settings.notifications.help.title': 'About Notifications',
  'settings.notifications.help.inAppTitle': 'In-app notifications',
  'settings.notifications.help.inAppDesc':
    'appear in the notification bell and on the notifications page. You\'ll see them in real-time while using BenGER.',
  'settings.notifications.help.emailTitle': 'Email notifications',
  'settings.notifications.help.emailDescBefore': 'are sent to',
  'settings.notifications.help.emailDescAfter':
    'You can send a test email to verify your settings are working.',
  'settings.notifications.help.roleBasedDesc':
    'Notifications are sent based on your role and organization membership. You\'ll only receive notifications for tasks and organizations you have access to.',
  'settings.notifications.help.preferencesDesc':
    'Changes to your notification preferences are saved immediately and apply to all future notifications.',
  'settings.notifications.timezone.utc': 'UTC',
}

const mockT = (key: string, params?: Record<string, any>) => {
  let translation = mockTranslations[key as keyof typeof mockTranslations] || key
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      translation = translation.replace(new RegExp(`\\{${k}\\}`, 'g'), String(v))
    })
  }
  return translation
}

const mockEmailStatus = {
  available: true,
  configured: true,
  message: 'Email service is configured',
}

const mockPreferences = {
  project_created: { enabled: true, in_app: true, email: false },
  project_updated: { enabled: true, in_app: true, email: true },
  project_shared: { enabled: false, in_app: false, email: false },
  evaluation_completed: { enabled: true, in_app: true, email: false },
  annotation_assigned: { enabled: true, in_app: true, email: false },
}

// Setup default mocks for contexts
const mockIsEnabled = jest.fn((flag: string) => true)

jest.mock('@/contexts/AuthContext', () => {
  const mockUseAuth = jest.fn()
  return {
    useAuth: mockUseAuth,
    AuthProvider: ({ children }: any) => children,
  }
})

jest.mock('@/contexts/I18nContext', () => {
  const mockUseI18n = jest.fn()
  return {
    useI18n: mockUseI18n,
    I18nProvider: ({ children }: any) => children,
  }
})

jest.mock('@/contexts/FeatureFlagContext', () => {
  const mockUseFeatureFlags = jest.fn()
  return {
    useFeatureFlags: mockUseFeatureFlags,
    FeatureFlagProvider: ({ children }: any) => children,
  }
})

describe('NotificationSettingsPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()

    // Reset all mocks to default values
    mockIsEnabled.mockImplementation((flag: string) => true)

    // Mock auth context
    ;(useAuth as jest.Mock).mockReturnValue({
      user: mockUser,
    })

    // Mock i18n context
    ;(useI18n as jest.Mock).mockReturnValue({
      t: mockT,
      changeLanguage: jest.fn(),
      currentLanguage: 'en',
    })

    // Mock feature flags context
    ;(useFeatureFlags as jest.Mock).mockReturnValue({
      flags: {},
      isLoading: false,
      error: null,
      isEnabled: mockIsEnabled,
      refreshFlags: jest.fn(),
      checkFlag: jest.fn().mockResolvedValue(true),
      lastUpdate: Date.now(),
    })

    // Mock API responses
    ;(api.getNotificationPreferences as jest.Mock).mockResolvedValue(
      mockPreferences
    )
    ;(api.notifications.getEmailStatus as jest.Mock).mockResolvedValue(
      mockEmailStatus
    )
    ;(api.updateNotificationPreferences as jest.Mock).mockResolvedValue({})
    ;(api.notifications.sendTestEmail as jest.Mock).mockResolvedValue({
      message: 'Test email sent successfully!',
    })
  })

  describe('Page Rendering', () => {
    it('renders the page with title and subtitle', async () => {
      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(screen.getByText('Notification Settings')).toBeInTheDocument()
        expect(
          screen.getByText('Manage your notification preferences')
        ).toBeInTheDocument()
      })
    })

    it('renders breadcrumb navigation', async () => {
      render(<NotificationSettingsPage />)

      await waitFor(() => {
        const breadcrumb = screen.getByTestId('breadcrumb')
        expect(breadcrumb).toBeInTheDocument()
        expect(within(breadcrumb).getByText('Settings')).toBeInTheDocument()
        expect(
          within(breadcrumb).getByText('Notifications')
        ).toBeInTheDocument()
      })
    })

    it('shows loading state initially', () => {
      render(<NotificationSettingsPage />)

      expect(screen.getByText('Loading...')).toBeInTheDocument()
    })

    it('loads and displays notification preferences', async () => {
      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(screen.getByText('Project Created')).toBeInTheDocument()
        expect(screen.getByText('Project Updated')).toBeInTheDocument()
      })

      expect(api.getNotificationPreferences).toHaveBeenCalled()
    })

    it('requires authentication to view settings', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({ user: null })

      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(screen.getByText('Authentication Required')).toBeInTheDocument()
        expect(
          screen.getByText('Please log in to access notification settings')
        ).toBeInTheDocument()
      })
    })

    it('handles translation loading', async () => {
      ;(useI18n as jest.Mock).mockReturnValue({
        t: null,
        changeLanguage: jest.fn(),
        currentLanguage: 'en',
      })

      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(screen.getByText('Loading translations...')).toBeInTheDocument()
      })
    })
  })

  describe('Email Status Display', () => {
    it('displays email configured status', async () => {
      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(
          screen.getByText('Email notifications available')
        ).toBeInTheDocument()
        expect(
          screen.getByText('You can enable email notifications')
        ).toBeInTheDocument()
      })
    })

    it('displays email not configured warning', async () => {
      ;(api.notifications.getEmailStatus as jest.Mock).mockResolvedValue({
        available: false,
        configured: false,
        message: 'Email service not configured',
      })

      render(<NotificationSettingsPage />)

      await waitFor(() => {
        const notConfiguredElements = screen.getAllByText(
          'Email not configured'
        )
        expect(notConfiguredElements.length).toBeGreaterThan(0)
        expect(
          screen.getByText('Email service is not configured')
        ).toBeInTheDocument()
      })
    })

    it('shows test email button when email is configured', async () => {
      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(
          screen.getByTestId('settings-test-email-button')
        ).toBeInTheDocument()
      })
    })

    it('hides test email button when email is not configured', async () => {
      ;(api.notifications.getEmailStatus as jest.Mock).mockResolvedValue({
        available: false,
        configured: false,
        message: 'Email service not configured',
      })

      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(
          screen.queryByTestId('settings-test-email-button')
        ).not.toBeInTheDocument()
      })
    })
  })

  describe('Notification Preferences Display', () => {
    it('displays all notification types', async () => {
      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(screen.getByText('Project Created')).toBeInTheDocument()
        expect(screen.getByText('Project Updated')).toBeInTheDocument()
        expect(screen.getByText('Annotation Assigned')).toBeInTheDocument()
        expect(screen.getByText('Evaluation Completed')).toBeInTheDocument()
      })
    })

    it('displays notification descriptions', async () => {
      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(
          screen.getByText(
            'Receive notifications when new projects are created'
          )
        ).toBeInTheDocument()
        expect(
          screen.getByText('Receive notifications when projects are updated')
        ).toBeInTheDocument()
      })
    })

    it('displays category badges', async () => {
      render(<NotificationSettingsPage />)

      await waitFor(() => {
        const projectsElements = screen.getAllByText('Projects')
        expect(projectsElements.length).toBeGreaterThan(0)
        const annotationElements = screen.getAllByText('Annotation')
        expect(annotationElements.length).toBeGreaterThan(0)
      })
    })

    it('shows correct toggle states for enabled notifications', async () => {
      render(<NotificationSettingsPage />)

      await waitFor(() => {
        const projectCreatedToggle = screen.getByTestId(
          'settings-notification-toggle-project_created'
        )
        expect(projectCreatedToggle).toHaveClass('bg-emerald-600')
      })
    })

    it('shows correct toggle states for disabled notifications', async () => {
      render(<NotificationSettingsPage />)

      await waitFor(() => {
        const projectSharedToggle = screen.getByTestId(
          'settings-notification-toggle-project_shared'
        )
        expect(projectSharedToggle).not.toHaveClass('bg-emerald-600')
      })
    })
  })

  describe('Toggle Email Notifications', () => {
    it('toggles email notifications on', async () => {
      const user = userEvent.setup()
      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(screen.getByText('Project Created')).toBeInTheDocument()
      })

      const emailToggle = screen.getByTestId(
        'settings-notification-email-project_created'
      )
      await user.click(emailToggle)

      await waitFor(() => {
        expect(emailToggle).toHaveClass('bg-emerald-600')
      })
    })

    it('toggles email notifications off', async () => {
      const user = userEvent.setup()
      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(screen.getByText('Project Updated')).toBeInTheDocument()
      })

      const emailToggle = screen.getByTestId(
        'settings-notification-email-project_updated'
      )
      await user.click(emailToggle)

      await waitFor(() => {
        expect(emailToggle).not.toHaveClass('bg-emerald-600')
      })
    })

    it('disables email toggle when email is not configured', async () => {
      ;(api.notifications.getEmailStatus as jest.Mock).mockResolvedValue({
        available: false,
        configured: false,
        message: 'Email service not configured',
      })

      render(<NotificationSettingsPage />)

      await waitFor(() => {
        const emailToggle = screen.getByTestId(
          'settings-notification-email-project_created'
        )
        expect(emailToggle).toBeDisabled()
      })
    })

    it('disables email toggle when main toggle is off', async () => {
      render(<NotificationSettingsPage />)

      await waitFor(() => {
        const emailToggle = screen.getByTestId(
          'settings-notification-email-project_shared'
        )
        expect(emailToggle).toBeDisabled()
      })
    })
  })

  describe('Toggle In-App Notifications', () => {
    it('toggles in-app notifications on', async () => {
      const user = userEvent.setup()
      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(screen.getByText('Project Created')).toBeInTheDocument()
      })

      // Toggle in-app off first
      const inAppToggle = screen.getByTestId(
        'settings-notification-inapp-project_created'
      )
      await user.click(inAppToggle)

      await waitFor(() => {
        expect(inAppToggle).not.toHaveClass('bg-emerald-600')
      })

      // Then toggle it back on
      await user.click(inAppToggle)

      await waitFor(() => {
        expect(inAppToggle).toHaveClass('bg-emerald-600')
      })
    })

    it('toggles in-app notifications off', async () => {
      const user = userEvent.setup()
      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(screen.getByText('Project Created')).toBeInTheDocument()
      })

      const inAppToggle = screen.getByTestId(
        'settings-notification-inapp-project_created'
      )
      await user.click(inAppToggle)

      await waitFor(() => {
        expect(inAppToggle).not.toHaveClass('bg-emerald-600')
      })
    })

    it('disables in-app toggle when main toggle is off', async () => {
      render(<NotificationSettingsPage />)

      await waitFor(() => {
        const inAppToggle = screen.getByTestId(
          'settings-notification-inapp-project_shared'
        )
        expect(inAppToggle).toBeDisabled()
      })
    })
  })

  describe('Toggle Main Notification Switch', () => {
    it('enables notification type', async () => {
      const user = userEvent.setup()
      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(screen.getByText('Project Shared')).toBeInTheDocument()
      })

      const mainToggle = screen.getByTestId(
        'settings-notification-toggle-project_shared'
      )

      // Verify it starts disabled
      expect(mainToggle).not.toHaveClass('bg-emerald-600')

      await user.click(mainToggle)

      // After clicking, it should be enabled
      expect(mainToggle).toHaveClass('bg-emerald-600')
    })

    it('disables notification type', async () => {
      const user = userEvent.setup()
      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(screen.getByText('Project Created')).toBeInTheDocument()
      })

      const mainToggle = screen.getByTestId(
        'settings-notification-toggle-project_created'
      )

      // Verify it starts enabled
      expect(mainToggle).toHaveClass('bg-emerald-600')

      await user.click(mainToggle)

      // After clicking, it should be disabled
      expect(mainToggle).not.toHaveClass('bg-emerald-600')
    })

    it('disables in-app and email when main toggle is disabled', async () => {
      const user = userEvent.setup()
      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(screen.getByText('Project Created')).toBeInTheDocument()
      })

      const mainToggle = screen.getByTestId(
        'settings-notification-toggle-project_created'
      )
      await user.click(mainToggle)

      await waitFor(() => {
        const inAppToggle = screen.getByTestId(
          'settings-notification-inapp-project_created'
        )
        const emailToggle = screen.getByTestId(
          'settings-notification-email-project_created'
        )
        expect(inAppToggle).toBeDisabled()
        expect(emailToggle).toBeDisabled()
      })
    })
  })

  describe('Save Settings', () => {
    it('saves notification preferences successfully', async () => {
      const user = userEvent.setup()
      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(
          screen.getByTestId('settings-save-notifications-button')
        ).toBeInTheDocument()
      })

      const saveButton = screen.getByTestId(
        'settings-save-notifications-button'
      )
      await user.click(saveButton)

      await waitFor(() => {
        expect(api.updateNotificationPreferences).toHaveBeenCalled()
        expect(
          screen.getByText('Notification preferences saved successfully!')
        ).toBeInTheDocument()
      })
    })

    it('shows saving state during save', async () => {
      const user = userEvent.setup()
      ;(api.updateNotificationPreferences as jest.Mock).mockImplementation(
        () => new Promise((resolve) => setTimeout(resolve, 100))
      )

      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(
          screen.getByTestId('settings-save-notifications-button')
        ).toBeInTheDocument()
      })

      const saveButton = screen.getByTestId(
        'settings-save-notifications-button'
      )
      await user.click(saveButton)

      expect(screen.getByText('Saving...')).toBeInTheDocument()
      expect(saveButton).toBeDisabled()
    })

    it('handles save error', async () => {
      const user = userEvent.setup()
      ;(api.updateNotificationPreferences as jest.Mock).mockRejectedValue(
        new Error('Failed to save')
      )

      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(
          screen.getByTestId('settings-save-notifications-button')
        ).toBeInTheDocument()
      })

      const saveButton = screen.getByTestId(
        'settings-save-notifications-button'
      )
      await user.click(saveButton)

      await waitFor(() => {
        expect(
          screen.getByText('Failed to save notification preferences')
        ).toBeInTheDocument()
      })
    })

    it('converts new format to legacy format when saving', async () => {
      const user = userEvent.setup()
      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(
          screen.getByTestId('settings-save-notifications-button')
        ).toBeInTheDocument()
      })

      const saveButton = screen.getByTestId(
        'settings-save-notifications-button'
      )
      await user.click(saveButton)

      await waitFor(() => {
        expect(api.updateNotificationPreferences).toHaveBeenCalledWith(
          expect.objectContaining({
            project_created: true,
            project_updated: true,
            project_shared: false,
          })
        )
      })
    })
  })

  describe('Bulk Actions', () => {
    it('disables all notifications', async () => {
      const user = userEvent.setup()
      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(
          screen.getByTestId('settings-disable-all-notifications-button')
        ).toBeInTheDocument()
      })

      const disableAllButton = screen.getByTestId(
        'settings-disable-all-notifications-button'
      )
      await user.click(disableAllButton)

      await waitFor(() => {
        const projectCreatedToggle = screen.getByTestId(
          'settings-notification-toggle-project_created'
        )
        expect(projectCreatedToggle).not.toHaveClass('bg-emerald-600')
      })
    })

    it('enables all notifications', async () => {
      const user = userEvent.setup()
      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(
          screen.getByTestId('settings-enable-all-notifications-button')
        ).toBeInTheDocument()
      })

      const enableAllButton = screen.getByTestId(
        'settings-enable-all-notifications-button'
      )
      await user.click(enableAllButton)

      await waitFor(() => {
        const projectSharedToggle = screen.getByTestId(
          'settings-notification-toggle-project_shared'
        )
        expect(projectSharedToggle).toHaveClass('bg-emerald-600')
      })
    })

    it('shows count of enabled notifications', async () => {
      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(
          screen.getByText(/of.*notification types enabled/)
        ).toBeInTheDocument()
      })
    })
  })

  describe('Send Test Email', () => {
    it('sends test email successfully', async () => {
      const user = userEvent.setup()
      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(
          screen.getByTestId('settings-test-email-button')
        ).toBeInTheDocument()
      })

      const testButton = screen.getByTestId('settings-test-email-button')
      await user.click(testButton)

      await waitFor(() => {
        expect(api.notifications.sendTestEmail).toHaveBeenCalled()
        expect(
          screen.getByText('Test email sent successfully!')
        ).toBeInTheDocument()
      })
    })

    it('shows sending state during test email', async () => {
      const user = userEvent.setup()
      ;(api.notifications.sendTestEmail as jest.Mock).mockImplementation(
        () => new Promise((resolve) => setTimeout(resolve, 100))
      )

      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(
          screen.getByTestId('settings-test-email-button')
        ).toBeInTheDocument()
      })

      const testButton = screen.getByTestId('settings-test-email-button')
      await user.click(testButton)

      expect(screen.getByText('Sending...')).toBeInTheDocument()
      expect(testButton).toBeDisabled()
    })

    it('handles test email error', async () => {
      const user = userEvent.setup()
      ;(api.notifications.sendTestEmail as jest.Mock).mockRejectedValue({
        response: {
          data: {
            detail: 'Email service unavailable',
          },
        },
      })

      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(
          screen.getByTestId('settings-test-email-button')
        ).toBeInTheDocument()
      })

      const testButton = screen.getByTestId('settings-test-email-button')
      await user.click(testButton)

      await waitFor(() => {
        expect(
          screen.getByText('Email service unavailable')
        ).toBeInTheDocument()
      })
    })
  })

  describe('Error Handling', () => {
    it('handles API error when loading preferences', async () => {
      ;(api.getNotificationPreferences as jest.Mock).mockRejectedValue(
        new Error('Failed to load preferences')
      )

      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(
          screen.getByText('Failed to load notification preferences')
        ).toBeInTheDocument()
      })
    })

    it('handles translation loading error', async () => {
      ;(useI18n as jest.Mock).mockReturnValue({
        t: () => {
          throw new Error('Translation error')
        },
        changeLanguage: jest.fn(),
        currentLanguage: 'en',
      })

      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(
          screen.getByText('Error loading notification settings')
        ).toBeInTheDocument()
      })
    })

    it('shows reload button on configuration error', async () => {
      ;(useI18n as jest.Mock).mockReturnValue({
        t: () => {
          throw new Error('Translation error')
        },
        changeLanguage: jest.fn(),
        currentLanguage: 'en',
      })

      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(screen.getByText('Reload Page')).toBeInTheDocument()
        expect(
          screen.getByText('Error loading notification settings')
        ).toBeInTheDocument()
      })

      // Verify the button exists and can be interacted with
      const reloadButton = screen.getByText('Reload Page')
      expect(reloadButton).toBeInTheDocument()
    })

    it('handles email status loading failure gracefully', async () => {
      ;(api.notifications.getEmailStatus as jest.Mock).mockRejectedValue(
        new Error('Failed to load email status')
      )

      render(<NotificationSettingsPage />)

      await waitFor(() => {
        // Should still load preferences even if email status fails
        expect(screen.getByText('Project Created')).toBeInTheDocument()
      })
    })

    it('clears success message after timeout', async () => {
      jest.useFakeTimers()
      const user = userEvent.setup({ delay: null })

      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(
          screen.getByTestId('settings-save-notifications-button')
        ).toBeInTheDocument()
      })

      const saveButton = screen.getByTestId(
        'settings-save-notifications-button'
      )
      await user.click(saveButton)

      await waitFor(() => {
        expect(
          screen.getByText('Notification preferences saved successfully!')
        ).toBeInTheDocument()
      })

      jest.advanceTimersByTime(3000)

      await waitFor(() => {
        expect(
          screen.queryByText('Notification preferences saved successfully!')
        ).not.toBeInTheDocument()
      })

      jest.useRealTimers()
    })
  })

  describe('Notification Type Display', () => {
    it('shows all notification types including evaluations', async () => {
      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(screen.getByText('Evaluation Completed')).toBeInTheDocument()
        expect(screen.getByText('Evaluation Failed')).toBeInTheDocument()
      })
    })

    it('shows all notification types including generation', async () => {
      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(
          screen.getByText('LLM Generation Completed')
        ).toBeInTheDocument()
      })
    })

    it('shows all notification types including data upload', async () => {
      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(screen.getByText('Data Upload Completed')).toBeInTheDocument()
      })
    })

    it('shows all notification types', async () => {
      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(screen.getByText('Project Created')).toBeInTheDocument()
        expect(screen.getByText('Evaluation Completed')).toBeInTheDocument()
        expect(screen.getByText('LLM Generation Completed')).toBeInTheDocument()
        expect(screen.getByText('Data Upload Completed')).toBeInTheDocument()
      })
    })
  })

  describe('Legacy Preference Conversion', () => {
    it('converts legacy boolean preferences to new format', async () => {
      ;(api.getNotificationPreferences as jest.Mock).mockResolvedValue({
        project_created: true,
        project_updated: false,
      })

      render(<NotificationSettingsPage />)

      await waitFor(() => {
        const projectCreatedToggle = screen.getByTestId(
          'settings-notification-toggle-project_created'
        )
        const projectUpdatedToggle = screen.getByTestId(
          'settings-notification-toggle-project_updated'
        )

        expect(projectCreatedToggle).toHaveClass('bg-emerald-600')
        expect(projectUpdatedToggle).not.toHaveClass('bg-emerald-600')
      })
    })
  })

  describe('Help Section', () => {
    it('displays help information', async () => {
      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(screen.getByText('About Notifications')).toBeInTheDocument()
        expect(screen.getByText(/In-app notifications/)).toBeInTheDocument()
      })
    })

    it('shows user email in help section', async () => {
      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(screen.getByText('test@example.com')).toBeInTheDocument()
      })
    })

    it('hides email help when email is not configured', async () => {
      ;(api.notifications.getEmailStatus as jest.Mock).mockResolvedValue({
        available: false,
        configured: false,
        message: 'Email service not configured',
      })

      render(<NotificationSettingsPage />)

      await waitFor(() => {
        expect(
          screen.queryByText(/Email notifications are sent to/)
        ).not.toBeInTheDocument()
      })
    })
  })
})
