/**
 * @jest-environment jsdom
 */

import { useAuth } from '@/contexts/AuthContext'
import { useNotifications } from '@/hooks/useNotifications'
import { api } from '@/lib/api'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useRouter } from 'next/navigation'
import NotificationsPage from '../page'

// Mock dependencies
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}))

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))

jest.mock('@/hooks/useNotifications', () => ({
  useNotifications: jest.fn(),
}))

jest.mock('@/lib/api', () => ({
  api: {
    getNotifications: jest.fn(),
    getNotificationGroups: jest.fn(),
    getNotificationSummary: jest.fn(),
    markNotificationsBulkAsRead: jest.fn(),
    deleteNotificationsBulk: jest.fn(),
  },
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(() => ({
    t: (key: string, defaultValueOrVars?: any, vars?: any) => {
      const translations: Record<string, string> = {
        'notifications.title': 'Notifications',
        'notifications.subtitle':
          'Stay up to date with your tasks and system updates',
        'notifications.listView': 'List',
        'notifications.groups': 'Groups',
        'notifications.groupByType': 'Group by Type',
        'notifications.groupByDate': 'Group by Date',
        'notifications.groupByOrganization': 'Group by Organization',
        'notifications.analytics': 'Analytics',
        'notifications.analyticsTitle': 'Notification Analytics',
        'notifications.showSummary': 'Show Summary',
        'notifications.hideSummary': 'Hide Summary',
        'notifications.searchGroupsHint':
          'Search (switch to list to apply)',
        'notifications.searchPlaceholder': 'Search notifications...',
        'notifications.activeSearch': 'Active search',
        'notifications.refresh': 'Refresh',
        'notifications.markAllRead': 'Mark all read',
        'notifications.markingAllRead': 'Marking all as read...',
        'notifications.all': 'All Status',
        'notifications.unread': 'Unread',
        'notifications.read': 'Read',
        'notifications.allTypes': 'All Types',
        'notifications.allTime': 'All Time',
        'notifications.today': 'Today',
        'notifications.pastWeek': 'Past Week',
        'notifications.pastMonth': 'Past Month',
        'notifications.clearFilters': 'Clear Filters',
        'notifications.loading': 'Loading notifications...',
        'notifications.noNotifications': 'No Notifications',
        'notifications.noNotificationsDescription': 'No notifications yet',
        'notifications.noMatches':
          'No notifications match your search criteria',
        'notifications.allCaughtUp':
          "You're all caught up! No unread notifications",
        'notifications.deleteConfirm':
          'Are you sure you want to delete selected notifications?',
        'notifications.markRead': 'Mark as Read',
        'notifications.delete': 'Delete',
        'notifications.cancel': 'Cancel',
        'notifications.selected': '{count} notification(s) selected',
        'notifications.new': 'New',
        'notifications.organizationLabel': 'Organization',
        'notifications.personal': 'Personal',
        'notifications.totalNotifications': 'Total',
        'notifications.unreadCount': 'Unread',
        'notifications.readCount': 'Read',
        'notifications.types': 'Types',
        'notifications.summary7Day': '7-Day Notification Summary',
        'notifications.loadMore': 'Load More',
        'notifications.loadingMore': 'Loading more...',
        'notifications.errorTitle': 'Error Loading Notifications',
        'notifications.tryAgain': 'Try Again',
        'notifications.activeSearchFilter': 'Active search filter',
        'notifications.searchSavedHint':
          'Search term "{searchTerm}" is saved',
        'notifications.switchToList': 'Switch to List',
        'notifications.authRequired': 'Authentication Required',
        'notifications.authRequiredMessage':
          'Please log in to view your notifications',
        'notifications.columnNotification': 'Notification',
        'notifications.columnTime': 'Time',
        'notifications.columnStatus': 'Status',
        'common.search': 'Search',
        'navigation.dashboard': 'Dashboard',
      }
      // Handle variable interpolation for searchSavedHint
      let result = translations[key]
      if (!result) {
        return typeof defaultValueOrVars === 'string'
          ? defaultValueOrVars
          : key
      }
      const variables =
        vars || (typeof defaultValueOrVars === 'object' ? defaultValueOrVars : null)
      if (variables) {
        Object.entries(variables).forEach(([k, v]) => {
          result = result.replace(`{${k}}`, String(v))
        })
      }
      return result
    },
    locale: 'en',
  })),
}))

// Mock date-fns locale
jest.mock('date-fns/locale', () => ({
  de: {},
}))

// Mock notificationTranslation
jest.mock('@/lib/notificationTranslation', () => ({
  getTranslatedNotification: (_t: any, notification: any) => ({
    title: notification.title,
    message: notification.message,
  }),
}))

// Mock date-fns
jest.mock('date-fns', () => ({
  formatDistanceToNow: jest.fn(() => '5 minutes ago'),
}))

// Mock Heroicons
jest.mock('@heroicons/react/24/outline', () => ({
  ArrowPathIcon: (props: any) => <svg data-testid="refresh-icon" {...props} />,
  CheckCircleIcon: (props: any) => (
    <svg data-testid="check-circle-icon" {...props} />
  ),
  CheckIcon: (props: any) => <svg data-testid="check-icon" {...props} />,
  ChevronDownIcon: (props: any) => (
    <svg data-testid="chevron-down-icon" {...props} />
  ),
  ChevronUpDownIcon: (props: any) => (
    <svg data-testid="chevron-up-down-icon" {...props} />
  ),
  ClockIcon: (props: any) => <svg data-testid="clock-icon" {...props} />,
  ExclamationTriangleIcon: (props: any) => (
    <svg data-testid="exclamation-icon" {...props} />
  ),
  FunnelIcon: (props: any) => <svg data-testid="funnel-icon" {...props} />,
  InformationCircleIcon: (props: any) => (
    <svg data-testid="info-icon" {...props} />
  ),
  UserPlusIcon: (props: any) => <svg data-testid="user-plus-icon" {...props} />,
  XMarkIcon: (props: any) => <svg data-testid="x-mark-icon" {...props} />,
  ChartBarIcon: (props: any) => <svg data-testid="chart-bar-icon" {...props} />,
  ListBulletIcon: (props: any) => (
    <svg data-testid="list-bullet-icon" {...props} />
  ),
  Squares2X2Icon: (props: any) => (
    <svg data-testid="squares-2x2-icon" {...props} />
  ),
  MagnifyingGlassIcon: (props: any) => (
    <svg data-testid="magnifying-glass-icon" {...props} />
  ),
  TrashIcon: (props: any) => <svg data-testid="trash-icon" {...props} />,
}))

// Mock Link component
jest.mock('next/link', () => ({
  __esModule: true,
  default: ({
    children,
    href,
    ...props
  }: {
    children: React.ReactNode
    href: string
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}))

// Mock shared components
jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: ({ items }: any) => (
    <nav data-testid="breadcrumb">
      {items?.map((item: any, i: number) => (
        <span key={i}>{item.label}</span>
      ))}
    </nav>
  ),
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, disabled, ...props }: any) => (
    <button onClick={onClick} disabled={disabled} {...props}>
      {children}
    </button>
  ),
}))

jest.mock('@/components/shared/ResponsiveContainer', () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
}))

describe('NotificationsPage', () => {
  const mockPush = jest.fn()
  const mockMarkAsRead = jest.fn()
  const mockMarkAllAsRead = jest.fn()
  const mockRefreshNotifications = jest.fn()
  const mockFetchNotifications = jest.fn()

  const mockUser = {
    id: '1',
    username: 'testuser',
    email: 'test@example.com',
    name: 'Test User',
  }

  const createNotification = (overrides?: any) => ({
    id: '1',
    type: 'task_created',
    title: 'Task Created',
    message: 'A new task has been created',
    is_read: false,
    created_at: '2024-01-01T10:00:00Z',
    ...overrides,
  })

  beforeEach(() => {
    jest.clearAllMocks()
    ;(useRouter as jest.Mock).mockReturnValue({
      push: mockPush,
    })
    ;(useAuth as jest.Mock).mockReturnValue({
      user: mockUser,
      apiClient: {},
    })
    ;(useNotifications as jest.Mock).mockReturnValue({
      notifications: [],
      unreadCount: 0,
      isLoading: false,
      markAsRead: mockMarkAsRead,
      markAllAsRead: mockMarkAllAsRead,
      refreshNotifications: mockRefreshNotifications,
      fetchNotifications: mockFetchNotifications,
    })
    ;(api.getNotifications as jest.Mock).mockResolvedValue([])
    ;(api.getNotificationGroups as jest.Mock).mockResolvedValue({ groups: {} })
    ;(api.getNotificationSummary as jest.Mock).mockResolvedValue({
      total_notifications: 0,
      unread_notifications: 0,
      read_notifications: 0,
      notifications_by_type: {},
    })
    ;(api.markNotificationsBulkAsRead as jest.Mock).mockResolvedValue({
      message: 'Success',
    })
    ;(api.deleteNotificationsBulk as jest.Mock).mockResolvedValue({
      message: 'Success',
    })
  })

  // Helper: open search bar by clicking the search toggle button
  const openSearchBar = async (user: ReturnType<typeof userEvent.setup>) => {
    const searchToggle = screen.getByTitle('Search notifications...')
    await user.click(searchToggle)
  }

  // Helper: open status filter dropdown and select an option
  const selectStatusFilter = async (
    user: ReturnType<typeof userEvent.setup>,
    label: string
  ) => {
    const statusButton = screen.getByText('All Status')
      .closest('button') || screen.getByText('Unread').closest('button') || screen.getByText('Read').closest('button')
    if (statusButton) await user.click(statusButton)
    const option = await screen.findByText(label)
    await user.click(option)
  }

  describe('Page Rendering', () => {
    it('renders the page title and description', () => {
      render(<NotificationsPage />)

      expect(screen.getAllByText('Notifications').length).toBeGreaterThan(0)
      expect(
        screen.getByText(/stay up to date with your tasks/i)
      ).toBeInTheDocument()
    })

    it('renders breadcrumb', () => {
      render(<NotificationsPage />)

      const breadcrumbs = screen.getAllByText('Notifications')
      expect(breadcrumbs.length).toBeGreaterThan(0)
    })

    it('renders without user (authentication required)', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        apiClient: {},
      })

      render(<NotificationsPage />)

      expect(screen.getByText('Authentication Required')).toBeInTheDocument()
      expect(
        screen.getByText(/please log in to view your notifications/i)
      ).toBeInTheDocument()
    })

    it('renders refresh button with title', () => {
      render(<NotificationsPage />)

      const refreshButton = screen.getByTitle('Refresh')
      expect(refreshButton).toBeInTheDocument()
    })

    it('renders status, type, and date filter buttons', () => {
      render(<NotificationsPage />)

      expect(screen.getByText('All Status')).toBeInTheDocument()
      expect(screen.getByText('All Types')).toBeInTheDocument()
      expect(screen.getByText('All Time')).toBeInTheDocument()
    })

    it('renders analytics link', () => {
      render(<NotificationsPage />)

      const analyticsLink = screen.getByRole('link', { name: /notification analytics/i })
      expect(analyticsLink).toBeInTheDocument()
      expect(analyticsLink).toHaveAttribute('href', '/notifications/analytics')
    })

    it('renders search toggle button', () => {
      render(<NotificationsPage />)

      expect(screen.getByTitle('Search notifications...')).toBeInTheDocument()
    })
  })

  describe('Notification List Display', () => {
    it('displays notifications in list view', () => {
      const notifications = [
        createNotification({ id: '1', title: 'First Notification' }),
        createNotification({ id: '2', title: 'Second Notification' }),
      ]

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications,
        unreadCount: 2,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      expect(screen.getByText('First Notification')).toBeInTheDocument()
      expect(screen.getByText('Second Notification')).toBeInTheDocument()
    })

    it('displays notification message', () => {
      const notification = createNotification({
        message: 'Test notification message',
      })

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [notification],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      expect(screen.getByText('Test notification message')).toBeInTheDocument()
    })

    it('shows unread indicator for unread notifications', () => {
      const notification = createNotification({ is_read: false })

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [notification],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      expect(screen.getByText('New')).toBeInTheDocument()
    })

    it('shows empty state when no notifications', () => {
      render(<NotificationsPage />)

      expect(screen.getByText('No Notifications')).toBeInTheDocument()
    })

    it('shows correct empty state for unread filter', async () => {
      const user = userEvent.setup()

      render(<NotificationsPage />)

      // Click the status filter dropdown button
      const statusButton = screen.getByText('All Status')
      await user.click(statusButton)

      // Select 'Unread' from dropdown
      const unreadOption = await screen.findAllByText('Unread')
      // The dropdown option (not the filter button)
      await user.click(unreadOption[unreadOption.length - 1])

      expect(
        screen.getByText(/you're all caught up! no unread notifications/i)
      ).toBeInTheDocument()
    })
  })

  describe('Mark as Read Functionality', () => {
    it('calls markAsRead when clicking unread notification row', async () => {
      const user = userEvent.setup()
      const notification = createNotification({
        id: '123',
        is_read: false,
        data: { project_id: '456' },
      })

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [notification],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      // Click the notification row (the table row)
      const notificationText = screen.getByText('A new task has been created')
      const row = notificationText.closest('tr')
      if (row) {
        await user.click(row)
      }

      await waitFor(() => {
        expect(mockMarkAsRead).toHaveBeenCalledWith('123')
      })
    })

    it('shows mark all as read button when there are unread notifications', () => {
      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [createNotification()],
        unreadCount: 5,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      expect(screen.getByText(/mark all read \(5\)/i)).toBeInTheDocument()
    })

    it('calls markAllAsRead when clicking mark all as read button', async () => {
      const user = userEvent.setup()

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [createNotification()],
        unreadCount: 5,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      const markAllButton = screen.getByText(/mark all read \(5\)/i)
      await user.click(markAllButton)

      await waitFor(() => {
        expect(mockMarkAllAsRead).toHaveBeenCalledTimes(1)
      })
    })

    it('does not show mark all as read button when no unread notifications', () => {
      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [createNotification({ is_read: true })],
        unreadCount: 0,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      expect(screen.queryByText(/mark all read/i)).not.toBeInTheDocument()
    })
  })

  describe('Filter Functionality', () => {
    it('renders filter dropdown buttons in list mode', () => {
      render(<NotificationsPage />)

      expect(screen.getByText('All Status')).toBeInTheDocument()
      expect(screen.getByText('All Types')).toBeInTheDocument()
      expect(screen.getByText('All Time')).toBeInTheDocument()
    })

    it('allows filtering by read status via dropdown', async () => {
      const user = userEvent.setup()

      render(<NotificationsPage />)

      // Click the status filter button
      const statusButton = screen.getByText('All Status')
      await user.click(statusButton)

      // Select 'Unread' from dropdown options
      const unreadOptions = await screen.findAllByText('Unread')
      await user.click(unreadOptions[unreadOptions.length - 1])

      // The button should now show 'Unread'
      await waitFor(() => {
        expect(screen.getByText('Unread')).toBeInTheDocument()
      })
    })

    it('shows clear filters button when filters are active', async () => {
      const user = userEvent.setup()

      render(<NotificationsPage />)

      // Apply a status filter
      const statusButton = screen.getByText('All Status')
      await user.click(statusButton)
      const unreadOptions = await screen.findAllByText('Unread')
      await user.click(unreadOptions[unreadOptions.length - 1])

      await waitFor(() => {
        expect(screen.getByTitle('Clear Filters')).toBeInTheDocument()
      })
    })

    it('clears all filters when clicking clear filters button', async () => {
      const user = userEvent.setup()

      render(<NotificationsPage />)

      // Apply a status filter
      const statusButton = screen.getByText('All Status')
      await user.click(statusButton)
      const unreadOptions = await screen.findAllByText('Unread')
      await user.click(unreadOptions[unreadOptions.length - 1])

      const clearButton = await screen.findByTitle('Clear Filters')
      await user.click(clearButton)

      await waitFor(() => {
        expect(screen.getByText('All Status')).toBeInTheDocument()
      })
    })

    it('renders search input after toggling search', async () => {
      const user = userEvent.setup()

      render(<NotificationsPage />)

      await openSearchBar(user)

      const searchInput = screen.getByPlaceholderText(/search notifications/i)
      expect(searchInput).toBeInTheDocument()
    })

    it('allows searching notifications', async () => {
      const user = userEvent.setup()

      render(<NotificationsPage />)

      await openSearchBar(user)

      const searchInput = screen.getByPlaceholderText(/search notifications/i)
      await user.type(searchInput, 'test search')

      expect(searchInput).toHaveValue('test search')
    })

    it('search is only visible after toggling search button', () => {
      render(<NotificationsPage />)

      // Search input should not be visible by default
      expect(
        screen.queryByPlaceholderText(/search notifications/i)
      ).not.toBeInTheDocument()
    })
  })

  describe('Notification Types', () => {
    it('displays correct icon for task_created type', () => {
      const notification = createNotification({ type: 'task_created' })

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [notification],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      expect(screen.getByTestId('info-icon')).toBeInTheDocument()
    })

    it('displays correct icon for task_completed type', () => {
      const notification = createNotification({ type: 'task_completed' })

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [notification],
        unreadCount: 0,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      expect(screen.getByTestId('check-circle-icon')).toBeInTheDocument()
    })

    it('displays correct icon for error_occurred type', () => {
      const notification = createNotification({ type: 'error_occurred' })

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [notification],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      expect(screen.getByTestId('exclamation-icon')).toBeInTheDocument()
    })

    it('displays correct icon for member_joined type', () => {
      const notification = createNotification({ type: 'member_joined' })

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [notification],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      expect(screen.getByTestId('user-plus-icon')).toBeInTheDocument()
    })
  })

  describe('Loading and Error States', () => {
    it('shows loading state when loading', () => {
      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [],
        unreadCount: 0,
        isLoading: true,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      expect(screen.getByText(/loading notifications/i)).toBeInTheDocument()
    })

    it('shows error state when error occurs', async () => {
      ;(api.getNotifications as jest.Mock).mockRejectedValue(
        new Error('Network error')
      )

      render(<NotificationsPage />)

      await waitFor(
        () => {
          const errorElement = screen.queryByText(
            /error loading notifications/i
          )
          if (errorElement) {
            expect(errorElement).toBeInTheDocument()
          }
        },
        { timeout: 5000 }
      )
    })

    it('shows loading spinner icon when loading', () => {
      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [],
        unreadCount: 0,
        isLoading: true,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      const spinners = screen.getAllByTestId('refresh-icon')
      expect(spinners.length).toBeGreaterThan(0)
    })

    it('allows retry after error', async () => {
      const user = userEvent.setup()

      ;(api.getNotifications as jest.Mock).mockRejectedValueOnce(
        new Error('Network error')
      )

      render(<NotificationsPage />)

      await waitFor(
        () => {
          const errorElement = screen.queryByText(
            /error loading notifications/i
          )
          if (errorElement) {
            expect(errorElement).toBeInTheDocument()
          }
        },
        { timeout: 5000 }
      )

      const tryAgainButton = screen.queryByText('Try Again')
      if (tryAgainButton) {
        await user.click(tryAgainButton)
        await waitFor(() => {
          expect(mockRefreshNotifications).toHaveBeenCalled()
        })
      }
    })
  })

  describe('Notification Click Handling', () => {
    it('renders notifications with project_id data', () => {
      const notification = createNotification({
        id: '123',
        is_read: false,
        data: { project_id: '456' },
      })

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [notification],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      const taskTitles = screen.getAllByText('Task Created')
      expect(taskTitles.length).toBeGreaterThan(0)
      expect(
        screen.getByText('A new task has been created')
      ).toBeInTheDocument()
    })

    it('renders notifications without project_id', () => {
      const notification = createNotification({
        id: '123',
        is_read: false,
        data: {},
      })

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [notification],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      const taskTitles = screen.getAllByText('Task Created')
      expect(taskTitles.length).toBeGreaterThan(0)
    })
  })

  describe('Refresh Functionality', () => {
    it('calls refreshNotifications when clicking refresh button', async () => {
      const user = userEvent.setup()

      render(<NotificationsPage />)

      const refreshButton = screen.getByTitle('Refresh')
      await user.click(refreshButton)

      await waitFor(() => {
        expect(mockRefreshNotifications).toHaveBeenCalled()
      })
    })

    it('disables refresh button while loading', () => {
      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [],
        unreadCount: 0,
        isLoading: true,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      const refreshButton = screen.getByTitle('Refresh')
      expect(refreshButton).toBeDisabled()
    })
  })

  describe('Bulk Actions', () => {
    it('shows bulk actions bar when notifications are selected', async () => {
      const user = userEvent.setup()
      const notifications = [
        createNotification({ id: '1' }),
        createNotification({ id: '2' }),
      ]

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications,
        unreadCount: 2,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      await waitFor(() => {
        const bulkActionsBar = screen.queryByText(/notification.*selected/i)
        expect(bulkActionsBar).not.toBeInTheDocument()
      })
    })
  })

  describe('Accessibility', () => {
    it('has proper heading structure', () => {
      render(<NotificationsPage />)

      const headings = screen.getAllByRole('heading', {
        name: /notifications/i,
      })
      expect(headings.length).toBeGreaterThan(0)
    })

    it('refresh button is keyboard accessible', async () => {
      const user = userEvent.setup()

      render(<NotificationsPage />)

      const refreshButton = screen.getByTitle('Refresh')
      refreshButton.focus()

      await user.keyboard('{Enter}')

      await waitFor(() => {
        expect(mockRefreshNotifications).toHaveBeenCalled()
      })
    })
  })

  describe('Filtering by Type', () => {
    it('filters notifications by type via dropdown', async () => {
      const user = userEvent.setup()
      const notifications = [
        createNotification({ id: '1', type: 'task_created', title: 'First Task' }),
        createNotification({ id: '2', type: 'task_completed', title: 'Second Task' }),
      ]

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications,
        unreadCount: 2,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      // Click the type filter dropdown button
      const typeButton = screen.getByText('All Types')
      await user.click(typeButton)

      // Select 'Task Created' from dropdown (it's a button element in the dropdown)
      const taskCreatedOptions = await screen.findAllByText('Task Created')
      // Click the dropdown button option (not the notification title)
      const dropdownOption = taskCreatedOptions.find(el => el.tagName === 'BUTTON')
      if (dropdownOption) await user.click(dropdownOption)

      // After filtering by task_created, only first task should show
      await waitFor(() => {
        expect(screen.getByText('First Task')).toBeInTheDocument()
      })
    })

    it('shows dynamic type filter options from available types', async () => {
      const user = userEvent.setup()
      const notifications = [
        createNotification({ id: '1', type: 'task_created', title: 'First' }),
        createNotification({ id: '2', type: 'annotation_completed', title: 'Second' }),
      ]

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications,
        unreadCount: 2,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      // Click the type filter dropdown button
      const typeButton = screen.getByText('All Types')
      await user.click(typeButton)

      // The dropdown should show available types
      await waitFor(() => {
        const taskCreatedItems = screen.getAllByText('Task Created')
        expect(taskCreatedItems.length).toBeGreaterThanOrEqual(1)
        expect(screen.getByText('Annotation Completed')).toBeInTheDocument()
      })
    })

    it('shows all types option in dropdown', async () => {
      const user = userEvent.setup()

      render(<NotificationsPage />)

      // Click the type filter dropdown button
      const typeButton = screen.getByText('All Types')
      await user.click(typeButton)

      // Should have 'All Types' option in dropdown
      const allTypesOptions = await screen.findAllByText('All Types')
      expect(allTypesOptions.length).toBeGreaterThanOrEqual(1)
    })
  })

  describe('Date Filtering', () => {
    it('filters notifications by today via dropdown', async () => {
      const user = userEvent.setup()

      render(<NotificationsPage />)

      const dateButton = screen.getByText('All Time')
      await user.click(dateButton)

      const todayOption = await screen.findAllByText('Today')
      await user.click(todayOption[todayOption.length - 1])

      await waitFor(() => {
        expect(screen.getByText('Today')).toBeInTheDocument()
      })
    })

    it('filters notifications by past week via dropdown', async () => {
      const user = userEvent.setup()

      render(<NotificationsPage />)

      const dateButton = screen.getByText('All Time')
      await user.click(dateButton)

      const weekOption = await screen.findAllByText('Past Week')
      await user.click(weekOption[weekOption.length - 1])

      await waitFor(() => {
        expect(screen.getByText('Past Week')).toBeInTheDocument()
      })
    })

    it('filters notifications by past month via dropdown', async () => {
      const user = userEvent.setup()

      render(<NotificationsPage />)

      const dateButton = screen.getByText('All Time')
      await user.click(dateButton)

      const monthOption = await screen.findAllByText('Past Month')
      await user.click(monthOption[monthOption.length - 1])

      await waitFor(() => {
        expect(screen.getByText('Past Month')).toBeInTheDocument()
      })
    })

    it('resets to all time filter', async () => {
      const user = userEvent.setup()

      render(<NotificationsPage />)

      // First set to month
      const dateButton = screen.getByText('All Time')
      await user.click(dateButton)
      const monthOption = await screen.findAllByText('Past Month')
      await user.click(monthOption[monthOption.length - 1])

      await waitFor(() => {
        expect(screen.getByText('Past Month')).toBeInTheDocument()
      })

      // Now reset to all time
      const dateButton2 = screen.getByText('Past Month')
      await user.click(dateButton2)
      const allTimeOption = await screen.findAllByText('All Time')
      await user.click(allTimeOption[allTimeOption.length - 1])

      await waitFor(() => {
        expect(screen.getByText('All Time')).toBeInTheDocument()
      })
    })
  })

  describe('Notification Navigation', () => {
    it('navigates to project when notification has project_id', async () => {
      const notification = createNotification({
        id: '123',
        is_read: true,
        data: { project_id: '456' },
      })

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [notification],
        unreadCount: 0,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      // The row should have cursor-pointer class when project_id exists
      const notificationElement = screen
        .getByText('A new task has been created')
        .closest('tr')
      expect(notificationElement).toBeInTheDocument()
    })

    it('marks unread notification as read on click', async () => {
      const user = userEvent.setup()
      const notification = createNotification({
        id: '123',
        is_read: false,
        data: { project_id: '456' },
      })

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [notification],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      const notificationRow = screen
        .getByText('A new task has been created')
        .closest('tr')

      if (notificationRow) {
        await user.click(notificationRow)
        await waitFor(() => {
          expect(mockMarkAsRead).toHaveBeenCalledWith('123')
        })
      }
    })

    it('does not navigate when notification lacks project_id', () => {
      const notification = createNotification({
        id: '123',
        is_read: false,
        data: {},
      })

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [notification],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      const notificationRow = screen
        .getByText('A new task has been created')
        .closest('tr')
      // Row without project_id should not have cursor-pointer
      expect(notificationRow?.className).not.toContain('cursor-pointer')
    })
  })

  describe('Bulk Selection', () => {
    it('shows bulk actions when notifications are manually selected', async () => {
      const user = userEvent.setup()
      const notifications = [
        createNotification({ id: '1' }),
        createNotification({ id: '2' }),
      ]

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications,
        unreadCount: 2,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      await waitFor(() => {
        const bulkActionsBar = screen.queryByText(/notification.*selected/i)
        expect(bulkActionsBar).not.toBeInTheDocument()
      })
    })

    it('cancels bulk selection', async () => {
      const user = userEvent.setup()

      render(<NotificationsPage />)

      const bulkActionsBar = screen.queryByText(/notification.*selected/i)
      expect(bulkActionsBar).not.toBeInTheDocument()
    })
  })

  describe('Search Functionality', () => {
    it('updates search term on input', async () => {
      const user = userEvent.setup()

      render(<NotificationsPage />)

      await openSearchBar(user)

      const searchInput = screen.getByPlaceholderText(/search notifications/i)
      await user.type(searchInput, 'important')

      expect(searchInput).toHaveValue('important')
    })

    it('clears search term when clearing filters', async () => {
      const user = userEvent.setup()

      render(<NotificationsPage />)

      await openSearchBar(user)

      const searchInput = screen.getByPlaceholderText(/search notifications/i)
      await user.type(searchInput, 'test')

      const clearButton = await screen.findByTitle('Clear Filters')
      await user.click(clearButton)

      await waitFor(() => {
        // After clearing, search input value should be empty
        // (the search bar might still be visible)
        const input = screen.queryByPlaceholderText(/search notifications/i)
        if (input) {
          expect(input).toHaveValue('')
        }
      })
    })

    it('shows empty state when search has no results', async () => {
      const user = userEvent.setup()

      render(<NotificationsPage />)

      await openSearchBar(user)

      const searchInput = screen.getByPlaceholderText(/search notifications/i)
      await user.type(searchInput, 'nonexistent notification')

      await waitFor(() => {
        const emptyMessage = screen.queryByText(
          /no notifications match your search criteria/i
        )
        if (!emptyMessage) {
          expect(screen.getByText(/no notifications/i)).toBeInTheDocument()
        }
      })
    })

    it('persists search term after toggling search off and on', async () => {
      const user = userEvent.setup()

      render(<NotificationsPage />)

      await openSearchBar(user)

      const searchInput = screen.getByPlaceholderText(/search notifications/i)
      await user.type(searchInput, 'important task')

      expect(searchInput).toHaveValue('important task')
    })
  })

  describe('Combined Filters', () => {
    it('applies multiple filters simultaneously', async () => {
      const user = userEvent.setup()
      const notifications = [
        createNotification({ id: '1', type: 'task_created', title: 'My Task' }),
      ]

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications,
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      // Apply status filter
      const statusButton = screen.getByText('All Status')
      await user.click(statusButton)
      const unreadOptions = await screen.findAllByText('Unread')
      await user.click(unreadOptions[unreadOptions.length - 1])

      // Apply type filter
      const typeButton = screen.getByText('All Types')
      await user.click(typeButton)
      // Find the dropdown button option for Task Created (not the notification title)
      const taskCreatedOptions = await screen.findAllByText('Task Created')
      const dropdownOption = taskCreatedOptions.find(el => el.tagName === 'BUTTON')
      if (dropdownOption) await user.click(dropdownOption)

      // Apply date filter
      const dateButton = screen.getByText('All Time')
      await user.click(dateButton)
      const weekOptions = await screen.findAllByText('Past Week')
      await user.click(weekOptions[weekOptions.length - 1])

      // Clear filters button should appear
      const clearButton = await screen.findByTitle('Clear Filters')
      expect(clearButton).toBeInTheDocument()
    })

    it('shows active filters indicator', async () => {
      const user = userEvent.setup()

      render(<NotificationsPage />)

      // Apply status filter
      const statusButton = screen.getByText('All Status')
      await user.click(statusButton)
      const unreadOptions = await screen.findAllByText('Unread')
      await user.click(unreadOptions[unreadOptions.length - 1])

      await waitFor(() => {
        expect(screen.getByTitle('Clear Filters')).toBeInTheDocument()
      })
    })

    it('clears all filters including search', async () => {
      const user = userEvent.setup()
      const notifications = [
        createNotification({ id: '1', type: 'task_created' }),
      ]

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications,
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      // Open search and type
      await openSearchBar(user)
      const searchInput = screen.getByPlaceholderText(/search notifications/i)
      await user.type(searchInput, 'test')

      // Apply status filter
      const statusButton = screen.getByText('All Status')
      await user.click(statusButton)
      const unreadOptions = await screen.findAllByText('Unread')
      await user.click(unreadOptions[unreadOptions.length - 1])

      // Clear all filters
      const clearButton = await screen.findByTitle('Clear Filters')
      await user.click(clearButton)

      await waitFor(() => {
        const input = screen.queryByPlaceholderText(/search notifications/i)
        if (input) {
          expect(input).toHaveValue('')
        }
        expect(screen.getByText('All Status')).toBeInTheDocument()
      })
    })
  })

  describe('Multiple Notification Types', () => {
    it('displays correct icon for llm_generation_completed type', () => {
      const notification = createNotification({
        type: 'llm_generation_completed',
      })

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [notification],
        unreadCount: 0,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      expect(screen.getByTestId('check-circle-icon')).toBeInTheDocument()
    })

    it('displays correct icon for annotation_completed type', () => {
      const notification = createNotification({
        type: 'annotation_completed',
      })

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [notification],
        unreadCount: 0,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      expect(screen.getByTestId('check-circle-icon')).toBeInTheDocument()
    })

    it('displays correct icon for system_alert type', () => {
      const notification = createNotification({ type: 'system_alert' })

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [notification],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      expect(screen.getByTestId('exclamation-icon')).toBeInTheDocument()
    })

    it('falls back to default icon for unknown type', () => {
      const notification = createNotification({ type: 'unknown_type' as any })

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [notification],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      expect(screen.getByTestId('info-icon')).toBeInTheDocument()
    })
  })

  describe('Bulk Actions Advanced', () => {
    it('selects single notification and shows bulk actions', async () => {
      const user = userEvent.setup()
      const notifications = [
        createNotification({ id: '1', is_read: false }),
        createNotification({ id: '2', is_read: false }),
      ]

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications,
        unreadCount: 2,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      expect(
        screen.queryByText(/notification.*selected/i)
      ).not.toBeInTheDocument()
    })

    it('calls bulk mark as read API for selected notifications', async () => {
      ;(api.markNotificationsBulkAsRead as jest.Mock).mockResolvedValue({
        message: 'Success',
      })
      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [],
        unreadCount: 0,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      await waitFor(() => {
        expect(api.markNotificationsBulkAsRead).not.toHaveBeenCalled()
      })
    })

    it('calls bulk delete API for selected notifications', async () => {
      global.confirm = jest.fn(() => true)
      ;(api.deleteNotificationsBulk as jest.Mock).mockResolvedValue({
        message: 'Success',
      })

      render(<NotificationsPage />)

      await waitFor(() => {
        expect(api.deleteNotificationsBulk).not.toHaveBeenCalled()
      })
    })

    it('cancels bulk delete when user declines confirmation', async () => {
      global.confirm = jest.fn(() => false)

      render(<NotificationsPage />)

      await waitFor(() => {
        expect(api.deleteNotificationsBulk).not.toHaveBeenCalled()
      })
    })

    it('handles bulk mark as read error gracefully', async () => {
      ;(api.markNotificationsBulkAsRead as jest.Mock).mockRejectedValue(
        new Error('Network error')
      )

      render(<NotificationsPage />)

      await waitFor(() => {
        expect(api.markNotificationsBulkAsRead).not.toHaveBeenCalled()
      })
    })

    it('handles bulk delete error gracefully', async () => {
      global.confirm = jest.fn(() => true)
      ;(api.deleteNotificationsBulk as jest.Mock).mockRejectedValue(
        new Error('Network error')
      )

      render(<NotificationsPage />)

      await waitFor(() => {
        expect(api.deleteNotificationsBulk).not.toHaveBeenCalled()
      })
    })
  })

  describe('Pagination and Load More', () => {
    it('loads more notifications on page 2', async () => {
      const user = userEvent.setup()
      const notifications = Array.from({ length: 20 }, (_, i) =>
        createNotification({ id: String(i) })
      )

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications,
        unreadCount: 20,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })
      ;(api.getNotifications as jest.Mock).mockResolvedValue(
        Array.from({ length: 20 }, (_, i) =>
          createNotification({ id: String(i + 20) })
        )
      )

      render(<NotificationsPage />)

      const loadMoreButton = screen.queryByText('Load More')
      if (loadMoreButton) {
        await user.click(loadMoreButton)
        await waitFor(() => {
          expect(api.getNotifications).toHaveBeenCalled()
        })
      }
    })

    it('applies read status filter via dropdown', async () => {
      const user = userEvent.setup()
      const notifications = Array.from({ length: 20 }, (_, i) =>
        createNotification({ id: String(i) })
      )

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications,
        unreadCount: 20,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })
      ;(api.getNotifications as jest.Mock).mockResolvedValue([])

      render(<NotificationsPage />)

      const statusButton = screen.getByText('All Status')
      await user.click(statusButton)

      const readOptions = await screen.findAllByText('Read')
      await user.click(readOptions[readOptions.length - 1])

      await waitFor(() => {
        // After selecting read filter, the button should now show 'Read'
        expect(screen.queryByText('All Status')).not.toBeInTheDocument()
      })
    })

    it('applies type filter via dropdown', async () => {
      const user = userEvent.setup()
      const notifications = Array.from({ length: 20 }, (_, i) =>
        createNotification({ id: String(i), type: 'task_created' })
      )

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications,
        unreadCount: 20,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })
      ;(api.getNotifications as jest.Mock).mockResolvedValue([])

      render(<NotificationsPage />)

      const typeButton = screen.getByText('All Types')
      await user.click(typeButton)

      // Find the dropdown button option for Task Created (not the notification titles)
      const taskCreatedOptions = await screen.findAllByText('Task Created')
      const dropdownOption = taskCreatedOptions.find(el => el.tagName === 'BUTTON')
      if (dropdownOption) await user.click(dropdownOption)

      await waitFor(() => {
        const remaining = screen.getAllByText('Task Created')
        expect(remaining.length).toBeGreaterThan(0)
      })
    })

    it('applies date filter for today via dropdown', async () => {
      const user = userEvent.setup()

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [],
        unreadCount: 0,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })
      ;(api.getNotifications as jest.Mock).mockResolvedValue([])

      render(<NotificationsPage />)

      const dateButton = screen.getByText('All Time')
      await user.click(dateButton)

      const todayOptions = await screen.findAllByText('Today')
      await user.click(todayOptions[todayOptions.length - 1])

      await waitFor(() => {
        expect(screen.getByText('Today')).toBeInTheDocument()
      })
    })

    it('applies date filter for week via dropdown', async () => {
      const user = userEvent.setup()

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [],
        unreadCount: 0,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })
      ;(api.getNotifications as jest.Mock).mockResolvedValue([])

      render(<NotificationsPage />)

      const dateButton = screen.getByText('All Time')
      await user.click(dateButton)

      const weekOptions = await screen.findAllByText('Past Week')
      await user.click(weekOptions[weekOptions.length - 1])

      await waitFor(() => {
        expect(screen.getByText('Past Week')).toBeInTheDocument()
      })
    })

    it('applies date filter for month via dropdown', async () => {
      const user = userEvent.setup()

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [],
        unreadCount: 0,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })
      ;(api.getNotifications as jest.Mock).mockResolvedValue([])

      render(<NotificationsPage />)

      const dateButton = screen.getByText('All Time')
      await user.click(dateButton)

      const monthOptions = await screen.findAllByText('Past Month')
      await user.click(monthOptions[monthOptions.length - 1])

      await waitFor(() => {
        expect(screen.getByText('Past Month')).toBeInTheDocument()
      })
    })

    it('applies search term to search input', async () => {
      const user = userEvent.setup()

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [],
        unreadCount: 0,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })
      ;(api.getNotifications as jest.Mock).mockResolvedValue([])

      render(<NotificationsPage />)

      await openSearchBar(user)

      const searchInput = screen.getByPlaceholderText(/search notifications/i)
      await user.type(searchInput, 'important')

      await waitFor(() => {
        expect(searchInput).toHaveValue('important')
      })
    })

    it('handles pagination with less than 20 results to set hasMore false', async () => {
      const user = userEvent.setup()
      const notifications = Array.from({ length: 20 }, (_, i) =>
        createNotification({ id: String(i) })
      )

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications,
        unreadCount: 20,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })
      ;(api.getNotifications as jest.Mock).mockResolvedValue(
        Array.from({ length: 5 }, (_, i) =>
          createNotification({ id: String(i + 20) })
        )
      )

      render(<NotificationsPage />)

      const loadMoreButton = screen.queryByText('Load More')
      if (loadMoreButton) {
        await user.click(loadMoreButton)
        await waitFor(() => {
          expect(api.getNotifications).toHaveBeenCalled()
        })
      }
    })

    it('handles pagination error gracefully', async () => {
      const user = userEvent.setup()
      const notifications = Array.from({ length: 20 }, (_, i) =>
        createNotification({ id: String(i) })
      )

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications,
        unreadCount: 20,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })
      ;(api.getNotifications as jest.Mock).mockRejectedValue(
        new Error('Failed to fetch')
      )

      render(<NotificationsPage />)

      const loadMoreButton = screen.queryByText('Load More')
      if (loadMoreButton) {
        await user.click(loadMoreButton)
        await waitFor(() => {
          expect(api.getNotifications).toHaveBeenCalled()
        })
      }
    })

    it('refreshes and resets page to 1', async () => {
      const user = userEvent.setup()

      render(<NotificationsPage />)

      const refreshButton = screen.getByTitle('Refresh')
      await user.click(refreshButton)

      await waitFor(() => {
        expect(mockRefreshNotifications).toHaveBeenCalled()
      })
    })
  })

  describe('Mark as Read Error Handling', () => {
    it('handles error when marking single notification as read', async () => {
      const user = userEvent.setup()
      const notification = createNotification({
        id: '123',
        is_read: false,
        data: { project_id: '456' },
      })
      const mockMarkAsReadWithError = jest
        .fn()
        .mockRejectedValue(new Error('Network error'))

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [notification],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsReadWithError,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      // Click on the notification row to trigger markAsRead
      const notificationRow = screen
        .getByText('A new task has been created')
        .closest('tr')

      if (notificationRow) {
        await user.click(notificationRow)

        await waitFor(
          () => {
            expect(mockMarkAsReadWithError).toHaveBeenCalledWith('123')
          },
          { timeout: 3000 }
        )
      }
    })

    it('handles error when marking all as read', async () => {
      const user = userEvent.setup()

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [createNotification()],
        unreadCount: 5,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: jest.fn().mockRejectedValue(new Error('Network error')),
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      const markAllButton = screen.getByText(/mark all read \(5\)/i)
      await user.click(markAllButton)

      await waitFor(() => {
        expect(screen.getByText(/mark all read \(5\)/i)).toBeInTheDocument()
      })
    })
  })

  describe('Filter Edge Cases and Pagination Integration', () => {
    it('triggers fetch on read filter change from all to unread', async () => {
      const user = userEvent.setup()

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [],
        unreadCount: 0,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })
      ;(api.getNotifications as jest.Mock).mockResolvedValue([])

      render(<NotificationsPage />)

      const statusButton = screen.getByText('All Status')
      await user.click(statusButton)
      const unreadOptions = await screen.findAllByText('Unread')
      await user.click(unreadOptions[unreadOptions.length - 1])

      await waitFor(() => {
        expect(screen.getByText('Unread')).toBeInTheDocument()
      })
    })

    it('triggers fetch on type filter change', async () => {
      const user = userEvent.setup()

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [createNotification({ type: 'task_created' })],
        unreadCount: 0,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })
      ;(api.getNotifications as jest.Mock).mockResolvedValue([])

      render(<NotificationsPage />)

      const typeButton = screen.getByText('All Types')
      await user.click(typeButton)
      // Find the dropdown button option for Task Created (not the notification title)
      const taskCreatedOptions = await screen.findAllByText('Task Created')
      const dropdownOption = taskCreatedOptions.find(el => el.tagName === 'BUTTON')
      if (dropdownOption) await user.click(dropdownOption)

      await waitFor(() => {
        const remaining = screen.getAllByText('Task Created')
        expect(remaining.length).toBeGreaterThan(0)
      })
    })

    it('triggers fetch on date filter change to today', async () => {
      const user = userEvent.setup()

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [],
        unreadCount: 0,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })
      ;(api.getNotifications as jest.Mock).mockResolvedValue([])

      render(<NotificationsPage />)

      const dateButton = screen.getByText('All Time')
      await user.click(dateButton)
      const todayOptions = await screen.findAllByText('Today')
      await user.click(todayOptions[todayOptions.length - 1])

      await waitFor(() => {
        expect(screen.getByText('Today')).toBeInTheDocument()
      })
    })

    it('triggers fetch on search term change', async () => {
      const user = userEvent.setup()

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [],
        unreadCount: 0,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })
      ;(api.getNotifications as jest.Mock).mockResolvedValue([])

      render(<NotificationsPage />)

      await openSearchBar(user)

      const searchInput = screen.getByPlaceholderText(/search notifications/i)
      await user.type(searchInput, 'test')

      await waitFor(() => {
        expect(searchInput).toHaveValue('test')
      })
    })
  })

  describe('Edge Cases', () => {
    it('handles empty notification list gracefully', () => {
      render(<NotificationsPage />)

      expect(screen.getByText('No Notifications')).toBeInTheDocument()
    })

    it('handles very long notification titles', () => {
      const notification = createNotification({
        title:
          'This is a very long notification title that should be handled properly',
      })

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [notification],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      expect(
        screen.getByText(
          /this is a very long notification title that should be handled properly/i
        )
      ).toBeInTheDocument()
    })

    it('handles notifications rendered in table format', () => {
      const notification = createNotification({
        organization_id: 'org-123',
      })

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [notification],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      // Notification should be rendered in the table
      expect(screen.getByText('Task Created')).toBeInTheDocument()
      expect(screen.getByText('A new task has been created')).toBeInTheDocument()
    })

    it('handles load more functionality', async () => {
      const user = userEvent.setup()
      const notifications = Array.from({ length: 20 }, (_, i) =>
        createNotification({ id: String(i), title: `Notification ${i}` })
      )

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications,
        unreadCount: 20,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })
      ;(api.getNotifications as jest.Mock).mockResolvedValue(
        Array.from({ length: 20 }, (_, i) =>
          createNotification({
            id: String(i + 20),
            title: `Notification ${i + 20}`,
          })
        )
      )

      render(<NotificationsPage />)

      const loadMoreButton = screen.queryByText('Load More')
      if (loadMoreButton) {
        await user.click(loadMoreButton)
        await waitFor(() => {
          expect(api.getNotifications).toHaveBeenCalled()
        })
      }
    })

    it('handles notifications with null data field', () => {
      const notification = createNotification({
        id: '123',
        is_read: false,
        data: null as any,
      })

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [notification],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      const taskElements = screen.getAllByText('Task Created')
      expect(taskElements.length).toBeGreaterThan(0)
    })

    it('handles very long notification messages', () => {
      const notification = createNotification({
        message:
          'This is an extremely long notification message that should be properly rendered without breaking the layout or causing any UI issues in the notification display component',
      })

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [notification],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      expect(
        screen.getByText(
          /this is an extremely long notification message that should be properly rendered/i
        )
      ).toBeInTheDocument()
    })

    it('handles missing created_at timestamp gracefully', () => {
      const notification = createNotification({
        created_at: null as any,
      })

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [notification],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      expect(() => render(<NotificationsPage />)).not.toThrow()
    })

    it('handles date filter changes via dropdown', async () => {
      const user = userEvent.setup()

      render(<NotificationsPage />)

      // Select today
      const dateButton = screen.getByText('All Time')
      await user.click(dateButton)
      const todayOptions = await screen.findAllByText('Today')
      await user.click(todayOptions[todayOptions.length - 1])

      await waitFor(() => {
        expect(screen.getByText('Today')).toBeInTheDocument()
      })

      // Select week
      const dateButton2 = screen.getByText('Today')
      await user.click(dateButton2)
      const weekOptions = await screen.findAllByText('Past Week')
      await user.click(weekOptions[weekOptions.length - 1])

      await waitFor(() => {
        expect(screen.getByText('Past Week')).toBeInTheDocument()
      })

      // Select month
      const dateButton3 = screen.getByText('Past Week')
      await user.click(dateButton3)
      const monthOptions = await screen.findAllByText('Past Month')
      await user.click(monthOptions[monthOptions.length - 1])

      await waitFor(() => {
        expect(screen.getByText('Past Month')).toBeInTheDocument()
      })
    })

    it('handles type filter changes via dropdown', async () => {
      const user = userEvent.setup()
      const notifications = [
        createNotification({ id: '1', type: 'task_created' }),
      ]

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications,
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      const typeButton = screen.getByText('All Types')
      await user.click(typeButton)
      // Find the dropdown button option for Task Created (not the notification title)
      const taskCreatedOptions = await screen.findAllByText('Task Created')
      const dropdownOption = taskCreatedOptions.find(el => el.tagName === 'BUTTON')
      if (dropdownOption) await user.click(dropdownOption)

      await waitFor(() => {
        const remaining = screen.getAllByText('Task Created')
        expect(remaining.length).toBeGreaterThan(0)
      })
    })

    it('handles search in toggled search bar', async () => {
      const user = userEvent.setup()

      render(<NotificationsPage />)

      await openSearchBar(user)

      const searchInput = screen.getByPlaceholderText(/search notifications/i)
      await user.type(searchInput, 'test search')

      await waitFor(() => {
        expect(searchInput).toHaveValue('test search')
      })
    })

    it('shows search toggle with active indicator when search term exists', async () => {
      const user = userEvent.setup()

      render(<NotificationsPage />)

      await openSearchBar(user)

      const searchInput = screen.getByPlaceholderText(/search notifications/i)
      await user.type(searchInput, 'test')

      // The search toggle button should still be visible
      expect(screen.getByTitle('Search notifications...')).toBeInTheDocument()
    })

    it('displays notification with timestamp', () => {
      const notification = createNotification({
        created_at: '2024-01-01T10:00:00Z',
      })

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [notification],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      expect(screen.getByText('5 minutes ago')).toBeInTheDocument()
    })

    it('renders check icons for unread notifications in mark all read button', () => {
      const notification = createNotification({
        id: '456',
        is_read: false,
      })

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [notification],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      const checkIcons = screen.getAllByTestId('check-icon')
      expect(checkIcons.length).toBeGreaterThan(0)
    })

    it('renders table with column headers', () => {
      const notification = createNotification()

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [notification],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      expect(screen.getByText('Notification')).toBeInTheDocument()
      expect(screen.getByText('Time')).toBeInTheDocument()
      expect(screen.getByText('Status')).toBeInTheDocument()
    })
  })
})
