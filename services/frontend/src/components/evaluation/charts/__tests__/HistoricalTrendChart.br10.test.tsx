/**
 * @jest-environment jsdom
 *
 * Branch coverage tests for HistoricalTrendChart.
 * Targets 5 uncovered branches:
 * - formatDate with different dateRange values
 * - calculateDateRange with empty dates
 * - showConfidenceIntervals with/without CI data
 * - empty chartData display
 */

import '@testing-library/jest-dom'
import { render, screen, fireEvent } from '@testing-library/react'
import { HistoricalTrendChart } from '../HistoricalTrendChart'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'evaluation.charts.trend.historicalTrend': 'Historical Trend',
        'evaluation.charts.trend.range7d': '7D',
        'evaluation.charts.trend.range30d': '30D',
        'evaluation.charts.trend.range90d': '90D',
        'evaluation.charts.trend.rangeAll': 'All',
        'evaluation.charts.trend.noDataForRange': 'No data for this range',
      }
      return translations[key] || key
    },
  }),
}))

jest.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: any) => <div data-testid="responsive-container">{children}</div>,
  LineChart: ({ children, data }: any) => (
    <div data-testid="line-chart" data-points={data?.length || 0}>{children}</div>
  ),
  CartesianGrid: () => <div data-testid="grid" />,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  Tooltip: () => <div data-testid="tooltip" />,
  Legend: () => <div data-testid="legend" />,
  Line: ({ dataKey }: any) => <div data-testid={`line-${dataKey}`} />,
  Area: ({ dataKey }: any) => <div data-testid={`area-${dataKey}`} />,
}))

describe('HistoricalTrendChart', () => {
  const now = new Date()
  const makeDate = (daysAgo: number) => new Date(now.getTime() - daysAgo * 24 * 60 * 60 * 1000).toISOString()

  const sampleData = [
    { date: makeDate(1), model_id: 'gpt4', value: 0.85, ci_lower: 0.80, ci_upper: 0.90 },
    { date: makeDate(5), model_id: 'gpt4', value: 0.82, ci_lower: 0.77, ci_upper: 0.87 },
    { date: makeDate(20), model_id: 'gpt4', value: 0.78 },
    { date: makeDate(60), model_id: 'gpt4', value: 0.75 },
    { date: makeDate(120), model_id: 'gpt4', value: 0.70 },
  ]

  it('renders with data and date range buttons', () => {
    render(
      <HistoricalTrendChart
        data={sampleData}
        modelIds={['gpt4']}
        metric="F1"
      />
    )
    expect(screen.getByText(/F1/)).toBeInTheDocument()
    expect(screen.getByText('7D')).toBeInTheDocument()
    expect(screen.getByText('30D')).toBeInTheDocument()
    expect(screen.getByText('90D')).toBeInTheDocument()
    expect(screen.getByText('All')).toBeInTheDocument()
  })

  it('filters data when 7d range is selected', () => {
    render(
      <HistoricalTrendChart
        data={sampleData}
        modelIds={['gpt4']}
        metric="F1"
      />
    )
    fireEvent.click(screen.getByText('7D'))
    expect(screen.getByTestId('line-chart')).toBeInTheDocument()
  })

  it('filters data when 30d range is selected', () => {
    render(
      <HistoricalTrendChart
        data={sampleData}
        modelIds={['gpt4']}
        metric="F1"
      />
    )
    fireEvent.click(screen.getByText('30D'))
    expect(screen.getByTestId('line-chart')).toBeInTheDocument()
  })

  it('filters data when 90d range is selected', () => {
    render(
      <HistoricalTrendChart
        data={sampleData}
        modelIds={['gpt4']}
        metric="F1"
      />
    )
    fireEvent.click(screen.getByText('90D'))
    expect(screen.getByTestId('line-chart')).toBeInTheDocument()
  })

  it('shows all data by default', () => {
    render(
      <HistoricalTrendChart
        data={sampleData}
        modelIds={['gpt4']}
        metric="F1"
      />
    )
    expect(screen.getByTestId('line-chart')).toBeInTheDocument()
  })

  it('renders with empty data', () => {
    render(
      <HistoricalTrendChart
        data={[]}
        modelIds={['gpt4']}
        metric="F1"
      />
    )
    expect(screen.getByText('No data for this range')).toBeInTheDocument()
  })

  it('renders without confidence intervals', () => {
    render(
      <HistoricalTrendChart
        data={sampleData}
        modelIds={['gpt4']}
        metric="F1"
        showConfidenceIntervals={false}
      />
    )
    expect(screen.getByTestId('line-chart')).toBeInTheDocument()
  })

  it('renders with multiple models', () => {
    const multiData = [
      ...sampleData,
      { date: makeDate(1), model_id: 'claude', value: 0.90 },
      { date: makeDate(5), model_id: 'claude', value: 0.88 },
    ]
    render(
      <HistoricalTrendChart
        data={multiData}
        modelIds={['gpt4', 'claude']}
        metric="F1"
      />
    )
    expect(screen.getByTestId('line-gpt4')).toBeInTheDocument()
    expect(screen.getByTestId('line-claude')).toBeInTheDocument()
  })

  it('renders with values > 1 (non-percentage domain)', () => {
    const bigData = [
      { date: makeDate(1), model_id: 'gpt4', value: 42.5 },
      { date: makeDate(5), model_id: 'gpt4', value: 38.2 },
    ]
    render(
      <HistoricalTrendChart
        data={bigData}
        modelIds={['gpt4']}
        metric="BLEU"
      />
    )
    expect(screen.getByTestId('line-chart')).toBeInTheDocument()
  })
})
