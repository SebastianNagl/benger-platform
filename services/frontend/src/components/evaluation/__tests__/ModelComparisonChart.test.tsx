/**
 * @jest-environment jsdom
 */
import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import { ModelComparisonChart } from '../ModelComparisonChart'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, any>) => {
      const translations: Record<string, string> = {
        'evaluation.modelComparison.score': 'Score',
        'evaluation.modelComparison.model': 'Model',
        'evaluation.modelComparison.average': 'Average',
        'evaluation.modelComparison.missingData': 'Missing Data',
        'evaluation.modelComparison.missingDataDetail': `Models with incomplete data: ${params?.models}`,
      }
      return translations[key] || key
    },
  }),
}))

// Mock recharts components
jest.mock('recharts', () => {
  const MockResponsiveContainer = ({ children }: any) => (
    <div data-testid="responsive-container">{children}</div>
  )
  const MockRadarChart = ({ children }: any) => (
    <div data-testid="radar-chart">{children}</div>
  )
  const MockBarChart = ({ children }: any) => (
    <div data-testid="bar-chart">{children}</div>
  )
  const MockRadar = ({ name }: any) => <div data-testid={`radar-${name}`} />
  const MockBar = ({ name }: any) => <div data-testid={`bar-${name}`} />

  return {
    ResponsiveContainer: MockResponsiveContainer,
    RadarChart: MockRadarChart,
    BarChart: MockBarChart,
    Radar: MockRadar,
    Bar: MockBar,
    PolarGrid: () => null,
    PolarAngleAxis: () => null,
    PolarRadiusAxis: () => null,
    CartesianGrid: () => null,
    XAxis: () => null,
    YAxis: () => null,
    Tooltip: () => null,
    Legend: () => null,
    ErrorBar: () => null,
  }
})

describe('ModelComparisonChart', () => {
  const defaultModels = [
    {
      model_id: 'gpt-4',
      metrics: { accuracy: 0.9, f1: 0.85 },
    },
    {
      model_id: 'claude-3',
      metrics: { accuracy: 0.88, f1: 0.82 },
    },
  ]

  const defaultMetrics = ['accuracy', 'f1']

  describe('Radar chart mode', () => {
    it('renders radar chart by default', () => {
      render(
        <ModelComparisonChart
          models={defaultModels}
          metrics={defaultMetrics}
        />
      )
      expect(screen.getByTestId('radar-chart')).toBeInTheDocument()
    })

    it('renders a Radar component per model', () => {
      render(
        <ModelComparisonChart
          models={defaultModels}
          metrics={defaultMetrics}
        />
      )
      expect(screen.getByTestId('radar-gpt-4')).toBeInTheDocument()
      expect(screen.getByTestId('radar-claude-3')).toBeInTheDocument()
    })

    it('renders title when provided', () => {
      render(
        <ModelComparisonChart
          models={defaultModels}
          metrics={defaultMetrics}
          title="Model Comparison"
        />
      )
      expect(screen.getByText('Model Comparison')).toBeInTheDocument()
    })

    it('does not render title when not provided', () => {
      render(
        <ModelComparisonChart
          models={defaultModels}
          metrics={defaultMetrics}
        />
      )
      expect(screen.queryByText('Model Comparison')).not.toBeInTheDocument()
    })
  })

  describe('Bar chart mode', () => {
    it('renders bar chart when visualizationType is bar', () => {
      render(
        <ModelComparisonChart
          models={defaultModels}
          metrics={defaultMetrics}
          visualizationType="bar"
        />
      )
      expect(screen.getByTestId('bar-chart')).toBeInTheDocument()
    })

    it('renders a Bar component per metric', () => {
      render(
        <ModelComparisonChart
          models={defaultModels}
          metrics={defaultMetrics}
          visualizationType="bar"
        />
      )
      expect(screen.getByTestId('bar-accuracy')).toBeInTheDocument()
      expect(screen.getByTestId('bar-f1')).toBeInTheDocument()
    })

    it('renders summary table with model names', () => {
      render(
        <ModelComparisonChart
          models={defaultModels}
          metrics={defaultMetrics}
          visualizationType="bar"
        />
      )
      expect(screen.getByText('gpt-4')).toBeInTheDocument()
      expect(screen.getByText('claude-3')).toBeInTheDocument()
    })

    it('renders metric column headers in summary table', () => {
      render(
        <ModelComparisonChart
          models={defaultModels}
          metrics={defaultMetrics}
          visualizationType="bar"
        />
      )
      // Metric names appear both as Bar dataKey and table headers
      const accuracyElements = screen.getAllByText('accuracy')
      expect(accuracyElements.length).toBeGreaterThanOrEqual(1)
    })

    it('renders average column in summary table', () => {
      render(
        <ModelComparisonChart
          models={defaultModels}
          metrics={defaultMetrics}
          visualizationType="bar"
        />
      )
      expect(screen.getByText('Average')).toBeInTheDocument()
    })

    it('computes and displays average scores for each model', () => {
      render(
        <ModelComparisonChart
          models={defaultModels}
          metrics={defaultMetrics}
          visualizationType="bar"
        />
      )
      // gpt-4: (0.9 + 0.85) / 2 = 0.875
      expect(screen.getByText('0.875')).toBeInTheDocument()
      // claude-3: (0.88 + 0.82) / 2 = 0.850 (may also appear as individual metric value)
      expect(screen.getAllByText('0.850').length).toBeGreaterThanOrEqual(1)
    })

    it('shows confidence intervals when available', () => {
      const models = [
        {
          model_id: 'gpt-4',
          metrics: {
            accuracy: {
              value: 0.9,
              confidenceInterval: { lower: 0.85, upper: 0.95 },
            },
          },
        },
      ]
      render(
        <ModelComparisonChart
          models={models}
          metrics={['accuracy']}
          visualizationType="bar"
        />
      )
      expect(screen.getByText('[0.850, 0.950]')).toBeInTheDocument()
    })
  })

  describe('Missing data warning', () => {
    it('shows warning when models have missing metric data', () => {
      const models = [
        { model_id: 'gpt-4', metrics: { accuracy: 0.9 } },
        { model_id: 'claude-3', metrics: {} }, // Missing all metrics
      ]
      render(
        <ModelComparisonChart
          models={models}
          metrics={['accuracy', 'f1']}
          visualizationType="bar"
        />
      )
      expect(screen.getByText(/Missing Data/)).toBeInTheDocument()
    })

    it('does not show warning when all models have all metrics', () => {
      render(
        <ModelComparisonChart
          models={defaultModels}
          metrics={defaultMetrics}
          visualizationType="bar"
        />
      )
      expect(screen.queryByText(/Missing Data/)).not.toBeInTheDocument()
    })
  })

  describe('MetricValue objects', () => {
    it('extracts numeric value from MetricValue objects', () => {
      const models = [
        {
          model_id: 'test',
          metrics: {
            accuracy: { value: 0.9, confidenceInterval: { lower: 0.85, upper: 0.95 } },
          },
        },
      ]
      render(
        <ModelComparisonChart
          models={models}
          metrics={['accuracy']}
          visualizationType="bar"
        />
      )
      // 0.900 appears for both the metric value and the average (since only 1 metric)
      expect(screen.getAllByText('0.900').length).toBeGreaterThanOrEqual(1)
    })
  })
})
