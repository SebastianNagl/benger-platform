/**
 * fn3 function coverage for ModelComparisonChart.tsx
 * Targets: getMetricValue, getErrorValue, MissingDataWarning, bar visualization
 */

import React from 'react'
import { render, screen } from '@testing-library/react'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    locale: 'en',
    t: (key: string, vars?: any) => {
      if (vars?.models) return `Missing data for: ${vars.models}`
      return key
    },
    changeLocale: jest.fn(),
    isReady: true,
  }),
}))

// Mock recharts to render simple divs
jest.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: any) => <div data-testid="responsive-container">{children}</div>,
  RadarChart: ({ children }: any) => <div data-testid="radar-chart">{children}</div>,
  BarChart: ({ children }: any) => <div data-testid="bar-chart">{children}</div>,
  Radar: () => <div data-testid="radar" />,
  Bar: () => <div data-testid="bar" />,
  CartesianGrid: () => null,
  ErrorBar: () => null,
  Legend: () => null,
  PolarAngleAxis: () => null,
  PolarGrid: () => null,
  PolarRadiusAxis: () => null,
  Tooltip: () => null,
  XAxis: () => null,
  YAxis: () => null,
}))

import { ModelComparisonChart } from '../ModelComparisonChart'

describe('ModelComparisonChart fn3', () => {
  const sampleModels = [
    {
      model_id: 'gpt-4',
      metrics: {
        accuracy: 0.95,
        f1: { value: 0.9, error: 0.02, confidenceInterval: { lower: 0.88, upper: 0.92 } },
      },
    },
    {
      model_id: 'claude-3',
      metrics: {
        accuracy: 0.92,
        f1: 0.88,
      },
    },
  ]

  it('renders radar chart by default', () => {
    render(
      <ModelComparisonChart
        models={sampleModels}
        metrics={['accuracy', 'f1']}
      />
    )
    expect(screen.getByTestId('radar-chart')).toBeInTheDocument()
  })

  it('renders bar chart when visualizationType=bar', () => {
    render(
      <ModelComparisonChart
        models={sampleModels}
        metrics={['accuracy', 'f1']}
        visualizationType="bar"
      />
    )
    expect(screen.getByTestId('bar-chart')).toBeInTheDocument()
  })

  it('renders with title', () => {
    render(
      <ModelComparisonChart
        models={sampleModels}
        metrics={['accuracy']}
        title="Model Comparison"
      />
    )
    expect(screen.getByText('Model Comparison')).toBeInTheDocument()
  })

  it('shows missing data warning when model has undefined metric', () => {
    const modelsWithMissing = [
      { model_id: 'gpt-4', metrics: { accuracy: 0.95 } },
      { model_id: 'claude-3', metrics: {} },
    ]
    render(
      <ModelComparisonChart
        models={modelsWithMissing}
        metrics={['accuracy', 'nonexistent']}
        visualizationType="bar"
      />
    )
    // Both models should trigger missing data for 'nonexistent'
    expect(screen.getByText(/Missing data for/)).toBeInTheDocument()
  })

  it('handles MetricValue with confidenceInterval for error calculation', () => {
    const modelsCI = [
      {
        model_id: 'model-a',
        metrics: {
          bleu: { value: 0.75, confidenceInterval: { lower: 0.7, upper: 0.8 } },
        },
      },
    ]
    render(
      <ModelComparisonChart
        models={modelsCI}
        metrics={['bleu']}
        visualizationType="bar"
        showErrorBars={true}
      />
    )
    expect(screen.getByTestId('bar-chart')).toBeInTheDocument()
  })
})
