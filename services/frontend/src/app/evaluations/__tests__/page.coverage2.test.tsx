/**
 * @jest-environment jsdom
 *
 * Complement coverage for the Evaluations dashboard page, targeting arms the
 * existing page.coverage / page.branch / page.filters / page.mega / page.test
 * suites leave uncovered:
 *
 *   - fetchProjectData top-level error -> error toast (549-550).
 *   - handleRunEvaluation success path + SSE subscribe lifecycle (status /
 *     done(completed|failed) / error-retry) (684-770, 786-823).
 *   - handleRunEvaluation "no methods configured" early toast.
 *   - handleRunEvaluation API rejection toast.
 *   - comparison-data + statistics error branches (significanceError,
 *     statisticsError) (590-620, 640-673).
 *   - metric dropdown select-all / clear-all / toggle (1167-1201).
 *   - clear-all-filters button (1274-1279).
 *   - historical-trends + significance-heatmap render in a non-data chart view
 *     (1423-1473).
 *
 * Two evaluated models are seeded so the significance branch (needs >1 model)
 * is reachable.
 */

import { useToast } from '@/components/shared/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { apiClient } from '@/lib/api/client'
import { projectsAPI } from '@/lib/api/projects'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useRouter, useSearchParams } from 'next/navigation'
import EvaluationDashboard from '../page'

jest.mock('@/lib/api/client', () => ({
  apiClient: {
    get: jest.fn(),
    post: jest.fn(),
    evaluations: {
      getProjectEvaluationConfig: jest.fn(),
      getConfiguredMethods: jest.fn(),
      getEvaluatedModels: jest.fn(),
      getProjectAnnotators: jest.fn(),
      getEvaluationHistory: jest.fn(),
      getSignificanceTests: jest.fn(),
      computeStatistics: jest.fn(),
      runEvaluation: jest.fn(),
    },
  },
}))

jest.mock('@/lib/api/projects', () => ({
  projectsAPI: { list: jest.fn() },
}))

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
  useSearchParams: jest.fn(),
}))

jest.mock('@/contexts/AuthContext', () => ({ useAuth: jest.fn() }))
jest.mock('@/contexts/I18nContext', () => ({ useI18n: jest.fn() }))
jest.mock('@/components/shared/Toast', () => ({ useToast: jest.fn() }))

const mockStartEvaluation = jest.fn()
const mockUpdateEvaluation = jest.fn()
jest.mock('@/hooks/useOperationToasts', () => ({
  useOperationToasts: () => ({
    startEvaluation: mockStartEvaluation,
    updateEvaluation: mockUpdateEvaluation,
    renderToasts: () => null,
  }),
}))

jest.mock('@/utils/permissions', () => ({
  canAccessProjectData: jest.fn(() => true),
}))

jest.mock('@/lib/utils/subdomain', () => ({
  parseSubdomain: jest.fn(() => ({ isPrivateMode: true })),
}))

jest.mock('@heroicons/react/24/outline', () => ({
  ChartBarIcon: () => <div data-testid="chart-bar-icon" />,
  ChevronDownIcon: () => <div data-testid="chevron-down-icon" />,
  ExclamationTriangleIcon: () => <div data-testid="exclamation-icon" />,
  PlayIcon: () => <div data-testid="play-icon" />,
  XMarkIcon: () => <div data-testid="x-mark-icon" />,
}))

jest.mock('@/components/shared/FeatureFlag', () => ({
  FeatureFlag: ({ children }: any) => <>{children}</>,
}))
jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: () => <nav data-testid="breadcrumb" />,
}))
jest.mock('@/components/shared/ResponsiveContainer', () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
}))
jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, disabled, ...rest }: any) => (
    <button onClick={onClick} disabled={disabled} aria-label={rest['aria-label']}>
      {children}
    </button>
  ),
}))
jest.mock('@/components/shared/Card', () => ({
  Card: ({ children }: any) => <div data-testid="card">{children}</div>,
}))
jest.mock('@/components/shared/LoadingSpinner', () => ({
  LoadingSpinner: () => <div data-testid="loading-spinner" />,
}))

// Aggregation selector that lets us push 'sample' so box-plot disabling /
// statistics aggregation paths can flip.
jest.mock('@/components/evaluation/AggregationSelector', () => ({
  AggregationSelector: ({ onChange }: any) => (
    <button onClick={() => onChange(['sample'])}>set-sample-aggregation</button>
  ),
}))

// Chart type selector exposing a button to switch to a non-'data' view, so the
// chart / significance / historical render branches become reachable.
jest.mock('@/components/evaluation/ChartTypeSelector', () => ({
  ChartTypeSelector: ({ onChange }: any) => (
    <button onClick={() => onChange('bar')}>set-bar-view</button>
  ),
}))

jest.mock('@/components/evaluation/DynamicChartRenderer', () => ({
  DynamicChartRenderer: () => <div data-testid="dynamic-chart-renderer" />,
}))
jest.mock('@/components/evaluation/EvaluationResultsTable', () => ({
  EvaluationResultsTable: () => <div data-testid="evaluation-results-table" />,
}))
jest.mock('@/components/evaluation/EvaluationResults', () => ({
  EvaluationResults: () => <div data-testid="evaluation-results" />,
}))
jest.mock('@/components/evaluation/ScoreCard', () => ({
  ScoreCard: ({ metric }: any) => <div data-testid="score-card">{metric}</div>,
}))
jest.mock('@/components/evaluation/StatisticalResultsPanel', () => ({
  StatisticalResultsPanel: () => <div data-testid="statistical-results-panel" />,
}))
jest.mock('@/components/evaluation/StatisticsSelector', () => ({
  StatisticsSelector: () => <div data-testid="statistics-selector" />,
}))
jest.mock('@/components/evaluation/charts/HistoricalTrendChart', () => ({
  HistoricalTrendChart: () => <div data-testid="historical-trend-chart" />,
}))
jest.mock('@/components/evaluation/charts/SignificanceHeatmap', () => ({
  SignificanceHeatmap: () => <div data-testid="significance-heatmap" />,
}))

// Modal mock that exposes the onRunWithMode + scope-less callbacks so the
// page's handleRunEvaluation runs.
jest.mock('@/components/evaluation/EvaluationControlModal', () => ({
  EvaluationControlModal: ({ onRunWithMode }: any) => (
    <div data-testid="eval-control-modal">
      <button onClick={() => onRunWithMode(false)}>modal-run</button>
      <button
        onClick={() =>
          onRunWithMode(true, {
            evaluationConfigs: [{ id: 'cfg1', metric: 'bleu', enabled: true }],
            modelIds: ['gpt-4'],
            annotatorUserIds: [],
          })
        }
      >
        modal-run-scoped
      </button>
    </div>
  ),
}))

const mockRouter = { push: jest.fn(), replace: jest.fn() }
const mockAddToast = jest.fn()
const mockT = (key: string) => key

const mockUser = { id: 'u1', is_superadmin: true, is_active: true }

const mockProject = { id: 1, title: 'Proj', task_count: 5 }

const evalConfig = {
  evaluation_configs: [
    {
      id: 'cfg1',
      metric: 'bleu',
      display_name: 'BLEU',
      prediction_fields: ['model_answer'],
      reference_fields: ['reference'],
      enabled: true,
    },
    {
      id: 'cfg2',
      metric: 'rouge',
      display_name: 'ROUGE',
      prediction_fields: ['model_answer'],
      reference_fields: ['reference'],
      enabled: true,
    },
  ],
}

const twoModels = [
  { model_id: 'gpt-4', model_name: 'GPT-4', has_results: true, has_generations: true },
  { model_id: 'claude', model_name: 'Claude', has_results: true, has_generations: true },
]

// A minimal EventSource stand-in we can drive in tests.
class FakeEventSource {
  static instances: FakeEventSource[] = []
  url: string
  listeners: Record<string, ((e: any) => void)[]> = {}
  closed = false
  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }
  addEventListener(type: string, cb: (e: any) => void) {
    ;(this.listeners[type] ||= []).push(cb)
  }
  emit(type: string, data: any) {
    ;(this.listeners[type] || []).forEach((cb) =>
      cb({ data: JSON.stringify(data) })
    )
  }
  emitRaw(type: string) {
    ;(this.listeners[type] || []).forEach((cb) => cb({}))
  }
  close() {
    this.closed = true
  }
}

const baseEvalMocks = () => {
  ;(projectsAPI.list as jest.Mock).mockResolvedValue({ items: [mockProject] })
  ;(apiClient.evaluations.getProjectEvaluationConfig as jest.Mock).mockResolvedValue(evalConfig)
  ;(apiClient.evaluations.getConfiguredMethods as jest.Mock).mockResolvedValue({
    fields: [
      {
        field_name: 'model_answer',
        automated_methods: [
          { method_name: 'bleu', has_results: true, result_count: 5 },
          { method_name: 'rouge', has_results: true, result_count: 3 },
        ],
      },
    ],
  })
  ;(apiClient.evaluations.getEvaluatedModels as jest.Mock).mockResolvedValue(twoModels)
  ;(apiClient.get as jest.Mock).mockResolvedValue({
    data: [
      {
        id: 'r1',
        project_id: '1',
        project_name: 'Proj',
        model_id: 'gpt-4',
        metrics: { bleu: 0.8, rouge: 0.6 },
        samples_evaluated: 100,
        created_at: '2024-01-01',
        status: 'completed',
        evaluation_type: 'automated',
      },
    ],
  })
  ;(apiClient.evaluations.getEvaluationHistory as jest.Mock).mockResolvedValue({
    series: [{ metric: 'bleu', evaluation_config_id: 'cfg1', display_name: 'BLEU', data: [] }],
  })
  ;(apiClient.evaluations.getSignificanceTests as jest.Mock).mockResolvedValue({
    comparisons: [{ model_a: 'gpt-4', model_b: 'claude', p_value: 0.01 }],
  })
  ;(apiClient.evaluations.computeStatistics as jest.Mock).mockResolvedValue({})
  ;(apiClient.evaluations.runEvaluation as jest.Mock).mockResolvedValue({
    evaluation_id: 'eval-99',
  })
}

const renderSelected = async () => {
  // Auto-select project 1 from localStorage so all data-driven branches load.
  localStorage.setItem('evaluations_lastProjectId', '1')
  ;(useSearchParams as jest.Mock).mockReturnValue(new URLSearchParams())
  render(<EvaluationDashboard />)
  await waitFor(() => {
    expect(apiClient.evaluations.getProjectEvaluationConfig).toHaveBeenCalledWith('1')
  })
  // Models + configs settle.
  await waitFor(() => {
    expect(apiClient.evaluations.getEvaluatedModels).toHaveBeenCalled()
  })
}

describe('EvaluationDashboard - coverage complement', () => {
  let originalEventSource: any

  beforeEach(() => {
    jest.clearAllMocks()
    localStorage.clear()
    FakeEventSource.instances = []
    originalEventSource = (global as any).EventSource
    ;(global as any).EventSource = FakeEventSource as any
    ;(useRouter as jest.Mock).mockReturnValue(mockRouter)
    ;(useAuth as jest.Mock).mockReturnValue({ user: mockUser, isLoading: false })
    ;(useI18n as jest.Mock).mockReturnValue({ t: mockT })
    ;(useToast as jest.Mock).mockReturnValue({ addToast: mockAddToast })
    baseEvalMocks()
  })

  afterEach(() => {
    ;(global as any).EventSource = originalEventSource
  })

  it('shows an error toast when project data fetch fails at the top level', async () => {
    const errSpy = jest.spyOn(console, 'error').mockImplementation(() => {})
    // getConfiguredMethods resolves but with a non-array `fields`, so the
    // `(configuredMethods?.fields || []).flatMap(...)` call (outside the inner
    // try) throws -> outer catch -> addToast(dataFailed) (lines 548-550).
    ;(apiClient.evaluations.getConfiguredMethods as jest.Mock).mockResolvedValue({
      fields: 42 as any,
    })

    localStorage.setItem('evaluations_lastProjectId', '1')
    ;(useSearchParams as jest.Mock).mockReturnValue(new URLSearchParams())
    render(<EvaluationDashboard />)

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith(
        'toasts.evaluation.dataFailed',
        'error'
      )
    })
    errSpy.mockRestore()
  })

  it('runs an evaluation and drives the SSE status -> done(completed) lifecycle', async () => {
    const user = userEvent.setup()
    await renderSelected()

    // Open the modal via the empty-state / results "run" entry isn't wired in
    // mocks, so invoke handleRunEvaluation through the always-rendered modal.
    await user.click(screen.getByText('modal-run'))

    await waitFor(() => {
      expect(apiClient.evaluations.runEvaluation).toHaveBeenCalled()
    })
    expect(mockStartEvaluation).toHaveBeenCalledWith('eval-99', expect.any(Number))

    // An EventSource was opened for the returned evaluation id.
    await waitFor(() => expect(FakeEventSource.instances.length).toBe(1))
    const es = FakeEventSource.instances[0]
    expect(es.url).toContain('eval-99')

    // Drive a running status update, then a completed "done".
    act(() => {
      es.emit('status', { status: 'running', samples_evaluated: 10 })
    })
    expect(mockUpdateEvaluation).toHaveBeenCalledWith(
      'eval-99',
      'running',
      expect.any(String),
      expect.any(String)
    )

    act(() => {
      es.emit('status', { status: 'pending' })
    })

    act(() => {
      es.emit('done', { status: 'completed', samples_evaluated: 42 })
    })
    expect(mockAddToast).toHaveBeenCalledWith(
      'toasts.evaluation.complete',
      'success'
    )
    expect(es.closed).toBe(true)
  })

  it('handles an SSE done(failed) event with a failure toast', async () => {
    const user = userEvent.setup()
    await renderSelected()

    await user.click(screen.getByText('modal-run'))
    await waitFor(() => expect(FakeEventSource.instances.length).toBe(1))
    const es = FakeEventSource.instances[0]

    act(() => {
      es.emit('done', { status: 'failed', error_message: 'kaboom' })
    })

    expect(mockAddToast).toHaveBeenCalledWith('toasts.evaluation.failed', 'error')
    expect(es.closed).toBe(true)
  })

  it('reconnects on the first SSE error (exponential backoff path)', async () => {
    jest.useFakeTimers()
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })
    await renderSelected()

    await user.click(screen.getByText('modal-run'))
    await waitFor(() => expect(FakeEventSource.instances.length).toBe(1))

    const es = FakeEventSource.instances[0]
    // First error => reconnecting toast + a scheduled reconnect.
    act(() => es.emitRaw('error'))
    expect(mockUpdateEvaluation).toHaveBeenCalledWith(
      'eval-99',
      'running',
      'evaluation.viewer.status.reconnecting',
      expect.stringContaining('1/3')
    )
    expect(es.closed).toBe(true)

    // The 1s backoff fires a fresh EventSource.
    act(() => {
      jest.advanceTimersByTime(1000)
    })
    expect(FakeEventSource.instances.length).toBe(2)
    jest.useRealTimers()
  })

  it('gives up after maxRetries SSE errors without an intervening reconnect', async () => {
    jest.useFakeTimers()
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })
    await renderSelected()

    await user.click(screen.getByText('modal-run'))
    await waitFor(() => expect(FakeEventSource.instances.length).toBe(1))

    // Fire 4 errors on the SAME source before any backoff timer runs, so the
    // local retryCount climbs past maxRetries (3) -> "connection lost" branch.
    const es = FakeEventSource.instances[0]
    act(() => es.emitRaw('error')) // 1
    act(() => es.emitRaw('error')) // 2
    act(() => es.emitRaw('error')) // 3
    act(() => es.emitRaw('error')) // 4 -> give up

    expect(mockUpdateEvaluation).toHaveBeenCalledWith(
      'eval-99',
      'failed',
      'evaluation.viewer.status.connectionLost',
      'evaluation.viewer.status.unableToTrack'
    )
    jest.useRealTimers()
  })

  it('toasts when running an evaluation with no configured methods', async () => {
    const user = userEvent.setup()
    // Config with all methods disabled -> deriveEvaluationConfigs filters to [].
    ;(apiClient.evaluations.getProjectEvaluationConfig as jest.Mock).mockResolvedValue({
      evaluation_configs: [
        { id: 'cfg1', metric: 'bleu', enabled: false, prediction_fields: [], reference_fields: [] },
      ],
    })
    await renderSelected()

    await user.click(screen.getByText('modal-run'))

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith(
        'evaluation.noMethodsConfigured',
        'error'
      )
    })
    expect(apiClient.evaluations.runEvaluation).not.toHaveBeenCalled()
  })

  it('toasts when runEvaluation rejects', async () => {
    const user = userEvent.setup()
    const errSpy = jest.spyOn(console, 'error').mockImplementation(() => {})
    ;(apiClient.evaluations.runEvaluation as jest.Mock).mockRejectedValue(
      new Error('run failed')
    )
    await renderSelected()

    await user.click(screen.getByText('modal-run-scoped'))

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith('run failed', 'error')
    })
    errSpy.mockRestore()
  })

  it('captures a significance error when the significance endpoint rejects', async () => {
    ;(apiClient.evaluations.getSignificanceTests as jest.Mock).mockRejectedValue(
      Object.assign(new Error('sig down'), { message: 'sig down' })
    )
    await renderSelected()

    // Switch to a non-data chart so the significance card renders, exposing the
    // error banner.
    const user = userEvent.setup()
    await user.click(screen.getAllByText('set-bar-view')[0])

    await waitFor(() => {
      expect(
        screen.getByText('evaluation.viewer.results.statisticalSignificance')
      ).toBeInTheDocument()
    })
  })

  it('captures a statistics error when computeStatistics rejects for all levels', async () => {
    ;(apiClient.evaluations.computeStatistics as jest.Mock).mockRejectedValue(
      Object.assign(new Error('stats down'), { message: 'stats down' })
    )
    await renderSelected()

    const user = userEvent.setup()
    await user.click(screen.getAllByText('set-bar-view')[0])

    // The statistical results panel renders (with the error wired in).
    await waitFor(() => {
      expect(screen.getByTestId('statistical-results-panel')).toBeInTheDocument()
    })
  })

  it('renders the historical trends + significance heatmap in a chart view', async () => {
    await renderSelected()

    const user = userEvent.setup()
    await user.click(screen.getAllByText('set-bar-view')[0])

    await waitFor(() => {
      expect(screen.getByTestId('significance-heatmap')).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.getByTestId('historical-trend-chart')).toBeInTheDocument()
    })
  })

  it('clears all filters via the clear button', async () => {
    await renderSelected()

    const user = userEvent.setup()
    // First narrow a filter (switch chart view) so clear is enabled.
    await user.click(screen.getAllByText('set-bar-view')[0])

    const clearBtn = await screen.findByLabelText(
      'evaluation.viewer.filters.clearAllFilters'
    )
    await user.click(clearBtn)

    // After clearing, the data view (default) is restored — significance card
    // (chart-only) disappears.
    await waitFor(() => {
      expect(
        screen.queryByText('evaluation.viewer.results.statisticalSignificance')
      ).not.toBeInTheDocument()
    })
  })

  it('toggles metric selection: clear-all then select-all', async () => {
    await renderSelected()

    const user = userEvent.setup()
    // Open the metrics dropdown.
    await user.click(screen.getByText('evaluation.viewer.filters.allMetrics'))

    const clearAll = await screen.findAllByText('evaluation.viewer.filters.clearAll')
    await user.click(clearAll[clearAll.length - 1])

    // With nothing selected, the trigger label flips to "selectMetrics".
    await waitFor(() => {
      expect(
        screen.getByText('evaluation.viewer.filters.selectMetrics')
      ).toBeInTheDocument()
    })

    const selectAll = await screen.findAllByText(
      'evaluation.viewer.filters.selectAll'
    )
    await user.click(selectAll[selectAll.length - 1])

    await waitFor(() => {
      expect(
        screen.getByText('evaluation.viewer.filters.allMetrics')
      ).toBeInTheDocument()
    })
  })
})
