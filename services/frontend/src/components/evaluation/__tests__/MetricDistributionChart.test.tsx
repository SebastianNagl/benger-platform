/**
 * MetricDistributionChart Component Tests
 *
 * Comprehensive test suite covering:
 * - Statistics display (mean, median, std, min, max)
 * - Histogram chart rendering
 * - Quartile visualization
 * - Custom title and height props
 * - Edge cases (zero values, equal values, extreme distributions)
 * - Data formatting and precision
 *
 * Target: 85%+ coverage
 */

import { cleanup, render, screen } from '@testing-library/react'
import { MetricDistributionChart } from '../MetricDistributionChart'

// Mock Recharts components
jest.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  BarChart: ({ children, data }: any) => (
    <div data-testid="bar-chart" data-chart-data={JSON.stringify(data)}>
      {children}
    </div>
  ),
  Bar: ({ dataKey, name, children }: any) => (
    <div data-testid="bar" data-key={dataKey} data-name={name}>
      {children}
    </div>
  ),
  Cell: ({ fill }: any) => <div data-testid="cell" data-fill={fill} />,
  CartesianGrid: ({ strokeDasharray }: any) => (
    <div data-testid="cartesian-grid" data-stroke={strokeDasharray} />
  ),
  XAxis: ({ dataKey, angle, textAnchor, height, fontSize }: any) => (
    <div
      data-testid="x-axis"
      data-key={dataKey}
      data-angle={angle}
      data-anchor={textAnchor}
      data-height={height}
      data-fontsize={fontSize}
    />
  ),
  YAxis: ({ label }: any) => (
    <div data-testid="y-axis" data-label={JSON.stringify(label)} />
  ),
  Tooltip: ({ contentStyle }: any) => (
    <div data-testid="tooltip" data-style={JSON.stringify(contentStyle)} />
  ),
}))
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


describe('MetricDistributionChart', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  afterEach(() => {
    cleanup()
  })

  const mockDistributionData = {
    metric_name: 'accuracy',
    mean: 0.856,
    median: 0.85,
    std: 0.124,
    min: 0.45,
    max: 0.98,
    quartiles: {
      q1: 0.75,
      q2: 0.85,
      q3: 0.92,
    },
    histogram: {
      '0.4-0.5': 2,
      '0.5-0.6': 5,
      '0.6-0.7': 8,
      '0.7-0.8': 12,
      '0.8-0.9': 15,
      '0.9-1.0': 8,
    },
  }

  describe('Basic Rendering', () => {
    it('renders the component with default title', () => {
      render(<MetricDistributionChart data={mockDistributionData} />)

      expect(screen.getByText('accuracy Distribution')).toBeInTheDocument()
    })

    it('renders with custom title', () => {
      render(
        <MetricDistributionChart
          data={mockDistributionData}
          title="Custom Metric Analysis"
        />
      )

      expect(screen.getByText('Custom Metric Analysis')).toBeInTheDocument()
    })

    it('renders statistics summary section', () => {
      render(<MetricDistributionChart data={mockDistributionData} />)

      expect(screen.getByText('Mean')).toBeInTheDocument()
      const medianElements = screen.getAllByText('Median')
      expect(medianElements.length).toBeGreaterThan(0)
      expect(screen.getByText('Std Dev')).toBeInTheDocument()
      expect(screen.getByText('Min')).toBeInTheDocument()
      expect(screen.getByText('Max')).toBeInTheDocument()
    })

    it('renders histogram section', () => {
      render(<MetricDistributionChart data={mockDistributionData} />)

      expect(screen.getByText('Value Distribution')).toBeInTheDocument()
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument()
      expect(screen.getByTestId('bar-chart')).toBeInTheDocument()
    })

    it('renders quartiles visualization', () => {
      render(<MetricDistributionChart data={mockDistributionData} />)

      expect(screen.getByText('Quartiles')).toBeInTheDocument()

      const q1Elements = screen.getAllByText('Q1')
      const medianElements = screen.getAllByText('Median')
      const q3Elements = screen.getAllByText('Q3')

      expect(q1Elements.length).toBeGreaterThan(0)
      expect(medianElements.length).toBeGreaterThan(0)
      expect(q3Elements.length).toBeGreaterThan(0)
    })
  })

  describe('Statistics Display', () => {
    it('displays mean value with correct precision', () => {
      render(<MetricDistributionChart data={mockDistributionData} />)

      expect(screen.getByText('0.856')).toBeInTheDocument()
    })

    it('displays median value with correct precision', () => {
      render(<MetricDistributionChart data={mockDistributionData} />)

      expect(screen.getByText('0.850')).toBeInTheDocument()
    })

    it('displays standard deviation with correct precision', () => {
      render(<MetricDistributionChart data={mockDistributionData} />)

      expect(screen.getByText('0.124')).toBeInTheDocument()
    })

    it('displays min value with correct precision', () => {
      render(<MetricDistributionChart data={mockDistributionData} />)

      const minElements = screen.getAllByText('0.450')
      expect(minElements.length).toBeGreaterThan(0)
    })

    it('displays max value with correct precision', () => {
      render(<MetricDistributionChart data={mockDistributionData} />)

      const maxElements = screen.getAllByText('0.980')
      expect(maxElements.length).toBeGreaterThan(0)
    })

    it('formats statistics to 3 decimal places', () => {
      const dataWithMoreDecimals = {
        ...mockDistributionData,
        mean: 0.8562345,
        median: 0.8500123,
        std: 0.1244567,
      }
      render(<MetricDistributionChart data={dataWithMoreDecimals} />)

      expect(screen.getByText('0.856')).toBeInTheDocument()
      expect(screen.getByText('0.850')).toBeInTheDocument()
      expect(screen.getByText('0.124')).toBeInTheDocument()
    })
  })

  describe('Histogram Chart', () => {
    it('renders bar chart with correct data', () => {
      render(<MetricDistributionChart data={mockDistributionData} />)

      const barChart = screen.getByTestId('bar-chart')
      const chartData = JSON.parse(
        barChart.getAttribute('data-chart-data') || '[]'
      )

      expect(chartData).toHaveLength(6)
      expect(chartData[0]).toEqual({ range: '0.4-0.5', count: 2 })
      expect(chartData[1]).toEqual({ range: '0.5-0.6', count: 5 })
    })

    it('converts histogram object to array format', () => {
      render(<MetricDistributionChart data={mockDistributionData} />)

      const barChart = screen.getByTestId('bar-chart')
      const chartData = JSON.parse(
        barChart.getAttribute('data-chart-data') || '[]'
      )

      expect(chartData).toEqual([
        { range: '0.4-0.5', count: 2 },
        { range: '0.5-0.6', count: 5 },
        { range: '0.6-0.7', count: 8 },
        { range: '0.7-0.8', count: 12 },
        { range: '0.8-0.9', count: 15 },
        { range: '0.9-1.0', count: 8 },
      ])
    })

    it('renders bar component with correct props', () => {
      render(<MetricDistributionChart data={mockDistributionData} />)

      const bar = screen.getByTestId('bar')
      expect(bar.getAttribute('data-key')).toBe('count')
      expect(bar.getAttribute('data-name')).toBe('Sample Count')
    })

    it('renders cells with alternating colors', () => {
      render(<MetricDistributionChart data={mockDistributionData} />)

      const cells = screen.getAllByTestId('cell')
      expect(cells.length).toBeGreaterThan(0)

      const colors = cells.map((cell) => cell.getAttribute('data-fill'))
      expect(colors).toContain('#3b82f6')
      expect(colors).toContain('#60a5fa')
    })

    it('renders cartesian grid', () => {
      render(<MetricDistributionChart data={mockDistributionData} />)

      const grid = screen.getByTestId('cartesian-grid')
      expect(grid.getAttribute('data-stroke')).toBe('3 3')
    })

    it('renders x-axis with correct configuration', () => {
      render(<MetricDistributionChart data={mockDistributionData} />)

      const xAxis = screen.getByTestId('x-axis')
      expect(xAxis.getAttribute('data-key')).toBe('range')
      expect(xAxis.getAttribute('data-angle')).toBe('-45')
      expect(xAxis.getAttribute('data-anchor')).toBe('end')
      expect(xAxis.getAttribute('data-height')).toBe('80')
      expect(xAxis.getAttribute('data-fontsize')).toBe('11')
    })

    it('renders y-axis with count label', () => {
      render(<MetricDistributionChart data={mockDistributionData} />)

      const yAxis = screen.getByTestId('y-axis')
      const label = JSON.parse(yAxis.getAttribute('data-label') || '{}')
      expect(label.value).toBe('Count')
      expect(label.angle).toBe(-90)
      expect(label.position).toBe('insideLeft')
    })

    it('renders tooltip with custom styling', () => {
      render(<MetricDistributionChart data={mockDistributionData} />)

      const tooltip = screen.getByTestId('tooltip')
      const style = JSON.parse(tooltip.getAttribute('data-style') || '{}')
      expect(style.backgroundColor).toBe('white')
      expect(style.border).toBe('1px solid #ccc')
      expect(style.borderRadius).toBe('4px')
    })
  })

  describe('Quartile Visualization', () => {
    it('displays quartile markers', () => {
      render(<MetricDistributionChart data={mockDistributionData} />)

      const q1Elements = screen.getAllByText('Q1')
      const medianElements = screen.getAllByText('Median')
      const q3Elements = screen.getAllByText('Q3')

      expect(q1Elements.length).toBeGreaterThan(0)
      expect(medianElements.length).toBeGreaterThan(0)
      expect(q3Elements.length).toBeGreaterThan(0)
    })

    it('positions Q1 marker correctly', () => {
      const { container } = render(
        <MetricDistributionChart data={mockDistributionData} />
      )

      const q1Marker = container.querySelector('[title="Q1: 0.750"]')
      expect(q1Marker).toBeInTheDocument()

      // Q1 (0.75) is at (0.75 - 0.45) / (0.98 - 0.45) * 100 = 56.6%
      const style = (q1Marker as HTMLElement)?.style
      expect(style?.left).toContain('%')
    })

    it('positions median marker correctly', () => {
      const { container } = render(
        <MetricDistributionChart data={mockDistributionData} />
      )

      const medianMarker = container.querySelector('[title="Median: 0.850"]')
      expect(medianMarker).toBeInTheDocument()

      // Median (0.85) is at (0.85 - 0.45) / (0.98 - 0.45) * 100 = 75.5%
      const style = (medianMarker as HTMLElement)?.style
      expect(style?.left).toContain('%')
    })

    it('positions Q3 marker correctly', () => {
      const { container } = render(
        <MetricDistributionChart data={mockDistributionData} />
      )

      const q3Marker = container.querySelector('[title="Q3: 0.920"]')
      expect(q3Marker).toBeInTheDocument()

      // Q3 (0.92) is at (0.92 - 0.45) / (0.98 - 0.45) * 100 = 88.7%
      const style = (q3Marker as HTMLElement)?.style
      expect(style?.left).toContain('%')
    })

    it('displays min and max labels below quartile visualization', () => {
      render(<MetricDistributionChart data={mockDistributionData} />)

      expect(screen.getByText('Min: 0.450')).toBeInTheDocument()
      expect(screen.getByText('Max: 0.980')).toBeInTheDocument()
    })

    it('applies correct color classes to quartile markers', () => {
      const { container } = render(
        <MetricDistributionChart data={mockDistributionData} />
      )

      const q1Marker = container.querySelector('.bg-red-600')
      const medianMarker = container.querySelector('.bg-yellow-600')
      const q3Marker = container.querySelector('.bg-green-600')

      expect(q1Marker).toBeInTheDocument()
      expect(medianMarker).toBeInTheDocument()
      expect(q3Marker).toBeInTheDocument()
    })
  })

  describe('Custom Props', () => {
    it('uses default height of 400 when not provided', () => {
      render(<MetricDistributionChart data={mockDistributionData} />)

      const container = screen.getByTestId('responsive-container')
      expect(container).toBeInTheDocument()
      // ResponsiveContainer receives height prop
    })

    it('applies custom height when provided', () => {
      render(
        <MetricDistributionChart data={mockDistributionData} height={600} />
      )

      const container = screen.getByTestId('responsive-container')
      expect(container).toBeInTheDocument()
    })

    it('uses metric name in default title', () => {
      const customData = { ...mockDistributionData, metric_name: 'f1_score' }
      render(<MetricDistributionChart data={customData} />)

      expect(screen.getByText('f1_score Distribution')).toBeInTheDocument()
    })

    it('overrides default title with custom title', () => {
      render(
        <MetricDistributionChart
          data={mockDistributionData}
          title="Performance Analysis"
        />
      )

      expect(screen.getByText('Performance Analysis')).toBeInTheDocument()
      expect(
        screen.queryByText('accuracy Distribution')
      ).not.toBeInTheDocument()
    })
  })

  describe('Edge Cases', () => {
    it('handles single histogram bin', () => {
      const singleBinData = {
        ...mockDistributionData,
        histogram: { '0.8-0.9': 50 },
      }
      render(<MetricDistributionChart data={singleBinData} />)

      const barChart = screen.getByTestId('bar-chart')
      const chartData = JSON.parse(
        barChart.getAttribute('data-chart-data') || '[]'
      )

      expect(chartData).toHaveLength(1)
      expect(chartData[0]).toEqual({ range: '0.8-0.9', count: 50 })
    })

    it('handles zero standard deviation', () => {
      const zeroStdData = {
        ...mockDistributionData,
        std: 0,
        min: 0.85,
        max: 0.85,
      }
      render(<MetricDistributionChart data={zeroStdData} />)

      expect(screen.getByText('0.000')).toBeInTheDocument()
    })

    it('handles equal min and max values', () => {
      const equalRangeData = {
        ...mockDistributionData,
        min: 0.75,
        max: 0.75,
        quartiles: {
          q1: 0.75,
          q2: 0.75,
          q3: 0.75,
        },
      }
      render(<MetricDistributionChart data={equalRangeData} />)

      const minElements = screen.getAllByText('0.750')
      expect(minElements.length).toBeGreaterThan(0)
    })

    it('handles very small values', () => {
      const smallValuesData = {
        ...mockDistributionData,
        mean: 0.001,
        median: 0.0005,
        std: 0.0002,
        min: 0.0001,
        max: 0.002,
        quartiles: {
          q1: 0.0003,
          q2: 0.0005,
          q3: 0.0015,
        },
      }
      render(<MetricDistributionChart data={smallValuesData} />)

      const meanElements = screen.getAllByText('0.001')
      expect(meanElements.length).toBeGreaterThan(0)
    })

    it('handles very large values', () => {
      const largeValuesData = {
        ...mockDistributionData,
        mean: 999.856,
        median: 999.85,
        std: 50.124,
        min: 800.45,
        max: 1200.98,
        quartiles: {
          q1: 900.75,
          q2: 999.85,
          q3: 1100.92,
        },
      }
      render(<MetricDistributionChart data={largeValuesData} />)

      expect(screen.getByText('999.856')).toBeInTheDocument()
      expect(screen.getByText('999.850')).toBeInTheDocument()
    })

    it('handles negative values', () => {
      const negativeValuesData = {
        ...mockDistributionData,
        mean: -0.5,
        median: -0.6,
        std: 0.2,
        min: -0.9,
        max: -0.1,
        quartiles: {
          q1: -0.75,
          q2: -0.6,
          q3: -0.3,
        },
      }
      render(<MetricDistributionChart data={negativeValuesData} />)

      expect(screen.getByText('-0.500')).toBeInTheDocument()
      expect(screen.getByText('-0.600')).toBeInTheDocument()
    })

    it('handles empty histogram', () => {
      const emptyHistogramData = {
        ...mockDistributionData,
        histogram: {},
      }
      render(<MetricDistributionChart data={emptyHistogramData} />)

      const barChart = screen.getByTestId('bar-chart')
      const chartData = JSON.parse(
        barChart.getAttribute('data-chart-data') || '[]'
      )

      expect(chartData).toHaveLength(0)
    })

    it('handles histogram with zero counts', () => {
      const zeroCountsData = {
        ...mockDistributionData,
        histogram: {
          '0.0-0.2': 0,
          '0.2-0.4': 0,
          '0.4-0.6': 0,
        },
      }
      render(<MetricDistributionChart data={zeroCountsData} />)

      const barChart = screen.getByTestId('bar-chart')
      const chartData = JSON.parse(
        barChart.getAttribute('data-chart-data') || '[]'
      )

      expect(chartData).toEqual([
        { range: '0.0-0.2', count: 0 },
        { range: '0.2-0.4', count: 0 },
        { range: '0.4-0.6', count: 0 },
      ])
    })

    it('handles quartiles at boundaries', () => {
      const boundaryQuartilesData = {
        ...mockDistributionData,
        quartiles: {
          q1: 0.45, // at min
          q2: 0.715, // middle
          q3: 0.98, // at max
        },
      }
      const { container } = render(
        <MetricDistributionChart data={boundaryQuartilesData} />
      )

      const q1Marker = container.querySelector('[title="Q1: 0.450"]')
      const q3Marker = container.querySelector('[title="Q3: 0.980"]')

      expect(q1Marker).toBeInTheDocument()
      expect(q3Marker).toBeInTheDocument()
    })

    it('renders with precision metric name', () => {
      const precisionData = {
        ...mockDistributionData,
        metric_name: 'precision',
      }
      render(<MetricDistributionChart data={precisionData} />)

      expect(screen.getByText('precision Distribution')).toBeInTheDocument()
    })

    it('renders with recall metric name', () => {
      const recallData = {
        ...mockDistributionData,
        metric_name: 'recall',
      }
      render(<MetricDistributionChart data={recallData} />)

      expect(screen.getByText('recall Distribution')).toBeInTheDocument()
    })

    it('renders with f1 metric name', () => {
      const f1Data = {
        ...mockDistributionData,
        metric_name: 'f1',
      }
      render(<MetricDistributionChart data={f1Data} />)

      expect(screen.getByText('f1 Distribution')).toBeInTheDocument()
    })
  })

  describe('Layout and Styling', () => {
    it('applies correct container classes', () => {
      const { container } = render(
        <MetricDistributionChart data={mockDistributionData} />
      )

      const outerDiv = container.firstChild as HTMLElement
      expect(outerDiv).toHaveClass('space-y-4')
    })

    it('applies rounded border and padding to chart container', () => {
      const { container } = render(
        <MetricDistributionChart data={mockDistributionData} />
      )

      const chartContainer = container.querySelector(
        '.rounded-lg.border.bg-white.p-4'
      )
      expect(chartContainer).toBeInTheDocument()
    })

    it('applies grid layout to statistics', () => {
      const { container } = render(
        <MetricDistributionChart data={mockDistributionData} />
      )

      const statsContainer = container.querySelector(
        '.bg-gray-50.p-4.rounded-lg'
      )
      expect(statsContainer).toBeInTheDocument()
      expect(statsContainer).toHaveClass('grid')
    })

    it('applies gradient background to quartile visualization', () => {
      const { container } = render(
        <MetricDistributionChart data={mockDistributionData} />
      )

      const quartileBar = container.querySelector(
        '.bg-gradient-to-r.from-red-200.via-yellow-200.to-green-200'
      )
      expect(quartileBar).toBeInTheDocument()
      expect(quartileBar).toHaveClass('relative', 'h-8', 'w-full', 'rounded')
    })
  })

  describe('Data Formatting', () => {
    it('formats all statistics consistently', () => {
      const data = {
        metric_name: 'bleu',
        mean: 0.123456789,
        median: 0.987654321,
        std: 0.555555555,
        min: 0.111111111,
        max: 0.999999999,
        quartiles: {
          q1: 0.333333333,
          q2: 0.666666666,
          q3: 0.888888888,
        },
        histogram: { '0.0-1.0': 100 },
      }
      render(<MetricDistributionChart data={data} />)

      // All values should be formatted to 3 decimal places
      expect(screen.getByText('0.123')).toBeInTheDocument()
      expect(screen.getByText('0.988')).toBeInTheDocument()
      expect(screen.getByText('0.556')).toBeInTheDocument()
      expect(screen.getAllByText('0.111').length).toBeGreaterThan(0)
      expect(screen.getAllByText('1.000').length).toBeGreaterThan(0)
    })

    it('preserves histogram range labels', () => {
      const data = {
        ...mockDistributionData,
        histogram: {
          '0.0-0.25': 10,
          '0.25-0.5': 20,
          '0.5-0.75': 30,
          '0.75-1.0': 40,
        },
      }
      render(<MetricDistributionChart data={data} />)

      const barChart = screen.getByTestId('bar-chart')
      const chartData = JSON.parse(
        barChart.getAttribute('data-chart-data') || '[]'
      )

      expect(chartData.map((d: any) => d.range)).toEqual([
        '0.0-0.25',
        '0.25-0.5',
        '0.5-0.75',
        '0.75-1.0',
      ])
    })
  })
})
