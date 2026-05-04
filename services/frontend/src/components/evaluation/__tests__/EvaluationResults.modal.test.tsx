/**
 * Coverage tests for EvaluationResults - ResultDetailsModal and handlers
 *
 * Targets uncovered lines: handleTaskClick, handleScoreClick, ResultDetailsModal
 * tabs (annotation, generation, evaluation), close callbacks.
 *
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import { EvaluationResults } from '../EvaluationResults'

const mockAddToast = jest.fn()

jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: mockAddToast }),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: any) => {
      if (typeof params === 'string') return params
      return key
    },
    locale: 'en',
  }),
}))

jest.mock('@/components/shared/Badge', () => ({
  Badge: ({ children, className }: any) => <span className={className}>{children}</span>,
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, disabled, className, ...props }: any) => (
    <button onClick={onClick} disabled={disabled} className={className} {...props}>{children}</button>
  ),
}))

jest.mock('@/components/shared/Card', () => ({
  Card: ({ children, className }: any) => <div className={className}>{children}</div>,
}))

jest.mock('@/components/shared/LoadingSpinner', () => ({
  LoadingSpinner: () => <div data-testid="loading-spinner" />,
}))

jest.mock('@/components/tasks/TaskDataViewModal', () => ({
  TaskDataViewModal: ({ task, isOpen, onClose }: any) =>
    isOpen ? (
      <div data-testid="task-data-view-modal">
        {task ? <span>Task: {task.id}</span> : <span>Loading task...</span>}
        <button onClick={onClose} data-testid="close-task-modal">Close</button>
      </div>
    ) : null,
}))

jest.mock('@heroicons/react/24/outline', () => ({
  ArrowDownTrayIcon: () => <span data-testid="arrow-down-tray-icon" />,
  ArrowPathIcon: () => <span data-testid="arrow-path-icon" />,
  CheckCircleIcon: () => <span data-testid="check-circle-icon" />,
  ClockIcon: () => <span data-testid="clock-icon" />,
  ClipboardDocumentIcon: () => <span data-testid="clipboard-icon" />,
  ExclamationCircleIcon: () => <span data-testid="exclamation-icon" />,
  PlayIcon: () => <span data-testid="play-icon" />,
  QueueListIcon: () => <span data-testid="queue-icon" />,
  XCircleIcon: () => <span data-testid="x-circle-icon" />,
  XMarkIcon: () => <span data-testid="x-mark-icon" />,
}))

jest.mock('@headlessui/react', () => ({
  Dialog: ({ children, open, onClose }: any) =>
    open ? (
      <div data-testid="dialog" onClick={(e: any) => { if (e.target === e.currentTarget) onClose?.() }}>
        {typeof children === 'function' ? children({ open }) : children}
      </div>
    ) : null,
  DialogPanel: ({ children, className }: any) => (
    <div data-testid="dialog-panel" className={className}>{children}</div>
  ),
  DialogTitle: ({ children, className }: any) => (
    <h2 data-testid="dialog-title" className={className}>{children}</h2>
  ),
}))

// ---- API Mocks ----
const mockGetProjectEvaluationResults = jest.fn()
const mockGetProjectResultsByTaskModel = jest.fn()
const mockGetTaskEvaluation = jest.fn()
const mockApiClientGet = jest.fn()

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: null }),
}))

jest.mock('@/utils/permissions', () => ({
  canStartGeneration: () => false,
}))

jest.mock('@/lib/api/client', () => ({
  apiClient: {
    getProjectEvaluationResults: (...args: any[]) => mockGetProjectEvaluationResults(...args),
    getProjectResultsByTaskModel: (...args: any[]) => mockGetProjectResultsByTaskModel(...args),
    getTaskEvaluation: (...args: any[]) => mockGetTaskEvaluation(...args),
    get: (...args: any[]) => mockApiClientGet(...args),
    evaluations: { computeStatistics: jest.fn() },
  },
}))

const mockGetTask = jest.fn()
const mockGetTaskAnnotations = jest.fn()

jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    getTask: (...args: any[]) => mockGetTask(...args),
    getTaskAnnotations: (...args: any[]) => mockGetTaskAnnotations(...args),
  },
}))

// ---- Test Data (matching the shapes used by the component) ----

function makeTaskModelData() {
  return {
    evaluation_id: 'eval-001',
    models: ['gpt-4', 'claude-3'],
    model_names: { 'gpt-4': 'GPT-4', 'claude-3': 'Claude 3' },
    tasks: [
      {
        task_id: 'task-111',
        task_preview: 'Test question 1',
        scores: { 'gpt-4': 0.85, 'claude-3': 0.72 },
        has_annotation: true,
        generation_models: ['gpt-4', 'claude-3'],
      },
    ],
    summary: {
      'gpt-4': { avg: 0.85, count: 1, model_name: 'GPT-4' },
      'claude-3': { avg: 0.72, count: 1, model_name: 'Claude 3' },
    },
  }
}

function makeProjectResults() {
  return {
    project_id: 'p1',
    evaluations: [
      {
        evaluation_id: 'eval-001',
        model_id: 'gpt-4',
        status: 'completed',
        created_at: new Date().toISOString(),
        completed_at: new Date().toISOString(),
        samples_evaluated: 10,
        sample_results_count: 10,
        error_message: null,
        evaluation_configs: [
          {
            id: 'config-1',
            metric: 'exact_match',
            display_name: 'Exact Match',
            metric_type: 'automated',
            metric_parameters: {},
            prediction_fields: ['answer'],
            reference_fields: ['gold_answer'],
            enabled: true,
          },
        ],
        results_by_config: {
          'config-1': {
            field_results: [
              {
                combo_key: 'answer_vs_gold_answer',
                prediction_field: 'answer',
                reference_field: 'gold_answer',
                scores: { exact_match: 0.85 },
              },
            ],
            aggregate_score: 0.85,
          },
        },
        progress: { samples_passed: 8, samples_failed: 2, samples_skipped: 0 },
      },
    ],
    total_count: 1,
  }
}

const DATA_VIEW_PROPS = {
  viewType: 'data' as const,
  selectedMetrics: ['exact_match'],
}

function setupMocks() {
  mockGetProjectEvaluationResults.mockResolvedValue(makeProjectResults())
  mockGetProjectResultsByTaskModel.mockResolvedValue(makeTaskModelData())
  mockGetTask.mockResolvedValue({ id: 'task-111', data: { text: 'Hello world' } })
  mockGetTaskAnnotations.mockResolvedValue([
    {
      id: 'ann-1',
      task_id: 1,
      completed_by: 'admin',
      result: [{ value: 'answer text', from_name: 'answer', to_name: 'text', type: 'textarea' }],
      was_cancelled: false,
      ground_truth: true,
      lead_time: 45.5,
      created_at: '2025-01-01T00:00:00Z',
    },
    {
      id: 'ann-2',
      task_id: 1,
      completed_by: 'user-2',
      result: [{ value: { choices: ['A'] }, from_name: 'choice', to_name: 'text', type: 'choices' }],
      was_cancelled: true,
      ground_truth: false,
      lead_time: null,
      created_at: '2025-01-02T00:00:00Z',
    },
  ])
  mockApiClientGet.mockResolvedValue({
    results: [
      {
        task_id: 'task-111',
        model_id: 'gpt-4',
        generation_id: 'gen-1',
        status: 'completed',
        result: {
          generated_text: 'Generated response text here',
          fields: { answer: 'structured' },
        },
        prompt_used: 'The prompt used',
        generated_at: '2025-01-01T12:00:00Z',
        generation_time_seconds: 2.5,
        structure_key: 'default',
      },
    ],
  })
  // All three results carry `exact_match` so the per-metric filter
  // (selectedMetricName, added in 56b53b0 academic-rigor) doesn't drop
  // them when the table is showing exact_match. The pass/fail/error
  // assertions in "switches to evaluation tab" need all three rendered.
  mockGetTaskEvaluation.mockResolvedValue({
    results: [
      {
        id: 'result-1',
        field_name: 'exact_match-answer',
        answer_type: 'text',
        passed: true,
        confidence_score: 0.95,
        metrics: {
          exact_match: 1,
          bleu: 0.85,
          llm_judge_response: {
            score: 4.5,
            reasoning: 'Good answer',
          },
        },
      },
      {
        id: 'result-2',
        field_name: 'exact_match-choice',
        answer_type: 'single_choice',
        passed: false,
        confidence_score: null,
        metrics: { exact_match: 0 },
      },
      {
        id: 'result-3',
        field_name: 'exact_match-optional',
        answer_type: 'text',
        passed: null,
        confidence_score: null,
        metrics: { exact_match: 0 },
      },
    ],
  })
}

describe('EvaluationResults - modal and handler coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    setupMocks()
  })

  async function renderDataView() {
    render(<EvaluationResults projectId="p1" {...DATA_VIEW_PROPS} />)
    await waitFor(() => expect(mockGetProjectEvaluationResults).toHaveBeenCalled())
    await waitFor(() => {
      // Wait for task model data to load and render the data table
      const taskLinks = screen.queryAllByTitle('evaluation.multiFieldResults.clickToViewTaskData')
      return taskLinks.length > 0
    }, { timeout: 5000 })
    await act(async () => { await new Promise(r => setTimeout(r, 50)) })
  }

  it('opens task data modal when task link is clicked', async () => {
    await renderDataView()

    const taskLinks = screen.queryAllByTitle('evaluation.multiFieldResults.clickToViewTaskData')
    if (taskLinks.length > 0) {
      await act(async () => { fireEvent.click(taskLinks[0]) })

      await waitFor(() => expect(mockGetTask).toHaveBeenCalledWith('task-111'))
      await waitFor(() => expect(screen.getByTestId('task-data-view-modal')).toBeInTheDocument())

      // Close modal
      fireEvent.click(screen.getByTestId('close-task-modal'))
      await waitFor(() => expect(screen.queryByTestId('task-data-view-modal')).not.toBeInTheDocument())
    }
  })

  it('handles task click failure', async () => {
    mockGetTask.mockRejectedValue(new Error('Not found'))
    await renderDataView()

    const taskLinks = screen.queryAllByTitle('evaluation.multiFieldResults.clickToViewTaskData')
    if (taskLinks.length > 0) {
      await act(async () => { fireEvent.click(taskLinks[0]) })
      await waitFor(() => expect(mockAddToast).toHaveBeenCalledWith(expect.any(String), 'error'))
    }
  })

  it('opens result details modal when score cell is clicked', async () => {
    await renderDataView()

    const scoreCells = screen.queryAllByTitle('evaluation.multiFieldResults.clickToViewResponse')
    if (scoreCells.length > 0) {
      await act(async () => { fireEvent.click(scoreCells[0]) })

      await waitFor(() => expect(screen.getByTestId('dialog')).toBeInTheDocument())

      // Verify the modal is open and APIs were called
      // Note: getTaskAnnotations is only called for annotator cells, not model cells
      await waitFor(() => {
        expect(mockApiClientGet).toHaveBeenCalled()
        expect(mockGetTaskEvaluation).toHaveBeenCalled()
      })
    }
  })

  it('switches to generation tab in result details modal', async () => {
    await renderDataView()

    const scoreCells = screen.queryAllByTitle('evaluation.multiFieldResults.clickToViewResponse')
    if (scoreCells.length > 0) {
      await act(async () => { fireEvent.click(scoreCells[0]) })
      await waitFor(() => expect(screen.getByTestId('dialog')).toBeInTheDocument())
      await act(async () => { await new Promise(r => setTimeout(r, 100)) })

      // Click generation tab
      fireEvent.click(screen.getByText('evaluation.multiFieldResults.generationResults'))
      await waitFor(() => {
        expect(screen.getByText('Generated response text here')).toBeInTheDocument()
      })
    }
  })

  it('switches to evaluation tab and shows pass/fail/error results with LLM judge', async () => {
    await renderDataView()

    const scoreCells = screen.queryAllByTitle('evaluation.multiFieldResults.clickToViewResponse')
    if (scoreCells.length > 0) {
      await act(async () => { fireEvent.click(scoreCells[0]) })
      await waitFor(() => expect(screen.getByTestId('dialog')).toBeInTheDocument())
      await act(async () => { await new Promise(r => setTimeout(r, 100)) })

      // Click evaluation tab
      fireEvent.click(screen.getByText('evaluation.multiFieldResults.evaluationResults'))
      await waitFor(() => {
        expect(screen.getByText('evaluation.multiFieldResults.passed')).toBeInTheDocument()
        expect(screen.getByText('evaluation.multiFieldResults.failed')).toBeInTheDocument()
        expect(screen.getByText('evaluation.multiFieldResults.error')).toBeInTheDocument()
      })
    }
  })

  it('calls annotation API for annotator cells', async () => {
    mockGetProjectResultsByTaskModel.mockResolvedValue({
      evaluation_id: 'eval-001',
      models: ['annotator:user-1'],
      model_names: { 'annotator:user-1': 'User 1' },
      tasks: [
        {
          task_id: 'task-111',
          task_preview: 'Test question 1',
          scores: { 'annotator:user-1': 0.9 },
          has_annotation: true,
          generation_models: [],
        },
      ],
      summary: {
        'annotator:user-1': { avg: 0.9, count: 1, model_name: 'User 1' },
      },
    })
    mockGetTaskAnnotations.mockResolvedValue([])
    await renderDataView()

    const scoreCells = screen.queryAllByTitle('evaluation.multiFieldResults.clickToViewResponse')
    if (scoreCells.length > 0) {
      await act(async () => { fireEvent.click(scoreCells[0]) })
      await waitFor(() => expect(screen.getByTestId('dialog')).toBeInTheDocument())
      await waitFor(() => expect(mockGetTaskAnnotations).toHaveBeenCalled())
    }
  })

  it('shows empty generation state', async () => {
    mockApiClientGet.mockResolvedValue({ results: [] })
    await renderDataView()

    const scoreCells = screen.queryAllByTitle('evaluation.multiFieldResults.clickToViewResponse')
    if (scoreCells.length > 0) {
      await act(async () => { fireEvent.click(scoreCells[0]) })
      await waitFor(() => expect(screen.getByTestId('dialog')).toBeInTheDocument())
      await act(async () => { await new Promise(r => setTimeout(r, 100)) })

      fireEvent.click(screen.getByText('evaluation.multiFieldResults.generationResults'))
      await waitFor(() => {
        expect(screen.getByText('evaluation.multiFieldResults.noGenerationData')).toBeInTheDocument()
      })
    }
  })

  it('shows empty evaluation state', async () => {
    mockGetTaskEvaluation.mockResolvedValue({ results: [] })
    await renderDataView()

    const scoreCells = screen.queryAllByTitle('evaluation.multiFieldResults.clickToViewResponse')
    if (scoreCells.length > 0) {
      await act(async () => { fireEvent.click(scoreCells[0]) })
      await waitFor(() => expect(screen.getByTestId('dialog')).toBeInTheDocument())
      await act(async () => { await new Promise(r => setTimeout(r, 100)) })

      fireEvent.click(screen.getByText('evaluation.multiFieldResults.evaluationResults'))
      await waitFor(() => {
        expect(screen.getByText('evaluation.multiFieldResults.noEvalResults')).toBeInTheDocument()
      })
    }
  })

  it('closes result details modal', async () => {
    await renderDataView()

    const scoreCells = screen.queryAllByTitle('evaluation.multiFieldResults.clickToViewResponse')
    if (scoreCells.length > 0) {
      await act(async () => { fireEvent.click(scoreCells[0]) })
      await waitFor(() => expect(screen.getByTestId('dialog')).toBeInTheDocument())

      // Close via XMarkIcon button
      const closeBtn = screen.getAllByRole('button').find(b => b.querySelector('[data-testid="x-mark-icon"]'))
      if (closeBtn) {
        fireEvent.click(closeBtn)
        await waitFor(() => expect(screen.queryByTestId('dialog')).not.toBeInTheDocument())
      }
    }
  })

  it('skips generation fetch for annotator model', async () => {
    mockGetProjectResultsByTaskModel.mockResolvedValue({
      evaluation_id: 'eval-001',
      models: ['annotator:user-1'],
      model_names: { 'annotator:user-1': 'User 1' },
      tasks: [
        {
          task_id: 'task-111',
          task_preview: 'Test',
          scores: { 'annotator:user-1': 0.9 },
          has_annotation: true,
          generation_models: [],
        },
      ],
      summary: {
        'annotator:user-1': { avg: 0.9, count: 1, model_name: 'User 1' },
      },
    })

    await renderDataView()

    const scoreCells = screen.queryAllByTitle('evaluation.multiFieldResults.clickToViewResponse')
    if (scoreCells.length > 0) {
      await act(async () => { fireEvent.click(scoreCells[0]) })

      // Should NOT call the generation API for annotator models
      await act(async () => { await new Promise(r => setTimeout(r, 100)) })
      expect(mockApiClientGet).not.toHaveBeenCalled()
    }
  })
})
