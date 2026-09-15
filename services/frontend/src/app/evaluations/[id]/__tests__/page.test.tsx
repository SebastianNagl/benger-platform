/**
 * Tests for the Individual Evaluation Dashboard Page
 * (`app/evaluations/[id]/page.tsx`, issue #763).
 *
 * Behavioral coverage of the real derivation logic that lived untested:
 *  - `_bareMetric` composite-key parsing (`config|pred|ref|metric`, legacy
 *    `:`-delimited, and plain forms) feeding the bare→composite map.
 *  - `perRunRows` derivation from `eval_metadata.judges_by_config`.
 *  - `judgeAgreementForFirstMetric` including the empty-cohens-dict
 *    truthiness branch (must fall through to pearson, not lock onto {}).
 *  - tab switching (overview / samples / confusion / distributions / judges),
 *    incl. lazy multi-run stats load on the judges/samples tabs.
 *  - `consistencyByTaskId` flattening of task_consistency_by_model_metric.
 *  - metric-distribution load on mount + on metric change.
 *  - loading / not-found / refresh / error-toast paths.
 *
 * Mirrors the `use(params)` + apiClient mock idiom from
 * `app/evaluations/__tests__/page.test.tsx`.
 */

import '@testing-library/jest-dom'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(),
}))

jest.mock('@/components/shared/Toast', () => ({
  useToast: jest.fn(),
}))

// Named-export apiClient from @/lib/api/client (NOT the default @/lib/api).
jest.mock('@/lib/api/client', () => ({
  apiClient: {
    get: jest.fn(),
    post: jest.fn(),
    evaluations: {
      getResults: jest.fn(),
      getSamples: jest.fn(),
      getConfusionMatrix: jest.fn(),
    },
  },
}))

jest.mock('@/lib/api/projects', () => ({
  projectsAPI: { get: jest.fn() },
}))

jest.mock('@/lib/utils/logger', () => ({
  logger: {
    debug: jest.fn(),
    error: jest.fn(),
    warn: jest.fn(),
    info: jest.fn(),
  },
}))

// Child visualization components — render their props as testable DOM so
// derived values (perRunRows, consistency map, heatmap inputs, etc.) can be
// asserted directly.
jest.mock('@/components/evaluation/ConfusionMatrixChart', () => ({
  ConfusionMatrixChart: ({ data }: any) => (
    <div data-testid="confusion-matrix-chart">{JSON.stringify(data)}</div>
  ),
}))

jest.mock('@/components/evaluation/JudgeAgreementHeatmap', () => ({
  JudgeAgreementHeatmap: ({
    judgeModelIds,
    metric,
    scoreType,
    pairwise,
    fleissKappa,
  }: any) => (
    <div
      data-testid="judge-agreement-heatmap"
      data-judges={(judgeModelIds || []).join(',')}
      data-metric={metric}
      data-score-type={scoreType}
      data-fleiss={String(fleissKappa)}
      data-pairwise={JSON.stringify(pairwise)}
    />
  ),
}))

jest.mock('@/components/evaluation/MetricDistributionChart', () => ({
  MetricDistributionChart: ({ data }: any) => (
    <div data-testid="metric-distribution-chart">{JSON.stringify(data)}</div>
  ),
}))

jest.mock('@/components/evaluation/PerRunBreakdown', () => ({
  PerRunBreakdown: ({ rows, metric }: any) => (
    <div
      data-testid="per-run-breakdown"
      data-metric={metric}
      data-row-count={rows.length}
    >
      {rows.map((r: any, i: number) => (
        <div
          key={i}
          data-testid="per-run-row"
          data-metric={r.metric}
          data-metric-label={r.metric_label}
        >
          {r.target_model_id}|{r.judge_model_id}|{r.run_index}|{r.status}|
          {String(r.samples_evaluated)}|{String(r.mean_score)}
        </div>
      ))}
    </div>
  ),
}))

jest.mock('@/components/evaluation/SampleResultsTable', () => ({
  SampleResultsTable: ({ data, consistencyByTaskId, configs }: any) => (
    <div
      data-testid="sample-results-table"
      data-sample-count={data.length}
      data-consistency={JSON.stringify(consistencyByTaskId)}
      data-configs={JSON.stringify(configs)}
    />
  ),
}))

jest.mock('@/components/shared/Badge', () => ({
  Badge: ({ children, variant }: any) => (
    <span data-testid="badge" data-variant={variant}>
      {children}
    </span>
  ),
}))

jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: ({ items }: any) => (
    <div data-testid="breadcrumb">
      {items.map((item: any, i: number) => (
        <span key={i}>{item.label}</span>
      ))}
    </div>
  ),
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, disabled, variant, className }: any) => (
    <button
      onClick={onClick}
      disabled={disabled}
      data-variant={variant}
      className={className}
    >
      {children}
    </button>
  ),
}))

jest.mock('@/components/shared/Card', () => ({
  Card: ({ children, className }: any) => (
    <div data-testid="card" className={className}>
      {children}
    </div>
  ),
}))

jest.mock('@/components/shared/LoadingSpinner', () => ({
  LoadingSpinner: () => <div data-testid="loading-spinner" />,
}))

// NOTE: @/components/shared/Select is auto-mapped to the shared
// __mocks__/Select.tsx (native <select role="combobox"> + selectOptions
// support) via jest.config.js moduleNameMapper — no inline mock needed.

jest.mock('@heroicons/react/24/outline', () => ({
  ArrowLeftIcon: () => <div data-testid="arrow-left-icon" />,
  ArrowPathIcon: () => <div data-testid="arrow-path-icon" />,
  ChartBarIcon: () => <div data-testid="chart-bar-icon" />,
  // Used by the shared Alert.
  CheckCircleIcon: () => <div data-testid="check-circle-icon" />,
  ExclamationTriangleIcon: () => <div data-testid="warning-icon" />,
  InformationCircleIcon: () => <div data-testid="info-icon" />,
  XCircleIcon: () => <div data-testid="x-circle-icon" />,
}))

import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import { apiClient } from '@/lib/api/client'
import { registerMetric } from '@/lib/api/evaluation-types'
import { projectsAPI } from '@/lib/api/projects'
import { metricDisplayLabel } from '@/lib/evaluation/runDisplay'
import { registerSlot } from '@/lib/extensions/slots'
import { useRouter } from 'next/navigation'
import EvaluationDashboard from '../page'

const mockRouter = {
  push: jest.fn(),
  back: jest.fn(),
  replace: jest.fn(),
  forward: jest.fn(),
  refresh: jest.fn(),
  prefetch: jest.fn(),
}

const mockAddToast = jest.fn()

// t() returns a string fallback (2nd arg) when present, else the key.
const mockT = (key: string, fallback?: unknown) =>
  typeof fallback === 'string' ? fallback : key

// Composite-keyed metrics map: `config|pred|ref|metric`.
const baseEvaluation = {
  id: 'eval-1',
  project_id: 'project-1',
  model_id: 'gpt-4o',
  status: 'completed',
  samples_evaluated: 10,
  has_sample_results: true,
  metrics: {
    'cfg1|answer|gt|exact_match': 0.85,
    'cfg2|answer|gt|f1_score': 0.7123,
  },
  eval_metadata: {
    samples_passed: 8,
    samples_failed: 2,
    pass_rate: 0.8,
  },
  created_at: '2026-01-01T00:00:00Z',
  evaluation_configs: [
    { id: 'cfg1', metric: 'exact_match' },
    { id: 'cfg2', metric: 'f1_score' },
  ],
}

const baseSamples = {
  items: [
    {
      id: 's1',
      task_id: 'task-1',
      field_name: 'answer',
      answer_type: 'text',
      ground_truth: {},
      prediction: {},
      metrics: {},
      passed: true,
      confidence_score: null,
      error_message: null,
      processing_time_ms: null,
    },
  ],
  total: 1,
  page: 1,
  page_size: 100,
  has_next: false,
}

function renderPage() {
  return render(
    <EvaluationDashboard params={Promise.resolve({ id: 'eval-1' })} />,
  )
}

describe('EvaluationDashboard ([id] page)', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    ;(useRouter as jest.Mock).mockReturnValue(mockRouter)
    ;(useI18n as jest.Mock).mockReturnValue({ t: mockT })
    ;(useToast as jest.Mock).mockReturnValue({ addToast: mockAddToast })

    ;(apiClient.evaluations.getResults as jest.Mock).mockResolvedValue(
      baseEvaluation,
    )
    ;(apiClient.evaluations.getSamples as jest.Mock).mockResolvedValue(
      baseSamples,
    )
    ;(apiClient.evaluations.getConfusionMatrix as jest.Mock).mockResolvedValue(
      null,
    )
    ;(apiClient.get as jest.Mock).mockResolvedValue({
      data: { buckets: [1, 2, 3] },
    })
    ;(apiClient.post as jest.Mock).mockResolvedValue({})
    ;(projectsAPI.get as jest.Mock).mockResolvedValue({
      title: 'Klausur Polizeirecht',
    })
  })

  describe('Loading and not-found', () => {
    it('shows a spinner before the evaluation resolves', () => {
      ;(apiClient.evaluations.getResults as jest.Mock).mockReturnValue(
        new Promise(() => {}),
      )
      renderPage()
      expect(screen.getByTestId('loading-spinner')).toBeInTheDocument()
    })

    it('renders the not-found state when the eval is null and navigates to /runs', async () => {
      const user = userEvent.setup()
      ;(apiClient.evaluations.getResults as jest.Mock).mockResolvedValue(null)
      renderPage()
      await waitFor(() => {
        expect(
          screen.getByText('evaluations.detail.notFound'),
        ).toBeInTheDocument()
      })
      await user.click(screen.getByText('evaluations.detail.backToRuns'))
      expect(mockRouter.push).toHaveBeenCalledWith('/runs?type=evaluation')
    })

    it('shows an error toast when the evaluation fails to load', async () => {
      ;(apiClient.evaluations.getResults as jest.Mock).mockRejectedValue(
        new Error('load failed'),
      )
      renderPage()
      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'evaluations.detail.loadFailed',
          'error',
        )
      })
    })
  })

  describe('Overview tab + composite-key parsing', () => {
    it('fetches results + samples on mount', async () => {
      renderPage()
      await waitFor(() => {
        expect(apiClient.evaluations.getResults).toHaveBeenCalledWith('eval-1')
      })
      expect(apiClient.evaluations.getSamples).toHaveBeenCalledWith('eval-1', {
        page: 1,
        page_size: 100,
      })
    })

    it('labels metrics parsed from the composite keys by their registry names', async () => {
      renderPage()
      await waitFor(() => {
        // `cfg1|answer|gt|exact_match` -> bare `exact_match` -> its name
        expect(screen.getAllByText('Exact Match').length).toBeGreaterThan(0)
      })
      // Unregistered metrics read as words, not as snake_case keys.
      expect(screen.getAllByText('F1 Score').length).toBeGreaterThan(0)
      expect(screen.queryByText('exact_match')).not.toBeInTheDocument()
      // numeric metric value formatted via toFixed(3)
      expect(screen.getByText('0.850')).toBeInTheDocument()
      expect(screen.getByText('0.712')).toBeInTheDocument()
    })

    it('renders "—" for non-numeric metric values (judge-error placeholders)', async () => {
      ;(apiClient.evaluations.getResults as jest.Mock).mockResolvedValue({
        ...baseEvaluation,
        metrics: { 'cfg1|answer|gt|exact_match': { error: 'judge failed' } },
        evaluation_configs: [{ id: 'cfg1', metric: 'exact_match' }],
      })
      renderPage()
      await waitFor(() => {
        expect(screen.getAllByText('Exact Match').length).toBeGreaterThan(0)
      })
      expect(screen.getAllByText('—').length).toBeGreaterThan(0)
    })

    it('parses legacy colon-delimited composite metric keys', async () => {
      ;(apiClient.evaluations.getResults as jest.Mock).mockResolvedValue({
        ...baseEvaluation,
        // legacy `cfg:pred:ref:metric` -> slice(3) -> `bleu`
        metrics: { 'cfg:answer:gt:bleu': 0.5 },
        evaluation_configs: [{ id: 'cfg', metric: 'bleu' }],
      })
      renderPage()
      await waitFor(() => {
        expect(
          screen.getAllByText(metricDisplayLabel('bleu')).length,
        ).toBeGreaterThan(0)
      })
      expect(screen.getByText('0.500')).toBeInTheDocument()
    })

    it('renders the scope "Scoped to" banner when scope is present', async () => {
      ;(apiClient.evaluations.getResults as jest.Mock).mockResolvedValue({
        ...baseEvaluation,
        scope: {
          task_ids: ['t1', 't2'],
          model_ids: ['m1'],
          annotators: [{ user_id: 'u1', display: 'Alice' }],
        },
      })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('Eingeschränkt auf:')).toBeInTheDocument()
      })
      // annotator display rendered in the scope summary
      expect(screen.getByText(/Alice/)).toBeInTheDocument()
    })

    it('loads the metric distribution on mount for the auto-selected first metric', async () => {
      renderPage()
      await waitFor(() => {
        expect(apiClient.get).toHaveBeenCalledWith(
          '/evaluations/eval-1/metrics/exact_match/distribution',
        )
      })
    })
  })

  describe('Refresh + header', () => {
    it('re-fetches when the refresh button is clicked', async () => {
      const user = userEvent.setup()
      renderPage()
      await waitFor(() => {
        expect(apiClient.evaluations.getResults).toHaveBeenCalledTimes(1)
      })
      // The refresh button is the only one wrapping ArrowPathIcon.
      const refreshIcon = screen.getByTestId('arrow-path-icon')
      await user.click(refreshIcon.closest('button')!)
      await waitFor(() => {
        expect(apiClient.evaluations.getResults).toHaveBeenCalledTimes(2)
      })
    })

    it('navigates back via the back button', async () => {
      const user = userEvent.setup()
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('evaluations.detail.back')).toBeInTheDocument()
      })
      await user.click(screen.getByText('evaluations.detail.back'))
      expect(mockRouter.push).toHaveBeenCalledWith('/runs?type=evaluation')
    })
  })

  describe('Samples tab + consistency flattening', () => {
    it('switches to the samples tab and flattens task_consistency into a per-task map', async () => {
      const user = userEvent.setup()
      ;(apiClient.post as jest.Mock).mockResolvedValue({
        task_consistency_by_model_metric: {
          'gpt-4o|exact_match': [
            {
              task_id: 'task-1',
              n_runs: 3,
              variance: 0.02,
              fleiss_kappa: 0.6,
              percent_agreement: 0.9,
            },
          ],
          // a non-array bucket must be skipped without crashing
          'gpt-4o|bad': null,
        },
      })
      renderPage()
      await waitFor(() => {
        expect(
          screen.getByText('evaluation.human.results.detailed'),
        ).toBeInTheDocument()
      })
      await user.click(screen.getByText('evaluation.human.results.detailed'))

      const table = await screen.findByTestId('sample-results-table')
      expect(table).toHaveAttribute('data-sample-count', '1')
      await waitFor(() => {
        const consistency = JSON.parse(
          screen
            .getByTestId('sample-results-table')
            .getAttribute('data-consistency') || '{}',
        )
        expect(consistency['task-1']).toEqual({
          n_runs: 3,
          variance: 0.02,
          fleiss_kappa: 0.6,
          percent_agreement: 0.9,
        })
      })
    })

    it('posts statistics with bare metric names derived from evaluation_configs', async () => {
      const user = userEvent.setup()
      renderPage()
      await waitFor(() => {
        expect(
          screen.getByText('evaluation.human.results.detailed'),
        ).toBeInTheDocument()
      })
      await user.click(screen.getByText('evaluation.human.results.detailed'))
      await waitFor(() => {
        expect(apiClient.post).toHaveBeenCalledWith(
          '/evaluations/projects/project-1/statistics',
          {
            metrics: ['exact_match', 'f1_score'],
            aggregation: 'model',
            methods: ['ci'],
          },
        )
      })
    })
  })

  describe('Distributions tab', () => {
    it('renders the distribution chart and reloads on metric change', async () => {
      const user = userEvent.setup()
      renderPage()
      await waitFor(() => {
        expect(
          screen.getByText('evaluation.human.results.distribution'),
        ).toBeInTheDocument()
      })
      await user.click(
        screen.getByText('evaluation.human.results.distribution'),
      )

      expect(
        await screen.findByTestId('metric-distribution-chart'),
      ).toBeInTheDocument()

      const select = screen.getByRole('combobox')
      // The shared Select mock pushes <option>s in via an effect — wait for
      // the f1_score option to mount before driving the change.
      await waitFor(() =>
        expect(within(select).getByText('F1 Score')).toBeInTheDocument(),
      )
      await user.selectOptions(select, 'f1_score')
      await waitFor(() => {
        expect(apiClient.get).toHaveBeenCalledWith(
          '/evaluations/eval-1/metrics/f1_score/distribution',
        )
      })
    })

    it('surfaces an error toast when the distribution fetch fails', async () => {
      ;(apiClient.get as jest.Mock).mockRejectedValue(new Error('dist failed'))
      renderPage()
      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'evaluation.human.preference.saveFailed',
          'error',
        )
      })
    })
  })

  describe('Confusion tab', () => {
    it('renders the confusion tab when a classification field has matrix data', async () => {
      const user = userEvent.setup()
      ;(apiClient.evaluations.getSamples as jest.Mock).mockResolvedValue({
        ...baseSamples,
        items: [
          {
            ...baseSamples.items[0],
            answer_type: 'single_choice',
            field_name: 'verdict',
          },
        ],
      })
      ;(
        apiClient.evaluations.getConfusionMatrix as jest.Mock
      ).mockResolvedValue({
        labels: ['A', 'B'],
        matrix: [
          [1, 0],
          [0, 1],
        ],
      })
      renderPage()
      await waitFor(() => {
        expect(
          screen.getByText('evaluations.detail.confusionMatrix'),
        ).toBeInTheDocument()
      })
      expect(apiClient.evaluations.getConfusionMatrix).toHaveBeenCalledWith(
        'eval-1',
        'verdict',
      )
      await user.click(screen.getByText('evaluations.detail.confusionMatrix'))
      expect(
        await screen.findByTestId('confusion-matrix-chart'),
      ).toBeInTheDocument()
    })

    it('hides the confusion tab when the matrix endpoint throws', async () => {
      ;(apiClient.evaluations.getSamples as jest.Mock).mockResolvedValue({
        ...baseSamples,
        items: [
          {
            ...baseSamples.items[0],
            answer_type: 'classification',
            field_name: 'verdict',
          },
        ],
      })
      ;(
        apiClient.evaluations.getConfusionMatrix as jest.Mock
      ).mockRejectedValue(new Error('no matrix'))
      renderPage()
      await waitFor(() => {
        expect(apiClient.evaluations.getConfusionMatrix).toHaveBeenCalled()
      })
      expect(
        screen.queryByText('evaluations.detail.confusionMatrix'),
      ).not.toBeInTheDocument()
    })
  })

  describe('Judges tab + perRunRows + judgeAgreementForFirstMetric', () => {
    const judgesEvaluation = {
      ...baseEvaluation,
      eval_metadata: {
        ...baseEvaluation.eval_metadata,
        any_judge_failed: true,
        judges_by_config: {
          cfg1: [
            {
              judge_model_id: 'judge-a',
              run_index: 0,
              judge_run_id: 'jr-1',
              status: 'completed',
              samples_evaluated: 5,
            },
            {
              judge_model_id: 'judge-b',
              run_index: 1,
              judge_run_id: 'jr-2',
              status: null, // falls back to evaluation.status
              samples_evaluated: null,
            },
          ],
        },
      },
    }

    it('derives perRunRows from judges_by_config and shows the failed banner', async () => {
      const user = userEvent.setup()
      ;(apiClient.evaluations.getResults as jest.Mock).mockResolvedValue(
        judgesEvaluation,
      )
      ;(apiClient.post as jest.Mock).mockResolvedValue({})
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('Judges & Läufe')).toBeInTheDocument()
      })
      await user.click(screen.getByText('Judges & Läufe'))

      const breakdown = await screen.findByTestId('per-run-breakdown')
      expect(breakdown).toHaveAttribute('data-row-count', '2')
      const rows = within(breakdown).getAllByTestId('per-run-row')
      // row 1: explicit status + sample count
      expect(rows[0]).toHaveTextContent('gpt-4o|judge-a|0|completed|5|null')
      // row 2: null status falls back to evaluation.status='completed'; null samples
      expect(rows[1]).toHaveTextContent('gpt-4o|judge-b|1|completed|null|null')
      // metric passed to PerRunBreakdown is the first bare metric
      expect(breakdown).toHaveAttribute('data-metric', 'exact_match')
      // any-judge-failed banner
      expect(
        screen.getByText(/Mindestens ein Judge-Lauf ist fehlgeschlagen/),
      ).toBeInTheDocument()
    })

    it('grades each judge run on the metric of its own config', async () => {
      // An immediate grading: one config per judge tier, each graded by a
      // single judge run, on different metrics. The second row must take
      // its mean from f1_score, not from the first aggregated metric.
      const user = userEvent.setup()
      ;(apiClient.evaluations.getResults as jest.Mock).mockResolvedValue({
        ...baseEvaluation,
        results_by_config: {
          cfg1: { answer_vs_gt: { exact_match: 0.85 } },
          cfg2: { answer_vs_gt: { f1_score: 0.7 } },
        },
        eval_metadata: {
          ...baseEvaluation.eval_metadata,
          judges_by_config: {
            cfg1: [
              {
                judge_model_id: 'judge-free',
                run_index: 0,
                judge_run_id: 'jr-1',
                status: 'completed',
                samples_evaluated: 1,
              },
            ],
            cfg2: [
              {
                judge_model_id: 'judge-paid',
                run_index: 0,
                judge_run_id: 'jr-2',
                status: 'completed',
                samples_evaluated: 1,
              },
            ],
          },
        },
      })
      renderPage()
      await user.click(await screen.findByText('Judges & Läufe'))

      const breakdown = await screen.findByTestId('per-run-breakdown')
      const rows = within(breakdown).getAllByTestId('per-run-row')
      expect(rows[0]).toHaveTextContent('gpt-4o|judge-free|0|completed|1|0.85')
      expect(rows[0]).toHaveAttribute('data-metric', 'exact_match')
      expect(rows[1]).toHaveTextContent('gpt-4o|judge-paid|0|completed|1|0.7')
      expect(rows[1]).toHaveAttribute('data-metric', 'f1_score')
      expect(rows[1]).toHaveAttribute(
        'data-metric-label',
        metricDisplayLabel('f1_score', undefined, mockT),
      )
    })

    it('renders the agreement heatmap from pearson when cohens dict is empty', async () => {
      const user = userEvent.setup()
      ;(apiClient.evaluations.getResults as jest.Mock).mockResolvedValue(
        judgesEvaluation,
      )
      ;(apiClient.post as jest.Mock).mockResolvedValue({
        judge_agreement_by_model_metric: {
          'gpt-4o|exact_match': {
            // empty cohens dict is truthy — must NOT be chosen; fall through to pearson
            cohens_kappa_pairwise: {},
            pearson_r_pairwise: { 'judge-a__judge-b': 0.42 },
            fleiss_kappa: 0.33,
          },
        },
      })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('Judges & Läufe')).toBeInTheDocument()
      })
      await user.click(screen.getByText('Judges & Läufe'))

      const heatmap = await screen.findByTestId('judge-agreement-heatmap')
      // distinct judges derived from pearson pairwise keys split on '__'
      expect(heatmap).toHaveAttribute('data-judges', 'judge-a,judge-b')
      expect(heatmap).toHaveAttribute('data-metric', 'exact_match')
      expect(heatmap).toHaveAttribute('data-score-type', 'pearson')
      expect(heatmap).toHaveAttribute('data-fleiss', '0.33')
    })

    it('uses kappa scoreType when cohens dict is non-empty', async () => {
      const user = userEvent.setup()
      ;(apiClient.evaluations.getResults as jest.Mock).mockResolvedValue(
        judgesEvaluation,
      )
      ;(apiClient.post as jest.Mock).mockResolvedValue({
        judge_agreement_by_model_metric: {
          'gpt-4o|exact_match': {
            cohens_kappa_pairwise: { 'judge-a__judge-b': 0.55 },
            pearson_r_pairwise: {},
            fleiss_kappa: null,
          },
        },
      })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('Judges & Läufe')).toBeInTheDocument()
      })
      await user.click(screen.getByText('Judges & Läufe'))

      const heatmap = await screen.findByTestId('judge-agreement-heatmap')
      expect(heatmap).toHaveAttribute('data-score-type', 'kappa')
      expect(heatmap).toHaveAttribute('data-judges', 'judge-a,judge-b')
    })

    it('does not render the heatmap when only one distinct judge exists', async () => {
      const user = userEvent.setup()
      ;(apiClient.evaluations.getResults as jest.Mock).mockResolvedValue(
        judgesEvaluation,
      )
      ;(apiClient.post as jest.Mock).mockResolvedValue({
        judge_agreement_by_model_metric: {
          'gpt-4o|exact_match': {
            cohens_kappa_pairwise: {},
            pearson_r_pairwise: { 'judge-a__judge-a': 1.0 },
            fleiss_kappa: 0.1,
          },
        },
      })
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('Judges & Läufe')).toBeInTheDocument()
      })
      await user.click(screen.getByText('Judges & Läufe'))
      await screen.findByTestId('per-run-breakdown')
      expect(
        screen.queryByTestId('judge-agreement-heatmap'),
      ).not.toBeInTheDocument()
    })

    it('sets multiRunStats error sentinel when the statistics POST fails (no crash)', async () => {
      const user = userEvent.setup()
      ;(apiClient.evaluations.getResults as jest.Mock).mockResolvedValue(
        judgesEvaluation,
      )
      ;(apiClient.post as jest.Mock).mockRejectedValue(
        new Error('stats failed'),
      )
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('Judges & Läufe')).toBeInTheDocument()
      })
      await user.click(screen.getByText('Judges & Läufe'))
      // PerRunBreakdown still renders; heatmap absent (error sentinel has no agreement block).
      expect(await screen.findByTestId('per-run-breakdown')).toBeInTheDocument()
      expect(
        screen.queryByTestId('judge-agreement-heatmap'),
      ).not.toBeInTheDocument()
    })

    it('does not render the judges tab when there is no judges_by_config', async () => {
      renderPage()
      await waitFor(() => {
        expect(
          screen.getByText('evaluation.human.results.summary'),
        ).toBeInTheDocument()
      })
      expect(screen.queryByText('Judges & Läufe')).not.toBeInTheDocument()
    })
  })

  describe('No sample results', () => {
    it('skips the samples fetch when has_sample_results is false', async () => {
      ;(apiClient.evaluations.getResults as jest.Mock).mockResolvedValue({
        ...baseEvaluation,
        has_sample_results: false,
      })
      renderPage()
      await waitFor(() => {
        expect(apiClient.evaluations.getResults).toHaveBeenCalled()
      })
      expect(apiClient.evaluations.getSamples).not.toHaveBeenCalled()
    })
  })

  describe('a run that matched nothing', () => {
    it('shows why it failed and which configs matched no data', async () => {
      ;(apiClient.evaluations.getResults as jest.Mock).mockResolvedValue({
        ...baseEvaluation,
        status: 'failed',
        error_message:
          "no cells matched the evaluation configuration (0 of 2 configs matched any cell): 'Bewertungsbogen' (llm_judge_rubric) no_generations",
        eval_metadata: {
          ...baseEvaluation.eval_metadata,
          match_by_config: {
            cfg1: {
              metric: 'llm_judge_rubric',
              display_name: 'Bewertungsbogen',
              human_fields: [],
              llm_fields: ['__all_model__'],
              reason: 'no_generations',
            },
            k1: {
              metric: 'korrektur_custom',
              display_name: 'Korrektur',
              human_fields: [],
              llm_fields: [],
              reason: 'manual_metric',
            },
          },
        },
      })
      renderPage()
      const banner = await screen.findByTestId('evaluation-run-failed')
      expect(
        within(banner).getByText(
          /no cells matched the evaluation configuration/,
        ),
      ).toBeInTheDocument()
      const list = within(banner).getByTestId('evaluation-unmatched-configs')
      expect(within(list).getByText('Bewertungsbogen')).toBeInTheDocument()
      expect(within(list).getByText('no_generations')).toBeInTheDocument()
      // The reason is phrased in the reader's language.
      expect(
        within(list).getByText(
          /evaluations\.detail\.matchReasons\.noGenerations/,
        ),
      ).toBeInTheDocument()
      // Every reason was phrased, so the worker's English text moves into
      // the technical details disclosure (still present for the e2e check).
      const details = banner.querySelector('details')
      expect(details).not.toBeNull()
      expect(details).toHaveTextContent(
        'no cells matched the evaluation configuration',
      )
      // A benign reason is not a failure and must not be listed as one.
      expect(within(list).queryByText('Korrektur')).not.toBeInTheDocument()
    })

    it('shows no failure banner for a completed run', async () => {
      renderPage()
      await screen.findAllByText('evaluations.detail.statusLabels.completed')
      expect(
        screen.queryByTestId('evaluation-run-failed'),
      ).not.toBeInTheDocument()
    })

    it('hides the model for a run over submitted answers and greys an empty pass rate', async () => {
      ;(apiClient.evaluations.getResults as jest.Mock).mockResolvedValue({
        ...baseEvaluation,
        model_id: 'unknown',
        status: 'failed',
        samples_evaluated: 0,
        eval_metadata: { ...baseEvaluation.eval_metadata, pass_rate: 0 },
      })
      renderPage()
      await screen.findByTestId('evaluation-run-failed')
      // The worker records 'unknown' for such runs; it is not a model.
      expect(
        screen.queryByTestId('evaluation-detail-model'),
      ).not.toBeInTheDocument()
      // A 0.0% pass rate with nothing graded is not shown as a success.
      const passRate = screen.getByTestId('evaluation-detail-pass-rate')
      expect(passRate).toHaveClass('text-zinc-500')
      expect(passRate).not.toHaveClass('text-emerald-600')
    })

    it('keeps the model and the green pass rate for a graded run', async () => {
      renderPage()
      expect(
        await screen.findByTestId('evaluation-detail-model'),
      ).toHaveTextContent('gpt-4o')
      expect(screen.getByTestId('evaluation-detail-pass-rate')).toHaveClass(
        'text-emerald-600',
      )
    })
  })
  describe('header', () => {
    it('shows the project title as a link instead of its id', async () => {
      renderPage()
      const link = await screen.findByRole('link', {
        name: 'Klausur Polizeirecht',
      })
      expect(link).toHaveAttribute('href', '/projects/project-1')
      expect(projectsAPI.get).toHaveBeenCalledWith('project-1')
      expect(
        screen.getByTestId('evaluation-detail-project'),
      ).not.toHaveTextContent('project-1')
    })

    it('links to the project by a generic label when the project cannot load', async () => {
      ;(projectsAPI.get as jest.Mock).mockRejectedValue(new Error('403'))
      renderPage()
      const link = await screen.findByRole('link', {
        name: 'evaluations.detail.openProject',
      })
      expect(link).toHaveAttribute('href', '/projects/project-1')
    })

    it('shows the run status localized, and an unknown status as stored', async () => {
      ;(apiClient.evaluations.getResults as jest.Mock).mockResolvedValue({
        ...baseEvaluation,
        status: 'failed',
      })
      const { unmount } = renderPage()
      expect(
        await screen.findByTestId('evaluation-detail-status'),
      ).toHaveTextContent('evaluations.detail.statusLabels.failed')
      unmount()
      ;(apiClient.evaluations.getResults as jest.Mock).mockResolvedValue({
        ...baseEvaluation,
        status: 'resuming_somehow',
      })
      renderPage()
      expect(
        await screen.findByTestId('evaluation-detail-status'),
      ).toHaveTextContent('resuming_somehow')
    })
  })

  describe('aggregate metrics', () => {
    const rubricEvaluation = {
      ...baseEvaluation,
      metrics: {
        // Companion keys first: they must neither show nor be auto-selected.
        'rub|human:loesung|task.musterloesung|raw_score': 70,
        'rub|human:loesung|task.musterloesung|w5_page_rubric_passed': 1,
        'rub|human:loesung|task.musterloesung|w5_page_rubric': 0.7,
        'rub|human:loesung|task.musterloesung|w5_page_rubric_grade_points': 11,
      },
      evaluation_configs: [
        { id: 'rub', metric: 'w5_page_rubric', display_name: 'Bogen (paid)' },
      ],
    }

    beforeAll(() => {
      registerMetric('w5_page_rubric', {
        name: 'w5_page_rubric',
        display_name: 'Bewertungsbogen (LLM Judge)',
        description: '',
        category: 'LLM-as-Judge',
        status: 'stable',
        supports_parameters: false,
        display_scale: '0-1',
      })
      registerMetric('w5_page_rubric_grade_points', {
        name: 'w5_page_rubric_grade_points',
        display_name: 'Notenpunkte (Bewertungsbogen)',
        description: '',
        category: 'LLM-as-Judge',
        status: 'stable',
        supports_parameters: false,
        display_scale: '0-18',
      })
    })

    it('hides companion values and labels grade points by the registry', async () => {
      ;(apiClient.evaluations.getResults as jest.Mock).mockResolvedValue(
        rubricEvaluation,
      )
      renderPage()
      const tiles = await screen.findAllByTestId('evaluation-aggregate-metric')
      expect(tiles).toHaveLength(2)
      expect(tiles[0]).toHaveTextContent('Bewertungsbogen (LLM Judge)')
      expect(tiles[0]).toHaveTextContent('0.700')
      expect(tiles[1]).toHaveTextContent('Notenpunkte (Bewertungsbogen)')
      expect(tiles[1]).toHaveTextContent('11.0')
      expect(screen.queryByText(/raw_score|Raw Score/)).not.toBeInTheDocument()
      expect(screen.queryByText(/_passed|Passed$/)).not.toBeInTheDocument()
      // One config: no config name repeated on every tile.
      expect(screen.queryByText('Bogen (paid)')).not.toBeInTheDocument()
      // The auto-selected distribution metric is a result, not raw_score.
      await waitFor(() => {
        expect(apiClient.get).toHaveBeenCalledWith(
          '/evaluations/eval-1/metrics/w5_page_rubric/distribution',
        )
      })
    })

    it('names the config on each tile when the run holds several', async () => {
      renderPage()
      await screen.findAllByTestId('evaluation-aggregate-metric')
      await waitFor(() => {
        // The snapshot configs have no display_name: the metric name stands in.
        expect(
          screen.getAllByTestId('evaluation-aggregate-metric')[0],
        ).toHaveTextContent('Exact Match')
      })
    })

    it('offers only result metrics, by name, in the distribution picker', async () => {
      const user = userEvent.setup()
      ;(apiClient.evaluations.getResults as jest.Mock).mockResolvedValue(
        rubricEvaluation,
      )
      renderPage()
      await user.click(
        await screen.findByText('evaluation.human.results.distribution'),
      )
      const select = screen.getByRole('combobox')
      await waitFor(() =>
        expect(
          within(select).getByText('Notenpunkte (Bewertungsbogen)'),
        ).toBeInTheDocument(),
      )
      expect(within(select).queryByText(/raw_score/i)).not.toBeInTheDocument()
      expect(within(select).getAllByRole('option')).toHaveLength(2)
    })

    it('hands the run configs to the sample table', async () => {
      const user = userEvent.setup()
      ;(apiClient.evaluations.getResults as jest.Mock).mockResolvedValue(
        rubricEvaluation,
      )
      renderPage()
      await user.click(
        await screen.findByText('evaluation.human.results.detailed'),
      )
      const table = await screen.findByTestId('sample-results-table')
      expect(JSON.parse(table.getAttribute('data-configs') || '[]')).toEqual([
        { id: 'rub', metric: 'w5_page_rubric', display_name: 'Bogen (paid)' },
      ])
    })
  })

  describe('failed-run diagnostics', () => {
    const failed = (rec: Record<string, unknown>, message: string) => ({
      ...baseEvaluation,
      status: 'failed',
      error_message: message,
      eval_metadata: {
        ...baseEvaluation.eval_metadata,
        match_by_config: { cfg1: rec },
      },
    })

    it('names what the other side holds when the worker counted subjects', async () => {
      ;(apiClient.evaluations.getResults as jest.Mock).mockResolvedValue(
        failed(
          {
            metric: 'llm_judge_rubric',
            display_name: 'Bewertungsbogen',
            llm_fields: ['__all_model__'],
            human_fields: [],
            reason: 'no_generations',
            subject_counts: { generations: 0, annotations: 1 },
          },
          'no cells matched the evaluation configuration',
        ),
      )
      renderPage()
      const list = await screen.findByTestId('evaluation-unmatched-configs')
      expect(
        within(list).getByText(
          /evaluations\.detail\.matchReasons\.noGenerationsWithAnswers/,
        ),
      ).toBeInTheDocument()
    })

    it('keeps the worker message in view for a reason it cannot phrase', async () => {
      ;(apiClient.evaluations.getResults as jest.Mock).mockResolvedValue(
        failed(
          {
            metric: 'exact_match',
            display_name: 'Neu',
            llm_fields: [],
            human_fields: [],
            reason: 'a_reason_from_the_future',
          },
          'something new went wrong',
        ),
      )
      renderPage()
      const banner = await screen.findByTestId('evaluation-run-failed')
      expect(banner.querySelector('details')).toBeNull()
      expect(
        within(banner).getByText('something new went wrong'),
      ).toBeInTheDocument()
      expect(
        within(banner).getByText('a_reason_from_the_future'),
      ).toBeInTheDocument()
    })

    it('shows the worker message for a failure without config records', async () => {
      ;(apiClient.evaluations.getResults as jest.Mock).mockResolvedValue({
        ...baseEvaluation,
        status: 'failed',
        error_message: 'worker crashed',
      })
      renderPage()
      const banner = await screen.findByTestId('evaluation-run-failed')
      expect(within(banner).getByText('worker crashed')).toBeInTheDocument()
      expect(
        within(banner).queryByTestId('evaluation-unmatched-configs'),
      ).not.toBeInTheDocument()
    })
  })

  // Registration is module-global, so these run last in this file.
  describe('EvaluationRunRubricHost slot', () => {
    it('renders the page without a host when none is registered', async () => {
      renderPage()
      await screen.findByTestId('evaluation-detail-status')
      expect(screen.queryByTestId('rubric-host')).not.toBeInTheDocument()
    })

    it('wraps the page content in the registered host with the project id', async () => {
      registerSlot(
        'EvaluationRunRubricHost',
        ({ projectId, children }: any) => (
          <div data-testid="rubric-host" data-project-id={projectId}>
            {children}
          </div>
        ),
      )
      renderPage()
      const host = await screen.findByTestId('rubric-host')
      expect(host).toHaveAttribute('data-project-id', 'project-1')
      expect(
        within(host).getByTestId('evaluation-detail-status'),
      ).toBeInTheDocument()
      expect(
        within(host).getByText('evaluations.detail.aggregateMetrics'),
      ).toBeInTheDocument()
    })
  })
})
