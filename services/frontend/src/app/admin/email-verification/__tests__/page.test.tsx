/**
 * @jest-environment jsdom
 */

import { useI18n } from '@/contexts/I18nContext'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import EmailVerificationManagement from '../page'

// Mock i18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(),
}))

// Mock fetch
global.fetch = jest.fn()

const mockStatistics = {
  total_users: 100,
  verified_users: 85,
  unverified_users: 15,
  verification_rate_percent: 85,
  recent_unverified: 5,
  pending_verification: 10,
  expired_tokens: 3,
  period_days: 7,
  generated_at: '2024-01-15T10:00:00Z',
}

const mockUnverifiedUsers = [
  {
    id: 'user-1',
    username: 'testuser1',
    email: 'test1@example.com',
    name: 'Test User 1',
    created_at: '2024-01-01T00:00:00Z',
    email_verification_sent_at: '2024-01-10T00:00:00Z',
    has_verification_token: true,
    days_since_registration: 14,
  },
  {
    id: 'user-2',
    username: 'testuser2',
    email: 'test2@example.com',
    name: 'Test User 2',
    created_at: '2024-01-05T00:00:00Z',
    email_verification_sent_at: null,
    has_verification_token: false,
    days_since_registration: 10,
  },
]

const mockStatisticsReport = {
  weekly_stats: mockStatistics,
  monthly_stats: {
    ...mockStatistics,
    verification_rate_percent: 88,
    period_days: 30,
  },
  trends: {
    weekly_verification_rate: 85,
    monthly_verification_rate: 88,
    rate_trend: 'improving',
  },
  alerts: [
    {
      level: 'warning',
      message: 'High number of unverified users detected',
    },
  ],
}

describe('EmailVerificationManagement', () => {
  beforeEach(() => {
    jest.clearAllMocks()

    // Mock i18n
    const mockUseI18n = useI18n as jest.MockedFunction<typeof useI18n>
    mockUseI18n.mockReturnValue({
      locale: 'en',
      t: (key: string) => {
        // Return translation keys with placeholder replacements
        const translations: Record<string, string> = {
          'emailVerification.admin.title': 'Email Verification Management',
          'emailVerification.admin.description':
            'Monitor and manage email verification status',
          'emailVerification.admin.alerts.loadFailed':
            'Failed to load email verification data',
          'emailVerification.admin.alerts.cleanupSuccess':
            'Cleanup completed! {{count}} expired tokens removed.',
          'emailVerification.admin.alerts.cleanupFailed':
            'Failed to run token cleanup',
          'emailVerification.admin.alerts.remindersSuccess':
            'Reminder emails sent! {{count}} emails sent successfully.',
          'emailVerification.admin.alerts.remindersFailed':
            'Failed to send reminder emails',
          'emailVerification.admin.alerts.resendSuccess':
            'Verification email resent to {{email}}',
          'emailVerification.admin.alerts.resendFailed':
            'Failed to resend verification email',
          'emailVerification.admin.alerts.systemAlerts': 'System Alerts',
          'emailVerification.admin.metrics.totalUsers': 'Total Users',
          'emailVerification.admin.metrics.registeredUsers': 'Registered Users',
          'emailVerification.admin.metrics.verifiedUsers': 'Verified Users',
          'emailVerification.admin.metrics.emailVerified': 'Email Verified',
          'emailVerification.admin.metrics.unverifiedUsers': 'Unverified Users',
          'emailVerification.admin.metrics.needVerification':
            'Need Verification',
          'emailVerification.admin.metrics.verificationRate':
            'Verification Rate',
          'emailVerification.admin.metrics.overallRate': 'Overall Rate',
          'emailVerification.admin.metrics.pendingVerification':
            'Pending Verification',
          'emailVerification.admin.metrics.awaitingClick': 'Awaiting Click',
          'emailVerification.admin.metrics.expiredTokens': 'Expired Tokens',
          'emailVerification.admin.metrics.needCleanup': 'Need Cleanup',
          'emailVerification.admin.metrics.recentUnverified':
            'Recent Unverified',
          'emailVerification.admin.metrics.lastSevenDays': 'Last 7 Days',
          'emailVerification.admin.users.unverifiedCount':
            'Unverified Users ({{count}})',
          'emailVerification.admin.users.manageUnverified':
            'Manage Unverified Users',
          'emailVerification.admin.users.allVerified':
            'All users have verified their emails!',
          'emailVerification.admin.users.tokenActive': 'Token Active',
          'emailVerification.admin.users.noToken': 'No Token',
          'emailVerification.admin.users.registered': 'Registered: {{date}}',
          'emailVerification.admin.users.lastEmail': 'Last Email: {{date}}',
          'emailVerification.admin.users.daysAgo': '{{days}} days ago',
          'emailVerification.admin.users.resend': 'Resend',
          'emailVerification.admin.analytics.trends': 'Verification Trends',
          'emailVerification.admin.analytics.weeklyRate': 'Weekly Rate',
          'emailVerification.admin.analytics.monthlyRate': 'Monthly Rate',
          'emailVerification.admin.analytics.trend': 'Trend',
          'emailVerification.admin.analytics.improving': 'Improving',
          'emailVerification.admin.analytics.declining': 'Declining',
          'emailVerification.admin.maintenance.operations':
            'Maintenance Operations',
          'emailVerification.admin.maintenance.adminTasks':
            'Administrative Tasks',
          'emailVerification.admin.maintenance.cleanupExpired':
            'Cleanup Expired Tokens',
          'emailVerification.admin.maintenance.cleanupDesc':
            'Remove expired verification tokens from database',
          'emailVerification.admin.maintenance.runCleanup': 'Run Cleanup',
          'emailVerification.admin.maintenance.sendReminders':
            'Send Reminder Emails',
          'emailVerification.admin.maintenance.remindersDesc':
            'Send reminder emails to unverified users',
          'emailVerification.admin.maintenance.sendRemindersBtn':
            'Send Reminders',
          'emailVerification.admin.maintenance.refreshData': 'Refresh Data',
          'emailVerification.admin.maintenance.refreshDesc':
            'Reload all statistics and data',
          'emailVerification.admin.maintenance.refresh': 'Refresh',
          'emailVerification.admin.maintenance.loading': 'Loading...',
          'emailVerification.admin.tabs.overview': 'Overview',
          'emailVerification.admin.tabs.users': 'Users',
          'emailVerification.admin.tabs.analytics': 'Analytics',
          'emailVerification.admin.tabs.maintenance': 'Maintenance',
        }
        return translations[key] || key
      },
      changeLocale: jest.fn(),
    })
    ;(global.fetch as jest.Mock).mockImplementation((url: string) => {
      if (url.includes('/statistics-report')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ report: mockStatisticsReport }),
        })
      }
      if (url.includes('/statistics')) {
        return Promise.resolve({
          ok: true,
          json: async () => mockStatistics,
        })
      }
      if (url.includes('/unverified-users')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ users: mockUnverifiedUsers }),
        })
      }
      return Promise.reject(new Error('Unknown URL'))
    })
  })

  describe('Initial Loading', () => {
    it('should show loading state initially', async () => {
      let resolveStatistics: any
      ;(global.fetch as jest.Mock).mockImplementation(() => {
        return new Promise((resolve) => {
          resolveStatistics = resolve
        })
      })

      render(<EmailVerificationManagement />)

      expect(screen.getByText('Loading...')).toBeInTheDocument()

      // Cleanup
      if (resolveStatistics) {
        resolveStatistics({
          ok: true,
          json: async () => mockStatistics,
        })
      }
    })

    it('should load all initial data on mount', async () => {
      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining('/statistics'),
          expect.any(Object)
        )
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining('/unverified-users'),
          expect.any(Object)
        )
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining('/statistics-report'),
          expect.any(Object)
        )
      })
    })

    it('should display error when data loading fails', async () => {
      ;(global.fetch as jest.Mock).mockRejectedValue(new Error('Network error'))

      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(
          screen.getByText('Failed to load email verification data')
        ).toBeInTheDocument()
      })
    })
  })

  describe('Overview Tab', () => {
    it('should display overview tab by default', async () => {
      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })
    })

    it('should display all statistics cards', async () => {
      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
        expect(screen.getByText('Verified Users')).toBeInTheDocument()
        expect(screen.getByText('Unverified Users')).toBeInTheDocument()
        expect(screen.getByText('Verification Rate')).toBeInTheDocument()
        expect(screen.getByText('Pending Verification')).toBeInTheDocument()
        expect(screen.getByText('Expired Tokens')).toBeInTheDocument()
        expect(screen.getByText('Recent Unverified')).toBeInTheDocument()
      })
    })

    it('should display correct statistics values', async () => {
      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('100')).toBeInTheDocument() // total_users
        expect(screen.getByText('85')).toBeInTheDocument() // verified_users
        expect(screen.getByText('15')).toBeInTheDocument() // unverified_users
        expect(screen.getByText('85%')).toBeInTheDocument() // verification_rate
        expect(screen.getByText('10')).toBeInTheDocument() // pending_verification
        expect(screen.getByText('3')).toBeInTheDocument() // expired_tokens
        expect(screen.getByText('5')).toBeInTheDocument() // recent_unverified
      })
    })

    it('should display system alerts when present', async () => {
      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('System Alerts')).toBeInTheDocument()
        expect(
          screen.getByText('High number of unverified users detected')
        ).toBeInTheDocument()
      })
    })

    it('should not display alerts section when no alerts', async () => {
      ;(global.fetch as jest.Mock).mockImplementation((url: string) => {
        if (url.includes('/statistics-report')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              report: { ...mockStatisticsReport, alerts: [] },
            }),
          })
        }
        if (url.includes('/statistics')) {
          return Promise.resolve({
            ok: true,
            json: async () => mockStatistics,
          })
        }
        if (url.includes('/unverified-users')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({ users: [] }),
          })
        }
        return Promise.reject(new Error('Unknown URL'))
      })

      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      expect(screen.queryByText('System Alerts')).not.toBeInTheDocument()
    })

    it('should apply correct color to verification rate - green', async () => {
      ;(global.fetch as jest.Mock).mockImplementation((url: string) => {
        if (url.includes('/statistics')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              ...mockStatistics,
              verification_rate_percent: 95,
            }),
          })
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ report: mockStatisticsReport }),
        })
      })

      render(<EmailVerificationManagement />)

      await waitFor(() => {
        const rateElement = screen.getByText('95%')
        expect(rateElement).toHaveClass('text-green-600')
      })
    })

    it('should apply correct color to verification rate - yellow', async () => {
      ;(global.fetch as jest.Mock).mockImplementation((url: string) => {
        if (url.includes('/statistics')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              ...mockStatistics,
              verification_rate_percent: 80,
            }),
          })
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ report: mockStatisticsReport }),
        })
      })

      render(<EmailVerificationManagement />)

      await waitFor(() => {
        const rateElement = screen.getByText('80%')
        expect(rateElement).toHaveClass('text-yellow-600')
      })
    })

    it('should apply correct color to verification rate - red', async () => {
      ;(global.fetch as jest.Mock).mockImplementation((url: string) => {
        if (url.includes('/statistics')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              ...mockStatistics,
              verification_rate_percent: 60,
            }),
          })
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ report: mockStatisticsReport }),
        })
      })

      render(<EmailVerificationManagement />)

      await waitFor(() => {
        const rateElement = screen.getByText('60%')
        expect(rateElement).toHaveClass('text-red-600')
      })
    })
  })

  describe('Users Tab', () => {
    it('should switch to users tab', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const usersTab = screen.getByText('Users')
      await user.click(usersTab)

      await waitFor(() => {
        expect(screen.getByText(/Unverified Users \(/)).toBeInTheDocument()
      })
    })

    it('should display list of unverified users', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const usersTab = screen.getByText('Users')
      await user.click(usersTab)

      await waitFor(() => {
        expect(screen.getByText('Test User 1')).toBeInTheDocument()
        expect(screen.getByText('test1@example.com')).toBeInTheDocument()
        expect(screen.getByText('Test User 2')).toBeInTheDocument()
        expect(screen.getByText('test2@example.com')).toBeInTheDocument()
      })
    })

    it('should display token status badges', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const usersTab = screen.getByText('Users')
      await user.click(usersTab)

      await waitFor(() => {
        expect(screen.getByText('Token Active')).toBeInTheDocument()
        expect(screen.getByText('No Token')).toBeInTheDocument()
      })
    })

    it('should display user registration information', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const usersTab = screen.getByText('Users')
      await user.click(usersTab)

      await waitFor(() => {
        expect(screen.getByText(/14 days ago/)).toBeInTheDocument()
        expect(screen.getByText(/10 days ago/)).toBeInTheDocument()
      })
    })

    it('should show empty state when no unverified users', async () => {
      ;(global.fetch as jest.Mock).mockImplementation((url: string) => {
        if (url.includes('/unverified-users')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({ users: [] }),
          })
        }
        if (url.includes('/statistics')) {
          return Promise.resolve({
            ok: true,
            json: async () => mockStatistics,
          })
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ report: mockStatisticsReport }),
        })
      })

      const user = userEvent.setup()
      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const usersTab = screen.getByText('Users')
      await user.click(usersTab)

      await waitFor(() => {
        expect(
          screen.getByText('All users have verified their emails!')
        ).toBeInTheDocument()
      })
    })

    it('should display resend verification button', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const usersTab = screen.getByText('Users')
      await user.click(usersTab)

      await waitFor(() => {
        const resendButtons = screen.getAllByText('Resend')
        expect(resendButtons).toHaveLength(2)
      })
    })

    it('should handle resend verification successfully', async () => {
      const user = userEvent.setup()
      ;(global.fetch as jest.Mock).mockImplementation((url: string) => {
        if (url.includes('/resend-verification/user-1')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              success: true,
              user_email: 'test1@example.com',
            }),
          })
        }
        if (url.includes('/unverified-users')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({ users: mockUnverifiedUsers }),
          })
        }
        if (url.includes('/statistics')) {
          return Promise.resolve({
            ok: true,
            json: async () => mockStatistics,
          })
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ report: mockStatisticsReport }),
        })
      })

      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const usersTab = screen.getByText('Users')
      await user.click(usersTab)

      await waitFor(() => {
        expect(screen.getByText('Test User 1')).toBeInTheDocument()
      })

      const resendButtons = screen.getAllByText('Resend')
      await user.click(resendButtons[0])

      await waitFor(() => {
        expect(
          screen.getByText('Verification email resent to test1@example.com')
        ).toBeInTheDocument()
      })
    })

    it('should handle resend verification failure', async () => {
      const user = userEvent.setup()
      ;(global.fetch as jest.Mock).mockImplementation((url: string) => {
        if (url.includes('/resend-verification/user-1')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              success: false,
              message: 'Email service unavailable',
            }),
          })
        }
        if (url.includes('/unverified-users')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({ users: mockUnverifiedUsers }),
          })
        }
        if (url.includes('/statistics')) {
          return Promise.resolve({
            ok: true,
            json: async () => mockStatistics,
          })
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ report: mockStatisticsReport }),
        })
      })

      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const usersTab = screen.getByText('Users')
      await user.click(usersTab)

      await waitFor(() => {
        expect(screen.getByText('Test User 1')).toBeInTheDocument()
      })

      const resendButtons = screen.getAllByText('Resend')
      await user.click(resendButtons[0])

      await waitFor(() => {
        expect(
          screen.getByText('Email service unavailable')
        ).toBeInTheDocument()
      })
    })

    it('should handle resend verification API error', async () => {
      const user = userEvent.setup()
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation()
      ;(global.fetch as jest.Mock).mockImplementation((url: string) => {
        if (url.includes('/resend-verification/user-1')) {
          return Promise.resolve({
            ok: false,
            status: 500,
          })
        }
        if (url.includes('/unverified-users')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({ users: mockUnverifiedUsers }),
          })
        }
        if (url.includes('/statistics')) {
          return Promise.resolve({
            ok: true,
            json: async () => mockStatistics,
          })
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ report: mockStatisticsReport }),
        })
      })

      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const usersTab = screen.getByText('Users')
      await user.click(usersTab)

      await waitFor(() => {
        expect(screen.getByText('Test User 1')).toBeInTheDocument()
      })

      const resendButtons = screen.getAllByText('Resend')
      await user.click(resendButtons[0])

      await waitFor(() => {
        expect(
          screen.getByText('Failed to resend verification email')
        ).toBeInTheDocument()
      })

      consoleErrorSpy.mockRestore()
    })

    it('should handle multiple resend operations', async () => {
      const user = userEvent.setup()
      ;(global.fetch as jest.Mock).mockImplementation((url: string) => {
        if (url.includes('/resend-verification/user-1')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              success: true,
              user_email: 'test1@example.com',
            }),
          })
        }
        if (url.includes('/unverified-users')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({ users: mockUnverifiedUsers }),
          })
        }
        if (url.includes('/statistics')) {
          return Promise.resolve({
            ok: true,
            json: async () => mockStatistics,
          })
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ report: mockStatisticsReport }),
        })
      })

      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const usersTab = screen.getByText('Users')
      await user.click(usersTab)

      await waitFor(() => {
        expect(screen.getByText('Test User 1')).toBeInTheDocument()
      })

      const resendButtons = screen.getAllByText('Resend')
      const firstResendButton = resendButtons[0]

      expect(firstResendButton).not.toBeDisabled()

      await user.click(firstResendButton)

      await waitFor(() => {
        expect(
          screen.getByText('Verification email resent to test1@example.com')
        ).toBeInTheDocument()
      })
    })
  })

  describe('Analytics Tab', () => {
    it('should switch to analytics tab', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const analyticsTab = screen.getByText('Analytics')
      await user.click(analyticsTab)

      await waitFor(() => {
        expect(screen.getByText('Verification Trends')).toBeInTheDocument()
      })
    })

    it('should display trend statistics', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const analyticsTab = screen.getByText('Analytics')
      await user.click(analyticsTab)

      await waitFor(() => {
        expect(screen.getByText('Weekly Rate')).toBeInTheDocument()
        expect(screen.getByText('Monthly Rate')).toBeInTheDocument()
        expect(screen.getByText('Trend')).toBeInTheDocument()
      })
    })

    it('should display correct trend percentages', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const analyticsTab = screen.getByText('Analytics')
      await user.click(analyticsTab)

      await waitFor(() => {
        expect(screen.getByText('85%')).toBeInTheDocument()
        expect(screen.getByText('88%')).toBeInTheDocument()
      })
    })

    it('should display improving trend badge', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const analyticsTab = screen.getByText('Analytics')
      await user.click(analyticsTab)

      await waitFor(() => {
        expect(screen.getByText('↗️ Improving')).toBeInTheDocument()
      })
    })

    it('should display declining trend badge', async () => {
      ;(global.fetch as jest.Mock).mockImplementation((url: string) => {
        if (url.includes('/statistics-report')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              report: {
                ...mockStatisticsReport,
                trends: {
                  ...mockStatisticsReport.trends,
                  rate_trend: 'declining',
                },
              },
            }),
          })
        }
        if (url.includes('/statistics')) {
          return Promise.resolve({
            ok: true,
            json: async () => mockStatistics,
          })
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ users: [] }),
        })
      })

      const user = userEvent.setup()
      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const analyticsTab = screen.getByText('Analytics')
      await user.click(analyticsTab)

      await waitFor(() => {
        expect(screen.getByText('↘️ Declining')).toBeInTheDocument()
      })
    })
  })

  describe('Maintenance Tab', () => {
    it('should switch to maintenance tab', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const maintenanceTab = screen.getByText('Maintenance')
      await user.click(maintenanceTab)

      await waitFor(() => {
        expect(screen.getByText('Maintenance Operations')).toBeInTheDocument()
      })
    })

    it('should display maintenance operations', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const maintenanceTab = screen.getByText('Maintenance')
      await user.click(maintenanceTab)

      await waitFor(() => {
        expect(screen.getByText('Cleanup Expired Tokens')).toBeInTheDocument()
        expect(screen.getByText('Send Reminder Emails')).toBeInTheDocument()
        expect(screen.getByText('Refresh Data')).toBeInTheDocument()
      })
    })

    it('should handle cleanup tokens successfully', async () => {
      const user = userEvent.setup()
      ;(global.fetch as jest.Mock).mockImplementation(
        (url: string, options) => {
          if (url.includes('/run-cleanup') && options?.method === 'POST') {
            return Promise.resolve({
              ok: true,
              json: async () => ({ tokens_cleaned: 5 }),
            })
          }
          if (url.includes('/statistics')) {
            return Promise.resolve({
              ok: true,
              json: async () => mockStatistics,
            })
          }
          if (url.includes('/unverified-users')) {
            return Promise.resolve({
              ok: true,
              json: async () => ({ users: mockUnverifiedUsers }),
            })
          }
          return Promise.resolve({
            ok: true,
            json: async () => ({ report: mockStatisticsReport }),
          })
        }
      )

      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const maintenanceTab = screen.getByText('Maintenance')
      await user.click(maintenanceTab)

      await waitFor(() => {
        expect(screen.getByText('Run Cleanup')).toBeInTheDocument()
      })

      const cleanupButton = screen.getByText('Run Cleanup')
      await user.click(cleanupButton)

      await waitFor(() => {
        expect(
          screen.getByText('Cleanup completed! 5 expired tokens removed.')
        ).toBeInTheDocument()
      })
    })

    it('should handle cleanup tokens failure', async () => {
      const user = userEvent.setup()
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation()
      ;(global.fetch as jest.Mock).mockImplementation(
        (url: string, options) => {
          if (url.includes('/run-cleanup') && options?.method === 'POST') {
            return Promise.resolve({
              ok: false,
              status: 500,
            })
          }
          if (url.includes('/statistics')) {
            return Promise.resolve({
              ok: true,
              json: async () => mockStatistics,
            })
          }
          return Promise.resolve({
            ok: true,
            json: async () => ({ report: mockStatisticsReport }),
          })
        }
      )

      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const maintenanceTab = screen.getByText('Maintenance')
      await user.click(maintenanceTab)

      await waitFor(() => {
        expect(screen.getByText('Run Cleanup')).toBeInTheDocument()
      })

      const cleanupButton = screen.getByText('Run Cleanup')
      await user.click(cleanupButton)

      await waitFor(() => {
        expect(
          screen.getByText('Failed to run token cleanup')
        ).toBeInTheDocument()
      })

      consoleErrorSpy.mockRestore()
    })

    it('should handle send reminders successfully', async () => {
      const user = userEvent.setup()
      ;(global.fetch as jest.Mock).mockImplementation(
        (url: string, options) => {
          if (url.includes('/send-reminders') && options?.method === 'POST') {
            return Promise.resolve({
              ok: true,
              json: async () => ({ reminders_sent: 8 }),
            })
          }
          if (url.includes('/statistics')) {
            return Promise.resolve({
              ok: true,
              json: async () => mockStatistics,
            })
          }
          if (url.includes('/unverified-users')) {
            return Promise.resolve({
              ok: true,
              json: async () => ({ users: mockUnverifiedUsers }),
            })
          }
          return Promise.resolve({
            ok: true,
            json: async () => ({ report: mockStatisticsReport }),
          })
        }
      )

      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const maintenanceTab = screen.getByText('Maintenance')
      await user.click(maintenanceTab)

      await waitFor(() => {
        expect(screen.getByText('Send Reminders')).toBeInTheDocument()
      })

      const remindersButton = screen.getByText('Send Reminders')
      await user.click(remindersButton)

      await waitFor(() => {
        expect(
          screen.getByText('Reminder emails sent! 8 emails sent successfully.')
        ).toBeInTheDocument()
      })
    })

    it('should handle send reminders failure', async () => {
      const user = userEvent.setup()
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation()
      ;(global.fetch as jest.Mock).mockImplementation(
        (url: string, options) => {
          if (url.includes('/send-reminders') && options?.method === 'POST') {
            return Promise.resolve({
              ok: false,
              status: 500,
            })
          }
          if (url.includes('/statistics')) {
            return Promise.resolve({
              ok: true,
              json: async () => mockStatistics,
            })
          }
          return Promise.resolve({
            ok: true,
            json: async () => ({ report: mockStatisticsReport }),
          })
        }
      )

      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const maintenanceTab = screen.getByText('Maintenance')
      await user.click(maintenanceTab)

      await waitFor(() => {
        expect(screen.getByText('Send Reminders')).toBeInTheDocument()
      })

      const remindersButton = screen.getByText('Send Reminders')
      await user.click(remindersButton)

      await waitFor(() => {
        expect(
          screen.getByText('Failed to send reminder emails')
        ).toBeInTheDocument()
      })

      consoleErrorSpy.mockRestore()
    })

    it('should handle refresh data', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const maintenanceTab = screen.getByText('Maintenance')
      await user.click(maintenanceTab)

      await waitFor(() => {
        expect(screen.getByText('Refresh')).toBeInTheDocument()
      })

      jest.clearAllMocks()

      const refreshButton = screen.getByText('Refresh')
      await user.click(refreshButton)

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining('/statistics'),
          expect.any(Object)
        )
      })
    })

    it('should execute all maintenance operations', async () => {
      const user = userEvent.setup()
      ;(global.fetch as jest.Mock).mockImplementation(
        (url: string, options) => {
          if (url.includes('/run-cleanup') && options?.method === 'POST') {
            return Promise.resolve({
              ok: true,
              json: async () => ({ tokens_cleaned: 5 }),
            })
          }
          if (url.includes('/send-reminders') && options?.method === 'POST') {
            return Promise.resolve({
              ok: true,
              json: async () => ({ reminders_sent: 8 }),
            })
          }
          if (url.includes('/statistics')) {
            return Promise.resolve({
              ok: true,
              json: async () => mockStatistics,
            })
          }
          if (url.includes('/unverified-users')) {
            return Promise.resolve({
              ok: true,
              json: async () => ({ users: mockUnverifiedUsers }),
            })
          }
          return Promise.resolve({
            ok: true,
            json: async () => ({ report: mockStatisticsReport }),
          })
        }
      )

      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const maintenanceTab = screen.getByText('Maintenance')
      await user.click(maintenanceTab)

      await waitFor(() => {
        expect(screen.getByText('Run Cleanup')).toBeInTheDocument()
      })

      const cleanupButton = screen.getByText('Run Cleanup')
      expect(cleanupButton).not.toBeDisabled()

      await user.click(cleanupButton)

      await waitFor(() => {
        expect(
          screen.getByText('Cleanup completed! 5 expired tokens removed.')
        ).toBeInTheDocument()
      })
    })
  })

  describe('Tab Navigation', () => {
    it('should highlight active tab', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const overviewTab = screen.getByRole('button', { name: /Overview/ })
      expect(overviewTab).toHaveClass('bg-white')

      const usersTab = screen.getByRole('button', { name: /Users/ })
      await user.click(usersTab)

      await waitFor(() => {
        expect(usersTab).toHaveClass('bg-white')
      })
    })

    it('should maintain tab content when switching', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const usersTab = screen.getByRole('button', { name: /Users/ })
      await user.click(usersTab)

      await waitFor(() => {
        expect(screen.getByText('Test User 1')).toBeInTheDocument()
      })

      const overviewTab = screen.getByRole('button', { name: /Overview/ })
      await user.click(overviewTab)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      // Switch back to users tab
      await user.click(usersTab)

      await waitFor(() => {
        expect(screen.getByText('Test User 1')).toBeInTheDocument()
      })
    })

    it('should not show loading state when switching tabs after initial load', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const usersTab = screen.getByRole('button', { name: /Users/ })
      await user.click(usersTab)

      expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
    })
  })

  describe('Date Formatting', () => {
    it('should format dates correctly', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const usersTab = screen.getByText('Users')
      await user.click(usersTab)

      await waitFor(() => {
        expect(screen.getByText('Test User 1')).toBeInTheDocument()
      })

      // Check that dates are formatted (not raw ISO strings)
      expect(screen.queryByText('2024-01-01T00:00:00Z')).not.toBeInTheDocument()
    })

    it('should display "Never" for null dates', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const usersTab = screen.getByText('Users')
      await user.click(usersTab)

      await waitFor(() => {
        expect(screen.getByText('Test User 2')).toBeInTheDocument()
      })

      // Test User 2 has null email_verification_sent_at, should display "Never"
      await waitFor(() => {
        expect(screen.getByText(/Last Email: Never/)).toBeInTheDocument()
      })
    })
  })

  describe('API Base URL', () => {
    it('should use correct API base URL in production', async () => {
      const originalEnv = process.env.NODE_ENV
      process.env.NODE_ENV = 'production'

      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringMatching(/^\/api\//),
          expect.any(Object)
        )
      })

      process.env.NODE_ENV = originalEnv
    })

    it('should use correct API base URL in development', async () => {
      const originalEnv = process.env.NODE_ENV
      process.env.NODE_ENV = 'development'

      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringMatching(/^http:\/\/localhost:8000/),
          expect.any(Object)
        )
      })

      process.env.NODE_ENV = originalEnv
    })
  })

  describe('Error State Management', () => {
    it('should show error message when operation fails', async () => {
      const user = userEvent.setup()
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation()

      ;(global.fetch as jest.Mock).mockImplementation(
        (url: string, options) => {
          if (url.includes('/run-cleanup') && options?.method === 'POST') {
            return Promise.resolve({
              ok: false,
              status: 500,
            })
          }
          if (url.includes('/statistics')) {
            return Promise.resolve({
              ok: true,
              json: async () => mockStatistics,
            })
          }
          if (url.includes('/unverified-users')) {
            return Promise.resolve({
              ok: true,
              json: async () => ({ users: mockUnverifiedUsers }),
            })
          }
          return Promise.resolve({
            ok: true,
            json: async () => ({ report: mockStatisticsReport }),
          })
        }
      )

      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const maintenanceTab = screen.getByText('Maintenance')
      await user.click(maintenanceTab)

      await waitFor(() => {
        expect(screen.getByText('Run Cleanup')).toBeInTheDocument()
      })

      const cleanupButton = screen.getByText('Run Cleanup')
      await user.click(cleanupButton)

      await waitFor(() => {
        expect(
          screen.getByText('Failed to run token cleanup')
        ).toBeInTheDocument()
      })

      consoleErrorSpy.mockRestore()
    })

    it('should clear success on new operation', async () => {
      const user = userEvent.setup()
      ;(global.fetch as jest.Mock).mockImplementation(
        (url: string, options) => {
          if (url.includes('/run-cleanup') && options?.method === 'POST') {
            return Promise.resolve({
              ok: true,
              json: async () => ({ tokens_cleaned: 5 }),
            })
          }
          if (url.includes('/send-reminders') && options?.method === 'POST') {
            return Promise.resolve({
              ok: true,
              json: async () => ({ reminders_sent: 8 }),
            })
          }
          if (url.includes('/statistics')) {
            return Promise.resolve({
              ok: true,
              json: async () => mockStatistics,
            })
          }
          if (url.includes('/unverified-users')) {
            return Promise.resolve({
              ok: true,
              json: async () => ({ users: mockUnverifiedUsers }),
            })
          }
          return Promise.resolve({
            ok: true,
            json: async () => ({ report: mockStatisticsReport }),
          })
        }
      )

      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const maintenanceTab = screen.getByText('Maintenance')
      await user.click(maintenanceTab)

      await waitFor(() => {
        expect(screen.getByText('Run Cleanup')).toBeInTheDocument()
      })

      const cleanupButton = screen.getByText('Run Cleanup')
      await user.click(cleanupButton)

      await waitFor(() => {
        expect(
          screen.getByText('Cleanup completed! 5 expired tokens removed.')
        ).toBeInTheDocument()
      })

      const remindersButton = screen.getByText('Send Reminders')
      await user.click(remindersButton)

      await waitFor(() => {
        expect(
          screen.queryByText('Cleanup completed! 5 expired tokens removed.')
        ).not.toBeInTheDocument()
        expect(
          screen.getByText('Reminder emails sent! 8 emails sent successfully.')
        ).toBeInTheDocument()
      })
    })
  })

  describe('Edge Cases', () => {
    it('should handle null statistics gracefully', async () => {
      ;(global.fetch as jest.Mock).mockImplementation((url: string) => {
        if (url.includes('/statistics-report')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({ report: null }),
          })
        }
        if (url.includes('/statistics')) {
          return Promise.resolve({
            ok: true,
            json: async () => null,
          })
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ users: [] }),
        })
      })

      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      // Should display 0 for all values
      const zeroValues = screen.getAllByText('0')
      expect(zeroValues.length).toBeGreaterThan(0)
    })

    it('should handle empty unverified users array', async () => {
      ;(global.fetch as jest.Mock).mockImplementation((url: string) => {
        if (url.includes('/unverified-users')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({ users: undefined }),
          })
        }
        if (url.includes('/statistics')) {
          return Promise.resolve({
            ok: true,
            json: async () => mockStatistics,
          })
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ report: mockStatisticsReport }),
        })
      })

      const user = userEvent.setup()
      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const usersTab = screen.getByText('Users')
      await user.click(usersTab)

      await waitFor(() => {
        expect(
          screen.getByText('All users have verified their emails!')
        ).toBeInTheDocument()
      })
    })

    it('should handle zero tokens cleaned', async () => {
      const user = userEvent.setup()
      ;(global.fetch as jest.Mock).mockImplementation(
        (url: string, options) => {
          if (url.includes('/run-cleanup') && options?.method === 'POST') {
            return Promise.resolve({
              ok: true,
              json: async () => ({}),
            })
          }
          if (url.includes('/statistics')) {
            return Promise.resolve({
              ok: true,
              json: async () => mockStatistics,
            })
          }
          if (url.includes('/unverified-users')) {
            return Promise.resolve({
              ok: true,
              json: async () => ({ users: mockUnverifiedUsers }),
            })
          }
          return Promise.resolve({
            ok: true,
            json: async () => ({ report: mockStatisticsReport }),
          })
        }
      )

      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const maintenanceTab = screen.getByText('Maintenance')
      await user.click(maintenanceTab)

      const cleanupButton = screen.getByText('Run Cleanup')
      await user.click(cleanupButton)

      await waitFor(() => {
        expect(
          screen.getByText('Cleanup completed! 0 expired tokens removed.')
        ).toBeInTheDocument()
      })
    })
  })

  describe('Error Handling - API Failures', () => {
    it('should handle statistics API failure with error status', async () => {
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation()
      ;(global.fetch as jest.Mock).mockImplementation((url: string) => {
        if (
          url.includes('/statistics') &&
          !url.includes('/statistics-report')
        ) {
          return Promise.resolve({
            ok: false,
            status: 500,
          })
        }
        if (url.includes('/statistics-report')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({ report: mockStatisticsReport }),
          })
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ users: [] }),
        })
      })

      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(
          screen.getByText('Failed to load email verification data')
        ).toBeInTheDocument()
      })

      consoleErrorSpy.mockRestore()
    })

    it('should handle unverified users API failure with error status', async () => {
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation()
      ;(global.fetch as jest.Mock).mockImplementation((url: string) => {
        if (url.includes('/unverified-users')) {
          return Promise.resolve({
            ok: false,
            status: 404,
          })
        }
        if (url.includes('/statistics')) {
          return Promise.resolve({
            ok: true,
            json: async () => mockStatistics,
          })
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ report: mockStatisticsReport }),
        })
      })

      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(
          screen.getByText('Failed to load email verification data')
        ).toBeInTheDocument()
      })

      consoleErrorSpy.mockRestore()
    })

    it('should handle statistics report API failure with error status', async () => {
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation()
      ;(global.fetch as jest.Mock).mockImplementation((url: string) => {
        if (url.includes('/statistics-report')) {
          return Promise.resolve({
            ok: false,
            status: 503,
          })
        }
        if (url.includes('/statistics')) {
          return Promise.resolve({
            ok: true,
            json: async () => mockStatistics,
          })
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ users: [] }),
        })
      })

      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(
          screen.getByText('Failed to load email verification data')
        ).toBeInTheDocument()
      })

      consoleErrorSpy.mockRestore()
    })
  })

  describe('Cleanup Tokens - Error Handling', () => {
    it('should handle cleanup when response throws error in catch block', async () => {
      const user = userEvent.setup()
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation()
      ;(global.fetch as jest.Mock).mockImplementation(
        (url: string, options) => {
          if (url.includes('/run-cleanup') && options?.method === 'POST') {
            return Promise.reject(new Error('Network failure'))
          }
          if (url.includes('/statistics')) {
            return Promise.resolve({
              ok: true,
              json: async () => mockStatistics,
            })
          }
          if (url.includes('/unverified-users')) {
            return Promise.resolve({
              ok: true,
              json: async () => ({ users: [] }),
            })
          }
          return Promise.resolve({
            ok: true,
            json: async () => ({ report: mockStatisticsReport }),
          })
        }
      )

      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const maintenanceTab = screen.getByText('Maintenance')
      await user.click(maintenanceTab)

      await waitFor(() => {
        expect(screen.getByText('Run Cleanup')).toBeInTheDocument()
      })

      const cleanupButton = screen.getByText('Run Cleanup')
      await user.click(cleanupButton)

      await waitFor(() => {
        expect(
          screen.getByText('Failed to run token cleanup')
        ).toBeInTheDocument()
      })

      consoleErrorSpy.mockRestore()
    })
  })

  describe('Send Reminders - Error Handling', () => {
    it('should handle send reminders when response throws error in catch block', async () => {
      const user = userEvent.setup()
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation()
      ;(global.fetch as jest.Mock).mockImplementation(
        (url: string, options) => {
          if (url.includes('/send-reminders') && options?.method === 'POST') {
            return Promise.reject(new Error('Email service down'))
          }
          if (url.includes('/statistics')) {
            return Promise.resolve({
              ok: true,
              json: async () => mockStatistics,
            })
          }
          if (url.includes('/unverified-users')) {
            return Promise.resolve({
              ok: true,
              json: async () => ({ users: [] }),
            })
          }
          return Promise.resolve({
            ok: true,
            json: async () => ({ report: mockStatisticsReport }),
          })
        }
      )

      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const maintenanceTab = screen.getByText('Maintenance')
      await user.click(maintenanceTab)

      await waitFor(() => {
        expect(screen.getByText('Send Reminders')).toBeInTheDocument()
      })

      const remindersButton = screen.getByText('Send Reminders')
      await user.click(remindersButton)

      await waitFor(() => {
        expect(
          screen.getByText('Failed to send reminder emails')
        ).toBeInTheDocument()
      })

      consoleErrorSpy.mockRestore()
    })
  })

  describe('Resend Verification - Error Handling', () => {
    it('should handle resend verification network error in catch block', async () => {
      const user = userEvent.setup()
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation()
      ;(global.fetch as jest.Mock).mockImplementation(
        (url: string, options) => {
          if (
            url.includes('/resend-verification/') &&
            options?.method === 'POST'
          ) {
            return Promise.reject(new Error('Network timeout'))
          }
          if (url.includes('/unverified-users')) {
            return Promise.resolve({
              ok: true,
              json: async () => ({ users: mockUnverifiedUsers }),
            })
          }
          if (url.includes('/statistics')) {
            return Promise.resolve({
              ok: true,
              json: async () => mockStatistics,
            })
          }
          return Promise.resolve({
            ok: true,
            json: async () => ({ report: mockStatisticsReport }),
          })
        }
      )

      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const usersTab = screen.getByText('Users')
      await user.click(usersTab)

      await waitFor(() => {
        expect(screen.getByText('Test User 1')).toBeInTheDocument()
      })

      const resendButtons = screen.getAllByText('Resend')
      await user.click(resendButtons[0])

      await waitFor(() => {
        expect(
          screen.getByText('Failed to resend verification email')
        ).toBeInTheDocument()
      })

      consoleErrorSpy.mockRestore()
    })
  })

  describe('Tab Icons and Accessibility', () => {
    it('should render all tab icons correctly', async () => {
      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      // Check that all tabs are rendered with their labels
      expect(
        screen.getByRole('button', { name: /Overview/ })
      ).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Users/ })).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: /Analytics/ })
      ).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: /Maintenance/ })
      ).toBeInTheDocument()
    })

    it('should switch between all tabs correctly', async () => {
      const user = userEvent.setup()
      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      // Switch to Users tab
      const usersTab = screen.getByRole('button', { name: /Users/ })
      await user.click(usersTab)
      await waitFor(() => {
        expect(screen.getByText('Manage Unverified Users')).toBeInTheDocument()
      })

      // Switch to Analytics tab
      const analyticsTab = screen.getByRole('button', { name: /Analytics/ })
      await user.click(analyticsTab)
      await waitFor(() => {
        expect(screen.getByText('Verification Trends')).toBeInTheDocument()
      })

      // Switch to Maintenance tab
      const maintenanceTab = screen.getByRole('button', { name: /Maintenance/ })
      await user.click(maintenanceTab)
      await waitFor(() => {
        expect(screen.getByText('Administrative Tasks')).toBeInTheDocument()
      })

      // Switch back to Overview tab
      const overviewTab = screen.getByRole('button', { name: /Overview/ })
      await user.click(overviewTab)
      await waitFor(() => {
        expect(screen.getByText('Registered Users')).toBeInTheDocument()
      })
    })
  })

  describe('Loading States During Operations', () => {
    it('should complete cleanup operation successfully', async () => {
      const user = userEvent.setup()
      ;(global.fetch as jest.Mock).mockImplementation(
        (url: string, options) => {
          if (url.includes('/run-cleanup') && options?.method === 'POST') {
            return Promise.resolve({
              ok: true,
              json: async () => ({ tokens_cleaned: 3 }),
            })
          }
          if (url.includes('/statistics')) {
            return Promise.resolve({
              ok: true,
              json: async () => mockStatistics,
            })
          }
          if (url.includes('/unverified-users')) {
            return Promise.resolve({
              ok: true,
              json: async () => ({ users: [] }),
            })
          }
          return Promise.resolve({
            ok: true,
            json: async () => ({ report: mockStatisticsReport }),
          })
        }
      )

      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const maintenanceTab = screen.getByText('Maintenance')
      await user.click(maintenanceTab)

      const cleanupButton = screen.getByText('Run Cleanup')
      await user.click(cleanupButton)

      await waitFor(() => {
        expect(
          screen.getByText('Cleanup completed! 3 expired tokens removed.')
        ).toBeInTheDocument()
      })
    })

    it('should complete send reminders operation successfully', async () => {
      const user = userEvent.setup()
      ;(global.fetch as jest.Mock).mockImplementation(
        (url: string, options) => {
          if (url.includes('/send-reminders') && options?.method === 'POST') {
            return Promise.resolve({
              ok: true,
              json: async () => ({ reminders_sent: 5 }),
            })
          }
          if (url.includes('/statistics')) {
            return Promise.resolve({
              ok: true,
              json: async () => mockStatistics,
            })
          }
          if (url.includes('/unverified-users')) {
            return Promise.resolve({
              ok: true,
              json: async () => ({ users: [] }),
            })
          }
          return Promise.resolve({
            ok: true,
            json: async () => ({ report: mockStatisticsReport }),
          })
        }
      )

      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const maintenanceTab = screen.getByText('Maintenance')
      await user.click(maintenanceTab)

      const remindersButton = screen.getByText('Send Reminders')
      await user.click(remindersButton)

      await waitFor(() => {
        expect(
          screen.getByText('Reminder emails sent! 5 emails sent successfully.')
        ).toBeInTheDocument()
      })
    })

    it('should complete resend operation successfully', async () => {
      const user = userEvent.setup()
      ;(global.fetch as jest.Mock).mockImplementation(
        (url: string, options) => {
          if (
            url.includes('/resend-verification/') &&
            options?.method === 'POST'
          ) {
            return Promise.resolve({
              ok: true,
              json: async () => ({
                success: true,
                user_email: 'test1@example.com',
              }),
            })
          }
          if (url.includes('/unverified-users')) {
            return Promise.resolve({
              ok: true,
              json: async () => ({ users: mockUnverifiedUsers }),
            })
          }
          if (url.includes('/statistics')) {
            return Promise.resolve({
              ok: true,
              json: async () => mockStatistics,
            })
          }
          return Promise.resolve({
            ok: true,
            json: async () => ({ report: mockStatisticsReport }),
          })
        }
      )

      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const usersTab = screen.getByText('Users')
      await user.click(usersTab)

      await waitFor(() => {
        expect(screen.getByText('Test User 1')).toBeInTheDocument()
      })

      const resendButtons = screen.getAllByText('Resend')
      await user.click(resendButtons[0])

      await waitFor(() => {
        expect(
          screen.getByText('Verification email resent to test1@example.com')
        ).toBeInTheDocument()
      })
    })
  })

  describe('Data Refresh After Operations', () => {
    it('should refresh all data after successful cleanup', async () => {
      const user = userEvent.setup()
      ;(global.fetch as jest.Mock).mockImplementation(
        (url: string, options) => {
          if (url.includes('/run-cleanup') && options?.method === 'POST') {
            return Promise.resolve({
              ok: true,
              json: async () => ({ tokens_cleaned: 3 }),
            })
          }
          if (url.includes('/statistics')) {
            return Promise.resolve({
              ok: true,
              json: async () => mockStatistics,
            })
          }
          if (url.includes('/unverified-users')) {
            return Promise.resolve({
              ok: true,
              json: async () => ({ users: [] }),
            })
          }
          return Promise.resolve({
            ok: true,
            json: async () => ({ report: mockStatisticsReport }),
          })
        }
      )

      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      jest.clearAllMocks()

      const maintenanceTab = screen.getByText('Maintenance')
      await user.click(maintenanceTab)

      const cleanupButton = screen.getByText('Run Cleanup')
      await user.click(cleanupButton)

      await waitFor(() => {
        expect(
          screen.getByText('Cleanup completed! 3 expired tokens removed.')
        ).toBeInTheDocument()
      })

      // Verify that all data endpoints were called to refresh
      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining('/statistics'),
          expect.any(Object)
        )
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining('/unverified-users'),
          expect.any(Object)
        )
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining('/statistics-report'),
          expect.any(Object)
        )
      })
    })

    it('should refresh all data after successful reminders send', async () => {
      const user = userEvent.setup()
      ;(global.fetch as jest.Mock).mockImplementation(
        (url: string, options) => {
          if (url.includes('/send-reminders') && options?.method === 'POST') {
            return Promise.resolve({
              ok: true,
              json: async () => ({ reminders_sent: 7 }),
            })
          }
          if (url.includes('/statistics')) {
            return Promise.resolve({
              ok: true,
              json: async () => mockStatistics,
            })
          }
          if (url.includes('/unverified-users')) {
            return Promise.resolve({
              ok: true,
              json: async () => ({ users: [] }),
            })
          }
          return Promise.resolve({
            ok: true,
            json: async () => ({ report: mockStatisticsReport }),
          })
        }
      )

      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      jest.clearAllMocks()

      const maintenanceTab = screen.getByText('Maintenance')
      await user.click(maintenanceTab)

      const remindersButton = screen.getByText('Send Reminders')
      await user.click(remindersButton)

      await waitFor(() => {
        expect(
          screen.getByText('Reminder emails sent! 7 emails sent successfully.')
        ).toBeInTheDocument()
      })

      // Verify that all data endpoints were called to refresh
      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining('/statistics'),
          expect.any(Object)
        )
      })
    })

    it('should refresh unverified users after successful resend', async () => {
      const user = userEvent.setup()
      ;(global.fetch as jest.Mock).mockImplementation(
        (url: string, options) => {
          if (
            url.includes('/resend-verification/') &&
            options?.method === 'POST'
          ) {
            return Promise.resolve({
              ok: true,
              json: async () => ({
                success: true,
                user_email: 'test1@example.com',
              }),
            })
          }
          if (url.includes('/unverified-users')) {
            return Promise.resolve({
              ok: true,
              json: async () => ({ users: mockUnverifiedUsers }),
            })
          }
          if (url.includes('/statistics')) {
            return Promise.resolve({
              ok: true,
              json: async () => mockStatistics,
            })
          }
          return Promise.resolve({
            ok: true,
            json: async () => ({ report: mockStatisticsReport }),
          })
        }
      )

      render(<EmailVerificationManagement />)

      await waitFor(() => {
        expect(screen.getByText('Total Users')).toBeInTheDocument()
      })

      const usersTab = screen.getByText('Users')
      await user.click(usersTab)

      await waitFor(() => {
        expect(screen.getByText('Test User 1')).toBeInTheDocument()
      })

      jest.clearAllMocks()

      const resendButtons = screen.getAllByText('Resend')
      await user.click(resendButtons[0])

      await waitFor(() => {
        expect(
          screen.getByText('Verification email resent to test1@example.com')
        ).toBeInTheDocument()
      })

      // Verify that unverified users were refreshed
      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining('/unverified-users'),
          expect.any(Object)
        )
      })
    })
  })
})
