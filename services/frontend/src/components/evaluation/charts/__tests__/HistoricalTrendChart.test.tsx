/**
 * Tests for HistoricalTrendChart component
 * Tests date filtering, data transformation, rendering, and format helpers
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { render, screen, fireEvent } from '@testing-library/react'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (key: string) => key, locale: 'en' }),
}))

// Mock recharts
const mockLineChartProps: any[] = []
jest.mock('recharts', () => ({
  ResponsiveContainer: ({ children, height }: any) => (
    <div data-testid="responsive-container" data-height={height}>{children}</div>
  ),
  LineChart: ({ children, data }: any) => {
    mockLineChartProps.push({ data })
    return <div data-testid="line-chart" data-items={data?.length || 0}>{children}</div>
  },
  Line: ({ dataKey, stroke, name }: any) => (
    <div data-testid={`line-${dataKey}`} data-stroke={stroke} data-name={name} />
  ),
  Area: ({ dataKey, fill }: any) => (
    <div data-testid={`area-${dataKey}`} data-fill={fill} />
  ),
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  CartesianGrid: () => <div data-testid="cartesian-grid" />,
  Tooltip: () => <div data-testid="tooltip" />,
  Legend: () => <div data-testid="legend" />,
}))

import { HistoricalTrendChart } from '../HistoricalTrendChart'

describe('HistoricalTrendChart', () => {
  const modelIds = ['gpt-4', 'llama-3']

  const data = [
    { date: '2025-01-01T00:00:00Z', model_id: 'gpt-4', value: 0.8 },
    { date: '2025-01-01T00:00:00Z', model_id: 'llama-3', value: 0.7 },
    { date: '2025-02-01T00:00:00Z', model_id: 'gpt-4', value: 0.85 },
    { date: '2025-02-01T00:00:00Z', model_id: 'llama-3', value: 0.75 },
    { date: '2025-03-01T00:00:00Z', model_id: 'gpt-4', value: 0.9 },
    { date: '2025-03-01T00:00:00Z', model_id: 'llama-3', value: 0.82 },
  ]

  beforeEach(() => {
    mockLineChartProps.length = 0
  })

  it('renders without crashing', () => {
    const { container } = render(
      <HistoricalTrendChart data={data} modelIds={modelIds} metric="F1" />
    )
    expect(container).toBeTruthy()
  })

  it('renders the chart container', () => {
    render(
      <HistoricalTrendChart data={data} modelIds={modelIds} metric="F1" />
    )
    expect(screen.getByTestId('responsive-container')).toBeInTheDocument()
    expect(screen.getByTestId('line-chart')).toBeInTheDocument()
  })

  it('renders a line for each model', () => {
    render(
      <HistoricalTrendChart data={data} modelIds={modelIds} metric="F1" />
    )
    expect(screen.getByTestId('line-gpt-4')).toBeInTheDocument()
    expect(screen.getByTestId('line-llama-3')).toBeInTheDocument()
  })

  it('assigns different colors to each model line', () => {
    render(
      <HistoricalTrendChart data={data} modelIds={modelIds} metric="F1" />
    )
    const line1 = screen.getByTestId('line-gpt-4')
    const line2 = screen.getByTestId('line-llama-3')
    expect(line1.getAttribute('data-stroke')).not.toBe(line2.getAttribute('data-stroke'))
  })

  it('displays the metric name in the heading', () => {
    render(
      <HistoricalTrendChart data={data} modelIds={modelIds} metric="BLEU" />
    )
    expect(screen.getByText(/BLEU/)).toBeInTheDocument()
  })

  it('renders date range filter buttons', () => {
    render(
      <HistoricalTrendChart data={data} modelIds={modelIds} metric="F1" />
    )
    expect(screen.getByText('evaluation.charts.trend.range7d')).toBeInTheDocument()
    expect(screen.getByText('evaluation.charts.trend.range30d')).toBeInTheDocument()
    expect(screen.getByText('evaluation.charts.trend.range90d')).toBeInTheDocument()
    expect(screen.getByText('evaluation.charts.trend.rangeAll')).toBeInTheDocument()
  })

  it('defaults to "all" date range', () => {
    render(
      <HistoricalTrendChart data={data} modelIds={modelIds} metric="F1" />
    )
    // The "all" button should have the active class
    const allButton = screen.getByText('evaluation.charts.trend.rangeAll')
    expect(allButton.className).toContain('bg-blue-600')
  })

  it('passes all data points when "all" range is selected', () => {
    render(
      <HistoricalTrendChart data={data} modelIds={modelIds} metric="F1" />
    )
    const lastProps = mockLineChartProps[mockLineChartProps.length - 1]
    // 3 unique dates
    expect(lastProps.data.length).toBe(3)
  })

  it('transforms data into pivoted format with model values as columns', () => {
    render(
      <HistoricalTrendChart data={data} modelIds={modelIds} metric="F1" />
    )
    const lastProps = mockLineChartProps[mockLineChartProps.length - 1]
    const firstPoint = lastProps.data[0]
    expect(firstPoint.date).toBe('2025-01-01T00:00:00Z')
    expect(firstPoint['gpt-4']).toBe(0.8)
    expect(firstPoint['llama-3']).toBe(0.7)
  })

  it('sorts data chronologically', () => {
    const unsortedData = [
      { date: '2025-03-01T00:00:00Z', model_id: 'gpt-4', value: 0.9 },
      { date: '2025-01-01T00:00:00Z', model_id: 'gpt-4', value: 0.8 },
      { date: '2025-02-01T00:00:00Z', model_id: 'gpt-4', value: 0.85 },
    ]
    render(
      <HistoricalTrendChart data={unsortedData} modelIds={['gpt-4']} metric="F1" />
    )
    const lastProps = mockLineChartProps[mockLineChartProps.length - 1]
    expect(lastProps.data[0].date).toBe('2025-01-01T00:00:00Z')
    expect(lastProps.data[1].date).toBe('2025-02-01T00:00:00Z')
    expect(lastProps.data[2].date).toBe('2025-03-01T00:00:00Z')
  })

  it('filters data when a date range is selected', () => {
    // Create data that spans from very old to now
    const now = new Date()
    const recentData = [
      { date: new Date(now.getTime() - 2 * 24 * 60 * 60 * 1000).toISOString(), model_id: 'gpt-4', value: 0.9 },
      { date: new Date(now.getTime() - 100 * 24 * 60 * 60 * 1000).toISOString(), model_id: 'gpt-4', value: 0.7 },
    ]

    render(
      <HistoricalTrendChart data={recentData} modelIds={['gpt-4']} metric="F1" />
    )

    // Click 7d button
    fireEvent.click(screen.getByText('evaluation.charts.trend.range7d'))

    const lastProps = mockLineChartProps[mockLineChartProps.length - 1]
    // Only the recent data point (2 days ago) should remain
    expect(lastProps.data.length).toBe(1)
  })

  it('uses custom height when provided', () => {
    render(
      <HistoricalTrendChart data={data} modelIds={modelIds} metric="F1" height={500} />
    )
    const container = screen.getByTestId('responsive-container')
    expect(container.getAttribute('data-height')).toBe('500')
  })

  it('defaults height to 300', () => {
    render(
      <HistoricalTrendChart data={data} modelIds={modelIds} metric="F1" />
    )
    const container = screen.getByTestId('responsive-container')
    expect(container.getAttribute('data-height')).toBe('300')
  })

  it('shows no-data message when filtered data is empty', () => {
    // Data is from 2025, so 7d filter relative to "now" (2026) will return empty
    render(
      <HistoricalTrendChart data={data} modelIds={modelIds} metric="F1" />
    )
    fireEvent.click(screen.getByText('evaluation.charts.trend.range7d'))
    expect(screen.getByText('evaluation.charts.trend.noDataForRange')).toBeInTheDocument()
  })

  it('handles empty data array gracefully', () => {
    render(
      <HistoricalTrendChart data={[]} modelIds={modelIds} metric="F1" />
    )
    expect(screen.getByTestId('line-chart')).toBeInTheDocument()
  })

  it('renders confidence interval areas when showConfidenceIntervals is true and CI data exists', () => {
    const ciData = [
      { date: '2025-01-01', model_id: 'gpt-4', value: 0.8, ci_lower: 0.75, ci_upper: 0.85 },
      { date: '2025-02-01', model_id: 'gpt-4', value: 0.9, ci_lower: 0.85, ci_upper: 0.95 },
    ]
    render(
      <HistoricalTrendChart
        data={ciData}
        modelIds={['gpt-4']}
        metric="F1"
        showConfidenceIntervals={true}
      />
    )
    expect(screen.getByTestId('area-gpt-4_ci')).toBeInTheDocument()
  })

  it('does not render CI areas when showConfidenceIntervals is false', () => {
    const ciData = [
      { date: '2025-01-01', model_id: 'gpt-4', value: 0.8, ci_lower: 0.75, ci_upper: 0.85 },
    ]
    render(
      <HistoricalTrendChart
        data={ciData}
        modelIds={['gpt-4']}
        metric="F1"
        showConfidenceIntervals={false}
      />
    )
    expect(screen.queryByTestId('area-gpt-4_ci')).not.toBeInTheDocument()
  })

  it('highlights the active date range button', () => {
    render(
      <HistoricalTrendChart data={data} modelIds={modelIds} metric="F1" />
    )
    fireEvent.click(screen.getByText('evaluation.charts.trend.range30d'))
    const button30d = screen.getByText('evaluation.charts.trend.range30d')
    expect(button30d.className).toContain('bg-blue-600')
    // "all" button should no longer be active
    const allButton = screen.getByText('evaluation.charts.trend.rangeAll')
    expect(allButton.className).not.toContain('bg-blue-600')
  })
})
