/**
 * fn3 function coverage for ConfusionMatrixChart.tsx
 * Targets: plotData useMemo, layout useMemo, per-class metrics table rendering
 */

import React from 'react'
import { render, screen } from '@testing-library/react'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    locale: 'en',
    t: (key: string, vars?: any) => (vars ? `${key}:${JSON.stringify(vars)}` : key),
    changeLocale: jest.fn(),
    isReady: true,
  }),
}))

// Mock react-plotly.js dynamic import
jest.mock('next/dynamic', () => {
  return () => {
    const MockPlot = (props: any) => <div data-testid="plot" />
    MockPlot.displayName = 'MockPlot'
    return MockPlot
  }
})

import { ConfusionMatrixChart } from '../ConfusionMatrixChart'

describe('ConfusionMatrixChart fn3', () => {
  const sampleData = {
    field_name: 'label',
    labels: ['positive', 'negative', 'neutral'],
    matrix: [
      [50, 5, 2],
      [3, 45, 7],
      [1, 4, 40],
    ],
    accuracy: 0.86,
    precision_per_class: { positive: 0.92, negative: 0.83, neutral: 0.82 },
    recall_per_class: { positive: 0.88, negative: 0.82, neutral: 0.89 },
    f1_per_class: { positive: 0.9, negative: 0.82, neutral: 0.85 },
  }

  it('renders confusion matrix with data and per-class metrics', () => {
    render(<ConfusionMatrixChart data={sampleData} />)
    expect(screen.getByTestId('plot')).toBeInTheDocument()
    // Class labels should appear in the metrics table
    expect(screen.getByText('positive')).toBeInTheDocument()
    expect(screen.getByText('negative')).toBeInTheDocument()
    expect(screen.getByText('neutral')).toBeInTheDocument()
  })

  it('renders with custom title', () => {
    render(<ConfusionMatrixChart data={sampleData} title="My Classification" />)
    expect(screen.getByTestId('plot')).toBeInTheDocument()
  })

  it('renders with custom dimensions', () => {
    render(<ConfusionMatrixChart data={sampleData} width={500} height={500} />)
    expect(screen.getByTestId('plot')).toBeInTheDocument()
  })

  it('displays accuracy percentage', () => {
    render(<ConfusionMatrixChart data={sampleData} />)
    // Accuracy should be displayed as 86.00%
    expect(screen.getByText('86.00%')).toBeInTheDocument()
  })
})
