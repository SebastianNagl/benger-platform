/**
 * Interval-row views: the forest and bar charts per series, the series x
 * label table, the DynamicChartRenderer routes into them, and the bar mode
 * of the generic forest plot.
 */

import '@testing-library/jest-dom'
import { render, screen, within } from '@testing-library/react'

import { ForestPlot } from '@/components/analysis/ForestPlot'
import {
  intervalRowsFromEstimates,
  intervalRowsFromStatistics,
} from '@/lib/results/intervalRows'
import { makeEstimates } from '@/test-utils/analysisFixtures'
import { DynamicChartRenderer } from '../DynamicChartRenderer'
import { IntervalForestChart, IntervalTable } from '../charts/IntervalCharts'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

jest.mock('../ModelComparisonChart', () => ({
  ModelComparisonChart: ({ visualizationType }: any) => (
    <div data-testid={`model-comparison-${visualizationType}`} />
  ),
}))

const metricRows = intervalRowsFromStatistics({
  by_model: {
    a: {
      metrics: {
        bleu: { mean: 0.4, ci_lower: 0.3, ci_upper: 0.5, n: 4 },
        rouge: { mean: 0.6, ci_lower: 0.5, ci_upper: 0.7, n: 4 },
      },
    },
    b: { metrics: { bleu: { mean: 0.2, ci_lower: 0.1, ci_upper: 0.3, n: 4 } } },
  },
})
const estimateRows = intervalRowsFromEstimates(makeEstimates(), {
  pooledLabel: 'Pooled',
})

describe('IntervalForestChart', () => {
  it('draws one forest plot per series with a legend of the level', () => {
    render(<IntervalForestChart rows={metricRows} />)
    const figures = screen.getAllByRole('figure')
    expect(figures).toHaveLength(2)
    expect(within(figures[0]).getByText('bleu')).toBeInTheDocument()
    expect(within(figures[0]).getAllByTestId('forest-plot-row')).toHaveLength(2)
    expect(within(figures[1]).getAllByTestId('forest-plot-row')).toHaveLength(1)
    expect(
      within(figures[0]).getByText('Estimate with 95% confidence interval'),
    ).toBeInTheDocument()
    // Metric statistics carry no reference value: no null line.
    expect(screen.queryByTestId('forest-plot-null')).toBeNull()
  })

  it('draws the null line of estimates and their engine message', () => {
    render(<IntervalForestChart rows={estimateRows} />)
    expect(screen.getAllByTestId('forest-plot-null')).toHaveLength(2)
    expect(
      screen.getByText("unknown parameter 'x_p:system[sys_a]'"),
    ).toBeInTheDocument()
  })

  it('draws bars in bar mode', () => {
    render(<IntervalForestChart rows={metricRows} mode="bar" />)
    expect(screen.getAllByTestId('forest-plot-bar')).toHaveLength(3)
    expect(screen.queryByTestId('forest-plot-point')).toBeNull()
    expect(screen.getAllByTestId('interval-bar-plot')).toHaveLength(2)
  })

  it('says so when there is nothing to draw', () => {
    render(<IntervalForestChart rows={[]} emptyMessage="Nothing here" />)
    expect(screen.getByText('Nothing here')).toBeInTheDocument()
  })
})

describe('IntervalTable', () => {
  it('lays series out against labels with estimate, interval and p adj.', () => {
    render(<IntervalTable rows={estimateRows} seriesHeader="Contrast" />)
    const table = screen.getByTestId('interval-table')
    const headers = within(table)
      .getAllByRole('columnheader')
      .map((h) => h.textContent)
    expect(headers).toEqual([
      'Contrast',
      'Pooled',
      'system = sys_a',
      'system = sys_b',
    ])
    const body = within(table).getAllByRole('row').slice(1)
    expect(body).toHaveLength(2)
    expect(within(body[0]).getByText('-6')).toBeInTheDocument()
    expect(within(body[0]).getByText('[-8, -4]')).toBeInTheDocument()
    expect(within(body[0]).getByText('p adj. 0.020')).toBeInTheDocument()
    expect(within(body[0]).getByText('p adj. 2E-4')).toBeInTheDocument()
    // The second contrast has only a pooled row: the rest are empty cells.
    expect(within(body[1]).getAllByText('—').length).toBeGreaterThanOrEqual(2)
  })

  it('says so when there is nothing to show', () => {
    render(<IntervalTable rows={[]} seriesHeader="Contrast" />)
    expect(screen.getByText('No data available')).toBeInTheDocument()
  })
})

describe('DynamicChartRenderer with interval rows', () => {
  it('draws the forest view from interval rows next to model data', () => {
    render(
      <DynamicChartRenderer
        chartType="forest"
        models={[{ model_id: 'a', metrics: { bleu: 0.4 } }]}
        metrics={['bleu']}
        intervalRows={metricRows}
      />,
    )
    expect(screen.getByTestId('interval-forest-chart')).toBeInTheDocument()
  })

  it('shows the empty message for a forest view without rows', () => {
    render(
      <DynamicChartRenderer
        chartType="forest"
        models={[{ model_id: 'a', metrics: { bleu: 0.4 } }]}
        metrics={['bleu']}
        emptyMessage="No forest"
      />,
    )
    expect(screen.getByText('No forest')).toBeInTheDocument()
  })

  it('draws bars and the table from interval rows without models', async () => {
    const { rerender } = render(
      <DynamicChartRenderer
        chartType="bar"
        models={[]}
        metrics={[]}
        intervalRows={estimateRows}
      />,
    )
    expect(screen.getAllByTestId('forest-plot-bar').length).toBeGreaterThan(0)
    expect(screen.queryByTestId('model-comparison-bar')).toBeNull()
    rerender(
      <DynamicChartRenderer
        chartType="table"
        models={[]}
        metrics={[]}
        intervalRows={estimateRows}
        intervalSeriesHeader="Contrast"
      />,
    )
    expect(await screen.findByTestId('interval-table')).toBeInTheDocument()
    expect(screen.getByText('Contrast')).toBeInTheDocument()
  })

  it('keeps the model bar chart for metric data', () => {
    render(
      <DynamicChartRenderer
        chartType="bar"
        models={[{ model_id: 'a', metrics: { bleu: 0.4 } }]}
        metrics={['bleu']}
      />,
    )
    expect(screen.getByTestId('model-comparison-bar')).toBeInTheDocument()
  })
})

describe('ForestPlot bar mode', () => {
  it('starts bars at the null value and keeps the whisker', () => {
    render(
      <ForestPlot
        mode="bar"
        nullValue={1}
        ariaLabel="bars"
        rows={[
          { id: 'a', label: 'a', estimate: 3, lower: 2, upper: 4 },
          { id: 'b', label: 'b', estimate: null, lower: null, upper: null },
        ]}
      />,
    )
    const bars = screen.getAllByTestId('forest-plot-bar')
    expect(bars).toHaveLength(1)
    expect(Number(bars[0].getAttribute('width'))).toBeGreaterThan(0)
    expect(screen.getByTestId('forest-plot-null')).toBeInTheDocument()
  })

  it('draws bars from zero without a null value', () => {
    render(
      <ForestPlot
        mode="bar"
        nullValue={null}
        ariaLabel="bars"
        rows={[{ id: 'a', label: 'a', estimate: -2, lower: -3, upper: -1 }]}
      />,
    )
    expect(screen.getByTestId('forest-plot-bar')).toBeInTheDocument()
  })
})
