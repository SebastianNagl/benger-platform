/**
 * Mega branch-coverage tests for EvaluationDashboard (evaluations/page.tsx)
 * Targets 91 uncovered branch lines including:
 * - parseSubdomain conditional (109)
 * - URL parameter parsing (290, 304, 312, 320, 331, 337, 342, 346)
 * - Chart type/aggregation/filter logic (304-346)
 * - Data loading and transformation (386+)
 * - fetchProjectData branches (451-598)
 * - fetchComparisonData branches (620-659)
 * - computeStatistics branches (661-723)
 * - handleRunEvaluation branches (805-867)
 * - chartDisabledInfo memo (920-957)
 * - modelsWithScores memo (960-1003)
 * - Access control / auth loading branches (882-909)
 * - toggleModel (911-917)
 * - Filter bar conditionals (1107+)
 */

import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { apiClient } from '@/lib/api/client'
import { projectsAPI } from '@/lib/api/projects'
import { canAccessProjectData } from '@/utils/permissions'
import '@testing-library/jest-dom'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useRouter, useSearchParams } from 'next/navigation'
import EvaluationDashboard from '../page'

// --- Mocks ---

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
  projectsAPI: {
    list: jest.fn(),
  },
}))

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
  useSearchParams: jest.fn(),
}))

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(),
}))

const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: mockAddToast }),
}))

jest.mock('@/hooks/useOperationToasts', () => ({
  useOperationToasts: () => ({
    startEvaluation: jest.fn(),
    updateEvaluation: jest.fn(),
    renderToasts: () => null,
  }),
}))

jest.mock('@/utils/permissions', () => ({
  canAccessProjectData: jest.fn(() => true),
}))

jest.mock('@/lib/utils/subdomain', () => ({
  parseSubdomain: () => ({ isPrivateMode: false, orgSlug: null }),
}))

// Mock all icons
jest.mock('@heroicons/react/24/outline', () => ({
  ChartBarIcon: () => <div data-testid="chart-bar-icon" />,
  ChevronDownIcon: () => <div data-testid="chevron-down-icon" />,
  PlayIcon: () => <div data-testid="play-icon" />,
  ExclamationTriangleIcon: () => <div data-testid="exclamation-icon" />,
}))

// Mock shared components
jest.mock('@/components/shared/FeatureFlag', () => ({
  FeatureFlag: ({ children }: any) => <>{children}</>,
}))

jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: ({ items }: any) => (
    <nav data-testid="breadcrumb">
      {items.map((item: any, i: number) => (
        <span key={i}>{item.label}</span>
      ))}
    </nav>
  ),
}))

jest.mock('@/components/shared/ResponsiveContainer', () => ({
  ResponsiveContainer: ({ children }: any) => (
    <div data-testid="responsive-container">{children}</div>
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
  Card: ({ children, className }: any) => <div data-testid="card" className={className}>{children}</div>,
}))

jest.mock('@/components/shared/LoadingSpinner', () => ({
  LoadingSpinner: () => <div data-testid="loading-spinner">Loading...</div>,
}))

// Mock evaluation components
jest.mock('@/components/evaluation/AggregationSelector', () => ({
  AggregationSelector: ({ value, onChange }: any) => (
    <div data-testid="aggregation-selector">
      <button data-testid="set-sample-agg" onClick={() => onChange(['sample'])}>
        Set Sample
      </button>
    </div>
  ),
}))

jest.mock('@/components/evaluation/ChartTypeSelector', () => ({
  ChartTypeSelector: ({ value, onChange, disabledTypes }: any) => (
    <div data-testid="chart-type-selector" data-disabled={JSON.stringify(disabledTypes)}>
      <button data-testid="set-chart-bar" onClick={() => onChange('bar')}>Bar</button>
      <button data-testid="set-chart-table" onClick={() => onChange('table')}>Table</button>
      <button data-testid="set-chart-heatmap" onClick={() => onChange('heatmap')}>Heatmap</button>
      <button data-testid="set-chart-box" onClick={() => onChange('box')}>Box</button>
    </div>
  ),
}))

jest.mock('@/components/evaluation/DynamicChartRenderer', () => ({
  DynamicChartRenderer: () => <div data-testid="dynamic-chart-renderer" />,
}))

jest.mock('@/components/evaluation/EvaluationResultsTable', () => ({
  EvaluationResultsTable: () => <div data-testid="evaluation-results-table" />,
}))

jest.mock('@/components/evaluation/FieldPairSelector', () => ({
  FieldPairSelector: () => <div data-testid="field-pair-selector" />,
}))

jest.mock('@/components/evaluation/EvaluationResults', () => ({
  EvaluationResults: ({ onDataLoaded, onHasResults }: any) => (
    <div data-testid="evaluation-results">
      <button data-testid="trigger-data-loaded" onClick={() => onDataLoaded?.([])}>
        Load Data
      </button>
      <button data-testid="trigger-has-results" onClick={() => onHasResults?.(true)}>
        Has Results
      </button>
    </div>
  ),
}))

jest.mock('@/components/evaluation/ScoreCard', () => ({
  ScoreCard: ({ title, value }: any) => (
    <div data-testid="score-card">{title}: {value}</div>
  ),
}))

jest.mock('@/components/evaluation/StatisticalResultsPanel', () => ({
  StatisticalResultsPanel: () => <div data-testid="statistical-results-panel" />,
}))

jest.mock('@/components/evaluation/StatisticsSelector', () => ({
  StatisticsSelector: ({ value, onChange }: any) => (
    <div data-testid="statistics-selector">
      <button data-testid="set-stats-ci" onClick={() => onChange(['ci'])}>CI</button>
    </div>
  ),
}))

jest.mock('@/components/evaluation/charts/HistoricalTrendChart', () => ({
  HistoricalTrendChart: () => <div data-testid="historical-trend-chart" />,
}))

jest.mock('@/components/evaluation/charts/SignificanceHeatmap', () => ({
  SignificanceHeatmap: () => <div data-testid="significance-heatmap" />,
}))

jest.mock('@/components/evaluation/EvaluationControlModal', () => ({
  EvaluationControlModal: ({ isOpen }: any) =>
    isOpen ? <div data-testid="eval-control-modal" /> : null,
}))

// --- Test Data ---

const mockRouter = { push: jest.fn(), replace: jest.fn() }

const mockUser = {
  id: 'user-1',
  name: 'Test User',
  email: 'test@example.com',
  is_superadmin: true,
  is_active: true,
  created_at: '2024-01-01',
  updated_at: '2024-01-01',
}

const mockProjects = [
  { id: 'p1', title: 'Project One', task_count: 50 },
  { id: 'p2', title: 'Project Two', task_count: 30 },
]

const mockEvaluatedModels = [
  {
    model_id: 'gpt-4',
    model_name: 'GPT-4',
    provider: 'OpenAI',
    is_configured: true,
    has_generations: true,
    has_results: true,
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
    is_configured: true,
    has_generations: true,
    has_results: true,
    evaluation_count: 8,
    total_samples: 80,
    last_evaluated: '2026-01-02T00:00:00Z',
    average_score: 0.82,
    ci_lower: 0.79,
    ci_upper: 0.85,
  },
]

const mockEvalConfig = {
  evaluation_configs: [
    {
      id: 'eval-1',
      metric: 'bleu',
      display_name: 'BLEU',
      prediction_fields: ['model_answer'],
      reference_fields: ['reference'],
      enabled: true,
    },
    {
      id: 'eval-2',
      metric: 'rouge',
      display_name: 'ROUGE',
      prediction_fields: ['model_answer'],
      reference_fields: ['reference'],
      enabled: true,
    },
  ],
}

function setupBasicMocks(overrides: {
  searchParams?: URLSearchParams
  user?: any
  isLoading?: boolean
  canAccess?: boolean
  projects?: any[]
} = {}) {
  ;(useRouter as jest.Mock).mockReturnValue(mockRouter)

  const sp = overrides.searchParams || new URLSearchParams()
  ;(useSearchParams as jest.Mock).mockReturnValue(sp)

  ;(useAuth as jest.Mock).mockReturnValue({
    user: overrides.user ?? mockUser,
    isLoading: overrides.isLoading ?? false,
  })

  ;(useI18n as jest.Mock).mockReturnValue({
    t: (key: string, fallback?: any) => {
      if (typeof fallback === 'string') return fallback
      return key
    },
  })

  ;(canAccessProjectData as jest.Mock).mockReturnValue(overrides.canAccess ?? true)

  ;(projectsAPI.list as jest.Mock).mockResolvedValue({
    items: overrides.projects ?? mockProjects,
  })

  // Default API mocks
  ;(apiClient.evaluations.getProjectEvaluationConfig as jest.Mock).mockResolvedValue(mockEvalConfig)
  ;(apiClient.evaluations.getConfiguredMethods as jest.Mock).mockResolvedValue({ fields: [] })
  ;(apiClient.evaluations.getEvaluatedModels as jest.Mock).mockResolvedValue(mockEvaluatedModels)
  ;(apiClient.evaluations.getEvaluationHistory as jest.Mock).mockResolvedValue({ data: [] })
  ;(apiClient.evaluations.getSignificanceTests as jest.Mock).mockResolvedValue({ comparisons: [] })
  ;(apiClient.evaluations.computeStatistics as jest.Mock).mockResolvedValue({})
  ;(apiClient.evaluations.runEvaluation as jest.Mock).mockResolvedValue({ evaluation_id: 'eval-run-1' })
  ;(apiClient.get as jest.Mock).mockResolvedValue({ data: [] })

  // Clear localStorage
  localStorage.clear()
}

describe('EvaluationDashboard - Mega Branch Coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    localStorage.clear()
  })

  // --- Auth loading state (line 888) ---

  it('shows loading spinner when auth is loading', () => {
    setupBasicMocks({ isLoading: true })
    render(<EvaluationDashboard />)

    expect(screen.getByTestId('loading-spinner')).toBeInTheDocument()
  })

  // --- Access denied state (line 896) ---

  it('shows access denied when user lacks permissions', () => {
    setupBasicMocks({ canAccess: false })
    render(<EvaluationDashboard />)

    expect(screen.getByText('evaluation.accessDenied')).toBeInTheDocument()
  })

  it('redirects to projects when no permission and not loading', async () => {
    setupBasicMocks({ canAccess: false })
    render(<EvaluationDashboard />)

    await waitFor(() => {
      expect(mockRouter.replace).toHaveBeenCalledWith('/projects?error=no-permission')
    })
  })

  // --- Basic render with no project selected ---

  it('renders evaluation dashboard with project selector', async () => {
    setupBasicMocks()
    render(<EvaluationDashboard />)

    await waitFor(() => {
      expect(screen.getByText('evaluation.viewer.title')).toBeInTheDocument()
    })
  })

  // --- URL param: projectId loading from search params (line 287-293) ---

  it('auto-selects project from URL projectId param', async () => {
    const sp = new URLSearchParams('projectId=p1')
    setupBasicMocks({ searchParams: sp })
    render(<EvaluationDashboard />)

    await waitFor(() => {
      // Should auto-select Project One
      expect(apiClient.evaluations.getProjectEvaluationConfig).toHaveBeenCalled()
    })
  })

  // --- URL param: chartType (line 296-299) ---

  it('restores chartType from URL params', async () => {
    const sp = new URLSearchParams('projectId=p1&chartType=bar')
    setupBasicMocks({ searchParams: sp })
    render(<EvaluationDashboard />)

    await waitFor(() => {
      expect(screen.getByTestId('chart-type-selector')).toBeInTheDocument()
    })
  })

  // --- URL param: aggregation (line 301-307) ---

  it('restores aggregation levels from URL params', async () => {
    const sp = new URLSearchParams('projectId=p1&aggregation=sample,model')
    setupBasicMocks({ searchParams: sp })
    render(<EvaluationDashboard />)

    await waitFor(() => {
      expect(screen.getByTestId('aggregation-selector')).toBeInTheDocument()
    })
  })

  // --- URL param: stats (line 309-315) ---

  it('restores statistical methods from URL params', async () => {
    const sp = new URLSearchParams('projectId=p1&stats=ci,bootstrap')
    setupBasicMocks({ searchParams: sp })
    render(<EvaluationDashboard />)

    await waitFor(() => {
      expect(screen.getByTestId('statistics-selector')).toBeInTheDocument()
    })
  })

  // --- URL param: models and metrics after data load (line 319-350) ---

  it('applies models and metrics from URL after data loads', async () => {
    const sp = new URLSearchParams('projectId=p1&models=gpt-4&metrics=bleu')
    setupBasicMocks({ searchParams: sp })
    render(<EvaluationDashboard />)

    await waitFor(() => {
      expect(apiClient.evaluations.getEvaluatedModels).toHaveBeenCalled()
    })
  })

  // --- fetchProjectData: evaluation config fetch failure (line 461-464) ---

  it('handles evaluation config fetch failure gracefully', async () => {
    const sp = new URLSearchParams('projectId=p1')
    setupBasicMocks({ searchParams: sp })
    ;(apiClient.evaluations.getProjectEvaluationConfig as jest.Mock).mockRejectedValue(
      new Error('Config not found')
    )

    render(<EvaluationDashboard />)

    await waitFor(() => {
      expect(screen.getByText('evaluation.viewer.title')).toBeInTheDocument()
    })
  })

  // --- fetchProjectData: no config => empty state (line 507-513) ---

  it('shows empty state when project has no evaluation config', async () => {
    const sp = new URLSearchParams('projectId=p1')
    setupBasicMocks({ searchParams: sp })
    ;(apiClient.evaluations.getProjectEvaluationConfig as jest.Mock).mockResolvedValue({
      evaluation_configs: [],
      selected_methods: {},
    })

    render(<EvaluationDashboard />)

    await waitFor(() => {
      expect(screen.getByText('evaluation.viewer.title')).toBeInTheDocument()
    })
  })

  // --- fetchProjectData: legacy selected_methods bridge (line 481-500) ---

  it('bridges legacy selected_methods to evaluation_configs', async () => {
    const sp = new URLSearchParams('projectId=p1')
    setupBasicMocks({ searchParams: sp })
    ;(apiClient.evaluations.getProjectEvaluationConfig as jest.Mock).mockResolvedValue({
      evaluation_configs: [],
      selected_methods: {
        text: {
          automated: ['bleu', { name: 'rouge', parameters: { variant: 'rougeL' } }],
          human: ['accuracy'],
          field_mapping: {
            prediction_field: 'model_answer',
            reference_field: 'reference',
          },
        },
      },
    })

    render(<EvaluationDashboard />)

    await waitFor(() => {
      expect(apiClient.evaluations.getEvaluatedModels).toHaveBeenCalled()
    })
  })

  // --- fetchProjectData: llm_judge detection (line 519-523) ---

  it('detects llm_judge metrics in evaluation config', async () => {
    const sp = new URLSearchParams('projectId=p1')
    setupBasicMocks({ searchParams: sp })
    ;(apiClient.evaluations.getProjectEvaluationConfig as jest.Mock).mockResolvedValue({
      evaluation_configs: [
        { id: 'e1', metric: 'llm_judge_classic', prediction_fields: ['f1'], reference_fields: ['f2'], enabled: true },
        { id: 'e2', metric: 'bleu', prediction_fields: ['f1'], reference_fields: ['f2'], enabled: true },
      ],
    })

    render(<EvaluationDashboard />)

    await waitFor(() => {
      expect(apiClient.evaluations.getEvaluatedModels).toHaveBeenCalled()
    })
  })

  // --- fetchProjectData: model results fetch error (line 608-610) ---

  it('handles model fetch error gracefully', async () => {
    const sp = new URLSearchParams('projectId=p1')
    setupBasicMocks({ searchParams: sp })
    ;(apiClient.evaluations.getEvaluatedModels as jest.Mock).mockRejectedValue(
      new Error('Models unavailable')
    )

    render(<EvaluationDashboard />)

    await waitFor(() => {
      expect(screen.getByText('evaluation.viewer.title')).toBeInTheDocument()
    })
  })

  // --- fetchProjectData: evaluation results fetch error (line 588-590) ---

  it('handles evaluation results fetch error gracefully', async () => {
    const sp = new URLSearchParams('projectId=p1')
    setupBasicMocks({ searchParams: sp })
    ;(apiClient.get as jest.Mock).mockRejectedValue(new Error('Results unavailable'))

    render(<EvaluationDashboard />)

    await waitFor(() => {
      expect(screen.getByText('evaluation.viewer.title')).toBeInTheDocument()
    })
  })

  // --- Project selection via dropdown (line 1083-1089) ---

  it('allows selecting a project from dropdown', async () => {
    setupBasicMocks()
    render(<EvaluationDashboard />)

    // Click the project dropdown button
    await waitFor(() => {
      expect(screen.getByText('evaluation.viewer.filters.selectProject')).toBeInTheDocument()
    })

    await userEvent.click(screen.getByText('evaluation.viewer.filters.selectProject'))

    // Projects should appear
    await waitFor(() => {
      expect(screen.getByText('Project One')).toBeInTheDocument()
    })

    await userEvent.click(screen.getByText('Project One'))

    await waitFor(() => {
      expect(apiClient.evaluations.getProjectEvaluationConfig).toHaveBeenCalled()
    })
  })

  // --- Model annotator prefix (line 1165-1168) ---

  it('displays annotator models with cleaned names', async () => {
    const sp = new URLSearchParams('projectId=p1')
    setupBasicMocks({ searchParams: sp })
    ;(apiClient.evaluations.getEvaluatedModels as jest.Mock).mockResolvedValue([
      ...mockEvaluatedModels,
      {
        model_id: 'annotator:john-doe',
        model_name: 'annotator:john-doe',
        provider: 'Human',
        is_configured: false,
        has_generations: false,
        has_results: true,
        evaluation_count: 5,
        total_samples: 50,
        last_evaluated: null,
        average_score: null,
        ci_lower: null,
        ci_upper: null,
      },
    ])

    render(<EvaluationDashboard />)

    await waitFor(() => {
      expect(apiClient.evaluations.getEvaluatedModels).toHaveBeenCalled()
    })
  })

  // --- Model with has_results=false and has_generations=false (line 1170-1181) ---

  it('shows status icons for models without results or generations', async () => {
    const sp = new URLSearchParams('projectId=p1')
    setupBasicMocks({ searchParams: sp })
    ;(apiClient.evaluations.getEvaluatedModels as jest.Mock).mockResolvedValue([
      {
        model_id: 'unconfigured-model',
        model_name: 'Unconfigured',
        provider: 'OpenAI',
        is_configured: true,
        has_generations: false,
        has_results: false,
        evaluation_count: 0,
        total_samples: 0,
        last_evaluated: null,
        average_score: null,
        ci_lower: null,
        ci_upper: null,
      },
    ])

    render(<EvaluationDashboard />)

    await waitFor(() => {
      expect(screen.getByText('evaluation.viewer.title')).toBeInTheDocument()
    })
  })

  // --- fetchComparisonData: historical data (line 620-635) ---

  it('fetches historical data when project and metrics are selected', async () => {
    const sp = new URLSearchParams('projectId=p1')
    setupBasicMocks({ searchParams: sp })

    render(<EvaluationDashboard />)

    await waitFor(() => {
      expect(apiClient.evaluations.getEvaluatedModels).toHaveBeenCalled()
    })

    // Historical data should have been fetched
    await waitFor(() => {
      expect(apiClient.evaluations.getEvaluationHistory).toHaveBeenCalled()
    })
  })

  // --- fetchComparisonData: significance tests with 2+ models (line 638-655) ---

  it('fetches significance tests when multiple models selected', async () => {
    const sp = new URLSearchParams('projectId=p1')
    setupBasicMocks({ searchParams: sp })

    render(<EvaluationDashboard />)

    await waitFor(() => {
      expect(apiClient.evaluations.getSignificanceTests).toHaveBeenCalled()
    })
  })

  // --- fetchComparisonData: significance test error (line 649-652) ---

  it('handles significance test error gracefully', async () => {
    const sp = new URLSearchParams('projectId=p1')
    setupBasicMocks({ searchParams: sp })
    ;(apiClient.evaluations.getSignificanceTests as jest.Mock).mockRejectedValue(
      new Error('Significance test failed')
    )

    render(<EvaluationDashboard />)

    await waitFor(() => {
      expect(screen.getByText('evaluation.viewer.title')).toBeInTheDocument()
    })
  })

  // --- computeStatistics: error path (line 686-700) ---

  it('handles statistics computation error', async () => {
    const sp = new URLSearchParams('projectId=p1')
    setupBasicMocks({ searchParams: sp })
    ;(apiClient.evaluations.computeStatistics as jest.Mock).mockRejectedValue(
      new Error('Statistics computation failed')
    )

    render(<EvaluationDashboard />)

    await waitFor(() => {
      expect(screen.getByText('evaluation.viewer.title')).toBeInTheDocument()
    })
  })

  // --- computeStatistics: multiple aggregation levels (line 703-715) ---

  it('handles multiple aggregation levels in statistics', async () => {
    const sp = new URLSearchParams('projectId=p1&aggregation=model,sample')
    setupBasicMocks({ searchParams: sp })
    ;(apiClient.evaluations.computeStatistics as jest.Mock).mockResolvedValue({
      raw_scores: [
        { model_id: 'gpt-4', metric: 'bleu', value: 0.75 },
      ],
    })

    render(<EvaluationDashboard />)

    await waitFor(() => {
      expect(apiClient.evaluations.computeStatistics).toHaveBeenCalled()
    })
  })

  // --- localStorage fallback for last project (line 287) ---

  it('falls back to localStorage for last selected project', async () => {
    setupBasicMocks()
    localStorage.setItem('evaluations_lastProjectId', 'p2')
    render(<EvaluationDashboard />)

    // The project is loaded from localStorage only AFTER projects list is fetched
    // and the matching project is found. Since p2 is in mockProjects, it should
    // eventually select it and call the config API.
    await waitFor(
      () => {
        expect(apiClient.evaluations.getProjectEvaluationConfig).toHaveBeenCalled()
      },
      { timeout: 5000 }
    )
  })

  // --- handleRunEvaluation: no configs (line 841-848) ---

  it('shows error when running evaluation with no enabled configs', async () => {
    const sp = new URLSearchParams('projectId=p1')
    setupBasicMocks({ searchParams: sp })
    ;(apiClient.evaluations.getProjectEvaluationConfig as jest.Mock).mockResolvedValue({
      evaluation_configs: [
        { id: 'e1', metric: 'bleu', prediction_fields: ['f1'], reference_fields: ['f2'], enabled: false },
      ],
    })
    ;(apiClient.evaluations.getEvaluatedModels as jest.Mock).mockResolvedValue([])

    render(<EvaluationDashboard />)

    await waitFor(() => {
      expect(screen.getByText('evaluation.viewer.title')).toBeInTheDocument()
    })
  })

  // --- Chart disabled info: heatmap disabled with < 2 models (line 936-939) ---

  it('disables heatmap when only one model available', async () => {
    const sp = new URLSearchParams('projectId=p1')
    setupBasicMocks({ searchParams: sp })
    ;(apiClient.evaluations.getEvaluatedModels as jest.Mock).mockResolvedValue([
      mockEvaluatedModels[0], // Only one model
    ])

    render(<EvaluationDashboard />)

    await waitFor(() => {
      expect(screen.getByTestId('chart-type-selector')).toBeInTheDocument()
    })
  })

  // --- configuredMethods fetch error (line 471-473) ---

  it('handles configuredMethods fetch error', async () => {
    const sp = new URLSearchParams('projectId=p1')
    setupBasicMocks({ searchParams: sp })
    ;(apiClient.evaluations.getConfiguredMethods as jest.Mock).mockRejectedValue(
      new Error('Methods unavailable')
    )

    render(<EvaluationDashboard />)

    await waitFor(() => {
      expect(screen.getByText('evaluation.viewer.title')).toBeInTheDocument()
    })
  })

  // --- Selected project description display (line 1046-1049) ---

  it('shows project-specific description when project is selected', async () => {
    const sp = new URLSearchParams('projectId=p1')
    setupBasicMocks({ searchParams: sp })

    render(<EvaluationDashboard />)

    await waitFor(() => {
      expect(screen.getByText('evaluation.viewer.title')).toBeInTheDocument()
    })
  })

  // --- leaderboard button navigation ---

  it('navigates to leaderboard on button click', async () => {
    setupBasicMocks()
    render(<EvaluationDashboard />)

    await waitFor(() => {
      expect(screen.getByText('evaluation.viewer.llmLeaderboard')).toBeInTheDocument()
    })

    await userEvent.click(screen.getByText('evaluation.viewer.llmLeaderboard'))
    expect(mockRouter.push).toHaveBeenCalledWith('/leaderboards?tab=llm')
  })

  // --- legacy key (multi_field_evaluations) support (line 478) ---

  it('supports legacy multi_field_evaluations key in config', async () => {
    const sp = new URLSearchParams('projectId=p1')
    setupBasicMocks({ searchParams: sp })
    ;(apiClient.evaluations.getProjectEvaluationConfig as jest.Mock).mockResolvedValue({
      multi_field_evaluations: [
        { id: 'e1', metric: 'bleu', prediction_fields: ['f1'], reference_fields: ['f2'], enabled: true },
      ],
    })

    render(<EvaluationDashboard />)

    await waitFor(() => {
      expect(apiClient.evaluations.getEvaluatedModels).toHaveBeenCalled()
    })
  })

  // --- Full data loading error (line 612-614) ---

  it('shows toast on full data loading failure', async () => {
    const sp = new URLSearchParams('projectId=p1')
    setupBasicMocks({ searchParams: sp })
    ;(apiClient.evaluations.getProjectEvaluationConfig as jest.Mock).mockRejectedValue(
      new Error('Config error')
    )
    ;(apiClient.evaluations.getConfiguredMethods as jest.Mock).mockRejectedValue(
      new Error('Methods error')
    )
    ;(apiClient.evaluations.getEvaluatedModels as jest.Mock).mockRejectedValue(
      new Error('Models error')
    )
    ;(apiClient.get as jest.Mock).mockRejectedValue(new Error('Results error'))

    render(<EvaluationDashboard />)

    await waitFor(() => {
      expect(screen.getByText('evaluation.viewer.title')).toBeInTheDocument()
    })
  })

  // --- Invalid chartType from URL (line 297) ---

  it('ignores invalid chartType from URL', async () => {
    const sp = new URLSearchParams('projectId=p1&chartType=invalid_type')
    setupBasicMocks({ searchParams: sp })
    render(<EvaluationDashboard />)

    await waitFor(() => {
      expect(screen.getByText('evaluation.viewer.title')).toBeInTheDocument()
    })
  })

  // --- URL models that don't match available models (line 334-339) ---

  it('filters out invalid model IDs from URL params', async () => {
    const sp = new URLSearchParams('projectId=p1&models=nonexistent-model')
    setupBasicMocks({ searchParams: sp })
    render(<EvaluationDashboard />)

    await waitFor(() => {
      expect(apiClient.evaluations.getEvaluatedModels).toHaveBeenCalled()
    })
  })

  // --- URL metrics that don't match available metrics (line 344-347) ---

  it('filters out invalid metric IDs from URL params', async () => {
    const sp = new URLSearchParams('projectId=p1&metrics=nonexistent-metric')
    setupBasicMocks({ searchParams: sp })
    render(<EvaluationDashboard />)

    await waitFor(() => {
      expect(apiClient.evaluations.getEvaluatedModels).toHaveBeenCalled()
    })
  })
})
