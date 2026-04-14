/**
 * Unit tests for ModelComparisonChart component
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import { ModelComparisonChart } from '../../../components/evaluation/ModelComparisonChart'

// Mock recharts components
jest.mock('recharts', () => {
  const React = require('react')
  return {
    ResponsiveContainer: ({ children, height }: any) => (
      <div data-testid="responsive-container" data-height={height}>
        {children}
      </div>
    ),
    RadarChart: ({ children, data }: any) => (
      <div data-testid="radar-chart" data-chart-data={JSON.stringify(data)}>
        {children}
      </div>
    ),
    BarChart: ({ children, data }: any) => (
      <div data-testid="bar-chart" data-chart-data={JSON.stringify(data)}>
        {children}
      </div>
    ),
    PolarGrid: () => <div data-testid="polar-grid" />,
    PolarAngleAxis: ({ dataKey, tick }: any) => (
      <div
        data-testid="polar-angle-axis"
        data-key={dataKey}
        data-tick={JSON.stringify(tick)}
      />
    ),
    PolarRadiusAxis: ({ angle, domain, tick }: any) => (
      <div
        data-testid="polar-radius-axis"
        data-angle={angle}
        data-domain={JSON.stringify(domain)}
        data-tick={JSON.stringify(tick)}
      />
    ),
    Radar: ({ name, dataKey, stroke, fill, fillOpacity, strokeWidth }: any) => (
      <div
        data-testid="radar"
        data-name={name}
        data-key={dataKey}
        data-stroke={stroke}
        data-fill={fill}
        data-fill-opacity={fillOpacity}
        data-stroke-width={strokeWidth}
      />
    ),
    Legend: ({ wrapperStyle, iconType }: any) => (
      <div
        data-testid="legend"
        data-wrapper-style={JSON.stringify(wrapperStyle)}
        data-icon-type={iconType}
      />
    ),
    Tooltip: ({ contentStyle, formatter }: any) => (
      <div
        data-testid="tooltip"
        data-content-style={JSON.stringify(contentStyle)}
        data-has-formatter={!!formatter}
      />
    ),
    CartesianGrid: ({ strokeDasharray }: any) => (
      <div
        data-testid="cartesian-grid"
        data-stroke-dasharray={strokeDasharray}
      />
    ),
    XAxis: ({ dataKey, tick }: any) => (
      <div
        data-testid="x-axis"
        data-key={dataKey}
        data-tick={JSON.stringify(tick)}
      />
    ),
    YAxis: ({ domain, tick }: any) => (
      <div
        data-testid="y-axis"
        data-domain={JSON.stringify(domain)}
        data-tick={JSON.stringify(tick)}
      />
    ),
    Bar: ({ dataKey, fill, name }: any) => (
      <div
        data-testid="bar"
        data-key={dataKey}
        data-fill={fill}
        data-name={name}
      />
    ),
  }
})
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, varsOrDefault?: any) => {
      const translations: Record<string, any> = require('../../../locales/en/common.json')
      const parts = key.split('.')
      let value: any = translations
      for (const part of parts) {
        if (value && typeof value === 'object' && part in value) {
          value = value[part]
        } else {
          return key
        }
      }
      if (typeof value !== 'string') return key
      if (varsOrDefault && typeof varsOrDefault === 'object') {
        for (const [k, v] of Object.entries(varsOrDefault)) {
          value = value.replace(new RegExp(`\\{${k}\\}`, 'g'), String(v))
        }
      }
      return value
    },
    locale: 'en',
  }),
}))


describe('ModelComparisonChart', () => {
  const mockModels = [
    {
      model_id: 'gpt-4',
      metrics: {
        accuracy: 0.95,
        precision: 0.92,
        recall: 0.94,
        f1: 0.93,
      },
    },
    {
      model_id: 'claude-3',
      metrics: {
        accuracy: 0.93,
        precision: 0.91,
        recall: 0.92,
        f1: 0.915,
      },
    },
    {
      model_id: 'llama-2',
      metrics: {
        accuracy: 0.88,
        precision: 0.86,
        recall: 0.87,
        f1: 0.865,
      },
    },
  ]

  const mockMetrics = ['accuracy', 'precision', 'recall', 'f1']

  describe('Radar Chart Visualization', () => {
    it('should render radar chart by default', () => {
      render(<ModelComparisonChart models={mockModels} metrics={mockMetrics} />)

      expect(screen.getByTestId('radar-chart')).toBeInTheDocument()
      expect(screen.queryByTestId('bar-chart')).not.toBeInTheDocument()
    })

    it('should render radar chart with explicit type', () => {
      render(
        <ModelComparisonChart
          models={mockModels}
          metrics={mockMetrics}
          visualizationType="radar"
        />
      )

      expect(screen.getByTestId('radar-chart')).toBeInTheDocument()
    })

    it('should render responsive container with correct height', () => {
      render(
        <ModelComparisonChart
          models={mockModels}
          metrics={mockMetrics}
          height={500}
        />
      )

      const container = screen.getByTestId('responsive-container')
      expect(container).toHaveAttribute('data-height', '500')
    })

    it('should use default height when not specified', () => {
      render(<ModelComparisonChart models={mockModels} metrics={mockMetrics} />)

      const container = screen.getByTestId('responsive-container')
      expect(container).toHaveAttribute('data-height', '400')
    })

    it('should render polar grid', () => {
      render(<ModelComparisonChart models={mockModels} metrics={mockMetrics} />)

      expect(screen.getByTestId('polar-grid')).toBeInTheDocument()
    })

    it('should render polar angle axis with metric key', () => {
      render(<ModelComparisonChart models={mockModels} metrics={mockMetrics} />)

      const axis = screen.getByTestId('polar-angle-axis')
      expect(axis).toHaveAttribute('data-key', 'metric')
    })

    it('should render polar radius axis with correct domain', () => {
      render(<ModelComparisonChart models={mockModels} metrics={mockMetrics} />)

      const axis = screen.getByTestId('polar-radius-axis')
      expect(axis).toHaveAttribute('data-domain', JSON.stringify([0, 1]))
      expect(axis).toHaveAttribute('data-angle', '90')
    })

    it('should render radar for each model', () => {
      render(<ModelComparisonChart models={mockModels} metrics={mockMetrics} />)

      const radars = screen.getAllByTestId('radar')
      expect(radars).toHaveLength(3)
    })

    it('should render radar with correct model name', () => {
      render(<ModelComparisonChart models={mockModels} metrics={mockMetrics} />)

      const radars = screen.getAllByTestId('radar')
      expect(radars[0]).toHaveAttribute('data-name', 'gpt-4')
      expect(radars[1]).toHaveAttribute('data-name', 'claude-3')
      expect(radars[2]).toHaveAttribute('data-name', 'llama-2')
    })

    it('should render radar with correct model key', () => {
      render(<ModelComparisonChart models={mockModels} metrics={mockMetrics} />)

      const radars = screen.getAllByTestId('radar')
      expect(radars[0]).toHaveAttribute('data-key', 'gpt-4')
    })

    it('should apply different colors to each model', () => {
      render(<ModelComparisonChart models={mockModels} metrics={mockMetrics} />)

      const radars = screen.getAllByTestId('radar')
      const colors = radars.map((r) => r.getAttribute('data-stroke'))

      expect(new Set(colors).size).toBe(3)
      expect(colors[0]).toBe('#3b82f6')
      expect(colors[1]).toBe('#10b981')
      expect(colors[2]).toBe('#f59e0b')
    })

    it('should set fill opacity and stroke width', () => {
      render(<ModelComparisonChart models={mockModels} metrics={mockMetrics} />)

      const radar = screen.getAllByTestId('radar')[0]
      expect(radar).toHaveAttribute('data-fill-opacity', '0.3')
      expect(radar).toHaveAttribute('data-stroke-width', '2')
    })

    it('should render legend with circle icons', () => {
      render(<ModelComparisonChart models={mockModels} metrics={mockMetrics} />)

      const legend = screen.getByTestId('legend')
      expect(legend).toHaveAttribute('data-icon-type', 'circle')
    })

    it('should render tooltip', () => {
      render(<ModelComparisonChart models={mockModels} metrics={mockMetrics} />)

      const tooltip = screen.getByTestId('tooltip')
      expect(tooltip).toBeInTheDocument()
      expect(tooltip).toHaveAttribute('data-has-formatter', 'true')
    })

    it('should render title when provided', () => {
      render(
        <ModelComparisonChart
          models={mockModels}
          metrics={mockMetrics}
          title="Model Performance Comparison"
        />
      )

      expect(
        screen.getByText('Model Performance Comparison')
      ).toBeInTheDocument()
    })

    it('should not render title when not provided', () => {
      const { container } = render(
        <ModelComparisonChart models={mockModels} metrics={mockMetrics} />
      )

      const title = container.querySelector('h3')
      expect(title).not.toBeInTheDocument()
    })
  })

  describe('Bar Chart Visualization', () => {
    it('should render bar chart when specified', () => {
      render(
        <ModelComparisonChart
          models={mockModels}
          metrics={mockMetrics}
          visualizationType="bar"
        />
      )

      expect(screen.getByTestId('bar-chart')).toBeInTheDocument()
      expect(screen.queryByTestId('radar-chart')).not.toBeInTheDocument()
    })

    it('should render cartesian grid', () => {
      render(
        <ModelComparisonChart
          models={mockModels}
          metrics={mockMetrics}
          visualizationType="bar"
        />
      )

      const grid = screen.getByTestId('cartesian-grid')
      expect(grid).toHaveAttribute('data-stroke-dasharray', '3 3')
    })

    it('should render x-axis with model key', () => {
      render(
        <ModelComparisonChart
          models={mockModels}
          metrics={mockMetrics}
          visualizationType="bar"
        />
      )

      const xAxis = screen.getByTestId('x-axis')
      expect(xAxis).toHaveAttribute('data-key', 'model')
    })

    it('should render y-axis with correct domain', () => {
      render(
        <ModelComparisonChart
          models={mockModels}
          metrics={mockMetrics}
          visualizationType="bar"
        />
      )

      const yAxis = screen.getByTestId('y-axis')
      expect(yAxis).toHaveAttribute('data-domain', JSON.stringify([0, 1]))
    })

    it('should render bar for each metric', () => {
      render(
        <ModelComparisonChart
          models={mockModels}
          metrics={mockMetrics}
          visualizationType="bar"
        />
      )

      const bars = screen.getAllByTestId('bar')
      expect(bars).toHaveLength(4)
    })

    it('should render bars with correct metric keys', () => {
      render(
        <ModelComparisonChart
          models={mockModels}
          metrics={mockMetrics}
          visualizationType="bar"
        />
      )

      const bars = screen.getAllByTestId('bar')
      expect(bars[0]).toHaveAttribute('data-key', 'accuracy')
      expect(bars[1]).toHaveAttribute('data-key', 'precision')
      expect(bars[2]).toHaveAttribute('data-key', 'recall')
      expect(bars[3]).toHaveAttribute('data-key', 'f1')
    })

    it('should apply different colors to each metric', () => {
      render(
        <ModelComparisonChart
          models={mockModels}
          metrics={mockMetrics}
          visualizationType="bar"
        />
      )

      const bars = screen.getAllByTestId('bar')
      const colors = bars.map((b) => b.getAttribute('data-fill'))

      expect(new Set(colors).size).toBe(4)
    })

    it('should render summary table', () => {
      render(
        <ModelComparisonChart
          models={mockModels}
          metrics={mockMetrics}
          visualizationType="bar"
        />
      )

      expect(screen.getByText('Model')).toBeInTheDocument()
      expect(screen.getByText('Average')).toBeInTheDocument()
    })

    it('should render all model rows in table', () => {
      render(
        <ModelComparisonChart
          models={mockModels}
          metrics={mockMetrics}
          visualizationType="bar"
        />
      )

      expect(screen.getByText('gpt-4')).toBeInTheDocument()
      expect(screen.getByText('claude-3')).toBeInTheDocument()
      expect(screen.getByText('llama-2')).toBeInTheDocument()
    })

    it('should render metric headers in table', () => {
      render(
        <ModelComparisonChart
          models={mockModels}
          metrics={mockMetrics}
          visualizationType="bar"
        />
      )

      expect(screen.getByText('accuracy')).toBeInTheDocument()
      expect(screen.getByText('precision')).toBeInTheDocument()
      expect(screen.getByText('recall')).toBeInTheDocument()
      expect(screen.getByText('f1')).toBeInTheDocument()
    })

    it('should format metric values with three decimals', () => {
      render(
        <ModelComparisonChart
          models={mockModels}
          metrics={mockMetrics}
          visualizationType="bar"
        />
      )

      expect(screen.getAllByText('0.950').length).toBeGreaterThan(0)
      expect(screen.getAllByText('0.920').length).toBeGreaterThan(0)
    })

    it('should calculate and display average for each model', () => {
      render(
        <ModelComparisonChart
          models={mockModels}
          metrics={mockMetrics}
          visualizationType="bar"
        />
      )

      expect(screen.getByText('0.935')).toBeInTheDocument()
    })

    it('should render color indicators in table', () => {
      const { container } = render(
        <ModelComparisonChart
          models={mockModels}
          metrics={mockMetrics}
          visualizationType="bar"
        />
      )

      const indicators = container.querySelectorAll('.h-3.w-3.rounded-full')
      expect(indicators.length).toBeGreaterThan(0)
    })
  })

  describe('Data Transformation', () => {
    it('should transform data correctly for radar chart', () => {
      render(
        <ModelComparisonChart
          models={mockModels}
          metrics={mockMetrics}
          visualizationType="radar"
        />
      )

      const chart = screen.getByTestId('radar-chart')
      const chartData = JSON.parse(
        chart.getAttribute('data-chart-data') || '[]'
      )

      expect(chartData).toHaveLength(4)
      expect(chartData[0]).toHaveProperty('metric', 'accuracy')
      expect(chartData[0]).toHaveProperty('gpt-4', 0.95)
      expect(chartData[0]).toHaveProperty('claude-3', 0.93)
    })

    it('should transform data correctly for bar chart', () => {
      render(
        <ModelComparisonChart
          models={mockModels}
          metrics={mockMetrics}
          visualizationType="bar"
        />
      )

      const chart = screen.getByTestId('bar-chart')
      const chartData = JSON.parse(
        chart.getAttribute('data-chart-data') || '[]'
      )

      expect(chartData).toHaveLength(3)
      expect(chartData[0]).toHaveProperty('model', 'gpt-4')
      expect(chartData[0]).toHaveProperty('accuracy', 0.95)
    })

    it('should handle missing metric values with zero', () => {
      const modelsWithMissing = [
        {
          model_id: 'model-1',
          metrics: {
            accuracy: 0.9,
          },
        },
      ]

      render(
        <ModelComparisonChart
          models={modelsWithMissing}
          metrics={['accuracy', 'precision']}
        />
      )

      const chart = screen.getByTestId('radar-chart')
      const chartData = JSON.parse(
        chart.getAttribute('data-chart-data') || '[]'
      )

      expect(chartData[1]).toHaveProperty('model-1', 0)
    })
  })

  describe('Edge Cases', () => {
    it('should handle empty models array', () => {
      render(<ModelComparisonChart models={[]} metrics={mockMetrics} />)

      expect(screen.getByTestId('radar-chart')).toBeInTheDocument()
    })

    it('should handle empty metrics array', () => {
      render(<ModelComparisonChart models={mockModels} metrics={[]} />)

      expect(screen.getByTestId('radar-chart')).toBeInTheDocument()
    })

    it('should handle single model', () => {
      render(
        <ModelComparisonChart models={[mockModels[0]]} metrics={mockMetrics} />
      )

      const radars = screen.getAllByTestId('radar')
      expect(radars).toHaveLength(1)
    })

    it('should handle single metric', () => {
      render(
        <ModelComparisonChart models={mockModels} metrics={['accuracy']} />
      )

      const chart = screen.getByTestId('radar-chart')
      const chartData = JSON.parse(
        chart.getAttribute('data-chart-data') || '[]'
      )

      expect(chartData).toHaveLength(1)
    })

    it('should cycle colors for more than 6 models', () => {
      const manyModels = Array.from({ length: 8 }, (_, i) => ({
        model_id: `model-${i}`,
        metrics: { accuracy: 0.9 },
      }))

      render(
        <ModelComparisonChart models={manyModels} metrics={['accuracy']} />
      )

      const radars = screen.getAllByTestId('radar')
      expect(radars).toHaveLength(8)

      const colors = radars.map((r) => r.getAttribute('data-stroke'))
      expect(colors[0]).toBe(colors[6])
    })

    it('should handle zero values in metrics', () => {
      const modelsWithZero = [
        {
          model_id: 'model-zero',
          metrics: {
            accuracy: 0,
            precision: 0,
          },
        },
      ]

      render(
        <ModelComparisonChart
          models={modelsWithZero}
          metrics={['accuracy', 'precision']}
          visualizationType="bar"
        />
      )

      expect(screen.getAllByText('0.000').length).toBeGreaterThan(0)
    })

    it('should handle undefined metric values', () => {
      const modelsWithUndefined = [
        {
          model_id: 'model-undefined',
          metrics: {
            accuracy: 0.9,
          },
        },
      ]

      render(
        <ModelComparisonChart
          models={modelsWithUndefined}
          metrics={['accuracy', 'nonexistent']}
          visualizationType="bar"
        />
      )

      expect(screen.getByText('0.000')).toBeInTheDocument()
    })

    it('should calculate average correctly with missing values', () => {
      const modelsWithMissing = [
        {
          model_id: 'incomplete-model',
          metrics: {
            accuracy: 0.8,
            precision: 0.9,
          },
        },
      ]

      render(
        <ModelComparisonChart
          models={modelsWithMissing}
          metrics={['accuracy', 'precision', 'recall']}
          visualizationType="bar"
        />
      )

      expect(screen.getByText('0.567')).toBeInTheDocument()
    })
  })

  describe('Styling and Layout', () => {
    it('should apply correct wrapper styling', () => {
      const { container } = render(
        <ModelComparisonChart models={mockModels} metrics={mockMetrics} />
      )

      const wrapper = container.querySelector('.space-y-2')
      expect(wrapper).toBeInTheDocument()
    })

    it('should apply title styling', () => {
      render(
        <ModelComparisonChart
          models={mockModels}
          metrics={mockMetrics}
          title="Test Title"
        />
      )

      const title = screen.getByText('Test Title')
      expect(title).toHaveClass('text-lg', 'font-medium', 'text-gray-900')
    })

    it('should apply table styling for bar chart', () => {
      const { container } = render(
        <ModelComparisonChart
          models={mockModels}
          metrics={mockMetrics}
          visualizationType="bar"
        />
      )

      const table = container.querySelector('table')
      expect(table).toHaveClass('w-full', 'text-sm')
    })

    it('should apply hover effect to table rows', () => {
      const { container } = render(
        <ModelComparisonChart
          models={mockModels}
          metrics={mockMetrics}
          visualizationType="bar"
        />
      )

      const rows = container.querySelectorAll('tbody tr')
      rows.forEach((row) => {
        expect(row).toHaveClass('hover:bg-gray-50')
      })
    })

    it('should apply tabular-nums class to metric values', () => {
      const { container } = render(
        <ModelComparisonChart
          models={mockModels}
          metrics={mockMetrics}
          visualizationType="bar"
        />
      )

      const cells = container.querySelectorAll('.tabular-nums')
      expect(cells.length).toBeGreaterThan(0)
    })
  })

  describe('Accessibility', () => {
    it('should render table with proper structure', () => {
      const { container } = render(
        <ModelComparisonChart
          models={mockModels}
          metrics={mockMetrics}
          visualizationType="bar"
        />
      )

      const table = container.querySelector('table')
      const thead = table?.querySelector('thead')
      const tbody = table?.querySelector('tbody')

      expect(thead).toBeInTheDocument()
      expect(tbody).toBeInTheDocument()
    })

    it('should render table headers', () => {
      const { container } = render(
        <ModelComparisonChart
          models={mockModels}
          metrics={mockMetrics}
          visualizationType="bar"
        />
      )

      const headers = container.querySelectorAll('thead th')
      expect(headers.length).toBeGreaterThan(0)
    })

    it('should have semantic HTML structure', () => {
      const { container } = render(
        <ModelComparisonChart
          models={mockModels}
          metrics={mockMetrics}
          title="Test"
        />
      )

      const heading = container.querySelector('h3')
      expect(heading).toBeInTheDocument()
    })
  })
})
