/**
 * @jest-environment jsdom
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Notification, NotificationDropdown } from '../NotificationDropdown'

// Mock date-fns
jest.mock('date-fns', () => ({
  formatDistanceToNow: jest.fn(() => '5 minutes ago'),
}))

// Mock date-fns locale
jest.mock('date-fns/locale', () => ({
  de: {},
}))

// Mock I18nContext
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, defaultValue?: any) => {
      const translations: Record<string, string> = {
        'notifications.title': 'Notifications',
        'notifications.unread': 'unread',
        'notifications.refresh': 'Refresh notifications',
        'notifications.markAllRead': 'Mark all as read',
        'notifications.close': 'Close notifications',
        'notifications.empty': 'No notifications yet',
        'notifications.viewAll': 'View all notifications',
      }
      return (
        translations[key] ||
        (typeof defaultValue === 'string' ? defaultValue : key)
      )
    },
    locale: 'en',
    changeLocale: jest.fn(),
    isReady: true,
  }),
}))

// Mock notificationTranslation
jest.mock('@/lib/notificationTranslation', () => ({
  getTranslatedNotification: (_t: any, notification: any) => ({
    title: notification.title,
    message: notification.message,
  }),
}))

// Mock Heroicons
jest.mock('@heroicons/react/24/outline', () => ({
  ArrowPathIcon: (props: any) => <svg data-testid="refresh-icon" {...props} />,
  CheckCircleIcon: (props: any) => (
    <svg data-testid="check-circle-icon" {...props} />
  ),
  CheckIcon: (props: any) => <svg data-testid="check-icon" {...props} />,
  ExclamationTriangleIcon: (props: any) => (
    <svg data-testid="exclamation-icon" {...props} />
  ),
  InformationCircleIcon: (props: any) => (
    <svg data-testid="info-icon" {...props} />
  ),
  UserPlusIcon: (props: any) => <svg data-testid="user-plus-icon" {...props} />,
  XMarkIcon: (props: any) => <svg data-testid="x-mark-icon" {...props} />,
}))

describe('NotificationDropdown', () => {
  const mockOnClose = jest.fn()
  const mockOnMarkAsRead = jest.fn()
  const mockOnMarkAllAsRead = jest.fn()
  const mockOnRefresh = jest.fn()

  const defaultProps = {
    isOpen: true,
    notifications: [],
    unreadCount: 0,
    onClose: mockOnClose,
    onMarkAsRead: mockOnMarkAsRead,
    onMarkAllAsRead: mockOnMarkAllAsRead,
    onRefresh: mockOnRefresh,
  }

  const createNotification = (
    overrides?: Partial<Notification>
  ): Notification => ({
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
  })

  describe('Basic Rendering', () => {
    it('renders dropdown when isOpen is true', () => {
      render(<NotificationDropdown {...defaultProps} />)

      expect(screen.getByText('Notifications')).toBeInTheDocument()
    })

    it('does not render when isOpen is false', () => {
      render(<NotificationDropdown {...defaultProps} isOpen={false} />)

      expect(screen.queryByText('Notifications')).not.toBeInTheDocument()
    })

    it('renders header with title', () => {
      render(<NotificationDropdown {...defaultProps} />)

      expect(
        screen.getByRole('heading', { name: /notifications/i })
      ).toBeInTheDocument()
    })

    it('applies correct container styling', () => {
      const { container } = render(<NotificationDropdown {...defaultProps} />)

      const dropdown = container.firstChild
      expect(dropdown).toHaveClass(
        'w-96',
        'max-w-sm',
        'rounded-lg',
        'bg-white',
        'shadow-lg',
        'ring-1',
        'ring-black',
        'ring-opacity-5',
        'dark:bg-zinc-900',
        'dark:ring-zinc-700'
      )
    })

    it('renders refresh button', () => {
      render(<NotificationDropdown {...defaultProps} />)

      const refreshButton = screen.getByTitle('Refresh notifications')
      expect(refreshButton).toBeInTheDocument()
      expect(screen.getByTestId('refresh-icon')).toBeInTheDocument()
    })

    it('renders close button', () => {
      render(<NotificationDropdown {...defaultProps} />)

      const closeButton = screen.getByTitle('Close notifications')
      expect(closeButton).toBeInTheDocument()
      expect(screen.getByTestId('x-mark-icon')).toBeInTheDocument()
    })

    it('shows unread count in header when present', () => {
      render(<NotificationDropdown {...defaultProps} unreadCount={5} />)

      expect(screen.getByText('(5 unread)')).toBeInTheDocument()
    })

    it('does not show unread count when zero', () => {
      render(<NotificationDropdown {...defaultProps} unreadCount={0} />)

      expect(screen.queryByText('unread')).not.toBeInTheDocument()
    })
  })

  describe('Notification List Display', () => {
    it('renders all notifications', () => {
      const notifications = [
        createNotification({ id: '1', title: 'First Notification' }),
        createNotification({ id: '2', title: 'Second Notification' }),
        createNotification({ id: '3', title: 'Third Notification' }),
      ]

      render(
        <NotificationDropdown {...defaultProps} notifications={notifications} />
      )

      expect(screen.getByText('First Notification')).toBeInTheDocument()
      expect(screen.getByText('Second Notification')).toBeInTheDocument()
      expect(screen.getByText('Third Notification')).toBeInTheDocument()
    })

    it('displays notification message', () => {
      const notification = createNotification({
        message: 'This is a test message',
      })

      render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[notification]}
        />
      )

      expect(screen.getByText('This is a test message')).toBeInTheDocument()
    })

    it('displays notification timestamp', () => {
      const notification = createNotification()

      render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[notification]}
        />
      )

      expect(screen.getByText('5 minutes ago')).toBeInTheDocument()
    })

    it('shows unread indicator for unread notifications', () => {
      const notification = createNotification({ is_read: false })

      const { container } = render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[notification]}
        />
      )

      const unreadIndicator = container.querySelector(
        '.h-2.w-2.flex-shrink-0.rounded-full.bg-emerald-600'
      )
      expect(unreadIndicator).toBeInTheDocument()
    })

    it('does not show unread indicator for read notifications', () => {
      const notification = createNotification({ is_read: true })

      const { container } = render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[notification]}
        />
      )

      const unreadIndicator = container.querySelector(
        '.h-2.w-2.flex-shrink-0.rounded-full.bg-emerald-600'
      )
      expect(unreadIndicator).not.toBeInTheDocument()
    })

    it('applies different background for unread notifications', () => {
      const unreadNotification = createNotification({ is_read: false })
      const readNotification = createNotification({
        id: '2',
        is_read: true,
        title: 'Read Notification',
      })

      const { container } = render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[unreadNotification, readNotification]}
        />
      )

      const notifications = container.querySelectorAll('.cursor-pointer')
      expect(notifications[0]).toHaveClass('bg-zinc-50', 'dark:bg-zinc-800')
    })

    it('renders correct icon for task_created type', () => {
      const notification = createNotification({ type: 'task_created' })

      render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[notification]}
        />
      )

      expect(screen.getByTestId('info-icon')).toBeInTheDocument()
    })

    it('renders correct icon for task_completed type', () => {
      const notification = createNotification({ type: 'task_completed' })

      render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[notification]}
        />
      )

      expect(screen.getByTestId('check-circle-icon')).toBeInTheDocument()
    })

    it('renders correct icon for evaluation_failed type', () => {
      const notification = createNotification({ type: 'evaluation_failed' })

      render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[notification]}
        />
      )

      expect(screen.getByTestId('exclamation-icon')).toBeInTheDocument()
    })

    it('renders correct icon for organization_invitation_sent type', () => {
      const notification = createNotification({
        type: 'organization_invitation_sent',
      })

      render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[notification]}
        />
      )

      expect(screen.getByTestId('user-plus-icon')).toBeInTheDocument()
    })

    it('uses default icon for unknown notification type', () => {
      const notification = createNotification({ type: 'unknown_type' })

      render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[notification]}
        />
      )

      expect(screen.getByTestId('info-icon')).toBeInTheDocument()
    })

    it('applies correct color for task_created type', () => {
      const notification = createNotification({ type: 'task_created' })

      const { container } = render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[notification]}
        />
      )

      const iconContainer = container.querySelector(
        '.text-blue-600.bg-blue-100.dark\\:text-blue-400.dark\\:bg-blue-900'
      )
      expect(iconContainer).toBeInTheDocument()
    })

    it('applies correct color for evaluation_failed type', () => {
      const notification = createNotification({ type: 'evaluation_failed' })

      const { container } = render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[notification]}
        />
      )

      const iconContainer = container.querySelector(
        '.text-red-600.bg-red-100.dark\\:text-red-400.dark\\:bg-red-900'
      )
      expect(iconContainer).toBeInTheDocument()
    })

    it('applies correct color for task_completed type', () => {
      const notification = createNotification({ type: 'task_completed' })

      const { container } = render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[notification]}
        />
      )

      const iconContainer = container.querySelector(
        '.text-green-600.bg-green-100.dark\\:text-green-400.dark\\:bg-green-900'
      )
      expect(iconContainer).toBeInTheDocument()
    })
  })

  describe('Mark as Read Functionality', () => {
    it('calls onMarkAsRead when clicking unread notification', async () => {
      const user = userEvent.setup()
      const notification = createNotification({ id: '123', is_read: false })

      render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[notification]}
        />
      )

      const notificationItem = screen.getByText('Task Created')
      await user.click(notificationItem)

      expect(mockOnMarkAsRead).toHaveBeenCalledWith('123')
      expect(mockOnMarkAsRead).toHaveBeenCalledTimes(1)
    })

    it('does not call onMarkAsRead when clicking read notification', async () => {
      const user = userEvent.setup()
      const notification = createNotification({ id: '123', is_read: true })

      render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[notification]}
        />
      )

      const notificationItem = screen.getByText('Task Created')
      await user.click(notificationItem)

      expect(mockOnMarkAsRead).not.toHaveBeenCalled()
    })

    it('renders mark all as read button when there are unread notifications', () => {
      render(<NotificationDropdown {...defaultProps} unreadCount={3} />)

      expect(screen.getByTitle('Mark all as read')).toBeInTheDocument()
    })

    it('does not render mark all as read button when all notifications are read', () => {
      render(<NotificationDropdown {...defaultProps} unreadCount={0} />)

      expect(screen.queryByTitle('Mark all as read')).not.toBeInTheDocument()
    })

    it('calls onMarkAllAsRead when clicking mark all as read button', async () => {
      const user = userEvent.setup()

      render(<NotificationDropdown {...defaultProps} unreadCount={5} />)

      const markAllButton = screen.getByTitle('Mark all as read')
      await user.click(markAllButton)

      expect(mockOnMarkAllAsRead).toHaveBeenCalledTimes(1)
    })
  })

  describe('Clear All Functionality', () => {
    it('calls onRefresh when clicking refresh button', async () => {
      const user = userEvent.setup()

      render(<NotificationDropdown {...defaultProps} />)

      const refreshButton = screen.getByTitle('Refresh notifications')
      await user.click(refreshButton)

      expect(mockOnRefresh).toHaveBeenCalledTimes(1)
    })

    it('refresh button has correct styling', () => {
      render(<NotificationDropdown {...defaultProps} />)

      const refreshButton = screen.getByTitle('Refresh notifications')
      expect(refreshButton).toHaveClass(
        'rounded-full',
        'p-1',
        'text-zinc-400',
        'transition-colors',
        'hover:bg-zinc-100',
        'hover:text-zinc-600',
        'dark:hover:bg-zinc-700',
        'dark:hover:text-zinc-300'
      )
    })
  })

  describe('Empty State', () => {
    it('shows empty state when no notifications', () => {
      render(<NotificationDropdown {...defaultProps} notifications={[]} />)

      expect(screen.getByText('No notifications yet')).toBeInTheDocument()
    })

    it('renders empty state icon', () => {
      render(<NotificationDropdown {...defaultProps} notifications={[]} />)

      expect(screen.getByTestId('info-icon')).toBeInTheDocument()
    })

    it('applies correct styling to empty state icon', () => {
      const { container } = render(
        <NotificationDropdown {...defaultProps} notifications={[]} />
      )

      const icon = container.querySelector(
        '.mx-auto.mb-2.h-8.w-8.text-zinc-300.dark\\:text-zinc-600'
      )
      expect(icon).toBeInTheDocument()
    })

    it('does not show footer when no notifications', () => {
      render(<NotificationDropdown {...defaultProps} notifications={[]} />)

      expect(
        screen.queryByText('View all notifications')
      ).not.toBeInTheDocument()
    })

    it('shows footer when there are notifications', () => {
      const notification = createNotification()

      render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[notification]}
        />
      )

      expect(screen.getByText('View all notifications')).toBeInTheDocument()
    })
  })

  describe('User Interaction', () => {
    it('calls onClose when clicking close button', async () => {
      const user = userEvent.setup()

      render(<NotificationDropdown {...defaultProps} />)

      const closeButton = screen.getByTitle('Close notifications')
      await user.click(closeButton)

      expect(mockOnClose).toHaveBeenCalledTimes(1)
    })

    it('handles clicking notification with task_id in data', async () => {
      const user = userEvent.setup()
      const notification = createNotification({
        data: { task_id: '456', project_id: '789' },
        is_read: false,
      })

      render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[notification]}
        />
      )

      const notificationItem = screen.getByText('Task Created')
      await user.click(notificationItem)

      expect(mockOnMarkAsRead).toHaveBeenCalledWith('1')
    })

    it('handles clicking notification without task_id', async () => {
      const user = userEvent.setup()
      const notification = createNotification({ data: {}, is_read: false })

      render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[notification]}
        />
      )

      const notificationItem = screen.getByText('Task Created')
      await user.click(notificationItem)

      expect(mockOnMarkAsRead).toHaveBeenCalledWith('1')
    })

    it('closes dropdown when clicking view all', async () => {
      const user = userEvent.setup()
      const notification = createNotification()

      render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[notification]}
        />
      )

      const viewAllButton = screen.getByText('View all notifications')
      await user.click(viewAllButton)

      expect(mockOnClose).toHaveBeenCalled()
    })

    it('notification items have cursor pointer', () => {
      const notification = createNotification()

      const { container } = render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[notification]}
        />
      )

      const notificationItem = container.querySelector('.cursor-pointer')
      expect(notificationItem).toBeInTheDocument()
    })

    it('notification items show hover effect', () => {
      const notification = createNotification()

      const { container } = render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[notification]}
        />
      )

      const notificationItem = container.querySelector('.cursor-pointer')
      expect(notificationItem).toHaveClass(
        'hover:bg-zinc-50',
        'dark:hover:bg-zinc-700'
      )
    })
  })

  describe('Accessibility', () => {
    it('provides heading for notifications section', () => {
      render(<NotificationDropdown {...defaultProps} />)

      expect(
        screen.getByRole('heading', { name: /notifications/i })
      ).toBeInTheDocument()
    })

    it('buttons have descriptive titles', () => {
      render(<NotificationDropdown {...defaultProps} unreadCount={1} />)

      expect(screen.getByTitle('Refresh notifications')).toBeInTheDocument()
      expect(screen.getByTitle('Mark all as read')).toBeInTheDocument()
      expect(screen.getByTitle('Close notifications')).toBeInTheDocument()
    })

    it('refresh button is keyboard accessible', async () => {
      const user = userEvent.setup()

      render(<NotificationDropdown {...defaultProps} />)

      const refreshButton = screen.getByTitle('Refresh notifications')
      refreshButton.focus()

      await user.keyboard('{Enter}')

      expect(mockOnRefresh).toHaveBeenCalled()
    })

    it('close button is keyboard accessible', async () => {
      const user = userEvent.setup()

      render(<NotificationDropdown {...defaultProps} />)

      const closeButton = screen.getByTitle('Close notifications')
      closeButton.focus()

      await user.keyboard('{Enter}')

      expect(mockOnClose).toHaveBeenCalled()
    })

    it('notification items are clickable', async () => {
      const user = userEvent.setup()
      const notification = createNotification({ is_read: false })

      render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[notification]}
        />
      )

      const notificationItem = screen
        .getByText('Task Created')
        .closest('.cursor-pointer')
      expect(notificationItem).toBeInTheDocument()

      await user.click(notificationItem!)

      expect(mockOnMarkAsRead).toHaveBeenCalledWith('1')
    })
  })

  describe('Edge Cases', () => {
    it('handles notification without data field', () => {
      const notification = createNotification()
      delete notification.data

      render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[notification]}
        />
      )

      expect(screen.getByText('Task Created')).toBeInTheDocument()
    })

    it('handles notification with empty data', () => {
      const notification = createNotification({ data: {} })

      render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[notification]}
        />
      )

      expect(screen.getByText('Task Created')).toBeInTheDocument()
    })

    it('handles very long notification titles', () => {
      const notification = createNotification({
        title:
          'This is a very long notification title that should be truncated',
      })

      render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[notification]}
        />
      )

      expect(
        screen.getByText(
          'This is a very long notification title that should be truncated'
        )
      ).toBeInTheDocument()
    })

    it('handles very long notification messages', () => {
      const notification = createNotification({
        message:
          'This is a very long notification message that contains a lot of text and should be handled appropriately by the component',
      })

      render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[notification]}
        />
      )

      expect(
        screen.getByText(
          'This is a very long notification message that contains a lot of text and should be handled appropriately by the component'
        )
      ).toBeInTheDocument()
    })

    it('handles large number of notifications', () => {
      const notifications = Array.from({ length: 50 }, (_, i) =>
        createNotification({
          id: `${i}`,
          title: `Notification ${i}`,
        })
      )

      const { container } = render(
        <NotificationDropdown {...defaultProps} notifications={notifications} />
      )

      const scrollContainer = container.querySelector(
        '.max-h-96.overflow-y-auto'
      )
      expect(scrollContainer).toBeInTheDocument()
    })

    it('handles unreadCount greater than notification length', () => {
      const notification = createNotification()

      render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[notification]}
          unreadCount={10}
        />
      )

      expect(screen.getByText('(10 unread)')).toBeInTheDocument()
    })

    it('handles negative unreadCount gracefully', () => {
      render(<NotificationDropdown {...defaultProps} unreadCount={-1} />)

      expect(screen.queryByText('unread')).not.toBeInTheDocument()
    })

    it('handles notification with organization_id', () => {
      const notification = createNotification({
        organization_id: 'org-123',
      })

      render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[notification]}
        />
      )

      expect(screen.getByText('Task Created')).toBeInTheDocument()
    })

    it('handles null notification message', () => {
      const notification = createNotification({ message: '' })

      render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[notification]}
        />
      )

      expect(screen.getByText('Task Created')).toBeInTheDocument()
    })

    it('handles invalid date format gracefully', () => {
      const notification = createNotification({
        created_at: 'invalid-date',
      })

      render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[notification]}
        />
      )

      expect(screen.getByText('5 minutes ago')).toBeInTheDocument()
    })

    it('handles multiple rapid clicks on same notification', async () => {
      const user = userEvent.setup()
      const notification = createNotification({ is_read: false })

      render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[notification]}
        />
      )

      const notificationItem = screen.getByText('Task Created')
      await user.click(notificationItem)
      await user.click(notificationItem)
      await user.click(notificationItem)

      expect(mockOnMarkAsRead).toHaveBeenCalledTimes(3)
    })

    it('handles clicking different buttons rapidly', async () => {
      const user = userEvent.setup()

      render(<NotificationDropdown {...defaultProps} unreadCount={5} />)

      const refreshButton = screen.getByTitle('Refresh notifications')
      const markAllButton = screen.getByTitle('Mark all as read')
      const closeButton = screen.getByTitle('Close notifications')

      await user.click(refreshButton)
      await user.click(markAllButton)
      await user.click(closeButton)

      expect(mockOnRefresh).toHaveBeenCalledTimes(1)
      expect(mockOnMarkAllAsRead).toHaveBeenCalledTimes(1)
      expect(mockOnClose).toHaveBeenCalledTimes(1)
    })
  })

  describe('Dark Mode Support', () => {
    it('includes dark mode classes for container', () => {
      const { container } = render(<NotificationDropdown {...defaultProps} />)

      const dropdown = container.firstChild
      expect(dropdown).toHaveClass('dark:bg-zinc-900', 'dark:ring-zinc-700')
    })

    it('includes dark mode classes for header border', () => {
      const { container } = render(<NotificationDropdown {...defaultProps} />)

      const header = container.querySelector('.border-b')
      expect(header).toHaveClass('dark:border-zinc-700')
    })

    it('includes dark mode classes for buttons', () => {
      render(<NotificationDropdown {...defaultProps} />)

      const refreshButton = screen.getByTitle('Refresh notifications')
      expect(refreshButton).toHaveClass(
        'dark:hover:bg-zinc-700',
        'dark:hover:text-zinc-300'
      )
    })

    it('includes dark mode classes for empty state text', () => {
      const { container } = render(
        <NotificationDropdown {...defaultProps} notifications={[]} />
      )

      const emptyText = screen.getByText('No notifications yet')
      expect(emptyText.parentElement).toHaveClass('dark:text-zinc-400')
    })

    it('includes dark mode classes for notification dividers', () => {
      const notifications = [
        createNotification({ id: '1' }),
        createNotification({ id: '2' }),
      ]

      const { container } = render(
        <NotificationDropdown {...defaultProps} notifications={notifications} />
      )

      const divider = container.querySelector('.divide-y')
      expect(divider).toHaveClass('dark:divide-zinc-700')
    })

    it('includes dark mode classes for footer border', () => {
      const notification = createNotification()

      const { container } = render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[notification]}
        />
      )

      const footer = container.querySelector('.border-t')
      expect(footer).toHaveClass('dark:border-zinc-700')
    })

    it('includes dark mode classes for view all button', () => {
      const notification = createNotification()

      render(
        <NotificationDropdown
          {...defaultProps}
          notifications={[notification]}
        />
      )

      const viewAllButton = screen.getByText('View all notifications')
      expect(viewAllButton).toHaveClass(
        'dark:text-blue-400',
        'dark:hover:text-blue-300'
      )
    })
  })
})
