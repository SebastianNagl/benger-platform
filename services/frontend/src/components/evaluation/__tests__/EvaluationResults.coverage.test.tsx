/**
 * Complement coverage for EvaluationResults.
 *
 * The base suites (EvaluationResults.test.tsx + .modal + .metricSelector)
 * cover loading/error/empty, the chart + data tables, filtering, polling,
 * inline statistics, the result-details modal tabs, and score formatting.
 *
 * This file targets the still-uncovered branches:
 *  - localStorage restore of the saved evaluation_config selection.
 *  - metric-selector onValueChange → persists config id to localStorage.
 *  - the By-Run chart toggle + the per_run_means_by_model_metric onDataLoaded
 *    path (3-part composite keys → one chart entry per judge run, plus the
 *    no-per-run fall-back to a single bar).
 *  - the results_by_config chart fall-back when taskModelData has no summary.
 *  - the Export dropdown: open/close + JSON and CSV download (anchor click,
 *    Blob/URL plumbing).
 *  - formatRunsAggregate: the "± std (N runs)" multi-run summary line.
 *  - handleCellReEvaluate: the re-evaluate button in the result modal calls
 *    apiClient.evaluations.runEvaluation and toasts success / failure.
 *
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { EvaluationResults } from '../EvaluationResults'

// ---- shared mocks ----

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
        <button onClick={onClose} data-testid="close-task-modal">Close</button>
      </div>
    ) : null,
}))

jest.mock('@/components/evaluation/InflightRunsBanner', () => ({
  InflightRunsBanner: () => null,
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

// ---- API mocks ----
const mockGetProjectEvaluationResults = jest.fn()
const mockGetProjectResultsByTaskModel = jest.fn()
const mockGetTaskEvaluation = jest.fn()
const mockApiClientGet = jest.fn()
const mockRunEvaluation = jest.fn()

// canStartGeneration is toggled per-test so the re-evaluate button (gated
// on it) can be exercised. A mutable holder keeps the jest.mock factory
// referencing a mock-prefixed outer var (stable identity).
const mockPerm = { canStart: false }
jest.mock('@/utils/permissions', () => ({
  canStartGeneration: () => mockPerm.canStart,
}))

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'u1' } }),
}))

jest.mock('@/lib/api/client', () => ({
  apiClient: {
    getProjectEvaluationResults: (...a: any[]) => mockGetProjectEvaluationResults(...a),
    getProjectResultsByTaskModel: (...a: any[]) => mockGetProjectResultsByTaskModel(...a),
    getTaskEvaluation: (...a: any[]) => mockGetTaskEvaluation(...a),
    get: (...a: any[]) => mockApiClientGet(...a),
    evaluations: {
      computeStatistics: jest.fn(),
      runEvaluation: (...a: any[]) => mockRunEvaluation(...a),
    },
  },
}))

const mockGetTask = jest.fn()
const mockGetTaskAnnotations = jest.fn()
jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    getTask: (...a: any[]) => mockGetTask(...a),
    getTaskAnnotations: (...a: any[]) => mockGetTaskAnnotations(...a),
  },
}))

// ---- data factories ----

function makeEvaluation(overrides: Partial<any> = {}) {
  return {
    evaluation_id: 'eval-001',
    model_id: 'gpt-4',
    status: 'completed',
    created_at: new Date(Date.now() - 3600000).toISOString(),
    completed_at: new Date(Date.now() - 1800000).toISOString(),
    samples_evaluated: 10,
    sample_results_count: 10,
    error_message: null,
    evaluation_configs: [
      {
        id: 'cfg-1',
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
      'cfg-1': {
        field_results: [
          { combo_key: 'a_vs_b', prediction_field: 'answer', reference_field: 'gold_answer', scores: { exact_match: 0.85 } },
        ],
        aggregate_score: 0.85,
      },
    },
    progress: { samples_passed: 8, samples_failed: 2, samples_skipped: 0 },
    ...overrides,
  }
}

function makeProjectResults(evals: any[] = [makeEvaluation()]) {
  return { project_id: 'p1', evaluations: evals, total_count: evals.length }
}

function makeTaskModelData(overrides: Partial<any> = {}) {
  return {
    evaluation_id: 'eval-001',
    models: ['gpt-4', 'claude-3'],
    model_names: { 'gpt-4': 'GPT-4', 'claude-3': 'Claude 3' },
    tasks: [
      {
        task_id: 'task-111',
        task_preview: 'Question one',
        scores: { 'gpt-4': 0.85, 'claude-3': 0.72 },
        has_annotation: true,
        generation_models: ['gpt-4', 'claude-3'],
      },
    ],
    summary: {
      'gpt-4': { avg: 0.85, count: 1, model_name: 'GPT-4' },
      'claude-3': { avg: 0.72, count: 1, model_name: 'Claude 3' },
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

const DATA_VIEW_PROPS = {
  viewType: 'data' as const,
  selectedConfigIds: ['cfg-1'],
}

function setup(taskModelOverrides: Partial<any> = {}) {
  mockGetProjectEvaluationResults.mockResolvedValue(makeProjectResults())
  mockGetProjectResultsByTaskModel.mockResolvedValue(makeTaskModelData(taskModelOverrides))
  mockGetTask.mockResolvedValue({ id: 'task-111', data: {} })
  mockGetTaskAnnotations.mockResolvedValue([])
  mockApiClientGet.mockResolvedValue({ results: [] })
  mockGetTaskEvaluation.mockResolvedValue({ results: [] })
  mockRunEvaluation.mockResolvedValue({})
}

async function renderDataView(extraProps: Record<string, any> = {}) {
  render(<EvaluationResults projectId="p1" {...DATA_VIEW_PROPS} {...extraProps} />)
  await waitFor(() => expect(mockGetProjectEvaluationResults).toHaveBeenCalled())
  await waitFor(() => {
    expect(
      screen.queryAllByTitle('evaluation.multiFieldResults.clickToViewResponse').length
    ).toBeGreaterThan(0)
  })
  await act(async () => { await new Promise((r) => setTimeout(r, 30)) })
}

beforeEach(() => {
  jest.clearAllMocks()
  mockPerm.canStart = false
  localStorage.clear()
})

// ====================================================================
// localStorage round-trip of the selected metric config
// ====================================================================

describe('selected-config localStorage round-trip', () => {
  it('restores the saved evaluation_config id from localStorage', async () => {
    // Two configs exist; localStorage points at the second one.
    const e1 = makeEvaluation()
    const e2 = makeEvaluation({
      evaluation_id: 'eval-002',
      evaluation_configs: [
        {
          id: 'cfg-2',
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
        'cfg-2': { field_results: [], aggregate_score: 0.7 },
      },
    })
    mockGetProjectEvaluationResults.mockResolvedValue(makeProjectResults([e1, e2]))
    mockGetProjectResultsByTaskModel.mockResolvedValue(makeTaskModelData())
    localStorage.setItem('eval-selected-config-p1', 'cfg-2')

    render(<EvaluationResults projectId="p1" />)

    // The metric selector should restore to the F1 Score config.
    await waitFor(() => {
      const select = document.querySelector('select') as HTMLSelectElement
      expect(select).toBeTruthy()
      expect(select.value).toBe('cfg-2')
    })
  })

  it('persists the picked config id to localStorage when the selector changes', async () => {
    const e1 = makeEvaluation()
    const e2 = makeEvaluation({
      evaluation_id: 'eval-002',
      evaluation_configs: [
        {
          id: 'cfg-2',
          metric: 'f1_score',
          display_name: 'F1 Score',
          metric_type: 'automated',
          metric_parameters: {},
          prediction_fields: ['answer'],
          reference_fields: ['gold_answer'],
          enabled: true,
        },
      ],
      results_by_config: { 'cfg-2': { field_results: [], aggregate_score: 0.7 } },
    })
    mockGetProjectEvaluationResults.mockResolvedValue(makeProjectResults([e1, e2]))
    mockGetProjectResultsByTaskModel.mockResolvedValue(makeTaskModelData())

    render(<EvaluationResults projectId="p1" />)

    const select = await waitFor(() => {
      const s = document.querySelector('select') as HTMLSelectElement
      expect(s).toBeTruthy()
      return s
    })

    await act(async () => { fireEvent.change(select, { target: { value: 'cfg-2' } }) })

    await waitFor(() =>
      expect(localStorage.getItem('eval-selected-config-p1')).toBe('cfg-2')
    )
  })
})

// ====================================================================
// Export dropdown — open/close + JSON + CSV download
// ====================================================================

describe('Export dropdown', () => {
  function findExportButton(): HTMLElement {
    // The export trigger is the outline Button containing the export label.
    const btn = screen
      .getAllByRole('button')
      .find((b) => b.textContent?.includes('common.export') || b.textContent === 'Export')
    if (!btn) throw new Error('export button not found')
    return btn
  }

  it('opens the dropdown and downloads JSON then CSV', async () => {
    setup()
    // Spy the anchor click + URL plumbing so the jsdom Blob download doesn't
    // navigate, and so we can assert the chosen filename/extension.
    const createObjectURL = jest.fn(() => 'blob:mock')
    const revokeObjectURL = jest.fn()
    ;(URL as any).createObjectURL = createObjectURL
    ;(URL as any).revokeObjectURL = revokeObjectURL
    const clickSpy = jest
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => {})

    await renderDataView()

    // Open the dropdown.
    await act(async () => { fireEvent.click(findExportButton()) })
    expect(screen.getByText('JSON')).toBeInTheDocument()
    expect(screen.getByText('CSV')).toBeInTheDocument()

    // JSON download.
    await act(async () => { fireEvent.click(screen.getByText('JSON')) })
    expect(createObjectURL).toHaveBeenCalledTimes(1)
    expect(clickSpy).toHaveBeenCalledTimes(1)
    expect(revokeObjectURL).toHaveBeenCalledTimes(1)

    // Dropdown closed after a download; re-open for CSV.
    await waitFor(() => expect(screen.queryByText('JSON')).not.toBeInTheDocument())
    await act(async () => { fireEvent.click(findExportButton()) })
    await act(async () => { fireEvent.click(screen.getByText('CSV')) })
    expect(createObjectURL).toHaveBeenCalledTimes(2)
    expect(clickSpy).toHaveBeenCalledTimes(2)

    clickSpy.mockRestore()
  })

  it('closes the dropdown on outside click', async () => {
    setup()
    await renderDataView()

    await act(async () => { fireEvent.click(findExportButton()) })
    expect(screen.getByText('JSON')).toBeInTheDocument()

    // mousedown outside the dropdown ref closes it.
    await act(async () => {
      fireEvent.mouseDown(document.body)
    })
    await waitFor(() => expect(screen.queryByText('JSON')).not.toBeInTheDocument())
  })
})

// ====================================================================
// By-Run chart toggle + per_run_means_by_model_metric onDataLoaded path
// ====================================================================

describe('By-run chart toggle', () => {
  const statisticsWithPerRun = {
    by_model: {
      'gpt-4': {
        model_name: 'GPT-4',
        metrics: { exact_match: { mean: 0.85, std: 0.04, se: 0.01, ci_lower: 0.8, ci_upper: 0.9, n: 10 } },
        sample_count: 10,
      },
    },
    // 3-part composite key: model_id|config_id|metric
    per_run_means_by_model_metric: {
      'gpt-4|cfg-1|exact_match': [
        { judge_run_id: 'r1', judge_model_id: 'gpt-4o', run_index: 1, mean: 0.8, n_tasks: 10 },
        { judge_run_id: 'r2', judge_model_id: 'gpt-4o', run_index: 2, mean: 0.9, n_tasks: 10 },
      ],
    },
  }

  it('shows the by-run toggle only when per-run data is present', async () => {
    setup()
    // No per-run data → toggle hidden.
    const { rerender } = render(
      <EvaluationResults projectId="p1" {...DATA_VIEW_PROPS} />
    )
    await waitFor(() => expect(mockGetProjectEvaluationResults).toHaveBeenCalled())
    expect(
      screen.queryByText('Diagramm pro Lauf splitten')
    ).not.toBeInTheDocument()

    // With per-run data → toggle visible.
    rerender(
      <EvaluationResults
        projectId="p1"
        {...DATA_VIEW_PROPS}
        statisticsData={statisticsWithPerRun as any}
      />
    )
    await waitFor(() =>
      expect(screen.getByText('Diagramm pro Lauf splitten')).toBeInTheDocument()
    )
  })

  it('emits one chart entry per judge run when by-run is toggled on', async () => {
    setup()
    const onDataLoaded = jest.fn()

    render(
      <EvaluationResults
        projectId="p1"
        {...DATA_VIEW_PROPS}
        statisticsData={statisticsWithPerRun as any}
        onDataLoaded={onDataLoaded}
      />
    )

    await waitFor(() =>
      expect(screen.getByText('Diagramm pro Lauf splitten')).toBeInTheDocument()
    )

    // Toggle the by-run checkbox on.
    const toggle = screen
      .getByText('Diagramm pro Lauf splitten')
      .closest('label')!
      .querySelector('input[type="checkbox"]') as HTMLInputElement
    await act(async () => { fireEvent.click(toggle) })

    // onDataLoaded should now receive one entry per run (run 1 and run 2).
    await waitFor(() => {
      const lastCall = onDataLoaded.mock.calls[onDataLoaded.mock.calls.length - 1]?.[0]
      expect(Array.isArray(lastCall)).toBe(true)
      const runEntries = (lastCall as any[]).filter((d) =>
        String(d.model_id).includes('__r')
      )
      expect(runEntries.length).toBe(2)
    })
  })

  it('falls back to a single bar for a model with no per-run entries', async () => {
    setup()
    const onDataLoaded = jest.fn()
    // per-run block has data for gpt-4 only; claude-3 has none → single bar.
    render(
      <EvaluationResults
        projectId="p1"
        {...DATA_VIEW_PROPS}
        statisticsData={statisticsWithPerRun as any}
        onDataLoaded={onDataLoaded}
      />
    )
    await waitFor(() =>
      expect(screen.getByText('Diagramm pro Lauf splitten')).toBeInTheDocument()
    )
    const toggle = screen
      .getByText('Diagramm pro Lauf splitten')
      .closest('label')!
      .querySelector('input[type="checkbox"]') as HTMLInputElement
    await act(async () => { fireEvent.click(toggle) })

    await waitFor(() => {
      const lastCall = onDataLoaded.mock.calls[onDataLoaded.mock.calls.length - 1]?.[0]
      // claude-3 carries no per-run entry → appears as a plain single bar.
      const single = (lastCall as any[]).find((d) => d.model_id === 'claude-3')
      expect(single).toBeTruthy()
    })
  })
})

// ====================================================================
// onDataLoaded fall-back: results_by_config when summary is empty
// ====================================================================

describe('onDataLoaded fall-back from results_by_config', () => {
  it('extracts chart data from results_by_config when taskModelData has no summary', async () => {
    mockGetProjectEvaluationResults.mockResolvedValue(makeProjectResults())
    // taskModelData has an empty summary → the component falls back to
    // extracting per-config aggregate scores from the latest evaluation.
    mockGetProjectResultsByTaskModel.mockResolvedValue(emptyTaskModelData)
    const onDataLoaded = jest.fn()

    render(<EvaluationResults projectId="p1" onDataLoaded={onDataLoaded} />)

    await waitFor(() => expect(onDataLoaded).toHaveBeenCalled())
    const chartData = onDataLoaded.mock.calls[onDataLoaded.mock.calls.length - 1][0]
    expect(chartData).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          model_id: 'gpt-4',
          metrics: expect.objectContaining({ exact_match: 0.85 }),
        }),
      ])
    )
  })

  it('labels the fall-back entry "All Models" when model_id is unknown', async () => {
    mockGetProjectEvaluationResults.mockResolvedValue(
      makeProjectResults([makeEvaluation({ model_id: 'unknown' })])
    )
    mockGetProjectResultsByTaskModel.mockResolvedValue(emptyTaskModelData)
    const onDataLoaded = jest.fn()

    render(<EvaluationResults projectId="p1" onDataLoaded={onDataLoaded} />)

    await waitFor(() => expect(onDataLoaded).toHaveBeenCalled())
    const chartData = onDataLoaded.mock.calls[onDataLoaded.mock.calls.length - 1][0]
    expect(chartData).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ model_id: 'All Models' }),
      ])
    )
  })
})

// ====================================================================
// formatRunsAggregate — multi-run "± std (N runs)" summary line
// ====================================================================

describe('formatRunsAggregate summary line', () => {
  it('renders "± std (N runs)" on the average row when ≥2 runs exist', async () => {
    setup()
    const statisticsData = {
      by_model: {
        'gpt-4': {
          model_name: 'GPT-4',
          metrics: { exact_match: { mean: 0.85, std: 0.04, se: 0.01, ci_lower: 0.8, ci_upper: 0.9, n: 10 } },
          sample_count: 10,
        },
      },
      runs_by_model_metric: {
        'gpt-4|cfg-1|exact_match': { n_runs: 3, std_of_means: 0.021 },
      },
    }

    render(
      <EvaluationResults
        projectId="p1"
        {...DATA_VIEW_PROPS}
        selectedConfigIds={['cfg-1']}
        statisticsData={statisticsData as any}
      />
    )

    await waitFor(() => {
      expect(screen.getByText(/± 0\.021 \(3 runs\)/)).toBeInTheDocument()
    })
  })

  it('omits the "(N runs)" line when only one run exists', async () => {
    setup()
    const statisticsData = {
      by_model: {
        'gpt-4': {
          model_name: 'GPT-4',
          metrics: { exact_match: { mean: 0.85, std: 0.04, se: 0.01, ci_lower: 0.8, ci_upper: 0.9, n: 10 } },
          sample_count: 10,
        },
      },
      runs_by_model_metric: {
        'gpt-4|cfg-1|exact_match': { n_runs: 1, std_of_means: 0.0 },
      },
    }

    render(
      <EvaluationResults
        projectId="p1"
        {...DATA_VIEW_PROPS}
        selectedConfigIds={['cfg-1']}
        statisticsData={statisticsData as any}
      />
    )

    await waitFor(() => expect(screen.getByText('evaluation.multiFieldResults.average')).toBeInTheDocument())
    expect(screen.queryByText(/runs\)/)).not.toBeInTheDocument()
  })

  it('uses the highest-n_runs entry when multiple configs match via prefix', async () => {
    setup()
    const statisticsData = {
      by_model: {
        'gpt-4': {
          model_name: 'GPT-4',
          metrics: { exact_match: { mean: 0.85, std: 0.04, se: 0.01, ci_lower: 0.8, ci_upper: 0.9, n: 10 } },
          sample_count: 10,
        },
      },
      runs_by_model_metric: {
        'gpt-4|cfg-a|exact_match': { n_runs: 2, std_of_means: 0.01 },
        'gpt-4|cfg-b|exact_match': { n_runs: 5, std_of_means: 0.03 },
      },
    }

    // Multiple selectedConfigIds → no exact-key lookup, prefix scan picks
    // the entry with the highest n_runs (5).
    render(
      <EvaluationResults
        projectId="p1"
        {...DATA_VIEW_PROPS}
        selectedConfigIds={['cfg-a', 'cfg-b']}
        statisticsData={statisticsData as any}
      />
    )

    await waitFor(() => {
      expect(screen.getByText(/± 0\.030 \(5 runs\)/)).toBeInTheDocument()
    })
  })
})

// ====================================================================
// handleCellReEvaluate — re-evaluate button in the result modal
// ====================================================================

describe('Cell re-evaluation', () => {
  const evaluationConfigs = [
    {
      id: 'cfg-1',
      metric: 'exact_match',
      display_name: 'Exact Match',
      metric_parameters: {},
      prediction_fields: ['answer'],
      reference_fields: ['gold_answer'],
      enabled: true,
    },
  ]

  async function openModalAndReEvaluate() {
    const scoreCells = screen.queryAllByTitle('evaluation.multiFieldResults.clickToViewResponse')
    await act(async () => { fireEvent.click(scoreCells[0]) })
    await waitFor(() => expect(screen.getByTestId('dialog')).toBeInTheDocument())
    // The re-evaluate button carries the reEvaluate label.
    const reBtn = await waitFor(() => {
      const b = screen.getByText('evaluation.multiFieldResults.reEvaluate').closest('button')
      expect(b).toBeTruthy()
      return b as HTMLButtonElement
    })
    await act(async () => { fireEvent.click(reBtn) })
  }

  it('dispatches runEvaluation and toasts success', async () => {
    mockPerm.canStart = true
    setup()
    await renderDataView({ evaluationConfigs })

    await openModalAndReEvaluate()

    await waitFor(() =>
      expect(mockRunEvaluation).toHaveBeenCalledWith(
        expect.objectContaining({
          project_id: 'p1',
          force_rerun: true,
          task_ids: ['task-111'],
          model_ids: ['gpt-4'],
          evaluation_configs: expect.arrayContaining([
            expect.objectContaining({ id: 'cfg-1' }),
          ]),
        })
      )
    )
    expect(mockAddToast).toHaveBeenCalledWith(
      'evaluation.multiFieldResults.reEvaluateQueued',
      'success'
    )
  })

  it('toasts an error when runEvaluation rejects', async () => {
    mockPerm.canStart = true
    setup()
    mockRunEvaluation.mockRejectedValue(new Error('Queue is full'))
    await renderDataView({ evaluationConfigs })

    await openModalAndReEvaluate()

    await waitFor(() =>
      expect(mockAddToast).toHaveBeenCalledWith('Queue is full', 'error')
    )
  })

  it('does not render the re-evaluate button without permission', async () => {
    mockPerm.canStart = false
    setup()
    await renderDataView({ evaluationConfigs })

    const scoreCells = screen.queryAllByTitle('evaluation.multiFieldResults.clickToViewResponse')
    await act(async () => { fireEvent.click(scoreCells[0]) })
    await waitFor(() => expect(screen.getByTestId('dialog')).toBeInTheDocument())

    expect(
      screen.queryByText('evaluation.multiFieldResults.reEvaluate')
    ).not.toBeInTheDocument()
  })
})
