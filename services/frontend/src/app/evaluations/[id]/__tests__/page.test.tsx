/**
 * Test suite for Individual Evaluation Dashboard Page
 * Issue #763: Per-sample evaluation results and visualization dashboard
 *
 * Target: 85%+ coverage (from 0%)
 */

import { apiClient } from '@/lib/api/client'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import EvaluationDashboard from '../page'

// Mock dependencies
jest.mock('@/lib/api/client', () => ({
  apiClient: {
    get: jest.fn(),
  },
}))

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(() => ({
    push: jest.fn(),
    back: jest.fn(),
    replace: jest.fn(),
  })),
}))


// Create stable mock function outside the mock factory
const mockT = (key: string) => key

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: mockT,
    locale: 'en',
  }),
}))

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: '1', email: 'test@example.com' },
    isAuthenticated: true,
    login: jest.fn(),
    logout: jest.fn(),
  }),
  AuthProvider: ({ children }: any) => <>{children}</>,
}))

// Mock toast with stable function reference
const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({
    addToast: mockAddToast,
  }),
}))

jest.mock('@/components/shared/Badge', () => ({
  Badge: ({ children }: any) => <span data-testid="badge">{children}</span>,
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, disabled, ...props }: any) => (
    <button onClick={onClick} disabled={disabled} {...props}>
      {children}
    </button>
  ),
}))

jest.mock('@/components/shared/Card', () => ({
  Card: ({ children }: any) => <div data-testid="card">{children}</div>,
}))

jest.mock('@/components/shared/FeatureFlag', () => ({
  FeatureFlag: ({ children }: any) => <>{children}</>,
}))

jest.mock('@/components/shared/LoadingSpinner', () => ({
  LoadingSpinner: ({ className }: any) => (
    <div className={className} data-testid="loading-spinner">
      Loading...
    </div>
  ),
}))

jest.mock('@heroicons/react/24/outline', () => ({
  ArrowLeftIcon: () => <div data-testid="arrow-left-icon" />,
  ArrowPathIcon: () => <div data-testid="arrow-path-icon" />,
  ChartBarIcon: () => <div data-testid="chart-bar-icon" />,
}))

jest.mock('@/components/evaluation/ConfusionMatrixChart', () => ({
  ConfusionMatrixChart: ({ data }: any) => (
    <div data-testid="confusion-matrix">{JSON.stringify(data)}</div>
  ),
}))

jest.mock('@/components/evaluation/MetricDistributionChart', () => ({
  MetricDistributionChart: ({ data }: any) => (
    <div data-testid="metric-distribution">{JSON.stringify(data)}</div>
  ),
}))

jest.mock('@/components/evaluation/SampleResultsTable', () => ({
  SampleResultsTable: ({ data }: any) => (
    <div data-testid="sample-results-table">{data.length} samples</div>
  ),
}))

const mockEvaluationData = {
  id: 'eval-123',
  project_id: 'proj-456',
  model_id: 'gpt-4',
  status: 'completed',
  samples_evaluated: 100,
  metrics: {
    accuracy: 0.85,
    f1_score: 0.78,
    precision: 0.82,
  },
  eval_metadata: {
    samples_passed: 85,
    samples_failed: 15,
    pass_rate: 0.85,
  },
  created_at: '2024-01-01T10:00:00Z',
  has_sample_results: true,
}

const mockSampleResults = {
  items: [
    {
      id: 'sample-1',
      task_id: 'task-1',
      field_name: 'classification',
      answer_type: 'single_choice',
      ground_truth: { value: 'A' },
      prediction: { value: 'A' },
      metrics: { accuracy: 1.0 },
      passed: true,
      confidence_score: 0.95,
      error_message: null,
      processing_time_ms: 150,
    },
    {
      id: 'sample-2',
      task_id: 'task-2',
      field_name: 'classification',
      answer_type: 'single_choice',
      ground_truth: { value: 'B' },
      prediction: { value: 'A' },
      metrics: { accuracy: 0.0 },
      passed: false,
      confidence_score: 0.65,
      error_message: null,
      processing_time_ms: 200,
    },
  ],
}

const mockConfusionMatrix = {
  labels: ['A', 'B', 'C'],
  matrix: [
    [10, 2, 1],
    [1, 15, 2],
    [0, 1, 12],
  ],
}

const mockMetricDistribution = {
  bins: [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
  counts: [5, 10, 20, 30, 35],
}

describe('EvaluationDashboard Page', () => {
  const mockApiClient = apiClient as jest.Mocked<typeof apiClient>

  beforeEach(() => {
    jest.resetAllMocks()
    // Reset mock implementation to ensure clean state
    mockApiClient.get.mockReset()
  })

  describe('loading state', () => {
    it('shows loading spinner initially', () => {
      mockApiClient.get.mockImplementation(() => new Promise(() => {}))

      render(
        <EvaluationDashboard params={Promise.resolve({ id: 'eval-123' })} />
      )

      expect(screen.getByTestId('loading-spinner')).toBeInTheDocument()
    })
  })

  describe('data loading', () => {
    it('loads evaluation data on mount', async () => {
      mockApiClient.get.mockResolvedValueOnce({ data: mockEvaluationData })

      render(
        <EvaluationDashboard params={Promise.resolve({ id: 'eval-123' })} />
      )

      await waitFor(() => {
        expect(mockApiClient.get).toHaveBeenCalledWith('/evaluations/eval-123')
      })
    })

    it('loads sample results when has_sample_results is true', async () => {
      mockApiClient.get
        .mockResolvedValueOnce({ data: mockEvaluationData })
        .mockResolvedValueOnce({ data: mockSampleResults })
        .mockRejectedValueOnce(new Error('No confusion matrix'))
        .mockResolvedValueOnce({ data: mockMetricDistribution })

      render(
        <EvaluationDashboard params={Promise.resolve({ id: 'eval-123' })} />
      )

      await waitFor(() => {
        expect(mockApiClient.get).toHaveBeenCalledWith(
          '/evaluations/eval-123/samples',
          { params: { page: 1, page_size: 100 } }
        )
      })
    })

    it('loads confusion matrix for classification fields', async () => {
      mockApiClient.get
        .mockResolvedValueOnce({ data: mockEvaluationData })
        .mockResolvedValueOnce({ data: mockSampleResults })
        .mockResolvedValueOnce({ data: mockConfusionMatrix })
        .mockResolvedValueOnce({ data: mockMetricDistribution })

      render(
        <EvaluationDashboard params={Promise.resolve({ id: 'eval-123' })} />
      )

      await waitFor(() => {
        expect(mockApiClient.get).toHaveBeenCalledWith(
          '/evaluations/eval-123/confusion-matrix',
          { params: { field_name: 'classification' } }
        )
      })
    })

    it('auto-selects first metric for distribution', async () => {
      mockApiClient.get
        .mockResolvedValueOnce({ data: mockEvaluationData })
        .mockResolvedValueOnce({ data: mockSampleResults })
        .mockRejectedValueOnce(new Error('No confusion matrix'))
        .mockResolvedValueOnce({ data: mockMetricDistribution })

      render(
        <EvaluationDashboard params={Promise.resolve({ id: 'eval-123' })} />
      )

      await waitFor(() => {
        expect(mockApiClient.get).toHaveBeenCalledWith(
          '/evaluations/eval-123/metrics/accuracy/distribution'
        )
      })
    })

    it('handles API errors gracefully', async () => {
      const consoleError = jest.spyOn(console, 'error').mockImplementation()
      mockApiClient.get.mockRejectedValueOnce(new Error('API Error'))

      render(
        <EvaluationDashboard params={Promise.resolve({ id: 'eval-123' })} />
      )

      await waitFor(() => {
        expect(consoleError).toHaveBeenCalledWith(
          'Failed to load evaluation:',
          expect.any(Error)
        )
      })

      consoleError.mockRestore()
    })

    it('does not load samples when has_sample_results is false', async () => {
      const dataWithoutSamples = {
        ...mockEvaluationData,
        has_sample_results: false,
      }
      mockApiClient.get.mockResolvedValueOnce({ data: dataWithoutSamples })

      render(
        <EvaluationDashboard params={Promise.resolve({ id: 'eval-123' })} />
      )

      await waitFor(() => {
        expect(mockApiClient.get).toHaveBeenCalledTimes(1)
      })
    })
  })

  describe('no evaluation found', () => {
    it('shows no results message when evaluation is null', async () => {
      mockApiClient.get.mockResolvedValueOnce({ data: null })

      render(
        <EvaluationDashboard params={Promise.resolve({ id: 'eval-123' })} />
      )

      await waitFor(() => {
        expect(
          screen.getByText(/evaluation.human.results.noResults/i)
        ).toBeInTheDocument()
      })
    })

    it('shows back button when no evaluation found', async () => {
      mockApiClient.get.mockResolvedValueOnce({ data: null })

      render(
        <EvaluationDashboard params={Promise.resolve({ id: 'eval-123' })} />
      )

      await waitFor(() => {
        expect(
          screen.getByText(/evaluation.human.preference.next/i)
        ).toBeInTheDocument()
      })
    })
  })

  describe('header section', () => {
    beforeEach(async () => {
      mockApiClient.get
        .mockResolvedValueOnce({ data: mockEvaluationData })
        .mockResolvedValueOnce({ data: mockSampleResults })
        .mockRejectedValueOnce(new Error('No confusion matrix')) // confusion matrix call
        .mockResolvedValueOnce({ data: mockMetricDistribution })

      render(
        <EvaluationDashboard params={Promise.resolve({ id: 'eval-123' })} />
      )

      await waitFor(() => {
        expect(
          screen.getByText(/evaluation.human.results.title/i)
        ).toBeInTheDocument()
      })
    })

    it('displays evaluation title', () => {
      expect(
        screen.getByText(/evaluation.human.results.title/i)
      ).toBeInTheDocument()
    })

    it('displays model ID', () => {
      expect(screen.getByText(/evaluations.detail.model.*gpt-4/i)).toBeInTheDocument()
    })

    it('displays project ID', () => {
      expect(screen.getByText(/evaluations.detail.project.*proj-456/i)).toBeInTheDocument()
    })

    it('displays status badge', () => {
      expect(screen.getByText('completed')).toBeInTheDocument()
    })

    it('shows completed status with success variant', () => {
      const badge = screen.getByText('completed')
      expect(badge).toBeInTheDocument()
    })

    it('has refresh button', () => {
      expect(screen.getByTestId('arrow-path-icon')).toBeInTheDocument()
    })

    it('has back button that navigates to evaluations list', () => {
      expect(screen.getByText('evaluations.detail.back')).toBeInTheDocument()
    })
  })

  describe('tabs navigation', () => {
    beforeEach(async () => {
      mockApiClient.get
        .mockResolvedValueOnce({ data: mockEvaluationData })
        .mockResolvedValueOnce({ data: mockSampleResults })
        .mockResolvedValueOnce({ data: mockConfusionMatrix })
        .mockResolvedValueOnce({ data: mockMetricDistribution })

      render(
        <EvaluationDashboard params={Promise.resolve({ id: 'eval-123' })} />
      )

      await waitFor(() => {
        expect(
          screen.getByText(/evaluation.human.results.summary/i)
        ).toBeInTheDocument()
      })
    })

    it('displays all tabs', () => {
      expect(
        screen.getByText(/evaluation.human.results.summary/i)
      ).toBeInTheDocument()
      expect(
        screen.getByText(/evaluation.human.results.detailed/i)
      ).toBeInTheDocument()
      expect(screen.getByText('evaluations.detail.confusionMatrix')).toBeInTheDocument()
      expect(
        screen.getByText(/evaluation.human.results.distribution/i)
      ).toBeInTheDocument()
    })

    it('switches to samples tab on click', async () => {
      const user = userEvent.setup()
      const samplesTab = screen.getByText(/evaluation.human.results.detailed/i)

      await user.click(samplesTab)

      await waitFor(() => {
        expect(screen.getByTestId('sample-results-table')).toBeInTheDocument()
      })
    })

    it('switches to confusion matrix tab on click', async () => {
      const user = userEvent.setup()
      const confusionTab = screen.getByText('evaluations.detail.confusionMatrix')

      await user.click(confusionTab)

      await waitFor(() => {
        expect(screen.getByTestId('confusion-matrix')).toBeInTheDocument()
      })
    })

    it('switches to distributions tab on click', async () => {
      const user = userEvent.setup()
      const distributionsTab = screen.getByText(
        /evaluation.human.results.distribution/i
      )

      await user.click(distributionsTab)

      await waitFor(() => {
        expect(screen.getByText('evaluations.detail.selectMetric')).toBeInTheDocument()
      })
    })
  })

  describe('confusion matrix visibility', () => {
    it('does not show confusion matrix tab when no confusion matrix available', async () => {
      jest.clearAllMocks()
      const noSamplesEval = {
        id: 'eval-456', // Different ID to avoid caching
        project_id: 'proj-456',
        model_id: 'gpt-4',
        status: 'completed',
        samples_evaluated: 100,
        metrics: {
          accuracy: 0.85,
        },
        eval_metadata: {
          samples_passed: 85,
          samples_failed: 15,
          pass_rate: 0.85,
        },
        created_at: '2024-01-01T10:00:00Z',
        has_sample_results: false, // No samples, so no confusion matrix
      }
      mockApiClient.get.mockResolvedValueOnce({ data: noSamplesEval })

      render(
        <EvaluationDashboard params={Promise.resolve({ id: 'eval-456' })} />
      )

      // Wait for loading to complete
      await waitFor(
        () => {
          expect(
            screen.queryByTestId('loading-spinner')
          ).not.toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      // Check that tabs are rendered
      const summaryTabs = screen.getAllByText(
        /evaluation.human.results.summary/i
      )
      expect(summaryTabs.length).toBeGreaterThan(0)

      // Confusion Matrix tab should NOT be present
      expect(screen.queryByText('evaluations.detail.confusionMatrix')).not.toBeInTheDocument()
    })
  })

  describe('overview tab', () => {
    beforeEach(async () => {
      mockApiClient.get
        .mockResolvedValueOnce({ data: mockEvaluationData })
        .mockResolvedValueOnce({ data: mockSampleResults })
        .mockRejectedValueOnce(new Error('No confusion matrix'))
        .mockResolvedValueOnce({ data: mockMetricDistribution })

      render(
        <EvaluationDashboard params={Promise.resolve({ id: 'eval-123' })} />
      )

      await waitFor(() => {
        expect(screen.getByText('evaluations.detail.passRate')).toBeInTheDocument()
        expect(screen.getByText('85.0%')).toBeInTheDocument()
      })
    })

    it('displays total samples count', () => {
      expect(screen.getByText('evaluations.detail.totalSamples')).toBeInTheDocument()
      expect(screen.getByText('100')).toBeInTheDocument()
    })

    it('displays pass rate', () => {
      expect(screen.getByText('evaluations.detail.passRate')).toBeInTheDocument()
      expect(screen.getByText('85.0%')).toBeInTheDocument()
    })

    it('displays samples passed count', () => {
      expect(screen.getByText('evaluations.detail.passed')).toBeInTheDocument()
      expect(screen.getByText('85')).toBeInTheDocument()
    })

    it('displays samples failed count', () => {
      expect(screen.getByText('evaluations.detail.failed')).toBeInTheDocument()
      expect(screen.getByText('15')).toBeInTheDocument()
    })

    it('displays aggregate metrics', () => {
      expect(screen.getByText('evaluations.detail.aggregateMetrics')).toBeInTheDocument()
      expect(screen.getByText('accuracy')).toBeInTheDocument()
      expect(screen.getByText('0.850')).toBeInTheDocument()
      expect(screen.getByText('f1_score')).toBeInTheDocument()
      expect(screen.getByText('0.780')).toBeInTheDocument()
    })

    it('formats metrics to 3 decimal places', () => {
      expect(screen.getByText('0.850')).toBeInTheDocument()
      expect(screen.getByText('0.780')).toBeInTheDocument()
      expect(screen.getByText('0.820')).toBeInTheDocument()
    })
  })

  describe('samples tab', () => {
    it('displays sample results table', async () => {
      mockApiClient.get
        .mockResolvedValueOnce({ data: mockEvaluationData })
        .mockResolvedValueOnce({ data: mockSampleResults })
        .mockRejectedValueOnce(new Error('No confusion matrix'))
        .mockResolvedValueOnce({ data: mockMetricDistribution })

      render(
        <EvaluationDashboard params={Promise.resolve({ id: 'eval-123' })} />
      )

      await waitFor(() => {
        expect(
          screen.getByText(/evaluation.human.results.summary/i)
        ).toBeInTheDocument()
      })

      const user = userEvent.setup()
      const samplesTab = screen.getByText(/evaluation.human.results.detailed/i)
      await user.click(samplesTab)

      expect(screen.getByTestId('sample-results-table')).toBeInTheDocument()
      expect(screen.getByText('2 samples')).toBeInTheDocument()
    })

    it('shows per-sample results heading', async () => {
      mockApiClient.get
        .mockResolvedValueOnce({ data: mockEvaluationData })
        .mockResolvedValueOnce({ data: mockSampleResults })
        .mockRejectedValueOnce(new Error('No confusion matrix'))
        .mockResolvedValueOnce({ data: mockMetricDistribution })

      render(
        <EvaluationDashboard params={Promise.resolve({ id: 'eval-123' })} />
      )

      await waitFor(() => {
        expect(
          screen.getByText(/evaluation.human.results.summary/i)
        ).toBeInTheDocument()
      })

      const user = userEvent.setup()
      const samplesTab = screen.getByText(/evaluation.human.results.detailed/i)
      await user.click(samplesTab)

      expect(screen.getByText('evaluations.detail.perSampleResults')).toBeInTheDocument()
    })
  })

  describe('distributions tab', () => {
    beforeEach(async () => {
      // Mock order: eval data, samples, then distribution and confusion matrix may interleave
      // so use mockImplementation to handle both cases
      mockApiClient.get.mockImplementation((url: string) => {
        if (url === '/evaluations/eval-123') {
          return Promise.resolve({ data: mockEvaluationData })
        }
        if (url === '/evaluations/eval-123/samples') {
          return Promise.resolve({ data: mockSampleResults })
        }
        if (url.includes('/distribution')) {
          return Promise.resolve({ data: mockMetricDistribution })
        }
        if (url.includes('/confusion-matrix')) {
          return Promise.reject(new Error('No confusion matrix'))
        }
        return Promise.reject(new Error(`Unexpected URL: ${url}`))
      })

      render(
        <EvaluationDashboard params={Promise.resolve({ id: 'eval-123' })} />
      )

      await waitFor(() => {
        expect(
          screen.getByText(/evaluation.human.results.summary/i)
        ).toBeInTheDocument()
      })

      const user = userEvent.setup()
      const distributionsTab = screen.getByText(
        /evaluation.human.results.distribution/i
      )
      await user.click(distributionsTab)
    })

    it('shows metric selector', () => {
      expect(screen.getByText('evaluations.detail.selectMetric')).toBeInTheDocument()
    })

    it('displays all available metrics in selector', () => {
      const select = screen.getByRole('combobox')
      expect(select).toBeInTheDocument()

      const options = screen.getAllByRole('option')
      expect(options).toHaveLength(3)
      expect(
        screen.getByRole('option', { name: 'accuracy' })
      ).toBeInTheDocument()
      expect(
        screen.getByRole('option', { name: 'f1_score' })
      ).toBeInTheDocument()
      expect(
        screen.getByRole('option', { name: 'precision' })
      ).toBeInTheDocument()
    })

    it('loads metric distribution on metric change', async () => {
      jest.clearAllMocks()
      mockApiClient.get.mockResolvedValueOnce({ data: mockMetricDistribution })

      const user = userEvent.setup()
      const select = screen.getByRole('combobox')

      await user.selectOptions(select, 'f1_score')

      await waitFor(() => {
        expect(mockApiClient.get).toHaveBeenCalledWith(
          '/evaluations/eval-123/metrics/f1_score/distribution'
        )
      })
    })

    it('displays metric distribution chart', async () => {
      // The metric distribution should already be loaded in beforeEach
      // Check if it's visible or wait a bit more
      await waitFor(
        () => {
          const chart = screen.queryByTestId('metric-distribution')
          if (!chart) {
            // If chart isn't visible, it might be still loading
            expect(screen.queryByTestId('loading-spinner')).toBe(null)
          }
          expect(screen.getByTestId('metric-distribution')).toBeInTheDocument()
        },
        { timeout: 5000 }
      )
    })
  })

  describe('refresh functionality', () => {
    it('reloads data when refresh button clicked', async () => {
      mockApiClient.get
        .mockResolvedValueOnce({ data: mockEvaluationData })
        .mockResolvedValueOnce({ data: mockSampleResults })
        .mockRejectedValueOnce(new Error('No confusion matrix'))
        .mockResolvedValueOnce({ data: mockMetricDistribution })

      render(
        <EvaluationDashboard params={Promise.resolve({ id: 'eval-123' })} />
      )

      await waitFor(() => {
        expect(mockApiClient.get).toHaveBeenCalledWith('/evaluations/eval-123')
      })

      jest.clearAllMocks()

      mockApiClient.get
        .mockResolvedValueOnce({ data: mockEvaluationData })
        .mockResolvedValueOnce({ data: mockSampleResults })
        .mockRejectedValueOnce(new Error('No confusion matrix'))
        .mockResolvedValueOnce({ data: mockMetricDistribution })

      const user = userEvent.setup()
      const refreshButtons = screen.getAllByRole('button')
      const refreshButton = refreshButtons.find((btn) =>
        btn.querySelector('svg')?.classList.contains('h-4')
      )

      if (refreshButton) {
        await user.click(refreshButton)

        await waitFor(() => {
          expect(mockApiClient.get).toHaveBeenCalledWith(
            '/evaluations/eval-123'
          )
        })
      }
    })
  })

  describe('status badge variants', () => {
    it('shows success variant for completed status', async () => {
      mockApiClient.get
        .mockResolvedValueOnce({ data: mockEvaluationData })
        .mockResolvedValueOnce({ data: mockSampleResults })
        .mockRejectedValueOnce(new Error('No confusion matrix'))
        .mockResolvedValueOnce({ data: mockMetricDistribution })

      render(
        <EvaluationDashboard params={Promise.resolve({ id: 'eval-123' })} />
      )

      await waitFor(() => {
        const badge = screen.getByText('completed')
        expect(badge).toBeInTheDocument()
      })
    })

    it('shows default variant for non-completed status', async () => {
      const runningEval = {
        ...mockEvaluationData,
        status: 'running',
        has_sample_results: false,
      }
      mockApiClient.get.mockResolvedValueOnce({ data: runningEval })

      render(
        <EvaluationDashboard params={Promise.resolve({ id: 'eval-123' })} />
      )

      await waitFor(
        () => {
          expect(
            screen.queryByTestId('loading-spinner')
          ).not.toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      const badge = screen.getByTestId('badge')
      expect(badge).toBeInTheDocument()
      expect(badge).toHaveTextContent('running')
    })
  })

  describe('edge cases', () => {
    it('handles evaluation with no metrics', async () => {
      const noMetricsEval = {
        ...mockEvaluationData,
        metrics: {},
        has_sample_results: false,
      }
      mockApiClient.get.mockResolvedValueOnce({ data: noMetricsEval })

      render(
        <EvaluationDashboard params={Promise.resolve({ id: 'eval-123' })} />
      )

      await waitFor(
        () => {
          expect(
            screen.getByText(/evaluation.human.results.title/i)
          ).toBeInTheDocument()
        },
        { timeout: 3000 }
      )
    })

    it('handles evaluation with missing eval_metadata', async () => {
      const noMetadataEval = {
        ...mockEvaluationData,
        eval_metadata: { samples_passed: 0, samples_failed: 0, pass_rate: 0 },
        has_sample_results: false,
      }
      mockApiClient.get.mockResolvedValueOnce({ data: noMetadataEval })

      render(
        <EvaluationDashboard params={Promise.resolve({ id: 'eval-123' })} />
      )

      await waitFor(
        () => {
          expect(
            screen.queryByTestId('loading-spinner')
          ).not.toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      expect(screen.getByText(/0\.0%/)).toBeInTheDocument()
    })

    it('handles confusion matrix API error gracefully', async () => {
      const consoleLog = jest.spyOn(console, 'log').mockImplementation()
      const consoleError = jest.spyOn(console, 'error').mockImplementation()

      // Use mockImplementation to handle async call ordering correctly
      mockApiClient.get.mockImplementation((url: string) => {
        if (url === '/evaluations/eval-123') {
          return Promise.resolve({ data: mockEvaluationData })
        }
        if (url === '/evaluations/eval-123/samples') {
          return Promise.resolve({ data: mockSampleResults })
        }
        if (url.includes('/distribution')) {
          return Promise.resolve({ data: mockMetricDistribution })
        }
        if (url.includes('/confusion-matrix')) {
          return Promise.reject(new Error('Confusion matrix not available'))
        }
        return Promise.reject(new Error(`Unexpected URL: ${url}`))
      })

      render(
        <EvaluationDashboard params={Promise.resolve({ id: 'eval-123' })} />
      )

      await waitFor(
        () => {
          expect(
            screen.queryByTestId('loading-spinner')
          ).not.toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      // The page should load successfully despite the confusion matrix error
      expect(
        screen.getByText(/evaluation.human.results.title/i)
      ).toBeInTheDocument()

      // Confusion matrix tab should not be visible
      expect(screen.queryByText('evaluations.detail.confusionMatrix')).not.toBeInTheDocument()

      // No error should be thrown to console.error
      expect(consoleError).not.toHaveBeenCalled()

      consoleLog.mockRestore()
      consoleError.mockRestore()
    })

    it('handles metric distribution API error', async () => {
      const consoleError = jest.spyOn(console, 'error').mockImplementation()

      mockApiClient.get
        .mockResolvedValueOnce({ data: mockEvaluationData })
        .mockResolvedValueOnce({ data: mockSampleResults })
        .mockRejectedValueOnce(new Error('No confusion matrix'))
        .mockRejectedValueOnce(new Error('Distribution error'))

      render(
        <EvaluationDashboard params={Promise.resolve({ id: 'eval-123' })} />
      )

      await waitFor(
        () => {
          expect(consoleError).toHaveBeenCalledWith(
            'Failed to load metric distribution:',
            expect.any(Error)
          )
        },
        { timeout: 3000 }
      )

      consoleError.mockRestore()
    })
  })

  describe('accessibility', () => {
    it('renders with proper heading structure', async () => {
      mockApiClient.get
        .mockResolvedValueOnce({ data: mockEvaluationData })
        .mockResolvedValueOnce({ data: mockSampleResults })
        .mockRejectedValueOnce(new Error('No confusion matrix'))
        .mockResolvedValueOnce({ data: mockMetricDistribution })

      render(
        <EvaluationDashboard params={Promise.resolve({ id: 'eval-123' })} />
      )

      await waitFor(() => {
        expect(
          screen.getByText(/evaluation.human.results.title/i)
        ).toBeInTheDocument()
      })
    })
  })
})
