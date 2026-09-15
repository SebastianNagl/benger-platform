/**
 * NotificationDropdown routing for the "new grading on your submission"
 * notifications: a student opens the exam in the student shell, everyone else
 * the project's task list.
 *
 * @jest-environment jsdom
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Notification, NotificationDropdown } from '../NotificationDropdown'

const mockPush = jest.fn()
const mockUiMode = jest.fn(() => 'expert')

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}))

jest.mock('@/hooks/useResolvedUiMode', () => ({
  useResolvedUiMode: () => mockUiMode(),
}))

jest.mock('date-fns', () => ({
  formatDistanceToNow: jest.fn(() => '5 minutes ago'),
}))
jest.mock('date-fns/locale', () => ({ de: {} }))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, defaultValue?: any) =>
      typeof defaultValue === 'string' ? defaultValue : key,
    locale: 'en',
  }),
}))

jest.mock('@/lib/notificationTranslation', () => ({
  getTranslatedNotification: (_t: any, notification: any) => ({
    title: notification.title,
    message: notification.message,
  }),
}))

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

describe('NotificationDropdown: evaluation received routing', () => {
  const onClose = jest.fn()

  const makeNotification = (
    type: string,
    data?: Record<string, any>,
  ): Notification => ({
    id: 'n1',
    type,
    title: 'New grading',
    message: 'msg',
    data,
    is_read: true,
    created_at: new Date().toISOString(),
  })

  const renderWith = (notification: Notification) =>
    render(
      <NotificationDropdown
        isOpen
        notifications={[notification]}
        unreadCount={0}
        onClose={onClose}
        onMarkAsRead={jest.fn()}
        onMarkAllAsRead={jest.fn()}
        onRefresh={jest.fn()}
      />,
    )

  beforeEach(() => {
    jest.clearAllMocks()
    mockUiMode.mockReturnValue('expert')
  })

  it.each([
    'evaluation_received_human',
    'evaluation_received_immediate',
    'evaluation_received_batch',
  ])('opens the task list for %s in the expert shell', async (type) => {
    renderWith(
      makeNotification(type, {
        project_id: 'p1',
        project_kind: 'exam',
        task_id: 't1',
      }),
    )

    await userEvent.click(screen.getByText('New grading'))

    expect(mockPush).toHaveBeenCalledWith('/projects/p1/my-tasks')
    expect(onClose).toHaveBeenCalled()
  })

  it('opens the exam in the student shell', async () => {
    mockUiMode.mockReturnValue('student')
    renderWith(
      makeNotification('evaluation_received_human', {
        project_id: 'p1',
        project_kind: 'exam',
        task_id: 't1',
      }),
    )

    await userEvent.click(screen.getByText('New grading'))

    expect(mockPush).toHaveBeenCalledWith('/student/exams/p1')
    expect(onClose).toHaveBeenCalled()
  })

  it('opens the task list for a student on a non-exam project', async () => {
    mockUiMode.mockReturnValue('student')
    renderWith(
      makeNotification('evaluation_received_batch', {
        project_id: 'p1',
        project_kind: null,
      }),
    )

    await userEvent.click(screen.getByText('New grading'))

    expect(mockPush).toHaveBeenCalledWith('/projects/p1/my-tasks')
  })

  it('does not navigate without a project, even with a task id', async () => {
    renderWith(makeNotification('evaluation_received_human', { task_id: 't1' }))

    await userEvent.click(screen.getByText('New grading'))

    expect(mockPush).not.toHaveBeenCalled()
    expect(onClose).not.toHaveBeenCalled()
  })
})
