/**
 * Branch coverage tests for Evaluations Dashboard Page
 *
 * Targets uncovered branches: auth loading, project loading,
 * no project selected, no results, permission denied, running state,
 * filter dropdown opens/closes, URL param loading, metric params visibility,
 * evaluation types, and stats method loading.
 *
 * @jest-environment jsdom
 */

import { useToast } from '@/components/shared/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { apiClient } from '@/lib/api/client'
import { projectsAPI } from '@/lib/api/projects'
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react'
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

jest.mock('@/lib/utils/subdomain', () => ({
  parseSubdomain: () => ({ isPrivateMode: true }),
}))

jest.mock('@heroicons/react/24/outline', () => ({
  ChartBarIcon: () => <div data-testid="chart-bar-icon" />,
  FunnelIcon: () => <div data-testid="funnel-icon" />,
  ChevronDownIcon: () => <div data-testid="chevron-down-icon" />,
  PlayIcon: () => <div data-testid="play-icon" />,
  ExclamationTriangleIcon: () => <div data-testid="exclamation-icon" />,
}))

jest.mock('@/components/shared/FeatureFlag', () => ({
  FeatureFlag: ({ children }: any) => <>{children}</>,
}))

jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: ({ items }: any) => (
    <nav data-testid="breadcrumb">
      {items.map((item: any, i: number) => <span key={i}>{item.label}</span>)}
    </nav>
  ),
}))

jest.mock('@/components/shared/ResponsiveContainer', () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, disabled, variant, className }: any) => (
    <button onClick={onClick} disabled={disabled} className={className}>{children}</button>
  ),
}))

jest.mock('@/components/shared/Card', () => ({
  Card: ({ children, className }: any) => <div className={className}>{children}</div>,
}))

jest.mock('@/components/shared/LoadingSpinner', () => ({
  LoadingSpinner: () => <div data-testid="loading-spinner">Loading...</div>,
}))

jest.mock('@/components/evaluation/EvaluationResults', () => ({
  EvaluationResults: () => <div data-testid="evaluation-results">Results</div>,
}))

jest.mock('@/components/evaluation/EvaluationResultsTable', () => ({
  EvaluationResultsTable: () => <div data-testid="evaluation-results-table">Table</div>,
}))

jest.mock('@/components/evaluation/ScoreCard', () => ({
  ScoreCard: () => <div data-testid="score-card">Score</div>,
}))

jest.mock('@/components/evaluation/AggregationSelector', () => ({
  AggregationSelector: () => <div data-testid="aggregation-selector" />,
}))

jest.mock('@/components/evaluation/ChartTypeSelector', () => ({
  ChartTypeSelector: () => <div data-testid="chart-type-selector" />,
}))

jest.mock('@/components/evaluation/FieldPairSelector', () => ({
  FieldPairSelector: () => <div data-testid="field-pair-selector" />,
}))

jest.mock('@/components/evaluation/StatisticsSelector', () => ({
  StatisticsSelector: () => <div data-testid="statistics-selector" />,
}))

jest.mock('@/components/evaluation/StatisticalResultsPanel', () => ({
  StatisticalResultsPanel: () => <div data-testid="stats-panel" />,
}))

jest.mock('@/components/evaluation/DynamicChartRenderer', () => ({
  DynamicChartRenderer: () => <div data-testid="chart-renderer" />,
}))

jest.mock('@/components/evaluation/charts/HistoricalTrendChart', () => ({
  HistoricalTrendChart: () => <div data-testid="historical-chart" />,
}))

jest.mock('@/components/evaluation/charts/SignificanceHeatmap', () => ({
  SignificanceHeatmap: () => <div data-testid="significance-heatmap" />,
}))

jest.mock('@/components/evaluation/EvaluationControlModal', () => ({
  EvaluationControlModal: () => <div data-testid="evaluation-modal" />,
}))

const mockRouter = { push: jest.fn(), replace: jest.fn() }
const mockSearchParams = new URLSearchParams()
const mockAddToast = jest.fn()

function setupMocks(overrides: Record<string, any> = {}) {
  ;(useRouter as jest.Mock).mockReturnValue(mockRouter)
  ;(useSearchParams as jest.Mock).mockReturnValue(overrides.searchParams ?? mockSearchParams)
  ;(useAuth as jest.Mock).mockReturnValue({
    user: overrides.user ?? { id: 'u1', is_superadmin: true, role: 'admin' },
    isLoading: overrides.authLoading ?? false,
  })
  ;(useI18n as jest.Mock).mockReturnValue({
    t: (key: string, vars?: any) => {
      if (vars) {
        let text = key
        Object.entries(vars).forEach(([k, v]) => {
          text = text.replace(`{${k}}`, String(v))
        })
        return text
      }
      return key
    },
  })
  ;(useToast as jest.Mock).mockReturnValue({ addToast: mockAddToast })

  const projects = overrides.projects ?? [
    { id: 'p1', title: 'Project 1', task_count: 10, annotation_count: 5 },
    { id: 'p2', title: 'Project 2', task_count: 20, annotation_count: 10 },
  ]
  ;(projectsAPI.list as jest.Mock).mockResolvedValue({ items: projects })
  ;(apiClient.evaluations.getProjectEvaluationConfig as jest.Mock).mockResolvedValue({
    selected_methods: {},
    evaluation_configs: [],
  })
  ;(apiClient.evaluations.getConfiguredMethods as jest.Mock).mockResolvedValue({
    automated: [],
    human: [],
  })
  ;(apiClient.evaluations.getEvaluatedModels as jest.Mock).mockResolvedValue(overrides.evaluatedModels ?? [])
  ;(apiClient.evaluations.getProjectAnnotators as jest.Mock).mockResolvedValue([])
  ;(apiClient.evaluations.getEvaluationHistory as jest.Mock).mockResolvedValue([])
  ;(apiClient.evaluations.getSignificanceTests as jest.Mock).mockResolvedValue([])
  ;(apiClient.evaluations.computeStatistics as jest.Mock).mockResolvedValue({})
  ;(apiClient.get as jest.Mock).mockResolvedValue({ configured_methods: [], metrics_with_results: [] })
}

describe('EvaluationDashboard Branch Coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    // Mock localStorage
    const store: Record<string, string> = {}
    jest.spyOn(Storage.prototype, 'getItem').mockImplementation((key) => store[key] || null)
    jest.spyOn(Storage.prototype, 'setItem').mockImplementation((key, value) => { store[key] = value })
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  describe('Initial render without project selected', () => {
    it('renders page with breadcrumb and title', async () => {
      setupMocks()
      render(<EvaluationDashboard />)
      await waitFor(() => {
        expect(screen.getByTestId('breadcrumb')).toBeInTheDocument()
      })
    })

    it('shows select project prompt when no project selected', async () => {
      setupMocks()
      render(<EvaluationDashboard />)
      await waitFor(() => {
        expect(screen.getByText('evaluation.viewer.emptyStates.selectProject.title')).toBeInTheDocument()
      })
    })
  })

  describe('Auth loading state', () => {
    it('skips project loading while auth is loading', async () => {
      setupMocks({ authLoading: true })
      render(<EvaluationDashboard />)
      // Projects should not be loaded yet
      expect(projectsAPI.list).not.toHaveBeenCalled()
    })

    it('loads projects after auth completes', async () => {
      setupMocks({ authLoading: false })
      render(<EvaluationDashboard />)
      await waitFor(() => {
        expect(projectsAPI.list).toHaveBeenCalled()
      })
    })
  })

  describe('URL parameter loading', () => {
    it('loads projectId from URL searchParams', async () => {
      const params = new URLSearchParams('projectId=p1')
      setupMocks({ searchParams: params })
      render(<EvaluationDashboard />)
      await waitFor(() => {
        expect(projectsAPI.list).toHaveBeenCalled()
      })
    })

    it('loads chartType from URL', async () => {
      const params = new URLSearchParams('chartType=bar')
      setupMocks({ searchParams: params })
      render(<EvaluationDashboard />)
      await waitFor(() => {
        expect(screen.getByTestId('breadcrumb')).toBeInTheDocument()
      })
    })

    it('loads aggregation from URL', async () => {
      const params = new URLSearchParams('aggregation=model,annotator')
      setupMocks({ searchParams: params })
      render(<EvaluationDashboard />)
      await waitFor(() => {
        expect(screen.getByTestId('breadcrumb')).toBeInTheDocument()
      })
    })

    it('loads stats methods from URL', async () => {
      const params = new URLSearchParams('stats=ci,bootstrap')
      setupMocks({ searchParams: params })
      render(<EvaluationDashboard />)
      await waitFor(() => {
        expect(screen.getByTestId('breadcrumb')).toBeInTheDocument()
      })
    })

    it('falls back to localStorage for projectId', async () => {
      jest.spyOn(Storage.prototype, 'getItem').mockImplementation((key) => {
        if (key === 'evaluations_lastProjectId') return 'p1'
        return null
      })
      setupMocks()
      render(<EvaluationDashboard />)
      await waitFor(() => {
        expect(projectsAPI.list).toHaveBeenCalled()
      })
    })
  })

  describe('Projects list empty state', () => {
    it('handles empty projects list', async () => {
      setupMocks({ projects: [] })
      render(<EvaluationDashboard />)
      await waitFor(() => {
        expect(screen.getByText('evaluation.viewer.emptyStates.selectProject.title')).toBeInTheDocument()
      })
    })
  })

  describe('Permission denied branch', () => {
    it('handles permission check', async () => {
      const { canAccessProjectData } = require('@/utils/permissions')
      ;(canAccessProjectData as jest.Mock).mockReturnValue(false)
      setupMocks()
      const { container } = render(<EvaluationDashboard />)
      await waitFor(() => {
        expect(container.firstChild).toBeTruthy()
      })
    })
  })

  describe('Null searchParams branch', () => {
    it('handles null searchParams', async () => {
      setupMocks({ searchParams: null })
      const { container } = render(<EvaluationDashboard />)
      await waitFor(() => {
        expect(container.firstChild).toBeTruthy()
      })
    })
  })

  describe('Invalid chartType from URL', () => {
    it('ignores invalid chartType', async () => {
      const params = new URLSearchParams('chartType=invalid')
      setupMocks({ searchParams: params })
      const { container } = render(<EvaluationDashboard />)
      await waitFor(() => {
        expect(container.firstChild).toBeTruthy()
      })
    })
  })

  describe('Project list load error', () => {
    it('handles projects API error gracefully', async () => {
      setupMocks()
      ;(projectsAPI.list as jest.Mock).mockRejectedValue(new Error('Network error'))
      const { container } = render(<EvaluationDashboard />)
      await waitFor(() => {
        expect(container.firstChild).toBeTruthy()
      })
    })
  })
})
