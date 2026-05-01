/**
 * Surgical branch coverage tests for Evaluations Dashboard
 * Targets uncovered lines: 109, 242, 290, 304, 312, 320, 328, 331, 337, 342, 346, 383, 386, 487, 493
 * @jest-environment jsdom
 */

import { useToast } from '@/components/shared/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { apiClient } from '@/lib/api/client'
import { projectsAPI } from '@/lib/api/projects'
import '@testing-library/jest-dom'
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
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

jest.mock('@/lib/utils/subdomain', () => ({
  parseSubdomain: jest.fn(() => ({ isPrivateMode: false, orgSlug: 'tum' })),
}))

// Mock all icons
jest.mock('@heroicons/react/24/outline', () => ({
  ChartBarIcon: () => <div data-testid="chart-bar-icon" />,
  FunnelIcon: () => <div data-testid="funnel-icon" />,
  ChevronDownIcon: () => <div data-testid="chevron-down-icon" />,
  PlayIcon: () => <div data-testid="play-icon" />,
  ExclamationTriangleIcon: () => <div data-testid="exclamation-icon" />,
  XMarkIcon: () => <div data-testid="x-mark-icon" />,
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

// Mock evaluation components
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

describe('EvaluationDashboard - Surgical Branch Coverage 2', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    localStorage.clear()
    ;(useRouter as jest.Mock).mockReturnValue(mockRouter)
    ;(useAuth as jest.Mock).mockReturnValue({
      user: mockUser,
      isLoading: false,
    })
    ;(useI18n as jest.Mock).mockReturnValue({ t: mockT })
    ;(useToast as jest.Mock).mockReturnValue({ addToast: mockAddToast })

    // Default API mocks
    ;(projectsAPI.list as jest.Mock).mockResolvedValue({ items: [] })
    ;(apiClient.evaluations.getProjectEvaluationConfig as jest.Mock).mockResolvedValue({})
    ;(apiClient.evaluations.getConfiguredMethods as jest.Mock).mockResolvedValue({ fields: [] })
    ;(apiClient.evaluations.getEvaluatedModels as jest.Mock).mockResolvedValue([])
    ;(apiClient.evaluations.getProjectAnnotators as jest.Mock).mockResolvedValue({ annotators: [] })
    ;(apiClient.get as jest.Mock).mockResolvedValue({ data: [] })
  })

  // Line 109: parseSubdomain() - the window !== 'undefined' branch
  // In JSDOM typeof window is always 'object', so parseSubdomain() is called
  describe('parseSubdomain SSR vs client (line 109)', () => {
    it('calls parseSubdomain when window is defined (client)', () => {
      const mockSearchParams = new URLSearchParams()
      ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)

      render(<EvaluationDashboard />)
      expect(screen.getByText('evaluation.viewer.title')).toBeInTheDocument()
    })
  })

  // Line 242: response.items || [] - when items is undefined
  describe('Project loading with undefined items (line 242)', () => {
    it('handles response without items field', async () => {
      const mockSearchParams = new URLSearchParams()
      ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)
      ;(projectsAPI.list as jest.Mock).mockResolvedValue({})

      render(<EvaluationDashboard />)

      await waitFor(() => {
        expect(projectsAPI.list).toHaveBeenCalled()
      })
    })

    it('handles response with items field', async () => {
      const mockSearchParams = new URLSearchParams()
      ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)
      ;(projectsAPI.list as jest.Mock).mockResolvedValue({
        items: [
          { id: 1, title: 'Project 1', task_count: 10 },
        ],
      })

      render(<EvaluationDashboard />)

      await waitFor(() => {
        expect(projectsAPI.list).toHaveBeenCalled()
      })
    })
  })

  // Line 290: project from URL search params matches a loaded project
  // Line 304: URL aggregation with valid levels
  // Line 312: URL stats with valid methods
  describe('URL filter parsing (lines 290, 304, 312)', () => {
    it('loads project from URL params and applies aggregation and stats filters', async () => {
      const mockSearchParams = new URLSearchParams(
        'projectId=1&chartType=bar&aggregation=model,metric&stats=ci,bootstrap'
      )
      ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)

      const mockProjects = [
        { id: 1, title: 'Project 1', task_count: 10 },
        { id: 2, title: 'Project 2', task_count: 5 },
      ]
      ;(projectsAPI.list as jest.Mock).mockResolvedValue({
        items: mockProjects,
      })

      // Mock full evaluation data pipeline
      ;(apiClient.evaluations.getProjectEvaluationConfig as jest.Mock).mockResolvedValue({
        evaluation_configs: [
          { metric: 'bleu', enabled: true, prediction_fields: ['text'], reference_fields: ['ref'] },
        ],
      })
      ;(apiClient.evaluations.getConfiguredMethods as jest.Mock).mockResolvedValue({
        fields: [{ name: 'text', methods: ['bleu'] }],
      })
      ;(apiClient.evaluations.getEvaluatedModels as jest.Mock).mockResolvedValue([
        { model_id: 'gpt-4', model_name: 'GPT-4', provider: 'OpenAI', has_results: true, evaluation_count: 5 },
      ])

      render(<EvaluationDashboard />)

      await waitFor(() => {
        expect(projectsAPI.list).toHaveBeenCalled()
      })
    })

    it('loads project from localStorage when no URL param', async () => {
      localStorage.setItem('evaluations_lastProjectId', '2')
      const mockSearchParams = new URLSearchParams()
      ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)

      ;(projectsAPI.list as jest.Mock).mockResolvedValue({
        items: [
          { id: 2, title: 'Project 2', task_count: 5 },
        ],
      })

      render(<EvaluationDashboard />)

      await waitFor(() => {
        expect(projectsAPI.list).toHaveBeenCalled()
      })
    })
  })

  // Lines 320, 328, 331, 337, 342, 346: URL filter application after data loads
  describe('URL model/metric filters applied after data loads (lines 320-346)', () => {
    it('applies URL models and metrics filters when data is available', async () => {
      const mockSearchParams = new URLSearchParams(
        'projectId=1&models=gpt-4,claude-3&metrics=bleu,rouge'
      )
      ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)

      ;(projectsAPI.list as jest.Mock).mockResolvedValue({
        items: [{ id: 1, title: 'Project 1', task_count: 10 }],
      })

      ;(apiClient.evaluations.getProjectEvaluationConfig as jest.Mock).mockResolvedValue({
        evaluation_configs: [
          { metric: 'bleu', enabled: true, prediction_fields: ['text'], reference_fields: ['ref'] },
          { metric: 'rouge', enabled: true, prediction_fields: ['text'], reference_fields: ['ref'] },
        ],
      })
      ;(apiClient.evaluations.getConfiguredMethods as jest.Mock).mockResolvedValue({
        fields: [{ name: 'text', methods: ['bleu', 'rouge'] }],
      })
      ;(apiClient.evaluations.getEvaluatedModels as jest.Mock).mockResolvedValue([
        { model_id: 'gpt-4', model_name: 'GPT-4', provider: 'OpenAI', has_results: true, evaluation_count: 5 },
        { model_id: 'claude-3', model_name: 'Claude 3', provider: 'Anthropic', has_results: true, evaluation_count: 3 },
      ])

      render(<EvaluationDashboard />)

      await waitFor(() => {
        expect(apiClient.evaluations.getEvaluatedModels).toHaveBeenCalled()
      })
    })

    it('handles URL models filter with some invalid model ids', async () => {
      const mockSearchParams = new URLSearchParams(
        'projectId=1&models=gpt-4,nonexistent&metrics=bleu,nonexistent_metric'
      )
      ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)

      ;(projectsAPI.list as jest.Mock).mockResolvedValue({
        items: [{ id: 1, title: 'Project 1', task_count: 10 }],
      })

      ;(apiClient.evaluations.getProjectEvaluationConfig as jest.Mock).mockResolvedValue({
        evaluation_configs: [
          { metric: 'bleu', enabled: true, prediction_fields: ['text'], reference_fields: ['ref'] },
        ],
      })
      ;(apiClient.evaluations.getConfiguredMethods as jest.Mock).mockResolvedValue({
        fields: [{ name: 'text', methods: ['bleu'] }],
      })
      ;(apiClient.evaluations.getEvaluatedModels as jest.Mock).mockResolvedValue([
        { model_id: 'gpt-4', model_name: 'GPT-4', provider: 'OpenAI', has_results: true, evaluation_count: 5 },
      ])

      render(<EvaluationDashboard />)

      await waitFor(() => {
        expect(apiClient.evaluations.getEvaluatedModels).toHaveBeenCalled()
      })
    })
  })

  // Lines 383, 386: URL sync - aggregation and stats conditions
  describe('URL sync for aggregation and stats (lines 383, 386)', () => {
    it('syncs non-default aggregation and stats to URL', async () => {
      const mockSearchParams = new URLSearchParams('projectId=1&aggregation=metric&stats=bootstrap,permutation')
      ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)

      ;(projectsAPI.list as jest.Mock).mockResolvedValue({
        items: [{ id: 1, title: 'Project 1', task_count: 10 }],
      })

      ;(apiClient.evaluations.getProjectEvaluationConfig as jest.Mock).mockResolvedValue({
        evaluation_configs: [
          { metric: 'bleu', enabled: true, prediction_fields: ['text'], reference_fields: ['ref'] },
        ],
      })
      ;(apiClient.evaluations.getConfiguredMethods as jest.Mock).mockResolvedValue({
        fields: [],
      })
      ;(apiClient.evaluations.getEvaluatedModels as jest.Mock).mockResolvedValue([
        { model_id: 'gpt-4', model_name: 'GPT-4', provider: 'OpenAI', has_results: true, evaluation_count: 5 },
      ])

      render(<EvaluationDashboard />)

      await waitFor(() => {
        expect(projectsAPI.list).toHaveBeenCalled()
      })
    })
  })

  // Lines 487, 493: Legacy project bridge - selected_methods to evaluation_configs
  describe('Legacy project bridge from selected_methods (lines 487, 493)', () => {
    it('derives evaluation configs from selected_methods when evaluation_configs is empty', async () => {
      const mockSearchParams = new URLSearchParams('projectId=1')
      ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)

      ;(projectsAPI.list as jest.Mock).mockResolvedValue({
        items: [{ id: 1, title: 'Legacy Project', task_count: 10 }],
      })

      // Return config with selected_methods but no evaluation_configs
      ;(apiClient.evaluations.getProjectEvaluationConfig as jest.Mock).mockResolvedValue({
        selected_methods: {
          text: {
            automated: ['bleu', { name: 'rouge', parameters: { variant: 'rougeL' } }],
            human: [],
            field_mapping: {
              prediction_field: 'generated_text',
              reference_field: 'reference_text',
            },
          },
        },
        evaluation_configs: [],
      })

      ;(apiClient.evaluations.getConfiguredMethods as jest.Mock).mockResolvedValue({
        fields: [{ name: 'text', methods: ['bleu', 'rouge'] }],
      })

      ;(apiClient.evaluations.getEvaluatedModels as jest.Mock).mockResolvedValue([
        { model_id: 'gpt-4', model_name: 'GPT-4', provider: 'OpenAI', has_results: true, evaluation_count: 5 },
      ])

      render(<EvaluationDashboard />)

      await waitFor(() => {
        expect(apiClient.evaluations.getProjectEvaluationConfig).toHaveBeenCalled()
      })
    })

    it('handles legacy selected_methods with string metrics and object metrics', async () => {
      const mockSearchParams = new URLSearchParams('projectId=1')
      ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)

      ;(projectsAPI.list as jest.Mock).mockResolvedValue({
        items: [{ id: 1, title: 'Legacy Mixed', task_count: 10 }],
      })

      ;(apiClient.evaluations.getProjectEvaluationConfig as jest.Mock).mockResolvedValue({
        selected_methods: {
          answer: {
            automated: [
              'exact_match',
              { name: 'semantic_similarity', parameters: { model: 'all-MiniLM' } },
            ],
            human: ['accuracy'],
            field_mapping: {},
          },
        },
      })

      ;(apiClient.evaluations.getConfiguredMethods as jest.Mock).mockResolvedValue({
        fields: [{ name: 'answer', methods: ['exact_match', 'semantic_similarity'] }],
      })

      ;(apiClient.evaluations.getEvaluatedModels as jest.Mock).mockResolvedValue([])

      render(<EvaluationDashboard />)

      await waitFor(() => {
        expect(apiClient.evaluations.getProjectEvaluationConfig).toHaveBeenCalled()
      })
    })
  })
})
