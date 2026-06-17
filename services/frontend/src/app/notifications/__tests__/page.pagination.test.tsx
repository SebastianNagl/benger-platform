/**
 * @jest-environment jsdom
 *
 * Pagination-focused coverage for NotificationsPage.
 *
 * The page-1 path just refreshes the hook; the interesting, previously
 * uncovered code is the `fetchNotifications(pageNum > 1)` branch reached by
 * "Load More". It builds a URLSearchParams from the active filters
 * (read_status / type / from_date for today|week|month / search) and calls
 * api.getNotifications. These tests drive each filter and then paginate to
 * assert the constructed query string.
 */

import { useAuth } from '@/contexts/AuthContext'
import { useNotifications } from '@/hooks/useNotifications'
import { api } from '@/lib/api'
import { render, screen, waitFor } from '@testing-library/react'
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
    markNotificationsBulkAsRead: jest.fn(),
    deleteNotificationsBulk: jest.fn(),
  },
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(() => ({
    t: (key: string, defaultValueOrVars?: any, vars?: any) => {
      const translations: Record<string, string> = {
        'notifications.title': 'Notifications',
        'notifications.subtitle': 'Subtitle',
        'notifications.searchPlaceholder': 'Search notifications...',
        'notifications.all': 'All Status',
        'notifications.unread': 'Unread',
        'notifications.read': 'Read',
        'notifications.allTypes': 'All Types',
        'notifications.allTime': 'All Time',
        'notifications.today': 'Today',
        'notifications.pastWeek': 'Past Week',
        'notifications.pastMonth': 'Past Month',
        'notifications.loadMore': 'Load More',
        'notifications.loadingMore': 'Loading more...',
        'notifications.loadFailed': 'Failed to load notifications',
        'notifications.new': 'New',
        'notifications.columnNotification': 'Notification',
        'notifications.columnTime': 'Time',
        'notifications.columnStatus': 'Status',
        'notifications.analyticsTitle': 'Notification Analytics',
        'navigation.dashboard': 'Dashboard',
      }
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
    // Exercise the `locale === 'de' ? de : undefined` ternary (line 68).
    locale: 'de',
  })),
}))

jest.mock('date-fns/locale', () => ({ de: { code: 'de' } }))

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
  CheckCircleIcon: (props: any) => <svg data-testid="cc-icon" {...props} />,
  CheckIcon: (props: any) => <svg data-testid="check-icon" {...props} />,
  ExclamationTriangleIcon: (props: any) => <svg data-testid="warn-icon" {...props} />,
  InformationCircleIcon: (props: any) => <svg data-testid="info-icon" {...props} />,
  UserPlusIcon: (props: any) => <svg data-testid="up-icon" {...props} />,
  XMarkIcon: (props: any) => <svg data-testid="x-icon" {...props} />,
  ChartBarIcon: (props: any) => <svg data-testid="chart-icon" {...props} />,
  TrashIcon: (props: any) => <svg data-testid="trash-icon" {...props} />,
}))

jest.mock('next/link', () => ({
  __esModule: true,
  default: ({ children, href, ...props }: any) => (
    <a href={href} {...props}>
      {children}
    </a>
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
    <button onClick={onClick} disabled={disabled} {...props}>
      {children}
    </button>
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
  SelectItem: ({ value, children }: any) => <option value={value}>{children}</option>,
}))

jest.mock('@/components/shared/FilterToolbar', () => {
  const FilterToolbar = ({
    searchValue,
    onSearchChange,
    searchPlaceholder,
    children,
    rightExtras,
  }: any) => (
    <div data-testid="filter-toolbar">
      {onSearchChange && (
        <input
          data-testid="filter-toolbar-search"
          type="search"
          placeholder={searchPlaceholder}
          title={searchPlaceholder}
          value={searchValue ?? ''}
          onChange={(e) => onSearchChange(e.target.value)}
        />
      )}
      <div data-testid="filter-toolbar-fields">{children}</div>
      {rightExtras}
    </div>
  )
  // eslint-disable-next-line react/display-name
  FilterToolbar.Field = ({ children }: any) => <div>{children}</div>
  return { FilterToolbar }
})

const mockMarkAsRead = jest.fn()
const mockMarkAllAsRead = jest.fn()
const mockRefreshNotifications = jest.fn()
const mockFetchNotifications = jest.fn()

const mockUser = { id: '1', username: 'u', email: 'u@example.com', name: 'U' }

const createNotification = (overrides?: any) => ({
  id: '1',
  type: 'task_created',
  title: 'A Task',
  message: 'msg',
  is_read: false,
  created_at: new Date().toISOString(),
  ...overrides,
})

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

// Combobox order on the page: [0] read-status, [1] type, [2] date.
const getStatusFilter = () => screen.getAllByRole('combobox')[0]
const getTypeFilter = () => screen.getAllByRole('combobox')[1]
const getDateFilter = () => screen.getAllByRole('combobox')[2]

describe('NotificationsPage - pagination param construction', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    ;(useRouter as jest.Mock).mockReturnValue({ push: jest.fn() })
    ;(useAuth as jest.Mock).mockReturnValue({ user: mockUser, apiClient: {} })
    ;(api.getNotifications as jest.Mock).mockResolvedValue([])
  })

  const lastQuery = () => {
    const calls = (api.getNotifications as jest.Mock).mock.calls
    return calls[calls.length - 1][0] as string
  }

  it('paginates with read_status=true when the read filter is active', async () => {
    const user = userEvent.setup()
    renderWith([createNotification({ is_read: true })])

    await user.selectOptions(getStatusFilter(), 'read')
    await user.click(screen.getByText('Load More'))

    await waitFor(() => expect(api.getNotifications).toHaveBeenCalled())
    const q = lastQuery()
    expect(q).toContain('page=2')
    expect(q).toContain('read_status=true')
  })

  it('paginates with read_status=false when the unread filter is active', async () => {
    const user = userEvent.setup()
    renderWith([createNotification({ is_read: false })])

    await user.selectOptions(getStatusFilter(), 'unread')
    await user.click(screen.getByText('Load More'))

    await waitFor(() => expect(api.getNotifications).toHaveBeenCalled())
    expect(lastQuery()).toContain('read_status=false')
  })

  it('paginates with the type param when a type filter is active', async () => {
    const user = userEvent.setup()
    renderWith([createNotification({ type: 'task_created' })])

    await user.selectOptions(getTypeFilter(), 'task_created')
    await user.click(screen.getByText('Load More'))

    await waitFor(() => expect(api.getNotifications).toHaveBeenCalled())
    expect(lastQuery()).toContain('type=task_created')
  })

  it('paginates with a from_date param for the "today" date filter', async () => {
    const user = userEvent.setup()
    renderWith([createNotification({ created_at: new Date().toISOString() })])

    await user.selectOptions(getDateFilter(), 'today')
    await user.click(screen.getByText('Load More'))

    await waitFor(() => expect(api.getNotifications).toHaveBeenCalled())
    expect(lastQuery()).toContain('from_date=')
  })

  it('paginates with a from_date param for the "week" date filter', async () => {
    const user = userEvent.setup()
    renderWith([createNotification({ created_at: new Date().toISOString() })])

    await user.selectOptions(getDateFilter(), 'week')
    await user.click(screen.getByText('Load More'))

    await waitFor(() => expect(api.getNotifications).toHaveBeenCalled())
    expect(lastQuery()).toContain('from_date=')
  })

  it('paginates with a from_date param for the "month" date filter', async () => {
    const user = userEvent.setup()
    renderWith([createNotification({ created_at: new Date().toISOString() })])

    await user.selectOptions(getDateFilter(), 'month')
    await user.click(screen.getByText('Load More'))

    await waitFor(() => expect(api.getNotifications).toHaveBeenCalled())
    expect(lastQuery()).toContain('from_date=')
  })

  it('appends a search param when a search term is set, then paginates', async () => {
    const user = userEvent.setup()
    renderWith([createNotification({ title: 'Findable Task' })])

    const input = screen.getByPlaceholderText('Search notifications...')
    await user.type(input, 'Findable')

    // The debounced filter eventually narrows to the matching row.
    await waitFor(() =>
      expect(screen.getByText('Findable Task')).toBeInTheDocument()
    )

    await user.click(screen.getByText('Load More'))

    await waitFor(() => expect(api.getNotifications).toHaveBeenCalled())
    expect(lastQuery()).toContain('search=Findable')
  })

  it('keeps hasMore true and appends results when a full page (20) returns', async () => {
    const user = userEvent.setup()
    const page2 = Array.from({ length: 20 }, (_, i) =>
      createNotification({ id: `p2-${i}`, title: `Page2 ${i}` })
    )
    ;(api.getNotifications as jest.Mock).mockResolvedValue(page2)

    renderWith([createNotification({ id: 'p1', title: 'Page1 Item' })])

    await user.click(screen.getByText('Load More'))

    // The appended page-2 rows show up in the table.
    await waitFor(() =>
      expect(screen.getByText('Page2 0')).toBeInTheDocument()
    )
    // Load More is still offered because a full page came back.
    expect(screen.getByText('Load More')).toBeInTheDocument()
  })

  it('shows the load error message when pagination fetch rejects', async () => {
    const user = userEvent.setup()
    ;(api.getNotifications as jest.Mock).mockRejectedValue(new Error('boom'))
    const errSpy = jest.spyOn(console, 'error').mockImplementation(() => {})

    renderWith([createNotification({ id: 'p1', title: 'Page1 Item' })])

    await user.click(screen.getByText('Load More'))

    await waitFor(() =>
      expect(screen.getByText('Failed to load notifications')).toBeInTheDocument()
    )
    errSpy.mockRestore()
  })
})
