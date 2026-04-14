/**
 * @jest-environment jsdom
 *
 * Branch coverage: DynamicChartRenderer.tsx
 * Targets uncovered branches:
 *   - L92: model.model_name || model.model_id (model without model_name)
 *   - L205: metrics[0] || 'Score' (significance heatmap with empty metrics)
 *   - L257-258: ScoreHeatmap default args (height, colorScheme)
 *   - L263-274: accessible color scheme branches (all score ranges)
 *   - L271-274: default color scheme branches (all score ranges)
 *   - L299: model.model_name || model.model_id in ScoreHeatmap
 */

import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import { DynamicChartRenderer } from '../DynamicChartRenderer'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, any>) =>
      key === 'evaluation.charts.model' ? 'Model' : key,
  }),
}))

jest.mock('@/components/shared/LoadingSpinner', () => ({
  LoadingSpinner: () => <div data-testid="loading-spinner" />,
}))

jest.mock('../ModelComparisonChart', () => ({
  ModelComparisonChart: () => <div data-testid="model-chart" />,
}))

jest.mock('../EvaluationResultsTable', () => ({
  EvaluationResultsTable: () => <div data-testid="results-table" />,
}))

jest.mock('../charts/BoxPlotChart', () => ({
  BoxPlotChart: () => <div data-testid="box-plot-chart" />,
  calculateBoxPlotStats: (scores: number[], label: string) => ({
    label,
    min: Math.min(...scores),
    q1: 0,
    median: 0,
    q3: 0,
    max: Math.max(...scores),
    mean: 0,
    outliers: [],
  }),
}))

jest.mock('../charts/SignificanceHeatmap', () => ({
  SignificanceHeatmap: ({ modelIds, metric }: any) => (
    <div data-testid="significance-heatmap" data-metric={metric}>
      {modelIds.length} models
    </div>
  ),
}))

describe('DynamicChartRenderer br6 - uncovered branches', () => {
  describe('model.model_name fallback to model_id (L92)', () => {
    it('uses model_id when model_name is undefined in box plot data', () => {
      const models = [
        {
          model_id: 'custom-model-123',
          // model_name intentionally omitted
          metrics: { score: 0.8 },
          scores: [0.7, 0.8, 0.9],
        },
      ]
      render(
        <DynamicChartRenderer
          chartType="box"
          models={models}
          metrics={['score']}
        />
      )
      expect(screen.getByTestId('box-plot-chart')).toBeInTheDocument()
    })
  })

  describe('ScoreHeatmap accessible color scheme branches', () => {
    // All four ranges for accessible scheme: >=0.7, >=0.5, >=0.3, <0.3
    it('shows blue-500 for scores >= 0.7 in accessible scheme', () => {
      const models = [
        { model_id: 'a', model_name: 'A', metrics: { score: 0.75 } },
        { model_id: 'b', model_name: 'B', metrics: { score: 0.85 } },
      ]
      const { container } = render(
        <DynamicChartRenderer
          chartType="heatmap"
          models={models}
          metrics={['score']}
          colorScheme="accessible"
        />
      )
      expect(container.querySelector('.bg-blue-500')).toBeInTheDocument()
    })

    it('shows blue-200 for scores 0.5-0.7 in accessible scheme', () => {
      const models = [
        { model_id: 'a', model_name: 'A', metrics: { score: 0.55 } },
        { model_id: 'b', model_name: 'B', metrics: { score: 0.60 } },
      ]
      const { container } = render(
        <DynamicChartRenderer
          chartType="heatmap"
          models={models}
          metrics={['score']}
          colorScheme="accessible"
        />
      )
      expect(container.querySelector('.bg-blue-200')).toBeInTheDocument()
    })

    it('shows red-200 for scores 0.3-0.5 in accessible scheme', () => {
      const models = [
        { model_id: 'a', model_name: 'A', metrics: { score: 0.35 } },
        { model_id: 'b', model_name: 'B', metrics: { score: 0.40 } },
      ]
      const { container } = render(
        <DynamicChartRenderer
          chartType="heatmap"
          models={models}
          metrics={['score']}
          colorScheme="accessible"
        />
      )
      expect(container.querySelector('.bg-red-200')).toBeInTheDocument()
    })

    it('shows red-500 for scores < 0.3 in accessible scheme', () => {
      const models = [
        { model_id: 'a', model_name: 'A', metrics: { score: 0.15 } },
        { model_id: 'b', model_name: 'B', metrics: { score: 0.10 } },
      ]
      const { container } = render(
        <DynamicChartRenderer
          chartType="heatmap"
          models={models}
          metrics={['score']}
          colorScheme="accessible"
        />
      )
      expect(container.querySelector('.bg-red-500')).toBeInTheDocument()
    })
  })

  describe('ScoreHeatmap default color scheme branches', () => {
    it('shows yellow-400 for scores 0.5-0.7 in default scheme', () => {
      const models = [
        { model_id: 'a', model_name: 'A', metrics: { score: 0.55 } },
        { model_id: 'b', model_name: 'B', metrics: { score: 0.60 } },
      ]
      const { container } = render(
        <DynamicChartRenderer
          chartType="heatmap"
          models={models}
          metrics={['score']}
          colorScheme="default"
        />
      )
      expect(container.querySelector('.bg-yellow-400')).toBeInTheDocument()
    })

    it('shows orange-400 for scores 0.3-0.5 in default scheme', () => {
      const models = [
        { model_id: 'a', model_name: 'A', metrics: { score: 0.35 } },
        { model_id: 'b', model_name: 'B', metrics: { score: 0.40 } },
      ]
      const { container } = render(
        <DynamicChartRenderer
          chartType="heatmap"
          models={models}
          metrics={['score']}
          colorScheme="default"
        />
      )
      expect(container.querySelector('.bg-orange-400')).toBeInTheDocument()
    })

    it('shows red-500 for scores < 0.3 in default scheme', () => {
      const models = [
        { model_id: 'a', model_name: 'A', metrics: { score: 0.15 } },
        { model_id: 'b', model_name: 'B', metrics: { score: 0.10 } },
      ]
      const { container } = render(
        <DynamicChartRenderer
          chartType="heatmap"
          models={models}
          metrics={['score']}
          colorScheme="default"
        />
      )
      expect(container.querySelector('.bg-red-500')).toBeInTheDocument()
    })
  })

  describe('ScoreHeatmap model_name fallback (L299)', () => {
    it('uses model_id when model_name is undefined in heatmap', () => {
      const models = [
        { model_id: 'model-abc', metrics: { score: 0.8 } },
        { model_id: 'model-def', metrics: { score: 0.6 } },
      ]
      render(
        <DynamicChartRenderer
          chartType="heatmap"
          models={models}
          metrics={['score']}
        />
      )
      expect(screen.getByText('model-abc')).toBeInTheDocument()
      expect(screen.getByText('model-def')).toBeInTheDocument()
    })
  })

  describe('undefined metric value in heatmap (L307-309)', () => {
    it('shows dash for missing metric', () => {
      const models = [
        { model_id: 'a', model_name: 'A', metrics: { score: 0.8 } },
        { model_id: 'b', model_name: 'B', metrics: {} },
      ]
      render(
        <DynamicChartRenderer
          chartType="heatmap"
          models={models}
          metrics={['score']}
        />
      )
      // Should show dash for model B's missing score
      const dashes = screen.getAllByText('\u2014') // em dash
      expect(dashes.length).toBeGreaterThan(0)
    })
  })
})
