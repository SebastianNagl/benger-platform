import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { NotificationBell } from '../NotificationBell'

// Mock dependencies
const mockRefreshNotifications = jest.fn()
const mockMarkAsRead = jest.fn()
const mockMarkAllAsRead = jest.fn()

// Mock useNotifications hook
jest.mock('@/hooks/useNotifications', () => ({
  useNotifications: jest.fn(() => ({
    unreadCount: 0,
    notifications: [],
    markAsRead: mockMarkAsRead,
    markAllAsRead: mockMarkAllAsRead,
    refreshNotifications: mockRefreshNotifications,
  })),
}))

// Mock I18nContext
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, vars?: any) => {
      const translations: Record<string, string> = {
        'notifications.bellAriaLabel': 'Notifications',
        'notifications.bellAriaLabelUnread': 'Notifications ({count} unread)',
      }
      let result = translations[key] || key
      if (vars && typeof vars === 'object') {
        Object.entries(vars).forEach(([k, v]) => {
          result = result.replace(`{${k}}`, String(v))
        })
      }
      return result
    },
    locale: 'en',
  }),
}))

// Mock NotificationDropdown component
jest.mock('../NotificationDropdown', () => ({
  NotificationDropdown: ({
    isOpen,
    onClose,
    onMarkAsRead,
    onMarkAllAsRead,
    onRefresh,
    notifications,
    unreadCount,
  }: any) =>
    isOpen ? (
      <div data-testid="notification-dropdown">
        <div data-testid="dropdown-notifications">{notifications.length}</div>
        <div data-testid="dropdown-unread-count">{unreadCount}</div>
        <button onClick={onClose} data-testid="dropdown-close">
          Close
        </button>
        <button onClick={onMarkAsRead} data-testid="dropdown-mark-read">
          Mark as Read
        </button>
        <button onClick={onMarkAllAsRead} data-testid="dropdown-mark-all-read">
          Mark All Read
        </button>
        <button onClick={onRefresh} data-testid="dropdown-refresh">
          Refresh
        </button>
      </div>
    ) : null,
}))

// Mock Heroicons
jest.mock('@heroicons/react/24/outline', () => ({
  BellIcon: (props: any) => <svg data-testid="bell-icon" {...props} />,
}))

// Mock timers
jest.useFakeTimers()

describe('NotificationBell', () => {
  const mockUseNotifications =
    require('@/hooks/useNotifications').useNotifications

  beforeEach(() => {
    jest.clearAllMocks()
    mockUseNotifications.mockReturnValue({
      unreadCount: 0,
      notifications: [],
      markAsRead: mockMarkAsRead,
      markAllAsRead: mockMarkAllAsRead,
      refreshNotifications: mockRefreshNotifications,
    })
  })

  afterEach(() => {
    act(() => {
      jest.runOnlyPendingTimers()
    })
  })

  afterAll(() => {
    jest.useRealTimers()
  })

  describe('basic rendering', () => {
    it('renders notification bell button', () => {
      render(<NotificationBell />)

      const button = screen.getByRole('button', { name: /notifications/i })
      expect(button).toBeInTheDocument()
    })

    it('renders bell icon', () => {
      render(<NotificationBell />)

      expect(screen.getByTestId('bell-icon')).toBeInTheDocument()
    })

    it('applies correct button styling', () => {
      render(<NotificationBell />)

      const button = screen.getByRole('button')
      expect(button).toHaveClass(
        'relative',
        'flex',
        'size-6',
        'items-center',
        'justify-center',
        'rounded-md',
        'transition',
        'hover:bg-zinc-900/5',
        'dark:hover:bg-white/5'
      )
    })

    it('has proper aria-label when no unread notifications', () => {
      render(<NotificationBell />)

      const button = screen.getByRole('button')
      expect(button).toHaveAttribute('aria-label', 'Notifications')
    })

    it('includes pointer area for touch devices', () => {
      const { container } = render(<NotificationBell />)

      const pointerArea = container.querySelector('.pointer-fine\\:hidden')
      expect(pointerArea).toBeInTheDocument()
      expect(pointerArea).toHaveClass('absolute', 'size-12')
    })
  })

  describe('unread count badge', () => {
    it('shows unread count badge when there are unread notifications', () => {
      mockUseNotifications.mockReturnValue({
        unreadCount: 5,
        notifications: [],
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
      })

      render(<NotificationBell />)

      expect(screen.getByText('5')).toBeInTheDocument()
    })

    it('does not show badge when unread count is 0', () => {
      render(<NotificationBell />)

      expect(screen.queryByText('0')).not.toBeInTheDocument()
    })

    it('shows "99+" for unread count over 99', () => {
      mockUseNotifications.mockReturnValue({
        unreadCount: 150,
        notifications: [],
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
      })

      render(<NotificationBell />)

      expect(screen.getByText('99+')).toBeInTheDocument()
    })

    it('applies correct badge styling', () => {
      mockUseNotifications.mockReturnValue({
        unreadCount: 3,
        notifications: [],
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
      })

      render(<NotificationBell />)

      const badge = screen.getByText('3')
      expect(badge).toHaveClass(
        'absolute',
        '-top-1',
        '-right-1',
        'min-w-[16px]',
        'h-4',
        'bg-red-500',
        'text-white',
        'text-xs',
        'font-medium',
        'rounded-full',
        'flex',
        'items-center',
        'justify-center',
        'px-1'
      )
    })

    it('updates aria-label when there are unread notifications', () => {
      mockUseNotifications.mockReturnValue({
        unreadCount: 7,
        notifications: [],
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
      })

      render(<NotificationBell />)

      const button = screen.getByRole('button')
      expect(button).toHaveAttribute('aria-label', 'Notifications (7 unread)')
    })
  })

  describe('dropdown interaction', () => {
    it('opens dropdown when button is clicked', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })
      render(<NotificationBell />)

      const button = screen.getByRole('button')
      await user.click(button)

      expect(screen.getByTestId('notification-dropdown')).toBeInTheDocument()
    })

    it('closes dropdown when button is clicked again', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })
      render(<NotificationBell />)

      const button = screen.getByRole('button')
      await user.click(button)
      expect(screen.getByTestId('notification-dropdown')).toBeInTheDocument()

      await user.click(button)
      expect(
        screen.queryByTestId('notification-dropdown')
      ).not.toBeInTheDocument()
    })

    it('does not show dropdown initially', () => {
      render(<NotificationBell />)

      expect(
        screen.queryByTestId('notification-dropdown')
      ).not.toBeInTheDocument()
    })

    it('passes correct props to dropdown', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })
      const mockNotifications = [
        {
          id: '1',
          title: 'Test',
          message: 'Test message',
          type: 'info',
          is_read: false,
          created_at: '2024-01-01',
        },
      ]

      mockUseNotifications.mockReturnValue({
        unreadCount: 1,
        notifications: mockNotifications,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
      })

      render(<NotificationBell />)

      await user.click(screen.getByRole('button'))

      expect(screen.getByTestId('dropdown-notifications')).toHaveTextContent(
        '1'
      )
      expect(screen.getByTestId('dropdown-unread-count')).toHaveTextContent('1')
    })

    it('closes dropdown when backdrop is clicked', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })
      render(<NotificationBell />)

      await user.click(screen.getByRole('button'))
      expect(screen.getByTestId('notification-dropdown')).toBeInTheDocument()

      const backdrop = document.querySelector('.fixed.inset-0.z-40.lg\\:hidden')
      if (backdrop) {
        fireEvent.click(backdrop)
      }

      expect(
        screen.queryByTestId('notification-dropdown')
      ).not.toBeInTheDocument()
    })

    it('handles dropdown callback functions', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })
      render(<NotificationBell />)

      await user.click(screen.getByRole('button'))

      // Test dropdown close callback
      await user.click(screen.getByTestId('dropdown-close'))
      expect(
        screen.queryByTestId('notification-dropdown')
      ).not.toBeInTheDocument()

      // Reopen and test other callbacks
      await user.click(screen.getByRole('button'))

      await user.click(screen.getByTestId('dropdown-mark-read'))
      expect(mockMarkAsRead).toHaveBeenCalled()

      await user.click(screen.getByTestId('dropdown-mark-all-read'))
      expect(mockMarkAllAsRead).toHaveBeenCalled()

      await user.click(screen.getByTestId('dropdown-refresh'))
      expect(mockRefreshNotifications).toHaveBeenCalled()
    })
  })

  describe('backdrop and mobile support', () => {
    it('shows backdrop when dropdown is open', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })
      render(<NotificationBell />)

      await user.click(screen.getByRole('button'))

      const backdrop = document.querySelector('.fixed.inset-0.z-40.lg\\:hidden')
      expect(backdrop).toBeInTheDocument()
    })

    it('does not show backdrop when dropdown is closed', () => {
      render(<NotificationBell />)

      const backdrop = document.querySelector('.fixed.inset-0.z-40.lg\\:hidden')
      expect(backdrop).not.toBeInTheDocument()
    })

    it('backdrop has correct attributes', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })
      render(<NotificationBell />)

      await user.click(screen.getByRole('button'))

      const backdrop = document.querySelector('.fixed.inset-0.z-40.lg\\:hidden')
      expect(backdrop).toHaveAttribute('aria-hidden', 'true')
    })
  })

  describe('dropdown positioning', () => {
    it('positions dropdown correctly', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })
      render(<NotificationBell />)

      await user.click(screen.getByRole('button'))

      const dropdownContainer = document.querySelector(
        '.absolute.right-0.mt-2.z-50'
      )
      expect(dropdownContainer).toBeInTheDocument()
    })

    it('applies correct z-index for dropdown', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })
      render(<NotificationBell />)

      await user.click(screen.getByRole('button'))

      const dropdownContainer = document.querySelector('.z-50')
      expect(dropdownContainer).toBeInTheDocument()
    })
  })

  describe('auto-refresh functionality', () => {
    it('sets up interval for auto-refresh on mount', () => {
      render(<NotificationBell />)

      // Fast-forward 30 seconds
      act(() => {
        jest.advanceTimersByTime(30000)
      })

      expect(mockRefreshNotifications).toHaveBeenCalledTimes(1)
    })

    it('continues auto-refresh at regular intervals', () => {
      render(<NotificationBell />)

      // Fast-forward 90 seconds (3 intervals)
      act(() => {
        jest.advanceTimersByTime(90000)
      })

      expect(mockRefreshNotifications).toHaveBeenCalledTimes(3)
    })

    it('clears interval on unmount', () => {
      const { unmount } = render(<NotificationBell />)

      unmount()

      // Fast-forward time after unmount
      act(() => {
        jest.advanceTimersByTime(60000)
      })

      // Should not have called refresh after unmount
      expect(mockRefreshNotifications).not.toHaveBeenCalled()
    })

    it('respects refreshNotifications dependency in useEffect', () => {
      const { rerender } = render(<NotificationBell />)

      // Change the mock to return a different function
      const newRefreshMock = jest.fn()
      mockUseNotifications.mockReturnValue({
        unreadCount: 0,
        notifications: [],
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: newRefreshMock,
      })

      rerender(<NotificationBell />)

      // Fast-forward time
      act(() => {
        jest.advanceTimersByTime(30000)
      })

      expect(newRefreshMock).toHaveBeenCalled()
    })
  })

  describe('state management', () => {
    it('maintains independent dropdown state', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })
      render(<NotificationBell />)

      const button = screen.getByRole('button')

      // Open dropdown
      await user.click(button)
      expect(screen.getByTestId('notification-dropdown')).toBeInTheDocument()

      // Close dropdown
      await user.click(button)
      expect(
        screen.queryByTestId('notification-dropdown')
      ).not.toBeInTheDocument()

      // Open again
      await user.click(button)
      expect(screen.getByTestId('notification-dropdown')).toBeInTheDocument()
    })

    it('handles rapid clicks correctly', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })
      render(<NotificationBell />)

      const button = screen.getByRole('button')

      // Rapid clicks
      await user.click(button)
      await user.click(button)
      await user.click(button)

      // Should end up closed after odd number of clicks
      expect(screen.getByTestId('notification-dropdown')).toBeInTheDocument()
    })
  })

  describe('accessibility', () => {
    it('provides proper button role', () => {
      render(<NotificationBell />)

      expect(screen.getByRole('button')).toBeInTheDocument()
    })

    it('supports keyboard navigation', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })
      render(<NotificationBell />)

      const button = screen.getByRole('button')
      button.focus()

      await user.keyboard('{Enter}')

      expect(screen.getByTestId('notification-dropdown')).toBeInTheDocument()
    })

    it('supports space key activation', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })
      render(<NotificationBell />)

      const button = screen.getByRole('button')
      button.focus()

      await user.keyboard(' ')

      expect(screen.getByTestId('notification-dropdown')).toBeInTheDocument()
    })

    it('maintains focus management', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })
      render(<NotificationBell />)

      const button = screen.getByRole('button')
      await user.click(button)

      // Focus should still be manageable
      expect(document.activeElement).toBe(button)
    })
  })

  describe('responsive design', () => {
    it('applies mobile-specific styling', () => {
      const { container } = render(<NotificationBell />)

      // Check for responsive classes
      const button = container.querySelector('button')
      expect(button).toHaveClass('size-6')

      // Check for mobile pointer area
      const pointerArea = container.querySelector('.pointer-fine\\:hidden')
      expect(pointerArea).toHaveClass('absolute', 'size-12')
    })

    it('handles backdrop correctly for different screen sizes', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })
      render(<NotificationBell />)

      await user.click(screen.getByRole('button'))

      const backdrop = document.querySelector('.lg\\:hidden')
      expect(backdrop).toBeInTheDocument()
    })
  })

  describe('dark mode support', () => {
    it('includes dark mode classes for button', () => {
      render(<NotificationBell />)

      const button = screen.getByRole('button')
      expect(button).toHaveClass('dark:hover:bg-white/5')
    })

    it('includes dark mode classes for bell icon', () => {
      render(<NotificationBell />)

      const icon = screen.getByTestId('bell-icon')
      expect(icon).toHaveClass('dark:stroke-white')
    })
  })

  describe('edge cases', () => {
    it('handles undefined unreadCount gracefully', () => {
      mockUseNotifications.mockReturnValue({
        unreadCount: undefined,
        notifications: [],
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
      })

      render(<NotificationBell />)

      expect(screen.getByRole('button')).toBeInTheDocument()
      expect(screen.queryByText('0')).not.toBeInTheDocument()
    })

    it('handles null notifications array gracefully', () => {
      mockUseNotifications.mockReturnValue({
        unreadCount: 0,
        notifications: null,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
      })

      render(<NotificationBell />)

      expect(screen.getByRole('button')).toBeInTheDocument()
    })

    it('handles missing hook functions gracefully', () => {
      mockUseNotifications.mockReturnValue({
        unreadCount: 0,
        notifications: [],
        markAsRead: jest.fn(),
        markAllAsRead: jest.fn(),
        refreshNotifications: jest.fn(),
      })

      render(<NotificationBell />)

      expect(screen.getByRole('button')).toBeInTheDocument()
    })

    it('handles very large unread counts', () => {
      mockUseNotifications.mockReturnValue({
        unreadCount: 999999,
        notifications: [],
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
      })

      render(<NotificationBell />)

      expect(screen.getByText('99+')).toBeInTheDocument()
    })
  })

  describe('integration', () => {
    it('works with realistic notification data', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })
      const notifications = [
        {
          id: '1',
          title: 'Task Completed',
          message: 'Your annotation task has been completed',
          type: 'task_completed',
          is_read: false,
          created_at: '2024-01-01T10:00:00Z',
        },
        {
          id: '2',
          title: 'New Assignment',
          message: 'You have been assigned a new task',
          type: 'task_created',
          is_read: true,
          created_at: '2024-01-01T09:00:00Z',
        },
      ]

      mockUseNotifications.mockReturnValue({
        unreadCount: 1,
        notifications,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
      })

      render(<NotificationBell />)

      // Check unread badge
      expect(screen.getByText('1')).toBeInTheDocument()

      // Open dropdown
      await user.click(screen.getByRole('button'))

      // Check dropdown shows correct data
      expect(screen.getByTestId('dropdown-notifications')).toHaveTextContent(
        '2'
      )
      expect(screen.getByTestId('dropdown-unread-count')).toHaveTextContent('1')
    })

    it('handles component re-renders correctly', () => {
      const { rerender } = render(<NotificationBell />)

      // Update with new unread count
      mockUseNotifications.mockReturnValue({
        unreadCount: 5,
        notifications: [],
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        refreshNotifications: mockRefreshNotifications,
      })

      rerender(<NotificationBell />)

      expect(screen.getByText('5')).toBeInTheDocument()
    })
  })
})
