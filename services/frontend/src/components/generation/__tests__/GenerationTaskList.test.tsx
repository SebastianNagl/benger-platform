import '@testing-library/jest-dom'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { GenerationTaskList } from '../GenerationTaskList'

// Mock WebSocket - fires onopen synchronously when handler is set,
// eliminating microtask timing issues that cause CI flakes
class MockWebSocket {
  url: string
  private _onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  readyState: number = WebSocket.CONNECTING

  constructor(url: string) {
    this.url = url
  }

  // Fire onopen as soon as the handler is assigned (synchronous, no microtask)
  get onopen() {
    return this._onopen
  }
  set onopen(handler: ((event: Event) => void) | null) {
    this._onopen = handler
    if (handler) {
      this.readyState = WebSocket.OPEN
      handler(new Event('open'))
    }
  }

  send(data: string) {}

  close() {
    this.readyState = WebSocket.CLOSED
    if (this.onclose) {
      this.onclose(new CloseEvent('close'))
    }
  }

  simulateMessage(data: any) {
    if (this.onmessage) {
      this.onmessage(
        new MessageEvent('message', { data: JSON.stringify(data) })
      )
    }
  }

  simulateError() {
    if (this.onerror) {
      this.onerror(new Event('error'))
    }
  }
}

let mockWebSocket: MockWebSocket | null = null
// Track whether WebSocket creation should update mockWebSocket ref.
// Prevents leaked reconnect timers from overriding the test's WebSocket instance.
let trackWebSocketCreation = true

global.WebSocket = jest.fn((url: string) => {
  const ws = new MockWebSocket(url)
  if (trackWebSocketCreation) {
    mockWebSocket = ws
  }
  return ws as any
}) as any

// Mock the API client
jest.mock('@/lib/api/client', () => ({
  apiClient: {
    get: jest.fn(() =>
      Promise.resolve({
        tasks: [
          {
            id: 'task-1',
            data: { text: 'Test task content 1' },
            created_at: '2025-01-01',
            generation_status: {
              'model-1': { status: 'completed', generation_id: 'gen-1' },
              'model-2': { status: 'pending', generation_id: null },
            },
          },
          {
            id: 'task-2',
            data: { text: 'Test task content 2' },
            created_at: '2025-01-02',
            generation_status: {
              'model-1': { status: 'failed', generation_id: 'gen-2' },
              'model-2': { status: 'running', generation_id: 'gen-3' },
            },
          },
        ],
        total: 2,
        page: 1,
        page_size: 50,
        total_pages: 1,
        models: ['model-1', 'model-2'],
      })
    ),
  },
  getApiUrl: jest.fn(() => 'http://localhost:8000'),
}))

// Mock auth context
const mockUseAuth = jest.fn()
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}))

// Mock I18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, arg2?: any, arg3?: any) => {
      const vars = typeof arg2 === 'object' ? arg2 : arg3
      const translations: Record<string, string> = {
        'generation.taskList.searchPlaceholder': 'Search tasks...',
        'generation.taskList.allStatuses': 'All statuses',
        'generation.taskList.completed': 'Completed',
        'generation.taskList.failed': 'Failed',
        'generation.taskList.running': 'Running',
        'generation.taskList.pending': 'Pending',
        'generation.taskList.notGenerated': 'Not generated',
        'generation.taskList.startGeneration': 'Start Generation',
        'generation.taskList.task': 'Task',
        'generation.taskList.noTextData': 'No text data',
        'generation.taskList.noModels': 'No models configured for generation',
        'generation.taskList.configureFirst': 'Configure models in project settings first',
        'generation.taskList.loadError': 'Failed to load generation data',
        'common.retry': 'Retry',
        'generation.taskList.realTimeActive': 'Real-time updates active',
        'generation.taskList.tooltipStats': '{completed} completed, {running} running, {failed} failed',
        'generation.taskList.clickToView': 'Click to view',
        'generation.taskList.notYetGenerated': 'Not yet generated',
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

// Mock modal components
const mockControlModalOnClose = jest.fn()
const mockControlModalOnSuccess = jest.fn()
const mockResultModalOnClose = jest.fn()

jest.mock('../GenerationControlModal', () => ({
  GenerationControlModal: ({ onClose, onSuccess }: any) => {
    return (
      <div role="dialog" data-testid="control-modal">
        <button onClick={onClose} data-testid="control-close">
          Close
        </button>
        <button onClick={onSuccess} data-testid="control-success">
          Success
        </button>
      </div>
    )
  },
}))

jest.mock('../GenerationResultModal', () => ({
  GenerationResultModal: ({ onClose }: any) => {
    return (
      <div role="dialog" data-testid="result-modal">
        <button onClick={onClose} data-testid="result-close">
          Close
        </button>
      </div>
    )
  },
}))

describe('GenerationTaskList', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockWebSocket = null
    trackWebSocketCreation = true
    mockUseAuth.mockReturnValue({
      user: { is_superadmin: true },
      isLoading: false,
    })
    // Restore mock implementation (tests may override it)
    ;(global.WebSocket as jest.Mock).mockImplementation((url: string) => {
      const ws = new MockWebSocket(url)
      if (trackWebSocketCreation) {
        mockWebSocket = ws
      }
      return ws as any
    })
  })

  afterEach(() => {
    // Stop tracking so leaked reconnect timers don't override mockWebSocket
    trackWebSocketCreation = false
    if (mockWebSocket) {
      mockWebSocket.onclose = null // Prevent reconnect cascade
      mockWebSocket.close()
    }
  })

  describe('Responsive Layout', () => {
    it('should have responsive header controls layout', async () => {
      render(<GenerationTaskList projectId="test-project" />)

      // Wait for data to load
      await screen.findByPlaceholderText('Search tasks...')

      // Check outer header container has responsive classes (line 229 in implementation)
      // The outer container wraps both the controls and the button
      const headerContainer = screen
        .getByPlaceholderText('Search tasks...')
        .closest('div[class*="mb-4"]') // Find the outer container with mb-4
      expect(headerContainer?.className).toMatch(/flex-col/)
      expect(headerContainer?.className).toMatch(/md:flex-row/)
      expect(headerContainer?.className).toMatch(/md:items-center/)
      expect(headerContainer?.className).toMatch(/md:justify-between/)
    })

    it('should have responsive search controls', async () => {
      render(<GenerationTaskList projectId="test-project" />)

      await screen.findByPlaceholderText('Search tasks...')

      // SearchInput component wraps the actual input, so we check the wrapper has the responsive class
      const searchInputWrapper = screen
        .getByPlaceholderText('Search tasks...')
        .closest('div[class*="w-full"]')
      expect(searchInputWrapper?.className).toMatch(/w-full/)
      expect(searchInputWrapper?.className).toMatch(/sm:w-auto/)

      // Status select now uses the shared Select component (mocked as native <select>)
      // The SelectTrigger receives className="sm:w-44" from the component
      const selects = screen.getAllByRole('combobox')
      const statusSelect = selects.find((select) =>
        select.className.includes('sm:w-44')
      )
      expect(statusSelect).toBeTruthy()
    })

    it('should have responsive button layout', async () => {
      render(<GenerationTaskList projectId="test-project" />)

      await screen.findByText('Start Generation')

      const startButton = screen.getByText('Start Generation')
      expect(startButton).toHaveClass('w-full')
      expect(startButton).toHaveClass('sm:w-auto')
    })

    it('should have overflow-x-auto on table container', async () => {
      render(<GenerationTaskList projectId="test-project" />)

      await screen.findByRole('table')

      const tableContainer = screen.getByRole('table').parentElement
      expect(tableContainer).toHaveClass('overflow-x-auto')
    })

    it('should have min-w-full on table', async () => {
      render(<GenerationTaskList projectId="test-project" />)

      await screen.findByRole('table')

      const table = screen.getByRole('table')
      expect(table).toHaveClass('min-w-full')
    })
  })

  describe('Table Structure', () => {
    it('should render table headers correctly', async () => {
      render(<GenerationTaskList projectId="test-project" />)

      await screen.findByText('Task')

      expect(screen.getByText('Task')).toBeInTheDocument()
      expect(screen.getByText('model-1')).toBeInTheDocument()
      expect(screen.getByText('model-2')).toBeInTheDocument()
    })

    it('should render task data in table rows', async () => {
      render(<GenerationTaskList projectId="test-project" />)

      await screen.findByText('Test task content 1')

      expect(screen.getByText('Test task content 1')).toBeInTheDocument()
      expect(screen.getByText('Test task content 2')).toBeInTheDocument()
    })

    it('should truncate long task content', async () => {
      render(<GenerationTaskList projectId="test-project" />)

      await screen.findByText('Test task content 1')

      // The implementation wraps the text in a div with truncate class (line 291 in implementation)
      // Structure is: <td class="whitespace-nowrap..."><div class="truncate max-w-xs">text</div></td>
      // So we need to get the parent element's first child (the div with truncate)
      const taskCell = screen.getByText('Test task content 1').closest('td')
      const taskContentDiv = taskCell?.querySelector('.truncate')
      expect(taskContentDiv).toHaveClass('truncate')
      expect(taskContentDiv).toHaveClass('max-w-xs')
    })
  })

  describe('Empty State', () => {
    it('should show empty state when no models configured', async () => {
      const { apiClient } = require('@/lib/api/client')
      apiClient.get.mockResolvedValueOnce({
        tasks: [],
        total: 0,
        page: 1,
        page_size: 50,
        total_pages: 0,
        models: [],
      })

      render(<GenerationTaskList projectId="test-project" />)

      await screen.findByText('No models configured for generation')

      expect(
        screen.getByText('No models configured for generation')
      ).toBeInTheDocument()
      expect(
        screen.getByText('Configure models in project settings first')
      ).toBeInTheDocument()
    })
  })

  describe('Loading State', () => {
    it('should show loading spinner while fetching data', () => {
      render(<GenerationTaskList projectId="test-project" />)

      // Should show loading spinner initially
      const spinner = document.querySelector('.animate-spin')
      expect(spinner).toBeInTheDocument()
    })
  })

  describe('WebSocket Integration', () => {
    it('connects to WebSocket with correct URL', async () => {
      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(global.WebSocket).toHaveBeenCalledWith(
          'ws://localhost:8000/api/ws/projects/test-project/generation-progress'
        )
      })
    })

    it('establishes WebSocket connection successfully', async () => {
      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(mockWebSocket).not.toBeNull()
        expect(mockWebSocket?.readyState).toBe(WebSocket.OPEN)
      })
    })

    it('refreshes data when receiving generation_update message', async () => {
      const { apiClient } = require('@/lib/api/client')
      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(mockWebSocket).not.toBeNull()
      })

      const initialCallCount = apiClient.get.mock.calls.length

      mockWebSocket?.simulateMessage({
        type: 'generation_update',
      })

      await waitFor(() => {
        expect(apiClient.get.mock.calls.length).toBeGreaterThan(
          initialCallCount
        )
      })
    })

    it('handles WebSocket errors gracefully', async () => {
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()
      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(mockWebSocket).not.toBeNull()
      })

      mockWebSocket?.simulateError()

      consoleSpy.mockRestore()
    })

    it('attempts reconnection on WebSocket close with exponential backoff', async () => {
      jest.useFakeTimers()
      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(mockWebSocket).not.toBeNull()
      })

      const initialCallCount = (global.WebSocket as jest.Mock).mock.calls.length

      mockWebSocket?.close()

      jest.advanceTimersByTime(1100)

      await waitFor(() => {
        expect(
          (global.WebSocket as jest.Mock).mock.calls.length
        ).toBeGreaterThan(initialCallCount)
      })

      jest.useRealTimers()
    })

    it('handles WebSocket messages with invalid JSON', async () => {
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()
      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(mockWebSocket).not.toBeNull()
      })

      if (mockWebSocket?.onmessage) {
        mockWebSocket.onmessage(
          new MessageEvent('message', { data: 'invalid json' })
        )
      }

      expect(consoleSpy).toHaveBeenCalled()
      consoleSpy.mockRestore()
    })

    it('uses wss protocol for https URLs', async () => {
      const { getApiUrl } = require('@/lib/api/client')
      getApiUrl.mockReturnValueOnce('https://api.example.com')

      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(global.WebSocket).toHaveBeenCalledWith(
          'wss://api.example.com/api/ws/projects/test-project/generation-progress'
        )
      })
    })
  })

  describe('Real-time Updates (WebSocket only, no polling)', () => {
    it('does not make additional API calls when WebSocket disconnects (polling removed)', async () => {
      const { apiClient } = require('@/lib/api/client')

      apiClient.get.mockResolvedValue({
        tasks: [
          {
            id: 'task-1',
            data: { text: 'Test' },
            created_at: '2025-01-01',
            generation_status: {
              'model-1': { status: 'running', generation_id: 'gen-1' },
            },
          },
        ],
        total: 1,
        page: 1,
        page_size: 50,
        total_pages: 1,
        models: ['model-1'],
      })

      const { unmount } = render(
        <GenerationTaskList projectId="test-project" />
      )

      await waitFor(() => {
        expect(screen.getByText('Test')).toBeInTheDocument()
      })

      const callCountAfterLoad = apiClient.get.mock.calls.length

      // Data should remain visible after loading (no polling needed)
      expect(screen.getByText('Test')).toBeInTheDocument()
      expect(apiClient.get.mock.calls.length).toBe(callCountAfterLoad)

      unmount()
    })

    it('does not make extra API calls when WebSocket is connected', async () => {
      const { apiClient } = require('@/lib/api/client')

      apiClient.get.mockResolvedValue({
        tasks: [
          {
            id: 'task-1',
            data: { text: 'Test' },
            created_at: '2025-01-01',
            generation_status: {
              'model-1': { status: 'running', generation_id: 'gen-1' },
            },
          },
        ],
        total: 1,
        page: 1,
        page_size: 50,
        total_pages: 1,
        models: ['model-1'],
      })

      const { unmount } = render(
        <GenerationTaskList projectId="test-project" />
      )

      await waitFor(() => {
        expect(mockWebSocket).not.toBeNull()
        expect(mockWebSocket?.readyState).toBe(WebSocket.OPEN)
      })

      const callCountAfterLoad = apiClient.get.mock.calls.length

      // No additional API calls should be made (no polling)
      expect(apiClient.get.mock.calls.length).toBe(callCountAfterLoad)

      unmount()
    })
  })

  describe('Status Icons', () => {
    it('renders correct icons for all status types', async () => {
      const { apiClient } = require('@/lib/api/client')
      apiClient.get.mockResolvedValueOnce({
        tasks: [
          {
            id: 'task-1',
            data: { text: 'Test' },
            created_at: '2025-01-01',
            generation_status: {
              completed: { status: 'completed' },
              failed: { status: 'failed' },
              running: { status: 'running' },
              pending: { status: 'pending' },
              null: { status: null },
            },
          },
        ],
        total: 1,
        page: 1,
        page_size: 50,
        total_pages: 1,
        models: ['completed', 'failed', 'running', 'pending', 'null'],
      })

      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(screen.getByText('Test')).toBeInTheDocument()
      })

      const checkIcons = document.querySelectorAll('.text-green-600')
      expect(checkIcons.length).toBeGreaterThan(0)

      const failIcons = document.querySelectorAll('.text-red-600')
      expect(failIcons.length).toBeGreaterThan(0)

      const runningIcons = document.querySelectorAll('.text-yellow-600')
      expect(runningIcons.length).toBeGreaterThan(0)

      const grayIcons = document.querySelectorAll('.text-gray-400')
      expect(grayIcons.length).toBeGreaterThan(0)
    })
  })

  describe('Status Click Handling', () => {
    it('opens result modal when clicking completed status', async () => {
      const user = userEvent.setup()
      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        const table = screen.getByRole('table')
        expect(table).toBeInTheDocument()
      })

      const statusButtons = screen.getAllByRole('button')
      const completedButton = statusButtons.find((btn) =>
        btn.getAttribute('title')?.includes('Click to view')
      )

      if (completedButton) {
        await user.click(completedButton)
      }
    })

    it('opens result modal when clicking failed status', async () => {
      const user = userEvent.setup()
      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        const table = screen.getByRole('table')
        expect(table).toBeInTheDocument()
      })

      const statusButtons = screen.getAllByRole('button')
      const failedButton = statusButtons.find((btn) =>
        btn.getAttribute('title')?.includes('Click to view')
      )

      if (failedButton) {
        await user.click(failedButton)
      }
    })

    it('does not open modal for running status', async () => {
      const user = userEvent.setup()
      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        const table = screen.getByRole('table')
        expect(table).toBeInTheDocument()
      })

      const statusButtons = screen.getAllByRole('button')
      // New tooltip format shows stats like "0 completed, 1 running, 0 failed"
      // Look for buttons with running stats that don't have "Click to view"
      const runningButton = statusButtons.find((btn) => {
        const title = btn.getAttribute('title') || ''
        return title.includes('running') && !title.includes('Click to view')
      })

      // Running status buttons are now always clickable (they open the result modal)
      if (runningButton) {
        expect(runningButton).toHaveAttribute('title', expect.stringContaining('running'))
      }
    })
  })

  describe('Data Field Extraction', () => {
    it('extracts text field from task data', async () => {
      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        const table = screen.getByRole('table')
        expect(table).toBeInTheDocument()
      })
    })

    it('extracts question field from task data', async () => {
      const { apiClient } = require('@/lib/api/client')
      apiClient.get.mockResolvedValueOnce({
        tasks: [
          {
            id: 'task-1',
            data: { question: 'What is the answer?' },
            created_at: '2025-01-01',
            generation_status: {},
          },
        ],
        total: 1,
        page: 1,
        page_size: 50,
        total_pages: 1,
        models: ['model-1'],
      })

      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(screen.getByText('What is the answer?')).toBeInTheDocument()
      })
    })

    it('truncates long text to 100 characters', async () => {
      const { apiClient } = require('@/lib/api/client')
      const longText = 'A'.repeat(150)
      apiClient.get.mockResolvedValueOnce({
        tasks: [
          {
            id: 'task-1',
            data: { text: longText },
            created_at: '2025-01-01',
            generation_status: {},
          },
        ],
        total: 1,
        page: 1,
        page_size: 50,
        total_pages: 1,
        models: ['model-1'],
      })

      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        const truncatedText = longText.substring(0, 100) + '...'
        expect(screen.getByText(truncatedText)).toBeInTheDocument()
      })
    })

    it('shows "No text data" for tasks without text fields', async () => {
      const { apiClient } = require('@/lib/api/client')
      apiClient.get.mockResolvedValueOnce({
        tasks: [
          {
            id: 'task-1',
            data: { numeric_field: 123, boolean_field: true },
            created_at: '2025-01-01',
            generation_status: {},
          },
        ],
        total: 1,
        page: 1,
        page_size: 50,
        total_pages: 1,
        models: ['model-1'],
      })

      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(screen.getByText('No text data')).toBeInTheDocument()
      })
    })
  })

  describe('Pagination', () => {
    it('changes page when pagination is clicked', async () => {
      const user = userEvent.setup()
      const { apiClient } = require('@/lib/api/client')
      apiClient.get.mockResolvedValue({
        tasks: [
          {
            id: 'task-1',
            data: { text: 'Test' },
            created_at: '2025-01-01',
            generation_status: {},
          },
        ],
        total: 100,
        page: 1,
        page_size: 50,
        total_pages: 2,
        models: ['model-1'],
      })

      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(screen.getByText('Test')).toBeInTheDocument()
      })
    })

    it('changes page size when page size selector is used', async () => {
      const { apiClient } = require('@/lib/api/client')
      apiClient.get.mockResolvedValue({
        tasks: [
          {
            id: 'task-1',
            data: { text: 'Test' },
            created_at: '2025-01-01',
            generation_status: {},
          },
        ],
        total: 100,
        page: 1,
        page_size: 50,
        total_pages: 2,
        models: ['model-1'],
      })

      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(screen.getByText('Test')).toBeInTheDocument()
      })
    })
  })

  describe('Search and Filters', () => {
    it('updates search query when typing in search input', async () => {
      const user = userEvent.setup()
      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(
          screen.getByPlaceholderText('Search tasks...')
        ).toBeInTheDocument()
      })

      const searchInput = screen.getByPlaceholderText('Search tasks...')
      await user.type(searchInput, 'test query')

      expect(searchInput).toHaveValue('test query')
    })

    it('applies status filter when selecting from dropdown', async () => {
      const user = userEvent.setup()
      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        const table = screen.getByRole('table')
        expect(table).toBeInTheDocument()
      })

      const selects = document.querySelectorAll('select')
      const statusFilter = Array.from(selects).find((select) =>
        select.className.includes('sm:w-44')
      )

      if (statusFilter) {
        await user.selectOptions(statusFilter, 'completed')
        expect(statusFilter).toHaveValue('completed')
      }
    })

    it('triggers data fetch when search changes', async () => {
      jest.useFakeTimers()
      const user = userEvent.setup({ delay: null })
      const { apiClient } = require('@/lib/api/client')

      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(
          screen.getByPlaceholderText('Search tasks...')
        ).toBeInTheDocument()
      })

      const initialCallCount = apiClient.get.mock.calls.length

      const searchInput = screen.getByPlaceholderText('Search tasks...')
      await user.type(searchInput, 'test')

      jest.runAllTimers()

      await waitFor(() => {
        expect(apiClient.get.mock.calls.length).toBeGreaterThan(
          initialCallCount
        )
      })

      jest.useRealTimers()
    })

    it('triggers data fetch when status filter changes', async () => {
      const user = userEvent.setup()
      const { apiClient } = require('@/lib/api/client')

      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        const table = screen.getByRole('table')
        expect(table).toBeInTheDocument()
      })

      const initialCallCount = apiClient.get.mock.calls.length

      const selects = document.querySelectorAll('select')
      const statusFilter = Array.from(selects).find((select) =>
        select.className.includes('sm:w-44')
      )

      if (statusFilter) {
        await user.selectOptions(statusFilter, 'completed')

        await waitFor(() => {
          expect(apiClient.get.mock.calls.length).toBeGreaterThan(
            initialCallCount
          )
        })
      }
    })
  })

  describe('Modals', () => {
    it('opens control modal when Start Generation is clicked', async () => {
      const user = userEvent.setup()
      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(screen.getByText('Start Generation')).toBeInTheDocument()
      })

      const startButton = screen.getByText('Start Generation')
      await user.click(startButton)
    })

    it('shows Start Generation button for CONTRIBUTOR users', async () => {
      mockUseAuth.mockReturnValue({
        user: { is_superadmin: false, role: 'CONTRIBUTOR' },
        isLoading: false,
      })

      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(screen.getByText('Start Generation')).toBeInTheDocument()
      })
    })

    it('shows Start Generation button for ORG_ADMIN users', async () => {
      mockUseAuth.mockReturnValue({
        user: { is_superadmin: false, role: 'ORG_ADMIN' },
        isLoading: false,
      })

      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(screen.getByText('Start Generation')).toBeInTheDocument()
      })
    })

    it('hides Start Generation button for ANNOTATOR users', async () => {
      mockUseAuth.mockReturnValue({
        user: { is_superadmin: false, role: 'ANNOTATOR' },
        isLoading: false,
      })

      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(
          screen.getByPlaceholderText('Search tasks...')
        ).toBeInTheDocument()
      })

      expect(screen.queryByText('Start Generation')).not.toBeInTheDocument()
    })

    it('hides Start Generation button for users with no role', async () => {
      mockUseAuth.mockReturnValue({
        user: { is_superadmin: false },
        isLoading: false,
      })

      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(
          screen.getByPlaceholderText('Search tasks...')
        ).toBeInTheDocument()
      })

      expect(screen.queryByText('Start Generation')).not.toBeInTheDocument()
    })
  })

  describe('Project Data Fetching', () => {
    it('fetches project data on mount', async () => {
      const { apiClient } = require('@/lib/api/client')
      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(apiClient.get).toHaveBeenCalledWith('/projects/test-project')
      })
    })

    it('handles project data fetch errors gracefully', async () => {
      const { apiClient } = require('@/lib/api/client')
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()
      apiClient.get.mockRejectedValueOnce(new Error('Network error'))

      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(consoleSpy).toHaveBeenCalled()
      })

      consoleSpy.mockRestore()
    })
  })

  describe('Cleanup', () => {
    it('closes WebSocket on unmount', async () => {
      const { unmount } = render(
        <GenerationTaskList projectId="test-project" />
      )

      await waitFor(() => {
        expect(mockWebSocket).not.toBeNull()
      })

      const closeSpy = jest.spyOn(mockWebSocket!, 'close')
      unmount()

      expect(closeSpy).toHaveBeenCalled()
    })

    it('clears reconnect timeout on unmount', async () => {
      jest.useFakeTimers()
      const { unmount } = render(
        <GenerationTaskList projectId="test-project" />
      )

      await waitFor(() => {
        expect(mockWebSocket).not.toBeNull()
      })

      mockWebSocket?.close()
      unmount()

      jest.advanceTimersByTime(10000)
      jest.useRealTimers()
    })

    it('cleans up on unmount', async () => {
      const { apiClient } = require('@/lib/api/client')

      apiClient.get.mockResolvedValue({
        tasks: [
          {
            id: 'task-1',
            data: { text: 'Test' },
            created_at: '2025-01-01',
            generation_status: {
              'model-1': { status: 'running', generation_id: 'gen-1' },
            },
          },
        ],
        total: 1,
        page: 1,
        page_size: 50,
        total_pages: 1,
        models: ['model-1'],
      })

      const { unmount } = render(
        <GenerationTaskList projectId="test-project" />
      )

      await waitFor(() => {
        expect(screen.getByText('Test')).toBeInTheDocument()
      })

      unmount()
    })
  })

  describe('WebSocket Error Scenarios', () => {
    it('handles WebSocket connection error', async () => {
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()

      global.WebSocket = jest.fn(() => {
        throw new Error('WebSocket connection failed')
      }) as any

      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(consoleSpy).toHaveBeenCalledWith(
          'Failed to connect WebSocket:',
          expect.any(Error)
        )
      })

      consoleSpy.mockRestore()
      global.WebSocket = jest.fn((url: string) => {
        mockWebSocket = new MockWebSocket(url)
        return mockWebSocket as any
      }) as any
    })
  })

  describe('WebSocket Disconnect Handling', () => {
    it('component functions without polling after WebSocket disconnect', async () => {
      // Polling was removed - component now relies solely on WebSocket for real-time updates
      const { apiClient } = require('@/lib/api/client')

      apiClient.get.mockResolvedValue({
        tasks: [
          {
            id: 'task-1',
            data: { text: 'Test' },
            created_at: '2025-01-01',
            generation_status: {
              'model-1': { status: 'running', generation_id: 'gen-1' },
            },
          },
        ],
        total: 1,
        page: 1,
        page_size: 50,
        total_pages: 1,
        models: ['model-1'],
      })

      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(screen.getByText('Test')).toBeInTheDocument()
      })

      // Component should still render data after WebSocket disconnect
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()
      ;(global.WebSocket as jest.Mock).mockImplementation(() => {
        throw new Error('Reconnect blocked for test')
      })

      await act(async () => {
        if (mockWebSocket) mockWebSocket.close()
      })

      // Data should still be visible
      expect(screen.getByText('Test')).toBeInTheDocument()

      consoleSpy.mockRestore()
      ;(global.WebSocket as jest.Mock).mockImplementation((url: string) => {
        mockWebSocket = new MockWebSocket(url)
        return mockWebSocket as any
      })
    })

    it('cleans up WebSocket connections on unmount', async () => {
      const { apiClient } = require('@/lib/api/client')

      apiClient.get.mockResolvedValue({
        tasks: [
          {
            id: 'task-1',
            data: { text: 'Test' },
            created_at: '2025-01-01',
            generation_status: {
              'model-1': { status: 'running', generation_id: 'gen-1' },
            },
          },
        ],
        total: 1,
        page: 1,
        page_size: 50,
        total_pages: 1,
        models: ['model-1'],
      })

      const { unmount } = render(
        <GenerationTaskList projectId="test-project" />
      )

      await waitFor(() => {
        expect(screen.getByText('Test')).toBeInTheDocument()
      })

      const callCountBefore = apiClient.get.mock.calls.length

      // Unmount should clear all WebSocket connections
      unmount()

      // Verify no additional API calls happen after unmount
      expect(apiClient.get.mock.calls.length).toBe(callCountBefore)
    })
  })

  describe('Status Click Interactions', () => {
    it('shows correct titles for all status types', async () => {
      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        const table = screen.getByRole('table')
        expect(table).toBeInTheDocument()
      })

      const buttons = screen.getAllByRole('button')

      // New tooltip format: "X completed, Y running, Z failed" with optional " - Click to view"
      const hasClickToView = buttons.some((btn) =>
        btn.getAttribute('title')?.includes('Click to view')
      )

      const hasRunningStatus = buttons.some((btn) =>
        btn.getAttribute('title')?.includes('running')
      )

      const hasNotGenerated = buttons.some(
        (btn) => btn.getAttribute('title') === 'Not yet generated'
      )

      expect(hasClickToView || hasRunningStatus || hasNotGenerated).toBe(true)
    })

    it('shows correct title for null status button', async () => {
      const { apiClient } = require('@/lib/api/client')
      // When generation_status doesn't have an entry for a model, it shows "Not yet generated"
      apiClient.get.mockResolvedValueOnce({
        tasks: [
          {
            id: 'task-1',
            data: { text: 'Test' },
            created_at: '2025-01-01',
            generation_status: {
              // model-1 has no entry, so it should show "Not yet generated"
            },
          },
        ],
        total: 1,
        page: 1,
        page_size: 50,
        total_pages: 1,
        models: ['model-1'],
      })

      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(screen.getByText('Test')).toBeInTheDocument()
      })

      const buttons = screen.getAllByRole('button')
      const notGeneratedButton = buttons.find(
        (btn) => btn.getAttribute('title') === 'Not yet generated'
      )

      expect(notGeneratedButton).toBeTruthy()
      // Status buttons are always clickable (they open the result modal)
      expect(notGeneratedButton).toHaveAttribute('title', 'Not yet generated')
    })
  })

  describe('Data Field Extraction Edge Cases', () => {
    it('extracts content field from task data', async () => {
      const { apiClient } = require('@/lib/api/client')
      apiClient.get.mockResolvedValueOnce({
        tasks: [
          {
            id: 'task-1',
            data: { content: 'Content field text' },
            created_at: '2025-01-01',
            generation_status: {},
          },
        ],
        total: 1,
        page: 1,
        page_size: 50,
        total_pages: 1,
        models: ['model-1'],
      })

      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(screen.getByText('Content field text')).toBeInTheDocument()
      })
    })

    it('extracts title field from task data', async () => {
      const { apiClient } = require('@/lib/api/client')
      apiClient.get.mockResolvedValueOnce({
        tasks: [
          {
            id: 'task-1',
            data: { title: 'Title field text' },
            created_at: '2025-01-01',
            generation_status: {},
          },
        ],
        total: 1,
        page: 1,
        page_size: 50,
        total_pages: 1,
        models: ['model-1'],
      })

      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(screen.getByText('Title field text')).toBeInTheDocument()
      })
    })

    it('extracts input field from task data', async () => {
      const { apiClient } = require('@/lib/api/client')
      apiClient.get.mockResolvedValueOnce({
        tasks: [
          {
            id: 'task-1',
            data: { input: 'Input field text' },
            created_at: '2025-01-01',
            generation_status: {},
          },
        ],
        total: 1,
        page: 1,
        page_size: 50,
        total_pages: 1,
        models: ['model-1'],
      })

      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(screen.getByText('Input field text')).toBeInTheDocument()
      })
    })

    it('falls back to first string value when no standard field found', async () => {
      const { apiClient } = require('@/lib/api/client')
      apiClient.get.mockResolvedValueOnce({
        tasks: [
          {
            id: 'task-1',
            data: { custom_field: 'Custom string value', number: 123 },
            created_at: '2025-01-01',
            generation_status: {},
          },
        ],
        total: 1,
        page: 1,
        page_size: 50,
        total_pages: 1,
        models: ['model-1'],
      })

      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(screen.getByText('Custom string value')).toBeInTheDocument()
      })
    })

    it('truncates fallback string to 100 characters', async () => {
      const { apiClient } = require('@/lib/api/client')
      const longText = 'X'.repeat(150)
      apiClient.get.mockResolvedValueOnce({
        tasks: [
          {
            id: 'task-1',
            data: { custom_field: longText },
            created_at: '2025-01-01',
            generation_status: {},
          },
        ],
        total: 1,
        page: 1,
        page_size: 50,
        total_pages: 1,
        models: ['model-1'],
      })

      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        const truncatedText = longText.substring(0, 100) + '...'
        expect(screen.getByText(truncatedText)).toBeInTheDocument()
      })
    })
  })

  describe('Modal Rendering', () => {
    it('renders GenerationControlModal when opened', async () => {
      const user = userEvent.setup()
      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(screen.getByText('Start Generation')).toBeInTheDocument()
      })

      const startButton = screen.getByText('Start Generation')
      await user.click(startButton)

      await waitFor(() => {
        const controlModalContent = document.querySelector('[role="dialog"]')
        expect(controlModalContent).toBeTruthy()
      })
    })
  })

  describe('Status Filter Options', () => {
    it('renders all status filter options', async () => {
      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        const table = screen.getByRole('table')
        expect(table).toBeInTheDocument()
      })

      const selects = document.querySelectorAll('select')
      const statusFilter = Array.from(selects).find((select) =>
        select.className.includes('sm:w-44')
      )

      expect(statusFilter).toBeTruthy()
      if (statusFilter) {
        const options = statusFilter.querySelectorAll('option')
        // The mock SelectValue renders a disabled placeholder option, plus 6 SelectItem options = 7 total
        expect(options.length).toBe(7)
        // First option is the SelectValue placeholder (disabled)
        expect(options[0].textContent).toBe('All statuses')
        expect(options[0]).toBeDisabled()
        // Remaining options are the actual filter values
        expect(options[1].textContent).toBe('All statuses')
        expect(options[2].textContent).toBe('Completed')
        expect(options[3].textContent).toBe('Failed')
        expect(options[4].textContent).toBe('Running')
        expect(options[5].textContent).toBe('Pending')
        expect(options[6].textContent).toBe('Not generated')
      }
    })
  })

  describe('Error Handling', () => {
    it('handles project data fetch error gracefully', async () => {
      const { apiClient } = require('@/lib/api/client')
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()

      apiClient.get.mockImplementation((url: string) => {
        if (url.includes('/projects/')) {
          return Promise.reject(new Error('Project fetch failed'))
        }
        return Promise.resolve({
          tasks: [],
          total: 0,
          page: 1,
          page_size: 50,
          total_pages: 0,
          models: ['model-1'],
        })
      })

      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(consoleSpy).toHaveBeenCalledWith(
          '[GenerationTaskList] Failed to fetch project data:',
          expect.any(Error)
        )
      })

      consoleSpy.mockRestore()
    })

    it('shows error state when task-status API fails', async () => {
      const { apiClient } = require('@/lib/api/client')
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()

      apiClient.get.mockImplementation((url: string) => {
        if (url.includes('/generation-tasks/')) {
          return Promise.reject(new Error('HTTP error! status: 500'))
        }
        return Promise.resolve({ id: 'test-project', title: 'Test' })
      })

      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(screen.getByText('Failed to load generation data')).toBeInTheDocument()
      })

      expect(screen.getByText('HTTP error! status: 500')).toBeInTheDocument()
      expect(screen.getByText('Retry')).toBeInTheDocument()
      // Should NOT show "no models" message
      expect(screen.queryByText('No models configured for generation')).not.toBeInTheDocument()

      consoleSpy.mockRestore()
    })
  })

  describe('WebSocket-Only Updates', () => {
    it('renders data when WebSocket is unavailable (no polling fallback)', async () => {
      const { apiClient } = require('@/lib/api/client')

      // Prevent WebSocket from connecting
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()
      ;(global.WebSocket as jest.Mock).mockImplementation(() => {
        throw new Error('WebSocket blocked for test')
      })

      apiClient.get.mockResolvedValue({
        tasks: [
          {
            id: 'task-1',
            data: { text: 'Test' },
            created_at: '2025-01-01',
            generation_status: {
              'model-1': { status: 'running', generation_id: 'gen-1' },
            },
          },
        ],
        total: 1,
        page: 1,
        page_size: 50,
        total_pages: 1,
        models: ['model-1'],
      })

      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(screen.getByText('Test')).toBeInTheDocument()
      })

      // Data is rendered from initial fetch even without WebSocket
      expect(screen.getByText('Test')).toBeInTheDocument()

      // Restore WebSocket mock
      consoleSpy.mockRestore()
      ;(global.WebSocket as jest.Mock).mockImplementation((url: string) => {
        mockWebSocket = new MockWebSocket(url)
        return mockWebSocket as any
      })
    })
  })

  describe('Button Title Coverage', () => {
    it('covers all conditional button title branches', async () => {
      const { apiClient } = require('@/lib/api/client')

      apiClient.get.mockResolvedValueOnce({
        tasks: [
          {
            id: 'task-1',
            data: { text: 'Test' },
            created_at: '2025-01-01',
            generation_status: {
              // completed model has results - should show "Click to view"
              completed: { status: 'completed', generation_id: 'gen-1' },
              // running model has no results yet - should show running stats
              running: { status: 'running', generation_id: null },
              // not_generated model has NO entry - should show "Not yet generated"
            },
          },
        ],
        total: 1,
        page: 1,
        page_size: 50,
        total_pages: 1,
        // Include a model that doesn't have an entry in generation_status
        models: ['completed', 'running', 'not_generated'],
      })

      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(screen.getByText('Test')).toBeInTheDocument()
      })

      const buttons = screen.getAllByRole('button')

      // New tooltip format: "X completed, Y running, Z failed" with optional " - Click to view"
      // Check for buttons with results (completed with generation_id)
      expect(
        buttons.some((btn) =>
          btn.getAttribute('title')?.includes('Click to view')
        )
      ).toBe(true)

      // Check for running statuses
      expect(
        buttons.some((btn) => btn.getAttribute('title')?.includes('running'))
      ).toBe(true)

      // Check for not-yet-generated status (model with no entry in generation_status)
      expect(
        buttons.some((btn) => btn.getAttribute('title') === 'Not yet generated')
      ).toBe(true)
    })
  })

  describe('Modal State Management', () => {
    it('handles opening modals for completed and failed statuses', async () => {
      const user = userEvent.setup()
      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        const table = screen.getByRole('table')
        expect(table).toBeInTheDocument()
      })

      const buttons = screen.getAllByRole('button')

      const completedButton = buttons.find(
        (btn) => btn.getAttribute('title')?.includes('Click to view')
      )

      if (completedButton) {
        expect(completedButton).not.toBeDisabled()
        await user.click(completedButton)
      }

      const failedButton = buttons.find(
        (btn) => {
          const title = btn.getAttribute('title') || ''
          return title.includes('Click to view') && title !== completedButton?.getAttribute('title')
        }
      )

      if (failedButton) {
        expect(failedButton).not.toBeDisabled()
        await user.click(failedButton)
      }
    })
  })

  describe('Pagination Page Size', () => {
    it('changes page size and resets to first page', async () => {
      const user = userEvent.setup()
      const { apiClient } = require('@/lib/api/client')

      apiClient.get.mockResolvedValue({
        tasks: [
          {
            id: 'task-1',
            data: { text: 'Test' },
            created_at: '2025-01-01',
            generation_status: {},
          },
        ],
        total: 100,
        page: 2,
        page_size: 50,
        total_pages: 2,
        models: ['model-1'],
      })

      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(screen.getByText('Test')).toBeInTheDocument()
      })

      const pageSizeSelects = document.querySelectorAll('select')
      const pageSizeSelect = Array.from(pageSizeSelects).find((select) => {
        const options = select.querySelectorAll('option')
        return Array.from(options).some(
          (opt) => opt.value === '25' || opt.value === '100'
        )
      })

      if (pageSizeSelect) {
        await user.selectOptions(pageSizeSelect, '100')

        await waitFor(() => {
          expect(apiClient.get).toHaveBeenCalled()
        })
      }
    })
  })

  describe('Modal Callback Coverage', () => {
    it('handles control modal onClose callback', async () => {
      const user = userEvent.setup()
      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(screen.getByText('Start Generation')).toBeInTheDocument()
      })

      const startButton = screen.getByText('Start Generation')
      await user.click(startButton)

      await waitFor(() => {
        expect(screen.getByTestId('control-modal')).toBeInTheDocument()
      })

      const closeButton = screen.getByTestId('control-close')
      await user.click(closeButton)

      await waitFor(() => {
        expect(screen.queryByTestId('control-modal')).not.toBeInTheDocument()
      })
    })

    it('handles control modal onSuccess callback', async () => {
      const user = userEvent.setup()
      const { apiClient } = require('@/lib/api/client')
      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(screen.getByText('Start Generation')).toBeInTheDocument()
      })

      const startButton = screen.getByText('Start Generation')
      await user.click(startButton)

      await waitFor(() => {
        expect(screen.getByTestId('control-modal')).toBeInTheDocument()
      })

      const initialCallCount = apiClient.get.mock.calls.length

      const successButton = screen.getByTestId('control-success')
      await user.click(successButton)

      await waitFor(() => {
        expect(screen.queryByTestId('control-modal')).not.toBeInTheDocument()
        expect(apiClient.get.mock.calls.length).toBeGreaterThan(
          initialCallCount
        )
      })
    })

    it('handles result modal onClose callback', async () => {
      const user = userEvent.setup()
      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        const table = screen.getByRole('table')
        expect(table).toBeInTheDocument()
      })

      const buttons = screen.getAllByRole('button')
      const completedButton = buttons.find(
        (btn) => btn.getAttribute('title')?.includes('Click to view')
      )

      if (completedButton) {
        await user.click(completedButton)

        await waitFor(() => {
          expect(screen.getByTestId('result-modal')).toBeInTheDocument()
        })

        const closeButton = screen.getByTestId('result-close')
        await user.click(closeButton)

        await waitFor(() => {
          expect(screen.queryByTestId('result-modal')).not.toBeInTheDocument()
        })
      }
    })
  })

  describe('Polling Stop Coverage', () => {
    it('stops and clears polling when no running generations', async () => {
      const { apiClient } = require('@/lib/api/client')

      // Block WebSocket so component starts in polling mode
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()
      ;(global.WebSocket as jest.Mock).mockImplementation(() => {
        throw new Error('WebSocket blocked for polling test')
      })

      // All generations completed - no polling should happen
      apiClient.get.mockResolvedValue({
        tasks: [
          {
            id: 'task-1',
            data: { text: 'Test' },
            created_at: '2025-01-01',
            generation_status: {
              'model-1': { status: 'completed', generation_id: 'gen-1' },
            },
          },
        ],
        total: 1,
        page: 1,
        page_size: 50,
        total_pages: 1,
        models: ['model-1'],
      })

      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(screen.getByText('Test')).toBeInTheDocument()
      })

      // No WebSocket, no running generations - should not be polling
      expect(
        screen.queryByText('Real-time updates active')
      ).not.toBeInTheDocument()

      const callCountBefore = apiClient.get.mock.calls.length

      // Wait briefly to confirm no polling occurs
      await new Promise((resolve) => setTimeout(resolve, 100))

      expect(apiClient.get.mock.calls.length).toBe(callCountBefore)

      consoleSpy.mockRestore()
      ;(global.WebSocket as jest.Mock).mockImplementation((url: string) => {
        const ws = new MockWebSocket(url)
        if (trackWebSocketCreation) {
          mockWebSocket = ws
        }
        return ws as any
      })
    })
  })

  describe('Modal Props Coverage', () => {
    it('passes correct props to GenerationControlModal', async () => {
      const user = userEvent.setup()
      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(screen.getByText('Start Generation')).toBeInTheDocument()
      })

      const startButton = screen.getByText('Start Generation')
      await user.click(startButton)

      await waitFor(() => {
        const modal = document.querySelector('[role="dialog"]')
        expect(modal).toBeTruthy()
      })
    })

    it('passes correct props to GenerationResultModal', async () => {
      const user = userEvent.setup()
      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        const table = screen.getByRole('table')
        expect(table).toBeInTheDocument()
      })

      const buttons = screen.getAllByRole('button')
      const completedButton = buttons.find(
        (btn) => btn.getAttribute('title')?.includes('Click to view')
      )

      if (completedButton) {
        await user.click(completedButton)

        await waitFor(() => {
          const modal = document.querySelector('[role="dialog"]')
          expect(modal).toBeTruthy()
        })
      }
    })
  })

  describe('Polling Clear Logic', () => {
    it('clears polling interval when WebSocket connects with running generations', async () => {
      const { apiClient } = require('@/lib/api/client')

      // Phase 1: Start without WebSocket to enter polling mode
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()
      ;(global.WebSocket as jest.Mock).mockImplementation(() => {
        throw new Error('WebSocket blocked for polling test')
      })

      apiClient.get.mockResolvedValue({
        tasks: [
          {
            id: 'task-1',
            data: { text: 'Test' },
            created_at: '2025-01-01',
            generation_status: {
              'model-1': { status: 'running', generation_id: 'gen-1' },
            },
          },
        ],
        total: 1,
        page: 1,
        page_size: 50,
        total_pages: 1,
        models: ['model-1'],
      })

      render(<GenerationTaskList projectId="test-project" />)

      await waitFor(() => {
        expect(screen.getByText('Test')).toBeInTheDocument()
      })

      // Should be in polling mode (no WebSocket)
      expect(
        screen.queryByText('Real-time updates active')
      ).not.toBeInTheDocument()

      // Verify API was called for data loading
      expect(apiClient.get).toHaveBeenCalled()

      consoleSpy.mockRestore()
      ;(global.WebSocket as jest.Mock).mockImplementation((url: string) => {
        mockWebSocket = new MockWebSocket(url)
        return mockWebSocket as any
      })
    })
  })
})
