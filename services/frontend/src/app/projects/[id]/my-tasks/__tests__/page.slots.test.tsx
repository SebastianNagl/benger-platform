/**
 * My Tasks page — extended solver slots in each row: the result of the own
 * submission and the per-row actions cluster (stopPropagation so the row click
 * is untouched). The row click opens the review modal for a submitted task.
 *
 * @jest-environment jsdom
 */
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { registerSlot } from '@/lib/extensions/slots'
import { useProjectStore } from '@/stores/projectStore'
import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import MyTasksPage from '../page'

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(() => ({ push: jest.fn(), replace: jest.fn() })),
  useParams: jest.fn(() => ({ id: 'proj-1' })),
  useSearchParams: jest.fn(() => new URLSearchParams()),
  usePathname: jest.fn(() => '/'),
}))
jest.mock('@/contexts/AuthContext', () => ({ useAuth: jest.fn() }))
jest.mock('@/contexts/I18nContext', () => ({ useI18n: jest.fn() }))
jest.mock('@/stores/projectStore', () => ({ useProjectStore: jest.fn() }))
// Stable: addToast is a dep of the page's loadMyTasks callback.
const mockToast = { addToast: jest.fn() }
jest.mock('@/components/shared/Toast', () => ({ useToast: () => mockToast }))

const stableT = (k: string) => k
const task = {
  id: 't1',
  inner_id: 1,
  is_labeled: true,
  has_evaluation: true,
  has_feedback: false,
  assignment: null,
}

describe('MyTasksPage — extended slots', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    ;(useAuth as jest.Mock).mockReturnValue({ user: { id: 'u1' } })
    ;(useI18n as jest.Mock).mockReturnValue({ t: stableT })
    ;(useProjectStore as jest.Mock).mockReturnValue({
      currentProject: { id: 'proj-1', title: 'P' },
      fetchProject: jest.fn(),
      loading: false,
    })
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          tasks: [task],
          total: 1,
          page: 1,
          page_size: 20,
          pages: 1,
        }),
    }) as any
  })
  afterEach(() => {
    registerSlot('MyTaskRowResult', null as any)
    registerSlot('MyTaskRowActions', null as any)
    registerSlot('MyTaskEvaluationModal', null as any)
  })

  it('renders the row result for a submitted task and opens its review modal', async () => {
    const summary = { status: 'completed', grade_points: 11 }
    ;(global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          tasks: [
            { ...task, has_evaluation: false, grade_summary: summary },
            {
              id: 't2',
              inner_id: 2,
              is_labeled: false,
              has_evaluation: false,
              has_feedback: false,
              grade_summary: null,
              assignment: null,
            },
          ],
          total: 2,
          page: 1,
          page_size: 20,
          pages: 1,
        }),
    })
    const RowResult = jest.fn(({ task: rowTask }: any) => (
      <span data-testid="row-result">
        {String(rowTask.grade_summary.grade_points)}
      </span>
    ))
    registerSlot('MyTaskRowResult', RowResult)
    registerSlot('MyTaskEvaluationModal', ({ taskId }: any) => (
      <div data-testid="review-modal">{taskId}</div>
    ))
    render(<MyTasksPage />)
    // Only the submitted task gets a result; the open one has none.
    const results = await screen.findAllByTestId('row-result')
    expect(results).toHaveLength(1)
    expect(results[0]).toHaveTextContent('11')
    expect(RowResult.mock.calls[0][0].projectId).toBe('proj-1')
    expect(screen.queryByTestId('my-tasks-result-card')).not.toBeInTheDocument()
    // A submission still waiting for its grading (no evaluation row yet)
    // opens the review modal for that task.
    fireEvent.click(screen.getAllByTestId('my-task-item')[0])
    expect(await screen.findByTestId('review-modal')).toHaveTextContent('t1')
  })

  it('renders rows without a result in the community edition', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          tasks: [{ ...task, grade_summary: null }],
          total: 1,
          page: 1,
          page_size: 20,
          pages: 1,
        }),
    })
    render(<MyTasksPage />)
    expect(await screen.findByTestId('my-task-item')).toBeInTheDocument()
    expect(
      screen.queryByTestId('my-task-row-result-t1'),
    ).not.toBeInTheDocument()
  })

  it('renders row actions inside the row without triggering the row click', async () => {
    registerSlot('MyTaskRowActions', ({ task }: any) => (
      <button data-testid="row-action">{task.id}</button>
    ))
    const Modal = jest.fn(() => <div data-testid="review-modal" />)
    registerSlot('MyTaskEvaluationModal', Modal)
    render(<MyTasksPage />)
    const action = await screen.findByTestId('row-action')
    expect(action).toHaveTextContent('t1')
    fireEvent.click(action)
    await waitFor(() =>
      expect(screen.queryByTestId('review-modal')).not.toBeInTheDocument(),
    )
    fireEvent.click(screen.getByTestId('my-task-item'))
    expect(await screen.findByTestId('review-modal')).toBeInTheDocument()
  })
})
