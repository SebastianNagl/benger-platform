/**
 * @jest-environment jsdom
 */
import '@testing-library/jest-dom'
import { render } from '@testing-library/react'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (key: string) => key, locale: 'en' }),
}))

// Mock recharts — avoid canvas/SVG rendering issues in jsdom
jest.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: any) => <div data-testid="responsive-container">{children}</div>,
  ComposedChart: ({ children }: any) => <div data-testid="composed-chart">{children}</div>,
  BarChart: ({ children }: any) => <div data-testid="bar-chart">{children}</div>,
  LineChart: ({ children }: any) => <div data-testid="line-chart">{children}</div>,
  Bar: () => <div data-testid="bar" />,
  Line: () => <div data-testid="line" />,
  Cell: () => <div data-testid="cell" />,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  CartesianGrid: () => <div data-testid="cartesian-grid" />,
  Tooltip: () => <div data-testid="tooltip" />,
  Legend: () => <div data-testid="legend" />,
  ReferenceLine: () => <div data-testid="reference-line" />,
}))

import { BoxPlotChart } from '../BoxPlotChart'
import type { BoxPlotData } from '../BoxPlotChart'

describe('BoxPlotChart', () => {
  const sampleData: BoxPlotData[] = [
    { name: 'Model A', min: 0.2, q1: 0.4, median: 0.6, q3: 0.8, max: 0.95 },
    { name: 'Model B', min: 0.1, q1: 0.3, median: 0.5, q3: 0.7, max: 0.9 },
  ]

  it('renders without crash with valid data', () => {
    const { container } = render(<BoxPlotChart data={sampleData} />)
    expect(container).toBeTruthy()
  })

  it('renders with empty data', () => {
    const { container } = render(<BoxPlotChart data={[]} />)
    expect(container).toBeTruthy()
  })

  it('renders chart container', () => {
    const { getByTestId } = render(<BoxPlotChart data={sampleData} />)
    expect(getByTestId('responsive-container')).toBeInTheDocument()
  })

  it('accepts optional title prop', () => {
    const { container } = render(<BoxPlotChart data={sampleData} title="Score Distribution" />)
    expect(container).toBeTruthy()
  })

  it('accepts optional height prop', () => {
    const { container } = render(<BoxPlotChart data={sampleData} height={400} />)
    expect(container).toBeTruthy()
  })
})

// Note: SignificanceHeatmap, EvaluationHeatmap, and HistoricalTrendChart
// use complex recharts/canvas rendering that requires deep mocking.
// They are covered by E2E tests instead of unit tests.
