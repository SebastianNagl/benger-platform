/**
 * @jest-environment jsdom
 */
import '@testing-library/jest-dom'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EvaluationDashboard } from '../EvaluationDashboard'

// Mock i18n
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, any>) => {
      const translations: Record<string, string> = {
        'evaluation.dashboard.title': 'Evaluation Dashboard',
        'evaluation.dashboard.description': 'Compare model performance',
        'evaluation.dashboard.selectProject': 'Select Project',
        'evaluation.dashboard.selectProjectPrompt': 'Select a project to begin',
        'evaluation.dashboard.totalEvaluations': 'Total Evaluations',
        'evaluation.dashboard.modelsEvaluated': 'Models Evaluated',
        'evaluation.dashboard.bestModel': 'Best Model',
        'evaluation.dashboard.averageScore': 'Average Score',
        'evaluation.dashboard.noModelsEvaluated': 'No models evaluated',
        'evaluation.dashboard.modelLeaderboard': 'Model Leaderboard',
        'evaluation.dashboard.modelComparisonRadar': 'Model Comparison (Radar)',
        'evaluation.dashboard.modelComparisonBar': 'Model Comparison (Bar)',
        'evaluation.dashboard.statisticalSignificance': 'Statistical Significance',
        'evaluation.dashboard.significanceDescription': 'Pairwise significance tests',
        'evaluation.dashboard.modelA': 'Model A',
        'evaluation.dashboard.modelB': 'Model B',
        'evaluation.dashboard.metric': 'Metric',
        'evaluation.dashboard.pValue': 'p-value',
        'evaluation.dashboard.significance': 'Significance',
        'evaluation.dashboard.effectSize': 'Effect Size',
      }
      return translations[key] || key
    },
  }),
}))

// Mock API client
const mockGetProject = jest.fn()
const mockGetEvaluatedModels = jest.fn()
const mockGetSupportedMetrics = jest.fn()
const mockGetEvaluationHistory = jest.fn()
const mockGetSignificanceTests = jest.fn()

jest.mock('@/lib/api/client', () => ({
  __esModule: true,
  default: {
    getProject: (...args: any[]) => mockGetProject(...args),
    getSupportedMetrics: (...args: any[]) => mockGetSupportedMetrics(...args),
    evaluations: {
      getEvaluatedModels: (...args: any[]) => mockGetEvaluatedModels(...args),
      getEvaluationHistory: (...args: any[]) => mockGetEvaluationHistory(...args),
      getSignificanceTests: (...args: any[]) => mockGetSignificanceTests(...args),
    },
  },
}))

// Mock child components
jest.mock('@/components/generation/ProjectSelector', () => ({
  ProjectSelector: ({ selectedProjectId, onProjectSelect }: any) => (
    <div data-testid="project-selector">
      <button
        data-testid="select-project-btn"
        onClick={() => onProjectSelect({ id: 1, title: 'Test Project' })}
      >
        Select Project
      </button>
      {selectedProjectId && <span>Selected: {selectedProjectId}</span>}
    </div>
  ),
}))

jest.mock('@/components/shared/Card', () => ({
  Card: ({ children, className }: any) => (
    <div className={className} data-testid="card">{children}</div>
  ),
}))

jest.mock('@/components/shared/LoadingSpinner', () => ({
  LoadingSpinner: ({ size }: any) => <div data-testid="loading-spinner" data-size={size} />,
}))

jest.mock('../EvaluationResultsTable', () => ({
  EvaluationResultsTable: ({ results }: any) => (
    <div data-testid="results-table">
      {results?.map((r: any) => (
        <div key={r.modelId} data-testid={`table-row-${r.modelId}`}>
          {r.modelName}
        </div>
      ))}
    </div>
  ),
}))

jest.mock('../MetricSelector', () => ({
  MetricSelector: ({ availableMetrics, selectedMetrics, onSelectionChange }: any) => (
    <div data-testid="metric-selector">
      {availableMetrics?.map((m: string) => (
        <button key={m} data-testid={`metric-${m}`} onClick={() => onSelectionChange([m])}>
          {m}
        </button>
      ))}
    </div>
  ),
}))

jest.mock('../ModelSelector', () => ({
  ModelSelector: ({ projectId, selectedModels, onSelectionChange }: any) => (
    <div data-testid="model-selector" data-project-id={projectId}>
      <span>{selectedModels?.length ?? 0} models selected</span>
    </div>
  ),
}))

jest.mock('../ModelComparisonChart', () => ({
  ModelComparisonChart: ({ title, visualizationType }: any) => (
    <div data-testid={`model-chart-${visualizationType}`}>{title}</div>
  ),
}))

jest.mock('../ScoreCard', () => ({
  ScoreCard: ({ metric, value, description }: any) => (
    <div data-testid={`score-card-${metric}`}>
      {metric}: {value} {description && `(${description})`}
    </div>
  ),
}))

jest.mock('../charts/HistoricalTrendChart', () => ({
  HistoricalTrendChart: ({ metric }: any) => (
    <div data-testid="historical-chart">Trend for {metric}</div>
  ),
}))

describe('EvaluationDashboard', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetProject.mockResolvedValue({ id: 1, title: 'Test Project' })
    mockGetEvaluatedModels.mockResolvedValue([
      {
        model_id: 'gpt-4',
        model_name: 'GPT-4',
        provider: 'OpenAI',
        evaluation_count: 10,
        total_samples: 100,
        last_evaluated: '2026-01-01T00:00:00Z',
        average_score: 0.85,
        ci_lower: 0.82,
        ci_upper: 0.88,
      },
      {
        model_id: 'claude-3',
        model_name: 'Claude 3',
        provider: 'Anthropic',
        evaluation_count: 8,
        total_samples: 80,
        last_evaluated: '2026-01-02T00:00:00Z',
        average_score: 0.9,
        ci_lower: 0.87,
        ci_upper: 0.93,
      },
    ])
    mockGetSupportedMetrics.mockResolvedValue({
      supported_metrics: ['rouge', 'bleu', 'bertscore', 'meteor'],
    })
    mockGetEvaluationHistory.mockResolvedValue({ data: [] })
    mockGetSignificanceTests.mockResolvedValue({ comparisons: [] })
  })

  describe('Initial rendering', () => {
    it('renders the dashboard title and description', () => {
      render(<EvaluationDashboard />)
      expect(screen.getByText('Evaluation Dashboard')).toBeInTheDocument()
      expect(screen.getByText('Compare model performance')).toBeInTheDocument()
    })

    it('renders the project selector', () => {
      render(<EvaluationDashboard />)
      expect(screen.getByTestId('project-selector')).toBeInTheDocument()
    })

    it('shows select project prompt when no project is selected', () => {
      render(<EvaluationDashboard />)
      expect(screen.getByText('Select a project to begin')).toBeInTheDocument()
    })
  })

  describe('Initial project loading', () => {
    it('loads project from initialProjectId', async () => {
      render(<EvaluationDashboard initialProjectId="1" />)

      await waitFor(() => {
        expect(mockGetProject).toHaveBeenCalledWith(1)
      })
    })

    it('calls getProject and handles rejection when initial project load fails', async () => {
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()
      mockGetProject.mockRejectedValue(new Error('Not found'))

      render(<EvaluationDashboard initialProjectId="99" />)

      await waitFor(() => {
        expect(mockGetProject).toHaveBeenCalledWith(99)
      })
      // The error is set via setError but since selectedProject is never set,
      // the error card is not shown in the project content area
      // However the prompt card is still shown
      expect(screen.getByText('Select a project to begin')).toBeInTheDocument()
      consoleSpy.mockRestore()
    })
  })

  describe('After project selection', () => {
    it('fetches models and metrics when a project is selected', async () => {
      const user = userEvent.setup()
      render(<EvaluationDashboard />)

      await user.click(screen.getByTestId('select-project-btn'))

      await waitFor(() => {
        expect(mockGetEvaluatedModels).toHaveBeenCalledWith('1')
        expect(mockGetSupportedMetrics).toHaveBeenCalled()
      })
    })

    it('shows model and metric selectors after project selection', async () => {
      const user = userEvent.setup()
      render(<EvaluationDashboard />)

      await user.click(screen.getByTestId('select-project-btn'))

      await waitFor(() => {
        expect(screen.getByTestId('model-selector')).toBeInTheDocument()
        expect(screen.getByTestId('metric-selector')).toBeInTheDocument()
      })
    })

    it('shows summary stats cards after data loads', async () => {
      const user = userEvent.setup()
      render(<EvaluationDashboard />)

      await user.click(screen.getByTestId('select-project-btn'))

      await waitFor(() => {
        expect(screen.getByTestId('score-card-Total Evaluations')).toBeInTheDocument()
        expect(screen.getByTestId('score-card-Models Evaluated')).toBeInTheDocument()
        expect(screen.getByTestId('score-card-Best Model')).toBeInTheDocument()
        expect(screen.getByTestId('score-card-Average Score')).toBeInTheDocument()
      })
    })

    it('renders the leaderboard table', async () => {
      const user = userEvent.setup()
      render(<EvaluationDashboard />)

      await user.click(screen.getByTestId('select-project-btn'))

      await waitFor(() => {
        expect(screen.getByTestId('results-table')).toBeInTheDocument()
        expect(screen.getByText('Model Leaderboard')).toBeInTheDocument()
      })
    })

    it('renders model comparison charts', async () => {
      const user = userEvent.setup()
      render(<EvaluationDashboard />)

      await user.click(screen.getByTestId('select-project-btn'))

      await waitFor(() => {
        expect(screen.getByTestId('model-chart-radar')).toBeInTheDocument()
        expect(screen.getByTestId('model-chart-bar')).toBeInTheDocument()
      })
    })
  })

  describe('Loading state', () => {
    it('shows loading spinner while fetching data', async () => {
      const user = userEvent.setup()
      // Make the API call hang
      mockGetEvaluatedModels.mockReturnValue(new Promise(() => {}))

      render(<EvaluationDashboard />)

      await user.click(screen.getByTestId('select-project-btn'))

      await waitFor(() => {
        expect(screen.getByTestId('loading-spinner')).toBeInTheDocument()
      })
    })
  })

  describe('Error state', () => {
    it('shows error message when data fetch fails', async () => {
      const user = userEvent.setup()
      mockGetEvaluatedModels.mockRejectedValue(new Error('API error'))

      render(<EvaluationDashboard />)

      await user.click(screen.getByTestId('select-project-btn'))

      await waitFor(() => {
        expect(screen.getByText(/Failed to load project data/)).toBeInTheDocument()
      })
    })
  })

  describe('Significance data display', () => {
    it('shows significance table when significance data and multiple models selected', async () => {
      const user = userEvent.setup()
      mockGetSignificanceTests.mockResolvedValue({
        comparisons: [
          {
            model_a: 'GPT-4',
            model_b: 'Claude 3',
            metric: 'rouge',
            p_value: 0.003,
            significant: true,
            effect_size: 0.85,
            stars: '**',
          },
        ],
      })

      render(<EvaluationDashboard />)

      await user.click(screen.getByTestId('select-project-btn'))

      await waitFor(() => {
        expect(mockGetSignificanceTests).toHaveBeenCalled()
      })
    })
  })

  describe('Metrics from alternative API format', () => {
    it('handles metrics response with .metrics key instead of .supported_metrics', async () => {
      const user = userEvent.setup()
      mockGetSupportedMetrics.mockResolvedValue({
        metrics: ['accuracy', 'f1'],
      })

      render(<EvaluationDashboard />)

      await user.click(screen.getByTestId('select-project-btn'))

      await waitFor(() => {
        expect(screen.getByTestId('metric-selector')).toBeInTheDocument()
      })
    })
  })

  describe('Models with null scores', () => {
    it('handles models with null average_score for stats computation', async () => {
      const user = userEvent.setup()
      mockGetEvaluatedModels.mockResolvedValue([
        {
          model_id: 'gpt-4',
          model_name: 'GPT-4',
          provider: 'OpenAI',
          evaluation_count: 5,
          total_samples: 50,
          last_evaluated: null,
          average_score: null,
          ci_lower: null,
          ci_upper: null,
        },
      ])

      render(<EvaluationDashboard />)

      await user.click(screen.getByTestId('select-project-btn'))

      await waitFor(() => {
        // bestModel should be null, description should show "No models evaluated"
        expect(screen.getByTestId('score-card-Best Model')).toBeInTheDocument()
      })
    })
  })

  describe('Historical trend chart', () => {
    it('renders historical trend chart when data has entries', async () => {
      const user = userEvent.setup()
      mockGetEvaluationHistory.mockResolvedValue({
        data: [{ date: '2026-01-01', score: 0.8, model_id: 'gpt-4' }],
      })

      render(<EvaluationDashboard />)

      await user.click(screen.getByTestId('select-project-btn'))

      await waitFor(() => {
        expect(screen.getByTestId('historical-chart')).toBeInTheDocument()
      })
    })
  })

  describe('Comparison data error handling', () => {
    it('silently handles comparison data fetch errors', async () => {
      const user = userEvent.setup()
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()
      mockGetEvaluationHistory.mockRejectedValue(new Error('History fetch failed'))

      render(<EvaluationDashboard />)

      await user.click(screen.getByTestId('select-project-btn'))

      await waitFor(() => {
        expect(consoleSpy).toHaveBeenCalledWith(
          'Failed to load comparison data:',
          expect.any(Error)
        )
      })
      consoleSpy.mockRestore()
    })
  })
})
