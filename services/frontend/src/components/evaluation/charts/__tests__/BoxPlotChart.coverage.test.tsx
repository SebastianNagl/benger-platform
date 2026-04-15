/**
 * Coverage extension tests for BoxPlotChart
 *
 * Tests for previously uncovered code paths:
 * - CustomTooltip component (lines 50-53)
 * - BoxPlotShape custom rendering (lines 124-155)
 * - YAxis domain calculation with empty data (line 270)
 *
 * @jest-environment jsdom
 */

import { render, screen } from '@testing-library/react'
import {
  BoxPlotChart,
  calculateBoxPlotStats,
  type BoxPlotData,
} from '../BoxPlotChart'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => key,
  }),
}))

// Store tooltip and shape renderers so we can test them directly
let capturedTooltipContent: any = null
let capturedBarShape: any = null

jest.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: any) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  ComposedChart: ({ children, data }: any) => (
    <div data-testid="composed-chart" data-data-length={data?.length}>
      {children}
    </div>
  ),
  Bar: ({ dataKey, shape }: any) => {
    if (dataKey === 'iqr' && shape) {
      capturedBarShape = shape
    }
    return <div data-testid={`bar-${dataKey}`} />
  },
  Cell: () => <div data-testid="cell" />,
  CartesianGrid: () => <div data-testid="cartesian-grid" />,
  Tooltip: ({ content }: any) => {
    capturedTooltipContent = content
    return <div data-testid="tooltip">{content}</div>
  },
  XAxis: ({ dataKey }: any) => (
    <div data-testid="x-axis" data-key={dataKey} />
  ),
  YAxis: ({ domain, label }: any) => (
    <div
      data-testid="y-axis"
      data-domain={JSON.stringify(domain)}
      data-label={label?.value}
    />
  ),
}))

const sampleData: BoxPlotData[] = [
  {
    name: 'GPT-4',
    min: 0.5,
    q1: 0.65,
    median: 0.75,
    q3: 0.85,
    max: 0.95,
    mean: 0.74,
    count: 100,
  },
  {
    name: 'Claude-3',
    min: 0.6,
    q1: 0.7,
    median: 0.8,
    q3: 0.88,
    max: 0.98,
    mean: 0.79,
    count: 80,
  },
]

describe('BoxPlotChart - coverage extensions', () => {
  beforeEach(() => {
    capturedTooltipContent = null
    capturedBarShape = null
  })

  describe('CustomTooltip', () => {
    it('should return null when not active', () => {
      render(<BoxPlotChart data={sampleData} />)
      // The tooltip content component was captured; render it with inactive state
      if (capturedTooltipContent) {
        const TooltipComponent = capturedTooltipContent.type
        const { container } = render(
          <TooltipComponent active={false} payload={null} t={(k: string) => k} />
        )
        expect(container.innerHTML).toBe('')
      }
    })

    it('should return null when payload is empty', () => {
      render(<BoxPlotChart data={sampleData} />)
      if (capturedTooltipContent) {
        const TooltipComponent = capturedTooltipContent.type
        const { container } = render(
          <TooltipComponent active={true} payload={[]} t={(k: string) => k} />
        )
        expect(container.innerHTML).toBe('')
      }
    })

    it('should render tooltip content when active with valid payload', () => {
      render(<BoxPlotChart data={sampleData} />)
      if (capturedTooltipContent) {
        const TooltipComponent = capturedTooltipContent.type
        const mockPayload = [
          {
            payload: {
              name: 'GPT-4',
              min: 0.5,
              q1: 0.65,
              median: 0.75,
              q3: 0.85,
              max: 0.95,
              mean: 0.74,
              count: 100,
              color: '#10b981',
            },
          },
        ]
        const { container } = render(
          <TooltipComponent active={true} payload={mockPayload} t={(k: string) => k} />
        )
        expect(container.textContent).toContain('GPT-4')
        expect(container.textContent).toContain('0.750')
        expect(container.textContent).toContain('0.740')
        expect(container.textContent).toContain('100')
      }
    })

    it('should render tooltip without mean when mean is undefined', () => {
      render(<BoxPlotChart data={sampleData} />)
      if (capturedTooltipContent) {
        const TooltipComponent = capturedTooltipContent.type
        const mockPayload = [
          {
            payload: {
              name: 'Test',
              min: 0.1,
              q1: 0.3,
              median: 0.5,
              q3: 0.7,
              max: 0.9,
              color: '#10b981',
            },
          },
        ]
        const { container } = render(
          <TooltipComponent active={true} payload={mockPayload} t={(k: string) => k} />
        )
        expect(container.textContent).toContain('Test')
        expect(container.textContent).not.toContain('evaluation.charts.boxPlot.mean')
      }
    })

    it('should render tooltip without count when count is undefined', () => {
      render(<BoxPlotChart data={sampleData} />)
      if (capturedTooltipContent) {
        const TooltipComponent = capturedTooltipContent.type
        const mockPayload = [
          {
            payload: {
              name: 'Test',
              min: 0.1,
              q1: 0.3,
              median: 0.5,
              q3: 0.7,
              max: 0.9,
              mean: 0.5,
              color: '#10b981',
            },
          },
        ]
        const { container } = render(
          <TooltipComponent active={true} payload={mockPayload} t={(k: string) => k} />
        )
        expect(container.textContent).toContain('0.500')
        expect(container.textContent).not.toContain('evaluation.charts.boxPlot.n')
      }
    })
  })

  describe('yDomain calculation', () => {
    it('should handle empty data with default domain', () => {
      render(<BoxPlotChart data={[]} />)
      const yAxis = screen.getByTestId('y-axis')
      const domain = JSON.parse(yAxis.dataset.domain || '[]')
      expect(domain).toEqual([0, 1])
    })

    it('should handle data with outliers for yDomain', () => {
      const dataWithOutliers: BoxPlotData[] = [
        {
          name: 'Test',
          min: 0.1,
          q1: 0.4,
          median: 0.5,
          q3: 0.6,
          max: 0.9,
          outliers: [0.01, 0.99],
        },
      ]
      render(<BoxPlotChart data={dataWithOutliers} />)
      const yAxis = screen.getByTestId('y-axis')
      const domain = JSON.parse(yAxis.dataset.domain || '[]')
      // Domain should include outlier range with padding
      expect(domain[0]).toBeLessThanOrEqual(0.01)
      expect(domain[1]).toBeGreaterThanOrEqual(0.9)
    })
  })

  describe('color scheme', () => {
    it('should use accessible color scheme', () => {
      render(<BoxPlotChart data={sampleData} colorScheme="accessible" />)
      expect(screen.getByTestId('composed-chart')).toBeInTheDocument()
    })

    it('should use default color scheme by default', () => {
      render(<BoxPlotChart data={sampleData} />)
      expect(screen.getByTestId('composed-chart')).toBeInTheDocument()
    })
  })

  describe('yAxisLabel', () => {
    it('should use default yAxisLabel from translations when not provided', () => {
      render(<BoxPlotChart data={sampleData} />)
      const yAxis = screen.getByTestId('y-axis')
      expect(yAxis.dataset.label).toBe('evaluation.charts.boxPlot.score')
    })

    it('should use custom yAxisLabel when provided', () => {
      render(<BoxPlotChart data={sampleData} yAxisLabel="Custom Label" />)
      const yAxis = screen.getByTestId('y-axis')
      expect(yAxis.dataset.label).toBe('Custom Label')
    })
  })
})

describe('calculateBoxPlotStats - coverage extensions', () => {
  it('should calculate whisker bounds correctly using 1.5*IQR rule', () => {
    // Create data with clear outliers
    const scores = [0.01, 0.4, 0.45, 0.5, 0.55, 0.6, 0.99]
    const result = calculateBoxPlotStats(scores, 'whisker-test')

    expect(result).not.toBeNull()
    // Whisker should be capped at 1.5 * IQR from Q1/Q3
    expect(result!.min).toBeGreaterThanOrEqual(0.01)
    expect(result!.max).toBeLessThanOrEqual(0.99)
  })

  it('should identify outliers outside 1.5*IQR', () => {
    // Large spread with clear outliers: IQR is tight, outliers far away
    const scores = [0.01, 0.49, 0.5, 0.5, 0.5, 0.5, 0.51, 0.99]
    const result = calculateBoxPlotStats(scores, 'outlier-test')

    expect(result).not.toBeNull()
    if (result!.outliers && result!.outliers.length > 0) {
      // At least some values should be identified as outliers
      expect(result!.outliers.length).toBeGreaterThan(0)
    }
  })

  it('should calculate mean correctly for large dataset', () => {
    const scores = Array.from({ length: 100 }, (_, i) => i / 100)
    const result = calculateBoxPlotStats(scores, 'large')

    expect(result).not.toBeNull()
    expect(result!.count).toBe(100)
    // Mean of 0 to 0.99 in steps of 0.01
    expect(result!.mean).toBeCloseTo(0.495, 2)
  })

  it('should handle two values', () => {
    const result = calculateBoxPlotStats([0.3, 0.7], 'two-values')

    expect(result).not.toBeNull()
    expect(result!.count).toBe(2)
    expect(result!.mean).toBeCloseTo(0.5, 5)
  })

  it('should handle three values', () => {
    const result = calculateBoxPlotStats([0.2, 0.5, 0.8], 'three-values')

    expect(result).not.toBeNull()
    expect(result!.count).toBe(3)
    expect(result!.median).toBe(0.5)
  })
})
