/**
 * @jest-environment jsdom
 */

import { useAuth } from '@/contexts/AuthContext'
import { useNotifications } from '@/hooks/useNotifications'
import { api } from '@/lib/api'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useRouter } from 'next/navigation'
import NotificationsPage from '../page'

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
        'notifications.subtitle': 'Stay up to date with your tasks and system updates',
        'notifications.searchPlaceholder': 'Search notifications...',
        'notifications.refresh': 'Refresh',
        'notifications.markAllRead': 'Mark all read',
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
        'notifications.noMatches': 'No notifications match your search criteria',
        'notifications.allCaughtUp': "You're all caught up! No unread notifications",
        'notifications.deleteConfirm': 'Are you sure you want to delete?',
        'notifications.markRead': 'Mark as Read',
        'notifications.delete': 'Delete',
        'notifications.cancel': 'Cancel',
        'notifications.selected': '{count} notification(s) selected',
        'notifications.new': 'New',
        'notifications.loadMore': 'Load More',
        'notifications.loadingMore': 'Loading more...',
        'notifications.errorTitle': 'Error Loading Notifications',
        'notifications.tryAgain': 'Try Again',
        'notifications.loadFailed': 'Failed to load notifications',
        'notifications.authRequired': 'Authentication Required',
        'notifications.authRequiredMessage': 'Please log in to view your notifications',
        'notifications.columnNotification': 'Notification',
        'notifications.columnTime': 'Time',
        'notifications.columnStatus': 'Status',
        'notifications.analyticsTitle': 'Notification Analytics',
        'common.search': 'Search',
        'navigation.dashboard': 'Dashboard',
      }
      let result = translations[key]
      if (!result) {
        return typeof defaultValueOrVars === 'string' ? defaultValueOrVars : key
      }
      const variables = vars || (typeof defaultValueOrVars === 'object' ? defaultValueOrVars : null)
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

jest.mock('date-fns/locale', () => ({ de: {} }))

jest.mock('@/lib/notificationTranslation', () => ({
  getTranslatedNotification: (_t: any, notification: any) => ({
    title: notification.title,
    message: notification.message,
  }),
}))

jest.mock('date-fns', () => ({
  formatDistanceToNow: jest.fn(() => '5 minutes ago'),
}))

jest.mock('@heroicons/react/24/outline', () => ({
  ArrowPathIcon: (props: any) => <svg data-testid="refresh-icon" {...props} />,
  CheckCircleIcon: (props: any) => <svg data-testid="check-circle-icon" {...props} />,
  CheckIcon: (props: any) => <svg data-testid="check-icon" {...props} />,
  ChevronDownIcon: (props: any) => <svg data-testid="chevron-down-icon" {...props} />,
  ChevronUpDownIcon: (props: any) => <svg data-testid="chevron-up-down-icon" {...props} />,
  ClockIcon: (props: any) => <svg data-testid="clock-icon" {...props} />,
  ExclamationTriangleIcon: (props: any) => <svg data-testid="exclamation-icon" {...props} />,
  FunnelIcon: (props: any) => <svg data-testid="funnel-icon" {...props} />,
  InformationCircleIcon: (props: any) => <svg data-testid="info-icon" {...props} />,
  UserPlusIcon: (props: any) => <svg data-testid="user-plus-icon" {...props} />,
  XMarkIcon: (props: any) => <svg data-testid="x-mark-icon" {...props} />,
  ChartBarIcon: (props: any) => <svg data-testid="chart-bar-icon" {...props} />,
  MagnifyingGlassIcon: (props: any) => <svg data-testid="magnifying-glass-icon" {...props} />,
  TrashIcon: (props: any) => <svg data-testid="trash-icon" {...props} />,
}))

jest.mock('next/link', () => ({
  __esModule: true,
  default: ({ children, href, ...props }: { children: React.ReactNode; href: string }) => (
    <a href={href} {...props}>{children}</a>
  ),
}))

jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: ({ items }: any) => (
    <nav data-testid="breadcrumb">
      {items?.map((item: any, i: number) => <span key={i}>{item.label}</span>)}
    </nav>
  ),
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, disabled, ...props }: any) => (
    <button onClick={onClick} disabled={disabled} {...props}>{children}</button>
  ),
}))

jest.mock('@/components/shared/ResponsiveContainer', () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
}))
jest.mock('@/components/shared/Select', () => ({
  Select: ({ value, onValueChange, disabled, children }: any) => (
    <select
      value={value ?? ''}
      onChange={(e) => onValueChange(e.target.value)}
      disabled={disabled}
    >
      {children}
    </select>
  ),
  SelectTrigger: () => null,
  SelectValue: () => null,
  SelectContent: ({ children }: any) => <>{children}</>,
  SelectItem: ({ value, children }: any) => (
    <option value={value}>{children}</option>
  ),
}))

jest.mock('@/components/shared/FilterToolbar', () => {
  const FilterToolbar = ({
    searchValue,
    onSearchChange,
    searchPlaceholder,
    searchLabel,
    clearLabel = 'Clear filters',
    onClearFilters,
    hasActiveFilters,
    leftExtras,
    rightExtras,
    children,
  }: any) => (
    <div data-testid="filter-toolbar">
      {leftExtras}
      {onSearchChange && (
        <input
          data-testid="filter-toolbar-search"
          type="search"
          placeholder={searchPlaceholder}
          title={searchPlaceholder || searchLabel}
          value={searchValue ?? ''}
          onChange={(e) => onSearchChange(e.target.value)}
        />
      )}
      <div data-testid="filter-toolbar-fields">{children}</div>
      {onClearFilters && (
        <button
          data-testid="filter-toolbar-clear"
          onClick={onClearFilters}
          disabled={!hasActiveFilters}
          title={clearLabel}
          aria-label={clearLabel}
        />
      )}
      {rightExtras}
    </div>
  )
  FilterToolbar.Field = ({ children }: any) => <div>{children}</div>
  return { FilterToolbar }
})


describe('NotificationsPage - coverage extensions', () => {
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
    created_at: new Date().toISOString(),
    ...overrides,
  })

  beforeEach(() => {
    jest.clearAllMocks()
    ;(useRouter as jest.Mock).mockReturnValue({ push: mockPush })
    ;(useAuth as jest.Mock).mockReturnValue({ user: mockUser, apiClient: {} })
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
    ;(api.markNotificationsBulkAsRead as jest.Mock).mockResolvedValue({ message: 'Success' })
    ;(api.deleteNotificationsBulk as jest.Mock).mockResolvedValue({ message: 'Success' })
  })

  describe('Date filtering logic', () => {
    // Filter combobox order matches the page render order:
    //   [0] read-status, [1] type, [2] date.
    const getDateFilter = () => screen.getAllByRole('combobox')[2]

    const renderWith = (notifications: any[]) => {
      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications,
        unreadCount: notifications.length,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })
      render(<NotificationsPage />)
    }

    it('filters by "today" - shows only today notifications', async () => {
      const user = userEvent.setup()
      renderWith([
        createNotification({ id: 'today-1', title: 'Today Task', created_at: new Date().toISOString() }),
        createNotification({ id: 'old-1', title: 'Old Task', created_at: '2020-01-01T10:00:00Z' }),
      ])

      await user.selectOptions(getDateFilter(), 'today')

      const table = screen.getByRole('table')
      expect(within(table).getByText('Today Task')).toBeInTheDocument()
      expect(within(table).queryByText('Old Task')).not.toBeInTheDocument()
    })

    it('filters by "week" - hides notifications older than 7 days', async () => {
      const user = userEvent.setup()
      renderWith([
        createNotification({ id: 'recent-1', title: 'Recent Task', created_at: new Date().toISOString() }),
        createNotification({ id: 'old-1', title: 'Ancient Task', created_at: '2020-01-01T10:00:00Z' }),
      ])

      await user.selectOptions(getDateFilter(), 'week')

      const table = screen.getByRole('table')
      expect(within(table).getByText('Recent Task')).toBeInTheDocument()
      expect(within(table).queryByText('Ancient Task')).not.toBeInTheDocument()
    })

    it('filters by "month" - hides notifications before current month', async () => {
      const user = userEvent.setup()
      renderWith([
        createNotification({ id: 'month-1', title: 'This Month Task', created_at: new Date().toISOString() }),
        createNotification({ id: 'old-1', title: 'Last Year Task', created_at: '2020-01-01T10:00:00Z' }),
      ])

      await user.selectOptions(getDateFilter(), 'month')

      const table = screen.getByRole('table')
      expect(within(table).getByText('This Month Task')).toBeInTheDocument()
      expect(within(table).queryByText('Last Year Task')).not.toBeInTheDocument()
    })
  })

  describe('Search filtering', () => {
    it('filters notifications by title via search', async () => {
      const user = userEvent.setup()
      const notifications = [
        createNotification({ id: '1', title: 'Alpha Task', message: 'First' }),
        createNotification({ id: '2', title: 'Beta Task', message: 'Second' }),
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

      // Open search
      await user.click(screen.getByTitle('Search notifications...'))
      const input = screen.getByPlaceholderText('Search notifications...')
      await user.type(input, 'alpha')

      await waitFor(() => {
        expect(screen.getByText('Alpha Task')).toBeInTheDocument()
        expect(screen.queryByText('Beta Task')).not.toBeInTheDocument()
      })
    })

    it('shows no matches message when search returns nothing', async () => {
      const user = userEvent.setup()
      const notifications = [
        createNotification({ id: '1', title: 'Task A', message: 'First' }),
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

      await user.click(screen.getByTitle('Search notifications...'))
      const input = screen.getByPlaceholderText('Search notifications...')
      await user.type(input, 'nonexistent_query_xyz')

      await waitFor(() => {
        expect(
          screen.getByText('No notifications match your search criteria')
        ).toBeInTheDocument()
      })
    })
  })

  describe('Read status filtering', () => {
    it('filters to show only read notifications', async () => {
      const user = userEvent.setup()
      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [
          createNotification({ id: '1', title: 'Unread One', is_read: false }),
          createNotification({ id: '2', title: 'Read One', is_read: true }),
        ],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      const [statusFilter] = screen.getAllByRole('combobox')
      await user.selectOptions(statusFilter, 'read')

      const table = screen.getByRole('table')
      expect(within(table).getByText('Read One')).toBeInTheDocument()
      expect(within(table).queryByText('Unread One')).not.toBeInTheDocument()
    })
  })

  describe('Type filtering', () => {
    it('filters notifications by specific type', async () => {
      const user = userEvent.setup()
      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [
          createNotification({ id: '1', type: 'task_created', title: 'Task One' }),
          createNotification({ id: '2', type: 'annotation_completed', title: 'Annotation Done' }),
        ],
        unreadCount: 2,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      // Combobox order on the page: [0] read-status, [1] type, [2] date.
      const typeFilter = screen.getAllByRole('combobox')[1]
      await user.selectOptions(typeFilter, 'task_created')

      const table = screen.getByRole('table')
      expect(within(table).getByText('Task One')).toBeInTheDocument()
      expect(within(table).queryByText('Annotation Done')).not.toBeInTheDocument()
    })
  })

  describe('Load More and Pagination', () => {
    it('shows Load More button when hasMore is true', () => {
      const notifications = Array.from({ length: 20 }, (_, i) =>
        createNotification({
          id: String(i),
          title: `Task ${i}`,
          created_at: new Date().toISOString(),
        })
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

      render(<NotificationsPage />)

      // hasMore starts as true by default, and we have notifications
      expect(screen.getByText('Load More')).toBeInTheDocument()
    })

    it('calls fetchNotifications on Load More click', async () => {
      const user = userEvent.setup()
      const notifications = Array.from({ length: 5 }, (_, i) =>
        createNotification({
          id: String(i),
          title: `Task ${i}`,
          created_at: new Date().toISOString(),
        })
      )

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications,
        unreadCount: 5,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      ;(api.getNotifications as jest.Mock).mockResolvedValue([])

      render(<NotificationsPage />)

      const loadMoreButton = screen.getByText('Load More')
      await user.click(loadMoreButton)

      await waitFor(() => {
        expect(api.getNotifications).toHaveBeenCalled()
      })
    })
  })

  describe('Notification click navigation', () => {
    it('navigates to project page on notification click with project_id', async () => {
      const user = userEvent.setup()
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

      const row = screen.getByText('A new task has been created').closest('tr')
      if (row) {
        await user.click(row)
      }

      await waitFor(() => {
        expect(mockPush).toHaveBeenCalledWith('/projects/456')
      })
    })
  })

  describe('Read notification badge', () => {
    it('shows "Read" badge for read notifications', () => {
      const notification = createNotification({ is_read: true })

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

      const table = screen.getByRole('table')
      expect(within(table).getByText('Read')).toBeInTheDocument()
    })
  })

  describe('Mark all as read flow', () => {
    it('marks all as read and updates additional notifications', async () => {
      const user = userEvent.setup()

      ;(useNotifications as jest.Mock).mockReturnValue({
        notifications: [createNotification({ id: '1' })],
        unreadCount: 3,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead.mockResolvedValue(undefined),
        refreshNotifications: mockRefreshNotifications,
        fetchNotifications: mockFetchNotifications,
      })

      render(<NotificationsPage />)

      const markAllButton = screen.getByText(/mark all read \(3\)/i)
      await user.click(markAllButton)

      await waitFor(() => {
        expect(mockMarkAllAsRead).toHaveBeenCalled()
      })
    })
  })
})
