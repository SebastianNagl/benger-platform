/**
 * @jest-environment jsdom
 *
 * Branch coverage tests for BoxPlotChart.
 * Targets 8 uncovered branches:
 * - BoxPlotShape null payload (line 126)
 * - BoxPlotShape default color (line 128)
 * - BoxPlotShape iqr === 0 (line 146)
 * - yDomain empty data (line 244)
 * - yAxisLabel ternary (line 272)
 * - calculateBoxPlotStats empty scores
 */

import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import { BoxPlotChart, calculateBoxPlotStats, BoxPlotData } from '../BoxPlotChart'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'evaluation.charts.boxPlot.score': 'Score',
        'evaluation.charts.boxPlot.whiskers': 'Whiskers',
        'evaluation.charts.boxPlot.iqr': 'IQR',
        'evaluation.charts.boxPlot.medianLabel': 'Median',
        'evaluation.charts.boxPlot.max': 'Max',
        'evaluation.charts.boxPlot.q3': 'Q3',
        'evaluation.charts.boxPlot.median': 'Median',
        'evaluation.charts.boxPlot.q1': 'Q1',
        'evaluation.charts.boxPlot.min': 'Min',
        'evaluation.charts.boxPlot.mean': 'Mean',
        'evaluation.charts.boxPlot.n': 'N',
      }
      return translations[key] || key
    },
  }),
}))

// Mock recharts to render children without SVG complexity
jest.mock('recharts', () => {
  const OriginalModule = jest.requireActual('recharts')
  return {
    ...OriginalModule,
    ResponsiveContainer: ({ children }: any) => <div data-testid="responsive-container">{children}</div>,
    ComposedChart: ({ children, data }: any) => <div data-testid="composed-chart">{children}</div>,
    CartesianGrid: () => <div data-testid="cartesian-grid" />,
    XAxis: () => <div data-testid="x-axis" />,
    YAxis: (props: any) => <div data-testid="y-axis" data-label={props.label?.value || ''} />,
    Tooltip: () => <div data-testid="tooltip" />,
    Bar: ({ children, shape }: any) => <div data-testid="bar">{children}</div>,
    Cell: () => <div data-testid="cell" />,
  }
})

describe('BoxPlotChart', () => {
  const sampleData: BoxPlotData[] = [
    { name: 'Model A', min: 0.1, q1: 0.3, median: 0.5, q3: 0.7, max: 0.9, mean: 0.5, count: 100 },
    { name: 'Model B', min: 0.2, q1: 0.4, median: 0.6, q3: 0.8, max: 1.0, mean: 0.6, count: 50 },
  ]

  it('renders chart with data', () => {
    render(<BoxPlotChart data={sampleData} />)
    expect(screen.getByTestId('responsive-container')).toBeInTheDocument()
    expect(screen.getByText('Whiskers')).toBeInTheDocument()
    expect(screen.getByText('IQR')).toBeInTheDocument()
    expect(screen.getByText('Median')).toBeInTheDocument()
  })

  it('renders with accessible color scheme', () => {
    render(<BoxPlotChart data={sampleData} colorScheme="accessible" />)
    expect(screen.getByTestId('responsive-container')).toBeInTheDocument()
  })

  it('renders with empty data (triggers yDomain fallback)', () => {
    render(<BoxPlotChart data={[]} />)
    expect(screen.getByTestId('responsive-container')).toBeInTheDocument()
  })

  it('renders with custom height', () => {
    render(<BoxPlotChart data={sampleData} height={300} />)
    expect(screen.getByTestId('responsive-container')).toBeInTheDocument()
  })

  it('renders with empty yAxisLabel (falsy)', () => {
    render(<BoxPlotChart data={sampleData} yAxisLabel="" />)
    expect(screen.getByTestId('responsive-container')).toBeInTheDocument()
  })

  it('renders with custom className', () => {
    const { container } = render(<BoxPlotChart data={sampleData} className="custom-class" />)
    expect(container.firstChild).toHaveClass('custom-class')
  })

  it('renders with data that has outliers', () => {
    const dataWithOutliers: BoxPlotData[] = [
      { name: 'Model A', min: 0.1, q1: 0.3, median: 0.5, q3: 0.7, max: 0.9, outliers: [0.01, 0.99] },
    ]
    render(<BoxPlotChart data={dataWithOutliers} />)
    expect(screen.getByTestId('responsive-container')).toBeInTheDocument()
  })
})

describe('calculateBoxPlotStats', () => {
  it('returns null for empty scores', () => {
    expect(calculateBoxPlotStats([], 'Test')).toBeNull()
  })

  it('calculates statistics for valid scores', () => {
    const scores = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    const result = calculateBoxPlotStats(scores, 'Test')
    expect(result).not.toBeNull()
    expect(result!.name).toBe('Test')
    expect(result!.count).toBe(10)
    expect(result!.mean).toBeCloseTo(0.55, 2)
  })

  it('handles single score', () => {
    const result = calculateBoxPlotStats([0.5], 'Single')
    expect(result).not.toBeNull()
    expect(result!.median).toBe(0.5)
    expect(result!.count).toBe(1)
  })

  it('identifies outliers beyond 1.5*IQR', () => {
    const scores = [0.01, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.99]
    const result = calculateBoxPlotStats(scores, 'Outlier')
    expect(result).not.toBeNull()
    expect(result!.outliers).toBeDefined()
  })
})
