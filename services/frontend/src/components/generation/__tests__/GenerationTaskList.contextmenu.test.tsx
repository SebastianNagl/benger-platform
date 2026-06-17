/**
 * Behavioral coverage for GenerationTaskList's right-click context menu and
 * the per-cell generate / regenerate flow (handleCellGenerate).
 *
 * The existing GenerationTaskList.test.tsx exercises the table, WebSocket,
 * search/filter, pagination and modal-open paths but never:
 *   - opens the cell context menu (onContextMenu) and clicks its buttons
 *     (View Results, Generate, Regenerate)
 *   - drives handleCellGenerate -> apiClient.post success (queued toast +
 *     refetch) and failure (error toast)
 *   - renders the multi-run progress badge (runs_requested > 1)
 *
 * This file targets exactly those branches. It mirrors the existing file's
 * mocking idiom (inline jest.mock of @/lib/api/client, AuthContext, I18n,
 * the two child modals and FilterToolbar) but adds a `post` mock and asserts
 * on the global Toast mock from setupTests.
 */
import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { mockToast } from '@/test-utils/setupTests'
import { GenerationTaskList } from '../GenerationTaskList'

// Minimal WebSocket stub (the component opens one on mount).
class NoopWebSocket {
  url: string
  onopen: ((e: Event) => void) | null = null
  onmessage: ((e: MessageEvent) => void) | null = null
  onerror: ((e: Event) => void) | null = null
  onclose: ((e: CloseEvent) => void) | null = null
  readyState = 1
  constructor(url: string) {
    this.url = url
  }
  send() {}
  close() {}
}
global.WebSocket = jest.fn((url: string) => new NoopWebSocket(url)) as any

// Project payload returned by GET /projects/:id — used by handleCellGenerate
// to build structure_keys.
const projectPayload = {
  id: 'test-project',
  generation_config: {
    prompt_structures: { gliederung: {}, loesung: {} },
  },
}

// Task-status payload. task-1/model-1 is completed (hasResults -> View
// Results available), task-1/model-2 is "not generated" (status null ->
// Generate). model-3 carries multi-run progress (runs_requested > 1) so the
// badge renders.
const taskStatusPayload = {
  tasks: [
    {
      id: 'task-1aaaaaa',
      data: { text: 'First task content' },
      created_at: '2025-01-01',
      generation_status: {
        'model-1': [{ status: 'completed', generation_id: 'gen-1', error_message: null }],
        'model-2': [],
        'model-3': [
          {
            status: 'running',
            generation_id: 'gen-3',
            error_message: null,
            runs_requested: 3,
            runs_completed: 1,
            runs_failed: 1,
          },
        ],
      },
    },
  ],
  total: 1,
  page: 1,
  page_size: 50,
  total_pages: 1,
  models: ['model-1', 'model-2', 'model-3'],
  structures: ['gliederung', 'loesung'],
}

const mockPost = jest.fn()
const mockGet = jest.fn((url: string) => {
  if (url.startsWith('/projects/')) return Promise.resolve(projectPayload)
  return Promise.resolve(taskStatusPayload)
})

jest.mock('@/lib/api/client', () => ({
  apiClient: {
    get: (url: string) => mockGet(url),
    post: (url: string, body: any) => mockPost(url, body),
  },
  getApiUrl: jest.fn(() => 'http://localhost'),
}))

const mockUseAuth = jest.fn()
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, arg2?: any, arg3?: any) => {
      const vars = typeof arg2 === 'object' ? arg2 : arg3
      const translations: Record<string, string> = {
        'generation.taskList.task': 'Task',
        'generation.taskList.startGeneration': 'Start Generation',
        'generation.taskList.viewResults': 'View Results',
        'generation.taskList.generate': 'Generate',
        'generation.taskList.regenerate': 'Regenerate',
        'generation.taskList.cellGenerationQueued': 'Generation queued',
        'generation.taskList.cellGenerationFailed': 'Generation failed',
        'generation.taskList.notYetGenerated': 'Not yet generated',
        'generation.taskList.clickToView': 'Click to view',
      }
      let result = translations[key] || key
      if (vars) {
        Object.entries(vars).forEach(([k, v]) => {
          result = result.replace(`{${k}}`, String(v))
        })
      }
      return result
    },
    locale: 'en',
  }),
}))

// Child modals -> lightweight stand-ins.
jest.mock('../GenerationControlModal', () => ({
  GenerationControlModal: ({ onClose }: any) => (
    <div role="dialog" data-testid="control-modal">
      <button onClick={onClose}>close</button>
    </div>
  ),
}))
jest.mock('../GenerationResultModal', () => ({
  GenerationResultModal: ({ onClose }: any) => (
    <div role="dialog" data-testid="result-modal">
      <button onClick={onClose} data-testid="result-close">
        close
      </button>
    </div>
  ),
}))

jest.mock('@/components/shared/FilterToolbar', () => {
  const FilterToolbar = ({ children, leftExtras, rightExtras }: any) => (
    <div data-testid="filter-toolbar">
      {leftExtras}
      {children}
      {rightExtras}
    </div>
  )
  FilterToolbar.Field = ({ children }: any) => <div>{children}</div>
  return { FilterToolbar }
})

/** Find the <td> cell for a given model column header. */
function cellForModel(model: string): HTMLElement {
  // Locate via the row's tds by index using the header order.
  const headers = screen.getAllByRole('columnheader').map((h) => h.textContent)
  const colIndex = headers.indexOf(model)
  const row = screen.getByText('First task content').closest('tr') as HTMLElement
  const tds = within(row).getAllByRole('cell')
  // tds[0] is the task column; model columns follow.
  return tds[colIndex] as HTMLElement
}

describe('GenerationTaskList context menu + cell generation', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGet.mockImplementation((url: string) => {
      if (url.startsWith('/projects/')) return Promise.resolve(projectPayload)
      return Promise.resolve(taskStatusPayload)
    })
    mockUseAuth.mockReturnValue({
      user: { is_superadmin: true },
      isLoading: false,
    })
  })

  it('renders the multi-run progress badge for runs_requested > 1', async () => {
    render(<GenerationTaskList projectId="test-project" />)
    await screen.findByText('First task content')

    // model-3 has runs_requested=3 across 1 structure -> badge "1/3" plus a
    // failed-run "!" marker. Both live inside the model-3 cell; assert on the
    // cell's combined text rather than an exact element match.
    await waitFor(() => {
      const cell = cellForModel('model-3')
      expect(cell.textContent?.replace(/\s/g, '')).toContain('1/3')
      expect(cell.textContent).toContain('!')
    })
  })

  it('opens the context menu on right-click and shows View Results + Regenerate for a completed cell', async () => {
    render(<GenerationTaskList projectId="test-project" />)
    await screen.findByText('First task content')

    const cell = cellForModel('model-1')
    fireEvent.contextMenu(cell)

    // hasResults -> View Results; status completed (not running) -> Regenerate.
    expect(await screen.findByText('View Results')).toBeInTheDocument()
    expect(screen.getByText('Regenerate')).toBeInTheDocument()
  })

  it('context menu "Generate" on an ungenerated cell posts and toasts success', async () => {
    mockPost.mockResolvedValue({ queued: true })
    render(<GenerationTaskList projectId="test-project" />)
    await screen.findByText('First task content')

    // model-2 has no statuses -> status null -> "Generate" label, no View Results.
    const cell = cellForModel('model-2')
    fireEvent.contextMenu(cell)

    const generateBtn = await screen.findByText('Generate')
    await userEvent.click(generateBtn)

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith(
        '/generation-tasks/projects/test-project/generate',
        expect.objectContaining({
          mode: 'single',
          model_ids: ['model-2'],
          task_ids: ['task-1aaaaaa'],
          structure_keys: ['gliederung', 'loesung'],
        })
      )
    })
    await waitFor(() => {
      expect(mockToast.success).toHaveBeenCalledWith('Generation queued')
    })
  })

  it('context menu "View Results" opens the result modal', async () => {
    render(<GenerationTaskList projectId="test-project" />)
    await screen.findByText('First task content')

    const cell = cellForModel('model-1')
    fireEvent.contextMenu(cell)

    const viewBtn = await screen.findByText('View Results')
    await userEvent.click(viewBtn)

    expect(await screen.findByTestId('result-modal')).toBeInTheDocument()
  })

  it('shows an error toast when cell generation POST fails', async () => {
    mockPost.mockRejectedValue({
      response: { data: { detail: 'Quota exceeded' } },
    })
    render(<GenerationTaskList projectId="test-project" />)
    await screen.findByText('First task content')

    const cell = cellForModel('model-2')
    fireEvent.contextMenu(cell)
    const generateBtn = await screen.findByText('Generate')
    await userEvent.click(generateBtn)

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith('Quota exceeded')
    })
  })

  it('falls back to the generic failure message when the error has no detail', async () => {
    mockPost.mockRejectedValue(new Error('network down'))
    render(<GenerationTaskList projectId="test-project" />)
    await screen.findByText('First task content')

    const cell = cellForModel('model-2')
    fireEvent.contextMenu(cell)
    const generateBtn = await screen.findByText('Generate')
    await userEvent.click(generateBtn)

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith('Generation failed')
    })
  })

  it('does not open a context menu for users who cannot start generation', async () => {
    mockUseAuth.mockReturnValue({
      user: { is_superadmin: false, role: 'ANNOTATOR' },
      isLoading: false,
    })
    render(<GenerationTaskList projectId="test-project" />)
    await screen.findByText('First task content')

    const cell = cellForModel('model-1')
    fireEvent.contextMenu(cell)

    // canStartGeneration === false -> the handler returns early, no menu.
    expect(screen.queryByText('View Results')).not.toBeInTheDocument()
    expect(screen.queryByText('Generate')).not.toBeInTheDocument()
  })
})
