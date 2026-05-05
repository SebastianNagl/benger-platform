/**
 * @jest-environment jsdom
 *
 * Comprehensive tests for the EvaluationResults component.
 * This is the core evaluation display component (1,758 lines) that renders:
 * - Loading / error / empty states
 * - Evaluation cards with status badges, progress bars, and score displays
 * - Per-task/model data tables (viewType='data')
 * - ResultDetailsModal for per-sample drill-down
 * - Statistical annotations (CI, SE, std)
 * - Filtering by models, metrics, and eval types
 */
import '@testing-library/jest-dom'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EvaluationResults } from '../EvaluationResults'

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockAddToast = jest.fn()

jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: mockAddToast }),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, any>) => {
      const translations: Record<string, string> = {
        'evaluation.multiFieldResults.title': 'Evaluation Results',
        'evaluation.multiFieldResults.noResultsYet': 'No evaluation results yet',
        'evaluation.multiFieldResults.noResultsYetDesc':
          'Run an evaluation to see results here.',
        'evaluation.multiFieldResults.runEvaluationNow': 'Run Evaluation Now',
        'evaluation.multiFieldResults.starting': 'Starting...',
        'evaluation.multiFieldResults.runNow': 'Run Now',
        'evaluation.multiFieldResults.running': 'Running...',
        'evaluation.multiFieldResults.refresh': 'Refresh',
        'evaluation.multiFieldResults.evaluation': 'Evaluation',
        'evaluation.multiFieldResults.samplesEvaluated': `${params?.count ?? 0} samples evaluated`,
        'evaluation.multiFieldResults.processing': 'Processing...',
        'evaluation.multiFieldResults.samplesProcessed': `${params?.processed ?? 0}/${params?.total ?? 0} processed`,
        'evaluation.multiFieldResults.vs': 'vs',
        'evaluation.multiFieldResults.noResultsForConfig':
          'No results for this configuration.',
        'evaluation.multiFieldResults.waitingForResults':
          'Waiting for results...',
        'evaluation.multiFieldResults.noConfigsFound':
          'No evaluation configs found.',
        'evaluation.multiFieldResults.tryAgain': 'Try Again',
        'evaluation.multiFieldResults.failedLoadResults':
          'Failed to load evaluation results',
        'evaluation.multiFieldResults.perTaskResults': 'Per-Task Results',
        'evaluation.multiFieldResults.task': 'Task',
        'evaluation.multiFieldResults.average': 'Average',
        'evaluation.multiFieldResults.clickToViewTaskData': 'Click to view task data',
        'evaluation.multiFieldResults.clickToViewResponse': 'Click to view response',
        'evaluation.multiFieldResults.failedLoadTaskData': 'Failed to load task data',
        'evaluation.multiFieldResults.taskDetails': 'Task Details',
        'evaluation.multiFieldResults.model': 'Model',
        'evaluation.multiFieldResults.close': 'Close',
        'evaluation.multiFieldResults.copyJson': 'Copy JSON',
        'evaluation.multiFieldResults.copied': 'Copied!',
        'evaluation.multiFieldResults.annotationResult': 'Annotation Result',
        'evaluation.multiFieldResults.generationResults': 'Generation Results',
        'evaluation.multiFieldResults.evaluationResults': 'Evaluation Results',
        'evaluation.multiFieldResults.noAnnotationData': 'No annotation data available',
        'evaluation.multiFieldResults.noGenerationData': 'No generation data available',
        'evaluation.multiFieldResults.noEvalResults': 'No evaluation results available',
        'evaluation.multiFieldResults.passedCount': `${params?.count ?? 0} passed`,
        'evaluation.multiFieldResults.failedCount': `${params?.count ?? 0} failed`,
        'evaluation.multiFieldResults.skippedCount': `${params?.count ?? 0} skipped`,
        'evaluation.multiFieldResults.unknown': 'Unknown',
        'evaluation.multiFieldResults.justNow': 'just now',
        'evaluation.multiFieldResults.minutesAgo': `${params?.count ?? 0} minutes ago`,
        'evaluation.multiFieldResults.hoursAgo': `${params?.count ?? 0} hours ago`,
        'evaluation.multiFieldResults.daysAgo': `${params?.count ?? 0} days ago`,
        'evaluation.multiFieldResults.completedAgo': `Completed ${params?.time ?? ''}`,
        'evaluation.multiFieldResults.startedAgo': `Started ${params?.time ?? ''}`,
        'evaluation.multiFieldResults.field': 'Field',
        'evaluation.multiFieldResults.passed': 'Passed',
        'evaluation.multiFieldResults.failed': 'Failed',
        'evaluation.multiFieldResults.error': 'Error',
        'evaluation.multiFieldResults.groundTruth': 'Ground Truth',
        'evaluation.multiFieldResults.modelPrediction': 'Model Prediction',
        'evaluation.multiFieldResults.metrics': 'Metrics',
        'evaluation.multiFieldResults.confidence': 'Confidence',
        'evaluation.multiFieldResults.generatedResponse': 'Generated Response',
        'evaluation.multiFieldResults.generatedFields': 'Generated Fields',
        'evaluation.multiFieldResults.promptUsed': 'Prompt Used',
        'evaluation.multiFieldResults.metadata': 'Metadata',
        'evaluation.multiFieldResults.statusLabel': 'Status',
        'evaluation.multiFieldResults.generated': 'Generated',
        'evaluation.multiFieldResults.duration': 'Duration',
        'evaluation.multiFieldResults.rawJsonResponse': 'Raw JSON Response',
        'evaluation.multiFieldResults.llmJudgeResponse': 'LLM Judge Response',
        'evaluation.multiFieldResults.annotation': 'Annotation',
        'evaluation.multiFieldResults.annotator': 'Annotator',
        'evaluation.multiFieldResults.noAnnotationResults': 'No annotation results',
        'evaluation.multiFieldResults.cancelled': 'Cancelled',
        'evaluation.multiFieldResults.default': 'Default',
        'common.tasks': 'tasks',
        'common.models': 'models',
        'common.model': 'model',
        'common.export': 'Export',
      }
      return translations[key] || key
    },
    locale: 'en',
  }),
}))

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

jest.mock('@/components/tasks/TaskDataViewModal', () => ({
  TaskDataViewModal: ({ task, isOpen, onClose }: any) =>
    isOpen ? (
      <div data-testid="task-data-view-modal">
        {task ? <span>Task: {task.id}</span> : <span>Loading task...</span>}
        <button onClick={onClose}>Close Modal</button>
      </div>
    ) : null,
}))

jest.mock('@heroicons/react/24/outline', () => ({
  ArrowDownTrayIcon: (props: any) => <span data-testid="arrow-down-tray-icon" {...props} />,
  ArrowPathIcon: (props: any) => <span data-testid="arrow-path-icon" {...props} />,
  CheckCircleIcon: (props: any) => <span data-testid="check-circle-icon" {...props} />,
  ClockIcon: (props: any) => <span data-testid="clock-icon" {...props} />,
  ClipboardDocumentIcon: (props: any) => <span data-testid="clipboard-icon" {...props} />,
  ExclamationCircleIcon: (props: any) => <span data-testid="exclamation-icon" {...props} />,
  PlayIcon: (props: any) => <span data-testid="play-icon" {...props} />,
  QueueListIcon: (props: any) => <span data-testid="queue-list-icon" {...props} />,
  XCircleIcon: (props: any) => <span data-testid="x-circle-icon" {...props} />,
  XMarkIcon: (props: any) => <span data-testid="x-mark-icon" {...props} />,
}))

// ─── Test Data Factories ──────────────────────────────────────────────────────

function makeEvaluationResult(overrides: Partial<any> = {}) {
  return {
    evaluation_id: 'eval-001',
    model_id: 'gpt-4',
    status: 'completed',
    created_at: new Date(Date.now() - 3600000).toISOString(),
    completed_at: new Date(Date.now() - 1800000).toISOString(),
    samples_evaluated: 50,
    sample_results_count: 50,
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
            scores: { exact_match: 0.82 },
          },
        ],
        aggregate_score: 0.82,
      },
    },
    progress: {
      samples_passed: 41,
      samples_failed: 9,
      samples_skipped: 0,
    },
    ...overrides,
  }
}

function makeProjectResults(evaluations: any[] = [], overrides: Partial<any> = {}) {
  return {
    project_id: 'project-123',
    evaluations,
    total_count: evaluations.length,
    ...overrides,
  }
}

function makeTaskModelData(overrides: Partial<any> = {}) {
  return {
    evaluation_id: 'eval-001',
    models: ['gpt-4', 'claude-3'],
    model_names: { 'gpt-4': 'GPT-4', 'claude-3': 'Claude 3' },
    tasks: [
      {
        task_id: 'task-aaa11111-2222-3333-4444-555566667777',
        task_preview: 'What is the legal basis for...',
        scores: { 'gpt-4': 0.85, 'claude-3': 0.72 },
        has_annotation: true,
        generation_models: ['gpt-4', 'claude-3'],
      },
      {
        task_id: 'task-bbb11111-2222-3333-4444-555566667777',
        task_preview: 'Summarize the ruling in...',
        scores: { 'gpt-4': 0.91, 'claude-3': 0.88 },
        has_annotation: true,
        generation_models: ['gpt-4', 'claude-3'],
      },
    ],
    summary: {
      'gpt-4': { avg: 0.88, count: 2, model_name: 'GPT-4' },
      'claude-3': { avg: 0.8, count: 2, model_name: 'Claude 3' },
    },
    ...overrides,
  }
}

const emptyTaskModelData = {
  evaluation_id: null,
  models: [],
  model_names: {},
  tasks: [],
  summary: {},
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function setupCompletedEvaluation(evalOverrides: Partial<any> = {}, taskModelOverrides: Partial<any> = {}) {
  const evaluation = makeEvaluationResult(evalOverrides)
  mockGetProjectEvaluationResults.mockResolvedValue(
    makeProjectResults([evaluation])
  )
  mockGetProjectResultsByTaskModel.mockResolvedValue(
    makeTaskModelData(taskModelOverrides)
  )
}

function setupEmptyResults() {
  mockGetProjectEvaluationResults.mockResolvedValue(makeProjectResults([]))
  mockGetProjectResultsByTaskModel.mockResolvedValue(emptyTaskModelData)
}

function setupFetchError(message = 'Network error') {
  mockGetProjectEvaluationResults.mockRejectedValue(new Error(message))
  mockGetProjectResultsByTaskModel.mockResolvedValue(emptyTaskModelData)
}

// The component's default for selectedMetrics is [], and the condition
// (selectedMetrics === undefined || selectedMetrics.length > 0) hides the table
// when selectedMetrics is empty. Data view tests need at least one metric selected.
const DATA_VIEW_PROPS = {
  viewType: 'data' as const,
  selectedMetrics: ['exact_match'],
}

// ─── Tests ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  jest.clearAllMocks()
})

describe('EvaluationResults', () => {
  // ─── Loading State ────────────────────────────────────────────────────────

  describe('Loading state', () => {
    it('renders a loading spinner while fetching results', () => {
      mockGetProjectEvaluationResults.mockReturnValue(new Promise(() => {}))
      mockGetProjectResultsByTaskModel.mockReturnValue(new Promise(() => {}))

      render(<EvaluationResults projectId="project-123" />)

      // LoadingSpinner is globally mocked in setupTests.ts with data-testid="loading-spinner"
      expect(screen.getByTestId('loading-spinner')).toBeInTheDocument()
    })
  })

  // ─── Error State ──────────────────────────────────────────────────────────

  describe('Error state', () => {
    it('renders error message when fetch fails', async () => {
      setupFetchError('Server unreachable')

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        expect(screen.getByText('Server unreachable')).toBeInTheDocument()
      })
    })

    it('renders a Try Again button on error that triggers re-fetch', async () => {
      setupFetchError('Server unreachable')

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        expect(screen.getByText('Try Again')).toBeInTheDocument()
      })

      // Now set up success for retry
      setupCompletedEvaluation()

      await userEvent.click(screen.getByText('Try Again'))

      await waitFor(() => {
        expect(mockGetProjectEvaluationResults).toHaveBeenCalledTimes(2)
      })
    })

    it('uses fallback translation key when error has no message', async () => {
      mockGetProjectEvaluationResults.mockRejectedValue({})
      mockGetProjectResultsByTaskModel.mockResolvedValue(emptyTaskModelData)

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        expect(
          screen.getByText('Failed to load evaluation results')
        ).toBeInTheDocument()
      })
    })
  })

  // ─── Empty / No Configuration State ───────────────────────────────────────

  describe('Empty and no-configuration states', () => {
    it('renders null when hasConfiguration is false', async () => {
      setupEmptyResults()

      const { container } = render(
        <EvaluationResults projectId="project-123" hasConfiguration={false} />
      )

      await waitFor(() => {
        expect(mockGetProjectEvaluationResults).toHaveBeenCalled()
      })

      await waitFor(() => {
        expect(container.innerHTML).toBe('')
      })
    })

    it('renders "no results yet" when evaluations array is empty', async () => {
      setupEmptyResults()

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        expect(screen.getByText('No evaluation results yet')).toBeInTheDocument()
      })
      expect(
        screen.getByText('Run an evaluation to see results here.')
      ).toBeInTheDocument()
    })

    it('renders a Run Evaluation button when onRunEvaluation is provided and no results', async () => {
      setupEmptyResults()
      const mockRun = jest.fn()

      render(
        <EvaluationResults projectId="project-123" onRunEvaluation={mockRun} />
      )

      await waitFor(() => {
        expect(screen.getByText('Run Evaluation Now')).toBeInTheDocument()
      })
    })

    it('shows "Starting..." text on Run button when isRunningEvaluation is true', async () => {
      setupEmptyResults()

      render(
        <EvaluationResults
          projectId="project-123"
          onRunEvaluation={jest.fn()}
          isRunningEvaluation={true}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Starting...')).toBeInTheDocument()
      })
    })

    it('disables Run button when isRunningEvaluation is true', async () => {
      setupEmptyResults()

      render(
        <EvaluationResults
          projectId="project-123"
          onRunEvaluation={jest.fn()}
          isRunningEvaluation={true}
        />
      )

      await waitFor(() => {
        const button = screen.getByText('Starting...').closest('button')
        expect(button).toBeDisabled()
      })
    })
  })

  // ─── Chart View (default) – Evaluation Cards ─────────────────────────────

  describe('Chart view – evaluation cards', () => {
    it('renders evaluation header with title and refresh button', async () => {
      setupCompletedEvaluation()

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        expect(screen.getByText('Evaluation Results')).toBeInTheDocument()
      })
      expect(screen.getByText('Refresh')).toBeInTheDocument()
    })

    it('renders completed status badge', async () => {
      setupCompletedEvaluation()

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        expect(screen.getByText('completed')).toBeInTheDocument()
      })
    })

    it('renders model_id chip when model is not "unknown"', async () => {
      setupCompletedEvaluation({ model_id: 'gpt-4' })

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        expect(screen.getByText('gpt-4')).toBeInTheDocument()
      })
    })

    it('does NOT render model_id chip when model_id is "unknown"', async () => {
      setupCompletedEvaluation({ model_id: 'unknown' })

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        expect(screen.getByText('completed')).toBeInTheDocument()
      })

      // The component conditionally renders model chip: model_id && model_id !== 'unknown'
      const chips = document.querySelectorAll('.bg-gray-100')
      const unknownChip = Array.from(chips).find(el => el.textContent === 'unknown')
      expect(unknownChip).toBeUndefined()
    })

    it('renders samples evaluated count', async () => {
      setupCompletedEvaluation({ samples_evaluated: 50 })

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        expect(screen.getByText('50 samples evaluated')).toBeInTheDocument()
      })
    })

    it('renders aggregate score for a completed evaluation config', async () => {
      setupCompletedEvaluation()

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        // Aggregate score 0.82 formatted as 0.820 (appears as aggregate + field result)
        const scores = screen.getAllByText('0.820')
        expect(scores.length).toBeGreaterThanOrEqual(1)
      })
    })

    it('renders metric display name from config', async () => {
      setupCompletedEvaluation()

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        // Post the "drop misleading samples count from dropdown" change,
        // 'Exact Match' appears both in the metric-selector option AND in
        // the eval card. We just want the eval card here.
        expect(screen.getAllByText('Exact Match').length).toBeGreaterThan(0)
      })
    })

    it('renders field result with prediction vs reference fields', async () => {
      setupCompletedEvaluation()

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        expect(screen.getByText('answer')).toBeInTheDocument()
        expect(screen.getByText('gold_answer')).toBeInTheDocument()
        expect(screen.getByText('vs')).toBeInTheDocument()
      })
    })

    it('renders score bar for field results', async () => {
      setupCompletedEvaluation()

      render(<EvaluationResults projectId="project-123" viewType="chart" />)

      await waitFor(() => {
        const bars = document.querySelectorAll('.bg-emerald-500')
        expect(bars.length).toBeGreaterThan(0)
      })
    })

    it('renders footer with passed/failed counts for completed evaluations', async () => {
      setupCompletedEvaluation({
        progress: { samples_passed: 41, samples_failed: 9, samples_skipped: 0 },
      })

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        expect(screen.getByText('41 passed')).toBeInTheDocument()
        expect(screen.getByText('9 failed')).toBeInTheDocument()
      })
    })

    it('renders skipped count only when > 0', async () => {
      setupCompletedEvaluation({
        progress: { samples_passed: 40, samples_failed: 5, samples_skipped: 5 },
      })

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        expect(screen.getByText('5 skipped')).toBeInTheDocument()
      })
    })

    it('does not render skipped count when 0', async () => {
      setupCompletedEvaluation({
        progress: { samples_passed: 41, samples_failed: 9, samples_skipped: 0 },
      })

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        expect(screen.getByText('41 passed')).toBeInTheDocument()
      })
      expect(screen.queryByText('0 skipped')).not.toBeInTheDocument()
    })

    it('renders truncated evaluation ID in footer', async () => {
      setupCompletedEvaluation({ evaluation_id: 'eval-abcdefgh-1234-5678' })

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        expect(screen.getByText(/ID: eval-abc/)).toBeInTheDocument()
      })
    })
  })

  // ─── Running Evaluation Status ────────────────────────────────────────────

  describe('Running evaluation', () => {
    it('renders running status badge and processing text', async () => {
      setupCompletedEvaluation({ status: 'running', completed_at: null })

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        expect(screen.getByText('running')).toBeInTheDocument()
        expect(screen.getByText('Processing...')).toBeInTheDocument()
      })
    })

    it('renders progress bar for running evaluation', async () => {
      setupCompletedEvaluation({
        status: 'running',
        completed_at: null,
        samples_evaluated: 100,
        progress: { samples_passed: 30, samples_failed: 10, samples_skipped: 0 },
      })

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        expect(screen.getByText('40/100 processed')).toBeInTheDocument()
      })

      const progressBar = document.querySelector('.bg-blue-500')
      expect(progressBar).toBeInTheDocument()
      expect(progressBar).toHaveStyle({ width: '40%' })
    })

    it('shows "Waiting for results..." for configs without results yet', async () => {
      setupCompletedEvaluation({
        status: 'running',
        completed_at: null,
        results_by_config: {
          'config-1': {
            field_results: [],
            aggregate_score: null,
          },
        },
      })

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        expect(screen.getByText('Waiting for results...')).toBeInTheDocument()
      })
    })
  })

  // ─── Failed / Pending Evaluations ─────────────────────────────────────────

  describe('Failed evaluation', () => {
    it('renders failed status badge', async () => {
      setupCompletedEvaluation({ status: 'failed', completed_at: null })

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        expect(screen.getByText('failed')).toBeInTheDocument()
      })
    })

    it('renders error message when present', async () => {
      setupCompletedEvaluation({
        status: 'failed',
        error_message: 'Metric computation failed: division by zero',
      })

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        expect(
          screen.getByText('Metric computation failed: division by zero')
        ).toBeInTheDocument()
      })
    })
  })

  describe('Pending evaluation', () => {
    it('renders pending status badge', async () => {
      setupCompletedEvaluation({ status: 'pending', completed_at: null })

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        expect(screen.getByText('pending')).toBeInTheDocument()
      })
    })
  })

  // ─── Data View – Per-Task/Model Table ─────────────────────────────────────

  describe('Data view – per-task/model table', () => {
    it('renders per-task table with model columns in data view', async () => {
      setupCompletedEvaluation()

      render(
        <EvaluationResults projectId="project-123" {...DATA_VIEW_PROPS} />
      )

      await waitFor(() => {
        expect(screen.getByText('Per-Task Results')).toBeInTheDocument()
        expect(screen.getByText('GPT-4')).toBeInTheDocument()
        expect(screen.getByText('Claude 3')).toBeInTheDocument()
      })
    })

    it('renders task previews as clickable rows', async () => {
      setupCompletedEvaluation()

      render(<EvaluationResults projectId="project-123" {...DATA_VIEW_PROPS} />)

      await waitFor(() => {
        expect(
          screen.getByText('What is the legal basis for...')
        ).toBeInTheDocument()
        expect(
          screen.getByText('Summarize the ruling in...')
        ).toBeInTheDocument()
      })
    })

    it('renders scores in 3-decimal academic format', async () => {
      setupCompletedEvaluation()

      render(<EvaluationResults projectId="project-123" {...DATA_VIEW_PROPS} />)

      await waitFor(() => {
        expect(screen.getByText('0.850')).toBeInTheDocument()
        expect(screen.getByText('0.720')).toBeInTheDocument()
        expect(screen.getByText('0.910')).toBeInTheDocument()
      })
    })

    it('highlights best score per row in emerald', async () => {
      setupCompletedEvaluation()

      render(<EvaluationResults projectId="project-123" {...DATA_VIEW_PROPS} />)

      await waitFor(() => {
        // Score 0.850 (gpt-4 is best for task 1 since 0.85 > 0.72)
        const score850 = screen.getByText('0.850')
        expect(score850.className).toContain('text-emerald-600')
      })
    })

    it('renders average row with summary scores', async () => {
      setupCompletedEvaluation()

      render(<EvaluationResults projectId="project-123" {...DATA_VIEW_PROPS} />)

      await waitFor(() => {
        expect(screen.getByText('Average')).toBeInTheDocument()
      })
    })

    it('shows task and model counts in header', async () => {
      setupCompletedEvaluation()

      render(<EvaluationResults projectId="project-123" {...DATA_VIEW_PROPS} />)

      await waitFor(() => {
        expect(screen.getByText(/2 tasks/)).toBeInTheDocument()
        expect(screen.getByText(/2 models/)).toBeInTheDocument()
      })
    })

    it('shows "n/a" for models without a score for a task', async () => {
      setupCompletedEvaluation(
        {},
        {
          models: ['gpt-4', 'claude-3', 'llama-2'],
          model_names: { 'gpt-4': 'GPT-4', 'claude-3': 'Claude 3', 'llama-2': 'Llama 2' },
          tasks: [
            {
              task_id: 'task-aaa',
              task_preview: 'Test task',
              scores: { 'gpt-4': 0.9 },
              has_annotation: true,
              generation_models: ['gpt-4'],
            },
          ],
          summary: {
            'gpt-4': { avg: 0.9, count: 1, model_name: 'GPT-4' },
            'claude-3': { avg: null, count: 0, model_name: 'Claude 3' },
            'llama-2': { avg: null, count: 0, model_name: 'Llama 2' },
          },
        }
      )

      render(<EvaluationResults projectId="project-123" {...DATA_VIEW_PROPS} />)

      await waitFor(() => {
        const naCells = screen.getAllByText('n/a')
        expect(naCells.length).toBeGreaterThanOrEqual(2)
      })
    })
  })

  // ─── Filtering ────────────────────────────────────────────────────────────

  describe('Filtering evaluations', () => {
    it('filters evaluations by selectedModels in chart view', async () => {
      const eval1 = makeEvaluationResult({ evaluation_id: 'eval-1', model_id: 'gpt-4' })
      const eval2 = makeEvaluationResult({ evaluation_id: 'eval-2', model_id: 'claude-3' })
      mockGetProjectEvaluationResults.mockResolvedValue(
        makeProjectResults([eval1, eval2])
      )
      mockGetProjectResultsByTaskModel.mockResolvedValue(makeTaskModelData())

      render(
        <EvaluationResults projectId="project-123" selectedModels={['gpt-4']} />
      )

      await waitFor(() => {
        expect(screen.getByText('gpt-4')).toBeInTheDocument()
      })

      // claude-3 model chip should NOT appear
      expect(screen.queryByText('claude-3')).not.toBeInTheDocument()
    })

    it('filters by eval type - shows only llm-judge evaluations', async () => {
      const automatedEval = makeEvaluationResult({
        evaluation_id: 'eval-auto',
        model_id: 'gpt-4',
        evaluation_configs: [
          { id: 'c1', metric: 'exact_match', metric_type: 'automated', prediction_fields: ['a'], reference_fields: ['b'], enabled: true },
        ],
      })
      const llmEval = makeEvaluationResult({
        evaluation_id: 'eval-llm',
        model_id: 'claude-3',
        evaluation_configs: [
          { id: 'c2', metric: 'llm_judge', metric_type: 'llm-judge', prediction_fields: ['a'], reference_fields: ['b'], enabled: true },
        ],
      })
      mockGetProjectEvaluationResults.mockResolvedValue(
        makeProjectResults([automatedEval, llmEval])
      )
      mockGetProjectResultsByTaskModel.mockResolvedValue(makeTaskModelData())

      render(
        <EvaluationResults
          projectId="project-123"
          selectedEvalTypes={['llm-judge']}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('claude-3')).toBeInTheDocument()
      })

      expect(screen.queryByText('gpt-4')).not.toBeInTheDocument()
    })
  })

  // ─── Callbacks ────────────────────────────────────────────────────────────

  describe('Callbacks', () => {
    it('calls onResultsLoaded(true) when results are available', async () => {
      setupCompletedEvaluation()
      const onResultsLoaded = jest.fn()

      render(
        <EvaluationResults projectId="project-123" onResultsLoaded={onResultsLoaded} />
      )

      await waitFor(() => {
        expect(onResultsLoaded).toHaveBeenCalledWith(true)
      })
    })

    it('calls onResultsLoaded(false) when no results', async () => {
      setupEmptyResults()
      const onResultsLoaded = jest.fn()

      render(
        <EvaluationResults projectId="project-123" onResultsLoaded={onResultsLoaded} />
      )

      await waitFor(() => {
        expect(onResultsLoaded).toHaveBeenCalledWith(false)
      })
    })

    it('calls onRefresh when refresh button is clicked', async () => {
      setupCompletedEvaluation()
      const onRefresh = jest.fn()

      render(
        <EvaluationResults projectId="project-123" onRefresh={onRefresh} />
      )

      await waitFor(() => {
        expect(screen.getByText('Refresh')).toBeInTheDocument()
      })

      await userEvent.click(screen.getByText('Refresh'))

      expect(onRefresh).toHaveBeenCalledTimes(1)
    })

    it('calls onRunEvaluation when Run Now button is clicked', async () => {
      setupCompletedEvaluation()
      const onRunEvaluation = jest.fn()

      render(
        <EvaluationResults projectId="project-123" onRunEvaluation={onRunEvaluation} />
      )

      await waitFor(() => {
        expect(screen.getByText('Run Now')).toBeInTheDocument()
      })

      await userEvent.click(screen.getByText('Run Now'))

      expect(onRunEvaluation).toHaveBeenCalledTimes(1)
    })

    it('calls onDataLoaded with chart data from taskModelData summary', async () => {
      setupCompletedEvaluation()
      const onDataLoaded = jest.fn()

      render(
        <EvaluationResults projectId="project-123" onDataLoaded={onDataLoaded} />
      )

      await waitFor(() => {
        expect(onDataLoaded).toHaveBeenCalled()
      })

      const lastCall = onDataLoaded.mock.calls[onDataLoaded.mock.calls.length - 1][0]
      expect(lastCall).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ model_id: 'gpt-4', model_name: 'GPT-4' }),
          expect.objectContaining({ model_id: 'claude-3', model_name: 'Claude 3' }),
        ])
      )
    })
  })

  // ─── Statistics Display ───────────────────────────────────────────────────

  describe('Inline statistics in data view', () => {
    const statisticsData = {
      by_model: {
        'gpt-4': {
          model_name: 'GPT-4',
          metrics: {
            exact_match: {
              mean: 0.88,
              std: 0.05,
              se: 0.012,
              ci_lower: 0.856,
              ci_upper: 0.904,
              n: 50,
            },
          },
          sample_count: 50,
        },
      },
    }

    it('renders standard error annotation when "se" is selected', async () => {
      setupCompletedEvaluation()

      render(
        <EvaluationResults
          projectId="project-123"
          {...DATA_VIEW_PROPS}
          statisticsData={statisticsData}
          selectedStatistics={['se']}
        />
      )

      await waitFor(() => {
        expect(screen.getByText(/±0\.012/)).toBeInTheDocument()
      })
    })

    it('renders standard deviation annotation when "std" is selected', async () => {
      setupCompletedEvaluation()

      render(
        <EvaluationResults
          projectId="project-123"
          {...DATA_VIEW_PROPS}
          statisticsData={statisticsData}
          selectedStatistics={['std']}
        />
      )

      await waitFor(() => {
        expect(screen.getByText(/σ0\.050/)).toBeInTheDocument()
      })
    })

    it('renders 95% CI annotation when "ci" is selected', async () => {
      setupCompletedEvaluation()

      render(
        <EvaluationResults
          projectId="project-123"
          {...DATA_VIEW_PROPS}
          statisticsData={statisticsData}
          selectedStatistics={['ci']}
        />
      )

      await waitFor(() => {
        expect(screen.getByText(/85\.6%.*90\.4%/)).toBeInTheDocument()
      })
    })

    it('does not render stats when selectedStatistics is empty', async () => {
      setupCompletedEvaluation()

      render(
        <EvaluationResults
          projectId="project-123"
          {...DATA_VIEW_PROPS}
          statisticsData={statisticsData}
          selectedStatistics={[]}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Average')).toBeInTheDocument()
      })

      expect(screen.queryByText(/±/)).not.toBeInTheDocument()
      expect(screen.queryByText(/σ/)).not.toBeInTheDocument()
    })
  })

  // ─── Score Formatting ─────────────────────────────────────────────────────

  describe('Score formatting (formatScore)', () => {
    it('formats score with 3 decimal places (academic standard)', async () => {
      setupCompletedEvaluation({
        results_by_config: {
          'config-1': {
            field_results: [
              {
                combo_key: 'a_vs_b',
                prediction_field: 'a',
                reference_field: 'b',
                scores: { score: 0.5 },
              },
            ],
            aggregate_score: 0.5,
          },
        },
      })

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        // 0.500 appears twice: once as aggregate_score and once in field_results
        const scores = screen.getAllByText('0.500')
        expect(scores.length).toBeGreaterThanOrEqual(1)
      })
    })
  })

  // ─── Metric Display Name Logic ────────────────────────────────────────────

  describe('Metric display name', () => {
    it('uses display_name from config when available', async () => {
      setupCompletedEvaluation({
        evaluation_configs: [
          {
            id: 'config-1',
            metric: 'f1_score',
            display_name: 'F1 Score (Macro)',
            metric_type: 'automated',
            metric_parameters: {},
            prediction_fields: ['a'],
            reference_fields: ['b'],
            enabled: true,
          },
        ],
      })

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        expect(screen.getAllByText('F1 Score (Macro)').length).toBeGreaterThan(0)
      })
    })

    it('formats metric name from underscored key when no display_name', async () => {
      setupCompletedEvaluation({
        evaluation_configs: [
          {
            id: 'config-1',
            metric: 'exact_match',
            display_name: undefined,
            metric_type: 'automated',
            metric_parameters: {},
            prediction_fields: ['a'],
            reference_fields: ['b'],
            enabled: true,
          },
        ],
      })

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        // 'exact_match' -> 'Exact match'
        expect(screen.getByText('Exact match')).toBeInTheDocument()
      })
    })

    it('appends metric parameters to formatted name', async () => {
      setupCompletedEvaluation({
        evaluation_configs: [
          {
            id: 'config-1',
            metric: 'rouge',
            display_name: undefined,
            metric_type: 'automated',
            metric_parameters: { variant: 'rouge-l' },
            prediction_fields: ['a'],
            reference_fields: ['b'],
            enabled: true,
          },
        ],
      })

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        expect(screen.getByText('Rouge (variant=rouge-l)')).toBeInTheDocument()
      })
    })
  })

  // ─── No Configs Found ─────────────────────────────────────────────────────

  describe('No evaluation configs', () => {
    it('renders "No evaluation configs found" when configs array is empty', async () => {
      setupCompletedEvaluation({
        evaluation_configs: [],
        results_by_config: {},
      })

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        expect(
          screen.getByText('No evaluation configs found.')
        ).toBeInTheDocument()
      })
    })
  })

  // ─── Completed Evaluation with No Field Results ───────────────────────────

  describe('Completed evaluation with empty field results', () => {
    it('renders "No results for this configuration" for completed eval', async () => {
      setupCompletedEvaluation({
        results_by_config: {
          'config-1': {
            field_results: [],
            aggregate_score: null,
          },
        },
      })

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        expect(
          screen.getByText('No results for this configuration.')
        ).toBeInTheDocument()
      })
    })
  })

  // ─── Refresh Key ──────────────────────────────────────────────────────────

  describe('Refresh key', () => {
    it('re-fetches results when refreshKey changes', async () => {
      setupCompletedEvaluation()

      const { rerender } = render(
        <EvaluationResults projectId="project-123" refreshKey={1} />
      )

      await waitFor(() => {
        expect(mockGetProjectEvaluationResults).toHaveBeenCalledTimes(1)
      })

      rerender(<EvaluationResults projectId="project-123" refreshKey={2} />)

      await waitFor(() => {
        expect(mockGetProjectEvaluationResults).toHaveBeenCalledTimes(2)
      })
    })
  })

  // ─── Annotator Model Display ──────────────────────────────────────────────

  describe('Annotator model display in data view', () => {
    it('strips "annotator:" prefix and shows username', async () => {
      setupCompletedEvaluation(
        {},
        {
          models: ['annotator:john_doe', 'gpt-4'],
          model_names: { 'gpt-4': 'GPT-4' },
          tasks: [
            {
              task_id: 'task-aaa',
              task_preview: 'Legal question',
              scores: { 'annotator:john_doe': 0.95, 'gpt-4': 0.82 },
              has_annotation: true,
              generation_models: ['gpt-4'],
            },
          ],
          summary: {
            'annotator:john_doe': { avg: 0.95, count: 1, model_name: 'john_doe' },
            'gpt-4': { avg: 0.82, count: 1, model_name: 'GPT-4' },
          },
        }
      )

      render(<EvaluationResults projectId="project-123" {...DATA_VIEW_PROPS} />)

      await waitFor(() => {
        expect(screen.getByText('john_doe')).toBeInTheDocument()
      })
    })

    it('applies blue styling to annotator column header', async () => {
      setupCompletedEvaluation(
        {},
        {
          models: ['annotator:reviewer1'],
          model_names: {},
          tasks: [
            {
              task_id: 'task-a',
              task_preview: 'Task',
              scores: { 'annotator:reviewer1': 0.9 },
              has_annotation: true,
              generation_models: [],
            },
          ],
          summary: {
            'annotator:reviewer1': { avg: 0.9, count: 1, model_name: 'reviewer1' },
          },
        }
      )

      render(<EvaluationResults projectId="project-123" {...DATA_VIEW_PROPS} />)

      await waitFor(() => {
        const annotatorLabel = screen.getByText('reviewer1')
        expect(annotatorLabel.className).toContain('bg-blue-100')
      })
    })
  })

  // ─── Multiple Evaluations ─────────────────────────────────────────────────

  describe('Multiple evaluations', () => {
    it('renders multiple evaluation cards in chart view', async () => {
      const eval1 = makeEvaluationResult({ evaluation_id: 'eval-1', model_id: 'gpt-4' })
      const eval2 = makeEvaluationResult({
        evaluation_id: 'eval-2',
        model_id: 'claude-3',
        evaluation_configs: [
          {
            id: 'config-2',
            metric: 'f1_score',
            display_name: 'F1 Score',
            metric_type: 'automated',
            metric_parameters: {},
            prediction_fields: ['answer'],
            reference_fields: ['gold_answer'],
            enabled: true,
          },
        ],
        results_by_config: {
          'config-2': {
            field_results: [
              {
                combo_key: 'a_vs_b',
                prediction_field: 'answer',
                reference_field: 'gold_answer',
                scores: { f1_score: 0.75 },
              },
            ],
            aggregate_score: 0.75,
          },
        },
      })
      mockGetProjectEvaluationResults.mockResolvedValue(
        makeProjectResults([eval1, eval2])
      )
      mockGetProjectResultsByTaskModel.mockResolvedValue(makeTaskModelData())

      render(<EvaluationResults projectId="project-123" />)

      // Component deduplicates by metric and shows one eval at a time with a dropdown.
      // Both evals with different metrics should appear as options in the dropdown
      // and both should have cards rendered.
      await waitFor(() => {
        expect(screen.getByText('gpt-4')).toBeInTheDocument()
      })
      // The second eval card should also be visible since it has a different metric
      expect(screen.getByText('claude-3')).toBeInTheDocument()
    })
  })

  // ─── External Model Names ─────────────────────────────────────────────────

  describe('External model names', () => {
    it('uses modelNames prop when API model_names is empty', async () => {
      setupCompletedEvaluation(
        {},
        {
          models: ['custom-model-1'],
          model_names: {},
          tasks: [
            {
              task_id: 'task-a',
              task_preview: 'Test',
              scores: { 'custom-model-1': 0.77 },
              has_annotation: true,
              generation_models: ['custom-model-1'],
            },
          ],
          summary: {
            'custom-model-1': { avg: 0.77, count: 1, model_name: 'custom-model-1' },
          },
        }
      )

      render(
        <EvaluationResults
          projectId="project-123"
          {...DATA_VIEW_PROPS}
          modelNames={{ 'custom-model-1': 'Custom Model v1' }}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Custom Model v1')).toBeInTheDocument()
      })
    })
  })

  // ─── Polling for Running Evaluations ──────────────────────────────────────

  describe('Polling', () => {
    it('sets up polling interval when evaluation is running', async () => {
      jest.useFakeTimers()

      setupCompletedEvaluation({ status: 'running', completed_at: null })

      render(<EvaluationResults projectId="project-123" />)

      // Wait for initial render to complete
      await act(async () => {
        await jest.advanceTimersByTimeAsync(100)
      })

      const callCountAfterRender = mockGetProjectEvaluationResults.mock.calls.length

      // Advance by the 5000ms polling interval
      await act(async () => {
        await jest.advanceTimersByTimeAsync(5000)
      })

      expect(mockGetProjectEvaluationResults.mock.calls.length).toBeGreaterThan(
        callCountAfterRender
      )

      jest.useRealTimers()
    })
  })

  // ─── Run Button States ────────────────────────────────────────────────────

  describe('Run button in header (when results exist)', () => {
    it('shows Run Now button when onRunEvaluation is provided', async () => {
      setupCompletedEvaluation()

      render(
        <EvaluationResults projectId="project-123" onRunEvaluation={jest.fn()} />
      )

      await waitFor(() => {
        expect(screen.getByText('Run Now')).toBeInTheDocument()
      })
    })

    it('shows "Running..." when isRunningEvaluation is true', async () => {
      setupCompletedEvaluation()

      render(
        <EvaluationResults
          projectId="project-123"
          onRunEvaluation={jest.fn()}
          isRunningEvaluation={true}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Running...')).toBeInTheDocument()
      })
    })

    it('does not show Run button when onRunEvaluation is not provided', async () => {
      setupCompletedEvaluation()

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        expect(screen.getByText('Refresh')).toBeInTheDocument()
      })

      expect(screen.queryByText('Run Now')).not.toBeInTheDocument()
    })
  })

  // ─── Time Formatting ─────────────────────────────────────────────────────

  describe('Time formatting in evaluation cards', () => {
    it('renders "Completed" with time ago for completed evaluations', async () => {
      setupCompletedEvaluation({
        completed_at: new Date(Date.now() - 1800000).toISOString(),
      })

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        expect(screen.getByText(/Completed/)).toBeInTheDocument()
      })
    })

    it('renders "Started" with time ago when no completed_at', async () => {
      setupCompletedEvaluation({
        status: 'running',
        completed_at: null,
        created_at: new Date(Date.now() - 600000).toISOString(),
      })

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        expect(screen.getByText(/Started/)).toBeInTheDocument()
      })
    })
  })

  // ─── formatTimeAgo edge cases ─────────────────────────────────────────

  describe('formatTimeAgo edge cases', () => {
    it('renders "just now" for very recent evaluations', async () => {
      setupCompletedEvaluation({
        completed_at: new Date().toISOString(),
      })

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        expect(screen.getByText(/just now/)).toBeInTheDocument()
      })
    })

    it('renders "X days ago" for evaluations completed days ago', async () => {
      setupCompletedEvaluation({
        completed_at: new Date(Date.now() - 172800000).toISOString(), // 2 days ago
      })

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        expect(screen.getByText(/2 days ago/)).toBeInTheDocument()
      })
    })

    it('renders "Unknown" for null date', async () => {
      setupCompletedEvaluation({
        completed_at: null,
        created_at: null,
        status: 'completed',
      })

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        expect(screen.getByText(/Unknown/)).toBeInTheDocument()
      })
    })
  })

  // ─── getStatusIcon default case ───────────────────────────────────────

  describe('Status icon for unknown status', () => {
    it('renders exclamation icon for unknown status', async () => {
      setupCompletedEvaluation({ status: 'weird_unknown_status' })

      render(<EvaluationResults projectId="project-123" />)

      await waitFor(() => {
        expect(screen.getByTestId('exclamation-icon')).toBeInTheDocument()
      })
    })
  })

  // ─── onDataLoaded callback with chart data ────────────────────────

  describe('onDataLoaded callback', () => {
    it('calls onDataLoaded with chart data extracted from taskModelData', async () => {
      const onDataLoaded = jest.fn()
      setupCompletedEvaluation()

      render(
        <EvaluationResults
          projectId="project-123"
          onDataLoaded={onDataLoaded}
        />
      )

      await waitFor(() => {
        expect(onDataLoaded).toHaveBeenCalled()
      })

      const chartData = onDataLoaded.mock.calls[onDataLoaded.mock.calls.length - 1][0]
      expect(chartData).toEqual(expect.arrayContaining([
        expect.objectContaining({
          model_id: 'gpt-4',
          model_name: 'GPT-4',
        }),
        expect.objectContaining({
          model_id: 'claude-3',
          model_name: 'Claude 3',
        }),
      ]))
    })
  })

  // ─── Eval type filtering ──────────────────────────────────────────

  describe('Eval type filtering', () => {
    it('filters evaluations by llm-judge type', async () => {
      const llmJudgeEval = makeEvaluationResult({
        evaluation_id: 'eval-llm',
        evaluation_configs: [
          {
            id: 'config-llm',
            metric: 'llm_judge_custom',
            display_name: 'LLM Judge',
            metric_type: 'llm_judge',
            metric_parameters: {},
            prediction_fields: ['answer'],
            reference_fields: ['gold_answer'],
            enabled: true,
          },
        ],
        results_by_config: {
          'config-llm': { field_results: [], aggregate_score: 0.75 },
        },
      })

      mockGetProjectEvaluationResults.mockResolvedValue(
        makeProjectResults([llmJudgeEval])
      )
      mockGetProjectResultsByTaskModel.mockResolvedValue(makeTaskModelData())

      render(
        <EvaluationResults
          projectId="project-123"
          selectedEvalTypes={['llm-judge']}
        />
      )

      await waitFor(() => {
        // The LLM judge evaluation should appear (in both dropdown and card)
        const matches = screen.getAllByText(/LLM Judge/)
        expect(matches.length).toBeGreaterThanOrEqual(1)
      })
    })

    it('filters evaluations by human type', async () => {
      const humanEval = makeEvaluationResult({
        evaluation_id: 'eval-human',
        evaluation_configs: [
          {
            id: 'config-human',
            metric: 'agreement',
            display_name: 'Human Agreement',
            metric_type: 'human',
            metric_parameters: {},
            prediction_fields: ['answer'],
            reference_fields: ['gold_answer'],
            enabled: true,
          },
        ],
        results_by_config: {
          'config-human': { field_results: [], aggregate_score: 0.9 },
        },
      })

      mockGetProjectEvaluationResults.mockResolvedValue(
        makeProjectResults([humanEval])
      )
      mockGetProjectResultsByTaskModel.mockResolvedValue(makeTaskModelData())

      render(
        <EvaluationResults
          projectId="project-123"
          selectedEvalTypes={['human']}
        />
      )

      await waitFor(() => {
        // Human Agreement appears in both dropdown and card
        const matches = screen.getAllByText(/Human Agreement/)
        expect(matches.length).toBeGreaterThanOrEqual(1)
      })
    })
  })

})
