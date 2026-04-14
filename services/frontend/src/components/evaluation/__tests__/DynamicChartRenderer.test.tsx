/**
 * @jest-environment jsdom
 */
import '@testing-library/jest-dom'
import { render, screen, act } from '@testing-library/react'
import { DynamicChartRenderer, getSmartChartDefault } from '../DynamicChartRenderer'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, any>) => {
      const translations: Record<string, string> = {
        'evaluation.charts.noData': 'No data available',
        'evaluation.charts.noDistributionData': 'No distribution data available',
        'evaluation.charts.heatmapRequiresMultipleModels': 'Heatmap requires multiple models',
        'evaluation.charts.unknownChartType': `Unknown chart type: ${params?.type}`,
        'evaluation.charts.model': 'Model',
      }
      return translations[key] || key
    },
  }),
}))

jest.mock('@/components/shared/LoadingSpinner', () => ({
  LoadingSpinner: () => <div data-testid="loading-spinner" />,
}))

jest.mock('../ModelComparisonChart', () => ({
  ModelComparisonChart: ({ visualizationType, height }: any) => (
    <div data-testid={`model-chart-${visualizationType}`} data-height={height}>
      {visualizationType} chart
    </div>
  ),
}))

jest.mock('../EvaluationResultsTable', () => ({
  EvaluationResultsTable: ({ results }: any) => (
    <div data-testid="results-table">
      {results?.map((r: any) => <div key={r.modelId}>{r.modelName}</div>)}
    </div>
  ),
}))

jest.mock('../charts/BoxPlotChart', () => ({
  BoxPlotChart: ({ data }: any) => (
    <div data-testid="box-plot-chart">{data.length} data points</div>
  ),
  calculateBoxPlotStats: (scores: number[], label: string) => ({
    label,
    min: Math.min(...scores),
    q1: scores[Math.floor(scores.length * 0.25)],
    median: scores[Math.floor(scores.length * 0.5)],
    q3: scores[Math.floor(scores.length * 0.75)],
    max: Math.max(...scores),
    mean: scores.reduce((a, b) => a + b, 0) / scores.length,
    outliers: [],
  }),
}))

jest.mock('../charts/SignificanceHeatmap', () => ({
  SignificanceHeatmap: ({ modelIds, metric }: any) => (
    <div data-testid="significance-heatmap">
      {modelIds.length} models, {metric}
    </div>
  ),
}))

const defaultModels = [
  { model_id: 'gpt-4', model_name: 'GPT-4', metrics: { rouge: 0.85, bleu: 0.72 } },
  { model_id: 'claude-3', model_name: 'Claude 3', metrics: { rouge: 0.88, bleu: 0.75 } },
]

const defaultMetrics = ['rouge', 'bleu']

describe('DynamicChartRenderer', () => {
  describe('Loading state', () => {
    it('shows loading spinner when isLoading is true', () => {
      render(
        <DynamicChartRenderer
          chartType="bar"
          models={defaultModels}
          metrics={defaultMetrics}
          isLoading={true}
        />
      )
      expect(screen.getByTestId('loading-spinner')).toBeInTheDocument()
    })
  })

  describe('Empty state', () => {
    it('shows empty message when no models', () => {
      render(
        <DynamicChartRenderer
          chartType="bar"
          models={[]}
          metrics={defaultMetrics}
        />
      )
      expect(screen.getByText('No data available')).toBeInTheDocument()
    })

    it('shows empty message when no metrics', () => {
      render(
        <DynamicChartRenderer
          chartType="bar"
          models={defaultModels}
          metrics={[]}
        />
      )
      expect(screen.getByText('No data available')).toBeInTheDocument()
    })

    it('shows custom empty message', () => {
      render(
        <DynamicChartRenderer
          chartType="bar"
          models={[]}
          metrics={[]}
          emptyMessage="Custom empty"
        />
      )
      expect(screen.getByText('Custom empty')).toBeInTheDocument()
    })
  })

  describe('Chart types', () => {
    it('renders bar chart', () => {
      render(
        <DynamicChartRenderer
          chartType="bar"
          models={defaultModels}
          metrics={defaultMetrics}
        />
      )
      expect(screen.getByTestId('model-chart-bar')).toBeInTheDocument()
    })

    it('renders radar chart', () => {
      render(
        <DynamicChartRenderer
          chartType="radar"
          models={defaultModels}
          metrics={defaultMetrics}
        />
      )
      expect(screen.getByTestId('model-chart-radar')).toBeInTheDocument()
    })

    it('renders table view', () => {
      render(
        <DynamicChartRenderer
          chartType="table"
          models={defaultModels}
          metrics={defaultMetrics}
        />
      )
      expect(screen.getByTestId('results-table')).toBeInTheDocument()
      expect(screen.getByText('GPT-4')).toBeInTheDocument()
    })

    it('renders box plot when scores are available', () => {
      const modelsWithScores = [
        { model_id: 'gpt-4', model_name: 'GPT-4', metrics: { rouge: 0.85 }, scores: [0.8, 0.85, 0.9] },
      ]
      render(
        <DynamicChartRenderer
          chartType="box"
          models={modelsWithScores}
          metrics={['rouge']}
        />
      )
      expect(screen.getByTestId('box-plot-chart')).toBeInTheDocument()
    })

    it('shows no distribution data message for box plot without scores', () => {
      render(
        <DynamicChartRenderer
          chartType="box"
          models={defaultModels}
          metrics={defaultMetrics}
        />
      )
      expect(screen.getByText('No distribution data available')).toBeInTheDocument()
    })

    it('shows heatmap requires multiple models message for single model', () => {
      render(
        <DynamicChartRenderer
          chartType="heatmap"
          models={[defaultModels[0]]}
          metrics={defaultMetrics}
        />
      )
      expect(screen.getByText('Heatmap requires multiple models')).toBeInTheDocument()
    })

    it('renders significance heatmap when significance data is provided', () => {
      render(
        <DynamicChartRenderer
          chartType="heatmap"
          models={defaultModels}
          metrics={defaultMetrics}
          significanceData={[
            { model_a: 'gpt-4', model_b: 'claude-3', p_value: 0.01, significant: true, effect_size: 0.5, stars: '**' },
          ]}
        />
      )
      expect(screen.getByTestId('significance-heatmap')).toBeInTheDocument()
    })

    it('renders score heatmap when no significance data but multiple models', () => {
      render(
        <DynamicChartRenderer
          chartType="heatmap"
          models={defaultModels}
          metrics={defaultMetrics}
        />
      )
      // Should render ScoreHeatmap (the table-based heatmap)
      expect(screen.getByText('GPT-4')).toBeInTheDocument()
      expect(screen.getByText('0.850')).toBeInTheDocument()
    })

    it('shows unknown chart type message for invalid type', () => {
      render(
        <DynamicChartRenderer
          chartType={'unknown_chart' as any}
          models={defaultModels}
          metrics={defaultMetrics}
        />
      )
      expect(screen.getByText(/Unknown chart type/)).toBeInTheDocument()
    })
  })

  describe('Chart type transitions', () => {
    it('applies transition classes when chart type changes', async () => {
      jest.useFakeTimers()
      const { rerender, container } = render(
        <DynamicChartRenderer
          chartType="bar"
          models={defaultModels}
          metrics={defaultMetrics}
        />
      )

      // Change chart type
      rerender(
        <DynamicChartRenderer
          chartType="radar"
          models={defaultModels}
          metrics={defaultMetrics}
        />
      )

      // During transition, opacity should be 0
      const wrapper = container.firstChild as HTMLElement
      expect(wrapper.className).toContain('opacity-0')

      // After timeout, new chart type should be displayed
      act(() => {
        jest.advanceTimersByTime(200)
      })

      expect(screen.getByTestId('model-chart-radar')).toBeInTheDocument()

      jest.useRealTimers()
    })
  })

  describe('ScoreHeatmap color schemes', () => {
    it('renders with default color scheme', () => {
      const { container } = render(
        <DynamicChartRenderer
          chartType="heatmap"
          models={defaultModels}
          metrics={defaultMetrics}
        />
      )
      // High score (0.85) should use green with default scheme
      expect(container.querySelector('.bg-green-500')).toBeInTheDocument()
    })

    it('renders with accessible color scheme', () => {
      const { container } = render(
        <DynamicChartRenderer
          chartType="heatmap"
          models={defaultModels}
          metrics={defaultMetrics}
          colorScheme="accessible"
        />
      )
      // High score (0.85) should use blue with accessible scheme
      expect(container.querySelector('.bg-blue-500')).toBeInTheDocument()
    })

    it('shows dash for undefined metric values in heatmap', () => {
      const models = [
        { model_id: 'a', model_name: 'A', metrics: { rouge: 0.8 } },
        { model_id: 'b', model_name: 'B', metrics: {} },
      ]
      render(
        <DynamicChartRenderer
          chartType="heatmap"
          models={models}
          metrics={['rouge']}
        />
      )
      expect(screen.getByText('—')).toBeInTheDocument()
    })
  })
})

describe('getSmartChartDefault', () => {
  it('returns table for single model', () => {
    const models = [{ model_id: 'a', metrics: { rouge: 0.8 } }]
    expect(getSmartChartDefault(models, ['rouge'], false)).toBe('table')
  })

  it('returns radar for 3+ metrics and few models', () => {
    const models = [
      { model_id: 'a', metrics: { rouge: 0.8, bleu: 0.7, bertscore: 0.9 } },
      { model_id: 'b', metrics: { rouge: 0.7, bleu: 0.8, bertscore: 0.85 } },
    ]
    expect(getSmartChartDefault(models, ['rouge', 'bleu', 'bertscore'], false)).toBe('radar')
  })

  it('returns heatmap for many models with significance data', () => {
    const models = Array.from({ length: 5 }, (_, i) => ({
      model_id: `model-${i}`,
      metrics: { rouge: 0.8 },
    }))
    expect(getSmartChartDefault(models, ['rouge'], true)).toBe('heatmap')
  })

  it('returns bar as default', () => {
    const models = [
      { model_id: 'a', metrics: { rouge: 0.8 } },
      { model_id: 'b', metrics: { rouge: 0.7 } },
    ]
    expect(getSmartChartDefault(models, ['rouge'], false)).toBe('bar')
  })
})
