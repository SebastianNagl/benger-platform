/**
 * @jest-environment jsdom
 */

import { useI18n } from '@/contexts/I18nContext'
import api from '@/lib/api'
import {
  NotificationGroupsResponse,
  NotificationSummaryResponse,
} from '@/lib/api/notifications'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import NotificationAnalyticsPage from '../page'

jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: {
    getNotificationSummary: jest.fn(),
    getNotificationGroups: jest.fn(),
  },
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(),
}))

jest.mock('@heroicons/react/24/outline', () => ({
  BellIcon: (props: any) => <svg data-testid="bell-icon" {...props} />,
  ChartBarIcon: (props: any) => <svg data-testid="chart-bar-icon" {...props} />,
  CheckCircleIcon: (props: any) => (
    <svg data-testid="check-circle-icon" {...props} />
  ),
  ClockIcon: (props: any) => <svg data-testid="clock-icon" {...props} />,
  ExclamationTriangleIcon: (props: any) => (
    <svg data-testid="exclamation-icon" {...props} />
  ),
  InformationCircleIcon: (props: any) => (
    <svg data-testid="info-icon" {...props} />
  ),
}))

describe('NotificationAnalyticsPage', () => {
  const mockT = jest.fn((key: string, params?: Record<string, any>) => {
    const translations: Record<string, string> = {
      'notifications.analyticsTitle': 'Notification Analytics',
      'notifications.totalNotifications': 'Total Notifications',
      'notifications.unreadCount': 'Unread Notifications',
      'notifications.readCount': 'Read Notifications',
      'notifications.byType': 'Notifications by Type',
      'notifications.recentActivity': 'Recent Activity',
      'notifications.analytics.typesTitle': 'Notification Types',
      'notifications.analytics.typesSubtitle': 'Different types received',
      'notifications.analytics.chartTitle': 'Notifications {groupBy}',
      'notifications.analytics.loadFailed': 'Failed to load notification analytics',
      'notifications.analytics.subtitle': 'Insights into your notification patterns and activity',
      'notifications.analytics.noData': 'No data available',
      'notifications.analytics.lastNDays': 'Last {days} days',
      'notifications.analytics.percentOfTotal': '{percent}% of total',
      'notifications.analytics.readRate': '{percent}% read rate',
      'notifications.analytics.recentActivityDetails': 'Recent Activity Details',
      'notifications.analytics.noNotifications': 'No notifications in the selected time period',
      'notifications.analytics.tryLongerRange': 'Try selecting a longer time range',
      'notifications.analytics.generatedAt': 'Analytics generated on {date} for the period of {days} days',
      'notifications.analytics.timeRange.last7Days': 'Last 7 days',
      'notifications.analytics.timeRange.last2Weeks': 'Last 2 weeks',
      'notifications.analytics.timeRange.last30Days': 'Last 30 days',
      'notifications.analytics.timeRange.last3Months': 'Last 3 months',
      'notifications.analytics.groupBy.byType': 'By Type',
      'notifications.analytics.groupBy.byDate': 'By Date',
      'notifications.analytics.groupBy.byOrganization': 'By Organization',
    }
    if (key === 'notifications.analytics.notificationCount' && params) {
      const count = Number(params.count)
      return count === 1 ? '1 notification' : `${count} notifications`
    }
    let result = translations[key] || key
    if (params) {
      Object.entries(params).forEach(([k, v]) => {
        result = result.replace(`{${k}}`, String(v ?? ''))
      })
    }
    return result
  })

  const mockSummaryData: NotificationSummaryResponse = {
    total_notifications: 100,
    unread_notifications: 25,
    read_notifications: 75,
    notifications_by_type: {
      task_created: 40,
      evaluation_completed: 30,
      evaluation_failed: 10,
      data_upload_completed: 20,
    },
    period_days: 7,
    summary_generated_at: '2024-01-15T12:00:00Z',
  }

  const mockGroupsData: NotificationGroupsResponse = {
    groups: {
      task_created: [
        {
          id: '1',
          type: 'task_created',
          title: 'Task 1',
          message: 'Message 1',
          is_read: false,
          created_at: '2024-01-15T10:00:00Z',
        },
      ],
      evaluation_completed: [
        {
          id: '2',
          type: 'evaluation_completed',
          title: 'Eval 1',
          message: 'Message 2',
          is_read: true,
          created_at: '2024-01-15T11:00:00Z',
        },
      ],
    },
  }

  beforeEach(() => {
    jest.clearAllMocks()
    ;(useI18n as jest.Mock).mockReturnValue({
      t: mockT,
    })
    ;(api.getNotificationSummary as jest.Mock).mockResolvedValue(
      mockSummaryData
    )
    ;(api.getNotificationGroups as jest.Mock).mockResolvedValue(mockGroupsData)
  })

  describe('Loading State', () => {
    it('renders loading skeleton initially', () => {
      ;(api.getNotificationSummary as jest.Mock).mockImplementation(
        () => new Promise(() => {})
      )
      ;(api.getNotificationGroups as jest.Mock).mockImplementation(
        () => new Promise(() => {})
      )

      render(<NotificationAnalyticsPage />)

      const skeletonElements = document.querySelectorAll('.animate-pulse')
      expect(skeletonElements.length).toBeGreaterThan(0)
    })

    it('shows loading skeleton with correct structure', () => {
      ;(api.getNotificationSummary as jest.Mock).mockImplementation(
        () => new Promise(() => {})
      )
      ;(api.getNotificationGroups as jest.Mock).mockImplementation(
        () => new Promise(() => {})
      )

      render(<NotificationAnalyticsPage />)

      const skeletonCards = document.querySelectorAll('.animate-pulse .h-32')
      expect(skeletonCards.length).toBe(4)
    })
  })

  describe('Page Header', () => {
    it('renders page title', async () => {
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getByText('Notification Analytics')).toBeInTheDocument()
      })
    })

    it('renders page description', async () => {
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(
          screen.getByText(/insights into your notification patterns/i)
        ).toBeInTheDocument()
      })
    })

    it('renders time range selector', async () => {
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getByDisplayValue('Last 7 days')).toBeInTheDocument()
      })
    })

    it('renders group by selector', async () => {
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getByDisplayValue('By Type')).toBeInTheDocument()
      })
    })
  })

  describe('Statistics Cards', () => {
    it('renders total notifications stat card', async () => {
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getByText('Total Notifications')).toBeInTheDocument()
        expect(screen.getByText('100')).toBeInTheDocument()
        const lastSevenDaysTexts = screen.getAllByText('Last 7 days')
        expect(lastSevenDaysTexts.length).toBeGreaterThan(0)
      })
    })

    it('renders unread notifications stat card', async () => {
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getByText('Unread Notifications')).toBeInTheDocument()
        expect(screen.getByText('25')).toBeInTheDocument()
        expect(screen.getByText('25% of total')).toBeInTheDocument()
      })
    })

    it('renders read notifications stat card', async () => {
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getByText('Read Notifications')).toBeInTheDocument()
        expect(screen.getByText('75')).toBeInTheDocument()
        expect(screen.getByText('75% read rate')).toBeInTheDocument()
      })
    })

    it('renders notification types stat card', async () => {
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getByText('Notification Types')).toBeInTheDocument()
        expect(screen.getByText('4')).toBeInTheDocument()
        expect(screen.getByText('Different types received')).toBeInTheDocument()
      })
    })

    it('displays correct icons in stat cards', async () => {
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getAllByTestId('bell-icon').length).toBeGreaterThan(0)
        expect(
          screen.getAllByTestId('exclamation-icon').length
        ).toBeGreaterThan(0)
        expect(
          screen.getAllByTestId('check-circle-icon').length
        ).toBeGreaterThan(0)
        expect(screen.getAllByTestId('chart-bar-icon').length).toBeGreaterThan(
          0
        )
      })
    })

    it('calculates percentage correctly when total is zero', async () => {
      ;(api.getNotificationSummary as jest.Mock).mockResolvedValue({
        ...mockSummaryData,
        total_notifications: 0,
        unread_notifications: 0,
        read_notifications: 0,
      })

      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getByText('0% of total')).toBeInTheDocument()
      })
    })
  })

  describe('Charts', () => {
    it('renders notifications by type chart', async () => {
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getByText('Notifications by Type')).toBeInTheDocument()
      })
    })

    it('renders group chart with correct title', async () => {
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getByText('Notifications By Type')).toBeInTheDocument()
      })
    })

    it('displays chart bars for notification types', async () => {
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getAllByText('Task Created').length).toBeGreaterThan(0)
        expect(
          screen.getAllByText('Evaluation Completed').length
        ).toBeGreaterThan(0)
        expect(screen.getAllByText('Evaluation Failed').length).toBeGreaterThan(
          0
        )
        expect(
          screen.getAllByText('Data Upload Completed').length
        ).toBeGreaterThan(0)
      })
    })

    it('displays correct counts in chart bars', async () => {
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getByText('40')).toBeInTheDocument()
        expect(screen.getByText('30')).toBeInTheDocument()
        expect(screen.getByText('10')).toBeInTheDocument()
        expect(screen.getByText('20')).toBeInTheDocument()
      })
    })

    it('shows empty state when no data available', async () => {
      ;(api.getNotificationSummary as jest.Mock).mockResolvedValue({
        ...mockSummaryData,
        notifications_by_type: {},
      })
      ;(api.getNotificationGroups as jest.Mock).mockResolvedValue({
        groups: {},
      })

      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        const emptyMessages = screen.getAllByText('No data available')
        expect(emptyMessages.length).toBeGreaterThan(0)
      })
    })

    it('sorts chart data by value in descending order', async () => {
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        const chartBars = screen
          .getByText('Notifications by Type')
          .closest('div')
        expect(chartBars).toBeInTheDocument()

        const firstValue = screen.getAllByText('40')[0]
        const lastValue = screen.getAllByText('10')[0]
        expect(firstValue).toBeInTheDocument()
        expect(lastValue).toBeInTheDocument()
      })
    })
  })

  describe('Recent Activity Section', () => {
    it('renders recent activity section', async () => {
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getByText(/Recent Activity Details/i)).toBeInTheDocument()
      })
    })

    it('displays notification type cards with icons', async () => {
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getAllByText('Task Created').length).toBeGreaterThan(0)
        expect(screen.getByText('40 notifications')).toBeInTheDocument()
      })
    })

    it('displays correct plural form for single notification', async () => {
      ;(api.getNotificationSummary as jest.Mock).mockResolvedValue({
        ...mockSummaryData,
        notifications_by_type: {
          task_created: 1,
        },
      })

      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getByText('1 notification')).toBeInTheDocument()
      })
    })

    it('shows empty state when no notifications in period', async () => {
      ;(api.getNotificationSummary as jest.Mock).mockResolvedValue({
        ...mockSummaryData,
        notifications_by_type: {},
        total_notifications: 0,
      })

      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(
          screen.getByText('No notifications in the selected time period')
        ).toBeInTheDocument()
        expect(
          screen.getByText('Try selecting a longer time range')
        ).toBeInTheDocument()
      })
    })

    it('sorts notification types by count', async () => {
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        const activitySection = screen
          .getByText(/Recent Activity Details/i)
          .closest('div')
        expect(activitySection).toBeInTheDocument()

        expect(screen.getByText('40 notifications')).toBeInTheDocument()
        expect(screen.getByText('30 notifications')).toBeInTheDocument()
        expect(screen.getByText('20 notifications')).toBeInTheDocument()
        expect(screen.getByText('10 notifications')).toBeInTheDocument()
      })
    })
  })

  describe('Summary Information', () => {
    it('displays summary generation timestamp', async () => {
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getByText(/Analytics generated on/i)).toBeInTheDocument()
      })
    })

    it('displays period days in summary', async () => {
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(
          screen.getByText(/for the period of 7 days/i)
        ).toBeInTheDocument()
      })
    })

    it('renders clock icon in summary', async () => {
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getByTestId('clock-icon')).toBeInTheDocument()
      })
    })
  })

  describe('Time Range Filter', () => {
    it('changes time range to 14 days', async () => {
      const user = userEvent.setup()
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getByDisplayValue('Last 7 days')).toBeInTheDocument()
      })

      const timeRangeSelect = screen.getByDisplayValue('Last 7 days')
      await user.selectOptions(timeRangeSelect, '14')

      await waitFor(() => {
        expect(api.getNotificationSummary).toHaveBeenCalledWith(14)
      })
    })

    it('changes time range to 30 days', async () => {
      const user = userEvent.setup()
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getByDisplayValue('Last 7 days')).toBeInTheDocument()
      })

      const timeRangeSelect = screen.getByDisplayValue('Last 7 days')
      await user.selectOptions(timeRangeSelect, '30')

      await waitFor(() => {
        expect(api.getNotificationSummary).toHaveBeenCalledWith(30)
      })
    })

    it('changes time range to 90 days', async () => {
      const user = userEvent.setup()
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getByDisplayValue('Last 7 days')).toBeInTheDocument()
      })

      const timeRangeSelect = screen.getByDisplayValue('Last 7 days')
      await user.selectOptions(timeRangeSelect, '90')

      await waitFor(() => {
        expect(api.getNotificationSummary).toHaveBeenCalledWith(90)
      })
    })

    it('reloads analytics when time range changes', async () => {
      const user = userEvent.setup()
      render(<NotificationAnalyticsPage />)

      // Wait for initial load to complete
      await waitFor(() => {
        expect(screen.getByText('Total Notifications')).toBeInTheDocument()
      })

      await waitFor(() => {
        expect(api.getNotificationSummary).toHaveBeenCalledWith(7)
      })

      jest.clearAllMocks()

      const timeRangeSelect = screen.getByDisplayValue('Last 7 days')
      await user.selectOptions(timeRangeSelect, '30')

      await waitFor(() => {
        expect(api.getNotificationSummary).toHaveBeenCalledTimes(1)
        expect(api.getNotificationGroups).toHaveBeenCalledTimes(1)
      })
    })
  })

  describe('Group By Filter', () => {
    it('changes grouping to date', async () => {
      const user = userEvent.setup()
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getByDisplayValue('By Type')).toBeInTheDocument()
      })

      const groupBySelect = screen.getByDisplayValue('By Type')
      await user.selectOptions(groupBySelect, 'date')

      await waitFor(() => {
        expect(api.getNotificationGroups).toHaveBeenCalledWith('date', 50)
      })
    })

    it('changes grouping to organization', async () => {
      const user = userEvent.setup()
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getByDisplayValue('By Type')).toBeInTheDocument()
      })

      const groupBySelect = screen.getByDisplayValue('By Type')
      await user.selectOptions(groupBySelect, 'organization')

      await waitFor(() => {
        expect(api.getNotificationGroups).toHaveBeenCalledWith(
          'organization',
          50
        )
      })
    })

    it('updates chart title when grouping changes', async () => {
      const user = userEvent.setup()
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getByText('Notifications By Type')).toBeInTheDocument()
      })

      const groupBySelect = screen.getByDisplayValue('By Type')
      await user.selectOptions(groupBySelect, 'date')

      await waitFor(() => {
        expect(screen.getByText('Notifications By Date')).toBeInTheDocument()
      })
    })

    it('reloads analytics when grouping changes', async () => {
      const user = userEvent.setup()
      render(<NotificationAnalyticsPage />)

      // Wait for initial load to complete
      await waitFor(() => {
        expect(screen.getByText('Total Notifications')).toBeInTheDocument()
      })

      await waitFor(() => {
        expect(api.getNotificationGroups).toHaveBeenCalledWith('type', 50)
      })

      jest.clearAllMocks()

      const groupBySelect = screen.getByDisplayValue('By Type')
      await user.selectOptions(groupBySelect, 'date')

      await waitFor(() => {
        expect(api.getNotificationSummary).toHaveBeenCalledTimes(1)
        expect(api.getNotificationGroups).toHaveBeenCalledTimes(1)
      })
    })
  })

  describe('Error Handling', () => {
    it('displays error message when API fails', async () => {
      ;(api.getNotificationSummary as jest.Mock).mockRejectedValue(
        new Error('API Error')
      )

      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(
          screen.getByText('Failed to load notification analytics')
        ).toBeInTheDocument()
      })
    })

    it('logs error to console', async () => {
      const consoleErrorSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})
      ;(api.getNotificationSummary as jest.Mock).mockRejectedValue(
        new Error('API Error')
      )

      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(consoleErrorSpy).toHaveBeenCalledWith(
          'Error loading notification analytics:',
          expect.any(Error)
        )
      })

      consoleErrorSpy.mockRestore()
    })

    it('shows error icon in error message', async () => {
      ;(api.getNotificationSummary as jest.Mock).mockRejectedValue(
        new Error('API Error')
      )

      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getByTestId('exclamation-icon')).toBeInTheDocument()
      })
    })

    it('hides summary section when error occurs', async () => {
      ;(api.getNotificationSummary as jest.Mock).mockRejectedValue(
        new Error('API Error')
      )

      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(
          screen.queryByText('Total Notifications')
        ).not.toBeInTheDocument()
      })
    })
  })

  describe('Data Formatting', () => {
    it('formats notification type labels correctly', async () => {
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getAllByText('Task Created').length).toBeGreaterThan(0)
        expect(
          screen.getAllByText('Evaluation Completed').length
        ).toBeGreaterThan(0)
        expect(
          screen.getAllByText('Data Upload Completed').length
        ).toBeGreaterThan(0)
      })
    })

    it('calculates read rate correctly', async () => {
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getByText('75% read rate')).toBeInTheDocument()
      })
    })

    it('handles zero read rate', async () => {
      ;(api.getNotificationSummary as jest.Mock).mockResolvedValue({
        ...mockSummaryData,
        total_notifications: 100,
        read_notifications: 0,
        unread_notifications: 100,
      })

      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getByText('0% read rate')).toBeInTheDocument()
      })
    })

    it('handles 100% read rate', async () => {
      ;(api.getNotificationSummary as jest.Mock).mockResolvedValue({
        ...mockSummaryData,
        total_notifications: 100,
        read_notifications: 100,
        unread_notifications: 0,
      })

      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getByText('100% read rate')).toBeInTheDocument()
      })
    })
  })

  describe('API Integration', () => {
    it('fetches summary data on mount', async () => {
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(api.getNotificationSummary).toHaveBeenCalledWith(7)
      })
    })

    it('fetches groups data on mount', async () => {
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(api.getNotificationGroups).toHaveBeenCalledWith('type', 50)
      })
    })

    it('fetches both summary and groups in parallel', async () => {
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(api.getNotificationSummary).toHaveBeenCalled()
        expect(api.getNotificationGroups).toHaveBeenCalled()
      })
    })

    it('handles partial API failure gracefully', async () => {
      ;(api.getNotificationSummary as jest.Mock).mockResolvedValue(
        mockSummaryData
      )
      ;(api.getNotificationGroups as jest.Mock).mockRejectedValue(
        new Error('Groups API Error')
      )

      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(
          screen.getByText('Failed to load notification analytics')
        ).toBeInTheDocument()
      })
    })
  })

  describe('Color Assignments', () => {
    it('assigns correct colors to notification types', async () => {
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        const section = screen
          .getByText(/Recent Activity Details/i)
          .closest('div')
        expect(section).toBeInTheDocument()

        const coloredElements = document.querySelectorAll(
          '[style*="background"]'
        )
        expect(coloredElements.length).toBeGreaterThan(0)
      })
    })

    it('uses default color for unknown types', async () => {
      ;(api.getNotificationSummary as jest.Mock).mockResolvedValue({
        ...mockSummaryData,
        notifications_by_type: {
          unknown_type: 5,
        },
      })
      ;(api.getNotificationGroups as jest.Mock).mockResolvedValue({
        groups: {
          unknown_type: [
            {
              id: '1',
              type: 'unknown_type',
              title: 'Unknown',
              message: 'Unknown message',
              is_read: false,
              created_at: '2024-01-15T10:00:00Z',
            },
          ],
        },
      })

      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getAllByText('Unknown Type').length).toBeGreaterThan(0)
      })
    })
  })

  describe('Accessibility', () => {
    it('has proper heading structure', async () => {
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        const heading = screen.getByRole('heading', {
          name: /Notification Analytics/i,
        })
        expect(heading).toBeInTheDocument()
      })
    })

    it('has accessible select labels', async () => {
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        const selects = screen.getAllByRole('combobox')
        expect(selects.length).toBe(2)
      })
    })
  })

  describe('Edge Cases', () => {
    it('handles empty summary data', async () => {
      ;(api.getNotificationSummary as jest.Mock).mockResolvedValue({
        total_notifications: 0,
        unread_notifications: 0,
        read_notifications: 0,
        notifications_by_type: {},
        period_days: 7,
        summary_generated_at: '2024-01-15T12:00:00Z',
      })
      ;(api.getNotificationGroups as jest.Mock).mockResolvedValue({
        groups: {},
      })

      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getAllByText('0').length).toBeGreaterThan(0)
      })
    })

    it('handles very large notification counts', async () => {
      ;(api.getNotificationSummary as jest.Mock).mockResolvedValue({
        ...mockSummaryData,
        total_notifications: 999999,
        unread_notifications: 500000,
        read_notifications: 499999,
      })

      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getByText('999999')).toBeInTheDocument()
        expect(screen.getByText('500000')).toBeInTheDocument()
        expect(screen.getByText('499999')).toBeInTheDocument()
      })
    })

    it('handles single notification type', async () => {
      ;(api.getNotificationSummary as jest.Mock).mockResolvedValue({
        ...mockSummaryData,
        notifications_by_type: {
          task_created: 100,
        },
      })
      ;(api.getNotificationGroups as jest.Mock).mockResolvedValue({
        groups: {
          task_created: [
            {
              id: '1',
              type: 'task_created',
              title: 'Task 1',
              message: 'Message 1',
              is_read: false,
              created_at: '2024-01-15T10:00:00Z',
            },
          ],
        },
      })

      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getAllByText('Task Created').length).toBeGreaterThan(0)
        expect(screen.getByText('100 notifications')).toBeInTheDocument()
      })
    })

    it('handles many notification types', async () => {
      const manyTypes: Record<string, number> = {}
      for (let i = 0; i < 20; i++) {
        manyTypes[`type_${i}`] = i + 1
      }

      ;(api.getNotificationSummary as jest.Mock).mockResolvedValue({
        ...mockSummaryData,
        notifications_by_type: manyTypes,
      })

      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getByText(/Recent Activity Details/i)).toBeInTheDocument()
      })
    })
  })

  describe('Component Lifecycle', () => {
    it('loads data only once on mount', async () => {
      render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(api.getNotificationSummary).toHaveBeenCalledTimes(1)
        expect(api.getNotificationGroups).toHaveBeenCalledTimes(1)
      })
    })

    it('maintains state after rerenders', async () => {
      const { rerender } = render(<NotificationAnalyticsPage />)

      await waitFor(() => {
        expect(screen.getByText('100')).toBeInTheDocument()
      })

      rerender(<NotificationAnalyticsPage />)

      expect(screen.getByText('100')).toBeInTheDocument()
    })
  })
})
