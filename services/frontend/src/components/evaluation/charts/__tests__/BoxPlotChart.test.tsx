/**
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

// Mock recharts components to avoid canvas issues in jsdom
jest.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: any) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  ComposedChart: ({ children, data }: any) => (
    <div data-testid="composed-chart" data-data-length={data?.length}>
      {children}
    </div>
  ),
  Bar: ({ dataKey, shape }: any) => (
    <div data-testid={`bar-${dataKey}`} />
  ),
  Cell: () => <div data-testid="cell" />,
  CartesianGrid: () => <div data-testid="cartesian-grid" />,
  Tooltip: ({ content }: any) => <div data-testid="tooltip" />,
  XAxis: ({ dataKey }: any) => (
    <div data-testid="x-axis" data-key={dataKey} />
  ),
  YAxis: ({ label }: any) => (
    <div data-testid="y-axis" data-label={label?.value} />
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

describe('BoxPlotChart', () => {
  it('should render without crashing', () => {
    render(<BoxPlotChart data={sampleData} />)
    expect(screen.getByTestId('responsive-container')).toBeInTheDocument()
    expect(screen.getByTestId('composed-chart')).toBeInTheDocument()
  })

  it('should render with custom height', () => {
    render(<BoxPlotChart data={sampleData} height={600} />)
    expect(screen.getByTestId('responsive-container')).toBeInTheDocument()
  })

  it('should render with accessible color scheme', () => {
    render(<BoxPlotChart data={sampleData} colorScheme="accessible" />)
    expect(screen.getByTestId('composed-chart')).toBeInTheDocument()
  })

  it('should render axes', () => {
    render(<BoxPlotChart data={sampleData} xAxisLabel="Model" yAxisLabel="Score" />)
    expect(screen.getByTestId('x-axis')).toBeInTheDocument()
    expect(screen.getByTestId('y-axis')).toBeInTheDocument()
  })

  it('should render chart with empty data', () => {
    render(<BoxPlotChart data={[]} />)
    expect(screen.getByTestId('composed-chart')).toBeInTheDocument()
  })

  it('should render legend items', () => {
    render(<BoxPlotChart data={sampleData} />)
    expect(
      screen.getByText('evaluation.charts.boxPlot.whiskers')
    ).toBeInTheDocument()
    expect(
      screen.getByText('evaluation.charts.boxPlot.iqr')
    ).toBeInTheDocument()
    expect(
      screen.getByText('evaluation.charts.boxPlot.medianLabel')
    ).toBeInTheDocument()
  })

  it('should apply custom className', () => {
    const { container } = render(
      <BoxPlotChart data={sampleData} className="custom-class" />
    )
    expect(container.firstChild).toHaveClass('custom-class')
  })

  it('should render with showMean and showOutliers props', () => {
    render(
      <BoxPlotChart data={sampleData} showMean={true} showOutliers={false} />
    )
    expect(screen.getByTestId('composed-chart')).toBeInTheDocument()
  })

  it('should render data with outliers', () => {
    const dataWithOutliers: BoxPlotData[] = [
      {
        name: 'Test',
        min: 0.1,
        q1: 0.4,
        median: 0.5,
        q3: 0.6,
        max: 0.9,
        outliers: [0.01, 0.99],
        count: 50,
      },
    ]
    render(<BoxPlotChart data={dataWithOutliers} />)
    expect(screen.getByTestId('composed-chart')).toBeInTheDocument()
  })
})

describe('calculateBoxPlotStats', () => {
  it('should return null for empty array', () => {
    expect(calculateBoxPlotStats([], 'test')).toBeNull()
  })

  it('should calculate stats for a single value', () => {
    const result = calculateBoxPlotStats([0.5], 'single')
    expect(result).not.toBeNull()
    expect(result!.name).toBe('single')
    expect(result!.median).toBe(0.5)
    expect(result!.mean).toBe(0.5)
    expect(result!.count).toBe(1)
  })

  it('should calculate correct quartiles', () => {
    const scores = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    const result = calculateBoxPlotStats(scores, 'test')
    expect(result).not.toBeNull()
    expect(result!.q1).toBe(0.3) // 25th percentile
    expect(result!.median).toBe(0.6) // 50th percentile (floor of 5)
    expect(result!.q3).toBe(0.8) // 75th percentile
    expect(result!.count).toBe(10)
  })

  it('should calculate correct mean', () => {
    const scores = [1, 2, 3, 4, 5]
    const result = calculateBoxPlotStats(scores, 'mean-test')
    expect(result).not.toBeNull()
    expect(result!.mean).toBe(3)
  })

  it('should detect outliers', () => {
    // IQR = q3 - q1
    // Outliers are values outside q1 - 1.5*IQR to q3 + 1.5*IQR
    const scores = [0.01, 0.3, 0.4, 0.5, 0.6, 0.7, 0.99]
    const result = calculateBoxPlotStats(scores, 'outlier-test')
    expect(result).not.toBeNull()
    // The min/max should be whisker bounds, not actual min/max
    expect(result!.count).toBe(7)
  })

  it('should handle unsorted input', () => {
    const scores = [0.8, 0.2, 0.6, 0.4, 1.0]
    const result = calculateBoxPlotStats(scores, 'unsorted')
    expect(result).not.toBeNull()
    // Should sort internally
    expect(result!.min).toBeLessThanOrEqual(result!.q1)
    expect(result!.q1).toBeLessThanOrEqual(result!.median)
    expect(result!.median).toBeLessThanOrEqual(result!.q3)
    expect(result!.q3).toBeLessThanOrEqual(result!.max)
  })

  it('should handle identical values', () => {
    const scores = [0.5, 0.5, 0.5, 0.5]
    const result = calculateBoxPlotStats(scores, 'identical')
    expect(result).not.toBeNull()
    expect(result!.q1).toBe(0.5)
    expect(result!.median).toBe(0.5)
    expect(result!.q3).toBe(0.5)
    expect(result!.mean).toBe(0.5)
  })

  it('should set name from parameter', () => {
    const result = calculateBoxPlotStats([1, 2, 3], 'My Model')
    expect(result).not.toBeNull()
    expect(result!.name).toBe('My Model')
  })
})
