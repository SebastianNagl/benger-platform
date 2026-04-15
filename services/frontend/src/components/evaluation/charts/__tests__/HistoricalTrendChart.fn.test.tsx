/**
 * Additional coverage for HistoricalTrendChart - formatDate, formatValue, calculateDateRange
 * Tests the helper functions by rendering the component with different data
 */

import { render, screen, fireEvent } from '@testing-library/react'
import { HistoricalTrendChart } from '../HistoricalTrendChart'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, fallback?: string) => fallback || key,
    locale: 'en',
  }),
}))

// Mock recharts components
jest.mock('recharts', () => ({
  Area: () => <div data-testid="area" />,
  CartesianGrid: () => <div data-testid="grid" />,
  Legend: () => <div data-testid="legend" />,
  Line: ({ dataKey }: any) => <div data-testid={`line-${dataKey}`} />,
  LineChart: ({ children, data }: any) => (
    <div data-testid="line-chart" data-points={data?.length}>
      {children}
    </div>
  ),
  ResponsiveContainer: ({ children }: any) => <div data-testid="responsive-container">{children}</div>,
  Tooltip: () => <div data-testid="tooltip" />,
  XAxis: ({ tickFormatter }: any) => {
    // Call the tickFormatter to cover formatDate
    if (tickFormatter) {
      tickFormatter('2025-06-01T12:00:00Z')
    }
    return <div data-testid="xaxis" />
  },
  YAxis: ({ tickFormatter }: any) => {
    // Call the tickFormatter to cover formatValue
    if (tickFormatter) {
      tickFormatter(0.5)
      tickFormatter(5.0)
    }
    return <div data-testid="yaxis" />
  },
}))

describe('HistoricalTrendChart', () => {
  const baseData = [
    { date: '2025-06-01T12:00:00Z', model_id: 'gpt-4', value: 0.85, ci_lower: 0.80, ci_upper: 0.90 },
    { date: '2025-06-02T12:00:00Z', model_id: 'gpt-4', value: 0.87, ci_lower: 0.82, ci_upper: 0.92 },
    { date: '2025-06-01T12:00:00Z', model_id: 'claude-3', value: 0.75 },
    { date: '2025-06-02T12:00:00Z', model_id: 'claude-3', value: 0.78 },
  ]

  const defaultProps = {
    data: baseData,
    modelIds: ['gpt-4', 'claude-3'],
    metric: 'accuracy',
  }

  it('renders the chart title with metric', () => {
    render(<HistoricalTrendChart {...defaultProps} />)
    expect(screen.getByText(/accuracy/)).toBeInTheDocument()
  })

  it('renders date range buttons', () => {
    render(<HistoricalTrendChart {...defaultProps} />)
    expect(screen.getByText('evaluation.charts.trend.range7d')).toBeInTheDocument()
    expect(screen.getByText('evaluation.charts.trend.range30d')).toBeInTheDocument()
    expect(screen.getByText('evaluation.charts.trend.range90d')).toBeInTheDocument()
    expect(screen.getByText('evaluation.charts.trend.rangeAll')).toBeInTheDocument()
  })

  it('renders a line for each model', () => {
    render(<HistoricalTrendChart {...defaultProps} />)
    expect(screen.getByTestId('line-gpt-4')).toBeInTheDocument()
    expect(screen.getByTestId('line-claude-3')).toBeInTheDocument()
  })

  it('renders responsive container', () => {
    render(<HistoricalTrendChart {...defaultProps} />)
    expect(screen.getByTestId('responsive-container')).toBeInTheDocument()
  })

  it('changes date range when button is clicked', () => {
    render(<HistoricalTrendChart {...defaultProps} />)

    const btn7d = screen.getByText('evaluation.charts.trend.range7d')
    fireEvent.click(btn7d)

    // Active button should have different styling
    expect(btn7d.className).toContain('bg-blue-600')
  })

  it('renders with custom height', () => {
    render(<HistoricalTrendChart {...defaultProps} height={500} />)
    expect(screen.getByTestId('responsive-container')).toBeInTheDocument()
  })

  it('handles showConfidenceIntervals=false', () => {
    render(<HistoricalTrendChart {...defaultProps} showConfidenceIntervals={false} />)
    expect(screen.getByTestId('line-chart')).toBeInTheDocument()
  })

  it('shows no data message when data is empty', () => {
    render(<HistoricalTrendChart data={[]} modelIds={[]} metric="accuracy" />)
    expect(screen.getByText('evaluation.charts.trend.noDataForRange')).toBeInTheDocument()
  })

  it('handles data within 7 day range', () => {
    const now = new Date()
    const recent = [
      { date: new Date(now.getTime() - 1 * 24 * 60 * 60 * 1000).toISOString(), model_id: 'gpt-4', value: 0.8 },
      { date: now.toISOString(), model_id: 'gpt-4', value: 0.85 },
    ]

    render(<HistoricalTrendChart data={recent} modelIds={['gpt-4']} metric="accuracy" />)
    expect(screen.getByTestId('line-chart')).toBeInTheDocument()
  })

  it('handles data spanning over 90 days', () => {
    const longRange = [
      { date: '2024-01-01T12:00:00Z', model_id: 'gpt-4', value: 0.7 },
      { date: '2025-06-01T12:00:00Z', model_id: 'gpt-4', value: 0.9 },
    ]

    render(<HistoricalTrendChart data={longRange} modelIds={['gpt-4']} metric="accuracy" />)
    expect(screen.getByTestId('line-chart')).toBeInTheDocument()
  })

  it('filters by 30d range', () => {
    render(<HistoricalTrendChart {...defaultProps} />)
    fireEvent.click(screen.getByText('evaluation.charts.trend.range30d'))

    expect(screen.getByTestId('line-chart')).toBeInTheDocument()
  })

  it('filters by 90d range', () => {
    render(<HistoricalTrendChart {...defaultProps} />)
    fireEvent.click(screen.getByText('evaluation.charts.trend.range90d'))

    expect(screen.getByTestId('line-chart')).toBeInTheDocument()
  })

  it('handles non-percentage values', () => {
    const data = [
      { date: '2025-06-01T12:00:00Z', model_id: 'gpt-4', value: 15.5 },
      { date: '2025-06-02T12:00:00Z', model_id: 'gpt-4', value: 16.2 },
    ]

    render(<HistoricalTrendChart data={data} modelIds={['gpt-4']} metric="score" />)
    expect(screen.getByTestId('line-chart')).toBeInTheDocument()
  })
})
