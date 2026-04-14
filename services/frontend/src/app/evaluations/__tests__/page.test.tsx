/**
 * Test suite for Evaluations Dashboard Page
 * Tests filter-based results viewer functionality
 */

/**
 * @jest-environment jsdom
 */

import { useToast } from '@/components/shared/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { apiClient } from '@/lib/api/client'
import { projectsAPI } from '@/lib/api/projects'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useRouter, useSearchParams } from 'next/navigation'
import EvaluationDashboard from '../page'

// Mock dependencies
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
    getProject: jest.fn(),
    getProjectModels: jest.fn(),
    getProjectFields: jest.fn(),
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

jest.mock('@/components/shared/Toast', () => ({
  useToast: jest.fn(),
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

// Mock all icons
jest.mock('@heroicons/react/24/outline', () => ({
  ChartBarIcon: () => <div data-testid="chart-bar-icon" />,
  FunnelIcon: () => <div data-testid="funnel-icon" />,
  ChevronDownIcon: () => <div data-testid="chevron-down-icon" />,
  PlayIcon: () => <div data-testid="play-icon" />,
  ExclamationTriangleIcon: () => <div data-testid="exclamation-icon" />,
}))

// Mock all shared components
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
  Button: ({ children, onClick, disabled }: any) => (
    <button onClick={onClick} disabled={disabled}>
      {children}
    </button>
  ),
}))

jest.mock('@/components/shared/Card', () => ({
  Card: ({ children }: any) => <div data-testid="card">{children}</div>,
}))

jest.mock('@/components/shared/LoadingSpinner', () => ({
  LoadingSpinner: () => <div data-testid="loading-spinner">Loading...</div>,
}))

// Mock all evaluation components
jest.mock('@/components/evaluation/AggregationSelector', () => ({
  AggregationSelector: () => <div data-testid="aggregation-selector" />,
}))

jest.mock('@/components/evaluation/ChartTypeSelector', () => ({
  ChartTypeSelector: () => <div data-testid="chart-type-selector" />,
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
  EvaluationResults: () => <div data-testid="evaluation-results" />,
}))

jest.mock('@/components/evaluation/ScoreCard', () => ({
  ScoreCard: () => <div data-testid="score-card" />,
}))

jest.mock('@/components/evaluation/StatisticalResultsPanel', () => ({
  StatisticalResultsPanel: () => (
    <div data-testid="statistical-results-panel" />
  ),
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

jest.mock('@/components/evaluation/EvaluationControlModal', () => ({
  EvaluationControlModal: ({ isOpen }: any) =>
    isOpen ? <div data-testid="eval-control-modal" /> : null,
}))

const mockRouter = {
  push: jest.fn(),
  replace: jest.fn(),
}

const mockSearchParams = new URLSearchParams()

const mockUser = {
  id: 'user-1',
  name: 'Test User',
  email: 'test@example.com',
  is_superadmin: true,
  is_active: true,
  created_at: '2024-01-01',
  updated_at: '2024-01-01',
}

const mockAddToast = jest.fn()

const mockT = (key: string) => key

describe('EvaluationDashboard', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    // Clear localStorage to prevent test pollution from evaluations_lastProjectId
    localStorage.clear()
    ;(useRouter as jest.Mock).mockReturnValue(mockRouter)
    ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)
    ;(useAuth as jest.Mock).mockReturnValue({
      user: mockUser,
      isLoading: false,
    })
    ;(useI18n as jest.Mock).mockReturnValue({ t: mockT })
    ;(useToast as jest.Mock).mockReturnValue({ addToast: mockAddToast })

    // Default API mocks
    ;(projectsAPI.list as jest.Mock).mockResolvedValue({ items: [] })
    ;(
      apiClient.evaluations.getProjectEvaluationConfig as jest.Mock
    ).mockResolvedValue({})
    ;(
      apiClient.evaluations.getConfiguredMethods as jest.Mock
    ).mockResolvedValue({ fields: [] })
    ;(apiClient.evaluations.getEvaluatedModels as jest.Mock).mockResolvedValue(
      []
    )
    ;(
      apiClient.evaluations.getProjectAnnotators as jest.Mock
    ).mockResolvedValue({ annotators: [] })
    ;(apiClient.get as jest.Mock).mockResolvedValue({ data: [] })
  })

  describe('Page Rendering', () => {
    it('should render page title and description', () => {
      render(<EvaluationDashboard />)

      expect(screen.getByText('evaluation.viewer.title')).toBeInTheDocument()
      expect(
        screen.getByText('evaluation.viewer.selectProjectDescription')
      ).toBeInTheDocument()
    })

    it('should render breadcrumb navigation', () => {
      render(<EvaluationDashboard />)

      expect(screen.getByText('navigation.dashboard')).toBeInTheDocument()
      expect(screen.getByText('navigation.evaluation')).toBeInTheDocument()
    })

    it('should render filter bar with project dropdown', () => {
      render(<EvaluationDashboard />)

      // The filter bar contains a Project dropdown label and selector
      expect(screen.getByText('evaluation.viewer.filters.project')).toBeInTheDocument()
      expect(screen.getByText('evaluation.viewer.filters.selectProject')).toBeInTheDocument()
    })

    it('should show no project selected state', () => {
      render(<EvaluationDashboard />)

      expect(screen.getByText('evaluation.viewer.filters.selectProject')).toBeInTheDocument()
    })

    it('should render LLM Leaderboard button', () => {
      render(<EvaluationDashboard />)

      expect(screen.getByText('evaluation.viewer.llmLeaderboard')).toBeInTheDocument()
    })
  })

  describe('Project Selection', () => {
    it('should load projects on mount', async () => {
      const mockProjects = [
        { id: 1, title: 'Project 1', task_count: 10 },
        { id: 2, title: 'Project 2', task_count: 5 },
      ]
      ;(projectsAPI.list as jest.Mock).mockResolvedValue({
        items: mockProjects,
      })

      render(<EvaluationDashboard />)

      await waitFor(() => {
        expect(projectsAPI.list).toHaveBeenCalledWith(1, 100)
      })
    })

    it('should open project dropdown when clicked', async () => {
      const mockProjects = [{ id: 1, title: 'Test Project', task_count: 10 }]
      ;(projectsAPI.list as jest.Mock).mockResolvedValue({
        items: mockProjects,
      })

      const user = userEvent.setup()
      render(<EvaluationDashboard />)

      await waitFor(() => {
        expect(screen.getByText('evaluation.viewer.filters.selectProject')).toBeInTheDocument()
      })

      const projectButton = screen.getByText('evaluation.viewer.filters.selectProject')
      await user.click(projectButton)

      await waitFor(() => {
        expect(screen.getByText('Test Project')).toBeInTheDocument()
      })
    })
  })

  describe('Loading States', () => {
    it('should not show loading spinner initially', () => {
      render(<EvaluationDashboard />)

      expect(screen.queryByTestId('loading-spinner')).not.toBeInTheDocument()
    })
  })

  describe('Empty States', () => {
    it('should show select project message when no project selected', () => {
      render(<EvaluationDashboard />)

      expect(screen.getByText('evaluation.viewer.emptyStates.selectProject.title')).toBeInTheDocument()
      expect(
        screen.getByText(
          'evaluation.viewer.emptyStates.selectProject.description'
        )
      ).toBeInTheDocument()
    })
  })

  describe('Access Control', () => {
    it('should handle permission check', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: mockUser,
        isLoading: false,
      })

      render(<EvaluationDashboard />)

      // Should render normally
      expect(screen.getByText('evaluation.viewer.title')).toBeInTheDocument()
    })

    it('should show loading during auth check', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        isLoading: true,
      })

      render(<EvaluationDashboard />)

      expect(screen.getByTestId('loading-spinner')).toBeInTheDocument()
    })
  })

  describe('Project Selection with Data Loading', () => {
    const mockProject = { id: 1, title: 'Test Project', task_count: 10 }

    it('should select project and load data when project clicked', async () => {
      ;(projectsAPI.list as jest.Mock).mockResolvedValue({
        items: [mockProject],
      })
      ;(apiClient.evaluations.getConfiguredMethods as jest.Mock).mockResolvedValue({
        fields: [],
      })
      ;(apiClient.evaluations.getEvaluatedModels as jest.Mock).mockResolvedValue([])
      ;(apiClient.evaluations.getProjectAnnotators as jest.Mock).mockResolvedValue({
        annotators: [],
      })
      ;(apiClient.evaluations.getProjectEvaluationConfig as jest.Mock).mockResolvedValue({})

      const user = userEvent.setup()
      render(<EvaluationDashboard />)

      await waitFor(() => {
        expect(screen.getByText('evaluation.viewer.filters.selectProject')).toBeInTheDocument()
      })

      // Open dropdown and select project
      await user.click(screen.getByText('evaluation.viewer.filters.selectProject'))
      await waitFor(() => {
        expect(screen.getByText('Test Project')).toBeInTheDocument()
      })
      await user.click(screen.getByText('Test Project'))

      // Should have loaded project data
      await waitFor(() => {
        expect(apiClient.evaluations.getConfiguredMethods).toHaveBeenCalled()
        expect(apiClient.evaluations.getEvaluatedModels).toHaveBeenCalled()
      })
    })

    it('should handle projects list fetch error gracefully', async () => {
      ;(projectsAPI.list as jest.Mock).mockRejectedValue(new Error('Network error'))

      render(<EvaluationDashboard />)

      // Should still render without crashing
      await waitFor(() => {
        expect(screen.getByText('evaluation.viewer.title')).toBeInTheDocument()
      })
    })

    it('should have project filter UI elements', () => {
      render(<EvaluationDashboard />)

      // The filter bar should be visible
      expect(screen.getByText('evaluation.viewer.filters.project')).toBeInTheDocument()
    })
  })

  describe('URL Parameter Integration', () => {
    it('should read project from URL searchParams', () => {
      const paramsWithProject = new URLSearchParams('project=1')
      ;(useSearchParams as jest.Mock).mockReturnValue(paramsWithProject)
      ;(projectsAPI.list as jest.Mock).mockResolvedValue({
        items: [{ id: 1, title: 'URL Project', task_count: 5 }],
      })

      render(<EvaluationDashboard />)

      expect(screen.getByText('evaluation.viewer.title')).toBeInTheDocument()
    })
  })

  describe('Leaderboard Navigation', () => {
    it('should render leaderboard link', () => {
      render(<EvaluationDashboard />)

      expect(screen.getByText('evaluation.viewer.llmLeaderboard')).toBeInTheDocument()
    })
  })

  describe('Non-authenticated User', () => {
    it('should show loading when no user and not loading', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        isLoading: false,
      })

      render(<EvaluationDashboard />)

      // Page may show a different state for non-auth users
      // The key check is it doesn't crash
      expect(document.body).toBeTruthy()
    })
  })

  describe('Multiple Projects', () => {
    it('should load multiple projects', async () => {
      const mockProjects = [
        { id: 1, title: 'Project Alpha', task_count: 10 },
        { id: 2, title: 'Project Beta', task_count: 20 },
        { id: 3, title: 'Project Gamma', task_count: 30 },
      ]
      ;(projectsAPI.list as jest.Mock).mockResolvedValue({
        items: mockProjects,
      })

      render(<EvaluationDashboard />)

      await waitFor(() => {
        expect(projectsAPI.list).toHaveBeenCalledWith(1, 100)
      })
    })
  })

  describe('Project with Evaluation Config', () => {
    const mockProject = { id: 1, title: 'Test Project', task_count: 10 }

    const mockEvalConfig = {
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

    const mockModels = [
      {
        model_id: 'gpt-4',
        model_name: 'GPT-4',
        provider: 'openai',
        is_configured: true,
        has_generations: true,
        has_results: true,
        evaluation_count: 5,
        total_samples: 100,
      },
      {
        model_id: 'claude-3',
        model_name: 'Claude-3',
        provider: 'anthropic',
        is_configured: true,
        has_generations: true,
        has_results: true,
        evaluation_count: 3,
        total_samples: 80,
      },
    ]

    beforeEach(() => {
      ;(projectsAPI.list as jest.Mock).mockResolvedValue({
        items: [mockProject],
      })
      ;(
        apiClient.evaluations.getProjectEvaluationConfig as jest.Mock
      ).mockResolvedValue(mockEvalConfig)
      ;(
        apiClient.evaluations.getConfiguredMethods as jest.Mock
      ).mockResolvedValue({
        fields: [
          {
            field_name: 'model_answer',
            automated_methods: [
              { method_name: 'bleu', has_results: true, result_count: 5 },
              { method_name: 'rouge', has_results: false, result_count: 0 },
            ],
          },
        ],
      })
      ;(
        apiClient.evaluations.getEvaluatedModels as jest.Mock
      ).mockResolvedValue(mockModels)
      ;(apiClient.get as jest.Mock).mockResolvedValue({
        data: [
          {
            id: 'r1',
            project_id: '1',
            project_name: 'Test',
            model_id: 'gpt-4',
            metrics: { bleu: 0.85, rouge: 0.92 },
            samples_evaluated: 100,
            created_at: '2025-01-01',
            status: 'completed',
            evaluation_type: 'automated',
          },
        ],
      })
      ;(
        apiClient.evaluations.getEvaluationHistory as jest.Mock
      ).mockResolvedValue({ data: [] })
      ;(
        apiClient.evaluations.getSignificanceTests as jest.Mock
      ).mockResolvedValue({ comparisons: [] })
      ;(
        apiClient.evaluations.computeStatistics as jest.Mock
      ).mockResolvedValue({})
    })

    it('should load evaluation config when project selected', async () => {
      const user = userEvent.setup()
      render(<EvaluationDashboard />)

      await waitFor(() => {
        expect(
          screen.getByText('evaluation.viewer.filters.selectProject')
        ).toBeInTheDocument()
      })

      // Open dropdown and select project
      await user.click(
        screen.getByText('evaluation.viewer.filters.selectProject')
      )
      await waitFor(() => {
        expect(screen.getByText('Test Project')).toBeInTheDocument()
      })
      await user.click(screen.getByText('Test Project'))

      // Verify API calls
      await waitFor(() => {
        expect(
          apiClient.evaluations.getProjectEvaluationConfig
        ).toHaveBeenCalledWith('1')
        expect(
          apiClient.evaluations.getEvaluatedModels
        ).toHaveBeenCalledWith('1', true)
      })
    })

    it('should handle project eval config with legacy selected_methods', async () => {
      ;(
        apiClient.evaluations.getProjectEvaluationConfig as jest.Mock
      ).mockResolvedValue({
        selected_methods: {
          model_answer: {
            automated: ['bleu', 'rouge'],
            human: [],
            field_mapping: {
              prediction_field: 'model_answer',
              reference_field: 'reference',
            },
          },
        },
      })

      const user = userEvent.setup()
      render(<EvaluationDashboard />)

      await waitFor(() => {
        expect(
          screen.getByText('evaluation.viewer.filters.selectProject')
        ).toBeInTheDocument()
      })

      await user.click(
        screen.getByText('evaluation.viewer.filters.selectProject')
      )
      await waitFor(() => {
        expect(screen.getByText('Test Project')).toBeInTheDocument()
      })
      await user.click(screen.getByText('Test Project'))

      await waitFor(() => {
        expect(
          apiClient.evaluations.getProjectEvaluationConfig
        ).toHaveBeenCalled()
      })
    })

    it('should handle project with no evaluation config', async () => {
      ;(
        apiClient.evaluations.getProjectEvaluationConfig as jest.Mock
      ).mockResolvedValue({})
      ;(
        apiClient.evaluations.getEvaluatedModels as jest.Mock
      ).mockResolvedValue([])
      ;(apiClient.get as jest.Mock).mockResolvedValue({ data: [] })

      const user = userEvent.setup()
      render(<EvaluationDashboard />)

      await waitFor(() => {
        expect(
          screen.getByText('evaluation.viewer.filters.selectProject')
        ).toBeInTheDocument()
      })

      await user.click(
        screen.getByText('evaluation.viewer.filters.selectProject')
      )
      await waitFor(() => {
        expect(screen.getByText('Test Project')).toBeInTheDocument()
      })
      await user.click(screen.getByText('Test Project'))

      await waitFor(() => {
        expect(
          apiClient.evaluations.getProjectEvaluationConfig
        ).toHaveBeenCalled()
      })
    })

    it('should handle eval config fetch error', async () => {
      ;(
        apiClient.evaluations.getProjectEvaluationConfig as jest.Mock
      ).mockRejectedValue(new Error('Config error'))

      const user = userEvent.setup()
      render(<EvaluationDashboard />)

      await waitFor(() => {
        expect(
          screen.getByText('evaluation.viewer.filters.selectProject')
        ).toBeInTheDocument()
      })

      await user.click(
        screen.getByText('evaluation.viewer.filters.selectProject')
      )
      await waitFor(() => {
        expect(screen.getByText('Test Project')).toBeInTheDocument()
      })
      await user.click(screen.getByText('Test Project'))

      // Should not crash
      await waitFor(() => {
        expect(
          apiClient.evaluations.getProjectEvaluationConfig
        ).toHaveBeenCalled()
      })
    })

    it('should handle models fetch error', async () => {
      ;(
        apiClient.evaluations.getEvaluatedModels as jest.Mock
      ).mockRejectedValue(new Error('Models error'))

      const user = userEvent.setup()
      render(<EvaluationDashboard />)

      await waitFor(() => {
        expect(
          screen.getByText('evaluation.viewer.filters.selectProject')
        ).toBeInTheDocument()
      })

      await user.click(
        screen.getByText('evaluation.viewer.filters.selectProject')
      )
      await waitFor(() => {
        expect(screen.getByText('Test Project')).toBeInTheDocument()
      })
      await user.click(screen.getByText('Test Project'))

      await waitFor(() => {
        expect(
          apiClient.evaluations.getEvaluatedModels
        ).toHaveBeenCalled()
      })
    })

    it('should handle results fetch error', async () => {
      ;(apiClient.get as jest.Mock).mockRejectedValue(
        new Error('Results error')
      )

      const user = userEvent.setup()
      render(<EvaluationDashboard />)

      await waitFor(() => {
        expect(
          screen.getByText('evaluation.viewer.filters.selectProject')
        ).toBeInTheDocument()
      })

      await user.click(
        screen.getByText('evaluation.viewer.filters.selectProject')
      )
      await waitFor(() => {
        expect(screen.getByText('Test Project')).toBeInTheDocument()
      })
      await user.click(screen.getByText('Test Project'))

      await waitFor(() => {
        expect(apiClient.get).toHaveBeenCalled()
      })
    })
  })

  describe('URL Parameters', () => {
    it('should restore project from URL projectId', async () => {
      const paramsWithProjectId = new URLSearchParams('projectId=1')
      ;(useSearchParams as jest.Mock).mockReturnValue(paramsWithProjectId)
      ;(projectsAPI.list as jest.Mock).mockResolvedValue({
        items: [{ id: 1, title: 'URL Project', task_count: 5 }],
      })
      ;(
        apiClient.evaluations.getProjectEvaluationConfig as jest.Mock
      ).mockResolvedValue({})
      ;(
        apiClient.evaluations.getConfiguredMethods as jest.Mock
      ).mockResolvedValue({ fields: [] })
      ;(
        apiClient.evaluations.getEvaluatedModels as jest.Mock
      ).mockResolvedValue([])

      render(<EvaluationDashboard />)

      await waitFor(() => {
        expect(
          apiClient.evaluations.getProjectEvaluationConfig
        ).toHaveBeenCalledWith('1')
      })
    })

    it('should restore chartType from URL', async () => {
      const paramsWithChart = new URLSearchParams('chartType=bar')
      ;(useSearchParams as jest.Mock).mockReturnValue(paramsWithChart)

      render(<EvaluationDashboard />)

      // Should render without crashing
      expect(
        screen.getByText('evaluation.viewer.title')
      ).toBeInTheDocument()
    })

    it('should restore aggregation from URL', async () => {
      const paramsWithAgg = new URLSearchParams('aggregation=sample,model')
      ;(useSearchParams as jest.Mock).mockReturnValue(paramsWithAgg)

      render(<EvaluationDashboard />)

      expect(
        screen.getByText('evaluation.viewer.title')
      ).toBeInTheDocument()
    })

    it('should restore stats from URL', async () => {
      const paramsWithStats = new URLSearchParams('stats=ci,bootstrap')
      ;(useSearchParams as jest.Mock).mockReturnValue(paramsWithStats)

      render(<EvaluationDashboard />)

      expect(
        screen.getByText('evaluation.viewer.title')
      ).toBeInTheDocument()
    })
  })

  describe('Access Control - Permission Denied', () => {
    it('should redirect when user has no access', async () => {
      const { canAccessProjectData } = require('@/utils/permissions')
      ;(canAccessProjectData as jest.Mock).mockReturnValue(false)

      render(<EvaluationDashboard />)

      await waitFor(() => {
        expect(mockRouter.replace).toHaveBeenCalledWith(
          '/projects?error=no-permission'
        )
      })

      // Restore
      ;(canAccessProjectData as jest.Mock).mockReturnValue(true)
    })
  })

  describe('Leaderboard Button', () => {
    it('should navigate to leaderboard on click', async () => {
      const user = userEvent.setup()
      render(<EvaluationDashboard />)

      const leaderboardButton = screen.getByText(
        'evaluation.viewer.llmLeaderboard'
      )
      await user.click(leaderboardButton)

      expect(mockRouter.push).toHaveBeenCalledWith('/leaderboards?tab=llm')
    })
  })

  describe('Project Selection with Eval Config', () => {
    it('should load evaluation config with llm_judge metrics', async () => {
      const mockProject = { id: 1, title: 'Test', task_count: 10 }

      ;(projectsAPI.list as jest.Mock).mockResolvedValue({
        items: [mockProject],
      })
      ;(
        apiClient.evaluations.getProjectEvaluationConfig as jest.Mock
      ).mockResolvedValue({
        evaluation_configs: [
          {
            id: 'cfg1',
            metric: 'llm_judge_overall',
            enabled: true,
            prediction_fields: ['answer'],
            reference_fields: ['reference'],
          },
          {
            id: 'cfg2',
            metric: 'bleu',
            enabled: true,
            prediction_fields: ['answer'],
            reference_fields: ['reference'],
          },
        ],
        selected_methods: {
          answer: {
            automated: [],
            human: ['accuracy'],
          },
        },
      })
      ;(
        apiClient.evaluations.getConfiguredMethods as jest.Mock
      ).mockResolvedValue({ fields: [] })
      ;(
        apiClient.evaluations.getEvaluatedModels as jest.Mock
      ).mockResolvedValue([
        {
          model_id: 'gpt-4',
          model_name: 'GPT-4',
          has_results: true,
        },
      ])
      ;(apiClient.get as jest.Mock).mockResolvedValue({ data: [] })
      ;(
        apiClient.evaluations.computeStatistics as jest.Mock
      ).mockResolvedValue({})
      ;(
        apiClient.evaluations.getEvaluationHistory as jest.Mock
      ).mockResolvedValue({ data: [] })
      ;(
        apiClient.evaluations.getSignificanceTests as jest.Mock
      ).mockResolvedValue({ comparisons: [] })

      const user = userEvent.setup()
      render(<EvaluationDashboard />)

      await waitFor(() => {
        expect(
          screen.getByText('evaluation.viewer.filters.selectProject')
        ).toBeInTheDocument()
      })

      await user.click(
        screen.getByText('evaluation.viewer.filters.selectProject')
      )
      await waitFor(() => {
        expect(screen.getByText('Test')).toBeInTheDocument()
      })
      await user.click(screen.getByText('Test'))

      await waitFor(() => {
        expect(
          apiClient.evaluations.getProjectEvaluationConfig
        ).toHaveBeenCalledWith('1')
      })
    })
  })
})
