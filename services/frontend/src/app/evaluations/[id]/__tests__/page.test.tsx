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

jest.mock('@/lib/utils/logger', () => ({
  logger: { debug: jest.fn(), error: jest.fn(), warn: jest.fn(), info: jest.fn() },
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
  JudgeAgreementHeatmap: ({ judgeModelIds, metric, scoreType, pairwise, fleissKappa }: any) => (
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
        <div key={i} data-testid="per-run-row">
          {r.target_model_id}|{r.judge_model_id}|{r.run_index}|{r.status}|
          {String(r.samples_evaluated)}|{String(r.mean_score)}
        </div>
      ))}
    </div>
  ),
}))

jest.mock('@/components/evaluation/SampleResultsTable', () => ({
  SampleResultsTable: ({ data, consistencyByTaskId }: any) => (
    <div
      data-testid="sample-results-table"
      data-sample-count={data.length}
      data-consistency={JSON.stringify(consistencyByTaskId)}
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
    <button onClick={onClick} disabled={disabled} data-variant={variant} className={className}>
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
}))

import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import { apiClient } from '@/lib/api/client'
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

// t() returns the fallback (2nd arg) when present, else the key.
const mockT = (key: string, fallback?: string) => fallback ?? key

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
    <EvaluationDashboard params={Promise.resolve({ id: 'eval-1' })} />
  )
}

describe('EvaluationDashboard ([id] page)', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    ;(useRouter as jest.Mock).mockReturnValue(mockRouter)
    ;(useI18n as jest.Mock).mockReturnValue({ t: mockT })
    ;(useToast as jest.Mock).mockReturnValue({ addToast: mockAddToast })

    ;(apiClient.evaluations.getResults as jest.Mock).mockResolvedValue(baseEvaluation)
    ;(apiClient.evaluations.getSamples as jest.Mock).mockResolvedValue(baseSamples)
    ;(apiClient.evaluations.getConfusionMatrix as jest.Mock).mockResolvedValue(null)
    ;(apiClient.get as jest.Mock).mockResolvedValue({ data: { buckets: [1, 2, 3] } })
    ;(apiClient.post as jest.Mock).mockResolvedValue({})
  })

  describe('Loading and not-found', () => {
    it('shows a spinner before the evaluation resolves', () => {
      ;(apiClient.evaluations.getResults as jest.Mock).mockReturnValue(
        new Promise(() => {})
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
          screen.getByText('evaluation.human.results.noResults')
        ).toBeInTheDocument()
      })
      await user.click(screen.getByText('evaluation.human.preference.next'))
      expect(mockRouter.push).toHaveBeenCalledWith('/runs?type=evaluation')
    })

    it('shows an error toast when the evaluation fails to load', async () => {
      ;(apiClient.evaluations.getResults as jest.Mock).mockRejectedValue(
        new Error('load failed')
      )
      renderPage()
      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'evaluation.human.preference.saveFailed',
          'error'
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

    it('renders bare metric names parsed from the composite keys', async () => {
      renderPage()
      await waitFor(() => {
        // `cfg1|answer|gt|exact_match` -> bare `exact_match`
        expect(screen.getAllByText('exact_match').length).toBeGreaterThan(0)
      })
      expect(screen.getAllByText('f1_score').length).toBeGreaterThan(0)
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
        expect(screen.getAllByText('exact_match').length).toBeGreaterThan(0)
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
        expect(screen.getAllByText('bleu').length).toBeGreaterThan(0)
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
        expect(
          screen.getByText('Eingeschränkt auf:')
        ).toBeInTheDocument()
      })
      // annotator display rendered in the scope summary
      expect(screen.getByText(/Alice/)).toBeInTheDocument()
    })

    it('loads the metric distribution on mount for the auto-selected first metric', async () => {
      renderPage()
      await waitFor(() => {
        expect(apiClient.get).toHaveBeenCalledWith(
          '/evaluations/eval-1/metrics/exact_match/distribution'
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
        expect(screen.getByText('evaluation.human.results.detailed')).toBeInTheDocument()
      })
      await user.click(screen.getByText('evaluation.human.results.detailed'))

      const table = await screen.findByTestId('sample-results-table')
      expect(table).toHaveAttribute('data-sample-count', '1')
      await waitFor(() => {
        const consistency = JSON.parse(
          screen.getByTestId('sample-results-table').getAttribute('data-consistency') || '{}'
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
        expect(screen.getByText('evaluation.human.results.detailed')).toBeInTheDocument()
      })
      await user.click(screen.getByText('evaluation.human.results.detailed'))
      await waitFor(() => {
        expect(apiClient.post).toHaveBeenCalledWith(
          '/evaluations/projects/project-1/statistics',
          { metrics: ['exact_match', 'f1_score'], aggregation: 'model', methods: ['ci'] }
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
          screen.getByText('evaluation.human.results.distribution')
        ).toBeInTheDocument()
      })
      await user.click(screen.getByText('evaluation.human.results.distribution'))

      expect(await screen.findByTestId('metric-distribution-chart')).toBeInTheDocument()

      const select = screen.getByRole('combobox')
      // The shared Select mock pushes <option>s in via an effect — wait for
      // the f1_score option to mount before driving the change.
      await waitFor(() =>
        expect(within(select).getByText('f1_score')).toBeInTheDocument()
      )
      await user.selectOptions(select, 'f1_score')
      await waitFor(() => {
        expect(apiClient.get).toHaveBeenCalledWith(
          '/evaluations/eval-1/metrics/f1_score/distribution'
        )
      })
    })

    it('surfaces an error toast when the distribution fetch fails', async () => {
      ;(apiClient.get as jest.Mock).mockRejectedValue(new Error('dist failed'))
      renderPage()
      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'evaluation.human.preference.saveFailed',
          'error'
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
          { ...baseSamples.items[0], answer_type: 'single_choice', field_name: 'verdict' },
        ],
      })
      ;(apiClient.evaluations.getConfusionMatrix as jest.Mock).mockResolvedValue({
        labels: ['A', 'B'],
        matrix: [[1, 0], [0, 1]],
      })
      renderPage()
      await waitFor(() => {
        expect(
          screen.getByText('evaluations.detail.confusionMatrix')
        ).toBeInTheDocument()
      })
      expect(apiClient.evaluations.getConfusionMatrix).toHaveBeenCalledWith(
        'eval-1',
        'verdict'
      )
      await user.click(screen.getByText('evaluations.detail.confusionMatrix'))
      expect(await screen.findByTestId('confusion-matrix-chart')).toBeInTheDocument()
    })

    it('hides the confusion tab when the matrix endpoint throws', async () => {
      ;(apiClient.evaluations.getSamples as jest.Mock).mockResolvedValue({
        ...baseSamples,
        items: [
          { ...baseSamples.items[0], answer_type: 'classification', field_name: 'verdict' },
        ],
      })
      ;(apiClient.evaluations.getConfusionMatrix as jest.Mock).mockRejectedValue(
        new Error('no matrix')
      )
      renderPage()
      await waitFor(() => {
        expect(apiClient.evaluations.getConfusionMatrix).toHaveBeenCalled()
      })
      expect(
        screen.queryByText('evaluations.detail.confusionMatrix')
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
      ;(apiClient.evaluations.getResults as jest.Mock).mockResolvedValue(judgesEvaluation)
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
        screen.getByText(/Mindestens ein Judge-Lauf ist fehlgeschlagen/)
      ).toBeInTheDocument()
    })

    it('renders the agreement heatmap from pearson when cohens dict is empty', async () => {
      const user = userEvent.setup()
      ;(apiClient.evaluations.getResults as jest.Mock).mockResolvedValue(judgesEvaluation)
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
      ;(apiClient.evaluations.getResults as jest.Mock).mockResolvedValue(judgesEvaluation)
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
      ;(apiClient.evaluations.getResults as jest.Mock).mockResolvedValue(judgesEvaluation)
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
      expect(screen.queryByTestId('judge-agreement-heatmap')).not.toBeInTheDocument()
    })

    it('sets multiRunStats error sentinel when the statistics POST fails (no crash)', async () => {
      const user = userEvent.setup()
      ;(apiClient.evaluations.getResults as jest.Mock).mockResolvedValue(judgesEvaluation)
      ;(apiClient.post as jest.Mock).mockRejectedValue(new Error('stats failed'))
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('Judges & Läufe')).toBeInTheDocument()
      })
      await user.click(screen.getByText('Judges & Läufe'))
      // PerRunBreakdown still renders; heatmap absent (error sentinel has no agreement block).
      expect(await screen.findByTestId('per-run-breakdown')).toBeInTheDocument()
      expect(screen.queryByTestId('judge-agreement-heatmap')).not.toBeInTheDocument()
    })

    it('does not render the judges tab when there is no judges_by_config', async () => {
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('evaluation.human.results.summary')).toBeInTheDocument()
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
})
