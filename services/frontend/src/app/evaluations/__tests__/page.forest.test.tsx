/**
 * The Metrics view's forest type: the mean and 95 % CI of each model per
 * metric from the model-level statistics, as interval rows; disabled with a
 * reason while there are none.
 *
 * @jest-environment jsdom
 */

import { setMockFeatureFlags } from '@/test-utils/featureFlagsMock'
import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'

import { MetricResultsView } from '@/app/evaluations/_components/MetricResultsView'
import { apiClient } from '@/lib/api/client'

jest.mock('@/lib/featureFlags', () =>
  jest.requireActual('@/test-utils/featureFlagsMock').featureFlagsMockModule(),
)
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'u', is_superadmin: true } }),
}))
jest.mock('next/navigation', () => ({
  useRouter: () => ({ replace: jest.fn(), push: jest.fn() }),
}))
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: jest.fn() }),
}))
jest.mock('@/hooks/useOperationToasts', () => ({
  useOperationToasts: () => ({
    startEvaluation: jest.fn(),
    updateEvaluation: jest.fn(),
    renderToasts: () => null,
  }),
}))
jest.mock('@/lib/api/client', () => ({
  apiClient: {
    get: jest.fn(),
    evaluations: {
      getProjectEvaluationConfig: jest.fn(),
      getConfiguredMethods: jest.fn(),
      getEvaluatedModels: jest.fn(),
      getEvaluationHistory: jest.fn(),
      getSignificanceTests: jest.fn(),
      computeStatistics: jest.fn(),
    },
  },
}))
jest.mock('@/components/evaluation/results/useMultiConfigChartData', () => ({
  useMultiConfigChartData: () => ({ models: [], seriesNames: [] }),
}))

const mockRenderer = jest.fn()
jest.mock('@/components/evaluation/DynamicChartRenderer', () => ({
  DynamicChartRenderer: (props: any) => {
    mockRenderer(props)
    return <div data-testid="dynamic-chart-renderer" />
  },
}))
const mockSelector = jest.fn()
jest.mock('@/components/evaluation/ChartTypeSelector', () => ({
  ChartTypeSelector: (props: any) => {
    mockSelector(props)
    return <div data-testid="chart-type-selector" />
  },
}))
jest.mock('@/components/evaluation/EvaluationResults', () => ({
  EvaluationResults: () => null,
}))
jest.mock('@/components/evaluation/EvaluationResultsTable', () => ({
  EvaluationResultsTable: () => null,
}))
jest.mock('@/components/evaluation/ScoreCard', () => ({
  ScoreCard: () => null,
}))
jest.mock('@/components/evaluation/StatisticalResultsPanel', () => ({
  StatisticalResultsPanel: () => null,
}))
jest.mock('@/components/evaluation/StatisticsSelector', () => ({
  StatisticsSelector: () => null,
}))
jest.mock('@/components/evaluation/AggregationSelector', () => ({
  AggregationSelector: () => null,
}))
jest.mock('@/components/evaluation/EvaluationControlModal', () => ({
  EvaluationControlModal: () => null,
}))
jest.mock('@/components/evaluation/charts/HistoricalTrendChart', () => ({
  HistoricalTrendChart: () => null,
}))
jest.mock('@/components/evaluation/charts/SignificanceHeatmap', () => ({
  SignificanceHeatmap: () => null,
}))

const project = { id: 'p1', title: 'P', task_count: 3 } as any
const params = (q: string) => new URLSearchParams(q)

const evaluations = apiClient.evaluations as unknown as Record<
  string,
  jest.Mock
>

beforeEach(() => {
  jest.clearAllMocks()
  // The forest chart of the metrics belongs to variant_experiments.
  setMockFeatureFlags({ variant_experiments: true })
  evaluations.getProjectEvaluationConfig.mockResolvedValue({
    evaluation_configs: [
      {
        id: 'cfg-1',
        metric: 'bleu',
        display_name: 'BLEU (strict)',
        prediction_fields: ['a'],
        reference_fields: ['b'],
        enabled: true,
      },
    ],
  })
  evaluations.getConfiguredMethods.mockResolvedValue({ fields: [] })
  evaluations.getEvaluatedModels.mockResolvedValue([
    { model_id: 'm1', model_name: 'Model One' },
    { model_id: 'm2', model_name: 'Model Two' },
  ])
  evaluations.getEvaluationHistory.mockResolvedValue({ series: [] })
  evaluations.getSignificanceTests.mockResolvedValue({ comparisons: [] })
  ;(apiClient.get as jest.Mock).mockResolvedValue({
    data: [{ model_id: 'm1', metrics: { bleu: 0.4 } }],
  })
})

it('feeds the forest view with interval rows from the statistics', async () => {
  evaluations.computeStatistics.mockResolvedValue({
    aggregation: 'model',
    metrics: {},
    by_model: {
      m1: {
        metrics: { bleu: { mean: 0.4, ci_lower: 0.3, ci_upper: 0.5, n: 9 } },
      },
      m2: {
        metrics: { bleu: { mean: 0.2, ci_lower: 0.1, ci_upper: 0.3, n: 9 } },
      },
    },
  })
  render(
    <MetricResultsView
      selectedProject={project}
      filterBarLead={<span>lead</span>}
      initialParams={params('projectId=p1&chartType=forest')}
    />,
  )
  expect(screen.getByText('lead')).toBeInTheDocument()
  await waitFor(() =>
    expect(
      mockRenderer.mock.calls.some(([p]) => p.intervalRows?.length === 2),
    ).toBe(true),
  )
  const last = mockRenderer.mock.calls.at(-1)![0]
  expect(last.chartType).toBe('forest')
  expect(
    last.intervalRows.map((r: any) => [r.series, r.label, r.estimate]),
  ).toEqual([
    ['BLEU (strict)', 'Model One', 0.4],
    ['BLEU (strict)', 'Model Two', 0.2],
  ])
  const selector = mockSelector.mock.calls.at(-1)![0]
  expect(selector.disabledTypes).not.toContain('forest')
})

it('offers no forest view and shows the data view while variant_experiments is off', async () => {
  setMockFeatureFlags({})
  evaluations.computeStatistics.mockResolvedValue({
    aggregation: 'model',
    metrics: {},
    by_model: {
      m1: {
        metrics: { bleu: { mean: 0.4, ci_lower: 0.3, ci_upper: 0.5, n: 9 } },
      },
    },
  })
  render(
    <MetricResultsView
      selectedProject={project}
      filterBarLead={<span>lead</span>}
      initialParams={params('projectId=p1&chartType=forest')}
    />,
  )
  await waitFor(() => expect(mockSelector).toHaveBeenCalled())
  // The forest from the URL falls back to the data view.
  await waitFor(() =>
    expect(mockSelector.mock.calls.at(-1)![0].selectedType).toBe('data'),
  )
  expect(mockRenderer.mock.calls.some(([p]) => p.chartType === 'forest')).toBe(
    false,
  )
  const selector = mockSelector.mock.calls.at(-1)![0]
  expect(selector.availableTypes).not.toContain('forest')
  expect(selector.availableTypes).toContain('bar')
})

it('disables the forest view without model-level statistics', async () => {
  evaluations.computeStatistics.mockResolvedValue({
    aggregation: 'sample',
    metrics: {},
  })
  render(
    <MetricResultsView
      selectedProject={project}
      filterBarLead={null}
      initialParams={params('projectId=p1&aggregation=sample')}
    />,
  )
  await waitFor(() => expect(evaluations.computeStatistics).toHaveBeenCalled())
  await waitFor(() => {
    const selector = mockSelector.mock.calls.at(-1)![0]
    expect(selector.disabledTypes).toContain('forest')
    expect(selector.disabledReasons.forest).toBe(
      'evaluation.viewer.chart.disabledReasons.forestNeedsModelAggregation',
    )
  })
  // Other chart types get no interval rows.
  expect(
    mockRenderer.mock.calls.every(([p]) => p.intervalRows === undefined),
  ).toBe(true)
})
