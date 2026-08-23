/**
 * My Tasks page — extended solver slots: the result card above the list and
 * the per-row actions cluster (stopPropagation so the row click is untouched).
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
const task = { id: 't1', inner_id: 1, is_labeled: true, has_evaluation: true, has_feedback: false, assignment: null }

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
      json: () => Promise.resolve({ tasks: [task], total: 1, page: 1, page_size: 20, pages: 1 }),
    }) as any
  })
  afterEach(() => {
    registerSlot('MyTasksResultCard', null as any)
    registerSlot('MyTaskRowActions', null as any)
    registerSlot('MyTaskEvaluationModal', null as any)
  })

  it('renders the result card with tasks and opens the review modal via onOpenReview', async () => {
    const Card = jest.fn(({ tasks, onOpenReview }: any) => (
      <button data-testid="result-card" onClick={() => onOpenReview(tasks[0].id)}>
        {tasks.length}
      </button>
    ))
    registerSlot('MyTasksResultCard', Card)
    registerSlot('MyTaskEvaluationModal', ({ taskId }: any) => <div data-testid="review-modal">{taskId}</div>)
    render(<MyTasksPage />)
    expect(await screen.findByTestId('result-card')).toHaveTextContent('1')
    expect(Card.mock.calls[0][0].projectId).toBe('proj-1')
    fireEvent.click(screen.getByTestId('result-card'))
    expect(await screen.findByTestId('review-modal')).toHaveTextContent('t1')
  })

  it('renders row actions inside the row without triggering the row click', async () => {
    registerSlot('MyTaskRowActions', ({ task }: any) => <button data-testid="row-action">{task.id}</button>)
    const Modal = jest.fn(() => <div data-testid="review-modal" />)
    registerSlot('MyTaskEvaluationModal', Modal)
    render(<MyTasksPage />)
    const action = await screen.findByTestId('row-action')
    expect(action).toHaveTextContent('t1')
    fireEvent.click(action)
    await waitFor(() => expect(screen.queryByTestId('review-modal')).not.toBeInTheDocument())
    fireEvent.click(screen.getByTestId('my-task-item'))
    expect(await screen.findByTestId('review-modal')).toBeInTheDocument()
  })
})
