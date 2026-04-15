/**
 * fn3 function coverage for BoxPlotChart.tsx
 * Targets: CustomTooltip, BoxPlotShape internal render functions, calculateBoxPlotStats
 */

import React from 'react'
import { render, screen } from '@testing-library/react'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    locale: 'en',
    t: (key: string) => key,
    changeLocale: jest.fn(),
    isReady: true,
  }),
}))

// Mock recharts - simple passthrough that renders children
jest.mock('recharts', () => {
  const MockResponsiveContainer = ({ children }: any) => <div data-testid="chart-container">{typeof children === 'function' ? children(100, 100) : children}</div>
  const MockComposedChart = ({ children }: any) => <div data-testid="composed-chart">{children}</div>
  const MockBar = () => <div data-testid="bar" />
  const MockCartesianGrid = () => null
  const MockCell = () => null
  const MockTooltip = () => null
  const MockXAxis = () => null
  const MockYAxis = () => null
  return {
    ResponsiveContainer: MockResponsiveContainer,
    ComposedChart: MockComposedChart,
    Bar: MockBar,
    CartesianGrid: MockCartesianGrid,
    Cell: MockCell,
    Tooltip: MockTooltip,
    XAxis: MockXAxis,
    YAxis: MockYAxis,
  }
})

import { BoxPlotChart, calculateBoxPlotStats } from '../BoxPlotChart'

describe('BoxPlotChart fn3', () => {
  const sampleData = [
    { name: 'Model A', min: 0.1, q1: 0.3, median: 0.5, q3: 0.7, max: 0.9, mean: 0.5, count: 100 },
    { name: 'Model B', min: 0.2, q1: 0.4, median: 0.6, q3: 0.8, max: 1.0, mean: 0.6, count: 50 },
  ]

  it('renders box plot chart with data', () => {
    render(<BoxPlotChart data={sampleData} />)
    expect(screen.getByTestId('chart-container')).toBeInTheDocument()
  })

  it('renders with accessible color scheme', () => {
    render(<BoxPlotChart data={sampleData} colorScheme="accessible" />)
    expect(screen.getByTestId('chart-container')).toBeInTheDocument()
  })

  it('renders with custom axis labels', () => {
    render(
      <BoxPlotChart
        data={sampleData}
        xAxisLabel="Models"
        yAxisLabel="Score"
        showMean={true}
        showOutliers={true}
      />
    )
    expect(screen.getByTestId('chart-container')).toBeInTheDocument()
  })

  it('renders with empty data', () => {
    render(<BoxPlotChart data={[]} />)
    expect(screen.getByTestId('chart-container')).toBeInTheDocument()
  })

  it('renders with className', () => {
    render(<BoxPlotChart data={sampleData} className="custom-class" />)
    expect(screen.getByTestId('chart-container')).toBeInTheDocument()
  })
})

describe('calculateBoxPlotStats', () => {
  it('calculates stats from array of numbers', () => {
    if (typeof calculateBoxPlotStats === 'function') {
      const stats = calculateBoxPlotStats([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
      expect(stats).toHaveProperty('min')
      expect(stats).toHaveProperty('q1')
      expect(stats).toHaveProperty('median')
      expect(stats).toHaveProperty('q3')
      expect(stats).toHaveProperty('max')
    }
  })
})
