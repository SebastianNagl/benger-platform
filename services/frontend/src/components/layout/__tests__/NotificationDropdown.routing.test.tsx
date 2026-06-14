/**
 * Behavioral tests for NotificationDropdown's deep-link routing.
 *
 * The sibling NotificationDropdown.test.tsx covers rendering, icons, colours,
 * mark-as-read and the empty/footer states, but it does NOT mock
 * next/navigation's useRouter, so the run-detail routing branches in
 * handleNotificationClick (evaluation_completed / evaluation_failed →
 * /evaluations/{id} or /runs?type=evaluation; llm_generation_completed →
 * /generations/{id} or /runs?type=generation; task_id+project_id → /projects)
 * were entirely uncovered. This file exercises those branches.
 *
 * @jest-environment jsdom
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Notification, NotificationDropdown } from '../NotificationDropdown'

const mockPush = jest.fn()

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
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

describe('NotificationDropdown — deep-link routing', () => {
  const onClose = jest.fn()
  const onMarkAsRead = jest.fn()

  const baseProps = {
    isOpen: true,
    notifications: [] as Notification[],
    unreadCount: 0,
    onClose,
    onMarkAsRead,
    onMarkAllAsRead: jest.fn(),
    onRefresh: jest.fn(),
  }

  const makeNotification = (overrides?: Partial<Notification>): Notification => ({
    id: 'n1',
    type: 'task_created',
    title: 'A notification',
    message: 'msg',
    is_read: false,
    created_at: '2024-01-01T10:00:00Z',
    ...overrides,
  })

  beforeEach(() => {
    jest.clearAllMocks()
  })

  async function clickNotification(notification: Notification) {
    const user = userEvent.setup()
    render(
      <NotificationDropdown {...baseProps} notifications={[notification]} />
    )
    await user.click(screen.getByText(notification.title))
  }

  it('routes evaluation_completed with evaluation_id to /evaluations/{id} and closes', async () => {
    await clickNotification(
      makeNotification({
        type: 'evaluation_completed',
        data: { evaluation_id: 'eval-42' },
      })
    )
    expect(mockPush).toHaveBeenCalledWith('/evaluations/eval-42')
    expect(onClose).toHaveBeenCalled()
  })

  it('routes evaluation_completed via the eval_run_id alias', async () => {
    await clickNotification(
      makeNotification({
        type: 'evaluation_completed',
        data: { eval_run_id: 'run-7' },
      })
    )
    expect(mockPush).toHaveBeenCalledWith('/evaluations/run-7')
  })

  it('falls back to /runs?type=evaluation when an evaluation notification has no id', async () => {
    await clickNotification(
      makeNotification({ type: 'evaluation_failed', data: {} })
    )
    expect(mockPush).toHaveBeenCalledWith('/runs?type=evaluation')
    expect(onClose).toHaveBeenCalled()
  })

  it('routes llm_generation_completed with generation_id to /generations/{id}', async () => {
    await clickNotification(
      makeNotification({
        type: 'llm_generation_completed',
        data: { generation_id: 'gen-9' },
      })
    )
    expect(mockPush).toHaveBeenCalledWith('/generations/gen-9')
    expect(onClose).toHaveBeenCalled()
  })

  it('routes llm_generation_completed via the response_generation_id alias', async () => {
    await clickNotification(
      makeNotification({
        type: 'llm_generation_completed',
        data: { response_generation_id: 'rg-3' },
      })
    )
    expect(mockPush).toHaveBeenCalledWith('/generations/rg-3')
  })

  it('falls back to /runs?type=generation when a generation notification has no id', async () => {
    await clickNotification(
      makeNotification({ type: 'llm_generation_completed', data: {} })
    )
    expect(mockPush).toHaveBeenCalledWith('/runs?type=generation')
  })

  it('routes a task notification with task_id + project_id to the project page', async () => {
    await clickNotification(
      makeNotification({
        type: 'task_assigned',
        data: { task_id: 't1', project_id: 'p1' },
      })
    )
    expect(mockPush).toHaveBeenCalledWith('/projects/p1')
    expect(onClose).toHaveBeenCalled()
  })

  it('does not route (only marks read) when a task notification lacks project_id', async () => {
    await clickNotification(
      makeNotification({ type: 'task_assigned', data: { task_id: 't1' } })
    )
    expect(mockPush).not.toHaveBeenCalled()
    expect(onMarkAsRead).toHaveBeenCalledWith('n1')
  })

  it('does not re-mark an already-read evaluation notification but still routes', async () => {
    await clickNotification(
      makeNotification({
        type: 'evaluation_completed',
        is_read: true,
        data: { evaluation_id: 'eval-1' },
      })
    )
    expect(onMarkAsRead).not.toHaveBeenCalled()
    expect(mockPush).toHaveBeenCalledWith('/evaluations/eval-1')
  })
})
