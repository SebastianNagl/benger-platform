/**
 * @jest-environment jsdom
 *
 * Complement coverage for NotificationsPage focused on the reachable PARTIAL
 * branches the existing page.test / page.branches / page.coverage / pagination
 * suites leave half-covered:
 *
 *   - line 128: the "today" date filter EXCLUDING a row created before today
 *     (the false-arm of `created < startOfDay`).
 *   - line 136: the client-side search cascade matching on MESSAGE and on TYPE
 *     (existing tests only exercise the title-match arm).
 *   - the page-level loading view replacing the table while a pagination fetch
 *     is in flight (the `hookLoading || loading` arm — which also makes the
 *     Load More button's own `loading ? spinner` cond-arm at line 692
 *     unreachable, since `loading` true swaps in the outer view first).
 *
 * The unwired bulk-select handlers (handleSelectNotification / handleSelectAll /
 * handleBulk*), the unused getTypeLabel helper, and the page-1 reset path of
 * fetchNotifications are NOT exercised here: they are unreachable through the
 * rendered component (no checkboxes are wired, getTypeLabel has no callsite,
 * and handleLoadMore always calls fetchNotifications with reset=false). See the
 * final report note.
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
        'notifications.noNotifications': 'No Notifications',
        'notifications.noMatches': 'No notifications match',
        'notifications.noNotificationsDescription': 'No notifications yet',
        'notifications.columnNotification': 'Notification',
        'notifications.columnTime': 'Time',
        'notifications.columnStatus': 'Status',
        'notifications.analyticsTitle': 'Notification Analytics',
        'navigation.dashboard': 'Dashboard',
      }
      let result = translations[key]
      if (!result) {
        return typeof defaultValueOrVars === 'string' ? defaultValueOrVars : key
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

// Combobox order: [0] read-status, [1] type, [2] date.
const getDateFilter = () => screen.getAllByRole('combobox')[2]

describe('NotificationsPage - reachable partial-branch complement', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    ;(useRouter as jest.Mock).mockReturnValue({ push: jest.fn() })
    ;(useAuth as jest.Mock).mockReturnValue({ user: mockUser, apiClient: {} })
    ;(api.getNotifications as jest.Mock).mockResolvedValue([])
  })

  describe('client-side date filter excludes older rows (line 128 false-arm)', () => {
    it('hides a notification created before today when the "today" filter is active', async () => {
      const user = userEvent.setup()
      const twoDaysAgo = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString()
      renderWith([
        createNotification({ id: 'old', title: 'Old Task', created_at: twoDaysAgo }),
        createNotification({ id: 'new', title: 'New Task', created_at: new Date().toISOString() }),
      ])

      // Both visible before filtering.
      expect(screen.getByText('Old Task')).toBeInTheDocument()
      expect(screen.getByText('New Task')).toBeInTheDocument()

      await user.selectOptions(getDateFilter(), 'today')

      // The pre-today row is filtered out; today's row remains.
      await waitFor(() => {
        expect(screen.queryByText('Old Task')).not.toBeInTheDocument()
      })
      expect(screen.getByText('New Task')).toBeInTheDocument()
    })
  })

  describe('search matches message and type, not only title (line 136 OR-arms)', () => {
    it('keeps a row whose MESSAGE matches the query even when its title does not', async () => {
      const user = userEvent.setup()
      renderWith([
        createNotification({ id: 'a', title: 'Alpha', message: 'contains keyword needle' }),
        createNotification({ id: 'b', title: 'Beta', message: 'unrelated body' }),
      ])

      const input = screen.getByPlaceholderText('Search notifications...')
      await user.type(input, 'needle')

      // After the debounce, the non-matching row drops out and the
      // message-matched row stays.
      await waitFor(() => {
        expect(screen.queryByText('Beta')).not.toBeInTheDocument()
      })
      expect(screen.getByText('Alpha')).toBeInTheDocument()
    })

    it('keeps a row whose TYPE matches the query even when title and message do not', async () => {
      const user = userEvent.setup()
      renderWith([
        createNotification({
          id: 'a',
          title: 'Alpha',
          message: 'body',
          type: 'member_joined',
        }),
        createNotification({
          id: 'b',
          title: 'Beta',
          message: 'body',
          type: 'task_created',
        }),
      ])

      // "member_joined" only appears in the TYPE field of row a.
      const input = screen.getByPlaceholderText('Search notifications...')
      await user.type(input, 'member_joined')

      await waitFor(() => {
        expect(screen.queryByText('Beta')).not.toBeInTheDocument()
      })
      expect(screen.getByText('Alpha')).toBeInTheDocument()
    })
  })

  describe('page-level loading view takes over while paginating', () => {
    it('swaps the whole list for the page loading spinner while the fetch is in flight', async () => {
      const user = userEvent.setup()

      // Hold the pagination fetch open so `loading` stays true; the page
      // replaces the table (and the Load More button) with the page-level
      // loading view rather than an inline button spinner.
      let resolveFetch: (v: any) => void = () => {}
      ;(api.getNotifications as jest.Mock).mockImplementation(
        () =>
          new Promise((resolve) => {
            resolveFetch = resolve
          })
      )

      renderWith([createNotification({ id: 'p1', title: 'Page1 Item' })])

      await user.click(screen.getByText('Load More'))

      // While loading, the row and the Load More button are gone.
      await waitFor(() => {
        expect(screen.queryByText('Load More')).not.toBeInTheDocument()
      })
      expect(screen.queryByText('Page1 Item')).not.toBeInTheDocument()

      // Settle the fetch so the list returns.
      await waitFor(() => expect(api.getNotifications).toHaveBeenCalled())
      resolveFetch([])
      await waitFor(() => {
        expect(screen.getByText('Page1 Item')).toBeInTheDocument()
      })
    })
  })
})
